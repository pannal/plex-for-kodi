# coding=utf-8
"""Watch Together — Kodi bridge (spec: phase 2 design; docs/watch-together.md).

Kodi-side glue only: joins/leaves rooms, feeds local playback state to the
supervisor at 1 Hz, applies remote syncplay state back onto the player, runs
the lobby poll for invite toasts, and owns one global OSD status property.
The protocol itself lives in lib/watchtogether.py + lib/syncplay.py + lib/ws.py.
"""

from __future__ import absolute_import

import json
import threading
import time

from kodi_six import xbmc, xbmcgui
from plexnet import mediachoice, plexapp, plexlibrary, plexobjects

from lib import p3i_detector, plex, plexpeople, player, syncplay, util, watchtogether, ws
from . import busy, kodigui


def parse_source_uri(uri):
    """Room sourceUri -> (machineIdentifier, ratingKey), or (None, None).

    Accepts bare `server://<machine>/…/library/metadata/<key>` and the
    provider-prefixed `provider://…/server://<machine>/…` form (§4)."""
    if not uri or "server://" not in uri:
        return None, None
    rest = uri.rsplit("server://", 1)[1]
    machine, _, path = rest.partition("/")
    marker = "library/metadata/"
    idx = path.find(marker)
    if not machine or idx < 0:
        return None, None
    rating_key = path[idx + len(marker):].split("/")[0].split("?")[0]
    if not rating_key:
        return None, None
    return machine, rating_key


WATCHTOGETHER_HUB_ID = "watchtogether.rooms"
WATCHTOGETHER_PLACEHOLDER = "script.plex/thumb_fallbacks/movie16x9.png"
LOCAL_CHANGE_GRACE = 1.5   # seconds to hold off remote applies after a local change
WT_SEEK_COOLDOWN = 3.0     # seconds between remote-driven seeks (refill guard)
WT_WIDE_SEEK_DELTA = 10.0  # drift threshold once tempo is unavailable on a player
WT_PAUSE_CATCHUP_MAX = 2.0 # cap on a local pause catch-up (opt-in, see _pause_catchup)
WT_TEMPO_FAIL_LIMIT = 2    # consecutive SetTempo failures before tempo is given up
DETECTOR_TIMEOUT = 30.0    # seconds: pre-scan readiness deadline before fail-open


def participant_names(users):
    """users[] -> "A", "A and B", "A, B and C" (title, falling back to username)."""
    names = []
    for user in users or []:
        if not isinstance(user, dict):
            continue
        name = user.get("title") or user.get("username")
        if name:
            names.append(name)
    if not names:
        return ""
    if len(names) == 1:
        return names[0]
    return "{0} and {1}".format(", ".join(names[:-1]), names[-1])


def identity_user_id(key):
    """userID from a relay roster identity, or None if it is unparseable."""
    try:
        user_id = json.loads(syncplay.strip_identity(key)).get("userID")
    except (ValueError, TypeError, AttributeError):
        return None
    return None if user_id is None else str(user_id)


def identity_device_name(key):
    """deviceName from a relay roster identity, or None."""
    try:
        return json.loads(syncplay.strip_identity(key)).get("deviceName")
    except (ValueError, TypeError, AttributeError):
        return None


def _player():
    """The live PlexPlayer, or None during addon shutdown (player.PLAYER is
    deleted by player.shutdown() while daemon threads may still tick)."""
    return getattr(player, "PLAYER", None)


STATUS_INVITED = "invited"
STATUS_JOINING = "joining"
STATUS_BUFFERING = "buffering"
STATUS_WATCHING = "watching"


def member_state(on_roster, is_ready, stale=False, slow=False):
    """Which status row a room member gets (2026-10-23 live-session evidence)."""
    if not on_roster:
        return STATUS_INVITED
    if is_ready is None:
        return STATUS_JOINING
    if is_ready is False or stale or slow:
        return STATUS_BUFFERING
    return STATUS_WATCHING


def state_label(state, ready_label):
    """Translated label; `ready_label` is Ready in the lobby, Watching elsewhere."""
    if state == STATUS_INVITED:
        return util.T(35076, "Invited")
    if state == STATUS_JOINING:
        return util.T(35092, "Joining")
    if state == STATUS_BUFFERING:
        return util.T(35091, "Buffering")
    return ready_label


def _roster_entry(roster, user_id):
    """The roster entry for a participant id (matched via identity_user_id),
    or None when they are not on the roster."""
    target = str(user_id)
    for key, entry in (roster or {}).items():
        if not isinstance(entry, dict):
            continue
        if identity_user_id(key) == target:
            return entry
    return None


def member_state_label(user_id, roster, state_for, ready_label):
    """The status label for one participant: member_state + state_label."""
    entry = _roster_entry(roster, user_id)
    on_roster = entry is not None
    is_ready = entry.get("isReady") if entry is not None else None
    stale, slow = state_for(user_id) if state_for is not None else (False, False)
    return state_label(member_state(on_roster, is_ready, stale, slow), ready_label)


def room_info_rows(room, live_ids, state_for=None):
    """One row per room user for the info dialog, marking who is connected.
    `live_ids` are the userIDs seen on the relay roster (only known while
    connected to that room).

    With `state_for`, `sub` becomes the member-status label (Watching for a
    live member) instead of the bare "Live"/username."""
    rows = []
    for user in (room.participants if room else []):
        if not isinstance(user, dict):
            continue
        name = user.get("title") or user.get("username") or ""
        user_id = str(user.get("id"))
        is_live = user_id in live_ids
        if state_for is None:
            sub = util.T(35068, "Live") if is_live else (user.get("username") or "")
        else:
            stale, slow = state_for(user_id)
            state = member_state(is_live, True if is_live else None, stale, slow)
            sub = state_label(state, util.T(35090, "Watching"))
        rows.append({
            "name": name,
            "sub": sub,
            "thumb": user.get("thumb") or "",
            "live": is_live,
        })
    return rows


def lobby_rows(room, roster, preparing_id=None, state_for=None):
    """One row per room user for the lobby, with readiness status.

    Status is "Ready" when the user's id is on the roster with isReady True,
    else "Invited" (they have not joined/readied yet). `preparing_id`, when it
    matches a user's id (compared as str), overrides the status with
    "Preparing…" — the local self row while a p3i pre-scan is in flight.

    With `state_for` (a callable(user_id) -> (stale, slow)) the status is the
    richer member-state set (Joining/Buffering/Watching) instead of the bare
    Ready/Invited."""
    ready = syncplay.ready_member_ids(roster)
    rows = []
    for user in (room.participants if room else []):
        if not isinstance(user, dict):
            continue
        user_id = str(user.get("id"))
        if state_for is None:
            status = util.T(35075, "Ready") if user_id in ready \
                else util.T(35076, "Invited")
        else:
            status = member_state_label(user_id, roster, state_for,
                                        util.T(35075, "Ready"))
        if preparing_id is not None and user_id == preparing_id:
            status = util.T(35088, "Preparing…")
        rows.append({
            "title": user.get("title") or user.get("username") or "",
            "thumb": user.get("thumb") or "",
            "status": status,
        })
    return rows


def invite_rows(invitees):
    """list[plexpeople.Invitee] -> list-item dicts for the invite picker.

    `access_unknown` is "1" on a shared server (the sharee list cannot be
    enumerated, so the row is labelled) and "" otherwise."""
    rows = []
    for invitee in invitees or []:
        rows.append({
            "id": invitee.id,
            "title": invitee.title or "",
            "thumb": invitee.thumb or "",
            "access_unknown": "1" if invitee.access_unknown else "",
        })
    return rows


class WatchTogetherRoomItem(object):
    """One room tile. Not a PlexObject — the home renderer must not treat it
    as media, so `get()` is inert and `cachable` is False."""
    def __init__(self, room, image=None):
        self.room = room
        self.type = "watchtogether"
        self.title = room.title
        self.subtitle = participant_names(room.participants) or \
            util.T(35054, "{} watching").format(len(room.participants))
        self.image = image or WATCHTOGETHER_PLACEHOLDER
        self.cachable = False
        # Home's hub position/reselect and storeLastBG read these directly;
        # a plain object must still carry them (id itself is never logged).
        self.ratingKey = str(room.id)
        self.art = None
        self.thumb = None

    def get(self, key, default=None):
        return default


class WatchTogetherRoomsHub(plexlibrary.BaseHub):
    """Client-built Home hub (no Plex hub backs it), modelled on CollectionsHub.
    `factory()` rebuilds the item list from the bridge's live cache."""
    TYPE = "Hub"
    type = "watchtogether"
    hubIdentifier = WATCHTOGETHER_HUB_ID

    def __init__(self, factory, *args, **kwargs):
        super(WatchTogetherRoomsHub, self).__init__(False, *args, **kwargs)
        self._factory = factory
        self.items = factory()
        self.set("title", util.T(35053, "Watch Together"))

    def getCleanHubIdentifier(self, is_home=False):
        return self.hubIdentifier

    def reset(self):
        # BaseHub.reset reads items[0].container; ours are plain objects
        self.set("offset", 0)
        self.set("size", len(self.items))
        self.set("more", "")

    def reload(self, **kwargs):
        self.items = self._factory()
        return self


