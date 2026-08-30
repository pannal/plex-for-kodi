# Multi-Server Home Rail — Phase 2 Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Make a pinned foreign library show up on the home rail (suffixed title, `is.foreign` flag, offline placeholder), with pin/unpin via the section context menu and collision-safe rail reselect.

**Architecture:** Phase 1 built the foundation: `sectionId()` identity (home.py:414), the per-account foreign-library config (`pinForeignLibrary`/`unpinForeignLibrary`/`loadForeignLibraries`, home.py:1031-1078), `ForeignLibrarySection` placeholder (home.py:435), and `resolveForeignLibrary` (home.py:1080). Phase 2 wires them into the rail: `showSections` appends resolved foreign sections at the end of the rail (never into `wantedSections`/`allSections`/hub tasks), `sectionMenu` exposes Pin-to-Home/Remove-from-Home, `_showHubs` guards offline placeholders, and `serverRefresh` re-selects the same rail item by `sectionId()` instead of the collision-prone `.key`.

**Tech Stack:** Python (Py2-era, but tests run under /tmp/opencode/venv Python 3.9), pytest, kodigui `ManagedListItem` properties, existing `lib/windows/home.py` conventions (absolute_import, six, u'' strings).

**Scope decision (Option A — focused visible feature):** The deep cross-section hub pipeline migration (catalog_id encoding, `hubSettings`/`librarySettings` foreign keying, `findInSectionHubs`, the `HOME:` command contract in windowutils.py) is **deliberately deferred** to a later phase. This plan touches only the rail-assembly, the context menu, and the rail-item identity reselect.

**Prerequisite (already on branch `feature/multi-server-home-rail-impl`):** Phase 1 commits through `459e0ccb`, plus the follow-up `fa549f6a` (carry-forward items + comment fix). Working dir is on that branch, clean.

---

## Task 1: Offline-placeholder guard in `_showHubs`

Clicking/selecting a foreign placeholder must not crash. `_showHubs` (home.py:4214) dereferences `section.server.DEFER_HUBS` at 4218 and `section.server.DEFER_HUBS` at 4227; a `ForeignLibrarySection` has `server=None`. Add an early return for offline placeholders, mirroring the existing `section.key is False` guard at 4221. No hubs are fetched for placeholders this phase.

**Files:**
- Modify: `lib/windows/home.py:4221` (the `_showHubs` early-return block)
- Test: `tests/test_pinned_sections.py`

- [ ] **Step 1: Write the failing test**

```python
class ForeignPlaceholderHubGuardTest(KodiTestCase):
    def test_placeholder_never_fetches_hubs(self):
        win = homeWindow({})
        ph = home.ForeignLibrarySection.placeholder(
            server_uuid="ZZZZ", section_key="9", server_name="Away",
            section_title="Movies")
        win._showHubs(ph)
        win = win  # guard path exercised without a server dereference
```

The assertion is "does not raise" (a placeholder has `server=None`, so calling `_showHubs` today crashes on `section.server.DEFER_HUBS` at home.py:4218). Place this test at the end of the file.

- [ ] **Step 2: Run test to verify it fails**

Run: `/tmp/opencode/venv/bin/python -m pytest tests/test_pinned_sections.py::ForeignPlaceholderHubGuardTest -v`
Expected: FAIL — `AttributeError: 'NoneType' object has no attribute 'DEFER_HUBS'` (or similar) from `_showHubs`.

- [ ] **Step 3: Write minimal implementation**

In `_showHubs`, add an offline guard next to the existing `section.key is False` guard (home.py:4221):

```python
        if section.key is False:
            return

        if getattr(section, 'offline', False):
            # foreign placeholder: server is None, no hubs to fetch
            return
```

- [ ] **Step 4: Run test to verify it passes**

Run: `/tmp/opencode/venv/bin/python -m pytest tests/test_pinned_sections.py::ForeignPlaceholderHubGuardTest -v`
Expected: PASS.

