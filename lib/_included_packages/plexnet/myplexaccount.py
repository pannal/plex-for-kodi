from __future__ import absolute_import
import json
import time
import hashlib
from xml.etree import ElementTree

from . import plexapp
from . import myplexrequest
from . import locks
from . import callback
from . import asyncadapter

from . import util

from .exceptions import UserSwitchForbiddenException

ACCOUNT = None


class HomeUser(util.AttributeDict):
    def __repr__(self):
        return '<{0}:{1}:{2} (admin: {3})>'.format(self.__class__.__name__, self.id,
                                                   self.get('title', 'None').encode('utf8'), self.get('admin', 0))


class MyPlexAccount(object):
    def __init__(self):
        # Strings
        self.ID = None
        self.title = None
        self.username = None
        self.thumb = None
        self.email = None
        self.authToken = None
        self.pin = None
        self.thumb = None

        # Booleans
        self.isAuthenticated = util.INTERFACE.getPreference('auto_signin', False)
        self.cacheHomeUsers = util.INTERFACE.getPreference('cache_home_users', True)
        self.isSignedIn = False
        self.isOffline = False
        self.isExpired = False
        self.isPlexPass = False
        self.isManaged = False
        self.isSecure = False
        self.hasQueue = False

        self.isAdmin = False
        # only ever assigned from saved state or a plex.tv response, so without either
        # (fresh install straight into account-less local mode) it wouldn't exist at all
        self.isProtected = False
        self.switchUser = False
        self.forceResourceRefresh = False

        # local mode: the current user's per-server access tokens ({machineIdentifier: token}),
        # loaded from the LocalUsers registry on setLocal()/local user switches
        self.serverTokens = {}

        self.adminHasPlexPass = False

        self.lastHomeUserUpdate = None
        self.revalidatePlexPass = False
        self.homeUsers = []

        # defaultSubtitleAccessibility: 0 = prefer non SDH, 1 = prefer SDH, 2 = only SDH, 3 = only non SDH
        # defaultSubtitleForced: 0 = prefer non forced, 1 = prefer forced, 2 = only forced, 3 = only non forced
        self.subtitlesSDH = 0
        self.subtitlesForced = 0
        # empty = user has not set a preferred subtitle language (distinct from explicitly choosing one);
        # consumers that need a concrete language must fall back themselves.
        self.subtitlesLanguage = ''
        # Plex only allows a single "Preferred Audio Language"; combined with the subtitle mode below
        # we infer native languages for subtitle suppression (see lib.language_util.getNativeLanguages).
        self.audioLanguage = ''
        # Plex "Subtitle Mode": 0 = manual, 1 = shown with foreign audio, 2 = always enabled.
        self.autoSelectSubtitle = 0

    def init(self):
        self.loadState()

    def setLocal(self):
        # Explicit local-only mode; keeps cached account/server state but never contacts plex.tv.
        # Reuses the isOffline plumbing (feature gates, home user handling).
        self.isOffline = True
        self.isSignedIn = False
        self.isAuthenticated = False
        self.serverTokens = self.loadLocalUsers().get(str(self.ID), {}).get('serverTokens', {})

        # consider a single, unprotected user authenticated
        if not self.isProtected:
            self.isAuthenticated = True

    def loadLocalUsers(self):
        """
        Per-user data usable without plex.tv: {userId: {'token': ..., 'pinHash': ..., 'thumb': ...}}
        Populated by harvestLocalUsers() while online and opportunistically on user switches.
        """
        try:
            return json.loads(util.INTERFACE.getRegistry("LocalUsers", None, "myplex") or '{}')
        except ValueError:
            return {}

    def saveLocalUsers(self, localUsers):
        util.INTERFACE.setRegistry("LocalUsers", json.dumps(localUsers), "myplex")

    def cacheLocalUser(self, userId, token=None, pin=None, thumb=None, serverTokens=None,
                       tokenPrompted=None):
        if not userId:
            return
        localUsers = self.loadLocalUsers()
        user = localUsers.get(str(userId), {})
        if token:
            user['token'] = token
            if pin:
                user['pinHash'] = hashlib.sha256((pin + token).encode('utf-8')).hexdigest()
        if thumb:
            user['thumb'] = thumb
        if serverTokens:
            # merge, so a token added for one server doesn't drop the others
            merged = user.get('serverTokens', {})
            merged.update(serverTokens)
            user['serverTokens'] = merged
        if tokenPrompted is not None:
            user['tokenPrompted'] = tokenPrompted
        localUsers[str(userId)] = user
        self.saveLocalUsers(localUsers)

    def fetchServerTokens(self, token):
        """
        While online, resolve a user's plex.tv token into their per-server access tokens
        ({machineIdentifier: accessToken}). The PMS validates access tokens against its own
        database, so they keep working in local mode - unlike plex.tv account tokens, which
        the transcoder rejects with a bare 400 for managed users.
        """
        serverTokens = {}
        try:
            import requests

            headers = util.getPlexHeaders()
            headers['X-Plex-Token'] = token
            r = requests.get('https://plex.tv/api/resources?includeHttps=1', headers=headers, timeout=10)
            data = ElementTree.fromstring(r.content)
            for device in data.findall('Device'):
                if 'server' not in (device.attrib.get('provides') or ''):
                    continue
                cid = device.attrib.get('clientIdentifier')
                accessToken = device.attrib.get('accessToken')
                if cid and accessToken:
                    serverTokens[cid] = accessToken
        except:
            util.WARN_LOG("Local mode: couldn't fetch server access tokens")
        return serverTokens

    def harvestLocalUsers(self):
        """
        While plex.tv is still reachable, collect per-user tokens for all non-protected home users
        so user switching keeps working in local mode. Protected users are only cached when they
        sign in/switch while online (we need their PIN to do better than an unlock).
        Avatars are cached to disk so no plex.tv image URL is ever handed to Kodi in local mode.
        """
        if self.isOffline or not self.isSignedIn:
            return

        import threading

        # collect per-user data in parallel (avatar + switch-token + server access tokens
        # each cost a full plex.tv round trip; doing 3 x users of them sequentially made
        # "Go local" take ages); the registry writes happen serialized below, as
        # cacheLocalUser read-modify-writes the whole LocalUsers blob
        results = {}

        def harvest(user):
            entry = {'thumb': self.downloadAvatar(user.id, user.thumb)}

            if user.id == self.ID:
                entry['token'] = self.authToken
                entry['serverTokens'] = self.fetchServerTokens(self.authToken)
            elif not user.isProtected:
                try:
                    path = '/api/home/users/{0}/switch'.format(user.id)
                    req = myplexrequest.MyPlexRequest(path)
                    res = req.postToStringWithTimeout({'pin': ''}, timeout=util.PLEXTV_TIMEOUT)
                    data = ElementTree.fromstring(res)
                    token = data.attrib.get('authenticationToken')
                    if token:
                        entry['token'] = token
                        entry['serverTokens'] = self.fetchServerTokens(token)
                        util.DEBUG_LOG("Local mode: harvested token for home user {0}", user.id)
                except:
                    util.WARN_LOG("Local mode: couldn't harvest token for home user {0}", user.id)

            results[user.id] = entry

        users = [u for u in self.homeUsers if u.id != self.ID]
        if not any(u.id == self.ID for u in self.homeUsers):
            users.append(util.AttributeDict(id=self.ID, thumb=self.thumb, isProtected=self.isProtected))
        else:
            users.append(self.getHomeUser(self.ID))

        threads = [threading.Thread(target=harvest, args=(user,), name='localharvest') for user in users]
        for t in threads:
            t.start()
        for t in threads:
            t.join(30)

        for userId, entry in results.items():
            self.cacheLocalUser(userId, token=entry.get('token'),
                                thumb=entry.get('thumb'), serverTokens=entry.get('serverTokens'))

    def downloadAvatar(self, userId, thumbUrl):
        if not thumbUrl or not thumbUrl.startswith('http') or not userId:
            return None

        try:
            import os
            import requests

            path = os.path.join(util.translatePath(util.ADDON.getAddonInfo('profile')), 'local_avatars')
            try:
                # racy when the harvest downloads avatars in parallel
                os.makedirs(path)
            except OSError:
                pass
            fn = os.path.join(path, '{0}.jpg'.format(userId))

            r = requests.get(thumbUrl, timeout=10)
            if r.status_code == 200:
                with open(fn, 'wb') as f:
                    f.write(r.content)
                return fn
        except:
            util.WARN_LOG("Local mode: couldn't cache avatar for user {0}", userId)
        return None

    def safeUserThumb(self, userId, thumb=''):
        """
        Returns the given thumb unchanged - except in local mode, where only cached local files
        may be used as avatars (or nothing at all): Kodi's texture cache fetches image URLs
        itself, outside of our transport layer, so a plex.tv URL must never leave this method.
        """
        if not util.LOCAL_MODE:
            return thumb
        return self.loadLocalUsers().get(str(userId), {}).get('thumb') or ''

    def saveState(self):
        obj = {
            'ID': self.ID,
            'title': self.title,
            'username': self.username,
            'email': self.email,
            'authToken': self.authToken,
            'pin': self.pin,
            'isPlexPass': self.isPlexPass,
            'isManaged': self.isManaged,
            'isAdmin': self.isAdmin,
            'isSecure': self.isSecure,
            'adminHasPlexPass': self.adminHasPlexPass,
            'thumb': self.thumb,
            'lastHomeUserUpdate': self.lastHomeUserUpdate,
            'subtitlesSDH': self.subtitlesSDH,
            'subtitlesForced': self.subtitlesForced,
            'subtitlesLanguage': self.subtitlesLanguage,
            'audioLanguage': self.audioLanguage,
            'autoSelectSubtitle': self.autoSelectSubtitle,
        }

        if self.cacheHomeUsers:
            obj["homeUsers"] = self.homeUsers

        util.INTERFACE.setRegistry("MyPlexAccount", json.dumps(obj), "myplex")

    def loadState(self):
        # Look for the new JSON serialization. If it's not there, look for the
        # old token and Plex Pass values.

        util.APP.addInitializer("myplex")

        jstring = util.INTERFACE.getRegistry("MyPlexAccount", None, "myplex")

        if jstring:
            try:
                obj = json.loads(jstring)
            except:
                util.ERROR()
                obj = None

            if obj:
                self.ID = obj.get('ID') or self.ID
                self.title = obj.get('title') or self.title
                self.username = obj.get('username') or self.username
                self.email = obj.get('email') or self.email
                self.authToken = obj.get('authToken') or self.authToken
                self.pin = obj.get('pin') or self.pin
                self.isPlexPass = obj.get('isPlexPass') or self.isPlexPass
                self.isManaged = obj.get('isManaged') or self.isManaged
                self.isAdmin = obj.get('isAdmin') or self.isAdmin
                self.isSecure = obj.get('isSecure') or self.isSecure
                self.isProtected = bool(obj.get('pin'))
                self.adminHasPlexPass = obj.get('adminHasPlexPass') or self.adminHasPlexPass
                self.thumb = obj.get('thumb')
                self.lastHomeUserUpdate = obj.get('lastHomeUserUpdate')
                self.subtitlesSDH = obj.get('subtitlesSDH', 0)
                self.subtitlesForced = obj.get('subtitlesForced', 0)
                self.subtitlesLanguage = obj.get('subtitlesLanguage', '')
                self.audioLanguage = obj.get('audioLanguage', '')
                self.autoSelectSubtitle = obj.get('autoSelectSubtitle', 0)
                if self.cacheHomeUsers:
                    self.homeUsers = [HomeUser(data) for data in obj.get('homeUsers', [])]
                    self.setAdminByCHU()
                if self.homeUsers:
                    util.LOG("cached home users: {0} (last update: {1})".format(self.homeUsers,
                                                                                self.lastHomeUserUpdate))
                util.APP.trigger("loaded:cached_user", account=None)

    def setAdminByCHU(self):
        for user in self.homeUsers:
            if user.id == self.ID:
                self.isAdmin = user.isAdmin

    def verifyAccount(self):
        if self.authToken:
            request = myplexrequest.MyPlexRequest("/users/account")
            context = request.createRequestContext("account", callback.Callable(self.onAccountResponse),
                                                   timeout=util.PLEXTV_TIMEOUT)
            util.APP.startRequest(request, context)
        else:
            util.APP.clearInitializer("myplex")

    def logState(self):
        util.LOG("Authenticated as {0}:{1}", self.ID, repr(self.title))
        util.LOG("SignedIn: {0}", self.isSignedIn)
        util.LOG("Offline: {0}", self.isOffline)
        util.LOG("Authenticated: {0}", self.isAuthenticated)
        util.LOG("PlexPass: {0}", self.isPlexPass)
        util.LOG("Managed: {0}", self.isManaged)
        util.LOG("Protected: {0}", self.isProtected)
        util.LOG("Admin: {0}", self.isAdmin)
        util.LOG("AdminPlexPass: {0}", self.adminHasPlexPass)
        util.LOG("subtitlesSDH: {0}", self.subtitlesSDH)
        util.LOG("subtitlesForced: {0}", self.subtitlesForced)
        util.LOG("subtitlesLanguage: {0}", self.subtitlesLanguage)
        util.LOG("audioLanguage: {0}", self.audioLanguage)
        util.LOG("autoSelectSubtitle: {0}", self.autoSelectSubtitle)

    def getHomeSubscription(self):
        """
        This gets the state of the plex home subscription, which is easier to determine than using a combination of
        isAdmin and adminHasPlexPass, especially when caching home users.
        """
        try:
            req = myplexrequest.MyPlexRequest("/api/v2/home")
            xml = req.getToStringWithTimeout(timeout=util.PLEXTV_TIMEOUT)
            data = ElementTree.fromstring(xml)
            return data.attrib.get('subscription') == '1'
        except:
            util.LOG("Couldn't get Plex Home info")
            return
        return False

    def refreshSubscription(self):
        ret = self.getHomeSubscription()
        if isinstance(ret, bool):
            self.isPlexPass = ret

    def onAccountResponse(self, request, response, context):
        oldId = self.ID

        if response.isSuccess():
            data = response.getBodyXml()

            # The user is signed in
            self.isSignedIn = True
            self.isOffline = False
            self.ID = data.attrib.get('id')
            self.title = data.attrib.get('title')
            self.username = data.attrib.get('username')
            self.email = data.attrib.get('email')
            self.thumb = data.attrib.get('thumb').split("?")[0]
            self.authToken = data.attrib.get('authenticationToken')
            self.isPlexPass = self.isPlexPass or \
                (data.find('subscription') is not None and
                 data.find('subscription').attrib.get('active') == '1')
            self.isManaged = data.attrib.get('restricted') == '1'
            self.isSecure = data.attrib.get('secure') == '1'
            self.hasQueue = bool(data.attrib.get('queueEmail'))

            # profile settings
            prof = data.find('profile_settings')
            self.subtitlesSDH = int(prof.attrib.get('default_subtitle_accessibility', 0))
            self.subtitlesForced = int(prof.attrib.get('default_subtitle_forced', 0))
            self.subtitlesLanguage = str(prof.attrib.get('default_subtitle_language', ''))
            self.audioLanguage = str(prof.attrib.get('default_audio_language', ''))
            # Plex "Subtitle Mode" (auto_select_subtitle): 0 = manually selected,
            # 1 = shown with foreign audio, 2 = always enabled (confirmed). Only mode 1 implies
            # suppressing same-language subtitles, which is what our native-languages logic derives from.
            self.autoSelectSubtitle = int(prof.attrib.get('auto_select_subtitle', 0))

            # PIN
            if data.attrib.get('pin'):
                self.pin = data.attrib.get('pin')
            else:
                self.pin = None
            self.isProtected = bool(self.pin)

            # update the list of users in the home
            # Cache home users forever
            epoch = time.time()

            # never automatically update home users if we have some.
            # if we've never seen any, check once a week
            if (self.lastHomeUserUpdate and self.homeUsers) or \
                    (self.lastHomeUserUpdate and not self.homeUsers and epoch - self.lastHomeUserUpdate < 604800):
                util.DEBUG_LOG(
                    "Skipping home user update (updated {0} seconds ago)".format(epoch - self.lastHomeUserUpdate))
            else:
                self.updateHomeUsers(use_async=bool(self.homeUsers))

            if bool(self.homeUsers):
                self.setAdminByCHU()

            # revalidate plex home subscription state after switching home user
            if self.revalidatePlexPass and self.homeUsers:
                self.refreshSubscription()
                self.revalidatePlexPass = False

            if self.isAdmin and self.isPlexPass:
                self.adminHasPlexPass = True

            # consider a single, unprotected user authenticated
            if not self.isAuthenticated and not self.isProtected and len(self.homeUsers) <= 1:
                self.isAuthenticated = True

            self.logState()

            self.saveState()
            util.MANAGER.publish()

            if oldId != self.ID or (self.switchUser and not self.forceResourceRefresh):
                util.DEBUG_LOG("User changed, deferring refresh resources (force=False, "
                               "switchUser: {}, forceResourceRefresh: {})".format(self.switchUser,
                                                                                  self.forceResourceRefresh))
            else:
                util.DEBUG_LOG("User selected, refreshing resources (force=False)")
                plexapp.refreshResources()
                self.forceResourceRefresh = False

        elif response.getStatus() >= 400 and response.getStatus() < 500:
            # The user is specifically unauthorized, clear everything
            util.WARN_LOG("Sign Out: User is unauthorized")
            self.signOut(True)
        else:
            # Unexpected error, keep using whatever we read from the registry
            util.WARN_LOG("Unexpected response from plex.tv ({0}), switching to OFFLINE mode".format(response.getStatus()))
            self.logState()
            self.isOffline = True
            # consider a single, unprotected user authenticated
            if not self.isAuthenticated and not self.isProtected:
                self.isAuthenticated = True

        util.APP.clearInitializer("myplex")
        # Logger().UpdateSyslogHeader()  # TODO: ------------------------------------------------------------------------------------------------------IMPLEMENT

        if oldId != self.ID or self.switchUser:
            self.switchUser = None
            util.APP.trigger("change:user", account=self, reallyChanged=oldId != self.ID)

        util.APP.trigger("account:response")

    def signOut(self, expired=False):
        # Strings
        self.ID = None
        self.title = None
        self.username = None
        self.email = None
        self.authToken = None
        self.pin = None
        self.lastHomeUserUpdate = None
        self.homeUsers = []

        # Booleans
        self.isSignedIn = False
        #self.isPlexPass = False
        #self.adminHasPlexPass = False
        self.isManaged = False
        self.isSecure = False
        self.isExpired = expired

        # Clear the saved resources
        util.INTERFACE.clearRegistry("mpaResources", "xml_cache")

        # Clear harvested local mode user tokens
        util.INTERFACE.clearRegistry("LocalUsers", "myplex")
        self.serverTokens = {}

        # Remove all saved servers
        plexapp.SERVERMANAGER.clearServers()

        # Enable the welcome screen again
        util.INTERFACE.setPreference("show_welcome", True)

        util.APP.trigger("change:user", account=self, reallyChanged=True)

        self.saveState()

    def hasPlexPass(self):
        return self.isPlexPass or self.adminHasPlexPass

    def validateToken(self, token, switch_user=False, force_resource_refresh=False):
        self.authToken = token
        self.switchUser = switch_user
        self.forceResourceRefresh = force_resource_refresh

        request = myplexrequest.MyPlexRequest("/users/sign_in.xml")
        context = request.createRequestContext("sign_in", callback.Callable(self.onAccountResponse),
                                               timeout=util.PLEXTV_TIMEOUT)
        if self.isOffline:
            context.timeout = self.isOffline and asyncadapter.AsyncTimeout(1).setConnectTimeout(1)
        util.APP.startRequest(request, context, {})

    def refreshAccount(self):
        if not self.authToken:
            return
        self.validateToken(self.authToken, False)

    def updateHomeUsers(self, use_async=False, refreshSubscription=False):
        # Ignore request and clear any home users we are not signed in
        if not self.isSignedIn:
            # explicit local mode keeps the cached home user list for local user switching
            if not (util.LOCAL_MODE and self.homeUsers):
                self.homeUsers = []
                if self.isOffline:
                    self.homeUsers.append(MyPlexAccount())

            self.lastHomeUserUpdate = None
            return

        req = myplexrequest.MyPlexRequest("/api/home/users")
        if use_async:
            context = req.createRequestContext("home_users", callback.Callable(self.onHomeUsersUpdateResponse),
                                                timeout=util.PLEXTV_TIMEOUT)
            if self.isOffline:
                context.timeout = self.isOffline and asyncadapter.AsyncTimeout(1).setConnectTimeout(1)
            util.APP.startRequest(req, context)
        else:
            self.onHomeUsersUpdateResponse(req, None, None)

        if refreshSubscription:
            self.refreshSubscription()
            self.logState()
            self.saveState()

    def onHomeUsersUpdateResponse(self, request, response, context):
        """
        this can either be called with a given request, which will lead to a synchronous request, or as a
        completionCallback from an async request
        """
        if response:
            data = response.getBodyXml()
        else:
            xml = request.getToStringWithTimeout(timeout=util.PLEXTV_TIMEOUT)
            data = ElementTree.fromstring(xml)

        oldHU = self.homeUsers[:]
        if data.attrib.get('size') and data.find('User') is not None:
            self.homeUsers = []
            for user in data.findall('User'):
                homeUser = HomeUser(user.attrib)
                homeUser.isAdmin = homeUser.admin == "1"
                homeUser.isManaged = homeUser.restricted == "1"
                homeUser.isProtected = homeUser.protected == "1"
                self.homeUsers.append(homeUser)

            # set admin attribute for the user
            self.isAdmin = False
            if self.homeUsers:
                for user in self.homeUsers:
                    if self.ID == user.id:
                        self.isAdmin = str(user.admin) == "1"
                        break

            if oldHU != self.homeUsers:
                util.LOG("home users: {0}", self.homeUsers)

        self.lastHomeUserUpdate = time.time()
        self.saveState()

    def getHomeUser(self, userId):
        if not self.homeUsers:
            return None
        for user in self.homeUsers:
            if user.id == userId:
                return user

    def switchHomeUser(self, userId, pin='', silent=False):
        if userId == self.ID and self.isAuthenticated:
            return True

        # Offline/local support
        if self.isOffline:
            localUser = self.loadLocalUsers().get(str(userId), {})
            homeUser = self.getHomeUser(userId)
            token = localUser.get('token') or self.authToken

            if homeUser is not None and userId != self.ID:
                protected = homeUser.isProtected
            else:
                protected = self.isProtected

            granted = not protected or self.isAuthenticated
            if not granted and pin and token:
                hashed = hashlib.sha256((pin + token).encode('utf-8')).hexdigest()
                granted = bool(localUser.get('pinHash')) and localUser.get('pinHash') == hashed

            if granted:
                util.DEBUG_LOG("OFFLINE/LOCAL access granted for {0}", userId)
                oldId = self.ID
                self.isAuthenticated = True
                self.serverTokens = localUser.get('serverTokens', {})

                # account-less local mode has no plex.tv token at all; the profile's server
                # token (if any) is the whole identity there
                accountLess = not self.authToken and not self.isSignedIn
                hasIdentity = bool(localUser.get('token') or localUser.get('serverTokens'))

                if (hasIdentity or accountLess) and userId != self.ID and homeUser is not None:
                    # real switch: adopt the harvested identity/token; the PMS validates home user
                    # tokens against its own database, no plex.tv needed
                    self.ID = userId
                    self.title = homeUser.get('title')
                    self.username = homeUser.get('username') or self.username
                    self.thumb = localUser.get('thumb') or homeUser.get('thumb')
                    self.isAdmin = homeUser.isAdmin
                    self.isManaged = homeUser.isManaged
                    self.isProtected = homeUser.isProtected

                if token:
                    self.validateToken(token, True)
                    # the transport block answers the validation synchronously, so
                    # onAccountResponse has already consumed switchUser; restore it -
                    # callers check it to detect an actual switch
                    self.switchUser = True
                    # only save after validateToken has adopted the token - saving earlier
                    # persists the new identity paired with the previous user's token
                    self.saveState()
                else:
                    # nothing to validate against plex.tv - announce the switch ourselves
                    self.switchUser = True
                    self.saveState()
                    util.APP.trigger("change:user", account=self, reallyChanged=oldId != self.ID)
                    plexapp.refreshResources(True)
                return True
        else:
            # build path and post to myplex to switch the user
            path = '/api/home/users/{0}/switch'.format(userId)
            req = myplexrequest.MyPlexRequest(path)
            res = req.postToStringWithTimeout({'pin': pin}, timeout=util.PLEXTV_TIMEOUT, return_on_status_code=True)
            if not silent and type(res) == int and res == 401:
                raise UserSwitchForbiddenException()
            try:
                data = ElementTree.fromstring(res)
            except:
                return False

            if data.attrib.get('authenticationToken'):
                self.isAuthenticated = True
                # keep the per-user token/PIN cache fresh for local mode
                self.cacheLocalUser(userId, token=data.attrib.get('authenticationToken'), pin=pin or None,
                                    serverTokens=self.fetchServerTokens(data.attrib.get('authenticationToken')))
                # validate the token (trigger change:user) on user change or channel startup
                if userId != self.ID or not locks.LOCKS.isLocked("idleLock"):
                    self.revalidatePlexPass = True
                    self.validateToken(data.attrib.get('authenticationToken'), True,
                                       force_resource_refresh=plexapp.SERVERMANAGER.reachabilityNeverTested)
                return True

        return False

    def isActive(self):
        return self.isSignedIn or self.isOffline


ACCOUNT = MyPlexAccount()
