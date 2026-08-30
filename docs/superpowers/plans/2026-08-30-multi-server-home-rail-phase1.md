# Multi-Server Home Rail — Phase 1 (Identity + Foreign Config + Resolution) Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Lay the foundation for pinning foreign-server libraries into the home rail: a collision-safe `sectionId` identity for every rail section, plus the global per-account foreign-library config (pin/unpin/dedupe/prune), plus resolution of `(server_uuid, section_key)` into a live `LibrarySection` or an offline placeholder.

**Architecture:** Everything in Phase 1 is pure, control-free logic added to `lib/windows/home.py`, mirroring the existing `pinnedSectionKey` / `PinnedTypeSection` / `sectionPinnedTypes` conventions and the `test_pinned_sections.py` test pattern (FakeSection/FakeServer + `HomeWindow.__new__`). No `showSections` assembly, no context menu, no UI flags, no `sectionHubs`/`librarySettings` migration yet — those are later phases. Wire key `section.key` is never touched.

**Tech Stack:** Python 3, `lib/windows/home.py`, `tests/test_pinned_sections.py` pattern, `kodienv.ENV`, pytest (TDD).

**Spec ref:** `docs/superpowers/specs/2026-08-29-multi-server-home-rail-design.md` §1 (Data model & config).

---

### Task 1: `sectionId` identity function

Add a module-level `sectionId(section)` helper in `home.py` (same shape as `pinnedSectionKey`, `home.py:410`). It returns a stable, uuid-based string identity, separate from `section.key`, so foreign sections with colliding keys never collide.

Rules (from spec §1):
- `PinnedTypeSection` → `"{sectionId(librarySection)}#{item_type}"` (mirrors `pinnedSectionKey`).
- Home (`HomeSection`, `key is None`) → `"home"`.
- Playlists (`PlaylistsSection`) → `"playlists"`.
- Watchlist (`getattr(section, 'ID', None) == 'watchlist'`, a `LibrarySection` with real key) → `"watchlist"`.
- Everything else (real `LibrarySection`) → `"{server.uuid}:{key}"`.
- A pre-built placeholder (has `sectionIdSet`/`offline` marker) returns its stored identity verbatim — this is how the spec's "placeholder keeps identity from config uuid despite `server=None`" is implemented (see Task 3 for the placeholder class).

The function must be defensive: sections may lack `server` (placeholder). Placeholders carry their identity explicitly, so check that first.

**Files:**
- Modify: `lib/windows/home.py` (add function near `pinnedSectionKey`, ~line 410)
- Test: `tests/test_pinned_sections.py` (append a new test class)

- [ ] **Step 1: Write the failing test**

Add a `SectionIdentityTest` class to `tests/test_pinned_sections.py` (after `PinnedTypeSectionTest`). Import `sectionId` alongside `HomeWindow, PinnedTypeSection`.

```python
class SectionIdentityTest(KodiTestCase):
    def test_real_section_identity_is_uuid_colon_key(self):
        server = FakeServer()
        server.uuid = "AAAABBBB"
        section = FakeSection(key="1", title="Movies")
        section.server = server
        self.assertEqual("AAAABBBB:1", sectionId(section))
        # two servers, same key -> distinct identities
        other = FakeSection(key="1", title="Foreign Movies")
        other.server = FakeServer()  # uuid "SERVERUUID"
        self.assertNotEqual(sectionId(section), sectionId(other))

    def test_pinned_type_section_derives_identity_from_its_library(self):
        pin = PinnedTypeSection(self.section, "collection")
        self.assertEqual("SERVERUUID:3#collection", sectionId(pin))

    def test_home_and_playlists_use_sentinels(self):
        self.assertEqual("home", sectionId(home.HomeSection()))
        self.assertEqual("playlists", sectionId(home.PlaylistsSection()))

    def test_watchlist_uses_a_sentinel_despite_having_a_real_key(self):
        section = FakeSection(key="/library/sections/watchlist", title="Watchlist")
        section.ID = "watchlist"
        self.assertEqual("watchlist", sectionId(section))

    def test_a_placeholder_keeps_its_stored_identity_even_without_a_server(self):
        placeholder = home.ForeignLibrarySection.placeholder(
            server_uuid="ZZZZ", section_key="9", server_name="Away",
            section_title="Movies")
        self.assertEqual("ZZZZ:9", sectionId(placeholder))
        self.assertFalse(placeholder.server)
```

