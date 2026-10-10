# Plex Watch Together — client implementation spec (reverse engineered)

Everything a third-party client needs in order to implement Watch Together, reverse
engineered from the wire. Written for implementers, not users.

Live-verified against `together.plex.tv` and the Syncplay relay on 2026-10-04/05.
Static analysis from the Plex Web client your server still serves —
`https://<<SERVER>>/web/js/main-8792-…-plex-4.160.0-75ddd7b.js`
(Web 4.160.0, hash `1d3f5255491b16d9bd14`).

**Everything marked [LIVE] was captured off the wire**, not read out of the minified
bundle. Only the read path was exercised against a real user's live room; every
write-path test ran in a throwaway room the cloud never knew about (see §7).

### Read this before you start

This is an **undocumented, unsupported internal API**. Before you build on it:

* **The relay has no authentication whatsoever** (§7). Any client that can reach it can
  join any room it can name, and control that room's playback. A room ID is a bearer
  secret. Do not put room IDs in logs, analytics, crash reports, or share links; treat a
  leaked room ID as equivalent to leaking playback control.
* **There is no versioning contract.** The relay reports `realversion: 1.6.5` but accepts
  a `1.6.4` claim without complaint, so you cannot detect a protocol change before it
  breaks you. Log `realversion` and branch defensively.
* **Plex has announced removal of this feature from native clients** (§2). Web is the
  only supported surface today.
* **The server author cannot help you.** Nothing here touches the media server.
* You are reverse engineering against a cloud service that can change without notice.

If any of that is unacceptable for your project, stop here.

### How to read this document

| Section | For you if you're… |
|---|---|
| §2–§3 | implementing anything — status + topology |
| §4 | joining/discovering rooms over REST |
| §5 | **the core** — the WebSocket wire protocol |
| §6 | writing the sync loop (client-agnostic algorithm) |
| §7 | verifying your work; also the security model |
| §8 | **a conformance checklist — read this one** |
| §9–§12 | PM4K-specific (appendix): skip if you are not PM4K |

---

## 1. TL;DR

* Watch Together is **not a Plex Media Server feature**. Zero PMS endpoints. It is a
  Plex cloud service: `https://together.plex.tv` for room bookkeeping, plus a **Syncplay**
  WebSocket relay for the actual playback sync.
* PMS needs no changes at all. The only server interaction is the ordinary
  `sourceUri` → metadata fetch every client already does.
* The relay is a **dumb, unauthenticated pub/sub bus** [LIVE]. It has no room table, does
  no membership check, and takes no token. The room ID *is* the only secret. Confirmed
  against a real cloud-issued room with two real accounts: a third client with a fabricated
  `userID` joined anyway (§11 item 26).
* **There is no "end session for everyone" call** [LIVE]. `DELETE /rooms/{id}` only removes
  *you*, and the relay ignores cloud state entirely — so leaving never evicts anyone. Rooms
  die on a 3 h clock (§4).
* Wire protocol reverse engineered below, including three message types
  (`Set.playlistChange`, `Set.playlistIndex`, `Set.user.file`) and four fields
  (`controller`, `manuallyInitiated`, `realversion`, per-room `features`) that the shipped
  web client doesn't implement at all — the relay is ahead of Plex's own client.
* Most clients already have the player-side pieces. The one genuinely new piece of
  infrastructure is a ~150-line RFC6455 client on `ssl` + `socket`.
* Caveats: undocumented, unversioned, cloud-only, no access control, and Plex has already
  announced the feature's removal from native clients once.

---

## 2. Lifecycle / deprecation status

