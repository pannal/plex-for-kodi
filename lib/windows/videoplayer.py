from __future__ import absolute_import

import math
import threading
import time
import traceback
import uuid

from kodi_six import xbmc
from kodi_six import xbmcgui

from lib import colors
from lib import kodijsonrpc
from lib import player
from lib import util
from lib.util import T
from plexnet.serverdecision import DecisionFailure
from . import busy
from . import dropdown
from . import kodigui
from . import opener
from . import pagination
from . import search
from . import windowutils
from .mixins.spoilers import SpoilersMixin
from .mixins.roles import RolesMixin

PASSOUT_PROTECTION_DURATION_SECONDS = 7200
PASSOUT_LAST_VIDEO_DURATION_MILLIS = 1200000


class RelatedPaginator(pagination.BaseRelatedPaginator):
    def readyForPaging(self):
        return self.parentWindow.postPlayInitialized

    def getData(self, offset, amount):
        return (self.parentWindow.prev or self.parentWindow.next).getRelated(offset=offset, limit=amount)


class OnDeckPaginator(pagination.MCLPaginator):
    initialPageSize = 8

    def readyForPaging(self):
        return self.parentWindow.postPlayInitialized

    thumbFallback = lambda self, rel: 'script.plex/thumb_fallbacks/{0}.png'.format(
                    rel.type in ('show', 'season', 'episode') and 'show' or 'movie')

    def prepareListItem(self, data, mli):
        mli.setProperty('progress', util.getProgressImage(mli.dataSource))
        mli.setProperty('unwatched', not mli.dataSource.isWatched and '1' or '')
        mli.setProperty('watched', mli.dataSource.isFullyWatched and '1' or '')

        if data.type in 'episode':
            mli.setLabel2(
                u'{0} \u2022 {1}'.format(T(32310, 'S').format(data.parentIndex), T(32311, 'E').format(data.index)))
        else:
            mli.setLabel2(data.year)

    def createListItem(self, ondeck):
        title = ondeck.grandparentTitle or ondeck.title
        if ondeck.type == 'episode':
            hide_spoilers = self.parentWindow.hideSpoilers(ondeck, use_cache=False)
            thumb_opts = self.parentWindow.getThumbnailOpts(ondeck, hide_spoilers=hide_spoilers)
            thumb = ondeck.thumb.asTranscodedImageURL(*self.parentWindow.ONDECK_DIM, **thumb_opts)
        else:
            thumb = ondeck.defaultArt.asTranscodedImageURL(*self.parentWindow.ONDECK_DIM)

        mli = kodigui.ManagedListItem(title or '', thumbnailImage=thumb, data_source=ondeck)
        if mli:
            return mli

    def getData(self, offset, amount):
        data = (self.parentWindow.prev or self.parentWindow.next).sectionOnDeck(offset=offset, limit=amount)
        skipRKs = []
        if self.parentWindow.next:
            skipRKs.append(self.parentWindow.next.ratingKey)
        if self.parentWindow.prev:
            skipRKs.append(self.parentWindow.prev.ratingKey)
        if skipRKs:
            return list(filter(lambda x: x.ratingKey not in skipRKs, data))
        return data


