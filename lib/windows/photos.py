from __future__ import absolute_import

import hashlib
import os
import shutil
import threading
import time

import requests
from kodi_six import xbmc
from kodi_six import xbmcgui
from plexnet import plexapp, plexplayer, playqueue
from plexnet import util as plexnetUtil

from lib import util, colors
from . import busy
from . import kodigui


class PhotoWindow(kodigui.BaseWindow):
    xmlFile = 'script-plex-photo.xml'
    path = util.ADDON.getAddonInfo('path')
    theme = 'Main'
    res = '1080i'
    width = 1920
    height = 1080

    OVERLAY_BUTTON_ID = 250
    OSD_GROUP_ID = 200

    OSD_BUTTONS_GROUP_ID = 400
    REPEAT_BUTTON_ID = 401
    SHUFFLE_BUTTON_ID = 402
    ROTATE_BUTTON_ID = 403
    PREV_BUTTON_ID = 404
    PLAY_PAUSE_BUTTON_ID = 406
    STOP_BUTTON_ID = 407
    NEXT_BUTTON_ID = 409
    PQUEUE_BUTTON_ID = 412

    PQUEUE_LIST_ID = 500
    PQUEUE_LIST_OVERLAY_BUTTON_ID = 501

    SLIDESHOW_INTERVAL = util.slideshowInterval

    PHOTO_STACK_SIZE = 10
    tempSubFolder = ("p4k", "photos")

    def __init__(self, *args, **kwargs):
        kodigui.BaseWindow.__init__(self, *args, **kwargs)
        self.photo = kwargs.get('photo')
        self.autoPlay = False
        self.playQueue = kwargs.get('play_queue')
        self.playerObject = None
        self.timelineType = 'photo'
        self.lastTimelineState = None
        self.ignoreTimelines = False
        self.trueTime = 0
        self.slideshowThread = None
        self.slideshowRunning = False
        self.slideshowNext = 0
        self.osdTimer = None
        self.lastItem = None
        self.showPhotoThread = None
        self.showPhotoTimeout = 0
        self.rotate = 0
        self.tempFolder = None
        self.photoStack = []
        self.initialLoad = True

    def onFirstInit(self):
        self.tempFolder = os.path.join(util.translatePath("special://temp/"), *self.tempSubFolder)

        if not os.path.exists(self.tempFolder):
            try:
                os.makedirs(self.tempFolder)
            except OSError:
                if not os.path.isdir(self.tempFolder):
                    util.ERROR()

        self.pqueueList = kodigui.ManagedControlList(self, self.PQUEUE_LIST_ID, 14)
        #self.setProperty('photo', 'script.plex/indicators/busy-photo.gif')
        try:
            self.getPlayQueue()
        except AttributeError:
            raise util.NoDataException
        self.start()
        self.osdTimer = kodigui.PropertyTimer(self._winID, 4, 'OSD', '', init_value=False, callback=self.osdTimerCallback)
        self.imageControl = self.getControl(600)

        if self.autoPlay:
            self.play()

    def doAutoPlay(self):
        self.autoPlay = True
        return True

    def osdTimerCallback(self):
        self.setFocusId(self.OVERLAY_BUTTON_ID)

    def onAction(self, action):
        try:
            # controlID = self.getFocusId()
            if action == xbmcgui.ACTION_MOVE_LEFT:
                if not self.osdVisible() or self.getFocusId() == self.PQUEUE_LIST_OVERLAY_BUTTON_ID:
                    self.prev()
            elif action == xbmcgui.ACTION_MOVE_RIGHT:
                if not self.osdVisible() or self.getFocusId() == self.PQUEUE_LIST_OVERLAY_BUTTON_ID:
                    self.next()
            elif action == xbmcgui.ACTION_MOVE_UP:
                if self.osdVisible():
                    if self.getFocusId() == self.OVERLAY_BUTTON_ID:
                        self.hideOSD()
                    else:
                        self.showOSD()
            elif action == xbmcgui.ACTION_MOVE_DOWN:
                if self.osdVisible():
                    if self.getFocusId() == self.OVERLAY_BUTTON_ID:
                        self.hideOSD()
                    else:
                        self.showOSD()
            elif action == xbmcgui.ACTION_STOP:
                self.stop()
            elif action in (xbmcgui.ACTION_PLAYER_PLAY, xbmcgui.ACTION_PAUSE):
                if self.isPlaying():
                    self.pause()
                else:
                    self.play()
            elif action == xbmcgui.ACTION_PREV_ITEM:
                self.prev()
            elif action == xbmcgui.ACTION_NEXT_ITEM:
                self.next()
            elif action in (xbmcgui.ACTION_PREVIOUS_MENU, xbmcgui.ACTION_NAV_BACK):
                if self.osdVisible():
                    self.hideOSD()
                    return
                self.doClose()
                return

            self.osdTimer.reset(init=False)
        except:
            util.ERROR()

        kodigui.BaseWindow.onAction(self, action)

    def goHome(self, *args, **kwargs):
        self.doClose()

    def checkPqueueListChanged(self):
        item = self.pqueueList.getSelectedItem()
        if item == self.lastItem:
            return

        self.lastItem = item
        self.onPqueueListChanged()

    def onClick(self, controlID):
        if controlID == self.PREV_BUTTON_ID:
            self.prev()
        elif controlID == self.NEXT_BUTTON_ID:
            next(self)
        elif controlID == self.PLAY_PAUSE_BUTTON_ID:
            if self.isPlaying():
                self.pause()
            else:
                self.play()
        elif controlID == self.STOP_BUTTON_ID:
            self.stop()
        elif controlID == self.OVERLAY_BUTTON_ID:
            self.showOSD()
        elif controlID == self.SHUFFLE_BUTTON_ID:
            self.shuffleButtonClicked()
        elif controlID == self.REPEAT_BUTTON_ID:
            self.repeatButtonClicked()
        elif controlID == self.ROTATE_BUTTON_ID:
            self.setRotation()

    def shuffleButtonClicked(self):
        self.playQueue.setShuffle()

    def repeatButtonClicked(self):
        if self.playQueue.isRepeat:
            self.playQueue.setRepeat(False)
            self.playQueue.refresh(force=True)
        else:
            self.playQueue.setRepeat(True)
            self.playQueue.refresh(force=True)

    def setRotation(self, angle=None):
        if angle is None:
            self.resetSlideshowTimeout()
            self.rotate += 90
            if self.rotate > 270:
                self.rotate = 0
        else:
            self.rotate = angle

        if self.rotate == 90:
            self.imageControl.setPosition(420, -420)
            self.imageControl.setWidth(1080)
            self.imageControl.setHeight(1920)
        elif self.rotate == 180:
            self.imageControl.setPosition(0, 0)
            self.imageControl.setWidth(1920)
            self.imageControl.setHeight(1080)
        elif self.rotate == 270:
            self.imageControl.setPosition(420, -420)
            self.imageControl.setWidth(1080)
            self.imageControl.setHeight(1920)
        else:
            self.imageControl.setPosition(0, 0)
            self.imageControl.setWidth(1920)
            self.imageControl.setHeight(1080)

        self.setProperty('rotate', str(self.rotate))

    def isPlaying(self):
        return bool(self.getProperty('playing'))

    def getPlayQueue(self, shuffle=False):
        if self.playQueue:
            self.playQueue.on('items.changed', self.fillPqueueList)
            self.playQueue.on('change', self.updateProperties)
            self.updateProperties()
            self.fillPqueueList()
        else:
            self.playQueue = playqueue.createPlayQueueForItem(self.photo, options={'shuffle': shuffle})
            self.playQueue.on('items.changed', self.fillPqueueList)
            self.playQueue.on('change', self.updateProperties)

            util.DEBUG_LOG('waiting for playQueue to initialize')
            if busy.widthDialog(self.playQueue.waitForInitialization, None, delay=True):
                util.DEBUG_LOG('playQueue initialized: {0}', self.playQueue)
            else:
                util.DEBUG_LOG('playQueue timed out waiting for initialization')

        self.showPhoto()

    def fillPqueueList(self, **kwargs):
        items = []
        for qi in self.playQueue.items():
            mli = kodigui.ManagedListItem(thumbnailImage=qi.thumb.asTranscodedImageURL(123, 123), data_source=qi)
            items.append(mli)

        self.pqueueList.replaceItems(items)
        self.updatePqueueListSelection()

    def updatePqueueListSelection(self, current=None):
        selected = self.pqueueList.getListItemByDataSource(current or self.playQueue.current())
        if not selected or not selected.pos():
            return

        self.pqueueList.selectItem(selected.pos())

    @busy.dialog(delay=True, delay_time=1.5)
    def showPhoto(self, trigger=None, **kwargs):
        self.slideshowNext = 0

        if not self.showPhotoThread or not self.showPhotoThread.is_alive():
            # if trigger is given, trigger it. trigger loads the next or prev item, depending on what was requested
            # doing this here, this late prevents erratic behaviour when multiple next/prev calls were made but we were
            # still loading images
            if trigger:
                trigger()
                self.updateProperties()

            photo = self.playQueue.current()

            # fixme: video should work.
            # bad temporary fix for videos in photo playqueues
            if photo.type != "photo":
                self.next()
                util.DEBUG_LOG("SKIPPING PHOTO: {}", photo)
                return

            self.updatePqueueListSelection(photo)

        self.showPhotoTimeout = time.time() + 0.2
        if not self.showPhotoThread or not self.showPhotoThread.is_alive():
            self.showPhotoThread = threading.Thread(target=self._showPhoto, name="showphoto")
            self.showPhotoThread.start()

        # wait for the current thread to end, which might still be loading the surrounding images, for 10 seconds
        elif self.showPhotoThread.is_alive():
            waitedFor = 0
            self.setBoolProperty('is.updating', True)
            while waitedFor < 100:
                if not self.showPhotoThread.is_alive() and not util.MONITOR.abortRequested():
                    return self.showPhoto(trigger=trigger, **kwargs)
                elif util.MONITOR.abortRequested():
                    self.setBoolProperty('is.updating', False)
                    return

                util.MONITOR.waitForAbort(0.1)
                waitedFor += 0.1

            # fixme raise error here

    def _showPhoto(self):
        """
        load the current photo, preload the previous and the next one
        :return:
        """
        photo = self.playQueue.current()
        next = self.playQueue.getNext()
        loadItems = (photo, next, self.playQueue.getPrev())
        for item in loadItems:
            if item is not None:
                item.softReload()

        self.playerObject = plexplayer.PlexPhotoPlayer(photo)

        addToStack = []
        currentFailed = False
        try:
            for item in loadItems:
                if not item:
                    continue

                if item.type != "photo":
                    continue

                meta = self.playerObject.build(item=item)
                url = photo.server.getImageTranscodeURL(meta.get('url', ''), self.width, self.height)
                bgURL = item.thumb.asTranscodedImageURL(self.width, self.height, blur=128, opacity=60,
                                                        background=colors.noAlpha.Background)

                isCurrent = currentFailed or item == photo
                if isCurrent and not self.initialLoad:
                    self.setBoolProperty('is.updating', True)

                path, background = self.getCachedPhotoData(url, bgURL)
                if not (path and background):
                    currentFailed = True
                    continue

                if (path, background) not in self.photoStack:
                    if item == next:
                        # move the next image to the top of the stack
                        addToStack.insert(0, (path, background))
                    else:
                        addToStack.append((path, background))

                if isCurrent:
                    self._reallyShowPhoto(item, path, background)
                    self.setBoolProperty('is.updating', False)
                    self.initialLoad = False

            # maintain cache folder
            self.photoStack = addToStack + self.photoStack
            if len(self.photoStack) > self.PHOTO_STACK_SIZE:
                clean = self.photoStack[self.PHOTO_STACK_SIZE:]
                self.photoStack = self.photoStack[:self.PHOTO_STACK_SIZE]
                for remList in clean:
                    for rem in remList:
                        try:
                            os.remove(rem)
                        except:
                            pass
        finally:
            self.setBoolProperty('is.updating', False)

    def getCachedPhotoData(self, url, bgURL):
        if not url:
            return

        basename = hashlib.sha1(url.encode('utf-8')).hexdigest()
        tmpPath = os.path.join(self.tempFolder, basename)
        tmpBgPath = os.path.join(self.tempFolder, "%s_bg" % basename)

        for p, url in ((tmpPath, url), (tmpBgPath, bgURL)):
            if not os.path.exists(p):# and not xbmc.getCacheThumbName(tmpFn):
                try:
                    r = requests.get(url, allow_redirects=True, timeout=10.0)
                    r.raise_for_status()
                except Exception as e:
                    util.ERROR("Couldn't load image: %s" % e, notify=True)
                    return None, None
                else:
                    try:
                        with open(p, 'wb') as f:
                            f.write(r.content)
                    except:
                        return None, None

        return tmpPath, tmpBgPath

    def _reallyShowPhoto(self, photo, path, background):
        self.setRotation(0)
        self.setProperty('photo', path)
        self.setProperty('background', background)

        self.setProperty('photo.title', photo.title)
        self.setProperty('photo.date', util.cleanLeadingZeros(photo.originallyAvailableAt.asDatetime('%d %B %Y')))
        self.setProperty('camera.model', photo.media[0].model)
        self.setProperty('camera.lens', photo.media[0].lens)

        if photo.media[0].height:
            dims = u'{0} x {1}{2}'.format(
                photo.media[0].width,
                photo.media[0].height,
                photo.media[0].parts[0].orientation and u' \u2022 {0} Mo'.format(photo.media[0].parts[0].orientation) or ''
            )
            self.setProperty('photo.dims', dims)
        settings = []
        if photo.media[0].iso:
            settings.append('ISO {0}'.format(photo.media[0].iso))
        if photo.media[0].aperture:
            settings.append('{0}'.format(photo.media[0].aperture))
        if photo.media[0].exposure:
            settings.append('{0}'.format(photo.media[0].exposure))
        self.setProperty('camera.settings', u' \u2022 '.join(settings))
        self.setProperty('photo.summary', photo.summary)
        container = photo.media[0].container_ or os.path.splitext(photo.media[0].parts[0].file)[-1][1:].lower()
        if container == 'jpg':
            container = 'jpeg'
        self.setProperty('photo.container', container)
        self.updateNowPlaying(force=True, refreshQueue=True)
        self.resetSlideshowTimeout()

    def updateProperties(self, **kwargs):
        self.setProperty('pq.shuffled', self.playQueue.isShuffled and '1' or '')
        self.setProperty('pq.repeat', self.playQueue.isRepeat and '1' or '')
        if not self.getProperty('hide.prev') and not self.playQueue.hasPrev():
            if self.playQueue.hasNext():
                self.setFocusId(self.NEXT_BUTTON_ID)
            else:
                self.setFocusId(self.PLAY_PAUSE_BUTTON_ID)
        self.setProperty('hide.prev', not self.playQueue.hasPrev() and '1' or '')
        if not self.getProperty('hide.next') and not self.playQueue.hasNext():
            if self.playQueue.hasPrev():
                self.setFocusId(self.PREV_BUTTON_ID)
            else:
                self.setFocusId(self.PLAY_PAUSE_BUTTON_ID)
        self.setProperty('hide.next', not self.playQueue.hasNext() and '1' or '')

    def slideshow(self):
        util.DEBUG_LOG('Slideshow: STARTED')
        self.slideshowRunning = True

        # inhibit screensaver in matrix and above
        if util.KODI_VERSION_MAJOR > 18:
            xbmc.executebuiltin('InhibitScreensaver(true)')

        self.resetSlideshowTimeout()
        while not util.MONITOR.waitForAbort(0.1) and self.slideshowRunning:
            if not self.slideshowNext or time.time() < self.slideshowNext:
                continue
            self.next()

        if util.KODI_VERSION_MAJOR > 18:
            xbmc.executebuiltin('InhibitScreensaver(false)')

        util.DEBUG_LOG('Slideshow: STOPPED')

    def resetSlideshowTimeout(self):
        self.slideshowNext = time.time() + self.SLIDESHOW_INTERVAL

    def osdVisible(self):
        return self.getProperty('OSD')

    def pqueueVisible(self):
        return self.getProperty('show.pqueue')

    def start(self):
        self.setFocusId(self.OVERLAY_BUTTON_ID)

    def prev(self):
        if not self.playQueue.getPrev():
            return
        self.showPhoto(trigger=lambda: self.playQueue.prev())

    def next(self):
        if not self.playQueue.getNext():
            return
        self.showPhoto(trigger=lambda: self.playQueue.next())

    __next__ = next

    def play(self):
        self.setProperty('playing', '1')
        if self.slideshowThread and self.slideshowThread.is_alive():
            return

        self.slideshowThread = threading.Thread(target=self.slideshow, name='slideshow')
        self.slideshowThread.start()

    def pause(self):
        self.setProperty('playing', '')
        self.slideshowRunning = False

    def stop(self):
        self.doClose()

    def doClose(self, **kw):
        self.pause()
        shutil.rmtree(self.tempFolder, ignore_errors=True)

        kodigui.BaseWindow.doClose(self)

    def getCurrentItem(self):
        if self.playerObject:
            return self.playerObject.item
        return None

    def shouldSendTimeline(self, item):
        return item.ratingKey and item.getServer()

    def updateNowPlaying(self, force=False, refreshQueue=False, state=None):
        if self.ignoreTimelines:
            return

        item = self.getCurrentItem()

        if not item:
            return

        if not self.shouldSendTimeline(item):
            return

        state = state or 'paused'
        # Avoid duplicates
        if state == self.lastTimelineState and not force:
            return

        self.lastTimelineState = state
        # self.timelineTimer.reset()

        time = int(self.trueTime * 1000)

        # self.trigger("progress", [m, item, time])

        if refreshQueue and self.playQueue:
            self.playQueue.refreshOnTimeline = True

        data = plexnetUtil.AttributeDict({
            "key": str(item.key),
            "ratingKey": str(item.ratingKey),
            "guid": str(item.guid),
            "url": str(item.url),
            "duration": item.duration.asInt(),
            "containerKey": str(item.container.address)
        })

        plexapp.util.APP.nowplayingmanager.updatePlaybackState(self.timelineType, data, state, time, self.playQueue)

    def showOSD(self):
        self.osdTimer.reset(init=False)

    def hideOSD(self, closing=False):
        self.osdTimer.stop(trigger=True)
