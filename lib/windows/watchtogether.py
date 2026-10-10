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
from plexnet import plexapp, plexlibrary, plexobjects

from lib import plex, plexpeople, player, syncplay, util, watchtogether, ws
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


def _player():
    """The live PlexPlayer, or None during addon shutdown (player.PLAYER is
    deleted by player.shutdown() while daemon threads may still tick)."""
    return getattr(player, "PLAYER", None)


def room_info_rows(room, live_ids):
    """One row per room user for the info dialog, marking who is connected.
    `live_ids` are the userIDs seen on the relay roster (only known while
    connected to that room)."""
    rows = []
    for user in (room.participants if room else []):
        if not isinstance(user, dict):
            continue
        name = user.get("title") or user.get("username") or ""
        is_live = str(user.get("id")) in live_ids
        rows.append({
            "name": name,
            "sub": util.T(35068, "Live") if is_live else (user.get("username") or ""),
            "thumb": user.get("thumb") or "",
            "live": is_live,
        })
    return rows


def lobby_rows(room, roster):
    """One row per room user for the lobby, with readiness status.

    Status is "Ready" when the user's id is on the roster with isReady True,
    else "Invited" (they have not joined/readied yet)."""
    ready = syncplay.ready_member_ids(roster)
    rows = []
    for user in (room.participants if room else []):
        if not isinstance(user, dict):
            continue
        rows.append({
            "title": user.get("title") or user.get("username") or "",
            "thumb": user.get("thumb") or "",
            "status": util.T(35075, "Ready") if str(user.get("id")) in ready
                      else util.T(35076, "Invited"),
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
        self._tempo = 1.0
        self._tempo_retry_at = 0.0
        self._was_connected = False
        self._player_ready = False
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
        """Fresh GET /rooms/{id} while the participants dialog is open."""
        sup = self.supervisor
        if sup is None:
            return

        def work():
            try:
                room = self.ensure_api().room(sup.room.id)
            except Exception as exc:
                util.DEBUG_LOG("Watch Together: room refresh failed: {0}".format(
                    exc.__class__.__name__))
                return
            # post-request ownership check: a room switch may have happened
            # while the REST was in flight
            if self.supervisor is sup:
                self.room = room

        thread = threading.Thread(target=work, name="wt-room")
        thread.daemon = True
        thread.start()

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

        The host waiting in the Home lobby has no video yet, so that state
        counts as ready too — host() sets it, but the 1 s tick would otherwise
        overwrite it with False and auto-start would never fire."""
        if self._hosting and not self._started:
            self._player_ready = True
            sup.set_ready(True)
            return
        pl = _player()
        ready = bool(pl is not None and pl.isPlayingVideo()
                     and self._owns_playback()
                     and not xbmc.getCondVisibility("Player.Caching"))
        self._player_ready = ready
        sup.set_ready(ready)

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
        # the host waits in the lobby rather than buffering the video
        self._player_ready = True
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
        failure, so AuthError propagates for the caller to report."""
        if room is None:
            room = self.room
        if room is None:
            return list(user_ids)
        failed = []
        invited = False
        for user_id in user_ids:
            try:
                self.ensure_api().invite(room.id, [user_id])
                invited = True
            except watchtogether.AuthError:
                raise
            except watchtogether.WatchTogetherError:
                failed.append(user_id)
        if invited and room is self.room:
            self.refresh_room()     # pull the new members into the open lobby
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
        self._update_guest_lobby(remote)
        if time.monotonic() - self._local_change_at < LOCAL_CHANGE_GRACE:
            return          # our own change is in flight; don't be reverted
        pl = _player()
        # §6.3 foreground/background: v1 approximates "foreground" with "video
        # playing" (no ad-break sync — an explicit v1 non-goal). The lobby and
        # theme-music cases stay background and ignore the relay's playstate.
        if pl is None or not pl.isPlayingVideo() or not self._owns_playback():
            return
        local_pos = pl.getTime() or 0.0
        # publish our own position only once it actually matches the room: a
        # just-started video at ~0 (or a seek that hasn't landed yet) would
        # otherwise become the room position and drag everyone to the start
        if abs(local_pos - remote.get("position", 0.0)) < 2.0:
            sup.mark_synced()
        action = syncplay.sync_action(local_pos, remote.get("position", 0.0),
                                      remote.get("paused", True),
                                      session.latency.forward_delay)
        want_paused = remote.get("paused")
        is_paused = bool(xbmc.getCondVisibility("Player.Paused"))
        applied = False
        # arm the echo deadline only when we actually change something: remote
        # States arrive ~1 Hz, so arming on every frame would keep the gate
        # closed and swallow every genuine local event (design §Echo)
        if want_paused is not None and want_paused != is_paused:
            pl.wt_applying_remote = time.monotonic() + 2.0
            pl.control("pause" if want_paused else "play")
            self._set_tempo(1.0)
            applied = True
        if remote.get("doSeek"):
            # §5.6: a peer's explicit seek command — apply even inside the
            # drift band, where sync_action would stay put
            pl.wt_applying_remote = time.monotonic() + 2.0
            self._seek_to(remote.get("position", 0.0))
            self._set_tempo(1.0)
            applied = True
        elif action and action[0] == "seek":
            pl.wt_applying_remote = time.monotonic() + 2.0
            self._seek_to(action[1])
            self._set_tempo(1.0)
            applied = True
        elif action and action[0] == "tempo":
            # §6.2 gentle catch-up: slow to 0.95 with pitch preserved (Kodi 21+)
            result = self._set_tempo(action[1])
            if result is False:
                # no tempo here: degrade to a hard seek so drift still converges
                target = remote.get("position", 0.0) + \
                    (0 if remote.get("paused") else session.latency.forward_delay)
                pl.wt_applying_remote = time.monotonic() + 2.0
                self._seek_to(target)
                applied = True
            # result True: tempo applied; None: player busy, retry next tick
        else:
            self._set_tempo(1.0)   # inside the drift band: clear any catch-up
        if applied:
            util.DEBUG_LOG("Watch Together: applied remote {0} (paused={1}, pos={2})".format(
                action, want_paused, remote.get("position")))

    def _set_tempo(self, tempo):
        """§6.2 pitch-preserved tempo catch-up, via JSON-RPC Player.SetTempo
        (Kodi 21+). Returns True when applied, False when unavailable/failed
        (caller hard-seeks), or None when the player is busy seeking/caching
        (retry next tick)."""
        if tempo == self._tempo:
            return True
        # SetTempo is refused while the player is mid-seek or buffering (seen
        # on Kodi 21.0); don't call it then, and don't hard-seek either.
        if (xbmc.getCondVisibility("Player.Seeking")
                or xbmc.getCondVisibility("Player.Caching")):
            return None
        now = time.monotonic()
        if now < self._tempo_retry_at:
            return False
        if util.KODI_VERSION_MAJOR < 21:
            self._tempo_retry_at = now + 3600.0
            util.LOG("Watch Together: tempo catch-up needs Kodi 21+ (have {0}); "
                     "using hard seek".format(util.KODI_VERSION_MAJOR))
            return False
        try:
            players = util.rpc.Player.GetActivePlayers() or []
            playerid = next((p["playerid"] for p in players
                             if p.get("type") == "video"), None)
            if playerid is None:
                return False
            util.rpc.Player.SetTempo(playerid=playerid, tempo=tempo)
            self._tempo = tempo
            util.DEBUG_LOG("Watch Together: tempo {0}".format(tempo))
            return True
        except Exception as exc:
            # SetTempo is advertised on Kodi 21 but the player may still refuse
            # it. Back off and hard-seek meanwhile.
            self._tempo_retry_at = now + 60.0
            self._tempo = 1.0
            util.LOG("Watch Together: SetTempo failed ({0}); using hard seek "
                     "(retry in 60s)".format(exc))
            return False

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
        util.DEBUG_LOG("Watch Together: roster {0}".format(kind))

    def _on_ready(self, key, is_ready):
        """A peer's readiness changed (§6.4). Refresh the open lobby and start
        the room once everyone is ready. Supervisor thread — never raise."""
        try:
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
            try:
                ids.add(str(json.loads(syncplay.strip_identity(key)).get("userID")))
            except (ValueError, TypeError, AttributeError):
                pass
        return ids

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
        # lobby closes on the first playing State, then the video opens
        if self._room_unstarted():
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
        player.PLAYER.wt_broadcast = None
        player.PLAYER.wt_applying_remote = 0.0
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
        key = tuple(sorted(str(u.get('id')) for u in participants))
        if key == self._key:
            return
        self._key = key
        items = [kodigui.ManagedListItem(
            u.get('title') or u.get('username') or '',
            u.get('username') or '',
            thumbnailImage=u.get('thumb') or '',
            data_source=u) for u in participants]
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
        items = [kodigui.ManagedListItem(row['name'], row['sub'],
                                         thumbnailImage=row['thumb'],
                                         data_source=self.room)
                 for row in room_info_rows(self.room, live)]
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
        items = [kodigui.ManagedListItem(row['title'], row['status'],
                                         thumbnailImage=row['thumb'],
                                         data_source=room)
                 for row in lobby_rows(room, self.roster)]
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
