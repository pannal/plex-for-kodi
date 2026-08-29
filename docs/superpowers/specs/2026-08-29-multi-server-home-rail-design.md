# Multi-Server Libraries in the Home Rail — Design

Date: 2026-08-29
Status: Approved (design), pending spec review

## Problem

The home rail (left rail) currently shows libraries only from the single **selected server** (`selectedServer`). To browse a friend's shared server you must switch the server selector to that server, which swaps out **your own** libraries. The goal: let a user pin libraries from *other* servers into the home rail so they can open, e.g., `Movies - MyFriend` directly, without losing their own server's context.

This is a Plex-shared-library scenario: one signed-in account has access to both "your" server and a friend's server; both appear together in the same server list (`PlexServerManager.getServers()`).

## Feasibility / architecture basis

The codebase is already **server-per-section** at the data/navigation layers, which is what makes this tractable:

- `LibrarySection` objects carry the `server` they were constructed with (`PlexObject.__init__`, `plexobjects.py:179`).
- Hub fetching routes through the section's own server: `self.section.server.hubs(...)` (`home.py:87`, `home.py:1140`).
- Opening a library passes the section into `LibraryWindow` (`opener.py:156-174`), and `library.py` queries via `self.section.server.uuid` / `section.server` throughout (`library.py:504`, `1179`).
- The server manager already maintains every connected server independently and runs reachability on **all** servers (`plexservermanager.py:109-119`, `updateReachability` at `:234`). A friend's server can be queried without switching `selectedServer`.

Precedent that a non-selected server already drives a rail entry: `WatchlistSection` is built from `getDiscoverServer()` and injected into the same rail (`home.py:3889`).

Consequence: the change is concentrated in the home window's menu assembly (`showSections`, `home.py:3872`) and the collision-prone in-memory state, **not** in the deep-dive/navigation/playback layers.

## Decisions (from brainstorming)

