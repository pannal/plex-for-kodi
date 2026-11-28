# coding=utf-8
"""
Every xbmcvfs.File handle in lib/ must be closed on the failure path too.

The shape that bites is:

    f = xbmcvfs.File(path)
    data = json.loads(f.read())   # raises on malformed input
    f.close()                     # never runs

On a Kodi box that leaks a VFS handle every time a config file is corrupt.
Python surfaces it as a ResourceWarning, but that fires during garbage
collection - outside any test's context - so it cannot be turned into a test
failure. This reads the source instead, which is deterministic.

The repo's pattern is try/finally rather than `with`: xbmcvfs.File context
manager support is not verified for the Kodi 18 branch, so `with` is accepted
here but not used by the addon.
"""

from __future__ import absolute_import

import ast
import os

from .base import KodiTestCase
from . import REPO_ROOT

LIB_DIR = os.path.join(REPO_ROOT, "lib")


def python_sources():
    """Every addon-owned .py file; vendored packages are not ours to fix."""
    for root, dirs, files in os.walk(LIB_DIR):
        if "_included_packages" in root:
            continue
        for fn in sorted(files):
            if fn.endswith(".py"):
                yield os.path.join(root, fn)


def names_closed_in_finally(scope):
    """Names `x` for which `x.close()` appears in some finally: block."""
    closed = set()
    for node in ast.walk(scope):
        if not isinstance(node, ast.Try):
            continue
        for stmt in node.finalbody:
            for sub in ast.walk(stmt):
                if (isinstance(sub, ast.Call) and isinstance(sub.func, ast.Attribute)
                        and sub.func.attr == "close"
                        and isinstance(sub.func.value, ast.Name)):
                    closed.add(sub.func.value.id)
    return closed


def names_bound_by_with(scope):
    for node in ast.walk(scope):
        if not isinstance(node, ast.With):
            continue
        for item in node.items:
            if isinstance(item.optional_vars, ast.Name):
                yield item.optional_vars.id


def vfs_file_assignments(scope):
    """(name, lineno) for each `x = xbmcvfs.File(...)` in this scope."""
    for node in ast.walk(scope):
        if not (isinstance(node, ast.Assign) and isinstance(node.value, ast.Call)
                and isinstance(node.value.func, ast.Attribute)
                and node.value.func.attr == "File"
                and getattr(node.value.func.value, "id", "") == "xbmcvfs"):
            continue
        target = node.targets[0]
        if isinstance(target, ast.Name):
            yield target.id, node.lineno


class VfsHandleTest(KodiTestCase):
    def test_every_vfs_file_is_closed_in_a_finally(self):
        unprotected, total = [], 0
        for path in python_sources():
            with open(path, "r", encoding="utf-8") as fp:
                tree = ast.parse(fp.read())
            for scope in ast.walk(tree):
                if not isinstance(scope, (ast.Module, ast.FunctionDef, ast.AsyncFunctionDef)):
                    continue
                safe = names_closed_in_finally(scope) | set(names_bound_by_with(scope))
                for name, lineno in vfs_file_assignments(scope):
                    total += 1
                    if name not in safe:
                        unprotected.append("{0}:{1} ({2})".format(
                            os.path.relpath(path, REPO_ROOT), lineno, name))

        self.assertTrue(total, "found no xbmcvfs.File() calls - has lib/ moved?")
        self.assertEqual([], sorted(set(unprotected)),
                         "xbmcvfs.File handles that leak when the body raises")

    def test_the_scan_reaches_the_known_call_sites(self):
        """
        Guards the test above against silently scanning nothing: these files are
        known to open VFS handles.
        """
        expected = {"advancedsettings.py", "cache.py", "data_cache.py", "path_mapping.py",
                    "playback_utils.py", "seamless_branching.py", "util.py"}
        found = set()
        for path in python_sources():
            with open(path, "r", encoding="utf-8") as fp:
                if "xbmcvfs.File(" in fp.read():
                    found.add(os.path.basename(path))
        self.assertEqual(set(), expected - found,
                         "expected these to still open xbmcvfs handles")
