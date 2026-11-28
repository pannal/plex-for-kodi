# coding=utf-8
"""Run unchanged under Python 2.7/Leia and Python 3/current Kodi.

These are offline checks; Kodi's native GUI and playback still need device QA.
"""
from __future__ import absolute_import

import gc
import os
import subprocess
import sys
import shutil
import tempfile
import unittest
import weakref
from xml.etree import ElementTree

import six

from tests import REPO_ROOT
from tests.base import ensure_plex_interface
from plexnet.signalslot import Signal, Slot
from plexnet.signalslot._weakmethod import WeakMethod


class Receiver(object):
    def callback(self, **kwargs):
        return kwargs.get('value')


class RuntimeCompatibilityTest(unittest.TestCase):
    def test_all_themes_render_parseable_window_xml(self):
        from lib.templating.context import TEMPLATE_CONTEXTS
        from tests.base import make_engine
        target = tempfile.mkdtemp(prefix='pm4k-runtime-templates-')
        try:
            for theme in sorted(TEMPLATE_CONTEXTS['themes']):
                engine = make_engine(target)
                engine.apply(theme, lambda *args: None)
                self.assertTrue(engine.TEMPLATES)
                for name in engine.TEMPLATES:
                    path = os.path.join(target, 'script-plex-' + name + '.xml')
                    self.assertIsNotNone(ElementTree.parse(path).getroot())
                    os.remove(path)
        finally:
            shutil.rmtree(target)

    def test_cancelled_tasks_and_undefined_values_are_false(self):
        from lib.backgroundthread import Task
        from ibis.context import Undefined
        task = Task()
        self.assertTrue(task)
        task.cancel()
        self.assertFalse(task)
        self.assertFalse(Undefined())
        self.assertEqual(list(Undefined()), [])

    def test_startup_import_in_fresh_runtime(self):
        code = """
import os, sys, traceback
import tests
from kodienv import ENV
ENV.infolabels['System.BuildVersion'] = '18.9' if sys.version_info[0] == 2 else '21.2'
ENV.abort_requested = True
try:
    import lib.main
    from lib.kodi_util import KODI_VERSION_MAJOR
    assert KODI_VERSION_MAJOR == (18 if sys.version_info[0] == 2 else 21)
except BaseException:
    traceback.print_exc()
    sys.stderr.flush()
    os._exit(1)
os._exit(0)
"""
        subprocess.check_call([sys.executable, '-B', '-c', code], cwd=REPO_ROOT)

    def test_non_ascii_sources_declare_encoding(self):
        # compile(bytes) alone does not reliably detect missing Python 2 cookies.
        import re
        cookie = re.compile(br'coding[:=]\s*[-\w.]+')
        for root, dirs, files in os.walk(os.path.join(REPO_ROOT, 'lib')):
            dirs[:] = [d for d in dirs if d != '__pycache__']
            for name in files:
                if not name.endswith('.py'):
                    continue
                path = os.path.join(root, name)
                with open(path, 'rb') as source:
                    data = source.read()
                if any(value > 127 for value in bytearray(data)):
                    self.assertTrue(cookie.search(b'\n'.join(data.splitlines()[:2])) or
                                    data.startswith(b'\xef\xbb\xbf'), path)

    def test_backport_keeps_method_callable_without_retaining_owner(self):
        receiver = Receiver()
        reference = WeakMethod(receiver.callback)
        self.assertEqual(reference()(value=42), 42)
        owner = weakref.ref(receiver)
        del receiver
        gc.collect()
        self.assertIsNone(owner())
        self.assertIsNone(reference())

    def test_backport_does_not_retain_replaced_function(self):
        class TransientReceiver(object):
            def callback(self, **kwargs):
                pass
        receiver = TransientReceiver()
        reference = WeakMethod(receiver.callback)
        del TransientReceiver.callback
        gc.collect()
        self.assertIsNone(reference())

    def test_weak_slot_dispatch_and_disconnect(self):
        receiver = Receiver()
        signal = Signal()
        signal.connect(Slot(receiver.callback, weak=True))
        self.assertEqual(signal.emit(value=42), 42)
        signal.disconnect(receiver.callback)
        self.assertEqual(signal.slots, [])

    def test_weak_slot_is_pruned_after_owner_dies(self):
        receiver = Receiver()
        signal = Signal()
        signal.connect(Slot(receiver.callback, weak=True))
        owner = weakref.ref(receiver)
        del receiver
        gc.collect()
        self.assertIsNone(owner())
        self.assertEqual(signal.slots, [])

    def test_handler_exit_subscription_does_not_retain_handler(self):
        from kodienv import ENV
        ENV.abort_requested = True
        from lib import player, util
        from plexnet.signalsmixin import SignalsMixin
        original = util.MONITOR
        monitor = SignalsMixin()
        try:
            util.MONITOR = monitor
            handler = player.BasePlayerHandler.__new__(player.BasePlayerHandler)
            handler._exitMonitor = None
            handler._hookExit()
            owner = weakref.ref(handler)
            del handler
            gc.collect()
            self.assertIsNone(owner())
            self.assertFalse(any(s.slots for s in monitor._signals.values()))
        finally:
            util.MONITOR = original

    def test_playback_metadata_preserves_unicode_file_path(self):
        from plexnet import plexplayer, plexobjects
        from plexnet.util import AttributeDict as Obj
        ensure_plex_interface()
        part = Obj(file=plexobjects.PlexValue(u'/media/Gr\u00fc\u00dfe/\u6771\u4eac.mkv'),
                   duration=plexobjects.PlexValue('60000'), size='100',
                   isIndexed=lambda: False)
        player = plexplayer.PlexPlayer.__new__(plexplayer.PlexPlayer)
        player.item = Obj(getServer=lambda: None)
        player.media = Obj(parts=[part], duration=plexobjects.PlexValue('60000'),
                           getVideoResolution=lambda: 320, videoFrameRate='24p')
        player.choice = Obj(isDirectPlayable=True)
        player.seekValue = 0
        player.shouldSuppressSubtitleForAudioLanguage = lambda: True
        player.buildDirectPlay = lambda obj, index: obj
        metadata = player._build(directPlay=True)
        self.assertEqual(six.ensure_text(metadata.path), six.text_type(part.file))
        self.assertIsInstance(metadata.path, str)
