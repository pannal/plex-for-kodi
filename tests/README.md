# PM4K tests

Runs the addon outside Kodi by putting fake `xbmc*` modules on `sys.path`
before anything under `lib/` is imported.

## Running

```sh
python3 -m pytest                          # nicest output
python3 -m pytest tests/test_templates.py  # one area
python3 -m unittest discover -s tests -t . # no dependencies at all
```

Tests are plain `unittest.TestCase` classes, so both runners work. pytest is
optional and only buys better output and `-k` filtering.

Nothing needs a Kodi install, a Plex server or a network connection. Nothing is
written into the working tree — every path the addon would write to is
redirected into a temp directory that is removed on exit.

## Layout

```
tests/
  __init__.py            sys.path bootstrap (runs before any test module)
  base.py                KodiTestCase, template-engine and fixture helpers
  kodistubs/             the fake Kodi API
    kodienv.py           ENV: all steerable Kodi state, plus reset()
    xbmc.py xbmcgui.py xbmcvfs.py xbmcaddon.py xbmcplugin.py
    kodi_six/            the shim PM4K actually imports
  fixtures/plexnet/      recorded Plex API responses
  test_*.py
```

`kodistubs/` is a `sys.path` entry, not a package — that is what makes
`import xbmc` inside `lib/` resolve to the fake.

## Steering Kodi from a test

Everything the fakes answer with lives on one object:

```python
from kodienv import ENV

ENV.settings["path_mapping"] = "true"          # addon settings
ENV.kodi_settings["locale.timeformat"] = "regional"  # Kodi's own settings
ENV.infolabels["System.Time"] = "09:45:00"
ENV.regions["time"] = "%H%H:%M:%S"
ENV.cond_visibility["System.Platform.Android"] = True
ENV.dialog_answers = collections.deque(["10.0.0.5", "32400", ""])
ENV.screen = [1280, 1024]

assert ENV.logged("some message")              # xbmc.log() capture
assert ENV.builtin_called("Notification(")     # executebuiltin() capture
```

`KodiTestCase.setUp` calls `ENV.reset()`, so none of this leaks between tests.

### The one thing to watch out for

PM4K snapshots a lot of Kodi state into module-level constants **at import
time** — `util.timeFormat`, `util.DISPLAY_RESOLUTION`, `util.NEEDS_SCALING`,
`cache.CACHE_SIZE`, `kodi_util.KODI_VERSION_MAJOR`. Changing `ENV` afterwards
does not retroactively change those. Call the function under test
(`util.getTimeFormat()`) rather than asserting on the constant, or patch the
constant explicitly and restore it in a `finally`.

Same story for the module singletons — `advancedsettings.adv`, `path_mapping.pmm`,
`cache.kcm`, `data_cache.dcm`, `plex_hosts.pdm`. They read their files once. The
tests either construct a private instance (`Manager.__new__(Manager)`) or
explicitly re-`load()` the singleton; see `tests/test_advancedsettings.py`.

## What is covered

| Area | File |
|---|---|
| The stubs themselves | `test_harness.py` |
| Every `xbmcvfs.File` closes on the failure path | `test_vfs_handles.py` |
| `.xml.tpl` skin templates, all themes and indicator styles | `test_templates.py` |
| Template engine internals: context inheritance, filters | `test_templating_internals.py` |
| `lib/util.py` formatting, time/date formats, platform probes | `test_util.py` |
| Typed settings read/write | `test_settings_util.py` |
| Path mapping, broken-mapping bookkeeping | `test_path_mapping.py` |
| Local mode ("Go local") | `test_localmode.py` |
| Seamless branching detection and SB markers | `test_seamless_branching.py` |
| Shuffle eligibility and picking | `test_shuffle.py` |
| Native-language / subtitle suppression | `test_language_util.py` |
| Kodi cache sizing, on-disk data cache | `test_cache.py` |
| `advancedsettings.xml` rewriting, plex.direct hosts | `test_advancedsettings.py` |
| Self-update: check, unpack, major-change detection, install | `test_updater.py` |
| Version comparison, `fast_glob` | `test_version.py` |
| Translations and `.po` integrity | `test_i18n.py` |
| plexnet objects and typed values | `test_plexnet_objects.py` |
| plexnet streams: forced/SDH, DV profiles, titles | `test_plexnet_streams.py` |
| plexnet media decision engine | `test_plexnet_mde.py` |
| plexnet play queue, video session helpers | `test_plexnet_playqueue.py` |
| plexnet version handling | `test_plexnet_verlib.py` |

Native window-manager behavior still needs Kodi. `test_playback_return.py`
replays production movie/episode return methods with recording controls and
blocked requests: local progress, manual watch-state overrides, owner-thread
delivery, stale results, Back during I/O, retry after failure, and serialized
background requests. These checks do not prove native GUI timing or device behavior.

## Watch out for: multi-line `.po` entries

A long `.po` string is written as several quoted continuation lines:

```
msgctxt "#33692"
msgid "When you usually watch things in a different language with subtitles, "
"but are a native speaker of other languages, ..."
msgstr ""
```

Reading only the `msgid "..."` line truncates the string, which makes identical
entries look like they have drifted. That mistake originally produced a
confident but wrong report of 11 drifted German strings — there were none.
`tests/test_i18n.py::msgids` and `kodienv.parse_strings_po` both join
continuation lines, and `test_the_parser_joins_multi_line_entries` guards it.

## Recorded exemptions

Some tests assert "this has not got worse" rather than "this is correct":

- `test_i18n.py::KNOWN_MSGID_DRIFT` — translations whose `msgid` has drifted
  from `en_gb`, so Kodi shows English for them. Deliberately not resynced
  mechanically (see `0c93659c`): rewriting the msgid alone would re-enable a
  translation of text that no longer says the same thing — `33650` still names
  the old 500ms default in seven languages. Those need a translator round.
  `de_de` is pinned at zero and has its own test.
- `test_i18n.py::KNOWN_DUPLICATE_IDS` — ids appearing twice in one file.
- `test_templates.py::UNREFERENCED_TEMPLATES` — templates that ship and are
  compiled on every theme change but that no window loads
  (`script-plex-track_context`).

Each has a companion test that fails if the real number drops below the
recorded one, so fixing the underlying problem forces the baseline down instead
of letting it rot.

## ResourceWarnings are visible but cannot fail a test

`pytest.ini` keeps `ResourceWarning` on, because an unclosed `xbmcvfs.File`
surfaces as one and on a Kodi box that is a leaked VFS handle. It cannot be
promoted to an error: the warning fires during garbage collection, outside any
test's context, so pytest cannot attribute it to a test — `error::ResourceWarning`
looks like it works and silently does not.

`test_vfs_handles.py` is the enforcing check. It parses `lib/` and fails if any
`x = xbmcvfs.File(...)` is not closed in a `finally` (or bound by a `with`),
naming the exact file and line. None currently leak.

Note the addon uses `try/finally`, not `with`: `xbmcvfs.File` context-manager
support is unverified for the Kodi 18 branch. The test accepts either.

## Adding tests

Subclass `KodiTestCase` (from `.base`) so `ENV` is reset for you and
`self.mktemp()` gives you a directory that is cleaned up afterwards. Load Plex
XML with `base.fixture("plexnet", "movie.xml")`, and call
`base.ensure_plex_interface()` before touching plexnet — it installs PM4K's
real `plexnet.util.INTERFACE` (importing `plexapp` alone only gives you a
`DumbInterface` placeholder).