- [ ] **Step 5: Commit**

```bash
git add lib/windows/home.py tests/test_pinned_sections.py
git commit -m "fix: guard _showHubs against offline foreign placeholders"
```

---

## Task 2: Append foreign libraries to the rail

`showSections` (home.py:4009) builds the ordered rail from the selected server's libraries. Add a helper `foreignRailSections` that resolves the foreign-library config into appendable sections (suffixed live titles + placeholders), skipping any record that belongs to the currently selected server. Append them at the end of the rail, after the sort. They must NOT enter `wantedSections`, `allSections`, the pinned-type expansion, or the hub-task lists.

**Files:**
- Modify: `lib/windows/home.py` — new method near `resolveForeignLibrary` (~1107); call it in `showSections` (after the sort block, ~4075); mark `is.foreign` in the property block (~4103)
- Test: `tests/test_pinned_sections.py`

- [ ] **Step 1: Write the failing test**

```python
class ForeignRailSectionsTest(KodiTestCase):
    def setUp(self):
        super(ForeignRailSectionsTest, self).setUp()
        self.win = homeWindow({})
        self.win._foreignLibraries = [
            {"server_uuid": "AWAY", "section_key": "1",
             "server_name": "Away", "section_title": "Films"},
        ]

    def test_unknown_server_yields_a_placeholder(self):
        manager = FakeManager([])
        sections = self.win.foreignRailSections(manager=manager,
                                                selected_server_uuid="LOCAL")
        self.assertEqual(1, len(sections))
        ph = sections[0]
        self.assertTrue(ph.offline)
        self.assertEqual("Films - Away", ph.title)

    def test_reachable_server_yields_a_live_section_with_suffixed_title(self):
        live = FakeResolvableSection()  # title "Live Movies"
        class FakeLib(object):
            def sections(self):
                return [live]
        server = FakeServer()
        server.library = FakeLib()
        manager = FakeManager([server])
        sections = self.win.foreignRailSections(manager=manager,
                                                selected_server_uuid="LOCAL")
        self.assertEqual(1, len(sections))
        self.assertFalse(sections[0].offline)
        self.assertEqual("Live Movies - Away", sections[0].title)

    def test_record_for_the_selected_server_is_skipped(self):
        server = FakeServer()
        class FakeLib(object):
            def sections(self):
                return []
        server.library = FakeLib()
        manager = FakeManager([server])
        sections = self.win.foreignRailSections(manager=manager,
                                                selected_server_uuid="SERVERUUID")
        self.assertEqual([], sections)
```

Notes: `FakeResolvableSection.title == "Live Movies"` (tests/test_pinned_sections.py:466). `selected_server_uuid` lets the test control the skip check without a live Kodi server.

- [ ] **Step 2: Run test to verify it fails**

Run: `/tmp/opencode/venv/bin/python -m pytest tests/test_pinned_sections.py::ForeignRailSectionsTest -v`
Expected: FAIL — `AttributeError: 'HomeWindow' object has no attribute 'foreignRailSections'`.

- [ ] **Step 3: Write minimal implementation**

Add `foreignRailSections` next to `resolveForeignLibrary` (home.py:~1107):

```python
    def foreignRailSections(self, manager=None, selected_server_uuid=None):
        """Resolve the foreign-library config into rail-appendable sections.

        Live sections get their server suffix applied to the display title, matching
        the placeholder's suffixed title. Records for the currently selected server
        are skipped (they're already on the rail as normal libraries).
        """
        if selected_server_uuid is None:
            sel = plexapp.SERVERMANAGER.selectedServer
            selected_server_uuid = sel.uuid if sel else None
        sections = []
        for record in self.foreignLibraries():
            if record.get('server_uuid') == selected_server_uuid:
                continue
            section, offline = self.resolveForeignLibrary(record, manager=manager)
            if not offline:
                section.title = u'{0} - {1}'.format(
                    section.title, record.get('server_name'))
            sections.append(section)
        return sections
```