class VideoPlayerWindow(kodigui.ControlledWindow, windowutils.UtilMixin, RolesMixin, SpoilersMixin):
    xmlFile = 'script-plex-video_player.xml'
    path = util.ADDON.getAddonInfo('path')
    theme = 'Main'
    res = '1080i'
    width = 1920
    height = 1080

    NEXT_DIM = util.scaleResolution(537, 303)
    PREV_DIM = util.scaleResolution(462, 259)
    ONDECK_DIM = util.scaleResolution(329, 185)
    RELATED_DIM = util.scaleResolution(268, 402)
    ROLES_DIM = util.scaleResolution(334, 334)

    OPTIONS_GROUP_ID = 200

    PREV_BUTTON_ID = 101
    NEXT_BUTTON_ID = 102

    ONDECK_LIST_ID = 400
    RELATED_LIST_ID = 401
    ROLES_LIST_ID = 403

    HOME_BUTTON_ID = 201
    SEARCH_BUTTON_ID = 202

    PLAYER_STATUS_BUTTON_ID = 204

    def __init__(self, *args, **kwargs):
        kodigui.ControlledWindow.__init__(self, *args, **kwargs)
        windowutils.UtilMixin.__init__(self)
        SpoilersMixin.__init__(self, *args, **kwargs)
        self.playQueue = kwargs.get('play_queue')
        self.video = kwargs.get('video')
        self.resume = bool(kwargs.get('resume'))

        if util.platformFlavor == "CoreELEC":
            self.defer_init = True

        self.postPlayMode = False
        self.prev = None
        self.playlist = None
        self.handler = None
        self.next = None
        self.videos = None
        self.trailer = None
        self.aborted = True
        self.timeout = None
        self.passoutProtection = 0
        self.postPlayInitialized = False
        self.relatedPaginator = None
        self.onDeckPaginator = None
        self.lastFocusID = None
        self.lastNonOptionsFocusID = None
        self.playBackStarted = False
        self.handleBGM = kwargs.get('bgm')
        self.lastItem = None
        self.earlyAbortRequested = False
        self.sessionID = None

    def doClose(self, force=False):
        util.DEBUG_LOG('VideoPlayerWindow: Closing')
        self.timeout = None
        self.relatedPaginator = None
        self.onDeckPaginator = None
        self.lastItem = None
        if self.earlyAbortRequested:
            player.PLAYER._ignorePlaybackFailure = True
            if player.PLAYER.isPlayingVideo():
                player.PLAYER.close()
                if player.PLAYER.handler:
                    player.PLAYER.handler.stoppedManually = True
                player.PLAYER.stop()

        kodigui.ControlledWindow.doClose(self)

        if player.PLAYER.handler:
            player.PLAYER.handler.sessionEnded()

    def onFirstInit(self):
        player.PLAYER.on('session.ended', self.sessionEnded)
        player.PLAYER.on('videowindow.closed', self.videoWindowClosed)
        player.PLAYER.on('av.started', self.playerPlaybackStarted)
        player.PLAYER.on('starting.video', self.onVideoStarting)
        player.PLAYER.on('started.video', self.onVideoStarted)
        player.PLAYER.on('changed.video', self.onVideoChanged)
        player.PLAYER.on('post.play', self.postPlay)
        player.PLAYER.on('change.background', self.changeBackground)

        self.sessionID = str(uuid.uuid4())

        self.onDeckListControl = kodigui.ManagedControlList(self, self.ONDECK_LIST_ID, 5)
        self.relatedListControl = kodigui.ManagedControlList(self, self.RELATED_LIST_ID, 5)
        self.rolesListControl = kodigui.ManagedControlList(self, self.ROLES_LIST_ID, 5)

        util.DEBUG_LOG('VideoPlayerWindow: Starting session (ID: {0})', self.sessionID)
        self.resetPassoutProtection()
        self.play(resume=self.resume)

    def onVideoStarting(self, *args, **kwargs):
        util.setGlobalProperty('ignore_spinner', '1')

    def onVideoStarted(self, *args, **kwargs):
        util.setGlobalProperty('ignore_spinner', '')

    def onVideoChanged(self, *args, **kwargs):
        #util.setGlobalProperty('ignore_spinner', '')
        pass

    def onReInit(self):
        util.DEBUG_LOG('VideoPlayerWindow: Reinitializing')
        if not self.earlyAbortRequested:
            self.setBackground()

    def onAction(self, action):
        try:
            if self.postPlayMode:
                controlID = self.getFocusId()

                self.cancelTimer()
                self.resetPassoutProtection()
                if action in(xbmcgui.ACTION_NAV_BACK, xbmcgui.ACTION_CONTEXT_MENU):
                    if not xbmc.getCondVisibility('ControlGroup({0}).HasFocus(0)'.format(self.OPTIONS_GROUP_ID)):
                        if not util.addonSettings.fastBack or action == xbmcgui.ACTION_CONTEXT_MENU:
                            self.lastNonOptionsFocusID = self.lastFocusID
                            self.setFocusId(self.OPTIONS_GROUP_ID)
                            return
                    else:
                        if self.lastNonOptionsFocusID and action == xbmcgui.ACTION_CONTEXT_MENU:
                            self.setFocusId(self.lastNonOptionsFocusID)
                            self.lastNonOptionsFocusID = None
                            return

                if action in(xbmcgui.ACTION_NAV_BACK, xbmcgui.ACTION_PREVIOUS_MENU):
                    self.doClose()
                    return

                if action in (xbmcgui.ACTION_NEXT_ITEM, xbmcgui.ACTION_PLAYER_PLAY):
                    self.playVideo()
                elif action == xbmcgui.ACTION_PREV_ITEM:
                    self.playVideo(prev=True)
                elif action == xbmcgui.ACTION_STOP:
                    self.doClose()

                if controlID == self.RELATED_LIST_ID:
                    if self.relatedPaginator.boundaryHit:
                        self.relatedPaginator.paginate()
                        return

                elif controlID == self.ONDECK_LIST_ID:
                    if self.onDeckPaginator.boundaryHit:
                        self.onDeckPaginator.paginate()
                        return

                    mli = self.onDeckListControl.getSelectedItem()
                    if not mli or mli.getProperty("is.boundary"):
                        return

                    lastItem = self.lastItem

                    if action in (xbmcgui.ACTION_MOVE_RIGHT, xbmcgui.ACTION_MOVE_LEFT) and lastItem:
                        items = self.onDeckPaginator.wrap(mli, lastItem, action)
                        xbmc.sleep(100)
                        if items:
                            # wrapped with new data
                            return True

                    if mli != self.lastItem and not mli.getProperty("is.boundary"):
                        self.lastItem = mli
            else:
                if action in(xbmcgui.ACTION_NAV_BACK, xbmcgui.ACTION_PREVIOUS_MENU, xbmcgui.ACTION_STOP):
                    util.DEBUG_LOG('VideoPlayerWindow: Abort requested, setting flag')
                    self.earlyAbortRequested = True
        except:
            util.ERROR()

        kodigui.ControlledWindow.onAction(self, action)

    def playerPlaybackStarted(self, *args, **kwargs):
        self.playBackStarted = True

        if self.earlyAbortRequested:
            util.DEBUG_LOG('VideoPlayerWindow: Abort flag set, closing')
            self.doClose()

    def onClick(self, controlID):
        if not self.postPlayMode:
            return

        timeoutCanceled = False
        if util.addonSettings.postplayCancel:
            timeoutCanceled = bool(self.timeout)
            self.cancelTimer()

        if controlID == self.HOME_BUTTON_ID:
            self.goHome()
        elif controlID == self.ONDECK_LIST_ID:
            self.openItem(self.onDeckListControl)
        elif controlID == self.RELATED_LIST_ID:
            self.openItem(self.relatedListControl)
        elif controlID == self.ROLES_LIST_ID:
            if not self.roleClicked():
                return
        elif controlID == self.PREV_BUTTON_ID:
            self.playVideo(prev=True)
        elif controlID == self.NEXT_BUTTON_ID:
            if not timeoutCanceled:
                self.playVideo()
        elif controlID == self.PLAYER_STATUS_BUTTON_ID:
            self.showAudioPlayer()
        elif controlID == self.SEARCH_BUTTON_ID:
            self.searchButtonClicked()

    def onFocus(self, controlID):
        if not self.postPlayMode:
            return

        self.lastFocusID = controlID

        if 399 < controlID < 500:
            self.setProperty('hub.focus', str(controlID - 400))
        else:
            self.setProperty('hub.focus', '')

        if xbmc.getCondVisibility('Control.HasFocus(101) | Control.HasFocus(102) | ControlGroup(200).HasFocus(0)'):
            self.setProperty('on.extras', '')
        elif xbmc.getCondVisibility('ControlGroup(60).HasFocus(0)'):
            self.setProperty('on.extras', '1')

    def searchButtonClicked(self):
        self.processCommand(search.dialog(self, section_id=self.prev.getLibrarySectionId() or None))

    def getRoleItemDDPosition(self, *args, **kwargs):
        y = 1000
        if xbmc.getCondVisibility('Control.IsVisible(500)'):
            y += 360
        if xbmc.getCondVisibility('Control.IsVisible(501)'):
            y += 520
        if xbmc.getCondVisibility('!String.IsEmpty(Window.Property(on.extras))'):
            y -= 300
        if xbmc.getCondVisibility('Integer.IsGreater(Window.Property(hub.focus),0) + Control.IsVisible(500)'):
            y -= 500
        if xbmc.getCondVisibility('Integer.IsGreater(Window.Property(hub.focus),1) + Control.IsVisible(501)'):
            y -= 500

        return super(VideoPlayerWindow, self).getRoleItemDDPosition(y=y, container_id="403")

    def setBackground(self):
        video = self.video if self.video else self.playQueue.current()
        self.windowSetBackground(video.defaultArt.asTranscodedImageURL(1920, 1080, opacity=60,
                                                                       background=colors.noAlpha.Background))

    def changeBackground(self, url, **kwargs):
        self.windowSetBackground(url)

    def sessionEnded(self, session_id=None, **kwargs):
        if session_id != self.sessionID:
            util.DEBUG_LOG('VideoPlayerWindow: Ignoring session end (ID: {0} - SessionID: {1})', self.sessionID, session_id)
            return

        util.DEBUG_LOG('VideoPlayerWindow: Session ended - closing (ID: {0})', self.sessionID)
        self.doClose()

    def videoWindowClosed(self, session_id=None, video=None, **kwargs):
        if session_id != self.sessionID:
            return

        video.clearCache()

    def play(self, resume=False, handler=None):
        self.hidePostPlay()

        player.PLAYER.dontRequeueBGM = True

        def anyOtherVPlayer():
            return any(list(filter(lambda x: x['playerid'] > 0, kodijsonrpc.rpc.Player.GetActivePlayers())))

        if player.PLAYER.isPlayingVideo():
            activePlayers = anyOtherVPlayer()
            if activePlayers:
                util.DEBUG_LOG("Stopping other active players: {}", activePlayers)
                xbmc.executebuiltin('PlayerControl(Stop)')
                ct = 0
                while player.PLAYER.isPlayingVideo() or anyOtherVPlayer():
                    if ct >= 50:
                        util.showNotification("Other player active", header=util.T(32448, 'Playback Failed!'))
                        break
                    util.MONITOR.waitForAbort(0.1)
                    ct += 1

                if ct >= 50:
                    self.doClose()
                    return
                util.MONITOR.waitForAbort(0.5)

        # wait for BGM to end if it's playing or queued
        if self.handleBGM:
            while not player.PLAYER.bgmPlaying and player.PLAYER.bgmStarting:
                util.DEBUG_LOG("Waiting for BGM to start as it has been queued")
                util.MONITOR.waitForAbort(0.1)

            if player.PLAYER.bgmPlaying:
                util.DEBUG_LOG("Stopping BGM before starting playback")
                player.PLAYER.stopAndWait()

            while player.PLAYER.bgmPlaying or player.PLAYER.isPlayingAudio():
                util.MONITOR.waitForAbort(0.1)

        self.setBackground()

        self.sessionID = self.sessionID or str(uuid.uuid4())

        try:
            if self.playQueue:
                player.PLAYER.playVideoPlaylist(self.playQueue, resume=resume or self.resume, session_id=self.sessionID,
                                                handler=handler)
            elif self.video:
                player.PLAYER.playVideo(self.video, resume=resume or self.resume, force_update=True, session_id=self.sessionID,
                                        handler=handler)
        except DecisionFailure:
            util.LOG("Can't play this media.")
            self.doClose()

        except Exception as e:
            util.LOG("Playback failed: {}", traceback.format_exc())
            self.doClose()

        util.DEBUG_LOG("VideoPlayerWindow: Playback initialized; returning from play()")


    def openItem(self, control=None, item=None):
        if not item:
            mli = control.getSelectedItem()
            if not mli:
                return
            item = mli.dataSource

        self.processCommand(opener.open(item, came_from="postplay"))

    def showPostPlay(self):
        self.postPlayMode = True
        self.setProperty('post.play', '1')

    def hidePostPlay(self):
        self.postPlayMode = False
        self.setProperty('post.play', '')
        self.setProperties((
            'post.play.background',
            'info.title',
            'info.duration',
            'info.summary',
            'info.date',
            'next.thumb',
            'next.title',
            'next.subtitle',
            'prev.thumb',
            'prev.title',
            'prev.subtitle',
            'related.header',
            'has.next'
        ), '')

        self.onDeckListControl.reset()
        self.relatedListControl.reset()
        self.rolesListControl.reset()

    @busy.dialog()
    def postPlay(self, video=None, playlist=None, handler=None, stoppedManually=False, **kwargs):
        util.DEBUG_LOG('VideoPlayer: Starting post-play')
        self.showPostPlay()
        self.prev = video
        self.playlist = playlist
        self.handler = handler

        self.getHubs()

        self.setProperty(
            'thumb.fallback', 'script.plex/thumb_fallbacks/{0}.png'.format(self.prev.type in ('show', 'season', 'episode') and 'show' or 'movie')
        )

        util.DEBUG_LOG('PostPlay: Showing video info')
        if self.next:
            self.next.reload(includeChapters=1, includeExtras=1, includeExtrasCount=10)

        self.relatedPaginator = RelatedPaginator(self.relatedListControl,
                                                 leaf_count=int((self.prev or self.next).relatedCount),
                                                 parent_window=self)

        vid = self.prev or self.next
        if vid.sectionOnDeckCount:
            self.onDeckPaginator = OnDeckPaginator(self.onDeckListControl,
                                                   leaf_count=int(vid.sectionOnDeckCount) - 1 if self.next else 0,
                                                   parent_window=self)

        self.setInfo()
        self.fillOnDeck()
        hasPrev = self.fillRelated()
        self.fillRoles(hasPrev)

        if not stoppedManually:
            self.startTimer()

        if self.next:
            self.setFocusId(self.NEXT_BUTTON_ID)
        else:
            self.setFocusId(self.PREV_BUTTON_ID)
        self.postPlayInitialized = True

    def resetPassoutProtection(self):
        self.passoutProtection = time.time() + PASSOUT_PROTECTION_DURATION_SECONDS

    def startTimer(self):
        if not util.getUserSetting('post_play_auto', True):
            util.DEBUG_LOG('Post play auto-play disabled')
            return

        if not self.next:
            return

        if time.time() > self.passoutProtection and self.prev.duration.asInt() > PASSOUT_LAST_VIDEO_DURATION_MILLIS:
            util.DEBUG_LOG('Post play auto-play skipped: Passout protection')
            return
        else:
            millis = (self.passoutProtection - time.time()) * 1000
            util.DEBUG_LOG('Post play auto-play: Passout protection in {0}',
                           lambda: util.durationToShortText(millis))

        self.timeout = time.time() + abs(util.addonSettings.postplayTimeout)
        util.DEBUG_LOG('Starting post-play timer until: %i' % self.timeout)
        threading.Thread(target=self.countdown).start()

    def cancelTimer(self):
        if self.timeout is not None:
            util.DEBUG_LOG('Canceling post-play timer')

        self.timeout = None
        self.setProperty('countdown', '')

    def countdown(self):
        while self.timeout and not util.MONITOR.waitForAbort(0.1):
            now = time.time()
            if self.timeout and now > self.timeout:
                self.timeout = None
                self.setProperty('countdown', '')
                util.DEBUG_LOG('Post-play timer finished')
                # This works. The direct method caused the OSD to be broken, possibly because it was triggered from another thread?
                # That was the only real difference I could see between the direct method and the user actually clicking the button.
                xbmc.executebuiltin('SendClick(,{0})'.format(self.NEXT_BUTTON_ID))
                # Direct method, causes issues with OSD
                # self.playVideo()
                break
            elif self.timeout is not None:
                cd = min(abs(util.addonSettings.postplayTimeout - 1), int((self.timeout or now) - now))
                base = 15 / float(util.addonSettings.postplayTimeout - 1)
                self.setProperty('countdown', str(15 - int(math.ceil(base*cd))))

    def getHubs(self):
        try:
            self.hubs = self.prev.postPlay()
        except:
            util.ERROR("No data - disconnected?", notify=True, time_ms=5000)
            self.doClose()
            return

        self.next = None

        if self.playlist:
            if self.prev != self.playlist.current():
                self.next = self.playlist.current()
            else:
                if self.prev.type == 'episode' and 'tv.upnext' in self.hubs:
                    self.next = self.hubs['tv.upnext'].items[-1]

        if self.next:
            self.setProperty('has.next', '1')

    def setInfo(self):
        hide_spoilers = False
        if self.next and self.next.type == "episode":
            hide_spoilers = self.hideSpoilers(self.next, use_cache=False)
        if self.next:
            self.setProperty(
                'post.play.background',
                util.backgroundFromArt(self.next.art, width=self.width, height=self.height)
            )
            if self.next.type == "episode" and hide_spoilers:
                if self.noTitles:
                    self.setProperty('info.title',
                                     u'{0} \u2022 {1}'.format(T(32310, 'S').format(self.next.parentIndex),
                                                              T(32311, 'E').format(self.next.index)))
                else:
                    self.setProperty('info.title', self.next.title)
                self.setProperty('info.summary', T(33008, ''))
            else:
                self.setProperty('info.title', self.next.title)
                self.setProperty('info.summary', self.next.summary)
            self.setProperty('info.duration', util.durationToText(self.next.duration.asInt()))

        if self.prev:
            self.setProperty(
                'post.play.background',
                util.backgroundFromArt(self.prev.art, width=self.width, height=self.height)
            )
            self.setProperty('prev.info.title', self.prev.title)
            self.setProperty('prev.info.duration', util.durationToText(self.prev.duration.asInt()))
            self.setProperty('prev.info.summary', self.prev.summary)

        if self.prev.type == 'episode':
            self.setProperty('related.header', T(32306, 'Related Shows'))
            if self.next:
                thumb_opts = {}
                if hide_spoilers:
                    thumb_opts = self.getThumbnailOpts(self.next, hide_spoilers=hide_spoilers)
                self.setProperty('next.thumb', self.next.thumb.asTranscodedImageURL(*self.NEXT_DIM, **thumb_opts))
                self.setProperty('info.date',
                                 util.cleanLeadingZeros(self.next.originallyAvailableAt.asDatetime('%B %d, %Y')))

                self.setProperty('next.title', self.next.grandparentTitle)
                self.setProperty(
                    'next.subtitle',
                    u'{0} \u2022 {1}'.format(T(32303, 'Season').format(self.next.parentIndex),
                                             T(32304, 'Episode').format(self.next.index))
                )
            if self.prev:
                self.setProperty('prev.thumb', self.prev.thumb.asTranscodedImageURL(*self.PREV_DIM))
                self.setProperty('prev.title', self.prev.grandparentTitle)
                self.setProperty(
                    'prev.subtitle', u'{0} \u2022 {1}'.format(T(32303, 'Season').format(self.prev.parentIndex),
                                                              T(32304, 'Episode').format(self.prev.index))
                )
                self.setProperty('prev.info.date', util.cleanLeadingZeros(self.prev.originallyAvailableAt.asDatetime('%B %d, %Y')))
        elif self.prev.type == 'movie':
            self.setProperty('related.header', T(32404, 'Related Movies'))
            if self.next:
                self.setProperty('next.thumb', self.next.defaultArt.asTranscodedImageURL(*self.NEXT_DIM))
                self.setProperty('info.date', self.next.year)

                self.setProperty('next.title', self.next.title)
                self.setProperty('next.subtitle', self.next.year)
            if self.prev:
                self.setProperty('prev.thumb', self.prev.defaultArt.asTranscodedImageURL(*self.PREV_DIM))
                self.setProperty('prev.title', self.prev.title)
                self.setProperty('prev.subtitle', self.prev.year)
                self.setProperty('prev.info.date', self.prev.year)

    def fillOnDeck(self):
        if not self.onDeckPaginator:
            return False

        if not self.onDeckPaginator.leafCount:
            self.onDeckPaginator.reset()
            return False

        items = self.onDeckPaginator.paginate()

        if not items:
            return False

        return True

    def fillRelated(self, has_prev=False):
        if not self.relatedPaginator.leafCount:
            self.relatedListControl.reset()
            return False

        items = self.relatedPaginator.paginate()

        if not items:
            return False
        return True

    def fillRoles(self, has_prev=False):
        items = []
        idx = 0

        video = self.next if self.next else self.prev

        if not video.roles:
            self.rolesListControl.reset()
            return False

        for role in video.roles():
            mli = kodigui.ManagedListItem(role.tag, role.role, thumbnailImage=role.thumb.asTranscodedImageURL(*self.ROLES_DIM), data_source=role)
            mli.setProperty('index', str(idx))
            items.append(mli)
            idx += 1

        if not items:
            return False

        self.rolesListControl.reset()
        self.rolesListControl.addItems(items)
        return True

    def playVideo(self, prev=False):
        self.cancelTimer()
        resume = False
        try:
            if not self.next and self.playlist:
                if prev:
                    self.playlist.prev()
                self.aborted = False
                self.playQueue = self.playlist
                self.video = None
            else:
                video = self.next
                if prev:
                    video = self.prev

                if not video:
                    util.DEBUG_LOG('Trying to play next video with no next video available')
                    self.video = None
                    return

                if not prev:
                    if video.viewOffset.asInt():
                        choice = dropdown.showDropdown(
                            options=[
                                {'key': 'resume', 'display': T(32429, 'Resume from {0}').format(
                                    util.timeDisplay(video.viewOffset.asInt()).lstrip('0').lstrip(':'))},
                                {'key': 'play', 'display': T(32317, 'Play from beginning')}
                            ],
                            pos=(660, "middle"),
                            close_direction='none',
                            set_dropdown_prop=False,
                            header=T(32314, 'In Progress'),
                        )

                        if not choice:
                            return

                        if choice['key'] == 'resume':
                            resume = True

                self.playQueue = None
                self.video = video

            self.play(handler=self.handler, resume=resume)
        except:
            util.ERROR()


def play(video=None, play_queue=None, resume=False, bgm=False, **kwargs):
    try:
        w = VideoPlayerWindow.open(video=video, play_queue=play_queue, resume=resume, bgm=bgm)
    except util.NoDataException:
        raise
    finally:
        util.DEBUG_LOG("VideoPlayer Window exit")
        player.PLAYER.off('session.ended', w.sessionEnded)
        player.PLAYER.off('videowindow.closed', w.videoWindowClosed)
        player.PLAYER.off('post.play', w.postPlay)
        player.PLAYER.off('av.started', w.playerPlaybackStarted)
        player.PLAYER.off('starting.video', w.onVideoStarting)
        player.PLAYER.off('started.video', w.onVideoStarted)
        player.PLAYER.off('changed.video', w.onVideoChanged)
        player.PLAYER.off('change.background', w.changeBackground)
        player.PLAYER.reset()
        command = w.exitCommand
        del w
        util.garbageCollect()
        return command
