# Multi-Server Home Rail — Hub Phase Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Make the home hub pipeline collision-safe across servers — fix the wrong-hub/pollution bug, fetch hubs for live foreign libraries, persist hub/library settings keyed by `sectionId`, and remove the obsolete string/int shim.

**Architecture:** Migrate the `sectionHubs` in-memory cache (and persisted `hubSettings`/`librarySettings`) from bare `section.key` to the collision-safe `sectionId` identity, unified behind two small helpers so writer and reader always agree. Foreign live sections get a `SectionHubsTask` scheduled; offline placeholders never do. Two milestones: (1) runtime native-hub collision fix + foreign fetch, (2) persisted settings re-key + order + custom-config collision + shim removal.

**Tech Stack:** Python (legacy Py2-era), Kodi addon, `tests/test_pinned_sections.py` pytest harness (interpreter `/tmp/opencode/venv/bin/python -m pytest`), `lib/windows/home.py`.

**Working repo:** `/Users/mvanbaak/dev/personal/plex-for-kodi`, branch `feature/multi-server-home-rail-impl`. Do NOT create/switch branches. Design spec: `docs/superpowers/specs/2026-08-31-multi-server-home-rail-hub-phase-design.md`.

---

## Key helpers (introduced in Task 1, used everywhere)

The migration keys both the `sectionHubs` cache and persisted dicts by `sectionId`, but virtual sections (Home/Playlists/Watchlist) keep their existing scalar keys. Helpers centralize the mapping so writers and readers never drift:

`cacheKeyForSection(section)` — a method on `HomeWindow` (called as `self.cacheKeyForSection(...)` / `win.cacheKeyForSection(...)`). Given a **section object**, returns the `sectionHubs` key:

```python
def cacheKeyForSection(self, section):
    """Collision-safe sectionHubs key for a section object.

    Real libraries and pinned type-views key by sectionId ('uuid:key' / 'uuid:key#type'),
    which is unique per server. Virtual sections (Home/Playlists/Watchlist) keep their
    existing scalar keys.
    """
    if section is None or getattr(section, 'key', None) is None:
        return None  # Home
    sid = sectionId(section)
    if sid in ('playlists', 'watchlist', 'home'):
        return section.key  # virtual: keep existing scalar key
    return sid  # real + pinned-type
```

`hubSectionKey(section_key, server_uuid)` — a **module-level** function (called as `home.hubSectionKey(...)`), introduced in Milestone 2 (Task 4). Maps a bare section key + server uuid to the `hubSettings`/`allSections` lookup key (`None` for Home, `'{uuid}:{key}'` otherwise).

---

## Milestone 1 — Collision-safe native hub display + foreign hub fetch

Fixes the user-reported bug (hovering a foreign tile shows + pollutes the local cache) and enables living foreign tiles to fetch their own hubs. Only the `sectionHubs` in-memory cache is touched; persisted settings and custom-config/cross-section hubSettings paths are untouched until Milestone 2.

### Task 1: Migrate `sectionHubs` cache read/write/null to a collision-safe key for native display

**Files:**
- Modify: `lib/windows/home.py` (add `cacheKeyForSection` near `sectionId` at ~433; migrate read/write/null sites below)
- Test: `tests/test_pinned_sections.py`

This is the core fix for the user's bug. Derive the cache key from the **section object** at each site, never from a bare key.

- [ ] **Step 1: Write the failing test**

Append to `tests/test_pinned_sections.py`:

```python
class _Hub(object):
    def __init__(self, identifier, **kw):
        self.hubIdentifier = identifier
        for k, v in kw.items():
            setattr(self, k, v)


def hub(identifier, **kw):
    return _Hub(identifier, **kw)


class SectionHubsCollisionTest(KodiTestCase):
    def test_cache_key_collision_safe_across_servers(self):
        win = homeWindow({})
        a = FakeSection(key="1", server_uuid="AAA")
        b = FakeSection(key="1", server_uuid="BBB")
        self.assertNotEqual(win.cacheKeyForSection(a), win.cacheKeyForSection(b))
        self.assertEqual(win.cacheKeyForSection(a), "AAA:1")
        ph = home.ForeignLibrarySection.placeholder(
            server_uuid="BBB", section_key="1", server_name="Away",
            section_title="Movies")
        # a live foreign section and its placeholder resolve to the same cache key
        self.assertEqual(win.cacheKeyForSection(b), win.cacheKeyForSection(ph))

    def test_virtual_sections_keep_scalar_keys(self):
        win = homeWindow({})
        self.assertIsNone(win.cacheKeyForSection(home.home_section))
        self.assertEqual(win.cacheKeyForSection(home.playlists_section), "playlists")

    def test_cross_server_does_not_leak_or_clobber_hub_cache(self):
        win = homeWindow({})
        real = FakeSection(key="1", title="My Adult Movies")
        foreign = FakeSection(key="1", title="Movies", server_uuid="ZZZZ")
        win.sectionHubs[win.cacheKeyForSection(real)] = home.HubsList([hub("a")])
        # foreign section with same wire key never sees the local cache
        self.assertIsNone(win.sectionHubs.get(win.cacheKeyForSection(foreign)))
        # writing foreign never clobbers local
        win.sectionHubs[win.cacheKeyForSection(foreign)] = home.HubsList([hub("b")])
        self.assertEqual(win.sectionHubs[win.cacheKeyForSection(real)][0].hubIdentifier, "a")
        self.assertEqual(win.sectionHubs[win.cacheKeyForSection(foreign)][0].hubIdentifier, "b")
```

