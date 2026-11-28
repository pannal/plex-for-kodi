# coding=utf-8
"""
Mutable state behind the Kodi stubs.

Every stub module (xbmc, xbmcgui, xbmcvfs, xbmcaddon, xbmcplugin) is a thin
shell that reads and writes this singleton, so a test can steer Kodi's answers
without monkeypatching anything:

    from kodienv import ENV
    ENV.regions["time"] = "%H:%M:%S"

`ENV.reset()` restores the defaults; `tests.KodiTestCase` calls it in setUp.
Note that PM4K reads a lot of Kodi state once, at import time, into module
level constants (util.timeFormat, util.DISPLAY_RESOLUTION, ...). Changing ENV
afterwards does not retroactively change those - call the relevant re-read
function (e.g. util.populateTimeFormat()) or test the function directly.
"""

from __future__ import absolute_import

from io import open

import atexit
import collections
import json
import os
import re
import shutil
import sys
import tempfile


REPO_ROOT = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

# Kodi log levels (Kodi 19+ numbering)
LOGDEBUG = 0
LOGINFO = 1
LOGWARNING = 2
LOGERROR = 3
LOGFATAL = 4
LOGNONE = 5

LOG_LEVEL_NAMES = {
    LOGDEBUG: "DEBUG",
    LOGINFO: "INFO",
    LOGWARNING: "WARNING",
    LOGERROR: "ERROR",
    LOGFATAL: "FATAL",
    LOGNONE: "NONE",
}

_PO_CTXT_RE = re.compile(r'^msgctxt\s+"#(\d+)"\s*$')
_PO_MSGID_RE = re.compile(r'^msgid\s+"(.*)"\s*$')
_PO_MSGSTR_RE = re.compile(r'^msgstr\s+"(.*)"\s*$')


def parse_strings_po(path):
    """
    Minimal Kodi strings.po reader: {numeric id: translated-or-english string}.

    Handles the multi-line form, where a long string is split over several
    quoted continuation lines - reading only the first line silently truncates
    those entries and makes any msgid comparison wrong.

    Kodi itself falls back to msgid when msgstr is empty, which is how the
    en_gb file is written (every msgstr is ""), so mirror that.
    """
    with open(path, "r", encoding="utf-8") as fp:
        lines = fp.read().split("\n")

    def collect(index, prefix):
        """(joined text, index after the block) for a msgid/msgstr block."""
        if index >= len(lines) or not lines[index].startswith(prefix):
            return None, index
        text = lines[index][len(prefix):-1]
        index += 1
        while index < len(lines) and lines[index].startswith('"'):
            text += lines[index][1:-1]
            index += 1
        return text, index

    strings = {}
    i = 0
    while i < len(lines):
        match = _PO_CTXT_RE.match(lines[i])
        if not match:
            i += 1
            continue
        ident = int(match.group(1))
        i += 1
        msgid, i = collect(i, 'msgid "')
        msgstr, i = collect(i, 'msgstr "')
        strings[ident] = msgstr or msgid or ""
    return strings


class JSONRPCError(Exception):
    pass