def needs_takeover_confirm(room, playing_key):
    """True when joining may take over a *different* item already playing.

    Call only when a video is playing. Unknown room content or an
    unidentifiable playing item both prompt, to be safe."""
    _, room_key = parse_source_uri(room.source_uri)
    if not room_key or not playing_key:
        return True
    return str(playing_key) != room_key


def playing_rating_key():
    video = getattr(player.PLAYER, "video", None)
    return str(getattr(video, "ratingKey", "") or "")


def confirm_takeover(room):
    """True if joining may proceed: nothing playing, the room's own content,
    or the user confirmed the takeover."""
    if not player.PLAYER.isPlayingVideo():
        return True
    if not needs_takeover_confirm(room, playing_rating_key()):
        return True
    return xbmcgui.Dialog().yesno(
        util.T(35053, "Watch Together"),
        util.T(35060, "You are already watching something else. "
                      "Join and take over playback?"))


def confirm_switch():
    return xbmcgui.Dialog().yesno(
        util.T(35053, "Watch Together"),
        util.T(35061, "Leave the current room and join this one?"))


def confirm_leave():
    """Confirm leaving the room (used by the OSD menu and the dialog)."""
    from . import optionsdialog
    button = optionsdialog.show(
        util.T(35056, "Leave room"),
        util.T(35086, "Leave this Watch Together room?"),
        util.T(32328, "Yes"),
        util.T(32329, "No"))
    return button == 0


def host_menu_entry(item):
    """The "Start Watch Together" dropdown entry for `item`, or None when the
    item cannot resolve a sourceUri (no server uuid / ratingKey).

    Shared by the episodes view, the pre-play screen and Home, so the
    eligibility rule lives in one place."""
    server = getattr(item, "server", None)
    if not (server is not None and getattr(server, "uuid", None)
            and getattr(item, "ratingKey", None)):
        return None
    return {"key": "start_watch_together",
            "display": util.T(35080, "Start Watch Together")}


def confirm_host(dialog_props=None):
    """Confirm starting a new room when one is already joined: host() leaves the
    current room, so ask first (mirrors confirm_switch)."""
    from . import optionsdialog
    button = optionsdialog.show(
        util.T(35053, "Watch Together"),
        util.T(35081, "Leave the current room and start a new one?"),
        util.T(32328, "Yes"),
        util.T(32329, "No"),
        dialog_props=dialog_props)
    return button == 0


def start_hosting(item, dialog_props=None):
    """Confirm when a room is already joined, then host `item`."""
    if bridge.supervisor is not None and not confirm_host(dialog_props):
        return
    bridge.host(item)


def _ws_factory(host, port, on_open, on_message, on_close):
    return ws.WSClient(host, port, on_message, on_open=on_open, on_close=on_close)