Note: tasks are ordered so `ForeignLibrarySection` (Task 3) does not exist when this test is first written. The last test (`test_a_placeholder_keeps_its_stored_identity...`) references `home.ForeignLibrarySection`, which will not exist until Task 3. To keep every commit green, either (a) defer that one test to Task 3, or (b) write this Task-1 test without it. **Decision: omit `test_a_placeholder_keeps_its_stored_identity_even_without_a_server` here; add it in Task 3.**

```python
class SectionIdentityTest(KodiTestCase):
    def setUp(self):
        super(SectionIdentityTest, self).setUp()
        self.section = FakeSection()

    def test_real_section_identity_is_uuid_colon_key(self):
        server = FakeServer()
        server.uuid = "AAAABBBB"
        section = FakeSection(key="1", title="Movies")
        section.server = server
        self.assertEqual("AAAABBBB:1", sectionId(section))
        # two servers, same key -> distinct identities
        other = FakeSection(key="1", title="Foreign Movies")
        other.server = FakeServer()  # uuid "SERVERUUID"
        self.assertNotEqual(sectionId(section), sectionId(other))

    def test_pinned_type_section_derives_identity_from_its_library(self):
        pin = PinnedTypeSection(self.section, "collection")
        self.assertEqual("SERVERUUID:3#collection", sectionId(pin))

    def test_home_and_playlists_use_sentinels(self):
        self.assertEqual("home", sectionId(home.HomeSection()))
        self.assertEqual("playlists", sectionId(home.PlaylistsSection()))

    def test_watchlist_uses_a_sentinel_despite_having_a_real_key(self):
        section = FakeSection(key="/library/sections/watchlist", title="Watchlist")
        section.ID = "watchlist"
        self.assertEqual("watchlist", sectionId(section))
```

- [ ] **Step 2: Run test to verify it fails**

Run: `python3 -m pytest tests/test_pinned_sections.py::SectionIdentityTest -v`
Expected: FAIL — `ImportError: cannot import name 'sectionId'` (or `NameError` because `sectionId` undefined).

- [ ] **Step 3: Write minimal implementation**

Add to `lib/windows/home.py`, directly after `pinnedSectionKey` (line ~411):

```python
def sectionId(section):
    """Collision-safe identity for a rail section, separate from its wire `key`.

    Real sections are keyed by owning-server uuid + section key, so two servers with
    the same numeric key (e.g. both '1') never collide in the same rail. Virtual
    sections get fixed sentinels. A foreign placeholder carries its identity verbatim.
    """
    stored = getattr(section, 'sectionId', None)
    if stored:
        return stored
    if isinstance(section, PinnedTypeSection):
        return '{0}#{1}'.format(sectionId(section.librarySection), section.itemType)
    if section.key is None:
        return 'home'
    if getattr(section, 'key', None) == 'playlists':
        return 'playlists'
    if getattr(section, 'ID', None) == 'watchlist':
        return 'watchlist'
    return '{0}:{1}'.format(section.server.uuid, section.key)
```

- [ ] **Step 4: Run test to verify it passes**

Run: `python3 -m pytest tests/test_pinned_sections.py::SectionIdentityTest -v`
Expected: PASS.

- [ ] **Step 5: Commit**

```bash
git add lib/windows/home.py tests/test_pinned_sections.py
git commit -m "feat: add collision-safe sectionId identity for rail sections"
```

---

### Task 2: Foreign library config (setting + add/remove/dedupe/prune)

Add the global per-account foreign-library list backed by addon setting `home.foreign_libraries.<account>`, mirroring how `librarySettings` loads/saves (`home.py:964-979`). Public API on `HomeWindow` (testable via `HomeWindow.__new__`):

- `foreignLibraries()` → current list (loaded from setting as JSON array).
- `pinForeignLibrary(server_uuid, section_key, server_name, section_title)` → append-or-dedupe by `(server_uuid, section_key)`, save.
- `unpinForeignLibrary(server_uuid=None, section_key=None, section_id=None)` → remove matching record(s), save.
- `saveForeignLibraries()`, `loadForeignLibraries()`.
- `pruneForeignLibraries(known_servers)` → drop records whose `server_uuid` is not in `known_servers` (spec §4: lazy-prune on load).

The account scope uses the same account identifier as `loadLibrarySettings`/`loadHubSettings` (spec §4). `ACCOUNT.ID` is `util.ACCOUNT.ID`. Guard the `json.loads` exactly like `loadLibrarySettings` (`home.py:968-973`).