Then wire it into `showSections`. After the sort block (after home.py:4075), before the `# speedup` comment (4077), append foreign sections to the render list **only** (a separate list, excluded from `wantedSections`/`allSections`/pinned/tasks):

```python
        # foreign libraries: appended after local sorting; never enter wantedSections/
        # allSections/hub tasks (their hubs aren't fetched this phase)
        sections = sections + self.foreignRailSections()
```

Then mark the `is.foreign` property in the render loop's property block (home.py:4103-4122). Add a branch alongside the `is.pinned.type` check:

```python
            elif getattr(section, 'offline', False):
                mli.setProperty('is.foreign', '1')
            elif hasattr(section, 'server_uuid') and getattr(section, 'server_uuid', None):
                mli.setProperty('is.foreign', '1')
```

- [ ] **Step 4: Run test to verify it passes**

Run: `/tmp/opencode/venv/bin/python -m pytest tests/test_pinned_sections.py::ForeignRailSectionsTest -v`
Expected: PASS.

- [ ] **Step 5: Run the existing foreign + identity tests to confirm no regression**

Run: `/tmp/opencode/venv/bin/python -m pytest tests/test_pinned_sections.py -q`
Expected: all pass (including Phase-1 `ForeignResolutionTest`, `SectionIdentityTest`).

- [ ] **Step 6: Commit**

```bash
git add lib/windows/home.py tests/test_pinned_sections.py
git commit -m "feat: append pinned foreign libraries to the home rail"
```

---

## Task 3: Pin/Unpin from the section context menu

Add "Pin to home" / "Remove from home" to the normal-library branch of `sectionMenu` (home.py:3311-3361) and dispatch them (3363-3449). Pin captures the section's owning server (uuid + name) plus key + title via the Phase-1 `pinForeignLibrary`; unpin removes it. Both then refresh the rail so the change shows immediately.

New string ids: `35070` ("Pin to home"), `35071` ("Remove from home") — unused, English fallback via `T(ID, eng)`, so no strings.po edit required (add translations later if shipped).

**Files:**
- Modify: `lib/windows/home.py` — `sectionMenu` options (normal-library branch) + dispatch
- Test: `tests/test_pinned_sections.py`

- [ ] **Step 1: Write the failing test**

```python
class ForeignPinMenuTest(KodiTestCase):
    def setUp(self):
        super(ForeignPinMenuTest, self).setUp()
        self.win = homeWindow({})

    def test_is_pinable_reports_when_a_section_is_not_yet_pinned(self):
        server = FakeServer()
        section = FakeSection()
        section.server = server
        self.assertFalse(self.win.isSectionPinnedToHome(section))

    def test_is_pinable_reports_when_a_section_is_pinned(self):
        server = FakeServer()
        server.uuid = "SERVERUUID"
        section = FakeSection(key="3")
        section.server = server
        self.win._foreignLibraries = [
            {"server_uuid": "SERVERUUID", "section_key": "3",
             "server_name": "Tower", "section_title": "Movies"},
        ]
        self.assertTrue(self.win.isSectionPinnedToHome(section))
```

- [ ] **Step 2: Run test to verify it fails**

Run: `/tmp/opencode/venv/bin/python -m pytest tests/test_pinned_sections.py::ForeignPinMenuTest -v`
Expected: FAIL — `AttributeError: 'HomeWindow' object has no attribute 'isSectionPinnedToHome'`.

- [ ] **Step 3: Write minimal implementation**

Add `isSectionPinnedToHome` next to the other foreign helpers (home.py:~1107):

```python
    def isSectionPinnedToHome(self, section):
        return any(
            r.get('server_uuid') == section.server.uuid
            and r.get('section_key') == str(section.key)
            for r in self.foreignLibraries())
```

Add the context-menu option in the normal-library branch of `sectionMenu` (home.py, near the `options.append({'key': 'hide', ...})` line ~3338):

