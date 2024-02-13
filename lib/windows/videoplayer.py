from __future__ import absolute_import
import time
import threading
import math

from kodi_six import xbmc
from kodi_six import xbmcgui

from . import kodigui
from . import windowutils
from . import opener
from . import busy
from . import search
from . import dropdown
from . import pagination

from lib import util
from lib import player
from lib import colors
from lib import kodijsonrpc

from lib.util import T


PASSOUT_PROTECTION_DURATION_SECONDS = 7200
PASSOUT_LAST_VIDEO_DURATION_MILLIS = 1200000


class RelatedPaginator(pagination.BaseRelatedPaginator):
    def readyForPaging(self):
        return self.parentWindow.postPlayInitialized

    def getData(self, offset, amount):
        return (self.parentWindow.prev or self.parentWindow.next).getRelated(offset=offset, limit=amount)


class OnDeckPaginator(pagination.MCLPaginator):
    def readyForPaging(self):
        return self.parentWindow.postPlayInitialized

    thumbFallback = lambda self, rel: 'script.plex/thumb_fallbacks/{0}.png'.format(
                    rel.type in ('show', 'season', 'episode') and 'show' or 'movie')

    def prepareListItem(self, data, mli):
        mli.setProperty('progress', util.getProgressImage(mli.dataSource))
        mli.setProperty('unwatched', not mli.dataSource.isWatched and '1' or '')

        if data.type in 'episode':
            mli.setLabel2(
                u'{0}{1} \u2022 {2}{3}'.format(T(32310, 'S'), data.parentIndex, T(32311, 'E'), data.index))
        else:
            mli.setLabel2(data.year)

    def createListItem(self, ondeck):
        title = ondeck.grandparentTitle or ondeck.title
        if ondeck.type == 'episode':
            thumb = ondeck.thumb.asTranscodedImageURL(*self.parentWindow.ONDECK_DIM)
        else:
            thumb = ondeck.defaultArt.asTranscodedImageURL(*self.parentWindow.ONDECK_DIM)

        mli = kodigui.ManagedListItem(title or '', thumbnailImage=thumb, data_source=ondeck)
        if mli:
            return mli

    def getData(self, offset, amount):
        return (self.parentWindow.prev or self.parentWindow.next).sectionOnDeck(offset=offset, limit=amount)


