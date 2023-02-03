from __future__ import absolute_import
import re
import time
import threading

from kodi_six import xbmc
from kodi_six import xbmcgui

from . import kodigui
from . import playersettings
from . import dropdown
from plexnet import plexapp

from lib import util
from plexnet.videosession import VideoSessionInfo, ATTRIBUTE_TYPES as SESSION_ATTRIBUTE_TYPES
from plexnet.exceptions import ServerNotOwned, NotFound
from plexnet.signalsmixin import SignalsMixin

from lib.kodijsonrpc import builtin

from lib.util import T
from six.moves import range


KEY_MOVE_SET = frozenset(
    (
        xbmcgui.ACTION_MOVE_LEFT,
        xbmcgui.ACTION_MOVE_RIGHT,
        xbmcgui.ACTION_MOVE_UP,
        xbmcgui.ACTION_MOVE_DOWN
    )
)

KEY_STEP_SEEK_SET = frozenset(
    (
        xbmcgui.ACTION_MOVE_LEFT,
        xbmcgui.ACTION_MOVE_RIGHT,
        xbmcgui.ACTION_STEP_FORWARD,
        xbmcgui.ACTION_STEP_BACK
    )
)


class SeekDialog(kodigui.BaseDialog):
    xmlFile = 'script-plex-seek_dialog.xml'
    path = util.ADDON.getAddonInfo('path')
    theme = 'Main'
    res = '1080i'
    width = 1920
    height = 1080

    MAIN_BUTTON_ID = 100
    SEEK_IMAGE_ID = 200
    POSITION_IMAGE_ID = 201
    SELECTION_INDICATOR = 202
    BIF_IMAGE_ID = 300
    SEEK_IMAGE_WIDTH = 1920

    REPEAT_BUTTON_ID = 401
    SHUFFLE_BUTTON_ID = 402
    SETTINGS_BUTTON_ID = 403
    PREV_BUTTON_ID = 404
    SKIP_BACK_BUTTON_ID = 405
    PLAY_PAUSE_BUTTON_ID = 406
    SKIP_FORWARD_BUTTON_ID = 408
    NEXT_BUTTON_ID = 409
    PLAYLIST_BUTTON_ID = 410
    OPTIONS_BUTTON_ID = 411
    SUBTITLE_BUTTON_ID = 412

    BIG_SEEK_GROUP_ID = 500
    BIG_SEEK_LIST_ID = 501

    SKIP_INTRO_BUTTON_ID = 791
    NO_OSD_BUTTON_ID = 800

    BAR_X = 0
    BAR_Y = 921
    BAR_RIGHT = 1920
    BAR_BOTTOM = 969

    HIDE_DELAY = 4  # This uses the Cron tick so is +/- 1 second accurate
    OSD_HIDE_ANIMATION_DURATION = 0.2
    SKIP_STEPS = {"negative": [-10000], "positive": [30000]}

    def __init__(self, *args, **kwargs):
        kodigui.BaseDialog.__init__(self, *args, **kwargs)
        self.handler = kwargs.get('handler')
        self.initialVideoSettings = {}
        self.initialAudioStream = None
        self.initialSubtitleStream = None
        self.bifURL = None
        self.baseURL = None
        self.hasBif = bool(self.bifURL)
        self.baseOffset = 0
        self._duration = 0
        self.offset = 0
        self.selectedOffset = 0
        self.bigSeekOffset = 0
        self.bigSeekChanged = False
        self.title = ''
        self.title2 = ''
        self.fromSeek = 0
        self.initialized = False
        self.playlistDialog = None
        self.timeout = None
        self.autoSeekTimeout = None
        self.hasDialog = False
        self.lastFocusID = None
        self.previousFocusID = None
        self.playlistDialogVisible = False
        self._seeking = False
        self._applyingSeek = False
        self._seekingWithoutOSD = False
        self._delayedSeekThread = None
        self._delayedSeekTimeout = 0
        self._osdHideAnimationTimeout = 0
        self._osdHideFast = False
        self._hideDelay = self.HIDE_DELAY
        self._autoSeekDelay = util.advancedSettings.autoSeekDelay
        self._atSkipStep = -1
        self._lastSkipDirection = None
        self._forcedLastSkipAmount = None
        self.lastTimelineResponse = None
        self._ignoreInput = False
        self._enableIntroSkip = plexapp.ACCOUNT.hasPlexPass()
        self.intro = self.handler.player.video.intro
        self._introSkipShownStarted = None
        self.skipSteps = self.SKIP_STEPS
        self.useAutoSeek = util.advancedSettings.autoSeek
        self.useDynamicStepsForTimeline = util.advancedSettings.dynamicTimelineSeek

        self.auto_skip_intro = util.getSetting('auto_skip_intro', False)
        self.skip_intro_button_timeout = util.getSetting('skip_intro_button_timeout', 10)

        self.player.video.server.on("np:timelineResponse", self.timelineResponseCallback)

        if util.kodiSkipSteps and util.advancedSettings.kodiSkipStepping:
            self.skipSteps = {"negative": [], "positive": []}
            for step in util.kodiSkipSteps:
                key = "negative" if step < 0 else "positive"
                self.skipSteps[key].append(step * 1000)

            self.skipSteps["negative"].reverse()

        try:
            seconds = int(xbmc.getInfoLabel("Skin.String(SkinHelper.AutoCloseVideoOSD)"))
            if seconds > 0:
                self._hideDelay = seconds
        except ValueError:
            pass

    @property
    def player(self):
        return self.handler.player

    def timelineResponseCallback(self, **kwargs):
        response = kwargs.get("response")
        self.lastTimelineResponse = response.getBodyXml()

    def resetTimeout(self):
        self.timeout = time.time() + self._hideDelay

    def resetAutoSeekTimer(self, value="not_set"):
        self.autoSeekTimeout = value if value != "not_set" else time.time() + self._autoSeekDelay

    def resetSeeking(self):
        self._seeking = False
        self._seekingWithoutOSD = False
        self._delayedSeekTimeout = None
        self._applyingSeek = False
        self.bigSeekChanged = False
        self.selectedOffset = None
        self.setProperty('button.seek', '')
        self.resetAutoSeekTimer(None)
        self.resetSkipSteps()

    def trueOffset(self):
        if self.handler.mode == self.handler.MODE_ABSOLUTE:
            return (self.handler.player.playerObject.startOffset * 1000) + self.offset
        else:
            return self.baseOffset + self.offset

    def onFirstInit(self):
        try:
            self._onFirstInit()
        except RuntimeError:
            util.ERROR(hide_tb=True)
            self.started = False

    def _onFirstInit(self):
        self.resetTimeout()
        self.setProperty('introSkipText', T(32495, 'Skip intro'))
        self.bigSeekHideTimer = kodigui.PropertyTimer(self._winID, 0.5, 'hide.bigseek')

        if self.handler.playlist:
            self.handler.playlist.on('change', self.updateProperties)

        self.seekbarControl = self.getControl(self.SEEK_IMAGE_ID)
        self.positionControl = self.getControl(self.POSITION_IMAGE_ID)
        self.bifImageControl = self.getControl(self.BIF_IMAGE_ID)
        self.selectionIndicator = self.getControl(self.SELECTION_INDICATOR)
        self.selectionBox = self.getControl(203)
        self.bigSeekControl = kodigui.ManagedControlList(self, self.BIG_SEEK_LIST_ID, 12)
        self.bigSeekGroupControl = self.getControl(self.BIG_SEEK_GROUP_ID)
        self.initialized = True
        self.setBoolProperty('subtitle.downloads', util.getSetting('subtitle_downloads', False))
        self.updateProperties()
        self.videoSettingsHaveChanged()
        self.update()

    def onReInit(self):
        self.lastTimelineResponse = None
        self.resetTimeout()
        self.resetSeeking()
        self.updateProperties()
        self.videoSettingsHaveChanged()
        self.updateProgress()

    def onAction(self, action):
        if xbmc.getCondVisibility('Window.IsActive(selectdialog)'):
            if self.doKodiSelectDialogHack(action):
                return

        try:
            self.resetTimeout()

            controlID = self.getFocusId()

            if not self._ignoreInput:
                if action.getId() in KEY_MOVE_SET:
                    self.setProperty('mouse.mode', '')
                    if not controlID:
                        self.setBigSeekShift()
                        self.setFocusId(400)
                        return
                elif action == xbmcgui.ACTION_MOUSE_MOVE:
                    self.setProperty('mouse.mode', '1')

                if controlID in (self.MAIN_BUTTON_ID, self.NO_OSD_BUTTON_ID):
                    if action == xbmcgui.ACTION_MOUSE_LEFT_CLICK:
                        if self.getProperty('mouse.mode') != '1':
                            self.setProperty('mouse.mode', '1')

                        self.seekMouse(action, without_osd=controlID == self.NO_OSD_BUTTON_ID)
                        return
                    elif action == xbmcgui.ACTION_MOUSE_MOVE:
                        self.seekMouse(action, without_osd=controlID == self.NO_OSD_BUTTON_ID, preview=True)
                        return

                passThroughMain = False
                if controlID == self.SKIP_INTRO_BUTTON_ID:
                    if action == xbmcgui.ACTION_SELECT_ITEM:
                        self.setProperty('show.introSkip_OSDOnly', '1')
                        self.doSeek(int(self.intro.endTimeOffset))
                        return
                    elif action == xbmcgui.ACTION_MOVE_DOWN:
                        self.setProperty('show.introSkip_OSDOnly', '1')
                        self.showOSD()
                    elif action in (xbmcgui.ACTION_MOVE_RIGHT, xbmcgui.ACTION_STEP_FORWARD, xbmcgui.ACTION_MOVE_LEFT,
                                    xbmcgui.ACTION_STEP_BACK):
                        # allow no-OSD-seeking with intro skip button shown
                        passThroughMain = True

                if controlID == self.MAIN_BUTTON_ID:
                    # we're seeking from the timeline with the OSD open - do an actual timeline seek
                    if not self._seeking:
                        self.selectedOffset = self.trueOffset()

                    if action in (xbmcgui.ACTION_MOVE_RIGHT, xbmcgui.ACTION_STEP_FORWARD):
                        if self.useDynamicStepsForTimeline:
                            return self.skipForward()
                        return self.seekByOffset(10000, auto_seek=self.useAutoSeek)

                    elif action in (xbmcgui.ACTION_MOVE_LEFT, xbmcgui.ACTION_STEP_BACK):
                        if self.useDynamicStepsForTimeline:
                            return self.skipBack()
                        return self.seekByOffset(-10000, auto_seek=self.useAutoSeek)

                    elif action == xbmcgui.ACTION_MOVE_DOWN:
                        self.updateBigSeek()
                    # elif action == xbmcgui.ACTION_MOVE_UP:
                    #     self.seekForward(60000)
                    # elif action == xbmcgui.ACTION_MOVE_DOWN:
                    #     self.seekBack(60000)

                # don't auto-apply the currently selected seek when pressing down
                elif controlID == self.PLAY_PAUSE_BUTTON_ID and self.previousFocusID == self.MAIN_BUTTON_ID \
                        and action == xbmcgui.ACTION_MOVE_DOWN:
                    self.resetSeeking()

                elif controlID == self.NO_OSD_BUTTON_ID or passThroughMain:
                    if action in (xbmcgui.ACTION_MOVE_RIGHT, xbmcgui.ACTION_MOVE_LEFT):
                        # we're seeking from the timeline, with the OSD closed; act as we're skipping
                        if not self._seeking:
                            self.selectedOffset = self.trueOffset()

                        if action == xbmcgui.ACTION_MOVE_RIGHT:
                            self.skipForward(without_osd=True)

                        else:
                            self.skipBack(without_osd=True)
                    if action in (xbmcgui.ACTION_MOVE_UP, xbmcgui.ACTION_MOVE_DOWN):
                        # we're seeking from the timeline, with the OSD closed; act as we're skipping
                        if not self._seeking:
                            self.selectedOffset = self.trueOffset()

                        if self.skipChapter(forward=(action == xbmcgui.ACTION_MOVE_UP), without_osd=True):
                            return

                    if action in (
                        xbmcgui.ACTION_MOVE_UP,
                        xbmcgui.ACTION_MOVE_DOWN,
                        xbmcgui.ACTION_BIG_STEP_FORWARD,
                        xbmcgui.ACTION_BIG_STEP_BACK
                    ) and not self._seekingWithoutOSD:
                        self.selectedOffset = self.trueOffset()
                        self.setBigSeekShift()
                        self.updateProgress()
                        self.showOSD()
                        self.setFocusId(self.BIG_SEEK_LIST_ID)
                    elif action.getButtonCode() == 61519:
                        if self.getProperty('show.PPI'):
                            self.hidePPIDialog()
                        else:
                            self.showPPIDialog()

                elif controlID == self.BIG_SEEK_LIST_ID:
                    if action in (xbmcgui.ACTION_MOVE_RIGHT, xbmcgui.ACTION_BIG_STEP_FORWARD):
                        return self.updateBigSeek(changed=True)
                    elif action in (xbmcgui.ACTION_MOVE_LEFT, xbmcgui.ACTION_BIG_STEP_BACK):
                        return self.updateBigSeek(changed=True)
                    elif action == xbmcgui.ACTION_MOVE_UP and self.getProperty('show.introSkip'):
                        self.setFocusId(self.SKIP_INTRO_BUTTON_ID)
                        return

                if action.getButtonCode() == 61516:
                    builtin.Action('CycleSubtitle')
                elif action.getButtonCode() == 61524:
                    builtin.Action('ShowSubtitles')
                elif action.getButtonCode() == 323714:
                    # Alt-left
                    builtin.PlayerControl('tempodown')
                elif action.getButtonCode() == 323715:
                    # Alt-right
                    builtin.PlayerControl('tempoup')
                elif action == xbmcgui.ACTION_NEXT_ITEM:
                    self.handler.next()
                elif action == xbmcgui.ACTION_PREV_ITEM:
                    self.handler.prev()

            if action in (xbmcgui.ACTION_PREVIOUS_MENU, xbmcgui.ACTION_NAV_BACK):
                if self.getProperty('show.PPI'):
                    self.hidePPIDialog()
                    return

                if action in (xbmcgui.ACTION_PREVIOUS_MENU, xbmcgui.ACTION_NAV_BACK, xbmcgui.ACTION_STOP):
                    if self._seeking and not self._ignoreInput:
                        self.resetSeeking()
                        self.updateCurrent()
                        self.updateProgress()
                        if self.osdVisible():
                            self.hideOSD()
                        return

                    if action in (xbmcgui.ACTION_PREVIOUS_MENU, xbmcgui.ACTION_NAV_BACK):
                        if self._osdHideAnimationTimeout:
                            if self._osdHideAnimationTimeout >= time.time():
                                return
                            else:
                                self._osdHideAnimationTimeout = None

                        if self.osdVisible():
                            self.hideOSD()
                        else:
                            self.doClose()
                            # self.handler.onSeekAborted()
                            self.handler.player.stop()
                        return
        except:
            util.ERROR()

        kodigui.BaseDialog.onAction(self, action)

    def doKodiSelectDialogHack(self, action):
        command = {
            xbmcgui.ACTION_MOVE_UP: "Up",
            xbmcgui.ACTION_MOVE_DOWN: "Down",
            xbmcgui.ACTION_MOVE_LEFT: "Right", # Not sure if these are actually reversed or something else is up here
            xbmcgui.ACTION_MOVE_RIGHT: "Left",
            xbmcgui.ACTION_SELECT_ITEM: "Select",
            xbmcgui.ACTION_PREVIOUS_MENU: "Back",
            xbmcgui.ACTION_NAV_BACK: "Back"
        }.get(action.getId())

        if command is not None:
            xbmc.executebuiltin('Action({0},selectdialog)'.format(command))
            return True

        return False

    def onFocus(self, controlID):
        lastFocusID = self.lastFocusID
        self.previousFocusID = self.lastFocusID
        self.lastFocusID = controlID
        if controlID == self.MAIN_BUTTON_ID:
            self.selectedOffset = self.trueOffset()
            if lastFocusID == self.BIG_SEEK_LIST_ID and self.bigSeekChanged:
                xbmc.sleep(100)
                self.updateBigSeek(changed=True)
                self.updateProgress(set_to_current=False)
                if self.useAutoSeek:
                    self.delayedSeek()

            else:
                self.setBigSeekShift()
                self.updateProgress()

        elif controlID == self.BIG_SEEK_LIST_ID:
            self.setBigSeekShift()
            self.updateBigSeek(changed=False)
        elif xbmc.getCondVisibility('ControlGroup(400).HasFocus(0)'):
            self.selectedOffset = self.trueOffset()
            self.updateProgress()

    def onClick(self, controlID):
        if self._ignoreInput:
            return

        if controlID in (self.MAIN_BUTTON_ID, self.NO_OSD_BUTTON_ID):
            # only react to click events on our main areas if we're not in mouse mode, otherwise mouse seeking is
            # handled by onAction
            if self.getProperty('mouse.mode') != '1':
                if controlID == self.MAIN_BUTTON_ID:
                    self.resetAutoSeekTimer(None)
                    self.doSeek()
                elif controlID == self.NO_OSD_BUTTON_ID:
                    if not self._seeking:
                        self.showOSD()
                    else:
                        # currently seeking without the OSD, apply the seek
                        self.doSeek()

        elif controlID == self.SETTINGS_BUTTON_ID:
            self.handleDialog(self.showSettings)
        elif controlID == self.REPEAT_BUTTON_ID:
            self.repeatButtonClicked()
        elif controlID == self.SHUFFLE_BUTTON_ID:
            self.shuffleButtonClicked()
        elif controlID == self.PREV_BUTTON_ID:
            self.handler.prev()
        elif controlID == self.NEXT_BUTTON_ID:
            next(self.handler)
        elif controlID == self.PLAYLIST_BUTTON_ID:
            self.showPlaylistDialog()
        elif controlID == self.OPTIONS_BUTTON_ID:
            self.handleDialog(self.optionsButtonClicked)
        elif controlID == self.SUBTITLE_BUTTON_ID:
            self.handleDialog(self.subtitleButtonClicked)
        elif controlID == self.BIG_SEEK_LIST_ID:
            self.bigSeekSelected()
        elif controlID == self.SKIP_BACK_BUTTON_ID:
            self.skipBack()
        elif controlID == self.SKIP_FORWARD_BUTTON_ID:
            self.skipForward()

    def doClose(self, delete=False):
        if self.handler.playlist:
            self.handler.playlist.off('change', self.updateProperties)

        try:
            if self.playlistDialog:
                self.playlistDialog.doClose()
                if delete:
                    del self.playlistDialog
                    self.playlistDialog = None
                    util.garbageCollect()
        finally:
            kodigui.BaseDialog.doClose(self)

    def showPPIDialog(self):
        for attrib in SESSION_ATTRIBUTE_TYPES.values():
            self.setProperty('ppi.%s' % attrib.label, "")

        self.setProperty('show.PPI', '1')
        self.setProperty('ppi.Status', 'Loading ...')

        def getVideoSession(currentVideo):
            return currentVideo.server.findVideoSession(currentVideo.settings.getGlobal("clientIdentifier"),
                                                        currentVideo.ratingKey)

        while not self.player.started:
            util.MONITOR.waitForAbort(0.1)

        info = None
        currentVideo = self.player.video
        try:
            videoSession = None
            elapsed = 0
            while not videoSession:
                if elapsed > 10:
                    raise NotFound

                videoSession = getVideoSession(currentVideo)
                if videoSession:
                    break

                util.MONITOR.waitForAbort(1)
                elapsed += 1

            # fill attributes
            info = VideoSessionInfo(videoSession, currentVideo)

        except ServerNotOwned:
            # timeline response data fallback
            elapsed = 0
            try:
                while not self.lastTimelineResponse:
                    if elapsed > 10:
                        raise NotFound

                    util.MONITOR.waitForAbort(0.1)
                    elapsed += 0.1

                info = VideoSessionInfo(None, currentVideo, incompleteSessionData=self.lastTimelineResponse)
            except NotFound:
                self.setProperty('ppi.Status', 'Info not available (data not found)')

            except:
                util.ERROR()

        except NotFound:
            self.setProperty('ppi.Status', 'Info not available (session not found)')

        except:
            util.ERROR()

        if info:
            self.setProperty('ppi.Status', '')
            for attrib in info.attributes.values():
                self.setProperty('ppi.%s' % attrib.label, attrib.value)

    def hidePPIDialog(self):
        self.setProperty('show.PPI', '')

    def resetSkipSteps(self):
        self._forcedLastSkipAmount = None
        self._atSkipStep = -1
        self._lastSkipDirection = None

    def determineSkipStep(self, direction):
        stepCount = len(self.skipSteps[direction])

        # shortcut for simple skipping
        if stepCount == 1:
            return self.skipSteps[direction][0]

        use_direction = direction

        # kodi-style skip steps

        # when the direction changes, we either use the skip steps of the other direction, or walk backwards in the
        # current skip step list
        if self._lastSkipDirection != direction:
            if self._atSkipStep == -1 or self._lastSkipDirection is None:
                self._atSkipStep = 0
                self._lastSkipDirection = direction
                self._forcedLastSkipAmount = None
                step = self.skipSteps[use_direction][0]

            else:
                # we're reversing the current direction
                use_direction = self._lastSkipDirection

                # use the inverse value of the current skip step
                step = self.skipSteps[use_direction][min(self._atSkipStep, len(self.skipSteps[use_direction]) - 1)] * -1

                # we've hit a boundary, reverse the difference of the last skip step in relation to the boundary
                if self._forcedLastSkipAmount is not None:
                    step = self._forcedLastSkipAmount * -1
                    self._forcedLastSkipAmount = None

                # walk back one step
                self._atSkipStep -= 1
        else:
            # no reversal of any kind was requested and we've not hit any boundary, use the next skip step
            if self._forcedLastSkipAmount is None:
                self._atSkipStep += 1
                step = self.skipSteps[use_direction][min(self._atSkipStep, stepCount - 1)]

            else:
                # we've hit a timeline boundary and haven't reversed yet. Don't do any further skipping
                return

        return step

    def skipChapter(self, forward=True, without_osd=False):
        lastSelectedOffset = self.selectedOffset
        util.DEBUG_LOG('chapter skipping from {0} with formawrd {1}'.format(lastSelectedOffset, forward))
        if forward:
            nextChapters = [c for c in self.chapters if c.startTime() > lastSelectedOffset]
            util.DEBUG_LOG('Found {0} chapters among {1}'.format(len(nextChapters), len(self.chapters)))
            if len(nextChapters) == 0:
                return False
            chapter = nextChapters[0]
        else:
            startTimeLimit = lastSelectedOffset - 2000
            if startTimeLimit < 0:
                startTimeLimit = 0
            lastChapters = [c for c in self.chapters if c.startTime() <= startTimeLimit]
            util.DEBUG_LOG('Found {0} chapters among {1}'.format(len(lastChapters), len(self.chapters)))
            if len(lastChapters) == 0:
                return False
            chapter = lastChapters[-1]

        util.DEBUG_LOG('New start time is {0}'.format(chapter.startTime()))
        self.skipByOffset(chapter.startTime() - lastSelectedOffset, without_osd=without_osd)
        return True

    def skipForward(self, without_osd=False):
        self.skipByStep("positive", without_osd)

    def skipBack(self, without_osd=False):
        self.skipByStep("negative", without_osd)

    def skipByStep(self, direction="positive", without_osd=False):
        step = self.determineSkipStep(direction)
        self.skipByOffset(step, without_osd)

    def skipByOffset(self, offset, without_osd=False):
        if offset is not None:
            if not self.seekByOffset(offset, without_osd=without_osd):
                return

        if self.useAutoSeek:
            self.delayedSeek()
        else:
            self.setProperty('button.seek', '1')

    def delayedSeek(self):
        self.setProperty('button.seek', '1')
        delay = self._autoSeekDelay

        if delay > 0:
            self._delayedSeekTimeout = time.time() + delay

            if not self._delayedSeekThread or not self._delayedSeekThread.is_alive():
                self._delayedSeekThread = threading.Thread(target=self._delayedSeek)
                self._delayedSeekThread.start()
        else:
            # Do seek now
            self._performSeek()
            self.resetSeeking()

    def _delayedSeek(self):
        try:
            while not util.MONITOR.waitForAbort(0.1):
                if time.time() > self._delayedSeekTimeout or not self._delayedSeekTimeout:
                    break

            if not util.MONITOR.abortRequested() and self._delayedSeekTimeout is not None:
                self._performSeek()
        except:
            util.ERROR()

    def _performSeek(self):
        self._lastSkipDirection = None
        self._forcedLastSkipAmount = None
        self.doSeek()

    def handleDialog(self, func):
        self.hasDialog = True

        try:
            func()
        finally:
            self.resetTimeout()
            self.hasDialog = False

    def videoSettingsHaveChanged(self):
        changed = False
        if (
            self.player.video.settings.prefOverrides != self.initialVideoSettings or
            self.player.video.selectedAudioStream() != self.initialAudioStream
        ):
            self.initialVideoSettings = dict(self.player.video.settings.prefOverrides)
            self.initialAudioStream = self.player.video.selectedAudioStream()
            changed = True

        if self.player.video.selectedSubtitleStream(
                forced_subtitles_override=util.advancedSettings.forcedSubtitlesOverride
        ) != self.initialSubtitleStream:
            self.initialSubtitleStream = \
                self.player.video.selectedSubtitleStream(
                    forced_subtitles_override=util.advancedSettings.forcedSubtitlesOverride)
            if changed or self.handler.mode == self.handler.MODE_RELATIVE:
                return True
            else:
                return 'SUBTITLE'

        return changed

    def repeatButtonClicked(self):
        pl = self.handler.playlist

        if pl:
            if pl.isRepeatOne:
                pl.setRepeat(False, one=False)
                self.updateProperties()
            elif pl.isRepeat:
                pl.setRepeat(False, one=True)
                pl.refresh(force=True)
            else:
                pl.setRepeat(True)
                pl.refresh(force=True)
        else:
            xbmc.executebuiltin('PlayerControl(Repeat)')

    def shuffleButtonClicked(self):
        if self.handler.playlist:
            self.handler.playlist.setShuffle()

    def optionsButtonClicked(self):  # Button currently commented out.
        pass
        # options = []

        # options.append({'key': 'kodi_video', 'display': 'Video Options'})
        # options.append({'key': 'kodi_audio', 'display': 'Audio Options'})

        # choice = dropdown.showDropdown(options, (1360, 1060), close_direction='down', pos_is_bottom=True, close_on_playback_ended=True)

        # if not choice:
        #     return

        # if choice['key'] == 'kodi_video':
        #     xbmc.executebuiltin('ActivateWindow(OSDVideoSettings)')
        # elif choice['key'] == 'kodi_audio':
        #     xbmc.executebuiltin('ActivateWindow(OSDAudioSettings)')

    def subtitleButtonClicked(self):
        options = []

        options.append({'key': 'download', 'display': T(32405, 'Download Subtitles')})
        if xbmc.getCondVisibility('VideoPlayer.HasSubtitles'):
            if xbmc.getCondVisibility('VideoPlayer.SubtitlesEnabled'):
                options.append({'key': 'delay', 'display': T(32406, 'Subtitle Delay')})
                options.append({'key': 'cycle', 'display': T(32407, 'Next Subtitle')})
            options.append(
                {
                    'key': 'enable',
                    'display': xbmc.getCondVisibility(
                        'VideoPlayer.SubtitlesEnabled + VideoPlayer.HasSubtitles'
                    ) and T(32408, 'Disable Subtitles') or T(32409, 'Enable Subtitles')
                }
            )

        choice = dropdown.showDropdown(options, (1360, 1060), close_direction='down', pos_is_bottom=True, close_on_playback_ended=True)

        if not choice:
            return

        if choice['key'] == 'download':
            self.hideOSD()
            builtin.ActivateWindow('SubtitleSearch')
        elif choice['key'] == 'delay':
            self.hideOSD()
            builtin.Action('SubtitleDelay')
        elif choice['key'] == 'cycle':
            builtin.Action('CycleSubtitle')
        elif choice['key'] == 'enable':
            builtin.Action('ShowSubtitles')

    def showSettings(self):
        with self.propertyContext('settings.visible'):
            playersettings.showDialog(self.player.video, via_osd=True, parent=self)

        changed = self.videoSettingsHaveChanged()
        if changed == 'SUBTITLE':
            self.handler.setSubtitles()
        elif changed:
            self.doSeek(self.trueOffset(), settings_changed=True)

    def setBigSeekShift(self):
        closest = None
        for mli in self.bigSeekControl:
            if mli.dataSource > self.selectedOffset:
                break
            closest = mli
        if not closest:
            return

        self.bigSeekOffset = self.selectedOffset - closest.dataSource
        pxOffset = int(self.bigSeekOffset / float(self.duration) * 1920)
        self.bigSeekGroupControl.setPosition(-8 + pxOffset, 917)
        self.bigSeekControl.selectItem(closest.pos())
        self._seeking = True
        # xbmc.sleep(100)

    def updateBigSeek(self, changed=False):
        if changed:
            self.bigSeekChanged = True
            self.selectedOffset = self.bigSeekControl.getSelectedItem().dataSource + self.bigSeekOffset
            self.updateProgress(set_to_current=False)
        self.resetSkipSteps()

    def bigSeekSelected(self):
        self.bigSeekChanged = True
        self.setFocusId(self.MAIN_BUTTON_ID)

    def updateProperties(self, **kwargs):
        if not self.started:
            return

        if self.fromSeek:
            self.setFocusId(self.MAIN_BUTTON_ID)
            self.fromSeek = 0

        self.setProperty('has.bif', self.bifURL and '1' or '')
        self.setProperty('video.title', self.title)
        self.setProperty('video.title2', self.title2)
        self.setProperty('is.show', (self.player.video.type == 'episode') and '1' or '')
        self.setProperty('time.left', util.timeDisplay(self.duration))

        pq = self.handler.playlist
        if pq:
            self.setProperty('has.playlist', '1')
            self.setProperty('pq.isRemote', pq.isRemote and '1' or '')
            self.setProperty('pq.hasnext', pq.hasNext() and '1' or '')
            self.setProperty('pq.hasprev', pq.hasPrev() and '1' or '')
            self.setProperty('pq.repeat', pq.isRepeat and '1' or '')
            self.setProperty('pq.repeat.one', pq.isRepeatOne and '1' or '')
            self.setProperty('pq.shuffled', pq.isShuffled and '1' or '')
        else:
            self.setProperties(('pq.isRemote', 'pq.hasnext', 'pq.hasprev', 'pq.repeat', 'pq.shuffled', 'has.playlist'), '')

        self.updateCurrent()

        div = int(self.duration / 12)
        items = []
        for x in range(12):
            offset = div * x
            items.append(kodigui.ManagedListItem(data_source=offset))
        self.bigSeekControl.reset()
        self.bigSeekControl.addItems(items)

    def updateCurrent(self, update_position_control=True):
        ratio = self.trueOffset() / float(self.duration)

        if update_position_control:
            w = int(ratio * self.SEEK_IMAGE_WIDTH)
            self.positionControl.setWidth(w)

        to = self.trueOffset()
        self.setProperty('time.current', util.timeDisplay(to))
        self.setProperty('time.left', util.timeDisplay(self.duration - to))

        _fmt = util.timeFormat.replace(":%S", "")

        val = time.strftime(_fmt, time.localtime(time.time() + ((self.duration - to) / 1000)))
        if not util.padHour and val[0] == "0" and val[1] != ":":
            val = val[1:]

        self.setProperty('time.end', val)

    def doSeek(self, offset=None, settings_changed=False):
        self._applyingSeek = True
        self._ignoreInput = settings_changed
        offset = self.selectedOffset if offset is None else offset
        self.resetSkipSteps()
        self.updateProgress(offset=offset)

        try:
            self.handler.seek(offset, settings_changed=settings_changed)
        finally:
            self.resetSeeking()

    def seekByOffset(self, offset, auto_seek=False, without_osd=False):
        """
        Sets the selected offset and updates the progress bar to visually represent the current seek
        :param offset: offset to seek to
        :param auto_seek: whether to automatically seek to :offset: after a certain amount of time
        :param without_osd: indicates whether this seek was done with or without OSD
        :return:
        """
        if self.selectedOffset is None:
            self.selectedOffset = self.offset
        lastSelectedOffset = self.selectedOffset
        # If we are seeking forward and already past 5 seconds from end, don't seek at all
        if lastSelectedOffset > self.duration - 5000 and offset > 0:
            return False

        self._seeking = True
        self._seekingWithoutOSD = without_osd
        self.selectedOffset += offset
        # Don't skip past 5 seconds from end
        if self.selectedOffset > self.duration - 5000:
            # offset = +100, at = 80000, duration = 80007, realoffset = 2
            self._forcedLastSkipAmount = self.duration - 5000 - lastSelectedOffset
            self.selectedOffset = self.duration - 5000
        # Don't skip back past 1 (0 is handled specially so seeking to 0 will not do a seek)
        elif self.selectedOffset < 1:
            # offset = -100, at = 5, realat = -95, realoffset = 1 - 5 = -4
            self._forcedLastSkipAmount = 1 - lastSelectedOffset
            self.selectedOffset = 1

        self.updateProgress(set_to_current=False)
        self.setBigSeekShift()
        if auto_seek:
            self.resetAutoSeekTimer()
        self.bigSeekHideTimer.reset()
        return True

    def seekMouse(self, action, without_osd=False, preview=False):
        x = self.mouseXTrans(action.getAmount1())
        y = self.mouseYTrans(action.getAmount2())
        if not (self.BAR_Y <= y <= self.BAR_BOTTOM):
            return

        if not (self.BAR_X <= x <= self.BAR_RIGHT):
            return

        self._seeking = True
        self._seekingWithoutOSD = without_osd

        self.selectedOffset = int((x - self.BAR_X) / float(self.SEEK_IMAGE_WIDTH) * self.duration)
        if not preview:
            self.doSeek()
            if not xbmc.getCondVisibility('Window.IsActive(videoosd) | Player.Rewinding | Player.Forwarding'):
                self.hideOSD()
        else:
            self.updateProgress(set_to_current=False)
            self.setProperty('button.seek', '1')

    def shouldShowIntroSkip(self):
        if self.intro:
            if self._enableIntroSkip and \
                    int(self.intro.startTimeOffset) <= self.offset <= int(self.intro.endTimeOffset):
                if self.auto_skip_intro:
                    return True
                self.setProperty('show.introSkip', '1')

                if self._introSkipShownStarted is None:
                    self._introSkipShownStarted = time.time()

                else:
                    if self._introSkipShownStarted + self.skip_intro_button_timeout <= time.time():
                        self.setProperty('show.introSkip_OSDOnly', '1')
                return True
            self.setProperty('show.introSkip', '')
        return False

    def setup(self, duration, offset=0, bif_url=None, title='', title2='', chapters=None):
        self.title = title
        self.title2 = title2
        self.setProperty('video.title', title)
        self.setProperty('is.show', (self.player.video.type == 'episode') and '1' or '')
        self.setProperty('has.playlist', self.handler.playlist and '1' or '')
        self.setProperty('shuffled', (self.handler.playlist and self.handler.playlist.isShuffled) and '1' or '')
        self.baseOffset = offset
        self.offset = 0
        self._duration = duration
        self.chapters = chapters or []
        self.bifURL = bif_url
        self.hasBif = bool(self.bifURL)
        if self.hasBif:
            self.baseURL = re.sub('/\d+\?', '/{0}?', self.bifURL)
        self.update()

    def update(self, offset=None, from_seek=False):
        if from_seek:
            self.fromSeek = time.time()
        else:
            if time.time() - self.fromSeek > 0.5:
                self.fromSeek = 0

        if offset is not None:
            self.offset = offset
            self.selectedOffset = self.trueOffset()

        self.updateProgress()

    @property
    def duration(self):
        try:
            return self._duration or int(self.handler.player.getTotalTime() * 1000)
        except RuntimeError:  # Not playing
            return 1

    def updateProgress(self, set_to_current=True, offset=None):
        """
        Updates the progress bars (seek and position) and the currently-selected-time-label for the current position or
        seek state on the timeline.
        :param set_to_current: if True, sets both the position bar and the seek bar to the currently selected position,
                               otherwise we're in seek mode, whereas one of both bars move relatively to the currently
                               selected position depending on the direction of the seek
        :return: None
        """
        if not self.initialized:
            return

        offset = offset if offset is not None else \
            self.selectedOffset if self.selectedOffset is not None else self.trueOffset()
        ratio = offset / float(self.duration)
        w = int(ratio * self.SEEK_IMAGE_WIDTH)

        current_w = int(self.offset / float(self.duration) * self.SEEK_IMAGE_WIDTH)

        bifx = (w - int(ratio * 324)) + self.BAR_X
        # bifx = w
        self.selectionIndicator.setPosition(w, 896)
        if w < 51:
            self.selectionBox.setPosition(-50 + (50 - w), 0)
        elif w > 1869:
            self.selectionBox.setPosition(-100 + (1920 - w), 0)
        else:
            self.selectionBox.setPosition(-50, 0)
        self.setProperty('time.selection', util.simplifiedTimeDisplay(offset))
        if self.hasBif:
            self.setProperty('bif.image', self.handler.player.playerObject.getBifUrl(offset))
            self.bifImageControl.setPosition(bifx, 752)

        self.seekbarControl.setPosition(0, self.seekbarControl.getPosition()[1])
        if set_to_current:
            self.seekbarControl.setWidth(w)
            self.positionControl.setWidth(w)
        else:
            # we're seeking

            # current seek position below current offset? set the position bar's width to the current position of the
            # seek and the seek bar to the current position of the video, to visually indicate the backwards-seeking
            if self.selectedOffset < self.offset:
                self.positionControl.setWidth(current_w)
                self.seekbarControl.setWidth(w)

            # current seek position ahead of current offset? set the position bar's width to the current position of the
            # video and the seek bar to the current position of the seek, to visually indicate the forwards-seeking
            elif self.selectedOffset > self.offset:
                self.seekbarControl.setPosition(current_w, self.seekbarControl.getPosition()[1])
                self.seekbarControl.setWidth(w - current_w)
                # we may have "shortened" the width before, by seeking negatively, reset the position bar's width to
                # the current video's position if that's the case
                if self.positionControl.getWidth() < current_w:
                    self.positionControl.setWidth(current_w)

            else:
                self.seekbarControl.setWidth(w)
                self.positionControl.setWidth(w)

    def onPlaybackResumed(self):
        self._osdHideFast = True
        self.tick()

    def onPlaybackStarted(self):
        if self._ignoreInput:
            self._ignoreInput = False

    def onPlaybackPaused(self):
        self._osdHideFast = False

    def tick(self, offset=None):
        if not self.initialized:
            return

        if xbmc.getCondVisibility('Window.IsActive(busydialog) + !Player.Caching'):
            util.DEBUG_LOG('SeekDialog: Possible stuck busy dialog - closing')
            xbmc.executebuiltin('Dialog.Close(busydialog,1)')

        if not self.hasDialog and not self.playlistDialogVisible and self.osdVisible():
            if time.time() > self.timeout:
                if not xbmc.getCondVisibility('Window.IsActive(videoosd) | Player.Rewinding | Player.Forwarding'):
                    self.hideOSD()

            # try insta-hiding the OSDs when playback was requested
            elif self._osdHideFast:
                xbmc.executebuiltin('Dialog.Close(videoosd,true)')
                xbmc.executebuiltin('Dialog.Close(seekbar,true)')
                if not xbmc.getCondVisibility('Window.IsActive(videoosd) | Player.Rewinding | Player.Forwarding'):
                    self.hideOSD()

        self._osdHideFast = False

        try:
            self.offset = offset or int(self.handler.player.getTime() * 1000)
        except RuntimeError:  # Playback has stopped
            self.resetSeeking()
            return

        intro = self.shouldShowIntroSkip()
        if intro and self.auto_skip_intro:
            self.doSeek(int(self.intro.endTimeOffset) + 1)
            return True
        else:
            if intro and not self.osdVisible() and self.lastFocusID != self.SKIP_INTRO_BUTTON_ID and \
                    not self.getProperty('show.introSkip_OSDOnly'):
                self.setFocusId(self.SKIP_INTRO_BUTTON_ID)

            if offset or (self.autoSeekTimeout and time.time() >= self.autoSeekTimeout and
                          self.offset != self.selectedOffset):
                self.resetAutoSeekTimer(None)
                self.doSeek()
                return True

        self.updateCurrent(update_position_control=not self._seeking and not self._applyingSeek)

    @property
    def playlistDialogVisible(self):
        return self._playlistDialogVisible

    @playlistDialogVisible.setter
    def playlistDialogVisible(self, value):
        self._playlistDialogVisible = value
        self.setProperty('playlist.visible', '1' if value else '')

    def showPlaylistDialog(self):
        if not self.playlistDialog:
            self.playlistDialog = PlaylistDialog.create(show=False, handler=self.handler)

        self.playlistDialogVisible = True
        self.playlistDialog.doModal()
        self.resetTimeout()
        self.playlistDialogVisible = False

    def osdVisible(self):
        return xbmc.getCondVisibility('Control.IsVisible(801)')

    def showOSD(self):
        self.setProperty('show.OSD', '1')
        xbmc.executebuiltin('Dialog.Close(videoosd,true)')
        if xbmc.getCondVisibility('Player.showinfo'):
            xbmc.executebuiltin('Action(Info)')
        self.setFocusId(self.PLAY_PAUSE_BUTTON_ID)

    def hideOSD(self):
        self.setProperty('show.OSD', '')
        self.setFocusId(self.NO_OSD_BUTTON_ID)
        if self.shouldShowIntroSkip() and not self.getProperty('show.introSkip_OSDOnly'):
            self.setFocusId(self.SKIP_INTRO_BUTTON_ID)

        self.resetSeeking()
        self._osdHideAnimationTimeout = time.time() + self.OSD_HIDE_ANIMATION_DURATION

        self._osdHideFast = False
        if self.playlistDialog:
            self.playlistDialog.doClose()
            self.playlistDialogVisible = False