```python
        if self.isSectionPinnedToHome(section):
            options.append({'key': 'unpin_from_home', 'display': T(35071, "Remove from home")})
        else:
            options.append({'key': 'pin_to_home', 'display': T(35070, "Pin to home")})
```

Add dispatch in the `sectionMenu` handler (home.py:~3363-3393, beside the `hide` handler). Look up the section's owning server by uuid for the record fields:

```python
            if selection == 'pin_to_home':
                self.pinForeignLibrary(
                    server_uuid=section.server.uuid,
                    section_key=section.key,
                    server_name=section.server.name,
                    section_title=section.title)
                return self.serverRefresh(section)
            if selection == 'unpin_from_home':
                self.unpinForeignLibrary(
                    server_uuid=section.server.uuid,
                    section_key=section.key)
                return self.serverRefresh(section)
```

The exact dispatch style (how `selection` is read and how the handler returns `self.sectionList[...]` for re-navigation) must be matched to the surrounding code — read `sectionMenu`'s dispatch block (3363-3449) and mirror the `hide`/`show` pattern for how to re-select after refresh.

- [ ] **Step 4: Run test to verify it passes**

Run: `/tmp/opencode/venv/bin/python -m pytest tests/test_pinned_sections.py::ForeignPinMenuTest -v`
Expected: PASS.

- [ ] **Step 5: Run the foreign or identity tests to confirm no regression**

Run: `/tmp/opencode/venv/bin/python -m pytest tests/test_pinned_sections.py -q`
Expected: all pass.

- [ ] **Step 6: Commit**

```bash
git add lib/windows/home.py tests/test_pinned_sections.py
git commit -m "feat: pin and unpin foreign libraries from the section menu"
```

---

## Task 4: Collision-safe rail re-select on server refresh

`serverRefresh` (home.py:3100) re-selects the rail item that matches the just-refreshed section by `.key` at 3121. Two servers can share a key (both `1`), so after a refresh a foreign-or-local section could be matched to the wrong rail item. Compare by `sectionId()` instead — the identity the whole feature is built on — since it is unique per server+key. Foreign sections are already appendable objects whose `sectionId()` is valid.

**Files:**
- Modify: `lib/windows/home.py:3121` (serverRefresh re-select)
- Test: `tests/test_pinned_sections.py`

- [ ] **Step 1: Write the failing test**

`serverRefresh` is too entangled with the live Kodi window (busy.dialog, locks, focus) to unit-test end-to-end, so the reselect-match predicate is extracted into a tiny pure helper `_sameRailSection(a, b)` and tested directly:

```python
class ServerRefreshReselectTest(KodiTestCase):
    def test_same_rail_section_matches_by_section_id(self):
        win = homeWindow({})
        local = FakeSection(key="1")
        ph = home.ForeignLibrarySection.placeholder(
            server_uuid="ZZZZ", section_key="1", server_name="Away",
            section_title="Movies")
        # different servers, same key -> not the same rail item
        self.assertFalse(win._sameRailSection(local, ph))
        same_ph = home.ForeignLibrarySection.placeholder(
            server_uuid="ZZZZ", section_key="1", server_name="Away",
            section_title="Other")
        # same server+key, different label -> same rail item
        self.assertTrue(win._sameRailSection(ph, same_ph))
```

- [ ] **Step 2: Run test to verify it fails**

Run: `/tmp/opencode/venv/bin/python -m pytest tests/test_pinned_sections.py::ServerRefreshReselectTest -v`
Expected: FAIL — `AttributeError: 'HomeWindow' object has no attribute '_sameRailSection'`.

- [ ] **Step 3: Write minimal implementation**

Add a small predicate next to `foreignRailSections` (home.py:~1107):

```python
    def _sameRailSection(self, a, b):
        """Two rail sections are the same rail item iff their sectionIds match."""
        return sectionId(a) == sectionId(b)
```

