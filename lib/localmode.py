# coding=utf-8
"""
Local mode ("Go local"): run against a local PMS only, without any plex.tv access.

Handles the account-less bootstrap (manual server entry, user seeding from the PMS'
/accounts endpoint) and storage of manually added local servers.
"""
from __future__ import absolute_import

import json

import requests

from xml.etree import ElementTree

from kodi_six import xbmcgui

from . import util
from .i18n import T


PROBE_TIMEOUT = 10


def getStoredServers():
    try:
        servers = json.loads(util.getSetting('local_servers_json', '') or '[]')
    except ValueError:
        servers = []
    return [s for s in servers if isinstance(s, dict) and s.get('connection')]


def saveStoredServers(servers):
    util.setSetting('local_servers_json', json.dumps(servers))


def probe(ip, port, token=None):
    """
    Check whether a PMS answers at ip:port. Returns (ok, name, needsAuth).
    /identity answers unauthenticated; the root endpoint tells us whether the
    given token (or no token) is enough for actual library access.
    """
    base = 'http://{0}:{1}'.format(ip, port)
    try:
        r = requests.get(base + '/identity', timeout=PROBE_TIMEOUT)
        if r.status_code != 200:
            return False, None, False
    except Exception:
        return False, None, False

    name = None
    needsAuth = False
    try:
        headers = {'Accept': 'application/xml'}
        if token:
            headers['X-Plex-Token'] = token
        r = requests.get(base + '/', headers=headers, timeout=PROBE_TIMEOUT)
        if r.status_code == 200:
            name = ElementTree.fromstring(r.content).attrib.get('friendlyName')
        elif r.status_code in (401, 403):
            needsAuth = True
    except Exception:
        pass

    return True, name, needsAuth


def addServerDialog():
    """
    Dialog-driven manual server entry with an immediate connection check; on failure
    the entry dialogs are re-offered (values prefilled). Returns True if a server was
    stored.
    """
    ip = ''
    port = '32400'
    token = None
    while True:
        ip = xbmcgui.Dialog().input(T(35023, 'Local server IP or hostname'), ip)
        if not ip:
            return False

        port = xbmcgui.Dialog().input(T(35024, 'Local server port'), port, xbmcgui.INPUT_NUMERIC)
        if not port:
            return False

        token = xbmcgui.Dialog().input(T(35025, 'Plex token (optional)'), token or '') or None

        ok, name, needsAuth = probe(ip, port, token)
        if ok:
            break

        button = xbmcgui.Dialog().yesnocustom(
            T(32427, 'Failed'),
            T(35026, 'Could not reach a Plex Media Server at {0}.').format('{0}:{1}'.format(ip, port)),
            customlabel=T(35033, 'Add anyway'),
            nolabel=T(32337, 'Cancel'),
            yeslabel=T(35032, 'Try again'))
        if button == 1:
            continue
        elif button == 2:
            break
        return False

    if needsAuth:
        xbmcgui.Dialog().ok(
            T(35027, 'Authentication required'),
            T(35028, 'The server requires authentication. Enter a Plex token for it, or add this device\'s '
                     'network to the server\'s "List of IP addresses and networks that are allowed '
                     'without auth" setting.'))

    servers = [s for s in getStoredServers() if s.get('connection') != ip]
    servers.append({'connection': ip, 'port': int(port), 'token': token, 'name': name})
    saveStoredServers(servers)

    util.DEBUG_LOG('Local mode: stored local server {0}:{1} ({2})', ip, port, name or 'unnamed')
    return True


def offerServerIfNoneFound():
    """
    Local mode ended up without any reachable server - offer manual entry.
    Returns True if a server was stored (caller should re-check connections).
    """
    if not xbmcgui.Dialog().yesno(
            T(35030, 'No local server found'),
            T(35031, 'No local Plex Media Server was reachable. Add one by IP address?')):
        return False

    return addServerDialog()