class KodiEnv(object):
    def __init__(self):
        self._tmp_root = tempfile.mkdtemp(prefix="pm4k-tests-")
        atexit.register(shutil.rmtree, self._tmp_root, True)
        self._strings_cache = {}
        self.reset()

    # ------------------------------------------------------------------ paths
    @property
    def tmp_root(self):
        return self._tmp_root

    def _mk(self, *parts):
        path = os.path.join(self._tmp_root, *parts)
        if not os.path.isdir(path):
            os.makedirs(path)
        return path

    def reset(self):
        """Restore every piece of steerable Kodi state to its default."""
        self.temp_dir = self._mk("temp")
        self.home_dir = self._mk("home")
        self.profile_root = self._mk("profile")
        self.addon_data_dir = self._mk("profile", "addon_data", "script.plexmod")

        # xbmc.log() output, newest last: (message, level)
        self.log_lines = []
        # xbmc.executebuiltin() calls, in order
        self.builtins = []
        # xbmc.sleep() durations, in ms
        self.sleeps = []
        # xbmc.shutdown()/restart() call counters
        self.power_calls = []

        # xbmcaddon settings store, shared by every Addon() instance the way
        # Kodi's own settings store is
        self.settings = {}

        self.infolabels = {
            "System.BuildVersion": ("18.9 (18.9.0)" if sys.version_info[0] == 2
                                    else "21.2 (21.2.0) Git:20250101-abcdef1"),
            "System.Time": "13:45:00",
            "System.CurrentWindow": "Home",
            # lib.cache parses this with [:-2], so the "MB" suffix matters
            "System.Memory(free)": "2048MB",
            "System.Memory(total)": "4096MB",
            "System.FreeSpace": "100GB",
        }
        self.regions = {
            "time": "%H:%M:%S",
            "meridiem": "%p",
            "dateshort": "%d/%m/%Y",
            "datelong": "%A, %d %B %Y",
        }
        self.cond_visibility = {}
        self.skin_dir = "skin.estuary"
        self.user_agent = "Kodi/21.2 (X11; Linux x86_64)"

        self.screen = [1920, 1080]
        self.current_window_id = 10000
        self.current_dialog_id = 9999
        # {window id: {property: value}}
        self.window_props = collections.defaultdict(dict)

        # scripted answers popped by xbmcgui.Dialog methods
        self.dialog_answers = collections.deque()
        # every dialog invocation, as (method, args, kwargs)
        self.dialog_calls = []

        self.abort_requested = False
        # waitForAbort() returns this; set True to simulate an abort
        self.abort_on_wait = False
        self.waits = []

        # Kodi's own settings, as answered by Settings.GetSettingValue
        self.kodi_settings = dict(self.KODI_SETTING_DEFAULTS)
        self.jsonrpc_responses = {
            "Settings.GetSettingValue": self._default_setting_value,
            "Settings.SetSettingValue": self._set_setting_value,
            "Files.GetSources": {"sources": []},
            "Application.GetProperties": {"volume": 100, "muted": False},
        }
        self.jsonrpc_calls = []

        # Read from the working tree's addon.xml rather than hardcoded, so the
        # harness mirrors whichever variant is checked out. The name matters:
        # lib.kodi_util derives FROM_KODI_REPOSITORY from it, and the Kodi-repo
        # build ("PM4K for Plex") is forbidden from editing advancedsettings.xml.
        self.addon_info = {
            "id": "script.plexmod",
            "name": self._addon_attr("name", "Plex"),
            "version": self._addon_attr("version", "0.0.0"),
            "path": REPO_ROOT,
            "profile": "special://profile/addon_data/script.plexmod/",
            "icon": os.path.join(REPO_ROOT, "icon2.png"),
            "fanart": os.path.join(REPO_ROOT, "fanart.png"),
            "author": "pannal",
        }
        self.language = "en_gb"

    # --------------------------------------------------------------- helpers
    @staticmethod
    def _addon_attr(attr, fallback):
        """Pull an <addon> attribute straight out of the working tree's addon.xml."""
        try:
            with open(os.path.join(REPO_ROOT, "addon.xml"), "r", encoding="utf-8") as fp:
                head = fp.read(2048)
        except (IOError, OSError):
            return fallback
        match = re.search(r'\b{0}="([^"]*)"'.format(attr), head)
        return match.group(1) if match else fallback

    # Kodi's own Settings.GetSettingValue answers. Deliberately *not* all of
    # Kodi's shipped defaults: locale.timeformat/shortdateformat default to
    # "regional" in Kodi, which sends lib.util down its legacy detection path.
    # Explicit formats keep the harness deterministic; the tests that care
    # about the regional path set it to "regional" themselves.
    KODI_SETTING_DEFAULTS = {
        "locale.timeformat": "HH:mm:ss",
        "locale.shortdateformat": "DD/MM/YYYY",
        "locale.language": "resource.language.en_gb",
        "slideshow.staytime": 5,
        "videoplayer.seeksteps": [-600, -300, -180, -60, -30, -10, 10, 30, 60, 180, 300, 600],
        "audiooutput.channels": 1,
        "filecache.memorysize": 20,       # MB
        "filecache.readfactor": 400,      # percent; lib.cache divides by 100
        "services.devicename": "Kodi",
    }

    def _default_setting_value(self, params):
        key = params.get("setting")
        if key in self.kodi_settings:
            return {"value": self.kodi_settings[key]}
        raise JSONRPCError("Unknown Kodi setting requested: {0}".format(key))

    def _set_setting_value(self, params):
        self.kodi_settings[params["setting"]] = params["value"]
        return True

    def strings(self, language=None):
        """Real strings.po contents for a language folder, parsed once."""
        language = language or self.language
        if language not in self._strings_cache:
            path = os.path.join(REPO_ROOT, "resources", "language",
                                "resource.language.{}".format(language), "strings.po")
            self._strings_cache[language] = parse_strings_po(path) if os.path.exists(path) else {}
        return self._strings_cache[language]

    def translate_path(self, path):
        """special:// -> a real, writable path under the test temp root."""
        if not path.startswith("special://"):
            return path
        rest = path[len("special://"):]
        head, _, tail = rest.partition("/")
        root = {
            "temp": self.temp_dir,
            "home": self.home_dir,
            "profile": self.profile_root,
            "masterprofile": self.profile_root,
            "userdata": self.profile_root,
            "logpath": self.temp_dir,
        }.get(head, self.home_dir)
        return os.path.join(root, tail) if tail else root + os.sep

    def execute_jsonrpc(self, payload):
        command = json.loads(payload)
        method = command.get("method")
        params = command.get("params", {})
        self.jsonrpc_calls.append((method, params))

        if method not in self.jsonrpc_responses:
            return json.dumps({"jsonrpc": "2.0", "id": command.get("id"),
                               "error": {"code": -32601, "message": "Method not found."}})

        result = self.jsonrpc_responses[method]
        try:
            if callable(result):
                result = result(params)
        except JSONRPCError as exc:
            # surface it the way Kodi would, so lib.kodijsonrpc raises and the
            # addon's own fallback path runs
            return json.dumps({"jsonrpc": "2.0", "id": command.get("id"),
                               "error": {"code": -32602, "message": str(exc)}})
        return json.dumps({"jsonrpc": "2.0", "id": command.get("id"), "result": result})

    def log(self, message, level=LOGDEBUG):
        self.log_lines.append((message, level))

    def logged(self, needle, level=None):
        """True if any logged line contains `needle` (at `level`, if given)."""
        return any(needle in msg and (level is None or lvl == level)
                   for msg, lvl in self.log_lines)

    def builtin_called(self, needle):
        return any(needle in call for call in self.builtins)


ENV = KodiEnv()
