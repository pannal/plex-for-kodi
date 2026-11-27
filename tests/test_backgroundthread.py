# coding=utf-8
"""Abandon pending window callbacks without cancelling live playback owners."""
from __future__ import absolute_import

import gc
import threading
import weakref
from unittest.mock import patch

from lib import backgroundthread
from lib.windows import kodigui
from lib.windows.mixins.tasks import SimpleTask
from tests.base import KodiTestCase


class Window(kodigui.ControlledWindow):
    def work(self):
        pass


def noop(*args):
    pass


class BackgroundLifetimeTest(KodiTestCase):
    def test_reset_discards_pending_window_callbacks(self):
        manager = backgroundthread.ThreaderManager(worker_count=0)
        window = Window.__new__(Window)
        task = SimpleTask().setup(window.work, noop)
        manager.addTask(task)
        task_ref, window_ref = weakref.ref(task), weakref.ref(window)
        del task, window
        old = manager.threader
        manager.reset()
        gc.collect()
        self.assertIsNone(window_ref())
        self.assertIsNone(task_ref())
        self.assertTrue(old._queue.empty())
        self.assertEqual(old._queue.unfinished_tasks, 0)
        # A later idle reset also releases finished abandoned worker objects.
        manager.reset()
        self.assertEqual(manager.abandoned, [])

    def test_pending_discard_does_not_call_playback_cancelling_override(self):
        effects = []

        class PlaybackTask(backgroundthread.Task):
            def cancel(self):
                effects.append('stopped current playback')

        threader = backgroundthread.BackgroundThreader(worker_count=0)
        task = PlaybackTask()
        threader.addTask(task)
        threader.abort()
        threader.abort()
        self.assertTrue(task._canceled)
        self.assertEqual(effects, [])
        self.assertEqual(threader._queue.unfinished_tasks, 0)

    def test_methods_captured_before_reset_cannot_repopulate_abandoned_queue(self):
        manager = backgroundthread.ThreaderManager(worker_count=0)
        old = manager.threader
        add, batch, front = manager.addTask, manager.addTasks, manager.addTasksToFront
        add(backgroundthread.Task())
        manager.reset()
        window = Window.__new__(Window)
        tasks = [SimpleTask().setup(window.work, noop) for _ in range(3)]
        ref = weakref.ref(window)
        add(tasks[0])
        batch(tasks[1:2])
        front(tasks[2:])
        self.assertTrue(all(task._canceled for task in tasks))
        del window, tasks
        gc.collect()
        self.assertIsNone(ref())
        self.assertTrue(old._queue.empty())
        self.assertEqual(old._queue.unfinished_tasks, 0)

    def test_abort_preserves_running_task_but_drops_pending_callbacks(self):
        entered, release = threading.Event(), threading.Event()
        calls = []

        class RunningTask(backgroundthread.Task):
            def run(self):
                entered.set()
                if not release.wait(2):
                    calls.append('timeout')
                calls.append('finished')

        threader = backgroundthread.BackgroundThreader(worker_count=1)
        running = RunningTask()
        with patch.object(backgroundthread.MONITOR, 'abortRequested', lambda: False):
            threader.addTask(running)
            try:
                self.assertTrue(entered.wait(2))
                window = Window.__new__(Window)
                pending = SimpleTask().setup(window.work, noop)
                window_ref = weakref.ref(window)
                threader.addTask(pending)
                del window, pending
                threader.abort()
                gc.collect()
                self.assertIsNone(window_ref())
                self.assertFalse(running._canceled)
                self.assertFalse(running.finished)
            finally:
                release.set()
                threader.workers[0]._thread.join(2)
        self.assertFalse(threader.working())
        self.assertEqual(calls, ['finished'])
        self.assertTrue(running.finished)
        self.assertIsNone(threader.workers[0]._task)
        self.assertEqual(threader._queue.unfinished_tasks, 0)

    def test_abort_between_dequeue_and_run_does_not_execute_task(self):
        queue = backgroundthread.MutablePriorityQueue()
        worker = backgroundthread.BackgroundWorker(queue)
        calls = []
        task = SimpleTask().setup(lambda: calls.append('ran'), noop)
        worker.abort()
        worker._runTask(task)
        self.assertEqual(calls, [])

    def test_worker_releases_task_even_on_base_exception(self):
        queue = backgroundthread.MutablePriorityQueue()
        task = backgroundthread.Task()
        queue.put(task)
        worker = backgroundthread.BackgroundWorker(queue)
        # Inject an interruption at the worker boundary, outside _runTask's
        # ordinary exception handler (the worker uses KillableThread).
        with patch.object(backgroundthread.MONITOR, 'abortRequested', lambda: False), \
                patch.object(worker, '_runTask', side_effect=SystemExit):
            with self.assertRaises(SystemExit):
                worker._queueLoop()
        self.assertIsNone(worker._task)
        self.assertEqual(queue.unfinished_tasks, 0)