class WatchTogetherBridge(object):
    """Singleton wiring room <-> supervisor <-> player.

    Threads: the main thread drives join/leave; one daemon thread feeds local
    state at 1 Hz while joined (or polls the lobby every 15s while idle); the
    supervisor thread owns the socket and runs the session callbacks — those
    must never block, so REST refreshes the dialogs want run on their own
    throwaway threads."""

    def __init__(self):
        self.api = None
        self.supervisor = None
        self.room = None
        self.rooms_cache = []
        self.rooms_version = 0
        self.room_art = {}
        self._rooms_key = None
        self._rooms_seeded = False
        self._seen_rooms = set()
        self._thread = None
        self._stop = threading.Event()
        self._join_lock = threading.Lock()
        self._auto_join_done = False
        self._local_change_at = 0.0
        self._last_remote_state_at = 0.0   # monotonic; peer State heartbeat
        self._peer_probe = None             # (position, monotonic) slow anchor
        self._tempo = 1.0
        self._tempo_retry_at = 0.0
        self._tempo_failures = 0
        self._tempo_unavailable = False
        self._remote_seek_at = 0.0
        self._catchup_until = 0.0
        self._toasted = {}                 # (identity_user_id, kind) -> monotonic
        self._peer_stale_last = None       # last logged peer_stale() value
        self._peer_slow_last = None        # last logged peer_slow() value
        self._was_connected = False
        self._player_ready = False
        self._detector_requestid = None
        self._detector_part_index = 0
        self._detector_deadline = None
        self._prepared = True
        self._started = False
        self._hosting = False   # host() owns its lobby; guests auto-open one
        self.lobby = None       # the open LobbyDialog, if any (Task 8)

    # -- startup ------------------------------------------------------------

    def start(self):
        """Idempotent: lobby thread + one auto-join attempt. Called from
        HomeWindow.onFirstInit and from show()."""
        if self._thread and self._thread.is_alive():
            return
        self._stop.clear()
        self._thread = threading.Thread(target=self._run, name="wt-bridge")
        self._thread.daemon = True
        self._thread.start()
        self.auto_join()

    def _run(self):
        ticks = 0
        while not self._stop.is_set() and not util.MONITOR.abortRequested():
            if self._stop.wait(1.0):
                break
            ticks += 1
            try:
                sup = self.supervisor
                if sup is None:
                    if not self._rooms_seeded or ticks % 15 == 0:
                        self._poll_rooms()
                else:
                    if sup.connected != self._was_connected:
                        self._was_connected = sup.connected
                        self.update_status()
                    self.push_local()
                    self._poll_detector()
                    self._update_ready(sup)
                    self._maybe_auto_start()
            except Exception:
                # never let one bad tick kill the lobby/heartbeat thread
                util.ERROR()

    def ensure_api(self):
        if self.api is None:
            self.api = watchtogether.RoomsApi(plexapp.ACCOUNT.authToken)
        return self.api

    # -- lobby (no supervisor running) ---------------------------------------

    def _poll_rooms(self):
        try:
            rooms = self.ensure_api().rooms()
        except Exception as exc:
            # WatchTogetherError is expected (offline/HTTP); anything else is a
            # payload bug — still swallow it so the lobby thread survives.
            # class name only: the room id is a credential (§7)
            util.DEBUG_LOG("Watch Together: room poll failed: {0}".format(exc.__class__.__name__))
            return
        self.rooms_cache = rooms
        key = tuple(sorted((r.id, len(r.participants)) for r in rooms))
        if key != self._rooms_key:
            self._rooms_key = key
            self.rooms_version += 1
        live = set()
        for room in rooms:
            live.add(room.id)
            if room.id not in self.room_art:
                self.room_art[room.id] = self._resolve_room_art(room)
        for room_id in list(self.room_art):
            if room_id not in live:
                del self.room_art[room_id]
        current = set(r.id for r in rooms)
        if not self._rooms_seeded:
            # first paint: remember, never toast what was already there
            self._rooms_seeded = True
            self._seen_rooms = current
            return
        for room in rooms:
            if room.id not in self._seen_rooms:
                util.showNotification(
                    util.T(35058, "New Watch Together room: {}").format(room.title))
        # prune gone ids so a room re-created later can toast again, and the
        # set cannot grow without bound
        self._seen_rooms = current

    def refresh_room(self):
        """Fresh GET /rooms/{id} while a dialog is open (participants, invite)."""
        sup = self.supervisor
        if sup is None:
            return
        thread = threading.Thread(target=self._refresh_room_work, args=(sup,),
                                  name="wt-room")
        thread.daemon = True
        thread.start()

    def _refresh_room_work(self, sup):
        """Fetch the room and hand it to on_roster, which repaints any open
        lobby. Assigning self.room alone left a refreshed roster off-screen
        until the next roster push."""
        try:
            room = self.ensure_api().room(sup.room.id)
        except Exception as exc:
            util.DEBUG_LOG("Watch Together: room refresh failed: {0}".format(
                exc.__class__.__name__))
            return
        # post-request ownership check: a room switch may have happened while
        # the REST was in flight
        if self.supervisor is sup:
            self.on_roster(room)

    def _is_current_room(self, room):
        """True when `room` is the room we are in.

        Compare ids, not identity: the 15 s roster poll replaces self.room with
        a fresh Room object, so a picker's snapshot is a different instance by
        the time its OK is pressed - and an identity check then dropped the
        invite result entirely."""
        current = self.room
        return bool(room is not None and current is not None
                    and room.id == current.id)

    # -- home hub ------------------------------------------------------------

    def _resolve_room_art(self, room):
        """16:9 art for a room, resolved from sourceUri against its source
        server. Never raises: any failure yields the placeholder."""
        machine, key = parse_source_uri(room.source_uri)
        if not machine or not key:
            return WATCHTOGETHER_PLACEHOLDER
        try:
            servers = getattr(plexapp.SERVERMANAGER, "serversByUuid", None) or {}
            server = servers.get(machine)
            if server is None:
                return WATCHTOGETHER_PLACEHOLDER
            items = plexobjects.listItems(server, "/library/metadata/%s" % key)
            if not items:
                return WATCHTOGETHER_PLACEHOLDER
            item = items[0]
            art = item.defaultThumb if getattr(item, "type", None) == "episode" \
                else item.defaultArt
            if not art:
                art = item.defaultThumb
            return art.asTranscodedImageURL(532, 299)
        except Exception:
            return WATCHTOGETHER_PLACEHOLDER

    def _build_room_items(self):
        return [WatchTogetherRoomItem(r, self.room_art.get(r.id))
                for r in self.rooms_cache]

    def home_hub(self):
        if not self.rooms_cache:
            return None
        return WatchTogetherRoomsHub(self._build_room_items)

    # -- local -> relay -------------------------------------------------------

    def _owns_playback(self):
        """True only when the video in the player is the room's own item.

        isPlayingVideo() is true for any video. With auto-join the bridge is
        connected before room playback, so an unrelated movie must not be
        paused/seeked by room States, nor have its position published."""
        room = self.room
        _, room_key = parse_source_uri(room.source_uri) if room is not None \
            else (None, None)
        return bool(room_key and room_key == playing_rating_key())

    def push_local(self):
        """Feed the supervisor's snapshot at 1 Hz (§5.5). The supervisor sends;
        this only updates what it will send."""
        sup = self.supervisor
        pl = _player()
        if sup is None or pl is None:
            return
        # isPlayingVideo, not isPlaying: theme music runs through this same
        # player. Before playback starts, echo the room's position (never 0,
        # which would make us the driver at the start); the supervisor also
        # holds States until synced.
        if not pl.isPlayingVideo() or not self._owns_playback():
            session = sup.session
            pos = int((session.remote.get("position", 0) if session else 0) or 0)
            sup.outbound_state({"position": pos, "paused": True, "doSeek": False})
            return
        sup.outbound_state({
            "position": int(pl.getTime() or 0),
            "paused": bool(xbmc.getCondVisibility("Player.Paused")),
            "doSeek": False,
        })

    def _update_ready(self, sup):
        """§6.4: ready when the room's own video is loaded and not buffering.

        The host waiting in the Home lobby has no video yet, so while hosting
        and not started its readiness is the pre-scan state (`_prepared`); the
        1 s tick must not overwrite it with a playback check."""
        if self._hosting and not self._started:
            self._player_ready = self._prepared
            sup.set_ready(self._prepared)
            return
        pl = _player()
        ready = bool(pl is not None and pl.isPlayingVideo()
                     and self._owns_playback()
                     and not xbmc.getCondVisibility("Player.Caching"))
        self._player_ready = ready
        sup.set_ready(ready)

    # -- host pre-scan (p3i admission) ----------------------------------------

    def _detector_scan_path(self, item):
        """Part-0 Direct Play URI for `item`, or None (best effort). Same
        expression as plexplayer.BasePlayer.setupObj: the mapped path when
        there is one, else the server's key URL with the auth token."""
        try:
            choice = item.mediaChoice
            if choice is None:
                choice = mediachoice.MediaChoice(item.media()[0], partIndex=0)
            part = choice.part
            if part is None:
                return None
            server = item.getServer()
            url = part.getPathMappedUrl()
            if not url:
                url = server.buildUrl(part.getAbsolutePath("key"),
                                      includeToken=True)
            return url or None
        except Exception:
            return None

    def _start_scan(self, item, gate):
        """Start a p3i pre-scan for `item`. With `gate`, hold readiness until
        the job completes (or fails open). Returns the requestid, or None."""
        if self._detector_requestid is not None:
            return None
        path = self._detector_scan_path(item)
        if path is None:
            return None
        requestid = p3i_detector.start(path)
        if requestid is None:
            return None
        self._detector_requestid = requestid
        self._detector_part_index = 0
        self._detector_deadline = time.monotonic() + DETECTOR_TIMEOUT
        if gate:
            self._prepared = False
        return requestid

    def _poll_detector(self):
        """Tick the pre-scan state machine from the bridge thread (1 Hz).

        A scan completing after playback has already started is deliberately
        abandoned: applying P3I.Detector.GetPlayback/Apply at that point is out
        of scope, and the host can always press Start."""
        requestid = self._detector_requestid
        if requestid is None:
            return
        status = (p3i_detector.status(requestid) or {}).get('status')
        if self._detector_requestid != requestid:
            return                              # leave()/on_gone reset it mid-poll
        if status == 'completed':
            self._prepared = True
            self._detector_requestid = None
            pl = _player()
            if pl is not None:
                pl.wt_detector_requestid = requestid
                pl.wt_detector_part_index = self._detector_part_index
        elif status in ('queued', 'running', 'cancelling'):
            if time.monotonic() >= self._detector_deadline:
                self._prepared = True           # timeout: fail open
                p3i_detector.cancel(requestid)  # abandon the scan, not just the state
                self._detector_requestid = None
        else:
            self._prepared = True               # terminal non-completed / error: fail open
            self._detector_requestid = None

    def _cancel_detector(self):
        p3i_detector.cancel(self._detector_requestid)
        self._detector_requestid = None
        self._prepared = True
        self._detector_deadline = None

    def _maybe_auto_start(self):
        """Start the room once every user in room.users except self is on the
        roster and ready, and self is ready (§6.4). Only the host drives the
        room — a ready guest must never call start_playback(). A member who
        never joins blocks it — the host presses Start instead."""
        if not self._hosting or self._started or not self._player_ready:
            return
        sup = self.supervisor
        room = self.room
        if sup is None or sup.session is None or room is None:
            return
        self_id = str(getattr(plexapp.ACCOUNT, "ID", None))
        others = [uid for uid in room.user_ids if str(uid) != self_id]
        if others and syncplay.members_ready(others, sup.session.roster):
            self.start_playback()

    def start_playback(self):
        """Start the room: unpause self (§6.4). The local-change path then
        broadcasts paused:false, so guests unpause via _apply_remote. Closes
        the lobby (manual Start and auto-start both land here)."""
        if self._started:
            return          # idempotent: auto-start can race on two threads
        self._started = True
        pl = _player()
        if pl is not None:
            pl.control("play")
        sup = self.supervisor
        if sup is not None:
            sup.send_now()
        self._close_lobby()

    # -- host flow -----------------------------------------------------------

    def host(self, item):
        """Start hosting `item`: create the room, join it, show the lobby, and
        open the item only if the room starts. Main thread.

        The lobby runs over Home, not over the video: a modal dialog must own
        Kodi's main thread to take input focus, and a dialog opened over the
        video leaves focus on the video window."""
        rating_key = getattr(item, "ratingKey", None)
        if not rating_key:
            util.DEBUG_LOG("Watch Together: cannot host an item with no ratingKey")
            return
        machine_id = getattr(item.server, "uuid", None)
        if not machine_id:
            # no machine -> sourceUri would be unresolvable: creating a room
            # nobody can play is worse than not creating one
            util.DEBUG_LOG("Watch Together: cannot host an item with no server uuid")
            util.showNotification(util.T(35084, "This item cannot be hosted"))
            return
        source_uri = ("server://{0}/com.plexapp.plugins.library/library/metadata/{1}"
                      .format(machine_id, rating_key))
        self._ensure_people_identity()
        room = self._create_and_join(source_uri, item.title)
        if room is None:
            return
        self._hosting = True
        self._started = False
        # the host waits in the lobby rather than buffering the video; a p3i
        # pre-scan holds readiness until it completes (or fails open)
        self._start_scan(item, gate=True)
        self._player_ready = self._prepared
        self._open_lobby(host=True)          # blocks until Start/Cancel/ESC
        if self._started and self.supervisor is not None:
            self._play_item(item)            # the room started: open the video
            if self.supervisor is not None:
                self.disconnect()

    @busy.dialog()
    def _create_and_join(self, source_uri, title):
        """Create the room and join it behind a busy spinner (each REST call
        can block 15 s). Returns the room, or None on failure (already
        toasted)."""
        try:
            room = self.ensure_api().create(source_uri, title)
        except watchtogether.WatchTogetherError as exc:
            self._host_failed(exc)
            return None
        try:
            if self.supervisor is not None:
                # switch rooms: join() early-returns an existing supervisor,
                # which would orphan the room we just created and leave
                # self.room stale
                self.leave()
            self.join(room.id, hosting=True)
        except watchtogether.WatchTogetherError as exc:
            # created but never joined: DELETE the orphan before reporting
            self._host_failed(exc)
            try:
                self.ensure_api().leave(room.id)
            except watchtogether.WatchTogetherError:
                pass
            return None
        return room

    def _host_failed(self, exc):
        """Report a host create/join failure. Class name only in the log: the
        message may carry a service URL (§7). A dead token gets the sign-in
        hint the spec asks for (§4/Error handling)."""
        util.DEBUG_LOG("Watch Together: host failed: {0}".format(
            exc.__class__.__name__))
        if isinstance(exc, watchtogether.AuthError):
            util.showNotification(
                util.T(35083, "Sign in again to use Watch Together"))
        else:
            util.showNotification(str(exc))

    def _ensure_people_identity(self):
        """plexpeople is Kodi-free, so inject our client identifier/version
        before any plex.tv community call (the invite picker, §Eligibility)."""
        plexpeople.CLIENT_ID = plex.CLIENT_ID
        plexpeople.VERSION = util.ADDON.getAddonInfo("version")

    def _open_lobby(self, host=True):
        """Show the lobby modally, over Home, and block until it closes.

        Main thread only: a modal dialog needs Kodi's main-thread init, and a
        dialog shown over the video leaves input focus on the video window. The
        host's video opens after the lobby (see host()); a guest's when the
        room starts (see room_clicked)."""
        sup = self.supervisor
        roster = sup.session.roster \
            if sup is not None and sup.session is not None else {}
        lobby = LobbyDialog.create(show=False, room=self.room, roster=roster,
                                   host=host)
        # set the mode/title before the window is shown: Kodi evaluates the
        # controls' <visible> as it loads, so a property set in onFirstInit is
        # too late for its setFocusId on the host-only Start button
        lobby.setBoolProperty('is_host', host)
        lobby.setProperty('watching', self.room.title if self.room else '')
        self.lobby = lobby
        lobby.modal()               # blocks (main thread) until the lobby closes
        if self.lobby is lobby:
            self.lobby = None

    def _close_lobby(self):
        lobby, self.lobby = self.lobby, None
        close = getattr(lobby, "doClose", None)
        if close is not None:
            close()

    def _room_unstarted(self):
        """The joined room has not started: relay State paused with position
        < 1 s. No State yet counts as started (do not block the join)."""
        session = getattr(self.supervisor, "session", None)
        remote = getattr(session, "remote", None)
        return bool(remote is not None and remote.get("paused") is True
                    and (remote.get("position") or 0) < 1)

    def _update_guest_lobby(self, remote):
        """Guest lobby visibility: a guest's lobby is opened by room_clicked
        (over Home) and closed here the moment playback starts. The host owns
        its lobby via host(), so this is a no-op while hosting."""
        if self._hosting:
            return
        unstarted = (remote.get("paused") is True
                     and (remote.get("position") or 0) < 1)
        if not unstarted and self.lobby is not None:
            self._close_lobby()

    def _play_item(self, item):
        from . import videoplayer
        videoplayer.play(video=item)

    def invite(self, user_ids, room=None):
        """Invite each id into `room` (default: the current room); return the
        ids that failed.

        One request per id: the server's relationship gate (§11.9) rejects the
        whole request when any target is refused, so batching would lose the
        ones that could have been invited. A dead token is not a per-target
        failure, so AuthError propagates for the caller to report.

        Each response is the updated room; the last one is applied through
        on_roster so an open lobby shows the new members at once, then confirmed
        with a GET refresh (which also repaints)."""
        if room is None:
            room = self.room
        if room is None:
            return list(user_ids)
        failed = []
        invited = False
        latest = None
        for user_id in user_ids:
            try:
                latest = self.ensure_api().invite(room.id, [user_id])
                invited = True
            except watchtogether.AuthError:
                raise
            except watchtogether.WatchTogetherError:
                failed.append(user_id)
        if invited and self._is_current_room(room):
            if latest is not None:
                # the response already carries the updated room: show it now
                self.on_roster(latest)
            # confirm with a GET, and repaint again: the poll may have replaced
            # the room object under us, and the server's view is authoritative
            self.refresh_room()
        return failed

    def invitees(self, room=None):
        """Eligible invitees for `room` (default: the current room)
        (plexpeople.eligible_invitees).

        Home users plus friends; on a shared server every row is flagged
        access_unknown. Degrades to home users only when the friends lookup
        returns nothing (Review Focus 1) and never raises: the picker must
        open whatever plex.tv answers."""
        if room is None:
            room = self.room
        account = plexapp.ACCOUNT
        if room is None or account is None:
            return []
        machine_id, _ = parse_source_uri(room.source_uri)
        owned = self._server_owned(machine_id)
        self._ensure_people_identity()
        home = []
        try:
            home = self._home_user_dicts(account)
            return plexpeople.eligible_invitees(
                account.authToken, machine_id, owned, home,
                self_id=account.ID, room_user_ids=room.user_ids)
        except Exception:
            # any unexpected failure still offers home users (Review Focus 1)
            util.ERROR()
            return [plexpeople.Invitee(h["id"], h["title"], h["thumb"], not owned)
                    for h in home]

    def _home_user_dicts(self, account):
        """plexapp homeUsers -> the {"id", "title", "thumb"} dicts plexpeople
        takes (its ids must be ints to dedupe against room/self ids)."""
        out = []
        for user in getattr(account, "homeUsers", None) or []:
            try:
                user_id = int(user.get("id"))
            except (TypeError, ValueError):
                continue
            out.append({"id": user_id,
                        "title": user.get("title") or user.get("username") or "",
                        "thumb": user.get("thumb") or ""})
        return out

    def _server_owned(self, machine_id):
        try:
            servers = getattr(plexapp.SERVERMANAGER, "serversByUuid", None) or {}
            return bool(getattr(servers.get(machine_id), "owned", False))
        except Exception:
            return False

    def cancel_hosting(self):
        """Cancel hosting: leave the room (DELETE) and close the lobby."""
        self.leave()
        self._close_lobby()

    def on_local_change(self, kind):
        """Kodi fired onPlayBack* for a local event (the gate let it through)."""
        util.DEBUG_LOG("Watch Together: local {0}, broadcasting state".format(kind))
        sup = self.supervisor
        if kind == "seek" and sup is not None:
            # §5.6: a local seek is a command, not just a position report
            sup.request_seek()
        if kind == "play" and sup is not None:
            # the user pressed play: that is a manual readiness (§6.4)
            self._player_ready = True
            sup.set_ready(True, manually=True)
        # a local change must win: send it now and hold off incoming states
        # briefly, or a peer's older State reverts it (last-setBy-wins, but
        # only after ours lands)
        self._local_change_at = time.monotonic()
        self.push_local()
        if sup is not None:
            sup.send_now()

    # -- relay -> kodi ---------------------------------------------------------

    def _sup_guard(self, sup, fn, *args):
        """Run fn(*args) only if sup is still the current supervisor.

        A callback from a stopped supervisor must not touch the bridge after
        another room has been joined (stop() waits ≤5 s; a room REST can take
        15 s, so an old supervisor can deliver after a switch)."""
        if self.supervisor is sup:
            fn(*args)

    def _toast(self, key, kind, text):
        """One toast per (identity, kind) per 4 s: a flapping peer must not
        turn the screen into a notification wall (2026-10-23 live session)."""
        now = time.monotonic()
        if now - self._toasted.get((key, kind), 0.0) < 4.0:
            return
        self._toasted[(key, kind)] = now
        # prune entries older than 60 s so the dict cannot grow unbounded
        cutoff = now - 60.0
        for k in [k for k, t in self._toasted.items() if t < cutoff]:
            del self._toasted[k]
        util.DEBUG_LOG("Watch Together: toast {0} {1}: {2}".format(kind, key, text))
        util.showNotification(text, header=util.T(35053, "Watch Together"),
                              time_ms=3000)

    def on_state(self, remote):
        """syncplay.Session applied a remote State (supervisor thread).

        Must not raise: an exception here tears the connection down."""
        try:
            self._apply_remote(remote)
        except Exception:
            util.ERROR()

    def _apply_remote(self, remote):
        sup = self.supervisor
        if sup is None:
            return
        session = sup.session
        if session is None or not sup.connected:
            return
        self._last_remote_state_at = time.monotonic()
        self._update_guest_lobby(remote)
        if time.monotonic() - self._local_change_at < LOCAL_CHANGE_GRACE:
            return          # our own change is in flight; don't be reverted
        pl = _player()
        # §6.3 foreground/background: v1 approximates "foreground" with "video
        # playing" (no ad-break sync — an explicit v1 non-goal). The lobby and
        # theme-music cases stay background and ignore the relay's playstate.
        if pl is None or not pl.isPlayingVideo() or not self._owns_playback():
            self._catchup_until = 0.0   # playback ended/left: drop any pending freeze
            return
        if self._catchup_until:
            if time.monotonic() < self._catchup_until:
                return          # still frozen in a local catch-up pause
            self._catchup_until = 0.0
            pl.wtApplyingRemote("play")
            pl.control("play")
        local_pos = pl.getTime() or 0.0
        # publish our own position only once it actually matches the room: a
        # just-started video at ~0 (or a seek that hasn't landed yet) would
        # otherwise become the room position and drag everyone to the start
        if abs(local_pos - remote.get("position", 0.0)) < 2.0:
            sup.mark_synced()
        # any tempo failure widens the tolerance: a player that refuses SetTempo
        # must not get a seek for a 4-10s drift while the second probe waits
        seek_ahead = (WT_WIDE_SEEK_DELTA
                      if self._tempo_unavailable or self._tempo_failures
                      else syncplay.SEEK_AHEAD)
        action = syncplay.sync_action(local_pos, remote.get("position", 0.0),
                                      remote.get("paused", True),
                                      session.latency.forward_delay,
                                      seek_ahead=seek_ahead)
        want_paused = remote.get("paused")
        is_paused = bool(xbmc.getCondVisibility("Player.Paused"))
        # the seek target sync_action also computes, hoisted so the catch-up
        # branch can report the drift it leaves alone (sync_action stays pure
        # and recomputes its own)
        target = remote.get("position", 0.0) + \
            (0 if want_paused else session.latency.forward_delay)
        if action and action[0] == "tempo" and self._tempo_unavailable:
            # no tempo on this player: the band is "leave it", unless the opt-in
            # pause catch-up is on (2026-10-23 CoreELEC report)
            self._pause_catchup(pl, target)
            action = None
        applied = False
        applied_label = None
        published = remote.get("position", local_pos)
        # evaluated once: a blocked seek must skip only the seek, never the
        # trailing publish of anything else applied this tick (e.g. a pause)
        seek_ok = self._seek_allowed()
        util.DEBUG_LOG(
            "Watch Together: drift local={0:.2f} remote={1:.2f} action={2} "
            "paused={3} seeking={4} caching={5}".format(
                local_pos, remote.get("position", 0.0), action, want_paused,
                xbmc.getCondVisibility("Player.Seeking"),
                xbmc.getCondVisibility("Player.Caching")))
        # arm the echo deadline only when we actually change something: remote
        # States arrive ~1 Hz, so arming on every frame would keep the gate
        # closed and swallow every genuine local event (design §Echo)
        if want_paused is not None and want_paused != is_paused:
            pl.wtApplyingRemote("pause" if want_paused else "play")
            pl.control("pause" if want_paused else "play")
            self._set_tempo(1.0)
            applied = True
            applied_label = "pause" if want_paused else "play"
            name = self.display_name(remote.get("setBy"))
            if name:
                self._toast(identity_user_id(remote.get("setBy")),
                            "paused" if want_paused else "resumed",
                            (util.T(35093, "{} paused") if want_paused
                             else util.T(35094, "{} resumed")).format(name))
        if remote.get("doSeek") and seek_ok:
            # §5.6: a peer's explicit seek command — apply even inside the
            # drift band, where sync_action would stay put
            pl.wtApplyingRemote("seek")
            self._seek_to(remote.get("position", 0.0))
            self._set_tempo(1.0)
            applied = True
            applied_label = "seek (explicit)"
            name = self.display_name(remote.get("setBy"))
            if name:
                self._toast(identity_user_id(remote.get("setBy")), "jumped",
                            util.T(35095, "{} jumped to {}").format(
                                name, util.simplifiedTimeDisplay(
                                    int(remote.get("position", 0.0) * 1000))))
        elif action and action[0] == "seek" and seek_ok:
            gap = local_pos - action[1]
            if gap > 0:
                # the peer is behind us, so it is the side that must catch up: its
                # own client sees the room ahead and seeks forward. Dragging the
                # host back to a stalled peer is the jolt users report, and
                # peer_slow() flickers while a stuck peer wobbles by a second
                # (2026-10-23 live sessions), so this never moves us backwards.
                util.DEBUG_LOG(
                    "Watch Together: peer is behind, not seeking back "
                    "{0:.1f}s".format(gap))
            else:
                pl.wtApplyingRemote("seek")
                self._seek_to(action[1])
                self._set_tempo(1.0)
                applied = True
                applied_label = "seek"
                published = action[1]
                name = self.display_name(remote.get("setBy"))
                if name:
                    self._toast(identity_user_id(remote.get("setBy")), "jumped",
                                util.T(35095, "{} jumped to {}").format(
                                    name, util.simplifiedTimeDisplay(
                                        int(action[1] * 1000))))
        elif action and action[0] == "tempo":
            # §6.2 gentle catch-up: slow to 0.95 with pitch preserved (Kodi 21+)
            result = self._set_tempo(action[1])
            if result is False:
                # tempo unavailable here: a hard seek lands on the previous
                # keyframe and re-creates the drift (2026-10-23 CoreELEC).
                # Leave the drift alone — the widened threshold already limits
                # correction to genuinely large drift.
                util.DEBUG_LOG("Watch Together: tempo unavailable; drift {0:.2f}s "
                               "left alone".format(local_pos - target))
            # result True: tempo applied; None: busy/backing off, retry next tick
        else:
            self._set_tempo(1.0)   # inside the drift band: clear any catch-up
        if applied:
            # Feed the state we just applied. The supervisor only *stores* this
            # snapshot and its 1 Hz loop is the single sender, so its next beat
            # would otherwise publish the pre-apply one - last-setBy wins, the
            # room flips back and the peer undoes us: a stale paused made the
            # browser resume (seen live as pause/resume/pause), and a stale
            # position would make it seek back. Player.Paused and getTime() both
            # lag their commands by a few ms, so read neither here.
            sup.outbound_state({
                "position": published,
                "paused": want_paused if want_paused is not None else is_paused,
                "doSeek": False,
            })
            # log what was applied, not the drift decision: a pause tick also
            # carries action=('seek', ...) when the peer is behind, and printing
            # that made a skipped seek look like an applied one (2026-10-23)
            util.DEBUG_LOG("Watch Together: applied {0} (paused={1}, pos={2})".format(
                applied_label, want_paused, published))

    def _set_tempo(self, tempo):
        """§6.2 pitch-preserved tempo catch-up, via JSON-RPC Player.SetTempo
        (Kodi 21+). Returns True when applied, False when tempo is unavailable
        on this player (the caller leaves the drift alone), or None when not
        now: the player is busy seeking/caching or we are backing off (retry
        next tick)."""
        if tempo == self._tempo:
            return True
        # SetTempo is refused while the player is mid-seek or buffering (seen
        # on Kodi 21.0); don't call it then, and don't hard-seek either.
        if (xbmc.getCondVisibility("Player.Seeking")
                or xbmc.getCondVisibility("Player.Caching")):
            return None
        now = time.monotonic()
        if now < self._tempo_retry_at:
            return None
        if util.KODI_VERSION_MAJOR < 21:
            self._tempo_unavailable = True
            self._tempo_retry_at = now + 3600.0
            util.LOG("Watch Together: tempo catch-up needs Kodi 21+ (have {0}); "
                     "widening the drift tolerance".format(util.KODI_VERSION_MAJOR))
            return False
        try:
            players = util.rpc.Player.GetActivePlayers() or []
            playerid = next((p["playerid"] for p in players
                             if p.get("type") == "video"), None)
            if playerid is None:
                return None
            util.rpc.Player.SetTempo(playerid=playerid, tempo=tempo)
            self._tempo = tempo
            self._tempo_failures = 0
            util.DEBUG_LOG("Watch Together: tempo {0}".format(tempo))
            return True
        except Exception:
            # SetTempo is advertised on Kodi 21 but the player may still refuse
            # it. Count the failures; after a few, give up for the session and
            # widen the drift tolerance instead of probing every minute.
            self._tempo_failures += 1
            self._tempo = 1.0
            if self._tempo_failures >= WT_TEMPO_FAIL_LIMIT:
                self._tempo_unavailable = True
                self._tempo_retry_at = now + 3600.0
                util.LOG("Watch Together: tempo unavailable on this player; "
                         "widening the drift tolerance")
            else:
                self._tempo_retry_at = now + 60.0
            return False

    def _pause_catchup(self, pl, target):
        """Tempo-less player: lose the drift by freezing locally instead of
        seeking, which lands a GOP early on this decoder (2026-10-23 report).
        Never broadcast: the freeze is ours, the room must not pause."""
        if not util.getSetting("watchtogether.pause_catchup", False):
            return
        ahead = (pl.getTime() or 0.0) - target
        if not (syncplay.TEMPO_DIFF < ahead <= WT_PAUSE_CATCHUP_MAX):
            return
        pl.wtApplyingRemote("pause")
        pl.control("pause")
        self._catchup_until = time.monotonic() + ahead
        util.DEBUG_LOG("Watch Together: catch-up pause {0:.2f}s".format(ahead))

    def _seek_allowed(self):
        """A remote State must not seek a player that is already refilling, and
        must not stack seeks: during a refill the clock is frozen, so every 1 Hz
        beat would read drift and add another seek (2026-10-23 CoreELEC report)."""
        if (xbmc.getCondVisibility("Player.Seeking")
                or xbmc.getCondVisibility("Player.Caching")):
            return False
        return time.monotonic() - self._remote_seek_at >= WT_SEEK_COOLDOWN

    def _seek_to(self, target):
        """Through the seek dialog when it exists (it owns the full local seek
        path — transcodes, bookkeeping); plain seekTime otherwise. During video
        playback the dialog is created up front, so the fallback is the edge."""
        target = max(target, 0)
        pl = _player()
        if pl is None:
            return
        dialog = getattr(getattr(pl, "handler", None), "dialog", None)
        if dialog:
            dialog.doSeek(int(target * 1000))
        else:
            pl.seekTime(target)
        self._remote_seek_at = time.monotonic()

    # -- supervisor callbacks ---------------------------------------------------

    def on_roster(self, room):
        self.room = room
        self.update_status()
        # membership changed (e.g. an invitee joined): repaint the open lobby
        # so their Invited/Ready status shows without waiting for a ready change
        refresh = getattr(self.lobby, "refresh", None)
        if refresh is not None:
            refresh()

    def on_disconnected(self):
        util.DEBUG_LOG("Watch Together: relay connection lost, reconnecting")
        self.update_status()

    def on_event(self, kind, key):
        try:
            util.DEBUG_LOG("Watch Together: roster {0} {1}".format(
                kind, identity_user_id(key)))
            if kind not in ("joined", "left"):
                return
            name = self.display_name(key)
            if not name:
                return
            text = (util.T(35096, "{} joined the room") if kind == "joined"
                    else util.T(35097, "{} left the room")).format(name)
            self._toast(identity_user_id(key), kind, text)
        except Exception:
            util.ERROR()

    def _on_ready(self, key, is_ready):
        """A peer's readiness changed (§6.4). Refresh the open lobby and start
        the room once everyone is ready. Supervisor thread — never raise."""
        try:
            util.DEBUG_LOG("Watch Together: ready {0}={1}".format(
                identity_user_id(key), is_ready))
            refresh = getattr(self.lobby, "refresh", None)
            if refresh is not None:
                refresh()
            self._maybe_auto_start()
        except Exception:
            util.ERROR()

    def on_gone(self, sup=None):
        """Room ended / removed / dead token — supervisor thread. Teardown,
        no DELETE (§4). Dialogs notice supervisor=None and close themselves.

        `sup` is the supervisor that fired; when it is not the current one the
        callback is stale (we already left/rejoined) and must be ignored."""
        with self._join_lock:
            current = self.supervisor
            if current is None:
                # already left/detached: a NotMember poll after our own DELETE
                # is our departure, not a room that ended — do not announce it
                return
            if sup is not None and current is not sup:
                return
            self.supervisor = None
            self.room = None
            self._reset_player_link(forget_room=True)
            self._cancel_detector()
        util.showNotification(util.T(35059, "The Watch Together room has ended"))
        if current:
            current.stop()

    # -- join / leave -----------------------------------------------------------

    def join(self, room_id, hosting=False):
        with self._join_lock:
            if self.supervisor is not None:
                return self.supervisor
        # fetch + build outside the lock: the REST call can block 15s and must
        # not stall a concurrent leave()/on_gone()
        room = self.ensure_api().room(room_id)     # raises Auth/NotMember/Gone
        identity = syncplay.build_identity(plex.CLIENT_ID, plex.getFriendlyName(),
                                           plexapp.ACCOUNT.ID)
        sup = watchtogether.SessionSupervisor(room, identity,
                                              plexapp.ACCOUNT.authToken,
                                              _ws_factory, log=util.DEBUG_LOG)
        # bind each callback to its own supervisor: stop() waits ≤5 s but a
        # room REST can take 15 s, so an old supervisor must not deliver into
        # the bridge after another room has been joined
        sup.on_state = lambda remote, s=sup: self._sup_guard(s, self.on_state, remote)
        sup.on_roster = lambda room, s=sup: self._sup_guard(s, self.on_roster, room)
        sup.on_disconnected = lambda s=sup: self._sup_guard(s, self.on_disconnected)
        sup.on_gone = lambda s=sup: self.on_gone(s)
        sup.on_event = lambda kind, key, s=sup: self._sup_guard(s, self.on_event, kind, key)
        sup.on_ready = lambda key, ready, s=sup: self._sup_guard(s, self._on_ready, key, ready)
        with self._join_lock:
            if self.supervisor is not None:   # someone joined while we fetched
                return self.supervisor
            # set before start(): the supervisor connects immediately and a
            # relay State must not run the guest-lobby path for the host
            self._hosting = hosting
            sup.start()
            self.room = room
            self.supervisor = sup
            self._was_connected = False
            self._started = False
            self._last_remote_state_at = 0.0
            self._peer_probe = None
            pl = _player()
            if pl is not None:
                pl.wt_broadcast = self.on_local_change
                pl.wt_applying_remote = 0.0
            util.setSetting("watchtogether.last_room", room_id)
            self.update_status()
        return sup

    def _room_media_item(self, room):
        """Resolve the room's sourceUri to a playable, or None (best effort)."""
        machine, rating_key = parse_source_uri(room.source_uri)
        if not machine or not rating_key:
            return None
        try:
            servers = getattr(plexapp.SERVERMANAGER, "serversByUuid", None) or {}
            server = servers.get(machine)
            if server is None:
                util.DEBUG_LOG("Watch Together: source server not available")
                return None
            items = plexobjects.listItems(server,
                                          "/library/metadata/%s" % rating_key)
            if not items:
                util.DEBUG_LOG("Watch Together: room item not found")
                return None
            return items[0]
        except Exception:
            util.ERROR()
            return None

    def _watch_room(self, room):
        """Open the room's content in the normal video player window, so space,
        the OSD and stop all behave as usual. Playback stops -> we end the
        session (socket closed, peers told), but keep membership so the tile
        can rejoin. Returns the player window's exit command (the caller
        processes it, like preplay does); must run on the main thread."""
        pl = _player()
        if pl is None or pl.isPlayingVideo():
            return None
        item = self._room_media_item(room)
        if item is None:
            return None
        from . import videoplayer
        command = None
        try:
            command = videoplayer.play(video=item)
        except Exception:
            util.ERROR()
        finally:
            if self.supervisor is not None:
                self.disconnect()
        return command

    def disconnect(self):
        """End the session without DELETE: closing the socket tells peers we
        left (§5.8) but the room keeps us, so the tile can rejoin. Contrast
        leave(), which is the explicit 'leave the room' (DELETE)."""
        with self._join_lock:
            sup, self.supervisor = self.supervisor, None
            self.room = None
            self._reset_player_link(forget_room=False)
        self._cancel_detector()     # Cancel is JSON-RPC: keep it off the join lock
        if sup:
            sup.stop()

    def leave(self):
        # Detach + reset under the lock, then do the blocking REST call and
        # thread join outside it: holding _join_lock across api.leave() (up to
        # 15s) and sup.stop() (joins the supervisor) would stall a concurrent
        # on_gone()/join() — and on_gone() runs on the supervisor thread that
        # stop() is waiting to join.
        with self._join_lock:
            sup, room = self.supervisor, self.room
            self.supervisor = None
            self.room = None
            self._cancel_detector()
            self._reset_player_link(forget_room=True)
        if room is not None and self.api is not None:
            try:
                self.api.leave(room.id)
            except watchtogether.WatchTogetherError as exc:
                util.DEBUG_LOG("Watch Together: leave failed: {0}".format(
                    exc.__class__.__name__))
        if sup:
            sup.stop()

    def remove_room(self, room):
        """Remove me from this room (DELETE). If I was the last member the room
        ends up empty on the server and stops being listed for anyone."""
        room_id = room.id
        if self.supervisor is not None and self.room is not None and self.room.id == room_id:
            self.leave()
            return
        try:
            self.ensure_api().leave(room_id)
        except watchtogether.WatchTogetherError as exc:
            util.DEBUG_LOG("Watch Together: remove failed: {0}".format(
                exc.__class__.__name__))
        self._drop_room(room_id)

    def _drop_room(self, room_id):
        before = len(self.rooms_cache)
        self.rooms_cache = [r for r in self.rooms_cache if r.id != room_id]
        self.room_art.pop(room_id, None)
        if len(self.rooms_cache) != before:
            self.rooms_version += 1

    def _live_user_ids(self):
        """userIDs currently on the relay roster (only known for the room we
        are connected to)."""
        sup = self.supervisor
        if sup is None or sup.session is None:
            return set()
        ids = set()
        for key in list(sup.session.roster):
            user_id = identity_user_id(key)
            if user_id is not None:
                ids.add(user_id)
        return ids

    def display_name(self, key):
        """A human name for a roster identity: the matching room participant's
        title (fallback username), else the identity's deviceName, else ""."""
        name = ""
        user_id = identity_user_id(key)
        if user_id is not None:
            for user in (self.room.participants if self.room else []):
                if not isinstance(user, dict):
                    continue
                if str(user.get("id")) == user_id:
                    name = user.get("title") or user.get("username") or ""
                    break
        return name or identity_device_name(key) or ""

    def peer_stale(self):
        """True when no peer State has arrived for >5 s (the peer stalled)."""
        stale = self._last_remote_state_at and \
            time.monotonic() - self._last_remote_state_at > 5.0
        if bool(stale) != self._peer_stale_last:
            self._peer_stale_last = bool(stale)
            util.DEBUG_LOG("Watch Together: peer stale={0}".format(bool(stale)))
        return stale

    def peer_slow(self):
        """True when, over at least 8 s, the room position advanced less than
        0.9x the elapsed time — a buffering peer. Only meaningful for a
        2-participant room (self + one peer); else False.

        A backward jump or an explicit seek re-anchors the probe, so a peer's
        rewind is not read as ~10x its distance of buffering."""
        slow = self._peer_slow_now()
        if slow != self._peer_slow_last:
            self._peer_slow_last = slow
            util.DEBUG_LOG("Watch Together: peer slow={0}".format(slow))
        return slow

    def _peer_slow_now(self):
        room = self.room
        if room is None or len(room.participants) != 2:
            self._peer_probe = None    # a 3rd member joined/left: drop the anchor
            return False
        sup = self.supervisor
        session = sup.session if sup is not None else None
        if session is None or session.remote is None \
                or session.remote.get("paused", True):
            self._peer_probe = None     # paused is not slow; re-anchor on resume
            return False
        now = time.monotonic()
        pos = session.remote.get("position", 0.0)
        probe = self._peer_probe
        if probe is None:
            self._peer_probe = (pos, now)
            return False
        anchor_pos, anchor_at = probe
        if pos < anchor_pos or session.remote.get("doSeek"):
            # a peer jumped backwards or seeked: re-anchor at the new position
            # instead of letting the drop read as buffering
            self._peer_probe = (pos, now)
            return False
        elapsed = now - anchor_at
        if elapsed < 8.0:
            return False
        if pos - anchor_pos >= 0.9 * elapsed:
            self._peer_probe = (pos, now)   # healthy: re-anchor the window
            return False
        return True

    def _participant_state(self, user_id):
        """(stale, slow) for a participant row. The stale/slow heuristics are
        peer-only: our own row must never show buffering from a stalled peer,
        so it returns (False, False) for our account id. Readiness still comes
        from the roster for every row."""
        if str(getattr(plexapp.ACCOUNT, "ID", None)) == str(user_id):
            return (False, False)
        return (self.peer_stale(), self.peer_slow())

    def room_clicked(self, room):
        """Hub tile click: join and watch, switch, or (already watching) open
        participants. Playback stops -> leave, so a later click rejoins.
        Returns the video window's exit command, if any, for the caller."""
        sup = self.supervisor
        if sup is not None and self.room is not None and self.room.id == room.id:
            if _player() is not None and _player().isPlayingVideo():
                ParticipantsDialog.open()
                return None
            return self._watch_room(room)   # in the room but not watching
        leave_first = sup is not None
        if leave_first:
            if not confirm_switch():
                return None
        elif not confirm_takeover(room):
            return None
        try:
            self._join_or_switch(room.id, leave_first)
        except Exception as exc:
            util.DEBUG_LOG("Watch Together: join failed: {0}".format(
                exc.__class__.__name__))
            util.showNotification(str(exc))
            return None
        # a room that has not started shows the lobby (over Home) first; the
        # lobby closes on the first playing State, then the video opens. A
        # guest pre-scans the room item best-effort (never gating readiness)
        # so the direct-play path is ready if the job completes before the
        # room starts; the tick/disconnect abandons it otherwise.
        if self._room_unstarted():
            item = self._room_media_item(room)
            self._start_scan(item, gate=False)
            self._open_lobby(host=False)
        return self._watch_room(room)

    @busy.dialog()
    def _join_or_switch(self, room_id, leave_first):
        """Join/switch behind a busy spinner; the confirms stay in
        room_clicked so the busy window never covers them."""
        if leave_first:
            self.leave()
        self.join(room_id)

    def _reset_player_link(self, forget_room=False):
        # restore normal speed before detaching: a remote catch-up may have
        # left the player at 0.95, and leaving via the OSD keeps the video
        # running, so it would stay slowed after sync has ended
        if self._tempo != 1.0:
            self._set_tempo(1.0)
        self._tempo = 1.0
        self._last_remote_state_at = 0.0
        self._peer_probe = None
        player.PLAYER.wt_broadcast = None
        player.PLAYER.wt_applying_remote = 0.0
        player.PLAYER.wt_detector_requestid = None
        player.PLAYER.wt_detector_part_index = 0
        self._started = False
        self._hosting = False
        self._close_lobby()     # session ended: no lobby may outlive it
        if forget_room:
            util.setSetting("watchtogether.last_room", "")
        self.update_status()

    def auto_join(self):
        if self._auto_join_done:
            return
        self._auto_join_done = True
        if not util.getSetting("watchtogether.auto_join_last", False):
            return
        room_id = util.getSetting("watchtogether.last_room", "")
        if not room_id:
            return
        thread = threading.Thread(target=self._auto_join, args=(room_id,),
                                  name="wt-autojoin")
        thread.daemon = True
        thread.start()

    def _auto_join(self, room_id):
        try:
            self.join(room_id)
        except watchtogether.WatchTogetherError as exc:
            # dead room or dead token: forget it rather than retry every boot
            util.DEBUG_LOG("Watch Together: auto-join failed: {0}".format(
                exc.__class__.__name__))
            util.setSetting("watchtogether.last_room", "")
        except Exception:
            # transient/unexpected: log but keep last_room so the next boot retries
            util.ERROR()

    # -- OSD status --------------------------------------------------------------

    def update_status(self):
        if self.supervisor is None:
            text = ""
        elif not util.getSetting("watchtogether.show_osd_status", True):
            text = ""
        elif not self.supervisor.connected:
            text = util.T(35055, "Reconnecting…")
        else:
            count = len(self.room.participants) if self.room else 0
            text = util.T(35054, "{} watching").format(count)
        # base='{0}': the skin reads Window(10000).Property(watchtogether.status)
        util.setGlobalProperty("watchtogether.status", text, base="{0}")