Record shape (spec §1):
```
{'server_uuid': str, 'section_key': str, 'server_name': str, 'section_title': str}
```

**Files:**
- Modify: `lib/windows/home.py` (add methods near `loadLibrarySettings`, ~line 979)
- Test: `tests/test_pinned_sections.py` (new class)

- [ ] **Step 1: Write the failing test**

```python
class ForeignLibraryConfigTest(KodiTestCase):
    def setUp(self):
        super(ForeignLibraryConfigTest, self).setUp()
        # foreignSettingKey() reads plexapp.ACCOUNT.ID; no Plex init in tests, so stub it
        from plexnet import plexapp as _plexapp
        self._orig_account = _plexapp.ACCOUNT
        _plexapp.ACCOUNT = type("FakeAccount", (), {"ID": "TESTACCOUNT"})()
        self.win = homeWindow({})

    def tearDown(self):
        from plexnet import plexapp as _plexapp
        _plexapp.ACCOUNT = self._orig_account
        super(ForeignLibraryConfigTest, self).tearDown()

    def pin(self, server_uuid="SERVERUUID", section_key="1", name="Away",
            title="Movies", win=None):
        # use the REAL saveForeignLibraries so it writes ENV.settings via util.setSetting;
        # each KodiTestCase.setUp resets ENV, so tests start from a clean setting
        win = win or self.win
        win.pinForeignLibrary(server_uuid, section_key, name, title)
        return win

    def test_pin_creates_a_foreign_record(self):
        self.pin()
        self.assertEqual([{
            "server_uuid": "SERVERUUID", "section_key": "1",
            "server_name": "Away", "section_title": "Movies",
        }], self.win.foreignLibraries())

    def test_pinning_the_same_foreign_library_twice_dedupes(self):
        self.pin()
        self.pin()
        self.assertEqual(1, len(self.win.foreignLibraries()))

    def test_two_foreign_libraries_with_same_key_on_different_servers_both_stay(self):
        self.pin(server_uuid="AAA")
        self.pin(server_uuid="BBB", name="Other")
        self.assertEqual(2, len(self.win.foreignLibraries()))

    def test_unpin_removes_by_server_and_key(self):
        self.pin(server_uuid="AAA")
        self.pin(server_uuid="BBB", name="Other")
        self.win.unpinForeignLibrary(server_uuid="AAA", section_key="1")
        got = [r["server_uuid"] for r in self.win.foreignLibraries()]
        self.assertEqual(["BBB"], got)

    def test_unpin_for_a_missing_record_is_a_no_op(self):
        self.pin(server_uuid="AAA")
        self.win.unpinForeignLibrary(server_uuid="NOPE", section_key="1")
        self.assertEqual(1, len(self.win.foreignLibraries()))

    def test_prune_drops_records_for_unknown_servers(self):
        self.pin(server_uuid="AAA")
        self.pin(server_uuid="BBB", name="Other")
        pruned = self.win.pruneForeignLibraries(known_servers={"AAA"})
        surviving = [r["server_uuid"] for r in pruned]
        self.assertEqual(["AAA"], surviving)
```

- [ ] **Step 2: Run test to verify it fails**

Run: `python3 -m pytest tests/test_pinned_sections.py::ForeignLibraryConfigTest -v`
Expected: FAIL — `AttributeError: 'HomeWindow' object has no attribute 'foreignLibraries'`.

- [ ] **Step 3: Write minimal implementation**

Add methods to `HomeWindow` in `lib/windows/home.py`, after `saveLibrarySettings` (line ~979):