def ensureInsecureConnectionsAllowed(warn=True):
    """
    Local mode only ever talks to LAN addresses over plain HTTP - plex.direct hostnames
    need public DNS, so they're dropped. With "Allow Insecure Connections" left at its
    default of never, those connections are never even tested (they're parked as
    STATE_INSECURE and the insecure fallback round never runs), which looks exactly like
    "no server found". The server needs the matching setting, hence the warning.

    Returns True if the preference was changed.
    """
    from plexnet import util as pnUtil

    if util.getSetting('allow_insecure', 'never') == 'always':
        return False

    util.setSetting('allow_insecure', 'always')
    pnUtil.APP.trigger('change:allow_insecure', value='always')
    util.LOG('Local mode: allowing insecure connections')

    if warn:
        xbmcgui.Dialog().ok(
            T(35048, 'Insecure connections enabled'),
            T(35049, 'Local mode reaches your server over plain HTTP, so "Allow Insecure '
                     'Connections" has been set to "Always".\n\nYour server needs the matching '
                     'setting: in Plex under Settings > Network, "Secure connections" has to be '
                     '"Preferred" - with "Required" the server refuses these connections.'))

    return True


def bootstrap():
    """
    Account-less local mode entry from the pre-signin screen.
    """
    if not addServerDialog():
        return False

    ensureInsecureConnectionsAllowed()
    util.setSetting('local_mode', True)
    return True


def getSelectedProfiles():
    try:
        profiles = json.loads(util.getSetting('local_profiles_json', '') or 'null')
    except ValueError:
        profiles = None
    return profiles if isinstance(profiles, list) else None


def saveSelectedProfiles(ids):
    util.setSetting('local_profiles_json', json.dumps(list(ids)))


def fetchAccounts(server):
    """
    Server-side account profiles ({id, name, thumb}). The PMS lists every account it has
    ever tracked - home users and shared users alike - with nothing to tell them apart,
    hence the manual curation below.
    """
    from plexnet import plexrequest

    try:
        req = plexrequest.PlexRequest(server, '/accounts')
        data = ElementTree.fromstring(req.getToStringWithTimeout(PROBE_TIMEOUT))
    except Exception:
        util.DEBUG_LOG('Local mode: no user accounts available from {0}', repr(server.name))
        return []

    accounts = []
    for acc in data.findall('Account'):
        accountID = acc.attrib.get('id')
        # id 0 is the PMS' "unattributed" pseudo account
        if not accountID or accountID == '0':
            continue
        accounts.append({'id': accountID,
                         'name': acc.attrib.get('name') or accountID,
                         'thumb': acc.attrib.get('thumb') or ''})
    return accounts


def chooseProfiles(server, accounts=None):
    """
    Let the user pick which of the server's account profiles to show on this device.
    Returns the selected ids, or None if cancelled.
    """
    accounts = fetchAccounts(server) if accounts is None else accounts
    if not accounts:
        return None

    stored = getSelectedProfiles() or []
    preselect = [i for i, acc in enumerate(accounts) if acc['id'] in stored]

    selection = xbmcgui.Dialog().multiselect(T(35038, 'Which users do you want to use on this device?'),
                                             [acc['name'] for acc in accounts],
                                             preselect=preselect)
    if selection is None:
        return None

    ids = [accounts[i]['id'] for i in selection]
    saveSelectedProfiles(ids)
    util.DEBUG_LOG('Local mode: {0} of {1} user profiles selected', len(ids), len(accounts))
    return ids


def validateProfileToken(server, token, isOwnerProfile):
    """
    Returns (reachable, mismatch). A server that allows unauthenticated access on the LAN
    ignores unknown tokens entirely, so status codes alone can't prove a token is genuine.
    The owner-only /myplex/account endpoint does discriminate though: real managed-user
    tokens get 403 there, while bogus tokens (and the owner's own) get 200 - which is
    exactly the case that would otherwise silently serve the wrong user's library.
    """
    address = server.activeConnection and server.activeConnection.address
    if not address:
        return False, False

    headers = {'X-Plex-Token': token}
    try:
        if requests.get(address + '/', headers=headers, timeout=PROBE_TIMEOUT).status_code != 200:
            return False, False
        tokenIsOwner = requests.get(address + '/myplex/account', headers=headers,
                                    timeout=PROBE_TIMEOUT).status_code == 200
    except Exception:
        return False, False

    return True, bool(tokenIsOwner) != bool(isOwnerProfile)


