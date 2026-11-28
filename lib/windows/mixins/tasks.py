# coding=utf-8

from lib import backgroundthread, logging as log, monitor
from lib.windows import windowutils


class SimpleTask(backgroundthread.Task):
    def setup(self, func, cb, *args, **kwargs):
        self.func = func
        self.cb = cb
        self.args = args
        self.kwargs = kwargs
        return self

    def run(self):
        try:
            self.func(*self.args, **self.kwargs)
        except:
            log.ERROR("Task failed: {} (args: {}, kwargs: {})", self.func, self.args, self.kwargs)
        finally:
            self.cb(self)


class TasksMixin(object):
    def __init__(self):
        self.tasks = backgroundthread.Tasks()

    def postpone_simple(self, func, *args, **kwargs):
        task = SimpleTask().setup(func, self.default_callback, *args, **kwargs)
        backgroundthread.BGThreader.addTask(task)

    def batch_simple(self, tasks):
        batch = []
        for func, args, kwargs in tasks:
            task = SimpleTask().setup(func, self.default_callback, *(args or []), **(kwargs or {}))
            batch.append(task)
        backgroundthread.BGThreader.addTasks(batch)

    def default_callback(self, task):
        try:
            self.tasks.remove(task)
            del task
        except:
            pass

    def doClose(self):
        if self.tasks:
            try:
                log.DEBUG_LOG("Killing {} tasks".format(len(self.tasks)))
                windowutils.HOME.stopRetryingRequests()
                self.tasks.kill()

                if any(not t.finished for t in self.tasks):
                    log.DEBUG_LOG("Still waiting for tasks to finish")

                waited = 0
                while any(not t.finished for t in self.tasks) and waited < monitor.MONITOR.waitAmount(1):
                    monitor.MONITOR.waitFor()
                    waited += 1

                self.tasks = None
            except:
                pass
            finally:
                windowutils.HOME.stopRetryingRequests(False)