Replace the `.key` compare in `serverRefresh`'s re-select loop (home.py:3120-3123):

```python
            if section is not None:
                for mli in self.sectionList:
                    if mli.dataSource and self._sameRailSection(mli.dataSource, section):
                        self.sectionList.selectItem(mli.pos())
                        self.lastSection = mli.dataSource
```

- [ ] **Step 4: Run test to verify it passes**

Run: `/tmp/opencode/venv/bin/python -m pytest tests/test_pinned_sections.py::ServerRefreshReselectTest -v`
Expected: PASS.

- [ ] **Step 5: Run the full pinned-sections file to confirm no regression**

Run: `/tmp/opencode/venv/bin/python -m pytest tests/test_pinned_sections.py -q`
Expected: all pass.

- [ ] **Step 6: Commit**

```bash
git add lib/windows/home.py tests/test_pinned_sections.py
git commit -m "fix: reselect rail section by sectionId on server refresh"
```

---

## Task 5: Full suite green + verification

Run the whole suite once to confirm nothing regressed, and confirm the diff remains additive-only (this phase adds code; it should not delete existing behavior).

- [ ] **Step 1: Run the full suite**

Run: `/tmp/opencode/venv/bin/python -m pytest -q`
Expected: all pass (previous green state was 736 passed).

- [ ] **Step 2: Confirm additive-only diff for the phase**

Run: `git diff <first-commit-of-phase2>~1..HEAD --stat`
Expected: only `lib/windows/home.py` and `tests/test_pinned_sections.py` touched; `--numstat` shows inserted lines with 0 deletions on `home.py` for the source changes (the new helpers/methods/guards are additions). If any existing statement was modified in a way that changes behavior beyond the four intended edits, review it before committing.

- [ ] **Step 3: Run a real Kodi smoke test**

Launch Kodi (addon symlinked to this checkout on `feature/multi-server-home-rail-impl`), confirm:
1. Home rail loads as before (no startup errors in `~/Library/Logs/kodi.log`).
2. Select a library → context menu shows "Pin to home".
3. Pin another server's library, switch to a different server, and confirm the pinned foreign library appears at the end of the rail with a ` - {server}` suffix and `is.foreign` styling.
4. Switch the offending server offline (or remove it) and confirm the rail shows the placeholder without crashing on click/select.

Note: full Kodi interaction can't be automated here; the automated suite (Step 1) is the gate. The Kodi smoke test is manual and only if you run it — mark this step done only when you've actually observed it or explicitly defer it.

- [ ] **Step 4: Commit any follow-ups**

If the smoke test revealed fixes, implement them with their own tests/commits. Otherwise no commit needed.

---

## Deferred to a later phase (deliberately NOT in this plan)

These are the deep cross-server collision seams and UI polish for the *next* phase. Do NOT implement them here:

- **catalog_id encoding** (home.py:2168, 2194) embeds bare `section_key`; must become sectionId to stop cross-server hub-merge collisions.
- **`hubSettings` / `librarySettings` foreign keying** — persist/merge per server+section; `findInSectionHubs` (home.py:2141) and the `str(source_key)` string-match hacks.
- **`sectionHubs` / `allSections` / `wantedSections` / `lastHubs` keyed lookups** — migrate to sectionId (~40 call sites).
- **`HOME:` command contract** (windowutils.py:16 `'HOME:{0}'.format(section)`) — cross-file; the emitter must send a sectionId.
- **Hub fetching for foreign sections** (they render but fetch no hubs this phase).
- **Offline→live transition on `serverRefresh`** and the offline marker UI.
- **Carry-forward from Phase-1 review (live-title suffix)** — already satisfied in Task 2 (live foreign sections get ` - {server}` on `.title`).
- **Carry-forward from Phase-1 review (pin-over-placeholder `.key == 'None#...'`)** — still open; not exercised until hub-fetch touches foreign pins. Tracked for the hub phase.