class PlaylistDialog(kodigui.BaseDialog):
    xmlFile = 'script-plex-video_current_playlist.xml'
    path = util.ADDON.getAddonInfo('path')
    theme = 'Main'
    res = '1080i'
    width = 1920
    height = 1080

    LI_AR16X9_THUMB_DIM = (178, 100)
    LI_SQUARE_THUMB_DIM = (100, 100)

    PLAYLIST_LIST_ID = 101

    def __init__(self, *args, **kwargs):
        kodigui.BaseDialog.__init__(self, *args, **kwargs)
        self.handler = kwargs.get('handler')
        self.playlist = self.handler.playlist

    def onFirstInit(self):
        self.handler.player.on('playlist.changed', self.playQueueCallback)
        self.handler.player.on('session.ended', self.sessionEnded)
        self.playlistListControl = kodigui.ManagedControlList(self, self.PLAYLIST_LIST_ID, 6)
        self.fillPlaylist()
        self.updatePlayingItem()
        self.setFocusId(self.PLAYLIST_LIST_ID)

    def onClick(self, controlID):
        if controlID == self.PLAYLIST_LIST_ID:
            self.playlistListClicked()

    def playlistListClicked(self):
        mli = self.playlistListControl.getSelectedItem()
        if not mli:
            return
        self.handler.playAt(mli.pos())
        self.updatePlayingItem()

    def sessionEnded(self, **kwargs):
        util.DEBUG_LOG('Video OSD: Session ended - closing')
        self.doClose()

    def createListItem(self, pi):
        if pi.type == 'episode':
            return self.createEpisodeListItem(pi)
        elif pi.type in ('movie', 'clip'):
            return self.createMovieListItem(pi)

    def createEpisodeListItem(self, episode):
        label2 = u'{0} \u2022 {1}'.format(
            episode.grandparentTitle,
            u'{0}{1} \u2022 {2}{3}'.format(T(32310, 'S'), episode.parentIndex, T(32311, 'E'), episode.index)
        )
        mli = kodigui.ManagedListItem(episode.title, label2, thumbnailImage=episode.thumb.asTranscodedImageURL(*self.LI_AR16X9_THUMB_DIM), data_source=episode)
        mli.setProperty('track.duration', util.durationToShortText(episode.duration.asInt()))
        mli.setProperty('video', '1')
        mli.setProperty('watched', episode.isWatched and '1' or '')
        return mli

    def createMovieListItem(self, movie):
        mli = kodigui.ManagedListItem(movie.title, movie.year, thumbnailImage=movie.art.asTranscodedImageURL(*self.LI_AR16X9_THUMB_DIM), data_source=movie)
        mli.setProperty('track.duration', util.durationToShortText(movie.duration.asInt()))
        mli.setProperty('video', '1')
        mli.setProperty('watched', movie.isWatched and '1' or '')
        return mli

    def playQueueCallback(self, **kwargs):
        mli = self.playlistListControl.getSelectedItem()
        pi = mli.dataSource
        plexID = pi['comment'].split(':', 1)[0]
        viewPos = self.playlistListControl.getViewPosition()

        self.fillPlaylist()

        for ni in self.playlistListControl:
            if ni.dataSource['comment'].split(':', 1)[0] == plexID:
                self.playlistListControl.selectItem(ni.pos())
                break

        xbmc.sleep(100)

        newViewPos = self.playlistListControl.getViewPosition()
        if viewPos != newViewPos:
            diff = newViewPos - viewPos
            self.playlistListControl.shiftView(diff, True)

    def updatePlayingItem(self):
        playing = self.handler.player.video.ratingKey
        for mli in self.playlistListControl:
            mli.setProperty('playing', mli.dataSource.ratingKey == playing and '1' or '')

    def fillPlaylist(self):
        items = []
        idx = 1
        for pi in self.playlist.items():
            mli = self.createListItem(pi)
            if mli:
                mli.setProperty('track.number', str(idx))
                items.append(mli)
                idx += 1

        self.playlistListControl.reset()
        self.playlistListControl.addItems(items)