def isAccountLess():
    """Local mode without any plex.tv account behind it."""
    from plexnet import plexapp

    account = plexapp.ACCOUNT
    return bool(plexapp.util.LOCAL_MODE and not account.isSignedIn and not account.authToken)


def needsProfileToken(user, server=None):
    """
    Account-less local mode only: has this profile no server token yet, and haven't we
    asked for one before?
    """
    from plexnet import plexapp

    account = plexapp.ACCOUNT
    if not isAccountLess():
        return False

    server = server or plexapp.SERVERMANAGER.selectedServer
    if not server:
        return False

    stored = account.loadLocalUsers().get(str(user.id), {})
    return not stored.get('serverTokens', {}).get(server.uuid) and not stored.get('tokenPrompted')


def promptProfileToken(user, server=None):
    """
    Ask for a profile's server access token, so this user really is that user against the
    PMS. Without one every request is unauthenticated, which the server answers with the
    owner's view - so skipping is allowed, but it's not a real user switch.
    """
    from plexnet import plexapp

    account = plexapp.ACCOUNT
    server = server or plexapp.SERVERMANAGER.selectedServer
    if not server:
        return None

    isOwnerProfile = str(user.id) == '1'

    while True:
        token = xbmcgui.Dialog().input(T(35039, 'Plex token for {0} (optional)').format(user.title), '')
        if not token:
            # remember the skip, so picking this user doesn't ask again every time
            account.cacheLocalUser(user.id, tokenPrompted=True)
            return None

        reachable, mismatch = validateProfileToken(server, token, isOwnerProfile)
        if reachable and not mismatch:
            account.cacheLocalUser(user.id, serverTokens={server.uuid: token}, tokenPrompted=True)
            util.DEBUG_LOG('Local mode: stored server token for profile {0}', user.id)
            return token

        if mismatch:
            message = T(35040, 'That token does not belong to {0}.').format(user.title)
        else:
            message = T(35041, 'The server did not accept that token.')

        if not xbmcgui.Dialog().yesno(T(32427, 'Failed'), message,
                                      nolabel=T(32337, 'Cancel'), yeslabel=T(35032, 'Try again')):
            account.cacheLocalUser(user.id, tokenPrompted=True)
            return None


def seedUsersFromServer(server=None, reselect=False):
    """
    Account-less local mode: seed selectable user profiles from the PMS /accounts endpoint.
    The server lists every account it knows (home users and shared users alike, with nothing
    to tell them apart), so the user curates the list once; the selection is remembered.
    A profile only becomes a real identity once a server token is supplied for it - without
    one the PMS answers unauthenticated requests with the owner's view.
    """
    from plexnet import plexapp, myplexaccount

    account = plexapp.ACCOUNT
    if account.isSignedIn or (account.homeUsers and not reselect):
        return

    server = server or plexapp.SERVERMANAGER.selectedServer
    if not server:
        return

    accounts = fetchAccounts(server)
    if not accounts:
        return

    selected = getSelectedProfiles()
    if selected is None or reselect:
        # first run (or an explicit refresh): let the user pick who lives on this device
        firstRun = selected is None
        selected = chooseProfiles(server, accounts)
        if selected is None:
            if firstRun:
                # remember the decline, so this isn't asked on every start; the user menu
                # can bring the picker back
                saveSelectedProfiles([])
            return

    accounts = [acc for acc in accounts if acc['id'] in selected]

    users = []
    for acc in accounts:
        accountID = acc['id']
        user = myplexaccount.HomeUser({
            'id': accountID,
            'title': acc['name'],
            'thumb': acc['thumb'],
            'admin': accountID == '1' and '1' or '0',
            'restricted': '0',
            'protected': '0',
        })
        user.isAdmin = accountID == '1'
        user.isManaged = False
        user.isProtected = False
        users.append(user)

    if users:
        util.DEBUG_LOG('Local mode: seeded {0} user profiles from {1}', len(users), repr(server.name))
        account.homeUsers = users
        if not account.ID or account.ID not in [u.id for u in users]:
            account.ID = users[0].id
            account.title = users[0].title
            account.serverTokens = account.loadLocalUsers().get(str(users[0].id), {}).get('serverTokens', {})
        account.saveState()