`home` module ref, `HomeWindow`, `sectionId`, `FakeSection` (with `server_uuid`) are already available. `home.home_section`/`home.playlists_section`/`home.HubsList` come from the `home` module. The `_Hub`/`hub()` helpers are dependency-free (no `plexnet` import needed). All subsequent test classes in later tasks reuse this `hub()` helper — it must be defined once at module scope near the other fakes.

- [ ] **Step 2: Run tests to verify they fail**

Run: `/tmp/opencode/venv/bin/python -m pytest tests/test_pinned_sections.py::SectionHubsCollisionTest -v`
Expected: FAIL — `AttributeError: 'HomeWindow' object has no attribute 'cacheKeyForSection'`.

- [ ] **Step 3: Add `cacheKeyForSection` method**

Add a method inside the `HomeWindow` class (near the other foreign helpers like `_sameRailSection`, home.py ~1141):

```python
    def cacheKeyForSection(self, section):
        """Collision-safe sectionHubs key for a section object.

        Real libraries and pinned type-views key by sectionId ('uuid:key' / 'uuid:key#type'),
        which is unique per server. Virtual sections (Home/Playlists/Watchlist) keep their
        existing scalar keys.
        """
        if section is None or getattr(section, 'key', None) is None:
            return None  # Home
        sid = sectionId(section)
        if sid in ('playlists', 'watchlist', 'home'):
            return section.key  # virtual: keep existing scalar key
        return sid  # real + pinned-type
```

- [ ] **Step 4: Migrate the native-display `sectionHubs` read/write/null sites**

These sites all have a **section object** in scope; replace the bare `.key` with `self.cacheKeyForSection(section)`:

- `_showHubs` (home.py:4291): `hubs = self.sectionHubs.get(section.key)` → `hubs = self.sectionHubs.get(self.cacheKeyForSection(section))`
- `_showHubs` (home.py:4334-4335):
  ```python
  if section.key in self.sectionHubs:
      self.sectionHubs[section.key] = None
  ```
  →
  ```python
  ck = self.cacheKeyForSection(section)
  if ck in self.sectionHubs:
      self.sectionHubs[ck] = None
  ```
- `sectionHubsCallback` (home.py:3946): `update = bool(self.sectionHubs.get(section.key))` → `update = bool(self.sectionHubs.get(self.cacheKeyForSection(section)))`
- `sectionHubsCallback` (home.py:3955): `self.sectionHubs[section.key] = sorted_hubs` → `self.sectionHubs[self.cacheKeyForSection(section)] = sorted_hubs`
- `crossSectionHubsCallback` (home.py:2379): `self.sectionHubs[section.key] = sorted_hubs` → `self.sectionHubs[self.cacheKeyForSection(section)] = sorted_hubs`
- `updateHubCallback` (home.py:4003-4004):
  ```python
  checked_keys.add(section.key)
  hubs = self.sectionHubs.get(section.key, ())
  ```
  →
  ```python
  ck = self.cacheKeyForSection(section)
  checked_keys.add(ck)
  hubs = self.sectionHubs.get(ck, ())
  ```
