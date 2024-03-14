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

ACCOUNT = None


class HomeUser(util.AttributeDict):
    pass


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
        self.isSignedIn = False
        self.isOffline = False
        self.isExpired = False
        self.isPlexPass = False
        self.isManaged = False
        self.isSecure = False
        self.hasQueue = False

        self.isAdmin = False
        self.switchUser = False
        self.forceResourceRefresh = False

        self.adminHasPlexPass = False

        self.lastHomeUserUpdate = None
        self.homeUsers = []

    def init(self):
        self.loadState()

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
            'homeUsers': self.homeUsers,
            'lastHomeUserUpdate': self.lastHomeUserUpdate
        }

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
                self.homeUsers = [HomeUser(data) for data in obj.get('homeUsers', [])]
                if self.homeUsers:
                    util.LOG("cached home users: {0} (last update: {1})".format(self.homeUsers,
                                                                                self.lastHomeUserUpdate))

    def verifyAccount(self):
        if self.authToken:
            request = myplexrequest.MyPlexRequest("/users/account")
            context = request.createRequestContext("account", callback.Callable(self.onAccountResponse),
                                                   timeout=util.LONG_TIMEOUT)
            util.APP.startRequest(request, context)
        else:
            util.APP.clearInitializer("myplex")

    def logState(self):
        util.LOG("Authenticated as {0}:{1}".format(self.ID, repr(self.title)))
        util.LOG("SignedIn: {0}".format(self.isSignedIn))
        util.LOG("Offline: {0}".format(self.isOffline))
        util.LOG("Authenticated: {0}".format(self.isAuthenticated))
        util.LOG("PlexPass: {0}".format(self.isPlexPass))
        util.LOG("Managed: {0}".format(self.isManaged))
        util.LOG("Protected: {0}".format(self.isProtected))
        util.LOG("Admin: {0}".format(self.isAdmin))
        util.LOG("AdminPlexPass: {0}".format(self.adminHasPlexPass))

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
            self.thumb = data.attrib.get('thumb')
            self.authToken = data.attrib.get('authenticationToken')
            self.isPlexPass = (data.find('subscription') is not None and data.find('subscription').attrib.get('active') == '1')
            self.isManaged = data.attrib.get('restricted') == '1'
            self.isSecure = data.attrib.get('secure') == '1'
            self.hasQueue = bool(data.attrib.get('queueEmail'))

            # PIN
            if data.attrib.get('pin'):
                self.pin = data.attrib.get('pin')
            else:
                self.pin = None
            self.isProtected = bool(self.pin)

            # update the list of users in the home
            # Cache home users forever
            epoch = time.time()

            if self.lastHomeUserUpdate:
                util.DEBUG_LOG(
                    "Skipping home user update (updated {0} seconds ago)".format(epoch - self.lastHomeUserUpdate))
            else:
                self.updateHomeUsers(use_async=bool(self.homeUsers))

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
        self.isPlexPass = False
        self.adminHasPlexPass = False
        self.isManaged = False
        self.isSecure = False
        self.isExpired = expired

        # Clear the saved resources
        util.INTERFACE.clearRegistry("mpaResources", "xml_cache")

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
                                               timeout=util.LONG_TIMEOUT)
        if self.isOffline:
            context.timeout = self.isOffline and asyncadapter.AsyncTimeout(1).setConnectTimeout(1)
        util.APP.startRequest(request, context, {})

    def refreshAccount(self):
        if not self.authToken:
            return
        self.validateToken(self.authToken, False)

    def updateHomeUsers(self, use_async=False):
        # Ignore request and clear any home users we are not signed in
        if not self.isSignedIn:
            self.homeUsers = []
            if self.isOffline:
                self.homeUsers.append(MyPlexAccount())

            self.lastHomeUserUpdate = None
            return

        req = myplexrequest.MyPlexRequest("/api/home/users")
        if use_async:
            context = req.createRequestContext("home_users", callback.Callable(self.onHomeUsersUpdateResponse),
                                                timeout=util.LONG_TIMEOUT)
            if self.isOffline:
                context.timeout = self.isOffline and asyncadapter.AsyncTimeout(1).setConnectTimeout(1)
            util.APP.startRequest(req, context)
        else:
            self.onHomeUsersUpdateResponse(req, None, None)

    def onHomeUsersUpdateResponse(self, request, response, context):
        """
        this can either be called with a given request, which will lead to a synchronous request, or as a
        completionCallback from an async request
        """
        if response:
            data = response.getBodyXml()
        else:
            xml = request.getToStringWithTimeout(seconds=util.LONG_TIMEOUT)
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
                util.LOG("home users: {0}".format(self.homeUsers))

        self.lastHomeUserUpdate = time.time()
        self.saveState()

    def switchHomeUser(self, userId, pin=''):
        if userId == self.ID and self.isAuthenticated:
            return True

        # Offline support
        if self.isOffline:
            hashed = 'NONE'
            if pin and self.authToken:
                hashed = hashlib.sha256(pin + self.authToken).digest()

            if not self.isProtected or self.isAuthenticated or hashed == (self.pin or ""):
                util.DEBUG_LOG("OFFLINE access granted")
                self.isAuthenticated = True
                self.validateToken(self.authToken, True)
                return True
        else:
            # build path and post to myplex to swith the user
            path = '/api/home/users/{0}/switch'.format(userId)
            req = myplexrequest.MyPlexRequest(path)
            xml = req.postToStringWithTimeout({'pin': pin}, seconds=util.LONG_TIMEOUT)
            try:
                data = ElementTree.fromstring(xml)
            except:
                return False

            if data.attrib.get('authenticationToken'):
                self.isAuthenticated = True
                # validate the token (trigger change:user) on user change or channel startup
                if userId != self.ID or not locks.LOCKS.isLocked("idleLock"):
                    self.validateToken(data.attrib.get('authenticationToken'), True,
                                       force_resource_refresh=plexapp.SERVERMANAGER.reachabilityNeverTested)
                return True

        return False

    def isActive(self):
        return self.isSignedIn or self.isOffline


ACCOUNT = MyPlexAccount()