class VideoPlayerWindow(kodigui.ControlledWindow, windowutils.UtilMixin):
    xmlFile = 'script-plex-video_player.xml'
    path = util.ADDON.getAddonInfo('path')
    theme = 'Main'
    res = '1080i'
    width = 1920
    height = 1080

    NEXT_DIM = util.scaleResolution(537, 303)
    PREV_DIM = util.scaleResolution(462, 259)
    ONDECK_DIM = util.scaleResolution(329, 185)
    RELATED_DIM = util.scaleResolution(268, 397)
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
        self.playQueue = kwargs.get('play_queue')
        self.video = kwargs.get('video')
        self.resume = bool(kwargs.get('resume'))

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

    def doClose(self):
        util.DEBUG_LOG('VideoPlayerWindow: Closing')
        self.timeout = None
        self.relatedPaginator = None
        self.onDeckPaginator = None
        kodigui.ControlledWindow.doClose(self)
        player.PLAYER.handler.sessionEnded()

    def onFirstInit(self):
        player.PLAYER.on('session.ended', self.sessionEnded)
        player.PLAYER.on('av.started', self.playerPlaybackStarted)
        player.PLAYER.on('post.play', self.postPlay)
        player.PLAYER.on('change.background', self.changeBackground)

        self.onDeckListControl = kodigui.ManagedControlList(self, self.ONDECK_LIST_ID, 5)
        self.relatedListControl = kodigui.ManagedControlList(self, self.RELATED_LIST_ID, 5)
        self.rolesListControl = kodigui.ManagedControlList(self, self.ROLES_LIST_ID, 5)

        util.DEBUG_LOG('VideoPlayerWindow: Starting session (ID: {0})'.format(id(self)))
        self.resetPassoutProtection()
        self.play(resume=self.resume)

    def onReInit(self):
        self.setBackground()

    def onAction(self, action):
        try:
            if self.postPlayMode:
                controlID = self.getFocusId()

                self.cancelTimer()
                self.resetPassoutProtection()
                if action in(xbmcgui.ACTION_NAV_BACK, xbmcgui.ACTION_CONTEXT_MENU):
                    if not xbmc.getCondVisibility('ControlGroup({0}).HasFocus(0)'.format(self.OPTIONS_GROUP_ID)):
                        if not util.advancedSettings.fastBack or action == xbmcgui.ACTION_CONTEXT_MENU:
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
        except:
            util.ERROR()

        kodigui.ControlledWindow.onAction(self, action)

    def playerPlaybackStarted(self, *args, **kwargs):
        self.playBackStarted = True

    def onClick(self, controlID):
        if not self.postPlayMode:
            return

        timeoutCanceled = False
        if util.advancedSettings.postplayCancel:
            timeoutCanceled = bool(self.timeout)
            self.cancelTimer()

        if controlID == self.HOME_BUTTON_ID:
            self.goHome()
        elif controlID == self.ONDECK_LIST_ID:
            self.openItem(self.onDeckListControl)
        elif controlID == self.RELATED_LIST_ID:
            self.openItem(self.relatedListControl)
        elif controlID == self.ROLES_LIST_ID:
            self.roleClicked()
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

    def roleClicked(self):
        mli = self.rolesListControl.getSelectedItem()
        if not mli:
            return

        sectionRoles = busy.widthDialog(mli.dataSource.sectionRoles, '')

        if not sectionRoles:
            util.DEBUG_LOG('No sections found for actor')
            return

        if len(sectionRoles) > 1:
            x, y = self.getRoleItemDDPosition()

            options = [{'role': r, 'display': r.reasonTitle} for r in sectionRoles]
            choice = dropdown.showDropdown(options, (x, y), pos_is_bottom=True, close_direction='bottom')

            if not choice:
                return

            role = choice['role']
        else:
            role = sectionRoles[0]

        self.processCommand(opener.open(role))

    def getRoleItemDDPosition(self):
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

        focus = int(xbmc.getInfoLabel('Container(403).Position'))

        x = ((focus + 1) * 304) - 100
        return x, y

    def setBackground(self):
        video = self.video if self.video else self.playQueue.current()
        self.windowSetBackground(video.defaultArt.asTranscodedImageURL(1920, 1080, opacity=60,
                                                                       background=colors.noAlpha.Background))

    def changeBackground(self, url, **kwargs):
        self.windowSetBackground(url)

    def sessionEnded(self, session_id=None, **kwargs):
        if session_id != id(self):
            util.DEBUG_LOG('VideoPlayerWindow: Ignoring session end (ID: {0} - SessionID: {1})'.format(id(self), session_id))
            return

        util.DEBUG_LOG('VideoPlayerWindow: Session ended - closing (ID: {0})'.format(id(self)))
        self.doClose()

    def play(self, resume=False, handler=None):
        self.hidePostPlay()

        def anyOtherVPlayer():
            return any(list(filter(lambda x: x['playerid'] > 0, kodijsonrpc.rpc.Player.GetActivePlayers())))

        if player.PLAYER.isPlayingVideo():
            activePlayers = anyOtherVPlayer()
            if activePlayers:
                util.DEBUG_LOG("Stopping other active players: {}".format(activePlayers))
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

        self.setBackground()
        if self.playQueue:
            player.PLAYER.playVideoPlaylist(self.playQueue, resume=self.resume, session_id=id(self), handler=handler)
        elif self.video:
            player.PLAYER.playVideo(self.video, resume=self.resume, force_update=True, session_id=id(self), handler=handler)

    def openItem(self, control=None, item=None):
        if not item:
            mli = control.getSelectedItem()
            if not mli:
                return
            item = mli.dataSource

        self.processCommand(opener.open(item))

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
            self.next.reload(includeExtras=1, includeExtrasCount=10)

        self.relatedPaginator = RelatedPaginator(self.relatedListControl,
                                                 leaf_count=int((self.prev or self.next).relatedCount),
                                                 parent_window=self)

        vid = self.prev or self.next
        if vid.sectionOnDeckCount:
            self.onDeckPaginator = OnDeckPaginator(self.onDeckListControl,
                                                   leaf_count=int(vid.sectionOnDeckCount),
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
            util.DEBUG_LOG('Post play auto-play: Passout protection in {0}'.format(util.durationToShortText(millis)))

        self.timeout = time.time() + abs(util.advancedSettings.postplayTimeout)
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
                cd = min(abs(util.advancedSettings.postplayTimeout-1), int((self.timeout or now) - now))
                base = 15 / float(util.advancedSettings.postplayTimeout-1)
                self.setProperty('countdown', str(int(math.ceil(base*cd))))

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
        if self.next:
            self.setProperty(
                'post.play.background',
                util.backgroundFromArt(self.next.art, width=self.width, height=self.height)
            )
            self.setProperty('info.title', self.next.title)
            self.setProperty('info.duration', util.durationToText(self.next.duration.asInt()))
            self.setProperty('info.summary', self.next.summary)

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
                self.setProperty('next.thumb', self.next.thumb.asTranscodedImageURL(*self.NEXT_DIM))
                self.setProperty('info.date', util.cleanLeadingZeros(self.next.originallyAvailableAt.asDatetime('%B %d, %Y')))

                self.setProperty('next.title', self.next.grandparentTitle)
                self.setProperty(
                    'next.subtitle', u'{0} {1} \u2022 {2} {3}'.format(T(32303, 'Season'), self.next.parentIndex, T(32304, 'Episode'), self.next.index)
                )
            if self.prev:
                self.setProperty('prev.thumb', self.prev.thumb.asTranscodedImageURL(*self.PREV_DIM))
                self.setProperty('prev.title', self.prev.grandparentTitle)
                self.setProperty(
                    'prev.subtitle', u'{0} {1} \u2022 {2} {3}'.format(T(32303, 'Season'), self.prev.parentIndex, T(32304, 'Episode'), self.prev.index)
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

        self.setProperty('divider.{0}'.format(self.RELATED_LIST_ID), has_prev and '1' or '')
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

        self.setProperty('divider.{0}'.format(self.ROLES_LIST_ID), has_prev and '1' or '')

        self.rolesListControl.reset()
        self.rolesListControl.addItems(items)
        return True

    def playVideo(self, prev=False):
        self.cancelTimer()
        try:
            if not self.next and self.playlist:
                if prev:
                    self.playlist.prev()
                self.aborted = False
                self.playQueue = self.playlist
                self.video = None
                self.play(handler=self.handler)
            else:
                video = self.next
                if prev:
                    video = self.prev

                if not video:
                    util.DEBUG_LOG('Trying to play next video with no next video available')
                    self.video = None
                    return

                self.playQueue = None
                self.video = video
                self.play(handler=self.handler)
        except:
            util.ERROR()


def play(video=None, play_queue=None, resume=False):
    try:
        w = VideoPlayerWindow.open(video=video, play_queue=play_queue, resume=resume)
    except util.NoDataException:
        raise
    finally:
        player.PLAYER.off('session.ended', w.sessionEnded)
        player.PLAYER.off('post.play', w.postPlay)
        player.PLAYER.off('av.started', w.playerPlaybackStarted)
        player.PLAYER.off('change.background', w.changeBackground)
        player.PLAYER.reset()
        command = w.exitCommand
        del w
        util.garbageCollect()
        return command