bridge = WatchTogetherBridge()


class ParticipantsDialog(kodigui.BaseDialog, util.CronReceiver):
    """Who is in the room + leave. Roster refreshes from REST every 15s and
    the dialog closes itself if the room ends under it (supervisor gone)."""

    xmlFile = 'script-plex-watchtogether_participants.xml'
    path = util.ADDON.getAddonInfo('path')
    theme = 'Main'
    res = '1080i'
    width = 1920
    height = 1080

    LIST_ID = 100
    CLOSE_ID = 60
    LEAVE_ID = 61

    def onFirstInit(self):
        self.peopleList = kodigui.ManagedControlList(self, self.LIST_ID, 8)
        self._key = None
        self._ticks = 0
        bridge.refresh_room()
        self._sync()
        # focus Close (not Leave): OK must dismiss the popup, leaving must be
        # a deliberate second choice
        self.setFocusId(self.CLOSE_ID)
        util.CRON.registerReceiver(self)

    def onClosed(self):
        util.CRON.cancelReceiver(self)

    def tick(self):
        if bridge.supervisor is None:
            self.doClose()              # room gone / left from elsewhere
            return
        self._ticks += 1
        if self._ticks % 15 == 0:
            bridge.refresh_room()
        self._sync()

    def _sync(self):
        room = bridge.room
        participants = room.participants if room else []
        sup = bridge.supervisor
        roster = sup.session.roster \
            if sup is not None and sup.session is not None else {}
        watching = util.T(35090, "Watching")
        rows = [{
            "name": u.get('title') or u.get('username') or '',
            "thumb": u.get('thumb') or '',
            "status": member_state_label(str(u.get('id')), roster,
                                         bridge._participant_state, watching),
        } for u in participants]
        key = tuple((str(u.get('id')), r['status'])
                    for u, r in zip(participants, rows))
        if key == self._key:
            return
        self._key = key
        items = [kodigui.ManagedListItem(
            r['name'], r['status'],
            thumbnailImage=r['thumb'],
            data_source=u) for u, r in zip(participants, rows)]
        self.peopleList.reset()
        self.peopleList.addItems(items)

    def onClick(self, controlID):
        if controlID == self.CLOSE_ID:
            self.doClose()
        elif controlID == self.LEAVE_ID and confirm_leave():
            self.leaveRoom()

    @busy.dialog()
    def leaveRoom(self):
        bridge.leave()
        self.doClose()


