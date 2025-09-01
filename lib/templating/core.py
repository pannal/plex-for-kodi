# coding=utf-8
import os
import glob
import shutil

from pprint import pformat
from kodi_six import xbmcvfs, xbmc
from ibis.context import ContextDict
from lib.logging import log as LOG, log_error as ERROR
from .util import deep_update
from ..util import PROFILE
from lib.os_utils import fast_iglob
from .filters import *


def build_stack(inheritor, sources):
    inherit_from = inheritor.pop("INHERIT", None)
    data_stack = [inheritor]
    while inherit_from:
        inheritor = ContextDict(copy.deepcopy(sources[inherit_from]))
        inherit_from = inheritor.pop("INHERIT", None)
        data_stack.append(inheritor)

    return data_stack


def prepare_template_data(thm, context):
    template_context = {"theme": {}}

    theme_data = {"INHERIT": thm}

    # data stack
    data_stack = build_stack(theme_data, context.pop("themes"))

    # build inheritance stack
    while data_stack:
        deep_update(template_context["theme"], data_stack.pop())

    for ctx in ("core", "indicators",):
        # simple overrides
        if "START" not in context[ctx]:
            data_stack.append(context[ctx])
        else:
            # overrides with inheritance
            data_stack = build_stack(context[ctx]["START"], context[ctx])
        template_context[ctx] = ContextDict()
        while data_stack:
            deep_update(template_context[ctx], data_stack.pop())

    return ContextDict(template_context)


class TemplateEngine(object):
    loader = None
    target_dir = None
    template_dir = None
    custom_template_dir = None
    initialized = False
    context = None
    debug_log = None
    TEMPLATES = None

    def init(self, target_dir, template_dir, custom_template_dir):
        self.target_dir = target_dir


        # Alternative to checking env var: automatically set if dir isn't
        # writable with `if not os.access(path, os.W_OK):`
        if os.getenv("INSTALLATION_DIR_AVOID_WRITE"):
            # Use the user addon data directory in installations where the extension installation directory is not writable, for example when the addon is installed through the system package manager
            # Redirect template write target_dir to writable addon_data
            writable_base = os.path.join(PROFILE, "resources/skins/Main/1080i")
            os.makedirs(writable_base, exist_ok=True)
            # Link media dir into addon dir, so templates can access it via relative path
            link_path = os.path.join(PROFILE, "resources/skins/Main/media")
            media_src = os.path.join(os.path.dirname(target_dir), "media")
            if not os.path.exists(link_path):
                try:
                    os.symlink(media_src, link_path, True)
                except (OSError, NotImplementedError):
                    # If symlink fails (eg on windows without admin access), copy instead
                    shutil.copytree(media_src, link_path)
            self.target_dir = writable_base
        self.template_dir = template_dir
        self.custom_template_dir = custom_template_dir
        self.get_available_templates()
        paths = [custom_template_dir, self.template_dir]

        LOG("Looking for templates in: {}", paths)
        self.prepare_loader(paths)
        self.initialized = True

    def get_available_templates(self):
        tpls = []
        for f in fast_iglob(os.path.join(self.template_dir, "script-plex-*.xml.tpl")):
            tpls.append(f.split("script-plex-")[1].split(".xml.tpl")[0])
        self.TEMPLATES = tpls

    def prepare_loader(self, fns):
        self.loader = ibis.loaders.FileLoader(*fns)
        ibis.loader = self.loader

    def compile(self, fn, data):
        template = self.loader(fn)
        return template.render(data)

    def write(self, template, data, retry=0):
        def ensure_file_exists(file_name, expected_size):
            if xbmcvfs.exists(file_name):
                s = xbmcvfs.Stat(file_name)
                size = s.st_size()
                return size == expected_size
            return False

        leeway = 50
        expected_len = len(data)
        # write final file
        count = 0
        fn = os.path.join(self.target_dir, "script-plex-{}.xml".format(template))
        f = xbmcvfs.File(fn, "w")

        try:
            success = f.write(data)

            while not success and count < leeway:
                success = f.write(data)
                xbmc.sleep(100)
                count += 1
        finally:
            f.close()

        count = 0
        exists = ensure_file_exists(fn, expected_len)
        while not exists and count < leeway:
            xbmc.sleep(100)
            exists = ensure_file_exists(fn, expected_len)
            count += 1

        if not exists:
            if retry > 0:
                raise OSError("Timed out while waiting for template {} to be saved to disk".format(fn))
            return self.write(template, data, retry=1)
        return True

    def apply(self, theme, update_callback, templates=None):
        templates = self.TEMPLATES if templates is None else templates
        template_context = prepare_template_data(theme, self.context)
        self.debug_log("Final template context: {}".format(pformat(template_context)))

        progress = {"at": 0, "steps": len(templates)}

        def step(message):
            progress["at"] += 1
            update_callback(progress["at"], progress["steps"], message)

        custom_templates = []
        if theme == "custom":
            progress["steps"] += 1
            step("custom_templates")
            custom_templates = [f.split("script-plex-")[1].split(".custom.xml.tpl")[0] for f in
                                glob.iglob(os.path.join(self.custom_template_dir, "*.custom.xml.tpl"))]
            if not custom_templates:
                LOG("No custom templates found in: {}", self.custom_template_dir)

        applied = []
        for template in templates:
            fn = "script-plex-{}{}.xml.tpl".format(template, ".custom" if theme == "custom" and
                                                   template in custom_templates else "")
            compiled_template = self.compile(fn, template_context)
            if self.write(template, compiled_template):
                applied.append(template)
            else:
                raise Exception("Couldn't write script-plex-{}.xml", template)
            step(template)

        update_callback(progress["steps"], progress["steps"], "complete")
        LOG('Using theme {} for: {}', theme, applied)


engine = TemplateEngine()