- `getCombinedHubsForSection` native lookup (home.py:2150): `native_hubs = self.sectionHubs.get(section_key)` → `native_hubs = self.sectionHubs.get(self.cacheKeyForSection(section))`. (This function's hubSettings custom-config block below 2158 is LEFT UNTOUCHED until Milestone 2.)
- `getCombinedHubsForSection` stale-check raid (home.py:2336-2338) — leave for Milestone 2 (it serves the custom-config path).

- [ ] **Step 5: Run tests to verify they pass**

Run: `/tmp/opencode/venv/bin/python -m pytest tests/test_pinned_sections.py -q`
Expected: all pass (744+ suite count grows).

- [ ] **Step 6: Run full suite**

Run: `/tmp/opencode/venv/bin/python -m pytest -q`
Expected: green (no regressions).

- [ ] **Step 7: Commit**

```bash
git add lib/windows/home.py tests/test_pinned_sections.py
git commit -m "fix: key sectionHubs by sectionId to stop cross-server cache collision"
```

### Task 2: Schedule hub fetch for live foreign sections

**Files:**
- Modify: `lib/windows/home.py` (`showSections` ~4157-4161)
- Test: `tests/test_pinned_sections.py`

Foreign live sections currently render with no hubs because they're appended after the hub-task scheduling block. Change: schedule a `SectionHubsTask` per live foreign section; skip offline placeholders.

- [ ] **Step 1: Write the failing test**

```python
class ForeignHubSchedulingTest(KodiTestCase):
    def test_live_foreign_section_gets_hub_task_but_offline_placeholder_does_not(self):
        from plexnet import plexapp as _plexapp
        from lib import backgroundthread as _BG

        win = homeWindow({})
        live = FakeSection(key="1", server_uuid="ZZZZ")
        live.is_foreign = True
        offline = home.ForeignLibrarySection.placeholder(
            server_uuid="WW", section_key="2", server_name="Away", section_title="TV")

        # stub the framework dependencies the helper touches
        _fake_server = type("FS", (), {"hasHubs": lambda self: True, "uuid": "ZZZZ"})()
        _orig_sm = getattr(_plexapp, "SERVERMANAGER", None)
        _plexapp.SERVERMANAGER = type("SM", (), {"selectedServer": _fake_server})()
        _orig_add = _BG.BGThreader.addTasks
        _BG.BGThreader.addTasks = lambda tasks: None

        try:
            win.tasks = []
            win.wantedSections = None
            win.scheduleForeignHubFetches([live, offline])
            scheduled = [t.section for t in win.tasks if hasattr(t, "section")]
            self.assertIn(live, scheduled)
            self.assertNotIn(offline, scheduled)
        finally:
            _BG.BGThreader.addTasks = _orig_add
            if _orig_sm is not None:
                _plexapp.SERVERMANAGER = _orig_sm
```

Add an `is_foreign = True` attribute to `FakeSection` if not already present. The expected import paths are confirmed: `home.py` uses `from plexnet import plexapp` and `from lib import backgroundthread`, so stubbing `_plexapp.SERVERMANAGER` and `_BG.BGThreader.addTasks` mutates the exact objects the helper uses. This follows the existing `_orig_account` save/restore stub convention (line ~371).

- [ ] **Step 2: Run test to verify it fails**

Run: `/tmp/opencode/venv/bin/python -m pytest tests/test_pinned_sections.py::ForeignHubSchedulingTest -v`
Expected: FAIL — `AttributeError`.

- [ ] **Step 3: Add a scheduling helper and wire it into `showSections`**

Add (near `foreignRailSections`, home.py ~1146):

```python
def scheduleForeignHubFetches(self, sections):
    """Schedule hub fetch for live foreign sections; offline placeholders never fetch."""
    if not plexapp.SERVERMANAGER.selectedServer.hasHubs():
        # no hub pipeline on servers without hubs; nothing to schedule
        return
    tasks = [SectionHubsTask().setup(s, self.sectionHubsCallback, self.wantedSections)
             for s in sections
             if not getattr(s, 'offline', False) and s.server
             and not getattr(s.server, 'DEFER_HUBS', False)]
    self.tasks += tasks
    if tasks:
        backgroundthread.BGThreader.addTasks(tasks)
```

Then in `showSections`, capture the foreign sections so they can be scheduled, replacing home.py:4161:

```python
        foreign_sections = self.foreignRailSections()
        sections = sections + foreign_sections
        self.scheduleForeignHubFetches(foreign_sections)
```

(Keep the existing comment above the foreign append, updated to note hubs are now fetched for live foreign sections.)

- [ ] **Step 4: Run test to verify it passes**

Run: `/tmp/opencode/venv/bin/python -m pytest tests/test_pinned_sections.py::ForeignHubSchedulingTest -v`
Expected: PASS.

- [ ] **Step 5: Run full suite**

Run: `/tmp/opencode/venv/bin/python -m pytest -q`
Expected: green.

- [ ] **Step 6: Commit**

```bash
git add lib/windows/home.py tests/test_pinned_sections.py
git commit -m "feat: fetch hubs for live foreign sections on the home rail"
```

### Task 3: Skip offline/None-server foreign sources in cross-section refresh

**Files:**
- Modify: `lib/windows/home.py` (`fetchMissingSections` ~2280, `_refreshCrossSectionSources` ~2314)
- Test: `tests/test_pinned_sections.py`

Cross-section source refresh must not schedule a fetch for offline foreign sources (their `SectionHubsTask` would bail on `server is None`/empty). Add a guard.

- [ ] **Step 1: Write the failing test**

```python
class OfflineSourceSkipTest(KodiTestCase):
    def test_fetch_missing_sections_skips_offline_sources(self):
        win = homeWindow({})
        win.tasks = []
        win.allSections = {}
        offline = home.ForeignLibrarySection.placeholder(
            server_uuid="WW", section_key="2", server_name="Away", section_title="TV")
        # source key maps to the offline placeholder in allSections
        win.allSections[win.cacheKeyForSection(offline)] = offline
        win.fetchMissingSections(win.cacheKeyForSection(offline))
        self.assertEqual(win.tasks, [])  # no task scheduled for offline source
```

- [ ] **Step 2: Run test to verify it fails**

Run: `/tmp/opencode/venv/bin/python -m pytest tests/test_pinned_sections.py::OfflineSourceSkipTest -v`
Expected: FAIL — a `SectionHubsTask` was scheduled for the offline placeholder.

- [ ] **Step 3: Guard `fetchMissingSections`**

In `fetchMissingSections` (home.py:2295-2312), after resolving `section_obj`, add:

```python
            if section_obj is None or getattr(section_obj, 'offline', False):
                continue
```

- [ ] **Step 4: Guard `_refreshCrossSectionSources`**

In `_refreshCrossSectionSources` (home.py:2345-2347), replace:

```python
            section_obj = self.allSections.get(str_source) if hasattr(self, 'allSections') else None
            if section_obj is None:
                continue
```

with:

```python
            section_obj = self.allSections.get(str_source) if hasattr(self, 'allSections') else None
            if section_obj is None or getattr(section_obj, 'offline', False):
                continue
```

- [ ] **Step 5: Run tests to verify they pass**

Run: `/tmp/opencode/venv/bin/python -m pytest tests/test_pinned_sections.py -q`
Expected: PASS.

- [ ] **Step 6: Run full suite**

Run: `/tmp/opencode/venv/bin/python -m pytest -q`
Expected: green.

- [ ] **Step 7: Commit**

```bash
git add lib/windows/home.py tests/test_pinned_sections.py
git commit -m "fix: never fetch cross-section hubs from offline foreign sources"
```

---

## Milestone 2 — Persisted settings re-key, order, custom-config collision, shim removal

Makes custom hub config (`hubSettings`) and library show/order (`librarySettings`) collision-safe by re-keying persisted values to `sectionId`, changes `catalog_id` to the `|` separator, migrates the `order` list, and removes the now-dead `find_in_section_hubs` shim.

### Task 4: Add `hubSectionKey` helper; migrate `hubSettings` config-key reads + `allSections` re-key

**Files:**
- Modify: `lib/windows/home.py`
- Test: `tests/test_pinned_sections.py`

Introduce the collision-safe keying for `hubSettings`/`allSections`. Per spec §4, a foreign library's custom hub config is stored in the selected server's bucket **keyed by the foreign section's own `sectionId`** (`'{foreign_uuid}:1'`), so it can never collide with an own library. That key equals `cacheKeyForSection(section)` — so live hubSettings lookups use `cacheKeyForSection`, and the three bare-key functions (`getRequiredSourceSections`/`getEnabledHubsForSection`/`hasCrossSectionHubs`) are threaded a sectionId (or `None` for Home) instead of a bare wire key. (`hubSectionKey(section_key, server_uuid)` is introduced separately in Task 6 _only_ for composing keys during the on-disk re-key; it is NOT the live-lookup helper.)

- [ ] **Step 1: Write the failing test**

```python
class HubConfigKeyTest(KodiTestCase):
    def test_hub_settings_lookup_uses_foreign_sections_own_id(self):
        win = homeWindow({})
        own = FakeSection(key="1", server_uuid="AAA")
        foreign = FakeSection(key="1", server_uuid="BBB")
        # a foreign section's hub config key is its own sectionId, distinct from an
        # own section with the same wire key
        self.assertNotEqual(win.cacheKeyForSection(own), win.cacheKeyForSection(foreign))
        self.assertEqual(win.cacheKeyForSection(foreign), "BBB:1")
```

- [ ] **Step 2: Run test to verify it fails**

Run: `/tmp/opencode/venv/bin/python -m pytest tests/test_pinned_sections.py::HubConfigKeyTest -v`
Expected: PASS (validates the invariant `cacheKeyForSection` established in Task 1). If it already passes, that's fine — it locks in the contract Task 4 relies on.

- [ ] **Step 3: Thread sectionId through the bare-key hubSettings functions**

Change `getRequiredSourceSections(section_key)` (home.py:2094) and `getEnabledHubsForSection(section_key)` (home.py:2117) and `hasCrossSectionHubs(section_key)` (home.py:2084) so their input is a **sectionId** (or `None` for Home) rather than a bare wire `section.key`. Inside, replace `config_key = str(section_key) if section_key is not None else None` with `config_key = section_key` (it's already the sectionId string, or `None` for Home). `getRequiredSourceSections` at home.py:2131 (`enabled.add(...)` watching) — keep the `section_key is None` Home branch intact.

Update **all callers** to pass `self.cacheKeyForSection(section)` (or `None` for Home):
- `getCombinedHubsForSection(section)` (home.py:2169, 2174): `self.getEnabledHubsForSection(section_key)` / `self.getRequiredSourceSections(section_key)` → `... (self.cacheKeyForSection(section))`.
- `hasCrossSectionHubs(section_key)` — called from `sectionHubsCallback` (home.py:3959 `self.hasCrossSectionHubs(None)` — Home, unchanged) and render (home.py:4380 area). Home calls pass `None`; non-home callers pass `self.cacheKeyForSection(section)`.
- `_refreshCrossSectionSources(section_key)` (home.py:2322): `self.getRequiredSourceSections(section_key)` → pass the sectionId (its `section_key` param becomes a sectionId once callers thread it; see Step 5).
- `crossSectionHubsCallback` (home.py:2391): `self.getRequiredSourceSections(self.lastSection.key)` → `self.getRequiredSourceSections(self.cacheKeyForSection(self.lastSection))`.
- showSections (home.py:4140): `self.getRequiredSourceSections(None)` — Home, unchanged.

Update **`getCombinedHubsForSection`** (home.py:2158-2162):
- `config_key = str(section_key) if section_key is not None else None` → `config_key = self.cacheKeyForSection(section)`.
- `getEnabledHubsForSection`/`getRequiredSourceSections` calls pass `self.cacheKeyForSection(section)`.

- [ ] **Step 4: Re-key `self.allSections` to `str(sectionId)`**

- Writer (home.py:4100): `self.allSections[str(section.key)] = section` → `self.allSections[str(self.cacheKeyForSection(section))] = section`. (For real/foreign libraries `cacheKeyForSection` == `str(sectionId)`; virtual sections are never added to `allSections`.)
- Consumers that look up by key: home.py:1927, 2345, 4141-4145 — change from `str(section_key)`/`allSections.get(str_key)` to `allSections.get(str(self.cacheKeyForSection(section_obj)))` (where a section object is in scope) or `allSections.get(str(self.cacheKeyForSection(section)))`. Where only a bare key flows, thread the sectionId from the caller.
  - home.py:1927: `self.allSections.get(str(section_key))` — this function iterates `availableHubs`/sections; get the section object from `allSections` by sectionId instead of `str(section_key)`.
  - home.py:2345 (`_refreshCrossSectionSources`): `self.allSections.get(str_source)` → `self.allSections.get(str_source)` where `str_source` is already a sectionId string (threaded from `required_sources`).
  - home.py:4141-4145 (showSections): `if str_key and str_key in self.allSections:` / `fetch_sections.append(self.allSections[str_key])` — `str_key` becomes the sectionId string from `required_sources`; matches the re-keyed `allSections`.

- [ ] **Step 5: Thread sectionId through `_refreshCrossSectionSources`/`fetchMissingSections`**

`fetchMissingSections(section_keys)` (home.py:2280) builds `sections_by_key` from `str(mli.dataSource.key)` (home.py:2286-2287) and looks up `sections_by_key.get(str(section_key))` (home.py:2296). Re-key both to sectionId:
- home.py:2286-2287: `sections_by_key[str(mli.dataSource.key)] = mli.dataSource` → `sections_by_key[str(self.cacheKeyForSection(mli.dataSource))] = mli.dataSource`.
- home.py:2296: `sections_by_key.get(str(section_key) if section_key else None)` → `sections_by_key.get(section_key)` where `section_key` is now a sectionId string (or `None`).
- home.py:2303 (`already_fetching`): `str(task.section.key) == str(section_key)` → `str(self.cacheKeyForSection(task.section)) == section_key`.

**Preserve Task 3's offline-skip guard** in `fetchMissingSections` (the `getattr(section_obj, 'offline', False): continue` line) and in `_refreshCrossSectionSources` across this rewrite.

- [ ] **Step 6: Run tests**

Run: `/tmp/opencode/venv/bin/python -m pytest tests/test_pinned_sections.py -q`
Expected: PASS.

- [ ] **Step 7: Run full suite**

Run: `/tmp/opencode/venv/bin/python -m pytest -q`
Expected: green.

- [ ] **Step 8: Commit**

```bash
git add lib/windows/home.py tests/test_pinned_sections.py
git commit -m "feat: thread sectionId through hubSettings lookups and allSections"
```

### Task 5: Change `catalog_id` to `|` separator; cross-section merge; remove shim

**Files:**
- Modify: `lib/windows/home.py`
- Test: `tests/test_pinned_sections.py`

This task unifies: catalog_id composition/parsing, the hubSettings config-key reads, and the dead-shim removal. All land together so stored catalog_ids and lookups stay consistent.

- [ ] **Step 1: Write the failing test**

```python
class CatalogIdRoundTripTest(KodiTestCase):
    def test_separator_round_trip(self):
        win = homeWindow({})
        # real section
        composed = win.foreignCatalogId("AAAA:1", "continueWatching")
        src, ident = win.parseCatalogId(composed)
        self.assertEqual(src, "AAAA:1")
        self.assertEqual(ident, "continueWatching")
        # pinned-type sectionId contains '#' and ':'
        composed = win.foreignCatalogId("AAAA:1#movie", "1:all")
        src, ident = win.parseCatalogId(composed)
        self.assertEqual(src, "AAAA:1#movie")
        self.assertEqual(ident, "1:all")
        # home has no prefix
        self.assertEqual(win.parseCatalogId("home.ondeck"), (None, "home.ondeck"))
```

- [ ] **Step 2: Run test to verify it fails**

Run: `/tmp/opencode/venv/bin/python -m pytest tests/test_pinned_sections.py::CatalogIdRoundTripTest -v`
Expected: FAIL.

- [ ] **Step 3: Add helpers**

Define (near `cacheKeyForSection`):

```python
@staticmethod
def foreignCatalogId(section_key, identifier):
    """Compose a catalog_id embedding a section key, recovering both parts."""
    if section_key is None:
        return identifier
    return u'{0}|{1}'.format(section_key, identifier)

@staticmethod
def parseCatalogId(catalog_id):
    """Split a catalog_id back into (source_section_key, identifier). Home => (None, id)."""
    if '|' in str(catalog_id):
        src, ident = str(catalog_id).rsplit('|', 1)
        return src, ident
    return None, catalog_id
```

- [ ] **Step 4: Migrate composition sites** (change `'{0}:{1}'.format(section_key, clean_id)` → `foreignCatalogId`):

- home.py:2204, 2230 (cross-section filtered_native / combined) — inside `getCombinedHubsForSection`, where `section_key`/`source_key` are in scope.
- home.py:3532 (`'{0}:{1}'.format(hub_source_key, clean_identifier)` → `self.foreignCatalogId(hub_source_key, clean_identifier)`).

(Composition sites at 1322, 1374, 1427, 1505, 1750, 1914 are the hub-management dialog writers — verify each against the spec and migrate those that build a `'{key}:{id}'` prefix the same way; if a site is a pure identifier with no section-key prefix, leave it. State for each edited line in your commit.)

- [ ] **Step 5: Migrate the parse site** (home.py:2110, `getRequiredSourceSections`):

Replace:

```python
            if ':' in str(catalog_id):
                source_key = catalog_id.split(':')[0]
                required.add(source_key)
            else:
                required.add(None)  # Home section hub
```

with:

```python
            source_key, _ = self.parseCatalogId(catalog_id)
            required.add(source_key)
```

`parseCatalogId` returns `(None, id)` for Home, so lines 2112-2113 collapse into `required.add(source_key)`.

- [ ] **Step 6: Remove the `find_in_section_hubs` shim** (home.py:2176-2185)

Replace the shim helper and its callers with direct sectionId-keyed lookups:

```python
        def find_in_section_hubs(key):
            return self.sectionHubs.get(key)
```

and update the two call sites that relied on string-normalization of bare int keys (home.py:2192, 2221) — now that `sectionHubs` and `source_key`s are all sectionId strings (Milestone 1 cache + Task 4 source-key format), pass/compare the sectionId string directly. Remove the `str()` raid loop in the shim.

- [ ] **Step 7: Run tests**

Run: `/tmp/opencode/venv/bin/python -m pytest tests/test_pinned_sections.py -q`
Expected: PASS.

- [ ] **Step 8: Run full suite**

Run: `/tmp/opencode/venv/bin/python -m pytest -q`
Expected: green.

- [ ] **Step 9: Commit**

```bash
git add lib/windows/home.py tests/test_pinned_sections.py
git commit -m "refactor: sectionId-keyed hubSettings + '|' catalog_id separator; drop key shim"
```

### Task 6: Backward-compat re-key of persisted `hubSettings`/`librarySettings` at load

**Files:**
- Modify: `lib/windows/home.py` (`loadLibrarySettings` ~1012, `loadHubSettings` ~1154)
- Test: `tests/test_pinned_sections.py`

Existing users have on-disk `hub.settings.*`/`home.settings.*` keyed by bare `section.key` (and `'__home__'`), with `order` as a list of bare keys and catalog_ids using the `:` schema. Re-key them once at load against the current selected server.

- [ ] **Step 1: Write the failing test**

```python
class PersistenceReKeyTest(KodiTestCase):
    def test_library_settings_rekeyed_on_load(self):
        win = homeWindow({})
        old = {
            "1": {"show": False},                 # bare key -> sectionId "SERVERUUID:1"
            "2": {"show": True},
            "order": ["1", "2", "playlists"],
            "playlists": {"show": True},
        }
        # NOTE: FakeServer uuid is "SERVERUUID"; selectedServer here must be a FakeServer
        # with uuid "SERVERUUID" for the assertion below.
        win.librarySettings = win.rekeyLibrarySettings(old)
        self.assertEqual(win.librarySettings["SERVERUUID:1"]["show"], False)
        self.assertEqual(win.librarySettings["SERVERUUID:2"]["show"], True)
        self.assertEqual(win.librarySettings["order"], ["SERVERUUID:1", "SERVERUUID:2", "playlists"])
        self.assertNotIn("1", win.librarySettings)  # old bare key gone

    def test_hub_settings_rekeyed_on_load(self):
        win = homeWindow({})
        old = {
            "__home__": {"custom": True, "hubs": [{"catalog_id": "home.continue"}]},
            "1": {"custom": True, "hubs": [{"catalog_id": "1:continueWatching"}]},
        }
        win.hubSettings = win.rekeyHubSettings(old)
        self.assertIn(None, win.hubSettings)
        self.assertIn("SERVERUUID:1", win.hubSettings)
        # catalog_id re-keyed to '|' schema
        hubs = win.hubSettings["SERVERUUID:1"]["hubs"]
        self.assertTrue(any(h["catalog_id"] == "SERVERUUID:1|continueWatching" for h in hubs))
```

(Adjust the exact `catalog_id` in old hubSettings and the assertion to match how `rekeyHubSettings` composes — the `|` parse round-trips through `parseCatalogId`, so the re-keyed value is `'{SERVERUUID}:1|continueWatching'`.)

- [ ] **Step 2: Run test to verify it fails**

Run: `/tmp/opencode/venv/bin/python -m pytest tests/test_pinned_sections.py::PersistenceReKeyTest -v`
Expected: FAIL.

- [ ] **Step 3: Implement re-key helpers and call from load**

Add the module-level composition helper and predicate, plus the two instance re-key methods:

```python
def hubSectionKey(section_key, server_uuid):
    """Compose a persisted sectionId key for a (bare) section key owned by `server_uuid`.

    Home is None. Only used during on-disk re-key of bare own-server keys; already
    sectionId-shaped keys ('uuid:key') are never passed here.
    """
    if section_key is None:
        return None
    return u'{0}:{1}'.format(server_uuid, section_key)


def _is_bare_key(key):
    """True when a persisted settings key is a bare section wire key (needs re-key).

    Bare keys are integer strings with no ':' separator. sectionId keys ('uuid:key') and
    sentinel strings ('playlists', '/library/sections/watchlist', '__home__') are distinct.
    """
    if key is None:
        return False
    s = str(key)
    return s.lstrip('-').isdigit() and ':' not in s
```

```python
def rekeyLibrarySettings(self, settings):
    """Re-key bare section keys in persisted librarySettings to sectionId (selected server)."""
    if not settings:
        return settings
    server_uuid = plexapp.SERVERMANAGER.selectedServer.uuid
    out = {}
    for key, value in settings.items():
        if key == 'order':
            out[key] = [k if not _is_bare_key(k) else hubSectionKey(k, server_uuid)
                         for k in value]
        elif key == 'playlists' or key == '/library/sections/watchlist':
            out[key] = value
        elif _is_bare_key(key):
            out[hubSectionKey(key, server_uuid)] = value
        else:
            out[key] = value
    return out
```

and

```python
def rekeyHubSettings(self, settings):
    """Re-key persisted hubSettings to sectionId; re-key nested catalog_ids to '|' schema."""
    if not settings:
        return settings
    server_uuid = plexapp.SERVERMANAGER.selectedServer.uuid
    out = {}
    for key, value in settings.items():
        if key == '__home__':
            nk = None
        elif _is_bare_key(key):
            nk = hubSectionKey(key, server_uuid)
        else:
            nk = key  # already sectionId-shaped (own forward-written or foreign)
        if isinstance(value, dict) and 'hubs' in value:
            value = dict(value)
            value['hubs'] = [
                dict(h, catalog_id=self.rekeyCatalogId(h.get('catalog_id', ''), server_uuid))
                for h in value.get('hubs', [])
            ]
        out[nk] = value
    return out

def rekeyCatalogId(self, catalog_id, server_uuid):
    """Re-key a stored ':'-schema catalog_id to the '|' schema."""
    if '|' in str(catalog_id):
        return catalog_id
    if ':' in str(catalog_id):
        src, ident = str(catalog_id).split(':', 1)
        if src.isdigit():
            return u'{0}|{1}'.format(hubSectionKey(src, server_uuid), ident)
    return catalog_id
```

Then call them at end of `loadLibrarySettings` and `loadHubSettings` (before returning), and ensure `saveLibrarySettings`/`saveHubSettings` write the re-keyed form (they already serialize `self.hubSettings`/`self.librarySettings`, which are now sectionId-keyed, and `saveHubSettings` already maps `None → '__home__'`).

`loadLibrarySettings`/`loadHubSettings` order of operations: load raw JSON → parse → re-key → assign to `self.librarySettings`/`self.hubSettings`.

- [ ] **Step 4: Run tests**

Run: `/tmp/opencode/venv/bin/python -m pytest tests/test_pinned_sections.py -q`
Expected: PASS.

- [ ] **Step 5: Run full suite**

Run: `/tmp/opencode/venv/bin/python -m pytest -q`
Expected: green.

- [ ] **Step 6: Commit**

```bash
git add lib/windows/home.py tests/test_pinned_sections.py
git commit -m "feat: re-key persisted library/hub settings to sectionId on load"
```

### Task 7: Migrate `librarySettings` order read/write and menu sites to sectionId

**Files:**
- Modify: `lib/windows/home.py` (`orderPos` ~4121, order write ~3764, sectionMenu hide/show ~3432-3434, `section_id` payload ~3313, pinned_types ~3263)
- Test: `tests/test_pinned_sections.py`

The `order` list and the section-menu show/hide/pinned_types reads must use sectionId so foreign/own libs sharing a key don't clobber.

- [ ] **Step 1: Write the failing test**

```python
class LibrarySettingsOrderTest(KodiTestCase):
    def test_order_keyed_by_section_id(self):
        win = homeWindow({})
        a = FakeSection(key="1", server_uuid="AAA")
        b = FakeSection(key="1", server_uuid="BBB")
        win.librarySettings = {"order": ["AAA:1", "BBB:1"]}
        order = win.librarySettings["order"]
        self.assertIn(win.cacheKeyForSection(a), order)
        self.assertIn(win.cacheKeyForSection(b), order)

    def test_show_hide_keyed_by_section_id(self):
        win = homeWindow({})
        a = FakeSection(key="1", server_uuid="AAA")
        b = FakeSection(key="1", server_uuid="BBB")
        win.librarySettings = {}
        win.librarySettings[win.cacheKeyForSection(a)] = {"show": False}
        self.assertIn(win.cacheKeyForSection(a), win.librarySettings)
        self.assertNotIn(win.cacheKeyForSection(b), win.librarySettings)
```

- [ ] **Step 2: Run test to verify it fails** (it may pass if Task 1 already made `cacheKeyForSection` used by these sites — if so, the assertions validate the behavior; ensure they execute and reflect the sectionId keying)

Run: `/tmp/opencode/venv/bin/python -m pytest tests/test_pinned_sections.py::LibrarySettingsOrderTest -v`
Expected: PASS (or adjust to fail-first if the site isn't yet sectionId-keyed — confirm which).

- [ ] **Step 3: Migrate the sites** to use `cacheKeyForSection`/`sectionId`:

- `orderPos` (home.py:4121-4127): `s.key in order` → `self.cacheKeyForSection(s) in order`; `order.index(s.key)` → `order.index(self.cacheKeyForSection(s))`; PinnedType branch `order.index(s.librarySection.key)` → `order.index(self.cacheKeyForSection(s.librarySection))`.
- Order write (home.py:3764): `[i.dataSource.key for ...]` → `[self.cacheKeyForSection(i.dataSource) for ...]`.
- `sectionMenu` hide (home.py:3432-3434): `section.key not in self.librarySettings` / `self.librarySettings[section.key]` → `self.cacheKeyForSection(section)`; `...['show'] = False`.
- `sectionMenu` hidden-list build (home.py:3313): loop iterates `s` (a section in `sections`) — `self.librarySettings.get(s.key)` → `self.librarySettings.get(self.cacheKeyForSection(s))`; the `'section_id'` payload (home.py:3316) → `self.cacheKeyForSection(s)`.
- `sectionMenu` show dispatch (home.py:3439-3440): `choice["section_id"] in self.librarySettings` / `self.librarySettings[choice["section_id"]]` — now `choice["section_id"]` is the cacheKey/sectionId string, so direct lookup works (no change needed beyond the payload change above).
- `showSections` show/hide filter (home.py:4103): `section.key in self.librarySettings and not self.librarySettings[section.key].get("show", True)` → `ck = self.cacheKeyForSection(section); ck in self.librarySettings and not self.librarySettings[ck].get("show", True)`.
- `showSections` pinned_types (home.py:3263-3267) and watchlist/playlists presence checks (home.py:4077, 4086) — verify these use scalar sentinel keys (unchanged) — do NOT re-key virtual sections.

- [ ] **Step 4: Run tests**

Run: `/tmp/opencode/venv/bin/python -m pytest tests/test_pinned_sections.py -q`
Expected: PASS.

- [ ] **Step 5: Run full suite**

Run: `/tmp/opencode/venv/bin/python -m pytest -q`
Expected: green.

- [ ] **Step 6: Commit**

```bash
git add lib/windows/home.py tests/test_pinned_sections.py
git commit -m "fix: key library order and show/hide state by sectionId"
```

---

## Cross-cutting test: collision-safe cross-section merge (regression for the user bug end-to-end)

**Files:** Test `tests/test_pinned_sections.py`

Add a milestone-2 integration test proving two servers both with key `"1"` never merge/clobber in any keyed structure:

```python
class CrossServerMergeRegressionTest(KodiTestCase):
    def test_two_servers_same_key_do_not_clobber(self):
        win = homeWindow({})
        a = FakeSection(key="1", server_uuid="AAA")
        b = FakeSection(key="1", server_uuid="BBB")
        win.sectionHubs[win.cacheKeyForSection(a)] = home.HubsList([hub("a-hub")])
        win.sectionHubs[win.cacheKeyForSection(b)] = home.HubsList([hub("b-hub")])
        win.allSections[str(win.cacheKeyForSection(a))] = a
        win.allSections[str(win.cacheKeyForSection(b))] = b
        self.assertEqual(len(win.sectionHubs), 2)
        self.assertEqual(win.allSections[str(win.cacheKeyForSection(a))].key, "1")
        self.assertEqual(win.allSections[str(win.cacheKeyForSection(b))].key, "1")
        self.assertNotEqual(win.sectionHubs[win.cacheKeyForSection(a)][0].hubIdentifier,
                            win.sectionHubs[win.cacheKeyForSection(b)][0].hubIdentifier)
```

Run and commit (either within the milestone-2 final task or as its own task):

```bash
/tmp/opencode/venv/bin/python -m pytest tests/test_pinned_sections.py::CrossServerMergeRegressionTest -v
git add tests/test_pinned_sections.py
git commit -m "test: cross-server same-key hub merge regression"
```

---

## Manual smoke checklist (Kodi)

- [ ] Pin a friend's "Movies" to home, switch to own server; hovering the `Movies - friend` tile shows the **friend's** hubs, not your own (previously wrong).
- [ ] Hover your own library that shares the numeric key — its own hubs still show, and are not polluted after visiting the foreign tile.
- [ ] Foreign live tile loads hubs; offline foreign tile shows no hubs and no crash.
- [ ] Custom hub config (Manage Hubs) on a foreign library persists across restart and doesn't collide with an own library sharing the key.
- [ ] Library order and show/hide still work; order persists across restart.
- [ ] Watchlist, Playlists, Home cross-section hubs unaffected.