class RoomInfoDialog(kodigui.BaseDialog):
    """Read-only room info: the media and the participants, with a live marker
    for those currently connected (known only for the room we are in)."""

    xmlFile = 'script-plex-watchtogether_room_info.xml'
    path = util.ADDON.getAddonInfo('path')
    theme = 'Main'
    res = '1080i'
    width = 1920
    height = 1080

    LIST_ID = 100
    CLOSE_ID = 60

    def __init__(self, *args, **kwargs):
        kodigui.BaseDialog.__init__(self, *args, **kwargs)
        self.room = kwargs.get('room')
        self.item = kwargs.get('item')

    def onFirstInit(self):
        self.peopleList = kodigui.ManagedControlList(self, self.LIST_ID, 8)
        room = self.room
        self.setProperty('heading', room.title if room else '')
        self.setProperty('watching', self.item.title if self.item else '')
        self._sync()
        self.setFocusId(self.CLOSE_ID)

    def _sync(self):
        live = bridge._live_user_ids()
        state_for = bridge._participant_state if live else None
        items = [kodigui.ManagedListItem(row['name'], row['sub'],
                                         thumbnailImage=row['thumb'],
                                         data_source=self.room)
                 for row in room_info_rows(self.room, live, state_for)]
        self.peopleList.reset()
        self.peopleList.addItems(items)

    def onClick(self, controlID):
        if controlID == self.CLOSE_ID:
            self.doClose()


