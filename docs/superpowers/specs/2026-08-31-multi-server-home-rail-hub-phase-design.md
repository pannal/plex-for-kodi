# Multi-Server Home Rail — Hub Phase Design

Date: 2026-08-31
Status: Approved (design), pending spec review

## Problem

Phase 1/2 delivered the home-rail feature: pinned foreign libraries appear on the rail and open/play correctly. But the **hub-preview pipeline is still keyed by bare `section.key`**, which collides across servers:

- Hovering a *live* foreign tile (friend's "Movies", key `"1"`) shows the hubs of my own library sharing that key ("adult movies"), because `_showHubs` reads `sectionHubs[section.key]` (home.py:4291).
- It is **bidirectional/polluting**: the foreign fetch nulls `sectionHubs[section.key]` (home.py:4335) and `sectionHubsCallback` overwrites it with the foreign hubs (home.py:3955), corrupting the local library's cache until a forced refresh.
- Foreign sections are *not* scheduled for hub fetch at all this phase (appended after the hub-task block, home.py:4161), so even with a unique key they'd render no hubs.

This phase migrates all section-keyed hub state to the collision-safe `sectionId` identity introduced in Phase 1, schedules hub fetch for live foreign sections, persists custom hub/library settings keyed by `sectionId`, and removes the now-obsolete `find_in_section_hubs` string/int shim. This is the deferred "section-2 migration" from the Phase 2 plan.

## Decisions (from brainstorming)

- **Scope**: full migration — collision-safe keying, foreign hub fetch, `sectionId`-keyed persistence for own + foreign, cross-section merge with foreign libs, shim removal.
- **Key scheme**: `sectionId` for ALL entries (own + foreign), with a one-time re-key of existing persisted settings on load.
- **Sequencing**: phased. Chunk 1 = in-memory runtime caches + foreign hub fetch + shim removal. Chunk 2 = persisted settings re-key. Each chunk independently testable/reviewable, lands green.
- **`catalog_id` encoding**: prefix separator changes from `:` to `|`, parsed with `rsplit('|', 1)` (Section 2, Option A).
- **Virtual sentinels**: Home stays a distinct key (`None`); `'playlists'`/`'watchlist'` sentinels unchanged. Only real libraries + pinned-type migrate to `sectionId`. Minimizes the `key is None` surface.

## 1. Canonical identity & in-memory cache keying

Single canonical string `sectionId(section)` (already implemented, home.py:414) keys all in-memory cross-server state:

| Cache | Today | Becomes |
|---|---|---|
| `self.sectionHubs[...]` | heterogeneous (None, `'playlists'`, `'/library/sections/watchlist'`, raw `int`, `'N#type'`) | real libs: `sectionId` (`'uuid:key'`); pinned-type: `'uuid:key#type'`; virtual sentinels (`None`, `'playlists'`, `'watchlist'`) unchanged |
| `self.allSections[...]` | `str(section.key)` | `str(sectionId)`; callers at home.py:1927/2341/2345/4141 feed `sectionId` instead of bare key |
| `self.wantedSections` | list of bare wire keys | **unchanged as wire keys** — passed to `server.hubs(section_ids=...)` at the wire boundary; cross-section *lookups* use `sectionId`, never `wantedSections` membership |
| `self.lastHubs` / `lastSection` key-derived logic | `.key` compares / dict-key uses | sectionId-based |

Key migration sites (all in `lib/windows/home.py`):
- `sectionHubs` read/write/null/iteration: home.py:906, 1498, 1742, 1906, 1977, 2150, 2336-2338, 2379, 3026, 3946, 3955, 4004, 4019, 4291, 4334-4335.
- `lastHubs`/`lastSection` `.key`-derived: home.py:906, 1635-1637, 2391, 2598, 3524.

Home (`None`) and virtual sentinels keep their current keys; the `key is None` guards (home.py:2399, 2660, 3068, 3522, 3958, 4050) are untouched.

## 2. `catalog_id` encoding

Today `catalog_id = '{section_key}:{identifier}'`, parsed with `catalog_id.split(':')[0]` (home.py:2110). `sectionId` (`'uuid:key'`) contains `:`, which would break `split(':')[0]`.

**Change**: separator becomes `|`; parse with `rsplit('|', 1)` so the left side is the full `sectionId` (may contain `:` and `#` for pinned-type) and the right side is the hub identifier (may contain `:` like `'continueWatching'`).

- Composition sites (home.py:1322, 1374, 1427, 1505, 1750, 1914, 2204, 2230, 3532): `'{sectionId}|{identifier}'`.
- Parse site (home.py:2110): `rsplit('|', 1)`.
- Home special-case: keep the existing `None`-prefix handling (Home has no sectionId prefix at those sites today for the `is_home` branch).
- Nested catalog_id keys inside persisted `hubSettings` are re-keyed during the load migration (Section 4).

This makes the `find_in_section_hubs` string/int shim (home.py:2176-2185) dead: keys are now stable sectionId strings, so a direct `sectionHubs.get(sectionId)` suffices. Remove the shim and its `str()` fallback branches.

## 3. Foreign hub fetch + shim removal

**3a. Schedule hub fetch for live foreign sections.** In `showSections`, after the foreign sections are appended (home.py:4161), also schedule a `SectionHubsTask(section, ...)` for each **live** (non-offline) foreign section, exactly like own libraries. `SectionHubsTask` already routes via `section.server` (home.py:87-88), so a foreign section fetches from its own server. Offline placeholders are **never** scheduled (guard `getattr(section, 'offline', False)`), matching the existing `_showHubs` offline early-return (home.py:4281) and the `SectionHubsTask` `server is None` bail (home.py:82).

**3b. `_showHubs` collision-safe read/null.** Read (home.py:4291) and null (home.py:4334-4335) resolve by `sectionId`. `sectionHubsCallback` write (home.py:3955) and `crossSectionHubsCallback` write (home.py:2379) likewise. This fixes the user-reported wrong-hub + pollution bug.

**3c. Cross-section merge.** `getRequiredSourceSections`/`getCrossSectionSources` produce/consume sectionId keys; `_refreshCrossSectionSources` (home.py:2314) and `fetchMissingSections` (home.py:2280) look up by sectionId. Home cross-section hub cache (`sectionHubs[None]`) stays `None`-keyed. Foreign libs merge into Home cross-section hubs by sectionId with no key collision.

**3d. Skipping offline foreign sources.** `_refreshCrossSectionSources`/`fetchMissingSections` must skip `offline`/`None`-server foreign sources rather than scheduling a fetch that bails.

## 4. Persisted settings re-key

Both buckets are per-selected-server: `'home.settings.{server_uuid[-8:]}.{ACCOUNT_ID}'` and `'hub.settings.{...}'`, loaded once at init.

**4a. Load-time backward-compat migration.** On `loadLibrarySettings`/`loadHubSettings`, one-time re-key against the current `selectedServer`:
- Entries whose key is a **bare wire key** → rewrite to `str(sectionId)` (`'{uuid}:{key}'`).
- Entries already `'uuid:key'`-shaped, or sentinels (`'home'`, `'playlists'`, `'watchlist'`, `'__home__'` transform) → left intact.
- `librarySettings["order"]` is a **list** of bare keys → re-key each element to `str(sectionId)`. `orderPos()` (home.py:4121) compares `sectionId(s) in order` / `.index(sectionId(s))`; the order-write (home.py:3764) stores `sectionId(i.dataSource)`.
- Nested `hubSettings` catalog_id keys (which embed the section key) → re-keyed to the new `|` scheme (Section 2).

**4b. Menu read/write sites** become sectionId-keyed: hide/show (3432-3434), pinned_types (3263-3267), hidden-list (3313), playlists/watchlist (4077, 4086), order-write (3764).

**4c. `hubSettings` config_key** sites: all `config_key = str(section_key)` become `str(sectionId)`; Home stays `None`/`'__home__'`. Nested per-hub catalog_id keys re-keyed during load migration.

## 5. Testing

Harness already green: `tests/test_pinned_sections.py`, `KodiTestCase`, `homeWindow({})`, `FakeServer`/`FakeSection` (extended with `server_uuid` in Phase 2). Add:

1. **Cache collision (regression for user's bug):** two servers both library key `"1"` store/read `sectionHubs` independently; hovering server-B's "Movies" never returns server-A's cached hubs; fetching B does not clobber A's cache.
2. **sectionId keying of caches:** `_showHubs` read/null, `sectionHubsCallback`, `crossSectionHubsCallback` resolve by sectionId.
3. **Foreign hub fetch scheduled:** live foreign section gets `SectionHubsTask`; offline placeholder does not.
4. **`catalog_id` `|` round-trip:** compose + `rsplit('|', 1)` recovers sectionId and identifier, incl. pinned-type (`uuid:1#movie`) and home.
5. **Shim removal:** `find_in_section_hubs` gone; direct sectionId lookup on merge path.
6. **Cross-section merge with colliding keys:** two servers both key `"1"`, Home cross-section hubs merge both without clobber.
7. **Persistence re-key:** old bare-key `hubSettings`/`librarySettings` re-key to `uuid:key` on load; sentinels untouched; `order` list re-keyed; nested catalog_ids re-keyed; re-save preserves.
8. **Offline placeholder never scheduled** (guard).

Full existing suite (744+) stays green through each chunk.

## Out of scope
- Multiple Plex accounts.
- Dedicated pin picker dialog.
- Playlists across foreign servers.
- Per-selected-server foreign pin sets.
- Offline→live in-place rail swap animation/focus polish (Phase 2 already handles the identity transition; this phase does not add visual polish).