```python
def foreignSettingKey(self):
    # account scope identical to loadLibrarySettings/loadHubSettings (home.py:965,982)
    return 'home.foreign_libraries.{}'.format(plexapp.ACCOUNT.ID)

def loadForeignLibraries(self):
    self._foreignLibraries = []
    try:
        data = util.getSetting(self.foreignSettingKey(), '')
        self._foreignLibraries = json.loads(data) if data else []
    except ValueError:
        util.ERROR()

def saveForeignLibraries(self):
    util.setSetting(self.foreignSettingKey(), json.dumps(self._foreignLibraries))

def foreignLibraries(self):
    if not getattr(self, '_foreignLibraries', None):
        self.loadForeignLibraries()
    return self._foreignLibraries

def pinForeignLibrary(self, server_uuid, section_key, server_name, section_title):
    libs = self.foreignLibraries()
    for record in libs:
        if record.get('server_uuid') == server_uuid and record.get('section_key') == section_key:
            record['server_name'] = server_name
            record['section_title'] = section_title
            break
    else:
        libs.append({
            'server_uuid': server_uuid,
            'section_key': str(section_key),
            'server_name': server_name,
            'section_title': section_title,
        })
    self.saveForeignLibraries()

def unpinForeignLibrary(self, server_uuid=None, section_key=None):
    libs = self.foreignLibraries()
    before = len(libs)
    self._foreignLibraries = [
        r for r in libs
        if not (server_uuid is not None and r.get('server_uuid') == server_uuid)
        and not (section_key is not None and r.get('section_key') == str(section_key))
    ]
    if len(self._foreignLibraries) != before:
        self.saveForeignLibraries()

def pruneForeignLibraries(self, known_servers):
    libs = self.foreignLibraries()
    self._foreignLibraries = [r for r in libs if r.get('server_uuid') in known_servers]
    self.saveForeignLibraries()
    return self._foreignLibraries
```

`foreignSettingKey` uses `plexapp.ACCOUNT.ID`, matching `loadLibrarySettings`/`loadHubSettings` (`home.py:965,982`) exactly, so the account scope stays consistent. `util` is `lib.util` (imported at `home.py:16`); `plexapp` is imported at `home.py:11`.

- [ ] **Step 4: Run test to verify it passes**

Run: `python3 -m pytest tests/test_pinned_sections.py::ForeignLibraryConfigTest -v`
Expected: PASS.

- [ ] **Step 5: Commit**

```bash
git add lib/windows/home.py tests/test_pinned_sections.py
git commit -m "feat: add global per-account foreign library config with pin/unpin/prune"
```

---

### Task 3: Foreign placeholder section + resolution

Add a placeholder section class and the resolver. The placeholder is what keeps an offline/removed foreign library visible in the rail with the same `sectionId` even though it has no live server (spec §1, §2, §4).

`ForeignLibrarySection`:
- constructed from a config record only.
- `server = None`, `offline = True`, `type = None/null`, `title = "{section_title} - {server_name}"`, `key = None` (no wire key).
- carries `server_uuid`, `section_key`, `section_title`, `server_name`, and an explicit `sectionId = "{server_uuid}:{section_key}"` so `sectionId()` returns it verbatim (Task 1 first branch).
- classmethod `placeholder(server_uuid, section_key, server_name, section_title)`.

Resolver:
- `HomeWindow.resolveForeignLibrary(record)` → `(section, offline_bool)`.
  - Look up `server` via `plexapp.SERVERMANAGER` by `record['server_uuid']`. If not found → `(placeholder, True)`.
  - Else query `server.library.sections()`, match by `str(section.key) == str(record['section_key'])`. Match found → `(live_section, False)` and refresh `record['section_title'] = section.title`. No match → placeholder.
- `server_uuid → server` lookup needs a helper over `SERVERMANAGER`. Servers are available via `plexapp.SERVERMANAGER.getServers()` (spec §Problem). A record's server is found by `server.uuid == record['server_uuid']`.

For testability without Kodi, the resolver takes a server-manager-like object. To keep it control-free and match the `HomeWindow.__new__` pattern, expose a small module-level helper `findServerByUuid(manager, uuid)` plus the `HomeWindow.resolveForeignLibrary(record, manager=None)`. Default `manager=plexapp.SERVERMANAGER` at call time.

**Files:**
- Modify: `lib/windows/home.py` (add class near `PinnedTypeSection` ~line 410; resolver methods near `saveLibrarySettings` ~line 979)
- Test: `tests/test_pinned_sections.py`

- [ ] **Step 1: Write the failing test**

```python
class ForeignLibrarySectionTest(KodiTestCase):
    def test_placeholder_identity_comes_from_the_record_not_a_server(self):
        ph = home.ForeignLibrarySection.placeholder(
            server_uuid="ZZZZ", section_key="9", server_name="Away",
            section_title="Movies")
        self.assertEqual("somenonexistent", ph.server)  # server is None
```

(placeholder has no server — fix expected value to `assertIsNone(ph.server)`.)

