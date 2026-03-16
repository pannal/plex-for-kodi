from __future__ import absolute_import
import six.moves.queue
import heapq
from kodi_six import xbmc
from .monitor import MONITOR
from .settings_util import getSetting
from . import logging
from .kodi_util import ENABLE_HIGH_CONCURRENCY
from plexnet import threadutils
from six.moves import range


class Tasks(list):
    def add(self, task):
        for t in self:
            if not t.isValid():
                self.remove(t)

        if isinstance(task, list):
            self += task
        else:
            self.append(task)

    def cancel(self):
        while self:
            self.pop().cancel()

    def kill(self):
        self.cancel()
        BGThreader.kill()


class Task:
    def __init__(self, priority=None):
        self._priority = priority
        self._canceled = False
        self.finished = False

    def __cmp__(self, other):
        return self._priority - other._priority

    def __le__(self, other):
        return self._priority < other._priority

    def __gt__(self, other):
        return self._priority > other._priority

    def __bool__(self):
        return self.isValid()

    def start(self):
        BGThreader.addTask(self)

    def _run(self):
        self.run()
        self.finished = True

    def run(self):
        pass

    def cancel(self):
        self._canceled = True

    def isCanceled(self):
        return self._canceled or MONITOR.abortRequested()

    def isValid(self):
        return not self.finished and not self._canceled


class MutablePriorityQueue(six.moves.queue.PriorityQueue):
    def _get(self, heappop=heapq.heappop):
        self.queue.sort()
        return heappop(self.queue)

    def lowest(self):
        """Return the lowest priority item in the queue (not reliable!)."""
        self.mutex.acquire()
        try:
            lowest = self.queue and min(self.queue) or None
        except:
            lowest = None
            logging.ERROR()
        finally:
            self.mutex.release()
        return lowest


class BackgroundWorker:
    def __init__(self, queue, name=None):
        self._queue = queue
        self.name = name
        self._thread = None
        self._abort = False
        self._task = None

    def _runTask(self, task):
        if task._canceled:
            return
        try:
            task._run()
        except:
            logging.ERROR()

    def abort(self):
        self._abort = True
        return self

    def aborted(self):
        return self._abort or MONITOR.abortRequested()

    def start(self):
        if self._thread and self._thread.is_alive():
            return

        self._thread = threadutils.KillableThread(target=self._queueLoop, name='BACKGROUND-WORKER({0})'.format(self.name))
        self._thread.start()

    def _queueLoop(self):
        if self._queue.empty():
            return

        logging.DEBUG_LOG('BGThreader: ({0}): Active', self.name)
        try:
            while not self.aborted():
                self._task = self._queue.get_nowait()
                self._runTask(self._task)
                self._queue.task_done()
                self._task = None
        except six.moves.queue.Empty:
            logging.DEBUG_LOG('BGThreader ({0}): Idle', self.name)

    def shutdown(self):
        self.abort()

        if self._task:
            self._task.cancel()

        if self._thread and self._thread.is_alive():
            logging.DEBUG_LOG('BGThreader: thread ({0}): Waiting...', self.name)
            self._thread.join()
            logging.DEBUG_LOG('BGThreader: thread ({0}): Done', self.name)

    def working(self):
        return self._thread and self._thread.is_alive()

    def kill(self):
        if self._thread and self._thread.is_alive():
            logging.DEBUG_LOG('BGThreader: thread ({0}): Waiting...', self.name)
            self._thread.join()
            logging.DEBUG_LOG('BGThreader: thread ({0}): Done', self.name)


class BackgroundThreader:
    def __init__(self, name=None, worker_count=5):
        self.name = name
        self._queue = MutablePriorityQueue()
        self._abort = False
        self._priority = -1
        self.workers = [BackgroundWorker(self._queue, 'queue.{0}:worker.{1}'.format(self.name, x)) for x in range(worker_count)]

    def _nextPriority(self):
        self._priority += 1
        return self._priority

    def abort(self):
        self._abort = True
        for w in self.workers:
            w.abort()
        return self

    def aborted(self):
        return self._abort or MONITOR.abortRequested()

    def shutdown(self):
        self.abort()

        for w in self.workers:
            w.shutdown()

    def addTask(self, task):
        task._priority = self._nextPriority()
        self._queue.put(task)
        self.startWorkers()

    def addTasks(self, tasks):
        for t in tasks:
            t._priority = self._nextPriority()
            self._queue.put(t)

        self.startWorkers()

    def addTasksToFront(self, tasks):
        lowest = self.getLowestPrority()
        if lowest is None:
            return self.addTasks(tasks)

        p = lowest - len(tasks)
        for t in tasks:
            t._priority = p
            self._queue.put(t)
            p += 1

        self.startWorkers()

    def startWorkers(self):
        for w in self.workers:
            w.start()

    def working(self):
        return not self._queue.empty() or self.hasTask()

    def hasTask(self):
        return any([w.working() for w in self.workers])

    def getLowestPrority(self):
        lowest = self._queue.lowest()
        if not lowest:
            return None

        return lowest._priority

    def moveToFront(self, qitem):
        lowest = self.getLowestPrority()
        if lowest is None:
            return

        qitem._priority = lowest - 1

    def kill(self):
        for w in self.workers:
            w.kill()


class ThreaderManager:
    def __init__(self, worker_count=5):
        self.index = 0
        self.abandoned = []
        self.threader = BackgroundThreader(str(self.index), worker_count=worker_count)

    def __getattr__(self, name):
        return getattr(self.threader, name)

    def reset(self):
        if self.threader._queue.empty() and not self.threader.hasTask():
            return

        self.index += 1
        self.abandoned.append(self.threader.abort())
        self.threader = BackgroundThreader(str(self.index))

    def shutdown(self):
        self.threader.shutdown()
        for a in self.abandoned:
            a.shutdown()

    def kill(self):
        self.threader.kill()

# clamp worker count to 3 maximum if we're below python 3.14
BGThreader = ThreaderManager(worker_count=min(getSetting('worker_count', 3), ENABLE_HIGH_CONCURRENCY and 32 or 3))