class LobbyDialog(kodigui.BaseDialog):
    """The Watch Together lobby: media title, participant readiness, and the
    host's Start/Cancel/Invite — or a guest's read-only view with Leave.

    Shown non-modally via create(): host() shows it right before
    videoplayer.play() blocks, so a modal open would deadlock. It refreshes
    itself on a peer's readiness change (bridge._on_ready) and drops the
    bridge's reference when it closes."""

    xmlFile = 'script-plex-watchtogether_lobby.xml'
    path = util.ADDON.getAddonInfo('path')
    theme = 'Main'
    res = '1080i'
    width = 1920
    height = 1080

    LIST_ID = 100
    INVITE_ID = 60
    START_ID = 61
    CANCEL_ID = 62
    LEAVE_ID = 63

    def __init__(self, *args, **kwargs):
        kodigui.BaseDialog.__init__(self, *args, **kwargs)
        self.room = kwargs.get('room')
        self.roster = kwargs.get('roster') or {}
        self.is_host = bool(kwargs.get('host'))

    def onFirstInit(self):
        self.peopleList = kodigui.ManagedControlList(self, self.LIST_ID, 8)
        room = self.room
        self.setProperty('watching', room.title if room else '')
        self.setBoolProperty('is_host', self.is_host)
        self._sync()
        self.setFocusId(self.START_ID if self.is_host else self.LEAVE_ID)

    def refresh(self):
        """Re-read the roster and repaint (called from the supervisor thread on
        a roster/readiness change — never raise). Membership comes from
        bridge.room in _sync, so an invitee added by the 15 s poll appears.

        Kodi only delivers onNotification to xbmc.Monitor, never to a window
        (see Kodi's Window.h callback list), so there is no UI-thread hand-off
        to queue into here: _sync rejects the work once the dialog is closing,
        which is the state a stale callback would otherwise corrupt."""
        if getattr(self, 'peopleList', None) is None:
            return          # window not initialised yet: nothing to repaint
        sup = bridge.supervisor
        if sup is not None and sup.session is not None:
            self.roster = sup.session.roster
        try:
            self._sync()
        except Exception:
            # never tear down the supervisor thread that called us
            util.ERROR()

    def _sync(self):
        if self._closing:
            return          # closed while a callback still held this dialog
        # the open lobby must follow the bridge's live room (on_roster replaces
        # it every 15 s); self.room is only the fallback before the first poll
        room = bridge.room or self.room
        preparing_id = None
        if bridge._detector_requestid is not None:
            preparing_id = str(plexapp.ACCOUNT.ID)
        items = [kodigui.ManagedListItem(row['title'], row['status'],
                                         thumbnailImage=row['thumb'],
                                         data_source=room)
                 for row in lobby_rows(room, self.roster, preparing_id,
                                       bridge._participant_state)]
        self.peopleList.reset()
        self.peopleList.addItems(items)

    def onAction(self, action):
        if action in (xbmcgui.ACTION_PREVIOUS_MENU, xbmcgui.ACTION_NAV_BACK):
            # ESC/back: close the lobby and leave, instead of falling through
            # to the video window's stop (which left the modal lobby up on a
            # grey screen)
            if self.is_host:
                bridge.cancel_hosting()
            else:
                bridge.leave()
            return
        kodigui.BaseDialog.onAction(self, action)

    def onClick(self, controlID):
        if controlID == self.INVITE_ID:
            self._invite()
        elif controlID == self.START_ID:
            bridge.start_playback()     # closes the lobby
        elif controlID == self.CANCEL_ID:
            bridge.cancel_hosting()     # leave (DELETE) + close
        elif controlID == self.LEAVE_ID:
            bridge.leave()
            self.doClose()

    def _invite(self):
        # Task 9 provides InviteDialog; open it when present so the lobby does
        # not hard-depend on it landing first. Prefer the bridge's live room:
        # self.room is the snapshot taken when the lobby opened.
        invite_dialog = globals().get('InviteDialog')
        if invite_dialog is not None:
            invite_dialog.open(room=bridge.room or self.room)

    def doClose(self, **kw):
        if bridge.lobby is self:
            bridge.lobby = None
        kodigui.BaseDialog.doClose(self, **kw)