```python
class ForeignLibrarySectionTest(KodiTestCase):
    def test_placeholder_identity_comes_from_the_record_not_a_server(self):
        ph = home.ForeignLibrarySection.placeholder(
            server_uuid="ZZZZ", section_key="9", server_name="Away",
            section_title="Movies")
        self.assertIsNone(ph.server)
        self.assertTrue(ph.offline)
        self.assertEqual("ZZZZ:9", sectionId(ph))

    def test_placeholder_title_is_suffixed(self):
        ph = home.ForeignLibrarySection.placeholder(
            server_uuid="ZZZZ", section_key="9", server_name="Away",
            section_title="Movies")
        self.assertEqual("Movies - Away", ph.title)


class FakeManager(object):
    def __init__(self, servers):
        self.servers = servers

    def getServers(self):
        return self.servers


class FakeResolvableSection(object):
    key = "1"
    title = "Live Movies"


class ForeignResolutionTest(KodiTestCase):
    def setUp(self):
        super(ForeignResolutionTest, self).setUp()
        self.win = homeWindow({})

    def test_unknown_server_resolves_to_a_placeholder(self):
        manager = FakeManager([])
        section, offline = self.win.resolveForeignLibrary(
            {"server_uuid": "NOPE", "section_key": "1",
             "server_name": "Away", "section_title": "Movies"},
            manager=manager)
        self.assertTrue(offline)
        self.assertIsNone(section.server)

    def test_match_by_key_resolves_to_a_live_section(self):
        class FakeLib(object):
            def sections(self):
                return [FakeResolvableSection()]
        server = FakeServer()
        server.library = FakeLib()
        manager = FakeManager([server])
        record = {"server_uuid": "SERVERUUID", "section_key": "1",
                  "server_name": "Away", "section_title": "Movies"}
        section, offline = self.win.resolveForeignLibrary(record, manager=manager)
        self.assertFalse(offline)
        self.assertIs(section, FakeResolvableSection())
        # live match refreshes the denormalized title
        self.assertEqual("Live Movies", record["section_title"])

    def test_no_section_match_on_a_known_server_resolves_to_a_placeholder(self):
        class FakeLib(object):
            def sections(self):
                return []
        server = FakeServer()
        server.library = FakeLib()
        manager = FakeManager([server])
        section, offline = self.win.resolveForeignLibrary(
            {"server_uuid": "SERVERUUID", "section_key": "99",
             "server_name": "Away", "section_title": "Movies"},
            manager=manager)
        self.assertTrue(offline)
```

- [ ] **Step 2: Run test to verify it fails**

Run: `python3 -m pytest tests/test_pinned_sections.py::ForeignLibrarySectionTest tests/test_pinned_sections.py::ForeignResolutionTest -v`
Expected: FAIL — `AttributeError: module 'lib.windows.home' has no attribute 'ForeignLibrarySection'` (and `AttributeError: 'HomeWindow' object has no attribute 'resolveForeignLibrary'`).

- [ ] **Step 3: Write minimal implementation**

Add the placeholder class to `lib/windows/home.py`, directly after `pinnedSectionKey` (line ~411):

```python
class ForeignLibrarySection(object):
    """Stand-in for a foreign library whose server is unknown or unreachable.

    Carries the config record's denormalized labels and an explicit sectionId, so it
    renders in the rail (suffixed title) and keeps the same identity even with server
    None. Resolves to a live LibrarySection when the server is reachable.
    """
    offline = True
    server = None
    key = None
    type = None

    def __init__(self, server_uuid, section_key, server_name, section_title):
        self.server_uuid = server_uuid
        self.section_key = str(section_key)
        self.server_name = server_name
        self.section_title = section_title
        self.title = u'{0} - {1}'.format(section_title, server_name)
        self.sectionId = u'{0}:{1}'.format(server_uuid, self.section_key)

    @classmethod
    def placeholder(cls, **kwargs):
        return cls(**kwargs)
```

Add the resolver helpers to `HomeWindow` in `lib/windows/home.py`, after `saveForeignLibraries`:

```python
def resolveForeignLibrary(self, record, manager=None):
    """Resolve a foreign config record to a live section or an offline placeholder.

    Returns (section, offline). Live sections refresh the record's denormalized title.
    """
    if manager is None:
        manager = plexapp.SERVERMANAGER
    server = self._findServerByUuid(manager, record.get('server_uuid'))
    if server is None:
        return ForeignLibrarySection.placeholder(**{
            'server_uuid': record.get('server_uuid'),
            'section_key': record.get('section_key'),
            'server_name': record.get('server_name'),
            'section_title': record.get('section_title'),
        }), True
    try:
        for section in server.library.sections():
            if str(section.key) == str(record.get('section_key')):
                record['section_title'] = section.title
                return section, False
    except Exception:
        util.ERROR()
    return ForeignLibrarySection.placeholder(**{
        'server_uuid': record.get('server_uuid'),
        'section_key': record.get('section_key'),
        'server_name': record.get('server_name'),
        'section_title': record.get('section_title'),
    }), True

@staticmethod
def _findServerByUuid(manager, uuid):
    if manager is None or not uuid:
        return None
    for server in manager.getServers():
        if getattr(server, 'uuid', None) == uuid:
            return server
    return None
```