* Announced 2020-05-28 as free beta.
* 2025-02-25 [blog update](https://www.plex.tv/blog/coming-in-hot-watch-together-chill/):
  "we are ending support for some features we've grown to love, like Watch Together …
  you can continue using the feature in our web app for the foreseeable future."
* Reality (2026-10): Plex Web 4.160.0 still ships the complete implementation. Native
  clients dropped it. Still listed as a sidebar hub.
* No feature gating found: the live room record has no `subscription`/tier field at all.
  The `subscription` boolean I originally inferred from the bundle's user model does not
  appear in the actual API response.

---

## 3. Service topology

Discovered in the bundle's environment config (`localStorage` key `plexEnvironment`):

```js
{
  pubsub:        { baseUrl: "https://pubsub.plex.tv", wssBaseUrl: "wss://pubsub.plex.tv" },
  watchtogether: { baseUrl: "https://together.plex.tv" }
}
```

```
   Plex Web / (PM4K, hypothetically)
              │  REST: X-Plex-Token + normal Plex client headers
              ▼
   https://together.plex.tv/rooms     ← token-checked room list / create / invite / delete
              │  room record contains syncplayHost + syncplayPort
              ▼
   wss://pop-fra00.syncplay.plex.services:7776/ws    ← NOT token-checked, NOT membership-checked
              │
              │  (no PMS involvement at all)
              ▼
        Plex Media Server   ← only for sourceUri → metadata
```

**The two services have completely different security postures.** The cloud knows which
rooms exist and who may see them. The relay knows nothing. Anyone who learns a room ID can
join and, if they are the first connection, take control (§6).

Relay infra [LIVE] — **all four PoPs enumerated**, `docs/probes/popinventory.py`:

```
                 CNAME                             A                  AAAA
pop-fra00:7776   syncplay00.pop.fra.plex.bz       172.104.145.47     2a01:7e01::f03c:92ff:feda:4979
pop-fra01:7777   syncplay01.pop.fra.plex.bz       172.104.203.32     2a01:7e01::f03c:92ff:feda:495e
pop-atl00:7777   syncplay00.pop.atl.plex.bz       170.187.201.8      (none)
pop-atl01:7777   syncplay01.pop.atl.plex.bz       139.144.189.245    2600:3c02::f03c:93ff:fe06:f95e
```

* **One certificate for everything** — all four PoPs, both ports, byte-identical: serial
  `0FF0E59865B296ECDDF0C939A2DB1D9F`, SANs `*.syncplay.plex.services` + apex, issuer
  DigiCert Global G2 TLS RSA SHA256 2020 CA1, O=Plex GmbH, valid 2026-08-18 → **2027-03-04**.
  Not per-PoP, so there is nothing to fingerprint a PoP by.
* **No PoP differs in TLS.** Earlier drafts recorded fra01 as "TLSv1.2 (verified)" — that
  was the *probing client* (LibreSSL 2.8.3, capped at 1.2), not the PoP. `openssl 3.3.6`
  gets **TLSv1.3 / AEAD-AES256-GCM-SHA384** on all of them. ALPN: none offered.
* `Server: AutobahnPython/21.3.1`, `realversion 1.6.5`, identical `features` — every PoP.
* **Both ports are live on every PoP** (7776 and 7777 both upgrade), so the port is a second
  listener, not a different deployment.
* **A fourth PoP exists** and no room record has handed one out yet. Sweeping ~70
  `pop-<city><NN>` combinations resolves only `fra00/fra01` and `atl00/atl01`; there is no
  wildcard, and the apex `syncplay.plex.services` does not resolve despite being in the SANs.
* CNAME targets are `syncplay<NN>.pop.<city>.plex.bz` — a third TLD, `.bz`. Neither
  `pop.fra.plex.bz` nor `plex.bz` resolves on its own.
* IPv6 records exist but **reachability is untested** — the probing host has no working v6
  egress, so this is "unverified", not "broken".

#### Rooms are scoped to one host:port — a wrong port fails *silently* [LIVE]

The relay has no room table, which suggests any PoP would serve any room name. Half true,
and the false half is the one that bites. `docs/probes/popcrosstalk.py`:

| clients | handshake | each sees in `List` |
|---|---|---|
| 2 on the **same** host:port | `101` both | **both identities** (the control) |
| 2 on **different** PoPs | `101` both | only itself |
| 2 on the **same PoP, different port** | `101` both | only itself |

* **Every PoP accepts every room name** with `101` and a working `State` stream — so a wrong
  endpoint produces **no error at all**.
* **But a room name is scoped to a single relay *instance*, i.e. one `host:port` pair.**
  Clients that disagree on either field end up in separate rooms that look identical.
* **`syncplayHost` *and* `syncplayPort` are both load-bearing**, not advisory. Get the port
  wrong and you join an empty room, see a one-member roster, and **sync to yourself forever**
  while the UI reports a healthy session. Always take both from the room record.

**The port is not fixed, the PoP is not fixed, and neither correlates.** `7776` and `7777`
both appear, across two `fra` PoPs and an `atl` one — the third room got `7777` on `fra01`
where the first got `7776` on `fra00`. The naming is `pop-<city><NN>` and the numbering is
per-PoP, so **there is no way to derive the host or port from anything but the room record.**

Always take `syncplayHost`/`syncplayPort` from the room record — a client that hardcodes
either will fail for some fraction of real rooms, which is the worst kind of bug to ship.

Note the TLD is `.services`, **not** `.tv` — `syncplay.plex.tv` does not resolve, so
anyone grepping for that hostname will conclude (wrongly) that there's no relay.

The relay is the **paid Syncplay infrastructure**, shared with the Syncplay feature.
Evidence: the web client's Watch Together code carries no `controller`, `playlistChange`,
`playlistIndex`, `sharedPlaylists`, `manuallyInitiated` or `isolateRooms` symbols at all,
yet the relay speaks all of them (§5.4).

---

## 4. REST API — `https://together.plex.tv`

`X-Plex-Token` (plex.tv account token) plus the standard Plex client headers from the
environment object. JSON in, JSON out.

| Method | Path | Body | Response |
|---|---|---|---|
| `GET` | `/rooms` | – | `{"rooms":[…]}` — rooms you can see |
| `GET` | `/rooms/{roomID}` | – | `<Room>` |
| `POST` | `/rooms` | `{sourceUri, title, users}` | `201 <Room>`; client reads `.id` |
| `POST` | `/rooms/{roomID}/invite` | `{users:[userID,…]}` | `200 <Room>` with the user added |
| `DELETE` | `/rooms/{roomID}` | – | `204`, empty body — **this is "leave", not "destroy"** |
| `PATCH` | `/rooms/{roomID}` | JSON body | `200 <Room>` — **body required, see below** |

[LIVE] Verified:

```
GET  /rooms                    → 200  {"rooms":[…]}
GET  /rooms/ca8cfezmke4        → 200  {…}
GET  /rooms/doesnotexist123    → 404  "room not found not found!"
GET  /rooms  (no token)         → 401  "You must provide a token!"
GET  /rooms  (no active rooms)  → 200  {"rooms":[]}      ← empty array, not null/404
GET  /rooms/<expired roomID>    → 404  "room not found not found!"
```

The empty-list and expiry rows were captured by watching a real room pass its
three-hour wall: at `endsAt` the room stopped appearing in `GET /rooms` and the direct
fetch flipped from `200` to `404`. **A room ID you were given 20 minutes ago may simply
not exist** — surface that as "session ended", never as an error you should retry.

### Creating / inviting / leaving / renaming — **now live-verified** [LIVE]

Previously bundle-derived only. Exercised end-to-end against the real cloud on
2026-10-05 with a throwaway room, then cleaned up:

```
POST   /rooms  {sourceUri,title,users:null}          → 201, full Room, id returned
GET    /rooms                                        → 200, the room listed
GET    /rooms/{id}                                   → 200
POST   /rooms/{id}/invite  {users:[1000002]}          → 200, Room with users[] = 2
PATCH  /rooms/{id}  {title:…}                        → 200, Room with the new title
DELETE /rooms/{id}                                   → 204, empty body
DELETE /rooms/{id}          (no token)               → 401 "You must provide a token!"
DELETE /rooms/{id}          (bogus token)             → 401 "Invalid token"  (clean -- see below)
DELETE /rooms/doesnotexist123                        → 404 "room not found not found!"

tokenless sweep across every method, same room (2026-10-06):
GET /rooms/{id}   → 401 "You must provide a token!"
PATCH /rooms/{id} → 401 "You must provide a token!"
invite            → 401 "You must provide a token!"
and with a bogus token instead of none:
GET /rooms        → 401 "Invalid token"
PATCH /rooms/{id} → 401 "Invalid token"
DELETE /rooms/{id}→ 401 "Invalid token"
invite            → 401 "Invalid token"
POST /rooms       → 401 "Invalid token"
```

Findings that change what a client must do:

* **`PATCH` is not dead code, and it takes a body, not query params.** The bundle has no
  caller for it, but the endpoint is live. `?title=…` on its own is **silently ignored** —
  you must send `{"title": "…"}`. It is the only way to rename a live room, and it bumps
  `updatedAt`. Do not carry the "dead code" assumption into an implementation.
* **`POST /rooms` returns `201`, not `200`.** Anything checking `== 200` will treat a
  successful create as a failure.
* **`invite` returns the whole `Room`, not an empty body.** The doc's table said "–". Use
  the response if you want the new `users[]` rather than re-`GET`ing.
* **`DELETE` is silent about authorisation failures.** A missing or invalid token gets
  `401`, and the room survives — verified by re-fetching after both.

#### `DELETE` means "leave the room" — it never destroys anything [LIVE]

This is the sharpest result of the whole write-path exercise, and it overturns an earlier
reading of this very section, which claimed `DELETE` "destroys the entire room, not one
participant". It does the opposite. `authzprobe.py` / `authzprobe2.py` ran the full matrix
with two **genuinely different accounts** (`serverowner` `1000001` as creator,
`libraryuser` `1000002` as invited participant):

```
room with host + peer invited, then:

DELETE by PEER    → 204      peer  GET → 403 "you do not have access to that room"
                           host  GET → 200   ← room ALIVE
                           host GET /rooms → still listed
DELETE by CREATOR → 204      host  GET → 403
                           peer  GET → 200   ← room ALIVE
                           peer GET /rooms → still listed
second DELETE by the same caller → 404 "room not found not found!"
```

* **`DELETE` removes only the caller from `users[]`.** It is symmetric: creator and
  participant both just leave. Nobody's `DELETE` destroys the room for the others.
* **So `DELETE` *is* the per-participant removal endpoint.** There is no separate one, and
  no need for one — it doubles as both "leave" and, for the creator, "stop hosting".
* **There is no destroy-for-everyone.** Once you have left, `404`; a room only really goes
  away when it reaches `endsAt`. Every room this research created is still on the cloud,
  minus the caller's own membership, until its 3 h wall.
* **Leaving is reversible** — the creator can `invite` you straight back and you get `200`.
  So a client should offer "leave" rather than anything final-sounding, because the host
  can undo it.

#### Authorisation matrix, measured with two real accounts [LIVE]

Every cell is now measured — including all four tokenless ones and the whole
invalid-token column (2026-10-06). **Absence of a token and possession of a bad token are
the same answer: `401`, on every method.** Non-member with a *valid* token is where the
endpoints disagree.

| | no token | invalid token | non-member (valid token) | invited participant | creator |
|---|---|---|---|---|---|
| `GET /rooms` | `401` | `401` "Invalid token" | `200`, own rooms only | `200`, own rooms only | `200`, own rooms only |
| `GET /rooms/{id}` | `401` | `401` | **`403`** | `200` | `200` |
| `POST /rooms` | `401` | `401` | `201` (not gated) | `201` | `201` |
| `POST /rooms/{id}/invite` | `401` | `401` | **`403`** | **`200`** *(if target is the caller's friend/home user)* | `200` |
| `PATCH /rooms/{id}` | `401` | `401` | **`403`** | **`200` — title changed** | `200` |
| `DELETE /rooms/{id}` | `401` | `401` | **`404`** *(not `403`)* | `204` (leaves) | `204` (leaves) |

* **Tokenless and invalid-token are indistinguishable: `401` everywhere.** Measured on
  `GET`, `PATCH`, `DELETE`, `invite` and `POST /rooms` with no token at all, then again
  with `X-Plex-Token: bogus` — all `401`. A client cannot tell "forgot the token" from
  "token was revoked" and must not try to branch on it.
  * **The first `401` for an unknown token leaks an internal cluster URL; later ones do
    not.** First request with a never-before-seen token returns
    `Request failed with status code 401 (Unauthorized): GET http://my-plex-api.plex-tv.svc.cluster.local:8080/api/v2/services/user …`
    — the full in-cluster Kubernetes service URL, upstream error forwarded verbatim.
    The **second and third** requests with the *same* token return the plain
    `Invalid token`, so the failure is cached after the first hop. Reproduced on two
    fresh 16-hex tokens (`req1` leak, `req2`/`req3` clean), and it moves between
    endpoints (`GET /rooms` leaked on one run while `GET /rooms/{id}` leaked on another),
    so which call you see it on is not predictable.
    * `bogus` and `bogus-token` never leak — they are clean on `req1`, i.e. hard-coded
      test values that short-circuit before the upstream call. `BOGUS`, `Invalid`,
      `invalid`, `token`, `test`, `aaaa`, `12345` and `not-a-real-token` all leaked, so
      this is an allowlist of literal strings, not a normalisation rule.
    * **Practical: never log a `401` response body.** The body is untrusted, and the one
      that leaks tells an attacker the internal service topology. Log the status and the
      endpoint, not the payload. Note also that a client cannot distinguish "no token"
      from "bad token" by body text either — both are `401` and only the message differs.
* **`invite` is NOT host-gated — a plain participant can invite, and got `200`.** An
  earlier reading said the opposite because a participant inviting an unrelated id
  returned `400`; that `400` was the *relationship* gate (§11.9), not the role. The
  participant inviting a target it *is* related to returns `200` and grows `users[]` to
  three entries — **with the inviter's own id duplicated**, so `users[]` can contain the
  same id twice (`[1000001, 1000002, 1000001]`). Treat `users[]` as a set when reading
  it.
  Combined with `PATCH` below: **no write in this surface is gated on being the creator.**
  [LIVE, `inviteprobe.py`]
* **`PATCH` is *not* host-gated** and **can repoint `sourceUri`** — a participant renamed
  the room *and* repointed the library item (`…/227117` → `…/99999999`) with `200`. Treat
  `sourceUri` as participant-writable and do not rely on `PATCH` to gate anything.
* **`PATCH` with no JSON body returns `500` and leaks a Node internal:**
  `Cannot destructure property 'sourceUri' of 'req.body' as it is undefined.` It crashes on
  the body *before* the authorisation check, so a non-member gets a `500` instead of a
  `403`. Always send a body.
* **`GET` and `DELETE` disagree about the same state.** A non-member doing `GET` gets
  `403`; a non-member doing `DELETE` gets `404`. Same room, same caller, different code.

#### A room you have left is `403`, not `404` — and the relay never heard [LIVE]

```
DELETE /rooms/{id}          → 204
GET    /rooms/{id}          → 403 "you do not have access to that room"   ×3, stable
POST   /rooms/{id}/invite   → 403 "you do not have access to that room"
GET    /rooms               → 200 {"rooms":[]}
```

* **A room you are not in reads `403`, while an expired one reads `404`** — different
  status for two conditions a client must distinguish, and different message text. Handle
  all three (`403` not-a-member / `404` expired-or-never-existed / absent from `/rooms`).
* **The `403` is not transient and not a permissions bug** — it is what you get after
  leaving. Treat it as "gone", not as "retry with different credentials".
* **The relay still serves the room after everyone has left.** Immediately after the `204`,
  a socket to `pop-fra01:7777` with that room ID completed a full handshake and received a
  working session — `Hello`, `List`, `State` at 1 Hz, no complaint. The cloud's room table
  and the relay are **completely independent**, so leaving does not revoke relay access.

  Consequence: leaving on the cloud does not evict anyone from the relay. There is no
  server-side kick, and the relay will keep accepting that room name until the sockets die.
  A client that leaves a room must treat it as "stop advertising it" and rely on the
  participants' own sockets closing — it cannot enforce an end to the session.
* **`endsAt − startsAt == 10800`** confirmed on a freshly created room: 3 h, cloud-enforced.

### Room object [LIVE]

Real response (values abridged; identifiers redacted to deliberate placeholders):

```jsonc
{
  "id":           "ca8cfezmke4",
  "title":        "A Fazenda – S18 • E20 – Episode 20",
  "type":         "watch",
  "sourceUri":    "server://aaaa0000…4444/com.plexapp.plugins.library/library/metadata/227117",
  "source":       "server://aaaa0000…4444/com.plexapp.plugins.library/library/metadata/227117",
  "createdBy":    1000003,
  "startsAt":     1791128438,
  "updatedAt":    1791128438,
  "endsAt":       1791139238,
  "syncplayHost": "pop-fra00.syncplay.plex.services",
  "syncplayPort": 7776,
  "users": [
    { "id": 1000003,  "username": "otherviewer",       "title": "Other Viewer",
      "uuid": "aaaa000000000001", "thumb": "https://plex.tv/users/…/avatar?c=…" },
    { "id": 1000001, "username": "serverowner", "title": "Server Owner",
      "uuid": "aaaa000000000002", "thumb": "https://api.plex.tv/users/…/avatar?t=…" }
  ]
}
```

Corrections to my earlier reading of the bundle:

* `users` is a **JSON array of user objects**, *not* a dict keyed by userID.
* Fields are `id`, `username`, `title`, `uuid`, `thumb`. **No `subscription` field.**
* Extra fields the bundle's model doesn't advertise: `createdBy` (userID),
  `type: "watch"`, and `source`, which is a **verbatim duplicate of `sourceUri`**.
* `sourceUri` has **no `provider://` prefix** — it is
  `server://<machineIdentifier>/<ratingKey path>`. Newer Plex protocol versions
  (Plex Media Server 1.41+ / PMS "protocol 3.1") use
  `provider://<provider>/server://<machineIdentifier>/<key>`. **Send whatever your PMS
  understands and accept whatever comes back** — do not hardcode either form.
  Plex Web's own resolver handles both.
* `endsAt - startsAt = 10800` → **rooms live exactly 3 hours**, enforced by the cloud
  (verified: a real room vanished at its `endsAt`). The relay does not enforce it.
* **Room IDs are not fixed width.** Observed live: `ca8cfezmke4` (11 chars) and
  `1kp69st72evn` (12 chars). Treat them as opaque; the relay advertises
  `maxRoomNameLength: 36`.

### Room discovery / refresh

The web client keeps rooms fresh via pubsub, not polling:

```
wss://pubsub.plex.tv → {"command":"notifyWatchTogetherInvite", …}
wss://pubsub.plex.tv → {"command":"notifyWatchTogetherExpire", …}
   both merely trigger a re-GET of /rooms
```

Plus a one-shot `updateRooms` on sign-in / when the pubsub socket is not open.
**Polling `GET /rooms` on a timer is sufficient for most clients** and skips a whole second
WebSocket implementation (§10.4).

---

## 5. Syncplay wire protocol

[LIVE] Everything in this section.

Transport: WebSocket, text frames, plain JSON, no subprotocol, no compression.
The client must **pong server pings** — Autobahn sends an unsolicited empty ping frame
immediately on connect.

Handshake [LIVE]:

```
GET /ws HTTP/1.1
Host: pop-fra00.syncplay.plex.services
Upgrade: websocket
Connection: Upgrade
Sec-WebSocket-Key: <b64>
Sec-WebSocket-Version: 13
Origin: https://app.plex.tv
X-Plex-Product: PM4K          ← optional; no Plex headers are required

→ HTTP/1.1 101 Switching Protocols
  Server: AutobahnPython/21.3.1
  Upgrade: WebSocket
  Connection: Upgrade
  Sec-WebSocket-Accept: …
```

**No `X-Plex-Token`. No cookie. Nothing.** Verified: a socket with zero Plex
credentials received `101` and a full working session.

### 5.1 Identity value

```json
{"deviceIdentifier": "<X-Plex-Client-Identifier>",
 "deviceName":      "<device name>",
 "userID":          "<numeric string>"}
```

On the wire it is **double-encoded**: a JSON *string* inside the message.

```
Hello.room.name, List keys, Set.user keys, setBy  ── all carry this same string
```

The relay **echoes your string back verbatim** — it does not re-serialise it [LIVE].
A compact 54-byte identity (`json.dumps(..., separators=(",",":"))`) came back as those
same 54 bytes, separators and all. Plex Web happens to send spaced JSON, which is why the
raw bytes look canonical, but that is the *client's* choice.

Even so, **never string-compare a username raw** — for a completely different reason:

#### The relay mangles usernames in two ways [LIVE]

The identity string is used as the session key, and it is neither length-safe nor
collision-safe. Both behaviours verified against `features.maxUsernameLength: 150`:

| Input identity | Key the relay stores and reports |
|---|---|
| 54 bytes, compact separators | echoed verbatim (54) |
| 59 bytes, spaced separators | echoed verbatim (59) |
| 117 bytes | echoed verbatim (117) |
| 252–257 bytes | **hard-truncated to exactly 150 bytes** |
| byte-identical identity, 2nd concurrent session | sent value + `_` |
| byte-identical identity, 3rd concurrent session | sent value + `__` |
| byte-identical identity, 4th concurrent session | sent value + `___` |

So there is **no fixed-width padding** — but there *is* a **collision ladder**: the
*n*-th session presenting a byte-identical identity gets *n* trailing underscores.
Distinct sessions are **not** evicted (§5.8); they are simply given distinct keys.

Two consequences, and both will bite a naive client:

**1. Strip `/_+$/` before `json.loads`.** The web client does exactly this
(`t.replace(/_+$/,"")` before every parse) and it is *not* cosmetic. Without the strip, a
reconnect, a second instance of your own client, or two devices of the same user will
fail to parse that peer — and because the stripped value is also how you recognise
**yourself**, failing that check is what suppresses your own echo. Get it wrong and your
client either fights its own playback in a loop or broadcasts itself as a peer.

**2. Keep the identity JSON under 150 bytes, and shorten `deviceName` first.** The
truncation is a blind byte cut, not a JSON-aware one: a 252-byte identity came back as 150
bytes of *unterminated string* (`"deviceName": "MMM…` with no closing quote), which no
parser can read at all — that peer becomes permanently invisible and unidentifiable.
`deviceIdentifier` is a fixed UUID you cannot shorten, so budget from `deviceName`:
`"deviceName":"<model>"`, not the full marketing name.

Compact separators are worth using for exactly this reason — they saved 5 bytes on a
three-field identity (`54` vs `59`), which is real money against a 150-byte ceiling.

#### What real Plex clients actually put on the wire [LIVE]

Captured read-only from a genuine mid-playback session — Plex Web (Safari) on one side,
Plex for Android on a Sony BRAVIA television on the other. Both real identities, exactly
as the relay reported them **in the same room**:

```json
Plex Web / Safari
{"deviceIdentifier":"zzzzzzzzzzzzzzzzzzzzzz","deviceName":"Safari","userID":"1000001"}

Plex for Android TV
{"userID":"1000003","deviceIdentifier":"0000000000000000-com-plexapp-android",
 "deviceName":"BRAVIA VH1"}
```

This is the single most useful capture in this document, because it shows how much the
two shipped clients disagree while both working perfectly:

| | Plex Web (Safari) | Plex for Android TV |
|---|---|---|
| field order | `deviceIdentifier, deviceName, userID` | **`userID, deviceIdentifier, deviceName`** |
| `deviceIdentifier` format | 22-char base32-ish (`zzzzzzzz…`) | 16-hex + `-com-plexapp-android` |
| `deviceName` | `"Safari"` (the browser) | `"BRAVIA VH1"` (the TV model) |
| separators | compact | compact |
| `file` payload order | `ads` then `uri` | **`uri` then `ads`** |
| identity size | 82 bytes | 98 bytes |

Consequences:

* **"Never string-compare a username" is mandatory, not tidy.** The *same relay* held two
  clients whose identities differ in field order, identifier format, device naming, and
  payload ordering. Any client that string-matches will misidentify peers, and — because
  self-recognition is what suppresses your own echo — will fight its own playback.
* The relay does **not** normalise any of this; it stores and echoes each client's bytes
  as-is (consistent with the verbatim-echo finding above).
* **Compact separators are what real clients use** on the wire for both the identity and
  the `file` payload. Nothing pads to `json.dumps` defaults.
* At 82–98 bytes both real identities have headroom under the 150-byte cap; a longer
  `deviceName` ("Sony BRAVIA KD-55XG9500 4K HDR") would consume most of it, which is why
  `deviceName` is the field to budget.

This same **real shipped Android client emitted `Set{playlistChange}` with `files: []` and
`Set{playlistIndex}` with `index: null`** — i.e. the "shared playlist" messages the Plex
*web* client never sends are in fact used in production by the native Android client.
They are not dead protocol.

### 5.2 `Hello`

Client → server, immediately on connect:

```json
{"Hello":{
  "room":    {"name": "<roomID>"},
  "username": "<double-encoded identity>",
  "version": "1.6.4"
}}
```

Server → client [LIVE] — note four fields the client never asked for and doesn't parse:

```json
{"Hello":{
  "username":   "<identity>",
  "room":       {"name": "<roomID>"},
  "version":    "1.6.4",        ← echoed; what the CLIENT claims
  "realversion":"1.6.5",        ← what the RELAY actually implements
  "motd":       "",
  "features": {
    "isolateRooms": true, "readiness": true, "managedRooms": true,
    "chat": false, "maxChatMessageLength": 150,
    "maxUsernameLength": 150, "maxRoomNameLength": 36, "maxFilenameLength": 250
  }
}}
```

`version` is a *claim*, not a contract — 1.6.4 was accepted by a 1.6.5 relay with no
complaint. `realversion` is what to log and branch on. `readiness: true` is what enables
the lobby/ready flow; `chat: false` (and `maxChatMessageLength`/`motd`) are chat-related
and currently dead. Do **not** implement `isolateRooms`/`managedRooms` speculatively —
they're relay-side hints, not client obligations.

**On connect the relay pushes, in order:**

```json
{"Set": {"ready":           {"username": "<identity>", "isReady": null, "manuallyInitiated": false}}}
{"Set": {"playlistChange":  {"user": null, "files": []}}}
{"Set": {"playlistIndex":   {"user": null, "index": null}}}
{"Hello": {…}}
```

i.e. your own current readiness (null = never set), the room playlist, and the cursor.

### 5.3 `List` — roster snapshot

Request: `{"List":{}}`

Response [LIVE] — **nested by room name, then by username**:

```json
{"List": {"<roomName>": {"<identity>": {
    "position":  0,
    "file":      {},
    "controller": false,
    "isReady":   null,
    "features": {"sharedPlaylists": true, "chat": true,
                 "featureList": false, "readiness": true, "managedRooms": true}
}}}}
```

My earlier reading (flat `List` → user) was wrong. Note:

* `controller` — **dead. Do not use it.** [LIVE, resolved] In a real two-client session
  where the Android client was demonstrably driving playback (`setBy` = Android, `position`
  advancing every second), `controller` was `false` for **all three** sessions — the
  active controller, the passive Safari client, and my probe. It is also `false` after
  `Set{ready}`, and nothing in the web client references the field at all. There is no
  control-acquisition handshake to find: **control is implicit and emergent** — whoever
  last caused a state change is named by `setBy`, and that is the only control signal the
  protocol has.
* `features` is repeated per user *and* differs from the `Hello.features` for the same
  room (`chat: true` in `List`, `chat: false` in `Hello`). Relay inconsistency — ignore
  the feature flags, or take the union.
* `isReady` is tri-state: `null` (never reported) / `false` / `true`.

### 5.4 `Set` — everything stateful that isn't playback

**Client → server**

```json
{"Set": {"ready":          {"isReady": true, "manuallyInitiated": true}}}
{"Set": {"file":           {"name": "<double-encoded {ads, uri}>"}}}
{"Set": {"playlistChange": {"user": null, "files": [{"name": "…"}, …]}}}
{"Set": {"playlistIndex":  {"user": null, "index": 1}}}
```

* `manuallyInitiated: true` = the user pressed play (vs. the client deciding it has
  buffered enough). The relay stores and rebroadcasts it.
* `file.name` = double-encoded `{"ads":{"playing":bool,…}, "uri":"<sourceUri>"}`.

### 5.4a What the relay actually does with each write [LIVE]

Every `Set` write was exercised in a throwaway room, from **both** clients, since "the
sender sees its own write echoed" and "the write reached the peer" are different questions
(`docs/probes/writepathprobe.py`, `writepathprobe2.py`). The relay is a dumb store: it
echoes your value back to you *and* to every peer, and it validates almost nothing.

| Write | Returned to sender | Returned to peer | Validated? |
|---|---|---|---|
| `Set{file}` | `Set{user:{<you>:{room, file}}}` | same, verbatim payload | see below |
| `Set{ready}` | `Set{ready}` with `username` filled in | same | keys yes, values no |
| `Set{playlistChange}` | `Set{playlistChange}` with `user` filled in | same | no |
| `Set{playlistIndex}` | `Set{playlistIndex}` with `user` filled in | same | no |

**`Set{file}` — no schema validation, but a hard 250-byte cut.** The relay parses nothing;
it stores the string. Every one of these came back **byte-identical** to what was sent:

```
{"uri":…,"ads":…}   (Android key order)     {"ads":…, "uri":…}  (spaced separators)
{"ads":{…}}         (no uri at all)          {"uri":"not-a-uri"}
'{"uri":"server://x'  (truncated JSON!)
```

Only two things are rejected, and **silently — no error frame, the write just vanishes**:
an empty string, and a payload that does not start with `{`. Note the relay happily
broadcasts a `uri` of `"not-a-uri"` to peers; nothing downstream will tell you it is junk.

**`maxFilenameLength: 250` is a blind byte cut on the inner payload, and it breaks JSON.**
Swept:

| inner payload | comes back as |
|---|---|
| 133 B | 133 B, verbatim, parses |
| 233 B | 233 B, verbatim, parses |
| **273 B and up** | **exactly 250 B — unterminated string, `json.loads` raises** |

Identical failure mode to the 150-byte username cut (§5.1): past the limit a peer cannot
parse you at all. Budget check against real `sourceUri`s, wrapper included
(`{"ads":{"playing":false},"uri":""}` is 34 B, leaving **216 B for the URI**):

```
bare server://                        uri=101 B   inner=135 B   OK
provider://…/server://                uri=136 B   inner=170 B   OK
deep episode path + provider prefix   uri=156 B   inner=190 B   OK
```

Realistic URIs clear it, so this will not fire in practice — but it is a hard cliff with no
error, so a client should **measure the encoded payload and warn above ~200 B** rather than
discover it as a mysteriously unparseable peer.

**`Set{file}` lands in the roster.** After writing a file, `List` reports it under your
entry — so §5.8's "`file: {}` for a fresh session" is about sessions that never sent one:

```jsonc
{"deviceName":"BRAVIA VH1", "isReady":true,  "file":{"name":"{\"ads\":…,\"uri\":…}"}}
{"deviceName":"Safari",     "isReady":null,  "file":{}}
```

**`Set{ready}` is echoed with exactly three keys** — `username`, `isReady`,
`manuallyInitiated` — and unknown keys are dropped:

```
sent {"isReady":true,"manuallyInitiated":false,"bogusKey":42}
recv {"username":"…","isReady":true,"manuallyInitiated":false}      ← bogusKey gone
sent {"isReady":true}                       (no manuallyInitiated key)
recv {"username":"…","isReady":true,"manuallyInitiated":false}      ← defaulted, not null
```

`isReady: null` survives as `null` (tri-state is real, not just an omission artifact), and
`manuallyInitiated` is preserved verbatim — `true` stays `true`. Omitting it yields `false`,
never `null`. **Only send on change** (§6.4); the relay does not de-duplicate for you.

**The playlist messages are fully live, and they do round-trip `null`.** The doc's §5.4
shapes are all accepted and echoed to both clients with `user` filled in by the relay:

```
playlistChange {"user":null,"files":[]}       → files:[]        (preserved)
playlistIndex  {"user":null,"index":null}     → index:null      (preserved)
playlistIndex  {"user":null,"index":0}        → index:0         (0 not treated as absent)
playlistChange {"user":null,"files":[{"name":"<double-encoded>"}]} → verbatim, nested encoding intact
```

So §11 item 23's "explicit nulls rather than omitted keys" is confirmed as accepted, and the
Android client's shapes (§5.1) are first-class. Note the relay keeps **no** playlist state
of its own: there is no playlist field anywhere in `List`, and a reconnecting client gets
`files: []`/`index: null` back from the cloud-free relay. **A joining client must be handed
the playlist by another client, or it has none.**

**Server → client**

```json
{"Set": {"ready": {"username": "<identity>", "isReady": true, "manuallyInitiated": false}}}

{"Set": {"playlistChange": {"user": "<identity>", "files": [...]}}
{"Set": {"playlistIndex":  {"user": "<identity>", "index": 1}}

{"Set": {"user": {"<identity>": {
      "room": {"name": "<roomID>"},
      "file": {"name": "<double-encoded {ads,uri}>"},   ← present when a file was set
      "event": {"joined": true, "version": "1.6.4",      ← on join
                "features": {"sharedPlaylists": true, …}}
}}}}
{"Set": {"user": {"<identity>": {
      "room": {"name": "<roomID>"},
      "event": {"left": true}                            ← on leave
}}}}
```

Critical subtlety: **`Set.file` from a client comes back as `Set.user` with a `file` and
no `event`.** So `Set.user` is not only join/leave — it is also "this user's file
changed". A client that only handles `event.joined/left` will silently miss file changes.
Dispatch on the presence of `file` vs `event`, not on the message name.

### 5.5 `State` — the bidirectional 1 Hz sync heartbeat

`State` is the only message both sides send continuously. It is not a request/response
pair: the relay broadcasts on a 1 Hz timer *and* relays client `State`s.

Relay → client, exactly **once per second** (measured: `ping.latencyCalculation` deltas
of 1.000000 s):

```json
{"State":{
  "ping": {"latencyCalculation": 1791134198.23, "serverRtt": 0},
  "playstate": {"position": 0, "paused": true, "doSeek": false, "setBy": null}
}}
```

* `ping.latencyCalculation` is **server unix-epoch seconds** (`time.time()`).
* `ping.clientLatencyCalculation`, which the *client* sends, is **`performance.now()/1000`**
  — a monotonic relative clock. They are deliberately different fields because they are
  not comparable.
* `setBy` is filled in by the **server** and names whoever caused the last state change.
  `null` until someone does. Clients **never** set it — real clients send `"setBy": null`
  and let the relay assign the driver. Connecting to a live room does **not** grant you
  control: [LIVE] `controller` stayed `false` for the actively-driving client.

Client → relay. [LIVE, Safari Web Inspector, 131.2 s] **A real client sends exactly ONE
`State` per tick, ~1 Hz.** An earlier draft of this doc claimed two frames ~10 ms apart
from each client. That was a misread: the direction is not tagged in a Web Inspector WS
log, so it was inferred, and the inference was wrong.

The capture contains **two shapes, but they are not two roles — they are two directions.**
Split by `clientRtt`, which only a client ever populates:

| | `clientRtt` | `serverRtt` | `ignoringOnTheFly` | `setBy` | `position` (playing) | count |
|---|---|---|---|---|---|---|
| **Relay → you** (broadcast) | **absent 130/130** | present 130/130 | absent | server-assigned, names the driver | often `float` (extrapolated) | 130 |
| **You → relay** (heartbeat) | present | echoed | **both counters** | `null` | `int` | 138 |

The client frame:

```json
{"State":{
  "ping": {"clientLatencyCalculation": 2755.552, "clientRtt": 0,
           "serverRtt": 0, "latencyCalculation": 1791143688.112235},
  "playstate": {"doSeek": false, "paused": false,
                "position": 1804, "setBy": null},
  "ignoringOnTheFly": {"client": 0, "server": 0}}}
```

The relay broadcast, which is what every client actually consumes:

```json
{"State":{
  "ping": {"latencyCalculation": 1791143689.1127045,
           "serverRtt": 0.16222858428955078,
           "clientLatencyCalculation": 2756.3902396698},
  "playstate": {"position": 1806.0028346305862, "paused": false,
                "doSeek": false, "setBy": "{\"deviceIdentifier\":\"zzzzzzzzzzzzzzzzzz…\"}"}}}
```

The relay stamps `clientLatencyCalculation` into its own broadcast too — that field is a
shared heartbeat timestamp, not a purely client-side value. `serverRtt` and a
server-assigned `setBy` are the reliable tells that a frame came from the relay.

Relay behaviour on receiving an echo [LIVE]:

```json
{"State":{
  "ping": {"latencyCalculation": 1791143698.2830253,
           "serverRtt": 0.1694636344909668,
           "clientLatencyCalculation": 2765.5562961158753},
  "playstate": {…, "setBy": "<your identity>"},
  "ignoringOnTheFly": {"server": 1}}}           ← relay bumps this, and you must echo it back
```

#### You get your own `State` back — self-ignore is mandatory [LIVE]

The relay does **not** suppress your frames for you. A `State` you send comes back to
your own socket with `setBy` filled in as your identity, and the relay extrapolates
`position` in between your ticks.

Isolated in `docs/probes/selfecho.py`, one client alone in a throwaway room, no peers:

```
#0  paused=True  pos=0        doSeek=False setBy=<none>          ← relay's own tick
#1  paused=True  pos=0        doSeek=False setBy=SELF
#2  paused=True  pos=0        doSeek=False setBy=SELF
#3  paused=False pos=333.059  doSeek=True  setBy=SELF            ← the seek, echoed
#4  paused=False pos=333.055  doSeek=True  setBy=SELF            ← relay extrapolating
#5  paused=False pos=333.05   doSeek=True  setBy=SELF
...
#12 paused=False pos=333.088  doSeek=False setBy=SELF
13 of 14 frames carried MY OWN setBy.
```

* **Drop every frame whose `setBy` resolves to your own identity** before it touches your
  position, pause state, or drift calculation. This is not an optimisation: apply your own
  echo and you will fight yourself. Observed in the two-account run — the observer pinned
  itself at `pos=0` while its driver was at 100+, because every "remote" frame it applied
  was its own stale echo.
* **A `doSeek: true` you sent stays visible to you for several ticks**, and the relay's
  extrapolated `position` drifts *backwards* toward it (`333.059 → 333.036`). Both are
  consequences of the echo, and both disappear once you self-ignore.
* This corrects §7's original "0 inbound `doSeek` frames → sender gets no echo of its own
  seek". That count came from a capture with no peers, where every inbound frame was
  relay-owned. With a real echo present, the seek comes back 9 times over.

Consequences, all of which contradict earlier drafts of this document:

* **`ignoringOnTheFly` is always sent, with both counters, even when both are `0`.** An
  earlier version of this doc said "omit when 0" — that was inferred from my own probe,
  never observed in a real client. The probe omitted it; real clients do not.
* **You must echo the relay's `ignoringOnTheFly.server` counter back on your next tick.**
  [LIVE, root cause of a State stall — see §5.9] This is the single most important
  conformance rule in this document. The relay sets `server: 1` once it has applied your
  `State`; the real client copies that value into its next outbound frame. A client that
  hardcodes `server: 0` forever looks like it is talking over a message the relay already
  took, and the relay stops relaying within ~14 s. Handing the relay verbatim captured
  frames survives 131 s+ *for the same reason*: those frames carry whatever counter the
  relay last set.
* **Clients send `setBy: null`, they never name themselves.** The relay assigns it.
* `clientRtt` is a genuine measured round trip (~0.10–0.25 s once warm, `0` on the first
  frame of a connection).

#### `serverRtt` — RESOLVED: it is *your own* clock skew, not the relay's [LIVE]

**`serverRtt = relayNow − ping.latencyCalculation`, the value YOU sent.** Signed, and
**per-client** — a peer's bogus value does not touch it.

Swept by having one client vary only that field while a second client observed
(`docs/probes/rttprobe.py`):

| client sends `latencyCalculation` | its own inbound `serverRtt` | the peer's |
|---|---|---|
| fresh `time.time()` | `0.057` | `0.057` |
| `time.time() − 3600` | `+3600.06` | `0.057` |
| `time.time() + 3600` | `−3599.94` | `0.057` |
| `time.monotonic()` (~16.6) | `1791203064.20` | `0.057` |
| `0` | **frozen** at last good value | `0.057` |
| key omitted | **frozen** at last good value | `0.057` |

The second column is the whole field, and it reconciles every previously contradictory
observation:

* **Real sessions: `0.10`–`0.25`.** One-way transit plus the client's clock error. Your
  stamp is a few ms old when it lands, so a correct clock yields ~RTT/2.
* **Verbatim replay produced `~50510`.** The captured frames carried epoch stamps from
  hours earlier. Not the relay tolerating nonsense — it faithfully reporting staleness.
  **This is why the field looked broken.**
* **Frames before any client stamp showed `0`.** Nothing to subtract yet.
* The retracted claim was *structurally right and one field name off*: skew **is** what
  this measures, but against `latencyCalculation`, not `clientLatencyCalculation`.

So the earlier "do not compensate for clock skew on its strength" guidance was backwards,
and the field **is** load-bearing for §6.1. Two obligations follow:

* **Send a fresh epoch `latencyCalculation` on every outbound tick.** Send `0`, omit the
  key, or send monotonic and `serverRtt` freezes — or goes to epoch scale — and §6.1's
  skew correction then reads garbage.
* **Never gate on `serverRtt` from another client.** It is per-recipient, so it says
  nothing about the room or your peers.
* Relay-suppressed states were observed with `ignoringOnTheFly.server: 1` and
  `{"client":1,"server":1}` and `{"server":1}` — the relay mirrors your `client` counter
  and ORs in its own.

**`position` advances in ~1 s steps, but the steps are irregular.** [LIVE] 14 consecutive
`State` messages from a real playing session:

```
3138.107  3139.010  3139.982  3140.982  3142.179  3143.100  3144.057
3145.015  3145.974  3147.176  3148.176  3149.132  3150.053  3151.010
deltas: 0.90 0.97 1.00 1.20 0.92 0.96 0.96 0.96 1.20 1.00 0.96 0.92 0.96
```

The `State` messages themselves arrive at a metronomic 1.000000 s, but the *position
values* step by 0.90–1.20 s. The advance tracks the driving client's own `State` echo
cadence, not a uniform server timer. Two implications:

* **Never derive position by assuming one second elapsed per `State`.** Integrate against
  your own monotonic clock; treat the server position as a sampled correction.
* **Your echo cadence is everyone else's smoothness.** Because the room's position is
  effectively "last reported position, extrapolated by the reporter's rhythm", a client
  that echoes slowly or irregularly injects jitter into every peer's drift calculation.
  Echo at a steady 1 Hz.
* **`position` is a JSON number that changes type depending on who sent it and whether
  playback is running.** [LIVE, 131.2 s capture]

  | Frame | Playing | Paused |
  |---|---|---|
  | Relay broadcast (what you consume) | `float` — `1806.0028346305862` (115/115) | `int` — `1804` (15/15) |
  | Your own outbound frame | `int` — `1804` (116/116) | `int` — `1804` (15/15) |

  (The 116 + 15 breakdown splits the outbound frames by playstate; the `138` total in the
  direction table above counts every outbound `State` in the capture. They are two
  different groupings of the same capture, not two different totals.)

  Send an `int`; expect a `float`. The relay's float is its own extrapolation between
  your reports, which is why it advances by 0.90–1.20 s per 1.000000 s tick. Always parse
  inbound as float and never truncate. Do not assume a type — the same field is an `int`
  in one frame and a `float` in the next.

### 5.6 Seeking — `doSeek: true`

[LIVE] First real `doSeek: true` ever captured. Two seeks in one session, both from the
driving client, one client frame each:

```
t=13.22  OUT  pos=1753  paused=false doSeek=true setBy=null    clientLatencyCalculation monotonic
t=14.23  OUT  pos=1723  paused=false doSeek=true setBy=null    clientLatencyCalculation monotonic
```

Observed rules:

* A seek is `doSeek: true`, `paused: false`, and `position` set to the **seek target** —
  not a delta, not an offset.
* The client sets its own position immediately: `1800 → 1753 → 1723`. After the second
  seek the position is *behind* where it was, which is exactly why `doSeek` exists as a
  separate flag: **the flag is the command, `position` alone is only a report.**
* `doSeek: true` is **not** sticky — it appears on exactly one tick, then reverts to
  `false`. You may miss it if you poll slower than 1 Hz.
* `paused` and `doSeek` are independent: seeks were observed with `paused: false`.
* ~~**The relay does not echo `doSeek: true` back.**~~ **CORRECTED [LIVE] — it does.** The
  original reading came from a capture where the seeking client had *no peers*, so every
  inbound frame was relay-owned and none carried `setBy`. Isolated in
  `docs/probes/selfecho.py`: a **lone** driver that seeks to 333 receives its own seek back
  as `doSeek: true` on **9 consecutive frames**, `setBy` = its own identity, with the relay
  extrapolating between them (`333.059 → 333.055 → … → 333.036`). See
  §5.5 above ("You get your own `State` back") — the sender *does* receive an echo.
* **Consequence: self-ignore is mandatory, not optional.** Any frame whose `setBy` parses
  to your own identity must be dropped before it touches your position. A client that
  applies its own echo fights itself: in the two-account run the observer sat pinned at
  `pos=0` while its driver was at 100+, because every applied "remote" frame was its own.
* **Filter on `setBy` — never on `ignoringOnTheFly`.** The relay's
  `ignoringOnTheFly.server` is not a frame-ownership signal: §6.3 has the real client
  treating `ignoringOnTheFly.server > 0` as one of the reasons to *apply* server state.
  A probe that gated its apply path on `not ig` threw away genuine remote frames on every
  tick where the counter was set, so its observer stayed at `0` even after self-ignore was
  correct. Fixed in `docs/probes/twoclientprobe.py` (`is_self()`); see §11.14's re-run.
* Because the flag lives for one tick, a client whose drift correction runs at 1 Hz must
  evaluate `doSeek` on the frame it arrives and not on a coalesced "latest state" struct,
  or backward seeks will silently be ignored.
* **Verified end-to-end.** A two-client probe where A seeks to 900: B received
  `pos=900 doSeek=True setBy=BRAVIA VH1`, held 900 on the following tick, then saw
  `doSeek:False`. So `doSeek` propagates to peers, and — per the correction above — the
  sender gets it back too, so self-ignore it.

### 5.7 Suppression counters

Two counters, and both must be sent and both must be honoured:

| Counter | Set by | Meaning |
|---|---|---|
| `ignoringOnTheFly.client` | client | "I deliberately overrode this; don't rebroadcast my input" |
| `ignoringOnTheFly.server` | relay | "I applied your last message" — **mirror this back verbatim** |

**The `server` counter is a handshake with the relay, not just a hint.** It is the one
field a client gets *wrong* in a way that silently kills the stream. See §5.9.

Observed relay limits worth knowing:

* A `State` sent with `ignoringOnTheFly.client: 1` was **not propagated to the peer** — the
  peer kept its previous position. With `client: 0` the same position propagated. So
  `client: 1` means "apply this to me but do not tell anyone", which is the mechanism you
  want for a local-only correction (drift nudge) that should not be mistaken for a user
  command. It is not an eviction signal and the relay does not drop your session.
* **`List`'s per-user `position` is useless.** It stayed `0` for every user in a real
  session whose actual playback position was **3151 s and climbing**. The relay does not
  fold `State.position` into the roster it reports, for anybody. Read playback position
  from `State`, never from `List`.
* **The relay's `position` arithmetic is reproducible and benign** [LIVE, `posprobe.py`]:
  paused round-trips exactly, playing extrapolates your last report to now (±0.08 s for an
  advancing client). The earlier "relative position came back epoch-scale" reading did not
  reproduce at any magnitude tested and is retracted. **You still must keep your own
  estimate and re-send it every tick** — you are the source of truth when paused — but you
  do not need to guess at hidden relay state to do it.

### 5.8 Session lifecycle — joins, leaves, and what survives

All [LIVE], in a throwaway room with three concurrent sessions.

**Joining is not exclusive and duplicates are not evicted.** Three sockets presenting a
*byte-identical* identity all stayed connected simultaneously (`alive=True` for all
three). The relay does not kick the older session; it just extends the key with `_` (§5.1).
Practical consequences:

* A client reconnecting without closing its old socket leaves a **ghost session** that
  still appears in the roster and never emits `left`. Close your socket before reconnecting.
* Because ghosts are indistinguishable from real peers in the roster, keying your UI on
  the stripped identity will show duplicate rows. Key on the raw key.

**Peers are notified of a clean close:**

```json
{"Set":{"user":{"<identity>":{"room":{"name":"<roomID>"},"event":{"left":true}}}}}
```

This fires on a proper WebSocket close frame **and also on an abrupt socket close with no
Close frame at all — peers see it in ~0.2 s either way** (§11.13). So transport death is
reliable. What the relay cannot see is *silence on a live socket*: that waits out the
13.21 s timer above. Reap ghosts locally anyway — a process that hangs with its socket
open is indistinguishable from a healthy peer for the first 13 seconds.

**Per-user state does NOT survive a disconnect.** After a session disconnected and a new
one presented the same identity:

* the peer received `left: true`, then `joined: true`;
* the new session's `List` entry showed `isReady: null`, `file: {}`, `position: 0` — a
  clean slate, not the previous session's values;
* readiness, file, and playlist state are **per-connection, not per-user**.

So a reconnecting client must **re-announce its whole state** — `Set{file}`,
`Set{ready}`, playlist — or it will sit in the room silently out of sync with peers that
remember it. Conversely, do not assume the room remembers you just because your `userID`
matches.

**Rooms are ephemeral at the cloud layer.** A room is created by `POST /rooms` and is
hard-capped at three hours (§4); after that it is gone and reads `404`. The relay, having
no room table, does not enforce this — it will happily serve a room name forever, so a
stale-but-live socket and a stale-but-dead room ID are different failure modes and your
UI has to handle both.

**A non-echoing client is evicted after 13.21 s / 14 messages; a conforming client is
not.** [LIVE, `evictprobe.py`.] The timer runs against *your last outbound* `State`, so it
restarts on every tick you send — sending nothing means eviction on the 14th relay frame.
A client that connects, sends `Hello`, and then only reads receives `State` at 1 Hz for
exactly **14 messages / 13.21 s**, and is then subjected to:

```json
{"Set":{"user":{"<your own identity>":{"room":{"name":"<roomID>"},
                                       "event":{"left":true}}}}}
```

after which its `State` stream stops permanently — while its TCP/TLS socket is still open
and still pinging. So the relay has **two distinct "this client is gone" signals, both the
same `Set{user}{event:left}` frame**: one for transport death, which fires in ~0.2 s on
socket close (§11.13), and this one, for a *live but silent* socket, which waits out the
13.21 s timer. Neither is triggered by your own socket closure alone reaching you — you
cannot hear your own departure once you are gone. Practical consequences:

* **`left: true` against your own key is advisory, not a death certificate.** A replay
  of 138 verbatim captured frames received its synthetic `left:true` at the end of the
  run *and kept receiving `State` afterwards*. Keep reading the socket and let actual
  frame flow decide whether you are still live. (Against a *peer's* key it is far more
  useful: transport death reaches peers in ~0.2 s, §11.13.)
* **Echoing `State` *does* keep you alive — but only if you mirror
  `ignoringOnTheFly.server`.** The original matrix
  (`docs/probes/staterevivebisect.py`, fresh room per case, 40 s each) is what produced
  the "echoing makes it worse" reading, and it is now known to be **an artifact**: every
  row used a client that hardcoded `server: 0`. Re-run under the corrected rule:

  | clients | who echoes | mirrors `server` | States received | outcome |
  |---|---|---|---|---|
  | 1 | nobody | — | 14 | evicted @13.7 s |
  | 1 | itself, @1 Hz | no | 2 | silent @14.7 s |
  | 1 | itself, @1 Hz | **yes** | **75+** | **survived** |

  Two things fall out, and the first is a correction of an earlier reading of this
  document:

  1. **The heartbeat is a liveness signal, gated on the `server` counter.** Once the
     client echoes back the suppression counter the relay set, a single client sustains
     the 1 Hz stream indefinitely (verified 75 s+, `per5s` steady, no gaps). Do not
     hardcode `server: 0`.
  2. **With two clients both mirroring, both survive the whole run.** The corrected
     two-client probe ran 28 s end-to-end with `stopped=False` on the surviving client
     and a clean `left:true` for the peer that disconnected mid-run — which is the
     expected `left` shape, not a mute.
* **The old "our guessed echo is not good enough" blocker is resolved.** It was not a
  shape problem at all. Replaying 147 verbatim captured frames worked because those frames
  carried the relay's last `ignoringOnTheFly.server` value; the hand-built echo failed for
  the same single reason. Field names, types, and handshake `Set`s were all fine.
* The 14 s window is the maximum length of a **purely passive** observation. Any longer
  capture must echo `State`, which makes it a writer, not a reader.
* Because the socket stays open after a *silence* reap, a client that treats "I got
  `left` for myself" as "reconnect" will reconnect, be reaped again, and spin. Detect
  `event.left` where the key equals your own stripped identity and treat it as advisory,
  not as a peer departure. Keying on the raw key (§5.1) is what lets you tell the two
  signals apart.

### 5.9 The `ignoringOnTheFly.server` stall — root cause

**This was the last hard blocker on the protocol. It is a one-field bug, and it is worth
recording in full because it was invisible to every inspection-based approach.**

The symptom: a hand-built client echoing a perfectly well-formed `State` at 1 Hz received
2–3 relay `State` frames and then went silent, forever, socket open, pinging. It looked
exactly like the relay muting a client it did not recognise as conforming.

Three layers of evidence, in the order they arrived:

**1. Verbatim replay worked.** `replayprobe.py` fed the relay 147 captured frames
unmodified — 138 `State` — and received all 138 back, steady 1 Hz, for the full 131.2 s of
the original capture. So the *content* of a `State` was never wrong. That killed the shape
hypothesis: field names, types, `setBy: null`, `clientRtt`, the missing second variant,
all fine.

**2. Handshake bisect ruled out the handshake.** `handshakebisect.py` runs 8 handshakes
concurrently, each in its own room, 25 s each. If the handshake were the variable, some
variant would have diverged:

```
baseline               STALL  2 States  last t=1.1s
manual:false           STALL  3 States  last t=1.4s
false-then-true        STALL  2 States  last t=1.2s
null-ready-first       STALL  3 States  last t=1.3s
+Set.user              STALL  3 States  last t=1.4s
+playlist pair         STALL  3 States  last t=1.3s
full (capture order)   STALL  2 States  last t=1.1s
no ready at all        STALL  3 States  last t=1.3s
```

All eight identical, including the one replaying the capture's exact order. Re-running two
of them serially rather than concurrently gave the same numbers, so it was not a load
artifact.

**3. Two body variables were also innocent.** `clientLatencyCalculation` scale (`time.monotonic()`
≈ 0.007 vs Safari's `performance.now()/1000` ≈ 2755) and starting position (0 vs 1800)
both changed nothing.

**What was left was the one field the tests never varied.** The probe hardcoded
`ignoringOnTheFly.server: 0` on every frame. The relay sets `server: 1` once it has applied
your `State`, and a real client copies that number into its next outbound frame. Two
clients differ in exactly this:

```
server counter always 0    STALL  last inbound t=14.2s
server counter echoed     OK     last inbound t=23.2s
```

And for the record, the reading is not subtle in the raw timeline. Across the stalled run,
B's inbound `setBy` sequence is:

```
BRAVIA x6 -> Safari -> BRAVIA -> Safari -> BRAVIA -> Safari -> BRAVIA -> Safari x12
```

A's playstate alternates `100/102/104` against `paused:True pos=0`, because both clients
are shouting their own state at each other while the relay tries to apply each other's.
That alternation is the shape of a relay that believes it is being talked over.

**A second bug, found while verifying the fix: `sendall()` is not thread-safe.** The
probe's keepalive thread wrote a `State` every second while the main thread wrote
`announce()`/`List` on the same TLS socket. Interleaved partial writes corrupt the frame
stream and the relay silently drops the session — observed as one client receiving *zero*
inbound frames in 2 of 5 runs. Serialising sends behind one lock: 0 failures in 5 runs, and
two clients in one room now hold steady 1 Hz together (5/5, ~48–56 inbound frames each over
18 s). Not a relay quirk, a probe bug — but it will bite any client with a background
heartbeat, which is the shape of this whole feature.

**Rule, stated plainly:**

```python
# state you receive from the relay
self.relay_ignore = state.get("ignoringOnTheFly", {}).get("server", 0)

# every frame you send, on every tick
"ignoringOnTheFly": {"client": self.local_ignore,   # 1 = local-only, don't rebroadcast
                     "server": self.relay_ignore}   # mirror it back, verbatim
```

Never initialise `relay_ignore` to `0` as a default you then leave alone. It is a live
value read from the wire every tick. Verified after the fix: single client 75 s steady, and
the two-client probe runs end-to-end with drive, pause, and seek all propagating.

---

## 6. The sync algorithm

### 6.1 Latency compensation

```
send:   ping.clientLatencyCalculation = performance.now()/1000     # monotonic seconds
recv:   clientRtt = now_s - ping.clientLatencyCalculation         # real RTT/2-able
        skip sample if clientRtt < 0 or ping.serverRtt < 0
        if averageRtt == 0: averageRtt = ping.serverRtt
        averageRtt       = 0.85*averageRtt + 0.15*clientRtt        # EMA
        lastForwardDelay = averageRtt/2
        if ping.serverRtt < clientRtt:
            lastForwardDelay += clientRtt - ping.serverRtt          # clock-skew correction
```

`serverRtt` **is** a clock-skew measurement and this correction is legitimate: it is
`relayNow − the latencyCalculation you sent` (§5.5), so it measures your clock's error plus
one-way transit. It is only garbage if you stop stamping a fresh epoch `latencyCalculation`
each tick. Skew correction is per-client, which is correct — skew is a per-client property.

### 6.2 Target position + drift correction

```
target = serverState.position + (0 if paused else lastForwardDelay)
diff   = localPosition - target

if diff >=  4.0  or  diff <= -1.75 :  seek(target)
elif diff >   1.5                 :  tempo 0.95      # gentle catch-up, pitch preserved
else                               :  do nothing (drift)
```

The 0.95 is a **tempo** change, not a playback-speed change (§9).

### 6.3 Foreground vs background

```
shouldApplyServerState = (player NOT in foreground) OR ad.isPlaying OR ignoringOnTheFly.server > 0
```

`ignoringOnTheFly.server > 0` means the relay already applied your last message, so it
expects no action from the current frame. Reading it here is independent of the separate
duty to **echo it back** on your next outbound frame (§5.9) — do both.

* **Foreground** (user is watching): send your own playstate, *apply* the server's.
* **Background** (e.g. sitting in the lobby): *send* your playstate, *ignore* the server's.

This is what stops a lobby-idle client from hijacking a foregrounded peer's playback.
Local play/pause/seek set `hasPendingPlayPause` / `hasPendingSeek`, which makes the next
outgoing `State` carry local intent and bumps `ignoringOnTheFly.client`.

### 6.4 Ready / lobby state machine

```
isReady = (no ad playing) AND (hasInitialBuffer)
hasInitialBuffer = canPlayThrough  OR  (position + 5s) inside a bufferedRange
```

`Set{ready}` is sent **only on change**. On join you start at the remote position:
`startOffsetMilliseconds = round(1000 * remotePosition)`, `isPaused: true`, so the whole
room joins paused at the host's position and then un-pauses together.

Lobby visibility (from the web client):

* Show when a remote user is in an ad break, or when you haven't pressed play and a remote
  is already playing.
* Hide when all remote users are ready and present, or when you are the ready one.

---

## 7. Live verification log

```
GET https://together.plex.tv/rooms                 → 200, real room returned
GET https://together.plex.tv/rooms/ca8cfezmke4     → 200
GET https://together.plex.tv/rooms/doesnotexist123 → 404  "room not found not found!"
GET https://together.plex.tv/rooms   (no token)    → 401  "You must provide a token!"

wss://pop-fra00.syncplay.plex.services:7776/ws     → 101, AutobahnPython/21.3.1
                                                     relay realversion 1.6.5
                                                     unsolicited empty PING on connect
                                                     State cadence exactly 1.000000 s

Auth / authorization probes on the live relay:
  no Plex credentials at all .................. 101 + working session   ← NO AUTH
  userID of a NON-member (999999999, fabricated) ..... joined fine             ← NO MEMBERSHIP CHECK
  bogus room id "zzzzzzzzzz" .................. room created, worked    ← NO ROOM TABLE

Username-key probes (throwaway room, 4 concurrent sessions):
  54-byte compact identity ..................... echoed verbatim
  59-byte spaced identity ...................... echoed verbatim (NO padding)
  117-byte identity ........................... echoed verbatim
  252/257-byte identity ........................ truncated to 150 → invalid JSON
  same identity ×3, concurrent ................ keys gained _ , __ , ___   ← NO EVICTION

Identity echo test:
  compact separators in  -> compact separators out  ← relay does NOT re-serialise

Lifecycle probes (throwaway room):
  clean close (CLOSE frame) .................... peers got {"event":{"left":true}}
  disconnect then reconnect, same identity ..... isReady:null, file:{}, position:0
                                                      ← per-CONNECTION state, NOT restored

Cloud room expiry (real room, observed to its natural end):
  GET /rooms  while room active ............... 200, room listed
  GET /rooms  after endsAt ..................... 200, {"rooms":[]}
  GET /rooms/ca8cfezmke4 after endsAt .......... 404 "room not found not found!"

Two live rooms, same account, different topology:
  room ca8cfezmke4 → pop-fra00.syncplay.plex.services:7776
  room 1kp69st72evn → pop-atl01.syncplay.plex.services:7777   ← different PoP AND port

Real-client capture (read-only, 14 State messages, live room 1kp69st72evn):
  Plex for Android TV identity as reported by the relay:
    {"userID":"1000003","deviceIdentifier":"0000000000000000-com-plexapp-android",
     "deviceName":"BRAVIA VH1"}                                        98 bytes, compact
  its file payload: {"uri":"server://…","ads":{"playing":false}}   ← uri before ads
  it sent Set{playlistChange}{files:[]} and Set{playlistIndex}{index:null}
  server State carried serverRtt: 0 and setBy = that client, paused:true, position:0

Idle-eviction probe (throwaway room, zero State echoes, repeated twice):
  State received at 1Hz for exactly 14 messages / ~13.9s
  then: {"Set":{"user":{"<own identity>":{"event":{"left":true}}}}}
  then: no further State, socket still open, still ponging

Plex Web capture (read-only, Safari Web Inspector, 294 lines / 131.2s sustained):
  split by clientRtt: absent 130/130 (relay→you) · present (you→relay)
  you→relay is ONE frame/tick ~1Hz, NOT two frames 10ms apart
  relay stamps clientLatencyCalculation into its own broadcasts too
  first real outbound doSeek: {doSeek:true, paused:false, position:<absolute target>}
  0 inbound doSeek frames → WRONG, see the correction at the end of this log

Verbatim replay (throwaway room, 147 captured frames fed back unmodified):
  138 State frames selected after filtering relay-owned traffic
  inbound: 138 States, steady 1Hz, full 131.2s           ← frame CONTENT is correct
  got a synthetic {"event":{"left":true}} at the end AND kept receiving State after
  stale clientLatencyCalculation → inbound serverRtt ~50510, still accepted

Handshake bisect (8 concurrent handshakes, own throwaway room each, 25s each):
  baseline / manual:false / false-then-true / null-ready-first /
  +Set.user / +playlist pair / full capture order / no ready at all
  → ALL 8 stalled identically, last inbound State 1.1-1.4s   ← handshake is NOT the cause
  re-ran 2 serially: same numbers, not a concurrency artifact

The actual bug — ignoringOnTheFly.server (single variable, throwaway rooms):
  hardcoded {"client":0,"server":0} forever ....... STALL, last inbound 14.2s
  mirror relay's last server value ............... OK,   last inbound 23.2s
  confirmed long: single client 75s, steady 1Hz, per5s no gaps
  frame-body controls that changed nothing:
    clientLatencyCalculation ~0 vs ~2755 · starting position ~0 vs ~1800

Two-client steady-state check (fresh room each, 18s, both mirror the counter):
  5/5 runs both clients OK, ~48-56 inbound frames each, steady 1Hz
  → found+fixed a second bug: unsynchronised sendall() from two threads (see §5.9)

Corrected two-client probe, end to end (~30s, throwaway room, stable over 4 runs):
  Q1 controller=False for BOTH clients (dead field; setBy is the only signal)
  Q2 B sees A drive 100→102→104, setBy=BRAVIA VH1           ← drive propagation
  Q3 B sees A pause → paused:True                            ← pause propagation
  Q4 A seeks to 900 → B sees pos=900 doSeek=True then False ← seek propagation
  Q5 A sets ignoringOnTheFly.client=1 → peer does NOT see it  ← client:1 = local-only
  Q6 A disconnects → B gets {"event":{"left":true}}          ← expected shape
  Q7 B drives alone → setBy becomes B

serverRtt sweep (rttprobe.py, two clients, throwaway room, A varied / B observed):
  A sends fresh epoch ............ A: 0.057        B: 0.057
  A sends epoch - 3600 ........... A: +3600.06     B: 0.057
  A sends epoch + 3600 ........... A: -3599.94     B: 0.057
  A sends monotonic (~16.6) ...... A: 1791203064.20   B: 0.057
  A sends 0 ...................... A: FROZEN at last value
  A omits the key ................ A: FROZEN at last value
  → serverRtt = relayNow - A's own latencyCalculation, signed, PER-CLIENT

Relay write path (writepathprobe.py + writepathprobe2.py, two clients, throwaway room):
  Set{file} -> echoed to sender AND peer, byte-identical, 0 validation
    "uri":"not-a-uri" .......... stored & rebroadcast
    {"ads":{...}} no uri ....... stored & rebroadcast
    '{"uri":"server://x' ....... truncated JSON stored & rebroadcast
    "" and non-"{" ............. dropped SILENTLY, no error frame
  Set{file} size vs features.maxFilenameLength (250):
    inner=133 B -> 133 B verbatim, parses
    inner=233 B -> 233 B verbatim, parses
    inner=273 B -> 250 B, UNTERMINATED STRING, json.loads raises
    ...every length above 250 behaves identically
    real sourceUri encoded = 135-190 B, so the cliff is not hit in practice
  Set{ready} -> normalised to exactly {username, isReady, manuallyInitiated}
    unknown key "bogusKey" ..... DROPPED
    no manuallyInitiated ....... defaulted to false, never null
    isReady: null .............. preserved as null (tri-state is real)
    manuallyInitiated: true .... preserved verbatim
  Set{file} appears in List under the writer's entry; no playlist field exists in List
  playlist messages round-trip fully, nulls and index:0 included, nested encoding intact
  relay keeps NO playlist state: reconnecting session gets files:[]/index:null back
```

Consequences, and they matter to any implementer:

1. **A Watch Together room ID is a bearer secret.** There is no token on the socket. Any
   client that can reach the relay can join a room and control playback. Room IDs appear
   in URLs, browser history, logs and screenshots, so treat them as sensitive — and do
   not log them at `debug` level in your client.
2. Do **not** invent your own transport security. There is nothing to hold.
3. The relay is reachable directly by hostname. Any hardcoded IP would be wrong; always
   use `syncplayHost`/`syncplayPort` from the room record.
4. The relay accepts **fabricated** `deviceIdentifier`/`userID`. That is how the
   identity-based `setBy` self-ignore works, but it also means you cannot trust a peer's
   claimed identity. Nothing should depend on it.
5. Because there is no membership check, **a room ID leaked from a log or a screenshot is
   enough to hijack a viewing session.** This is the single biggest risk of implementing
   this protocol, and it is Plex's design, not yours. Re-confirmed against a **real**
   cloud-issued room: a third client claiming `userID 999999999` — in nobody's `users[]` —
   completed the handshake and appeared in the roster next to the two legitimate accounts
   (`docs/probes/realroomprobe.py`). The relay never consults the room record.
6. **`DELETE /rooms/{id}` is not a kill switch** [LIVE]. It is **"leave the room"**: it
   removes only the caller from `users[]`, so the other participants still read `200` and
   the room is still listed. There is **no destroy-for-everyone** — a second `DELETE` is
   `404`, and rooms really end only at `endsAt`. On top of that the relay has no room
   table and happily serves the same name, so **anyone already holding the ID keeps their
   session and new clients can still join.** There is no server-side kick anywhere in this
   protocol. Treat `DELETE` as *leaving*, and never as "this session is now over".

Probe hygiene: only `Hello` + `List` + `pong` were ever sent to the real room
`ca8cfezmke4`, which was idle and paused at position 0. All relay write-path tests
(`Set{ready}`, `Set{file}`, `Set{playlistChange}`, `Set{playlistIndex}`, `State` echo)
and all multi-session/identity/expiry probes were run in throwaway rooms named
`zzzzzzzzzz` / `wt<random>`, which the relay creates on demand and which the cloud never
knew about. **No live session was ever joined, paused, seeked or modified.**

The exceptions, all against rooms the probes created themselves: the *cloud* write path
(`POST`/`invite`/`PATCH`/`DELETE`) and then the two-account authorisation matrix. Invited
users were `1000002` (`libraryuser`) — to confirm a userID resolves to a profile and to
serve as the non-host participant — plus, once, `1000004` (`stranger`) as the
relationship-gate stranger (§11.9). Those are the **only** accounts ever invited or named,
all approved in advance. `libraryuser` `DELETE`/`PATCH`-ed a probe-created room but never
joined a relay socket and never had access to the source library. `stranger` was invited
but never joined any room, relay or otherwise (invite returns `400`, see §11.9). No third
party's room was touched, and no `users` array ever contained an id the probes had not
been explicitly authorised to use.

All three tokens live in `~/.plex-probe-token-host`, `~/.plex-probe-token` and
`~/.plex-probe-token-nonfriend`, mode `0600`, read by the probes from disk — never passed
as argv, never committed.

PMS probes (invalid token, for contrast):

```
/:/watchTogether → 404     /:/syncplay → 404     /:/groupSessions → 404
/watchTogether   → 403     /:/timeline  → 401 (control)
```

Cloud write path (REAL cloud, throwaway room, deleted afterwards — 2026-10-05):
  POST   /rooms  {sourceUri,title,users:null}         → 201, full Room, id returned
  GET    /rooms                                       → 200, listed
  POST   /rooms/{id}/invite  {users:[1000002]}         → 200, Room with users[] = 2
  PATCH  /rooms/{id} {title:renamed}                   → 200, title changed  ← NOT dead code
  PATCH  /rooms/{id}?title=renamed  (query param ALONE)     → 500 Node error, ignored (§4)
  DELETE /rooms/{id}                                   → 204, empty
  DELETE /rooms/{id}  (no token)                       → 401, room SURVIVES
  DELETE /rooms/{id}  (bogus token)                    → 401, room SURVIVES
  DELETE /rooms/doesnotexist123                        → 404 "room not found not found!"
  freshly created room: endsAt-startsAt = 10800        ← 3h, confirmed again

After DELETE — the important part:
  GET    /rooms/{id}          → 403 "you do not have access to that room"  (×3, stable)
  POST   /rooms/{id}/invite   → 403 "you do not have access to that room"
  GET    /rooms               → 200 {"rooms":[]}
  relay wss://pop-fra01:7777 with the DELETED room id  → 101, full working session
                                                          ← DELETE does NOT revoke the relay

Two-account authorisation matrix (REAL cloud, 2026-10-05 — `docs/probes/authzprobe.py`):
  accounts serverowner 1000001 (creator, Plex Pass Active)
          libraryuser   1000002 (invited participant, subscription **Inactive**)

  peer is *not* in the room yet:
    GET    /rooms/{id}          → 403 "you do not have access to that room"
    DELETE /rooms/{id}          → 404 "room not found not found!"   (room SURVIVES)
    PATCH  /rooms/{id}          → 500 Node leak, see §4              (crashes pre-authz)
  host invites peer:
    POST   /rooms/{id}/invite  {users:[1000002]}  → 200, users[] = 2
  peer is now in the room:
    GET    /rooms/{id}          → 200
    GET    /rooms               → 200, lists the room
    PATCH  /rooms/{id} {title}  → 200, title CHANGED      ← not host-gated
    PATCH  /rooms/{id} {sourceUri:…/99999999} → 200, sourceUri REPOINTED
    POST   /rooms/{id}/invite  {users:[999999999]}  → 400 Bad Request   ← absent target,
                                                             not role (§11.9); relationship
                                                             vs validity needs a stranger id
    DELETE /rooms/{id}          → 204 … and the room SURVIVES for the host (200 + listed)
  symmetric reverse: creator's DELETE → 204, creator 403, **peer still 200**
    second DELETE by the same caller → 404 "room not found not found!"
  peer leaves, host re-invites → 200, peer back to 200   ← leaving is reversible
  PATCH with no body → 500 "Cannot destructure property 'sourceUri' of 'req.body' as it is
    undefined."                                                        ← Node internals leak

Subscription flags are NOT a Plex Pass gate:
  serverowner  Active    → ['watch-together-20200520','watch-together-invite']
  libraryuser     Inactive  → ['watch-together-20200520','watch-together-invite']  ← same

Real two-account relay session (REAL cloud room, re-run 2026-10-06 — `docs/probes/realroomprobe.py`):
  room 1w7ut63c1zjf created by serverowner, libraryuser invited, both clients joined
  the relay from the record: pop-fra01.syncplay.plex.services:7777
  startsAt/endsAt 1791209779 -> 1791220579                       ← 3.0 h, cloud-enforced
  re-GET the room mid-session → same host:port                    ← STABLE for the room

  relay has NO view of the cloud record:
    third client claiming userID 999999999 (in nobody's users[])
      → HTTP/1.1 101 Switching Protocols, roster shows ['BRAVIA VH1','NotInUsers']
      ← a fabricated identity joins a REAL room alongside real accounts
    roster entry userID field → None for every user, including real accounts
      ← the relay stores only the identity string we sent; no plex.tv profile lookup

  playstate propagation between two real accounts DID work (A drove 100..104, B saw each
    as setBy=BRAVIA VH1; A's seek to 900 arrived as doSeek=True; A's pause arrived).
  …but B's own frames came back to it (setBy=libraryuser, pos=0), pinning B at 0 while A
  was at 100+. That is the self-echo problem in §5.5, and it is why the probe's own
  verdict line ("self-ignore works with real accounts") was wrong — B did receive A's
  frames *and* its own, and the probe applied both. Self-ignore is what separates them.

  Re-run after fixing both probe bugs (`twoclientprobe.py` gained a real `is_self()` drop
  keyed on the identity it sent, and `realroomprobe.py` no longer counts propagation as
  proof of self-ignore):

    R3a  frames A authored that B saw: 14   (propagation, not self-ignore)
    R3b  frames B self-ignored (own echo): 7 of 21 inbound
    R3b  B applied position after driving: 900 (A was at 900.0)
         ← was 0 before the fix; B now tracks A

  **The probe's second bug was worse than the first.** Its apply path read
  `elif not self.driver and not ig:` — dropping frames while the relay's
  `ignoringOnTheFly.server` was set. That flag is not a "this frame is mine" signal at
  all: §6.3 shows the real client treats `ignoringOnTheFly.server > 0` as one of the
  reasons to *apply* server state. So the probe discarded legitimate remote frames on
  every tick where the counter was set, leaving `applied` stale even with self-ignore
  correct. **Filter on `setBy`, not on `ignoringOnTheFly`.** `ignoringOnTheFly` is a
  send-side duty (§5.9) and a foreground/background gate (§6.3); it says nothing about
  frame ownership.

Self-echo, isolated (single client, no peers — `docs/probes/selfecho.py`):
  lone driver seeks to 333 → 13 of 14 inbound frames carry MY OWN setBy
  #3..#11  paused=False pos=333.059 … 333.036 doSeek=True setBy=SELF
           ← a seek you sent comes back to you, held for ~9 ticks, relay extrapolating
  lone observer, no mutations → 13 of 14 frames still setBy=SELF, all pos=0
  ⇒ §7's "0 inbound doSeek frames → sender gets no echo of its own seek" is WRONG

Relay endpoint spread (3 real rooms, 3 PoPs, ports do not correlate):
  room ca8cfezmke4 → pop-fra00:7776    room 1kp69st72evn → pop-atl01:7777
  room 2pk8mo9k00u → pop-fra01:7777    ← fra PoP on 7777; cannot be derived, only read

All four PoPs enumerated (popinventory.py) — one shared cert, TLS1.3-capable, Autobahn
21.3.1, both ports live on each, and a 4th PoP (pop-atl00) that no record has used yet:
  pop-fra00:7776 → syncplay00.pop.fra.plex.bz → 172.104.145.47
  pop-fra01:7777 → syncplay01.pop.fra.plex.bz → 172.104.203.32
  pop-atl00:7777 → syncplay00.pop.atl.plex.bz → 170.187.201.8
  pop-atl01:7777 → syncplay01.pop.atl.plex.bz → 139.144.189.245
  cert serial 0FF0E59865B296ECDDF0C939A2DB1D9F on ALL of them, valid .. 2027-03-04

Rooms are per-instance (popcrosstalk.py) — a wrong host:port does NOT error, it isolates:
  2 clients, same host:port      → 101 both, List shows BOTH      (control)
  2 clients, different PoPs      → 101 both, List shows self only
  2 clients, same PoP, other port → 101 both, List shows self only
  ⇒ syncplayHost AND syncplayPort are both load-bearing; a wrong one syncs you to yourself

Handshake ordering is NOT necessary (handshakeorder.py, 33 throwaway rooms, 0 failures):
  V2  Hello + 1 Hz State and NOTHING else      → 36 States, survives 35 s
  V1  full real-client order (ready false, ready true+manual false, playlist pair)
                                                 → 36 States, survives 35 s  ← identical
  V3/V4/V5/V6/V7 (ready only / playlist only / playlist first / no initial ready:false /
                 one unknown-key Set)          → 36 States, survives 35 s  ← identical
  P1/P2/P3 (pair inverted, playlist reversed, fully reversed) → identical survival
  all 11 variants: HTTP/1.1 101, realversion 1.6.5, 0 evictions, send_err=None
  Ordering's ONLY effect is last-write-wins on List.isReady: inverting the ready pair
  leaves isReady=False. Nothing about order affects liveness.
  Unknown Set keys are dropped silently (V7 ≡ V2 — the hsoNop never came back).
  Minimum viable handshake is ONE frame: Set{ready}{isReady:true,manuallyInitiated:false}

DNS: `together.plex.tv` → AWS ELB `us-east-1`; `pubsub.plex.tv` → Plex-operated;
`syncplay.plex.tv` → **NXDOMAIN** (see §3 for why that is misleading);
`syncplay.plex.services` (the cert apex) → **also NXDOMAIN** despite being in the SANs.

---

## 8. Conformance checklist

The minimum bar for a client that works alongside Plex Web. Work top to bottom; the order
matters, because each step is what makes the next one observable.

### Transport

- [ ] Resolve the relay from the room record — `syncplayHost` + `syncplayPort`. Never
      hardcode a hostname or IP; the room you are handed points at a specific PoP.
- [ ] TLS with **SNI and certificate verification on**. The cert is valid for
      `*.syncplay.plex.services`. Do not disable verification to "make it connect".
- [ ] Perform a real RFC6455 upgrade: random `Sec-WebSocket-Key`, expect `101`, and
      **verify the `Sec-WebSocket-Accept` digest**. No subprotocol, no permessage-deflate.
- [ ] Frame codec for text frames; **client→server frames must be masked**; handle 7/16/64-bit
      lengths. Payload is one small JSON object per second — 16-bit lengths suffice in practice.
- [ ] **Answer the relay's unsolicited PING with a PONG.** It pings on connect and
      periodically; a client that ignores this degrades or gets dropped.
- [ ] Handle a server CLOSE frame cleanly, and expose a way to close cleanly yourself
      (otherwise you leave ghost sessions — §5.8).

### Identity

- [ ] `username` is a **JSON string**, not an object, containing
      `deviceIdentifier` / `deviceName` / `userID`.
- [ ] Serialise it to **under 150 bytes**; shorten `deviceName` first; prefer compact
      separators. Over the limit and peers see unparseable JSON (§5.1).
- [ ] **`replace(/_+$/,"")` every username before `json.loads`** — yours and everyone
      else's, including your own echo. This is what makes self-recognition work (§5.1).
- [ ] Reuse a **stable `deviceIdentifier`** across restarts. A per-launch UUID makes every
      reconnect look like a new participant.
- [ ] `userID` as a **string**, from the account token, not a number.

### Session

- [ ] On connect, send `Hello {room:{name}, username, version}` and nothing else.
- [ ] Expect the relay to push `Set{ready}`, `Set{playlistChange}`, `Set{playlistIndex}`,
      then `Hello` — **before you send anything**. Do not assume your `Hello` is first.
- [ ] Read `realversion` from the server's `Hello` and log it. Your `version` is only a
      claim and is not validated.
- [ ] Request `{"List":{}}` when you need a roster; it nests `room → username → state`.
- [ ] **Dispatch `Set.user` on the presence of `file` vs `event`**, not on the message name.
      File changes arrive as `Set.user` with a `file` and no `event`.
- [ ] Treat `isReady` as **tri-state**: `null` / `false` / `true`.
- [ ] Ignore `Hello.features` vs per-user `features` disagreement (`chat` is `false` in one
      and `true` in the other). They are relay-side hints, not obligations — do not
      implement `isolateRooms` / `managedRooms` / chat speculatively.
- [ ] On (re)connect, **re-announce your full state** — file, readiness, playlist. State is
      per-connection and is not restored for you (§5.8).
- [ ] **Mirror `ignoringOnTheFly.server` on every outbound frame.** This is the single
      load-bearing conformance rule. A client that hardcodes `0` is muted within ~14 s; a
      client that echoes the relay's last value runs indefinitely (75 s+ verified) (§5.9).
      Read it from each inbound `State`, store it, send it back. This also replaces the
      ~14 s eviction as a design concern: the eviction is what the relay does to a client
      that *isn't* participating.
- [ ] Treat `event.left` where the key is **your own** stripped identity as **advisory,
      not as a peer departure and not as proof of eviction**. It fires for a non-echoing
      client that is genuinely being dropped, but it also fires at the end of a healthy
      replay that keeps receiving `State` afterwards. Keep reading the socket and let
      actual frame flow decide whether you are still live.
- [ ] Echo `State` on a **steady 1 Hz**. The room's position steps in 0.90–1.20 s
      increments that track the *driver's* echo cadence, so your jitter is everyone's
      jitter (§5.5).

### Sync loop

- [ ] Send `clientLatencyCalculation` as **monotonic seconds** (`performance.now()/1000`),
      never Unix epoch — the relay's own `latencyCalculation` is epoch seconds and the two
      are deliberately incomparable.
- [ ] **Send a fresh epoch `latencyCalculation` on every outbound tick**, alongside the
      monotonic `clientLatencyCalculation`. `serverRtt` is derived from the value *you*
      send; send `0`, omit the key, or send monotonic and it freezes or goes epoch-scale,
      and the skew correction below reads garbage (§5.5).
- [ ] Discard negative `clientRtt` samples; EWMA the rest; `forwardDelay ≈ averageRtt/2`.
- [ ] `serverRtt` **is** a clock-skew figure and **is** usable for §6.1's skew correction —
      it is `relayNow − your latencyCalculation`, signed and per-client. The earlier
      "relay-defined, do not compensate" guidance was retracted on the strength of a
      replay that was feeding stale stamps; that replay was the artifact. Never gate on a
      peer's `serverRtt` (§5.5).
- [ ] `target = remotePosition + (paused ? 0 : forwardDelay)`.
- [ ] **Emit exactly one `State` per tick, ~1 Hz.** One frame, with `ignoringOnTheFly` (both
      counters), `clientRtt`, `setBy: null`, integer position (§5.5).
- [ ] **Always include `ignoringOnTheFly` with both counters**, even at `0`. Real clients
      do (§11 item 18). Note the stall was *not* caused by omitting the block — it was
      caused by hardcoding `server: 0` in it (§11 item 19, next bullet).
- [ ] **Mirror the relay's `ignoringOnTheFly.server` back on your next tick.** Do not
      hardcode `0`. Hardcoding it makes the relay stop relaying within ~14 s — this was the
      root cause of the stall in §11 item 19 (§5.9).
- [ ] Never set `setBy` yourself — send `null` and let the relay assign the driver.
- [ ] **Drop every frame whose `setBy` is your own identity, before it touches position or
      pause state.** The relay echoes your own `State` back to you, `doSeek` included, and
      applying it pins a client at its own stale position (§5.5).
- [ ] Parse inbound `position` as a float and never truncate. You send an `int`; the relay
      replies with an extrapolated `float` while playing (§5.5).
- [ ] Evaluate `doSeek` **on the frame it arrives**, not on a coalesced latest-state struct —
      the flag is true for a single tick pair in what you SEND, but the relay echoes it
      back to you for ~9 ticks (§5.5), so slower polling silently drops *peers'* seeks (§5.6).
- [ ] Read playback position from `State`, **never from `List`** — `List.position` is `0`
      for every user regardless of where the room actually is.
- [ ] **Keep your own position estimate and re-send it every tick.** Do not try to emulate
      the relay's position arithmetic — it is correct for a conforming client (§5.5), but
      your own estimate is what keeps playing when you stop sending, so maintain and
      re-send it anyway.
- [ ] Honour both suppression counters: `ignoringOnTheFly.client` (yours — `1` means apply
      to me but do not rebroadcast, useful for a local drift nudge) and
      `ignoringOnTheFly.server` (the relay's, echoed back verbatim — this is the liveness
      gate, see §5.9).
- [ ] Apply the seek hysteresis and the gentle tempo-catchup band exactly (§6.2). A naive
      "seek whenever drift > 0.5s" loop will visibly stutter and will fight the host.
- [ ] Distinguish foreground (apply remote state) from background (ignore it), or a client
      idling in the lobby will hijack the room (§6.3).

### Room semantics

- [ ] Join by **playing the room's `sourceUri` from its recorded position, paused** — not by
      attaching to your current playback (§6.4). This mirrors Plex Web and the bundle's
      `populateMetadataItem` step. Verified end-to-end: a cloud-issued room ID joins the
      relay from its record's own `syncplayHost`/`syncplayPort` and gets a working session.
- [ ] Expect `POST /rooms` to return **`201`**, `invite` to return the **whole `Room`**, and
      `PATCH` to work (it is not dead code) if you want to rename a live room. `PATCH`
      takes a **JSON body** — `?title=…` alone is ignored (§4).
- [ ] Do not try to end a session for everyone. There is no such call: `DELETE` only
      **leaves**, for you, and a room ends when it hits `endsAt`. Model the UI as "leave
      this session" and let the host stop advertising it (§4).
- [ ] Resolve `sourceUri` against the **source server**, not your own. Accept both bare
      `server://…` and `provider://…/server://…`.
- [ ] Report readiness, and treat "host is playing, I have not pressed play" as the lobby
      condition rather than an error.
- [ ] Send `Set{ready}` **only on change** — the relay echoes every write verbatim and does
      not de-duplicate. Omit `manuallyInitiated` and it comes back `false`, never `null`;
      `isReady: null` survives as `null` (§5.4a).
- [ ] Keep the encoded `file` payload **under 250 bytes**. The relay cuts it at exactly 250
      with a blind byte slice, which yields unterminated JSON no peer can parse — and it
      fails silently. Realistic `sourceUri`s run 135–190 B, so measure and warn rather than
      discover it (§5.4a).
- [ ] Parse `Set{file}`'s inner payload **defensively**: the relay validates nothing, so a
      `uri` of `"not-a-uri"`, a missing `uri`, or truncated JSON will all arrive intact (§5.4a).
- [ ] If you join mid-session, read the room's current file from **`List`** — a peer that
      wrote one shows it under its entry (§5.4a). Do **not** expect the room to hand you a
      playlist; the relay stores none (§5.4a).
- [ ] Handle the room **disappearing mid-session** (three-hour cap, then `404`) as
      "session ended", not a retryable fault.
- [ ] Distinguish **all three** "gone" states: `403 "you do not have access to that room"`
      (you are not in it — which is what you get after `DELETE`, the *creator* included,
      stably), `404 "room not found not found!"` (expired, never existed, or already left),
      and absent from `GET /rooms`. They are different statuses with different text and a
      client that collapses them will retry a room it has left (§4).
- [ ] **`DELETE` does not evict anyone from the relay** — and it does not evict anyone from
      the room either. It only removes you. The relay has no room table and serves the same
      name immediately afterwards, so ending a room is "stop advertising it", not a session
      teardown (§4).
- [ ] Treat the room ID as a **credential**: no logging at debug level, no analytics, no
      shareable links (§7).

### Sanity test

- [ ] You can watch a real Plex Web session and have your client's position stay within the
      hysteresis band without visible stutter — in **both** directions: as host and as guest.
- [ ] Pausing on one client pauses the others; seeking on one client moves the others.
- [ ] Your client does not appear twice in the Plex Web roster, and Plex Web clients do not
      appear twice in yours.

---

---

# Appendix — PM4K integration notes

**Everything below this line is specific to the PM4K Kodi add-on** and of no interest to
other client implementers. §1–§8 above are the client-agnostic spec; the split is
deliberate so this document can be shared as-is.

---

## 9. What already exists in PM4K

| Need | Already in PM4K |
|---|---|
| plex.tv account token for `X-Plex-Token` | `MyPlexAccount`; see `lib/_included_packages/plexnet/myplexaccount.py:129` `fetchServerTokens` → `:142` for the plex.tv-with-account-token pattern |
| Persistent `clientIdentifier` | `lib/plex.py:97`, global setting `clientIdentifier` |
| Device name | global setting, same place |
| `sourceUri` ↔ (server, key) | already produced/consumed throughout plexnet. **Handle both the bare `server://…` form and the newer `provider://…/server://…` form** |
| Resolve item on the source server | `PlexServer.getObject()` / plexobjects |
| Send playstate to PMS | `lib/player.py:171` `updateNowPlaying()` → `lib/_included_packages/plexnet/nowplayingmanager.py:127` |
| Local pause/play/seek | `lib/player.py:547` `SeekPlayerHandler.seek()`, `:626` `seekAbsolute()`, `PlexPlayer.control()` |
| Player state callbacks | `lib/player.py:3047` paused, `:3055` resumed, `:3098` seek (base no-op interface `:52`) |
| Periodic tick inside the player | `lib/player.py:115` / `:1834` `tick()` |
| Background thread + task queue | `lib/backgroundthread.py:154` `BackgroundThreader`, `:58` `Task.run()` |
| Signals/events | `SignalsMixin` on `PlexPlayer` (`lib/player.py:2327`) |
| Dialog / modal pattern | `lib/windows/kodigui.py:43` `open()`, `lib/windows/dropdown.py:498` `showDropdown()` |
| Sidebar entry point for a hub | `lib/windows/home.py:3872` `showSections()`, virtual entries `:345-368` |
| Settings plumbing | `resources/settings.xml`, `lib/windows/settings.py:440` `SETTINGS`, `lib/settings_util.py:45` |

**Missing:** any raw socket / SSL / WebSocket usage in the addon
(`rg 'import ssl|websocket'` → nothing outside vendored `plexnet/netif` and `icmplib`).
Kodi's Python has no `websockets` module and `xbmc` exposes no WS API.

### The one real blocker: no WebSocket client

`ssl` + `socket` are available in Kodi's Python. A minimal RFC6455 client is genuinely
small for this workload — the traffic is one JSON message per second and the payloads are
far under 4 KiB:

1. `ssl.create_default_context()`, `wrap_socket(server_hostname=syncplayHost)` —
   SNI/hostname verification works as-is (the relay has a valid
   `*.syncplay.plex.services` cert, so keep verification **on**).
2. Send the HTTP/1.1 upgrade with a random `Sec-WebSocket-Key`, read the 101.
3. Frame codec for **text frames only**. Client→server frames **must** be masked; support
   7/16/64-bit lengths even though 16-bit is all this traffic needs.
4. Reader loop: `recv()`, deframe, `json.loads`. Handle control opcodes — **the relay
   pings, so you must pong** — and handle a clean close.
5. One thread, reconnect with backoff.

No `Sec-WebSocket-Protocol` and no permessage-deflate are negotiated by the web client,
and the relay accepted my socket without either. Estimated ~150-200 lines, and it is the
one piece worth writing once, generically, next to `lib/backgroundthread.py`.

### Kodi capability gaps that change the sync behaviour

* **The 0.95x catch-up is available — via `Player.SetTempo`, not `SetSpeed`.**
  `Player.SetSpeed` is the wrong tool: `CPlayerOperations::SetSpeed` accepts only an
  **integer** (`isInteger`, else `"increment"`/`"rewind"` → `playercontrol(forward|rewind)`),
  and the Python `xbmc.Player` API has no `setSpeed` at all. `Player.SetTempo` is correct:

  ```python
  xbmc.executeJSONRPC({"jsonrpc": "2.0", "id": 1,
                       "method": "Player.SetTempo", "params": {"tempo": 0.95}})
  ```

  Verified against Kodi master:

  | Fact | Source |
  |---|---|
  | accepts a `float` | `PlayerOperations.cpp` `SetTempo` → `isDouble()` branch |
  | pitch-preserving (tempo ≠ speed) | `CVideoPlayer::SetTempo` → `CDVDMsgPlayerSetSpeed{speed, clockSync: true}` |
  | clamped to **(0.75, 1.55)** | `CProcessInfo::IsTempoAllowed` + `MinTempoPlatform`/`MaxTempoPlatform` |
  | rounded to 2 decimals | `tempo = floor(tempo*100 + 0.5)/100` |
  | requires `SupportsTempo()` | `CVideoPlayer::SupportsTempo()` → `m_State.cantempo` |
  | `FailedToExecute` while paused | harmless — the 0.95x branch only runs while playing |
  | **added 2024-02-04 → Kodi 21 "Omega" only** | commit *add SetTempo command to JSON-RPC API* |
  | **no read-back** | no `Player.GetTempo`; `tempo` is not in `Player.GetProperties` |

  Consequences:

  * PM4K declares `<import addon="xbmc.python" version="3.0.0"/>` (Kodi 19+), so
    `SetTempo` must be **feature-detected**. Lazy check: issue the call once, treat an
    error result as unsupported. On Kodi 19/20, degrade to hard-seek-only (absorb the
    1.5–4 s drift band, then snap at ±4 s).
  * With no read-back, the sync client tracks its own `tempo_applied` flag. It needs a
    flag like that already to tag PM4K-initiated seeks, so it's the same mechanism.
  * `SetTempo(0.95)` leaves `Player.PlaySpeed` at 1 (tempo is a separate axis), so
    nothing odd shows in the OSD. Reset is `SetTempo(1.0)`.
* Kodi's Python `xbmc.Player` has **no `isPaused()`**. The sync client must read PM4K's
  own pause state, not Kodi's.
* `seekAbsolute()` from a non-main thread is something PM4K already does, so a sync thread
  driving seeks is not a new class of risk — but every applied pause/seek must be tagged
  so it isn't re-broadcast as a local user action. That maps onto the
  `initiator`-style flag PM4K already threads through its seek paths.

---

## 10. Integration plan

### 10.1 Where the code would live

Four new files, each with exactly one job. The split is not cosmetic:

| Component | Home | Why |
|---|---|---|
| `lib/ws.py` — minimal RFC6455 client | new | Generic: **no Plex and no Kodi**. Reusable if pubsub is ever wanted. |
| `lib/watchtogether.py` — rooms REST + model | new | Plain HTTPS, mirrors `myplexaccount.py`. No Kodi. |
| `lib/syncplay.py` — protocol session + drift math | new | **No Kodi imports.** This is what makes the drift math unit-testable. |
| `lib/windows/watchtogether.py` — dialog + player bridge | new | The only file that touches `xbmc`. |

Plus edits to `lib/player.py` (`updateNowPlaying()` at `:171`, behind the existing
`shouldSendTimeline` gate at `:145`) and the player paused/resumed/seek callbacks
(`:3047` / `:3055` / `:3098`), and a sidebar entry in `lib/windows/home.py`.

**Threading decision (locked).** The sync engine gets **its own reader thread** which
owns a plain `SyncState` object and applies player control directly, rather than folding
into PM4K's existing `_videoMonitor` tick or bouncing commands through signals. Reasons:

* PM4K's monitor thread *already* drives `updateNowPlaying()` and reads `getTime()` off
  the main thread (`lib/player.py:3227` → `_videoMonitor` → `:1838`), so this is
  established practice in the codebase, not a new hazard.
* Folding into `_videoMonitor` would tie session lifetime to playback — you could not sit
  in a room's lobby without something playing, which the ready/paused-join flow
  (§6.4) requires.
* Signal handoff adds a hop and makes the relay's fixed 1.0s `State` cadence fight
  PM4K's own tick, for no gain.
* It keeps the sync engine importable and testable without Kodi.

The reader thread must poll `util.MONITOR.abortRequested()` (or the player's `_closed`
flag) for shutdown, mirroring `_videoMonitor` at `lib/player.py:3222`. There is **no
existing `Task` subclass that owns an endless loop** — `BackgroundThreader`
(`lib/backgroundthread.py:154`) is a one-shot work queue, so it is the wrong primitive
here and should not be bent into one.

One explicit requirement that follows from this design: a **"sync override" flag** so
PM4K's own seek bookkeeping (notably `_applyingSeek`, `lib/windows/seekdialog.py:2024`)
does not misread a remote-driven seek as a local one and re-broadcast it.

### 10.2 The lazy first slice

Ladder check before writing anything:

1. **Does it need to exist?** Yes — it's the feature being asked for.
2. **Already in the codebase?** No; the WS client is genuinely absent.
3. **Stdlib?** `ssl`/`socket`, yes. `websockets`, no.
4. **Native platform feature?** Kodi has no WS API.
5. **Existing dependency?** None help. **New dependency? No** — a vendored `websockets`
   in a Kodi addon is a non-starter (it leans on `http.client` internals and threading
   assumptions Kodi doesn't guarantee).
6. → Hand-rolled minimal WS client. Shortest path.

**Skip in v1, in order of value/effort:**

* **Skip pubsub entirely.** Poll `GET /rooms` every ~15-20 s on the existing threader.
  Saves an entire second WebSocket implementation. Add pubsub only if invites feel slow.
* **Skip `createRoom` + invites.** Host from the web app, join from Kodi. Joining is the
  read-mostly half — one `GET`. Note §4: there is no invite URL, so a join-only Kodi
  client can only ever be the guest.
* **Skip shared playlists** (`Set{playlistChange}`, `Set{playlistIndex}`,
  `features.sharedPlaylists`). Present in the protocol, unimplemented by Plex's own web
  client, zero demand.
* **Skip ad-break sync** (`ads`, `breakPosition`, the lobby-shows-on-ad rule). Pure
  TUDN complexity.
* **Skip the participants popover / avatars / notifications / chat.** One OSD line
  ("3 watching, synced") covers 90% of the value.
* **Skip `controller`** — it never flipped in any probe and nothing client-side uses it.
* **Skip the 0.95x tempo branch on Kodi < 21** — feature-detect and fall back to seeks.

**Must be right in v1, or it isn't Watch Together:**

* `Hello` on connect, `List`, and the **1 Hz `State` echo loop** — stop echoing and the
  room thinks you left.
* **Pong the server's pings.** The relay pings on connect.
* `username` double-encoding. Parse it, and **strip `/_+$/`** before parsing — the relay
  appends underscores to make colliding identities unique, so a reconnect or a second
  instance will otherwise fail to recognise its own echo (§5.1).
* Keep the identity JSON **under 150 bytes** or peers see truncated, unparseable JSON.
* Dispatch `Set.user` on `file` vs `event` — a file change arrives as `Set.user`, not as
  `Set.file`.
* The `setBy`-is-self and `ignoringOnTheFly.{client,server}` ignore rules, or clients
  fight each other.
* `Set{ready}` on change, or the host's lobby never starts.
* Drift thresholds + RTT compensation, or you drift badly on WAN.
* Foreground/background asymmetry, or PM4K hijacks playback when you open the OSD.
* Keep TLS verification on for `*.syncplay.plex.services`.
* A "sync override" flag consulted by `shouldSendTimeline`-style gating, so PM4K's
  auto-resume, skip markers and the seek dialog's offset tracking stop fighting
  remote-driven seeks. PMS timeline reporting itself stays as-is — it's independent.

### 10.3 The piece that deserves a test

The drift/ping math is pure arithmetic with real edge cases (paused vs playing, negative
RTT samples, stale/absent `serverRtt`, the `ignoringOnTheFly` interactions) and it fails
*silently* when it's wrong. One small `test_syncplay.py` with a recorded relay transcript
as a fixture is the minimum. Everything else is plumbing.

### 10.4 Effort, honestly

| Slice | Size | Risk |
|---|---|---|
| WS client + `syncplay.py` + drift tests | the bulk | medium — needs a live relay to validate against |
| `GET /rooms` + room picker dialog | small | low |
| Player hook + ready/lobby | medium | **high** — desync bugs live here |
| `createRoom` + invite | small | low |
| pubsub notifications | small, once the WS client is generic | low |

---

## 11. Known unknowns / risks

1. ~~**Control acquisition is unknown.**~~ **RESOLVED [LIVE]:** `controller` is `false`
   for everyone, always — including the client actually driving playback. Control is
   implicit; `setBy` on the latest `State` is the only control signal. Nothing to build.
2. ~~**The relay mutates `playstate.position` in ways not reproduced by a plain "store
   the client's value" model — a relative position came back epoch-scale.**~~
   **RETRACTED [LIVE, `posprobe.py`] — the epoch-scale number never reproduces, and the
   relay's arithmetic is plain extrapolation from your last report.**
   * **Nothing ever comes back epoch-scale.** Swept `0, 1, 60, 1800, 3151, 3600, 86400,
     1e6`, plus `-1, 0.5, 1.5, 1e9, 1.7e9, 2^31`, and an *omitted* / `null` `position`
     (→ `0`) — paused and playing. Every magnitude round-trips as itself. The one input
     that looks epoch-like (`1.7e9`) comes back `1700000000`, i.e. stored verbatim.
     Whatever produced the original observation was a probe artefact, not the relay.
   * **Paused = exact store-and-return.** Deviation `+0.000` across every magnitude and
     all 29–30 frames of every run.
   * **Playing = extrapolate from your last report to now**, and it tracks a conforming
     client very tightly: a client advancing `position` by wall time each tick saw relay
     deltas of `0.922–1.001` against frame spacing of `0.937–1.049`, so
     **relay delta − frame spacing was median `−0.005`, range `−0.074…+0.063`** over 28.8 s.
     Residual error stays under ~0.08 s; there is no hidden clock base.
   * With a **fixed** (non-advancing) position the relay adds up to ~1–3 s of drift while
     playing, scaling with how stale your report is — up to `+3.167` at a 3 s send
     interval, `+1.995` at 1 s. That is the same extrapolation, just measured against a
     value that never moves, and it is bounded by your send interval rather than growing
     without limit (45 frames, no accumulation).
   * **Guidance is unchanged but for a different reason:** keep your own estimate and
     re-send it every tick. Not because the relay's numbers are unusable — they are
     accurate to ~0.08 s for a conforming client — but because you are the only source of
     truth when paused or stalled, and the relay simply carries your last word forward.
3. **Protocol version skew.** The client claims `1.6.4`, the relay implements `1.6.5`, and
   the relay has already shipped features (`controller`, shared playlists,
   `manuallyInitiated`, `isolateRooms`, `managedRooms`) that Plex's own web client does
   not implement. Log `realversion`; expect it to move.
4. **No versioning on `together.plex.tv`.** No `/v1/` prefix, no documented schema.
5. **Announced deprecation.** If Plex ships "similar functionality with new tooling"
   (their words), this goes dark.
6. **No access control on the relay.** The room ID is a bearer secret (§7). PM4K should
   not log room IDs at debug level, and should never reuse the room ID in a user-visible
   "share this room" feature as if it were a link.
7. **Requires internet + a plex.tv token — but only for *discovery*.** Creating a room,
   listing yours, and reading `syncplayHost`/`syncplayPort` are all cloud REST and need a
   token. The **relay itself takes none** (§1): once a client knows `roomID` and
   `host:port` it joins with nothing but a `Hello`. So WT cannot be a "just works with my
   server" feature end to end, but the socket half is fully offline-capable given a
   room's coordinates — relevant to PM4K's local mode, where the cloud half is what
   breaks, not the protocol.
8. **Playback requires access to the initiator's PMS — membership does not.** Nothing
   measured checks that the invitee can reach `sourceUri`: §11.9 shows `POST /invite`
   accepts a `sourceUri` pointing at a server that does not exist (no validation at
   invite time), and §11 item 26 shows the relay has no view of the room record at all —
   a fabricated `userID` in nobody's `users[]` joins a real room alongside real accounts.
   The failure is at the player: PM4K must resolve `sourceUri` itself to start playback,
   and without access to that server it has nothing to play. Scope the requirement to
   *media*, not to *membership*. **Untested:** an invitee whose account genuinely cannot
   read the host's library joining and then failing at playback — the invite gate (§11.9)
   would likely refuse that invite long before the player did.
9. ~~**UNSOURCED — invites are *believed* limited to friends / home users.**~~
   **RESOLVED [LIVE, `inviteprobe.py`] — the gate is the *inviter's relationship to the
   target*, proven with a valid-but-unrelated stranger.** The belief originally came from
   a single third-party account that a friend of *serverowner* accepted and *libraryuser* refused.
   That account has been retired, and the sweep was re-proven with an **explicitly
   approved stranger account** (`1000004` here is a redacted placeholder for it; a real,
   active plex.tv account that is friend of neither inviter and has access to zero
   servers, verified via `/api/resources`):

   | inviter | target | `sourceUri` = plausible id | `sourceUri` = bogus id |
   |---|---|---|---|
   | serverowner | libraryuser (`1000002`, related) | **200** | **200** |
   | serverowner | serverowner (self) | 400 | 400 |
   | libraryuser | serverowner (`1000001`, related) | **200** | **200** |
   | libraryuser | libraryuser (self) | 400 | 400 |
   | either | `999999999` (absent) | 400 | 400 |
   | either | `1000004` (**valid, unrelated**) | 400 | 400 |
   | libraryuser (participant) | serverowner | **200** | — |
   | either | `users:["NaN"]` (non-numeric) | **500** Postgres leak | — |

   What this settles:
   * **The relationship gate is real.** `1000004` exists, resolves, and is not
     suspended — yet is `400` from *both* inviters on *both* `sourceUri`s. An absent id
     (`999999999`) is refused for not existing; that is expected. A **valid** account
     being refused too means the refusal is **because the inviter is not linked to it** —
     "any existing account can be invited" is falsified.
   * **`sourceUri` is irrelevant.** The probes ship a *placeholder* machine identifier
     (`aaaa0000…4444` — the host's real PMS id is deliberately not published), and it
     behaves identically to the deliberately-bogus one: swapping in a server that does
     not exist changed no outcome, so invite does *not* check that the target can reach
     the room's media. Worth knowing: a room can be handed to someone with no access to
     its content.
   * **Self-invite is always `400`**, from either account, against either `sourceUri`.
   * **`invite` is NOT host-gated.** A participant inviting an account it is related to
     gets `200` and `users[]` grows to three entries — with the inviter's own id
     duplicated (`[1000001, 1000002, 1000001]`), so treat `users[]` as a set.
   * **Bad `users` shapes are `400`**: a bogus id, a negative id, a non-list `users`, or
     a missing `users` key. A non-*numeric* id is different: it is a **`500` leaking
     Postgres** (`invalid input syntax for type integer: "NaN"`), the only SQL-flavoured
     crash in the surface. Together with `PATCH`'s missing-body `500` (§4), these are the
     two bad-input paths that reach the caller as `500` instead of `400`.
   * `users` may be a **list or a bare id-shaped object**; both were accepted (`200`).
   * **There is genuinely no share URL.** A room is reachable only by an account the
     inviter invites; there is nothing to paste into chat. That is a product constraint,
     not a bug — worth stating up front to anyone expecting a link.
10. **Room lifetime is 3 h** (`endsAt - startsAt == 10800`), fixed. **RESOLVED
    [LIVE]** — measured on three separate rooms, and the relay does *not* enforce it.
11. **`sourceUri` format is version-dependent** (bare `server://` vs
    `provider://…/server://`). Accept both.
12. **`List.features` and `Hello.features` disagree** on the same room. Don't gate on
    them.
13. ~~**No presence timeout for an *echoing* client was observed; a hard-killed client
    produced no `left` event and stayed in the roster for the whole capture window.**~~
    **PARTLY WRONG [LIVE] — the relay *does* tell peers immediately when a socket dies;
    what it cannot see is silence on a live socket.** Three ways for a client to stop,
    observed by a *third, still-echoing* peer so the observer survives the whole window:

    | how the victim stops | peer sees `left` | |
    |---|---|---|
    | abrupt socket close, **no** WebSocket Close frame | **6.20 s** (action at 6.0 → ~0.2 s) | instant |
    | proper WebSocket Close frame | **6.25 s** (→ ~0.25 s) | instant |
    | socket **stays open**, client just stops sending | **18.40 s** (action at 6.0 → ~12.4 s) | the 13.21 s silence timer of item 17 |

    So the two mechanisms are cleanly separated:
    * **Transport death is detected in ~0.2 s** and broadcast as `Set{user}{event:left}`
      whether or not a Close frame was sent. The relay watches the socket, not the
      handshake. Peers can rely on this for roster cleanup.
    * **A live but silent socket is not detected until the 13.21 s silence timer of
      item 17 fires** — and that is the same synthetic `left`, just late.
    * **For a conforming client there is still no timeout**: echo every tick and mirror
      the suppression counter and you are never evicted, for as long as the socket lasts.
    The earlier "hard-killed client produced no `left`" reading did not reproduce under an
    observing peer; it most likely came from a capture where the observer had itself been
    evicted, or where only the victim's own incoming stream was being watched — a client
    cannot hear its own `left` once its socket is gone.
14. **RESOLVED [LIVE] — the cloud write path is exercised, with two real accounts.** The
    full matrix was run against the real service as `serverowner` (`1000001`, creator)
    and `libraryuser` (`1000002`, invited participant). See §4 and
    `docs/probes/authzprobe.py`. **Every cell is now measured** as of 2026-10-06: the
    tokenless column and the invalid-token column were filled in, both are `401`
    throughout, and one `401` body leaks an in-cluster URL (§4). What it settled:
    * **`DELETE` is "leave the room", not "destroy it."** Both the creator and a plain
      participant get `204` and lose only their *own* membership — the other party still
      reads `200`. There is **no destroy-for-everyone endpoint**; a second `DELETE` is
      `404`, and rooms genuinely end only at `endsAt`. This corrects an earlier reading of
      §4 that claimed `DELETE` destroyed the room.
    * **`invite` is not host-gated** — a participant got `200`. Its earlier `400` was the
      inviter↔target relationship gate (§11.9), which applies to the creator identically.
      **No write is gated on being the creator.**
    * **`PATCH` is not host-gated** and **repoints `sourceUri`**, so it gates nothing.
    * **The `watch-together-*` subscription flags are not gated on an active Plex Pass** —
      an `Inactive` account still carries `watch-together-20200520` and
      `watch-together-invite`. Do not use those flags as a proxy for "can create a room".
    * **`PATCH`'s writable set is `title` and `sourceUri`;** both verified writable by a
      non-host. No other field was tested, and the bundle has no caller to learn from.
15. ~~**Not yet observed from a real Plex Web or native client.**~~ **RESOLVED [LIVE]:**
    captured both real clients mid-playback — see §5.1 — and outbound frames in §5.5.
    `serverRtt` was `0` in relay-*initiated* `State` but populated (`0.10`–`0.25`) in the
    relay's rebroadcast of a client's own frame, and clients echo it back.
16. **RESOLVED [LIVE]:** the *outbound* seek frame is confirmed — `doSeek: true` with
    `paused: false` and `position` set to the absolute target, true for exactly one tick
    (§5.6). **Third-party propagation is now verified too**: a two-client probe where A
    seeks to 900 had B receive `pos=900 doSeek=True setBy=BRAVIA VH1`, hold 900, then see
    `doSeek:False`. Pause propagation verified the same way.
    **CORRECTION:** "only the *sender* gets no echo" was wrong — it was inferred from a
    peerless capture. A lone client gets its own frames back, `doSeek` included, for
    several ticks (13/14 frames in `selfecho.py`). See §5.5; self-ignore is mandatory.
17. ~~**Idle-eviction timing is approximate.**~~ **RESOLVED [LIVE] — it is a per-connection
    silence timer, reset by every `State` you send, measured at 13.21 s / 14 relay frames.**
    (`docs/probes/evictprobe.py`.)
    * **The timer runs against *your last outbound* `State`, not from join.** Joining an
      already-old room gives the same 14 frames / 13.21 s as joining a fresh one. Sending
      one `State` at `t=10` pushed eviction from 13.21 s to **23.25 s** — exactly
      `10 + 13.21`. So any echo restarts it; there is no absolute deadline.
    * **Threshold is between 13 and 14 s of silence:** echoing every 13.0 s survives,
      every 14.0 s dies (eviction always lands on the 14th relay frame at 13.21 s, before
      the 14 s echo could fire).
    * **Count vs clock stays formally inseparable, and the reason is itself a finding:**
      the relay normalises its *outbound* cadence to a fixed 1 Hz no matter what it
      receives. 4 Hz, 1 Hz and 0.5 Hz drivers all produced a median 1.0 s gap and exactly
      14 frames before eviction. So "14 messages" and "13.21 seconds" cannot be made to
      diverge from outside — and the driver's rate cannot be used to evict or spare anyone
      faster.
    * **Not load-dependent.** Four silent clients in one room were all evicted on the same
      14-frame / ~13.2 s schedule regardless of how many drivers were ticking (1, 4 or 6,
      at 1 or 4 Hz).
    * Practical consequence is unchanged and now firmer: **if you send nothing for ~13 s
      you are out**, silently — the `left` is a `Set`, not a `State`, and your socket stays
      open. Echo every tick and mirror the suppression counter and you are never evicted
      (§5.9). A client may safely ignore the exact value, but a **13 s gap in its outgoing
      `State` is a disconnect**, not a stall.
18. ~~**BLOCKER — no capture of a real client's OUTBOUND `State`.**~~ **RESOLVED [LIVE]**
    Captured a 131.2 s live session via Safari Web Inspector and split it by `clientRtt`
    (absent 130/130 in the relay direction, present in the client direction). This
    falsified three assumptions the probes were built on:
    * `ignoringOnTheFly` is **always** present with **both** counters, never omitted at `0`.
    * A client emits **one** frame per tick. The apparent "two shapes" were two
      **directions**, not two roles (§5.5).
    * Clients send `setBy: null` and a real `clientRtt`.
19. ~~**BLOCKER — the State stall (mis-timed at ~6 s; measured 13.7–14.2 s).**~~ **RESOLVED [LIVE] — root cause was the
    `ignoringOnTheFly.server` counter.** See §5.9. The stall was never a frame-shape or
    handshake problem:
    * An 8-way handshake bisect (baseline, `manuallyInitiated:false`, false-then-true,
      null-ready-first, `+Set.user`, `+playlist` pair, full capture order, no-ready-at-all)
      **all stalled identically at 1.1–1.4 s**, ruling out the handshake entirely.
    * Two single-variable tests on the frame body ruled out the rest: `clientLatencyCalculation`
      scale (~0 vs ~2755) and starting position (~0 vs ~1800) changed nothing.
    * The one variable that mattered: hardcoded `ignoringOnTheFly.server: 0` (STALL at
      14.2 s) versus mirroring the relay's last value (OK through 23.2 s). Confirmed again
      at length: single client, 75 s, steady 1 Hz, no gaps.
    The corrected two-client probe then ran end-to-end: drive propagation
    (`setBy=BRAVIA VH1` at 100/102/104), pause propagation, and `doSeek` propagation to
    900 all observed, `controller=false` for both clients, and the peer's clean-close
    `left:true` seen. Pause and seek propagation are now **tested positive**, not untested.
20. ~~**"Echoing makes it worse".**~~ **RETRACTED.** The `staterevivebisect.py` matrix behind
    that reading used a client that hardcoded `server: 0`. The heartbeat *is* a liveness
    signal; it is gated on echoing that counter. The probe has not been re-run in full for
    the §5.8 table's multi-client rows, so the old matrix should be treated as void rather
    than corrected.
21. ~~**`serverRtt` remains unresolved.**~~ **RESOLVED [LIVE] — it is your own clock skew.**
    `serverRtt = relayNow − the ping.latencyCalculation YOU sent`, signed and **per-client**.
    Swept directly (`rttprobe.py`): fresh epoch → `0.057`; `−3600` → `+3600.06`;
    `+3600` → `−3599.94`; monotonic → epoch-scale; `0`/omitted → frozen at the last value.
    The peer's number never moved. See §5.5.
    * The `~50510` that made this look broken was a **verbatim replay feeding epoch stamps
      from hours earlier** — the relay faithfully reporting staleness, not tolerating
      nonsense. The retraction was correct to distrust the field and wrong about why.
    * The retracted formula was structurally right, one field name off: skew is measured
      against `latencyCalculation`, not `clientLatencyCalculation`.
    * **This makes the field load-bearing for §6.1**, reversing the "do not compensate"
      guidance. Consequence: send a fresh epoch `latencyCalculation` every tick.
22. ~~**Only one relay PoP has been characterised in depth.**~~ **RESOLVED [LIVE] — all
   four PoPs enumerated** (`popinventory.py`), and they are *less* different than the "assume
   others differ" hedge implied: one shared certificate (identical serial across all four),
   identical `AutobahnPython/21.3.1`, identical `features`, and TLSv1.3 everywhere once you
   use a client that offers it. Ports do not correlate with PoP — both 7776 and 7777 upgrade
   on every PoP, so the port is a second listener, not a distinct deployment.
   * A **fourth PoP, `pop-atl00`, resolves but has never appeared in a room record.**
   * `List.features`/`Hello.features` still disagree (§11.12); that is a relay quirk, not a
     per-PoP one.
   * What remains genuinely open is small: **IPv6 reachability is untested** (the probing
     host has no v6 egress), so the AAAA records are unconfirmed rather than known-good.
23. ~~**`Set.ready` and the join handshake ordering are only partly characterised.**~~
    **RESOLVED [LIVE] — ordering is not necessary; the handshake does not participate in
    liveness at all.** (`docs/probes/handshakeorder.py`, 11 variants × 3 runs, 33
    throwaway rooms, zero evictions; supersedes the 8-way matrix in item 19.)
    * **Liveness is gated on exactly one thing:** mirroring `ignoringOnTheFly.server`
      back on every outbound `State` (§5.9). Every variant — including one that sends no
      `Set` at all — sustained 34 inbound `State` frames across 32 s, past the ~14 s
      eviction window, with no synthetic `left` and no send errors. `Hello` + 1 Hz `State`
      is indistinguishable from the full real-client sequence.
    * **The writes matter as values, never as order.** The relay is a plain
      last-write-wins store: `List.isReady` is whatever the last `Set{ready}` said, so
      inverting the ready pair leaves `isReady: false` in the roster and changes nothing
      else. `playlistChange`/`playlistIndex` round-trip verbatim before or after ready.
    * **An unknown `Set` key is silently dropped**, not echoed — a variant with a
      fabricated key is byte-for-byte indistinguishable from the baseline.
    * So a conforming client needs **one frame, not four**: `Set{ready}{isReady: true,
      manuallyInitiated: false}`. The real client's other three writes (the
      `isReady: false` priming write, and the explicit `files: []` / `index: null`
      playlist nulls) buy roster *content*, not survival.
    * Not exercised here: no variant sends `Set{file}`, so `file` is `{}` in every roster
      row and the `maxFilenameLength` interaction of item 24 is not covered.
24. **The relay write path is now fully characterised** [LIVE, `writepathprobe.py`] —
    see §5.4a. Three findings that change what a client must do:
    * **`maxFilenameLength: 250` is a blind byte cut that produces unparseable JSON.**
      233 B survives; 273 B comes back as exactly 250 B of unterminated string. Realistic
      `sourceUri`s (135–190 B encoded) clear it, so this is a cliff to *measure*, not a
      routine failure. Same failure mode as the 150-byte username cut.
    * **`Set{ready}` is normalised to exactly three keys** — `username`, `isReady`,
      `manuallyInitiated` — dropping unknown keys, defaulting a missing `manuallyInitiated`
      to `false` (never `null`), and preserving `isReady: null`. So "send on change" is the
      client's job; the relay will not de-duplicate.
    * **The relay keeps no playlist state.** `playlistChange`/`playlistIndex` round-trip
      faithfully — including `files: []`, `index: null`, and `index: 0` — and the nested
      double-encoding survives, but there is no playlist field in `List` and a reconnecting
      session gets empty values back. A joining client must be handed the playlist out of
      band. `Set{file}`, by contrast, *does* appear in `List` under the writer's entry.
25. **The relay performs no validation of `Set.file`.** `"uri":"not-a-uri"`, a missing
    `uri`, and truncated JSON are all stored and rebroadcast byte-identically. Only an
    empty string or a payload not starting with `{` is dropped — **silently, with no error
    frame**. A client must parse defensively and cannot rely on the relay to reject junk.
26. **RESOLVED [LIVE] — a real cloud room behaves exactly like a fabricated one.** The last
    assumption standing was that the relay might consult the room record now that rooms
    genuinely exist. It does not (`docs/probes/realroomprobe.py`, room `1w7ut63c1zjf`):
    * A client claiming `userID 999999999` — absent from the room's `users[]` — completed
      the handshake (`101`) and appeared in the roster beside both real accounts.
    * Roster entries carry `userID: None` for **everyone**, real accounts included. The
      relay keeps only the identity string it was handed; there is no plex.tv lookup, so a
      real `userID` buys a client nothing.
    * `syncplayHost`/`syncplayPort` were **stable** across a mid-session re-`GET` of the
      record, and `endsAt − startsAt` was exactly 3 h.
    * Playstate propagation between the two real accounts worked, but each client also
      received **its own** frames back — the self-echo of item 16's correction. So the
      cloud layer is a room *directory*; it confers no authority on the relay at all.
27. **Rooms the research left behind expire on their own 3 h clock.** The first wave was
    four rooms — `1w7ut63c1zjf` (the two-account relay run) plus `1xuwd5rbbe15`,
    `1kmf9gbb5ti` and `qo5obubb393` from the authz matrix — and later sweeps added a
    couple of dozen short-lived `invprobe`/`matrix`/`ctl` rooms.
    They are not reachable by anyone who has not been invited, and `DELETE` cannot destroy
    them — only the clock can.
    **Status 2026-10-06: both probe accounts list `0` rooms**, i.e. every one has either
    expired or been left. `GET /rooms` returning `[]` is the cheap way to confirm a sweep
    cleaned up after itself, and is worth doing at the end of any probe run that creates
    rooms. Leaving a room removes it from *your* list only; the room survives for the
    others until `endsAt` (§4).

---

## 12. Reproducing the captures

Probes live in `docs/probes/`, stdlib only, no Plex credentials needed for the relay ones.

| Probe | What it establishes |
|---|---|
| `wsprobe.py` | Reference client: TLS upgrade, masked framing, pong, `Hello`/`List`. Read-only. |
| `identityprobe.py` | §5.1 — identity echo, verbatim vs re-serialised, the 150-byte truncation, the `_`/`__` collision ladder |
| `readonlycapture.py` | Point at a real room: sends only `Hello` + `List` + pongs, prints everything, self-limits to the ~14 s eviction window |
| `lifecycleprobe.py` | §5.8 — duplicate sessions are not evicted, `left` on clean close, per-connection state, reset on reconnect |
| `staterevivebisect.py` | §5.8 — which frame shapes keep a session alive; 14-message eviction matrix. **Void**: hardcoded `ignoringOnTheFly.server: 0` |
| `twoclientprobe.py` | Two conforming clients: does one drive the other? Emits the real single-frame `State` (§5.5) and mirrors the relay's suppression counter (§5.9). Self-ignores its own echo via `is_self()` on the identity it sent (§5.5). **Gotcha:** `Client` reads the room from a module global, so concurrent use needs a lock |
| `replayprobe.py` | §5.9 — replays 147 verbatim captured frames; proves content-vs-handshake by construction |
| `handshakebisect.py` | §5.9 — 8 concurrent handshakes, one room each; rules the handshake out as the stall's cause |
| `rttprobe.py` | §5.5 — sweeps `ping.latencyCalculation` to resolve `serverRtt`; two clients so it separates per-client from room-wide |
| `writepathprobe.py` | §5.4a — every `Set` write from both sides: `file`/`ready`/playlist, validation, roster effects |
| `writepathprobe2.py` | §5.4a — exact bytes back: the 250-byte cut, `Set{ready}` key normalisation, playlist round-trips |
| `selfecho.py` | §5.5 — a lone client in a throwaway room: proves the relay echoes your own `State` (and your own `doSeek`) back, so self-ignore is mandatory |
| `evictprobe.py` | §5.8 / §11.17 — idle-eviction threshold: silence timer reset per outbound `State`, 13.21 s / 14 frames, and that the relay pins its outbound cadence to 1 Hz regardless of driver rate |
| `posprobe.py` | §11.2 — sweeps `playstate.position` across magnitudes and both playstates; proves the relay stores paused values verbatim and extrapolates while playing, and that the old "epoch-scale" reading does not reproduce |
| `killprobe.py` | §11.13 — three ways to stop (silence, abrupt socket close, WS Close) observed by a *third* echoing peer: transport death reaches peers in ~0.2 s, silence waits out the 13.21 s timer |
| `inviteprobe.py` | §11.9 / §4 — inviter × target × sourceUri sweep: the gate is the *inviter's* relationship to the target, `sourceUri` is irrelevant, self is always 400, non-numeric ids leak Postgres; and a plain participant invites successfully, so `invite` is **not** host-gated |
| `authzprobe.py` | §4 — two real accounts: the full cloud authorisation matrix, and that `DELETE` means "leave" |
| `authzprobe2.py` | §4 — exact `DELETE` semantics (symmetric leave, no destroy), `403`-vs-`404`, re-invite, and what `PATCH` really writes |
| `realroomprobe.py` | §11 item 26 — two real accounts on a **cloud-issued** room: the relay ignores the room record, and propagation works end to end. R3 split into propagation (R3a) vs self-ignore (R3b) so it can no longer report the former as the latter |
| `handshakeorder.py` | §11 item 23 — 11 handshake variants × 3 runs, 33 throwaway rooms: **ordering is not necessary**, the `State` echo alone sustains the session |
| `popinventory.py` | §3 / §11 item 22 — DNS (A/AAAA/CNAME/PTR) + TLS cert per PoP; sends no frames |
| `popcrosstalk.py` | §3 — whether PoPs are interchangeable. They accept any room name but a room is scoped to one `host:port` |

All probes are now import-safe (no live traffic on `import`) and each `twoclientprobe.py`
run creates its own throwaway relay room. That room name is never reported to the cloud.

```bash
# the three cloud probes need two real plex.tv tokens; see the note below
python3 docs/probes/authzprobe.py
python3 docs/probes/authzprobe2.py
python3 docs/probes/realroomprobe.py
```

The three cloud probes (`authzprobe`, `authzprobe2`, `realroomprobe`) **do** need two real
plex.tv account tokens, because no amount of one-token probing can tell "host-only" from
"anyone". They read them from `~/.plex-probe-token-host` and `~/.plex-probe-token` (mode
`0600`), never from argv, and only ever touch rooms they create themselves.

```bash
# room list (needs a plex.tv account token)
curl -s -H "X-Plex-Token: $TOKEN" -H "X-Plex-Product: PM4K" \
        https://together.plex.tv/rooms | python3 -m json.tool

# read-only relay session against a REAL room: Hello + List + pong, no Set/State.
# Bounded at ~14s: the relay reaps a session that never echoes State (§5.8).
python3 docs/probes/wsprobe.py <roomID> <syncplayHost> <syncplayPort> <userID>

# self-contained; spin their own throwaway rooms on the relay
python3 docs/probes/identityprobe.py
python3 docs/probes/lifecycleprobe.py
python3 docs/probes/handshakeorder.py     # ~11 rooms/run, ~35 s each
python3 docs/probes/selfecho.py           # 2 rooms, ~11 s each
python3 docs/probes/popinventory.py       # DNS + TLS only, sends nothing
python3 docs/probes/popcrosstalk.py       # one client per PoP by default

# two conforming clients, own throwaway room, ~30s. The load-bearing test:
# does B receive A's position and setBy? Also covers pause + doSeek propagation.
python3 docs/probes/twoclientprobe.py <syncplayHost> <syncplayPort>

# the stall bisect: 8 handshakes concurrently, own throwaway room each, ~25s.
# All 8 stall identically, which is what proves the handshake is not the cause.
python3 docs/probes/handshakebisect.py <syncplayHost> <syncplayPort> 25

# what IS serverRtt? sweeps latencyCalculation, two clients, own room, ~35s
python3 docs/probes/rttprobe.py <syncplayHost> <syncplayPort>

# what does the relay do with each write? two clients, own room, ~60s
python3 docs/probes/writepathprobe.py  <syncplayHost> <syncplayPort>
python3 docs/probes/writepathprobe2.py <syncplayHost> <syncplayPort>

# read-only look at a real room (will show as a brief extra participant named "probe")
python3 docs/probes/readonlycapture.py <host> <port> <roomID> <someUserID> 14
```

`syncplayHost` and `syncplayPort` come from the room record — do not hardcode them, and
note the port is **not** always 7776.

Writes were only ever exercised against a bogus room name, which the relay creates on
demand. Do not use a real room ID for protocol experiments — you will take control of
someone's playback, and there is no authorisation that will stop you.

### Verifying your own client without disturbing anyone

The safe sequence:

1. Create a throwaway room name that does not exist in the cloud. The relay will serve it.
2. Run **two** instances of your client against it. Everything in §5 and §6 — handshake,
   `List`, `Set`, drive propagation, pause, `doSeek`, drift correction, hysteresis — is
   fully exercisable this way, with two real implementations talking, and nobody disturbed.
3. Only then observe a real room, read-only, for ≤14 s.

Step 2 is the one most people skip, and it is the only way to test the sync algorithm
honestly. You do not need a second human.