class InviteDialog(kodigui.BaseDialog):
    """Multi-select picker over the eligible invitees for the current room.

    The list is a plex.tv round trip, so it is fetched off the UI thread; OK
    calls bridge.invite(selected). A failed target is toasted — the rest are
    still invited (bridge.invite is per-id)."""

    xmlFile = 'script-plex-watchtogether_invite.xml'
    path = util.ADDON.getAddonInfo('path')
    theme = 'Main'
    res = '1080i'
    width = 1920
    height = 1080

    LIST_ID = 100
    OK_ID = 60
    CANCEL_ID = 61

    def __init__(self, *args, **kwargs):
        kodigui.BaseDialog.__init__(self, *args, **kwargs)
        # the room to invite into; None means "the bridge's current room"
        self.room = kwargs.get('room')

    def onFirstInit(self):
        self.peopleList = kodigui.ManagedControlList(self, self.LIST_ID, 8)
        self._invitees = []
        self._load()
        # focus OK, not the (still empty) list: focusing an empty list at show
        # makes Kodi log "Control 100 ... asked to focus, but it can't"
        self.setFocusId(self.OK_ID)

    def _load(self):
        thread = threading.Thread(target=self._fetch, name="wt-invitees")
        thread.daemon = True
        thread.start()

    def _fetch(self):
        try:
            invitees = bridge.invitees(self.room)
        except Exception:
            # never let a people lookup break the picker (Review Focus 1)
            util.ERROR()
            invitees = []
        self._invitees = invitees
        self._sync()

    def _sync(self):
        if getattr(self, "_closing", False):
            return          # closed while the fetch was in flight
        self.setBoolProperty("empty", not self._invitees)
        self.peopleList.reset()
        self.peopleList.addItems([
            kodigui.ManagedListItem(
                row["title"], "", thumbnailImage=row["thumb"],
                data_source=row["id"],
                properties={"access_unknown": row["access_unknown"]})
            for row in invite_rows(self._invitees)])
        if self._invitees:
            # list was empty at show, so focus it now that it has rows
            self.setFocusId(self.LIST_ID)

    def _selected_ids(self):
        return [item.dataSource for item in self.peopleList.items
                if item.getProperty("selected")]

    def onAction(self, action):
        if action in (xbmcgui.ACTION_PREVIOUS_MENU, xbmcgui.ACTION_NAV_BACK):
            self.doClose()
            return
        kodigui.BaseDialog.onAction(self, action)

    def onClick(self, controlID):
        if controlID == self.LIST_ID:
            item = self.peopleList.getSelectedItem()
            if item is not None:
                item.setProperty("selected",
                                 "" if item.getProperty("selected") else "1")
        elif controlID == self.OK_ID:
            self._invite()
        elif controlID == self.CANCEL_ID:
            self.doClose()

    def _invite(self):
        ids = self._selected_ids()
        self.doClose()
        if ids:
            self._send(ids)

    @busy.dialog()
    def _send(self, ids):
        try:
            failed = bridge.invite(ids, self.room)
        except watchtogether.AuthError:
            # dead token: nothing was invited, ask the user to sign in again
            util.showNotification(
                util.T(35083, "Sign in again to use Watch Together"))
            return
        if failed:
            util.showNotification(
                util.T(35079, "Some people could not be invited"))


def show_room_info(room):
    """Open the room info dialog (resolves the media item best-effort)."""
    bridge.start()
    item = bridge._room_media_item(room)
    window = RoomInfoDialog.open(room=room, item=item)
    del window
    util.garbageCollect()


def show_participants():
    """Open the participants/leave dialog (used from the video OSD)."""
    bridge.start()
    window = ParticipantsDialog.open()
    del window
    util.garbageCollect()


@busy.dialog()
def leave_room():
    """Leave the current room (used from the video OSD)."""
    bridge.leave()