- [ ] **Step 4: Run test to verify it passes**

Run: `python3 -m pytest tests/test_pinned_sections.py::ForeignLibrarySectionTest tests/test_pinned_sections.py::ForeignResolutionTest -v`
Expected: PASS.

- [ ] **Step 5: Run the Task 1 test once more to confirm placeholder identity works**

Run: `python3 -m pytest tests/test_pinned_sections.py -v`
Expected: all PASS, including `SectionIdentityTest`. Add the deferred placeholder-identity test if you did not add it in Task 1:

```python
    def test_a_placeholder_keeps_its_stored_identity_even_without_a_server(self):
        placeholder = home.ForeignLibrarySection.placeholder(
            server_uuid="ZZZZ", section_key="9", server_name="Away",
            section_title="Movies")
        self.assertEqual("ZZZZ:9", sectionId(placeholder))
        self.assertIsNone(placeholder.server)
```

- [ ] **Step 6: Commit**

```bash
git add lib/windows/home.py tests/test_pinned_sections.py
git commit -m "feat: add foreign library placeholder and server+key resolution"
```

---

### Task 4: Green baseline + run full suite

Confirm nothing regressed and the whole Phase-1 surface is green.

**Files:**
- Test: whole `tests/`

- [ ] **Step 1: Run the full test suite**

Run: `python3 -m pytest`
Expected: all PASS (no pre-existing failures).

- [ ] **Step 2: Verify no wire key / existing behavior changed**

Re-read the diff for `lib/windows/home.py` and confirm Phase 1 only **adds** functions/methods; it must not alter `showSections`, `sectionHubs`, `section.key`, `librarySettings`, or `hubSettings` semantics.

Run: `git diff lib/windows/home.py`
Expected: only additive changes (new `sectionId`, `ForeignLibrarySection`, `*ForeignLibrary*` methods, `resolveForeignLibrary`, `_findServerByUuid`).

- [ ] **Step 3: Commit**

```bash
git add lib/windows/home.py tests/test_pinned_sections.py
git commit -m "test: confirm phase 1 identity+foreign-config baseline is green"
```

---

## Phase 1 done / not done

**Done:** `sectionId` identity (real/virtual/pinned/placeholder), foreign config (pin/unpin/dedupe/prune), placeholder + resolution, all testable control-free via the established pattern, full suite green.

**Deferred to later phases (spec still to come):**
- `showSections` foreign-append + per-selected-server `librarySettings` bypass + array ordering.
- Full `sectionId` migration of `sectionHubs`/`allSections`/`wantedSections`/`lastSection`/`getRequiredSourceSections`/`getCrossSectionSources`.
- `hubSettings`/`librarySettings` foreign-keying + `find_in_section_hubs` shim removal.
- Context menu Pin/Unpin, `is.foreign` rail flag, offline marker UI.
- Placeholder↔live transition on `serverRefresh()`, hub-fetch guard for placeholders.
- Cross-section hub merge tests (the riskiest regression).

**Carry-forward items from the Phase-1 final review — MUST land in the Phase-2 plan (not dropped):**
- **Live-title suffix**: `resolveForeignLibrary` returns the raw live `LibrarySection` with its unsuffixed `title`, but spec §1/§2 requires EVERY foreign entry render as `"{title} - {server_name}"`. The record preserves `server_name`, so the rail-assembly phase must apply the suffix to live sections (placeholders already do via `ForeignLibrarySection.title`). Reuse `record['server_name']`; refresh it alongside `section_title` on live resolution so labels don't drift.
- **Pin-over-placeholder `.key` garbage**: `PinnedTypeSection.__init__` derives `key = pinnedSectionKey(None, ...) == "None#collection"` when the underlying foreign section is its offline placeholder (identity `sectionId` is still correct, `"ZZZZ:9#collection"`). During the offline span the pin's wire `.key`/delegated `all()` are invalid. The Phase-2 hub-task guard must keep such pins out of the hub-fetch path so they never query `key=None` on the server.