- **Conceptual model**: rail = selected server's libraries + a separately pinned, global-per-account set of foreign libraries.
- **Placement**: foreign libraries render in the same rail (not a separate grouped/collapsed section) in the same visual rail as own libraries; ordered by the global foreign-array order, appended after the selected server's libraries.
- **Labeling**: foreign entries always suffixed `"{title} - {server_name}"`; own-server entries keep plain title.
- **Visual flag**: dashed/muted accent + type icon (Option A). No extra badge/icon by default (fallback to a small server glyph only if the skin template can't restyle the rail item container).
- **Opt-in**: context-menu "Pin to home rail", reached by temporarily switching the server selector to the friend's server and opening their library (server-switch flow). No dedicated picker.
- **Offline**: kept visible, visibly marked unreachable; gentle message on open.
- **Selected-server state**: entering a foreign library does **not** change the selected server.
- **Pinned set scope**: global per-account (one list, shown regardless of selected server).
- **Account scope**: single signed-in account only.
- **Playlists**: remain bound to the selected server; out of scope.

## Approach

**Approach B — server-aware runtime identity, separated from the wire key.**

The Plex API relies on the section's real `key` (e.g. `/library/sections/{key}/all`, `plexlibrary.py:207,237`). So `section.key` is left untouched. Instead we introduce a parallel **identity** used only by in-memory, collision-prone structures. This mirrors the existing `viewtype.{server_uuid}.{key}` convention (`library.py:504`).

## 1. Data model & config

**Foreign library record** (serializable):
```
{
  'server_uuid':    str,   # owning server
  'section_key':    str,   # Plex section key within that server
  'server_name':    str,   # denormalized label (rail / resolution)
  'section_title':  str,   # denormalized base title
}
```

Stored in a new **global per-account** addon setting `home.foreign_libraries.<account>` as a JSON array. Independent of which server is selected.

**Runtime section identity**: a single new string property `sectionId` on sections in `home.py`, separate from `key`. It is **stable and uuid-based** — the display label `server_name` is NOT part of the identity (it can change); `server_name` is used only for rendering the suffixed title.
- Real section: `sectionId = "{uuid}:{key}"` (e.g. `"a1b2...:1"`).
- Placeholder (offline) section: same `sectionId` from the config record's `server_uuid` + `section_key`, even though `server=None`.
- Virtual sections (Home/Watchlist/Playlists): distinct sentinel identities (`"home"`, `"watchlist"`, `"playlists"`), matching their scalar `key`.
- `PinnedTypeSection`: `sectionId = f"{sectionId}#{item_type}"` (mirrors `pinnedSectionKey`, `home.py:410`).

`section.key` and the wire format are untouched; `sectionId` is purely the in-memory/dict key and the sortable identity.

**Pinnable**: only library-type sections (`movie`/`show`/`artist`). Home/Watchlist/Playlists are never pinnable.

## 2. Home-rail assembly (`showSections`, `home.py:3872`)

1. Build base list exactly as today from `selectedServer.library.sections()` (`home.py:3901`) + Home/Watchlist/Playlists/pinned-type.
2. **Append pinned foreign libraries** from `home.foreign_libraries.<account>`:
   - Resolve `(server_uuid, section_key)` → live `LibrarySection` (foreign flag + suffixed title) when server known + section queryable. Resolution calls `server.library.sections()` and matches by `section.key` (no single-section-by-key helper exists; `plexlibrary.py:22-37`). Matches refresh the denormalized `section_title`.
   - Otherwise render a **placeholder section** (same `sectionId`, suffixed title, `offline=True`, `server=None`) so it stays visible-but-marked. Reachability transitions re-run the resolve step on `serverRefresh()` rebuild.
3. **Ordering**: own libraries keep the existing per-selected-server `librarySettings["order"]` sort (`home.py:3925`). Foreign items render in the **same rail, not as a separate grouped section**, appended after the selected server's libraries, ordered by their position in the global `home.foreign_libraries.<account>` array (so their relative order is consistent across selected servers). Foreign items are movable within the foreign block via the existing "Move" flow; arbitrary ordering interleaved with own libraries is out of scope because own-lib order is per-server while foreign order is global (would contradict global consistency).

**Collision-safe runtime state — migrate all section-keyed state to `sectionId`.** This is a **cross-cutting rename across the whole home window**, not a 4-line change. The following in `home.py` are keyed by bare `section.key` (or `str(section.key)`) today and MUST move to `sectionId` so foreign sections (with colliding keys like two servers' `"1"`) never clobber each other:
- `self.sectionHubs[...]` — read/write at `858, 1325, 1569, 1733, 1804, 1977, 2006, 2011, 2206, 2244, 2425, 2853, 2880, 3754, 3763, 3812, 4087, 4131, 2880`.
- `self.allSections[...]` — built at `3908, 3910`, read at `1754, 2117-2137, 2165, 2172, 3951-3953, 4167`.
- `self.wantedSections` — built `3907, 3915`, consumed `3955, 2137, 2180`.
- `self.lastSection` comparisons/focus — `858, 2218, 2425, 3724, 3739`.
- `getRequiredSourceSections(...)` / `getCrossSectionSources(...)` produce and consume these keys (`1913, 1921, 2001, 2149, 2218`) and must be made `sectionId`-based so Home cross-section hubs merge foreign libraries correctly despite key collisions.

The migration is mechanical (all keys derive from section objects; introduce `sectionId` accessors and replace `.key` with `.sectionId` at these sites), confined to `home.py`, and leaves the wire format and `section.key` untouched. Every function that accepts a section key for hub/merge lookups takes `sectionId` from then on.

**Hub tasks**: unchanged — foreign sections get a `SectionHubsTask` (`home.py:3955`) and pinned foreign collections views a `PinnedTypeHubsTask` (`home.py:3960`); both already route via `section.server`.

## 3. Context menu & visual flagging (`sectionMenu`, `home.py:3101`)

- **"Pin to home rail"**: shown on a section where `server != selectedServer` (you've switched to a friend's server). Writes the foreign record, refreshes rail. Mirrors the "Pin collections to the top bar" pattern.
- **"Unpin from home rail"**: shown on any rail entry in the foreign list (no server switch needed). Removes record, refreshes rail. Lightweight confirm if it's the currently-pinned/foreign entry.
- **Visual**: foreign entries get an `is.foreign` rail property → dashed/muted accent + type icon in the skin template (`script-plex-home.xml.tpl`). Fallback: small server/network glyph on the icon cell if the rail container can't be restyled. Verify skin support during planning.
- **Offline marker**: source of truth is `server.reachability` (already refreshed across all servers, `plexservermanager.py:234`; no new polling). Rail shows muted/offline indicator; selecting shows a gentle "server unreachable" message and unloads.

## 4. Persistence, edge cases, testing

**Persistence/lifecycle**
- Read/written like `librarySettings` (`home.py:965-982` pattern): loaded at init, JSON to the setting on change (pin/unpin/order).
- Denormalized `server_name`/`section_title` allow rendering when a server is unreachable at startup; live resolution refreshes `section_title` when reachable (via `server.library.sections()` match by `section.key`).
- Keyed by account; lazy-prune records whose server uuid is no longer known on load.

**Edge cases**
- **Server unshared/removed**: resolves to placeholder (`offline=True`); user can unpin; not silently dropped on transient loss.
- **Foreign hidden/hide**: hiding a foreign library = unpin (bypasses own-server hide logic).
- **Pinned foreign collections/type-views**: work via `PinnedTypeSection` delegation + server-routed task — no new code beyond identity.
- **Pinning an own-base entry**: dedupe by `sectionId`; no-op (already in rail). Unpin only affects foreign records.
- **Cross-section hubs** (`hasCrossSectionHubs`): keyed by identity so foreign libs merge into the Home cross-section hub correctly despite key collisions.
- **Playlists**: unchanged, selected-server bound (out of scope).

**Testing** (pytest, `tests/`, `pytest.ini`)
- `sectionId` generation incl. the collision case (two servers, same key → distinct identities) and pinned-type suffix; placeholder keeps identity from config uuid despite `server=None`.
- Config add/remove/dedupe.
- `showSections` foreign-append and placeholder-vs-real resolution (mock server manager).
- Foreign-array ordered rendering (appended after own libs, in array order).
- Offline placeholder rendering path.
- **Cross-section hub merge with foreign libs** — the riskiest regression: replicate two servers both having section key `"1"`, verify Home cross-section hubs merge both without clobbering (covers the `allSections`/`sectionHubs`/`wantedSections`/`getRequiredSourceSections` migration).
- Manual checklist (symlinked addon on Kodi): server-switch pin flow, unpin, offline server, same-name collisions, watchlist/home cross hubs unaffected.

## Out of scope
- Multiple Plex accounts.
- Dedicated pin picker dialog (deferred; server-switch flow covers it).
- Playlists across foreign servers.
- Per-selected-server foreign pin sets.
