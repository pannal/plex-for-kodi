from __future__ import absolute_import

import plexnet
from kodi_six import xbmc
from kodi_six import xbmcgui

from lib import metadata
from lib import util
from lib.util import T
from . import kodigui
from .dialog import showOptionsDialog
from .mixins.subtitledl import PlexSubtitleDownloadMixin


class VideoSettingsDialog(kodigui.BaseDialog, util.CronReceiver, PlexSubtitleDownloadMixin):
    xmlFile = 'script-plex-video_settings_dialog.xml'
    path = util.ADDON.getAddonInfo('path')
    theme = 'Main'
    res = '1080i'
    width = 1920
    height = 1080

    SETTINGS_LIST_ID = 100

    def __init__(self, *args, **kwargs):
        kodigui.BaseDialog.__init__(self, *args, **kwargs)
        PlexSubtitleDownloadMixin.__init__(self, *args, **kwargs)
        self.video = kwargs.get('video')
        self.viaOSD = kwargs.get('via_osd')
        self.nonPlayback = kwargs.get('non_playback')
        self.parent = kwargs.get('parent')
        self.sessionID = None
        if self.parent and self.parent.player:
            self.sessionID = self.parent.player.handler.sessionID
        self.roundRobin = kwargs.get('round_robin', True)
        self.lastSelectedItem = 0

        if not self.video.mediaChoice:
            playerObject = plexnet.plexplayer.PlexPlayer(self.video)
            playerObject.build()

    def onFirstInit(self):
        self.settingsList = kodigui.ManagedControlList(self, self.SETTINGS_LIST_ID, 6)
        self.setProperty('heading', T(32343, 'Settings'))
        if self.viaOSD:
            self.setProperty('via.OSD', '1')
        self.showSettings(True)
        util.CRON.registerReceiver(self)

    def onAction(self, action):
        try:
            if not xbmc.getCondVisibility('Player.HasMedia') and not self.nonPlayback:
                self.doClose()
                return
        except:
            util.ERROR()

        if self.roundRobin and action in (xbmcgui.ACTION_MOVE_UP, xbmcgui.ACTION_MOVE_DOWN) and \
                self.getFocusId() == self.SETTINGS_LIST_ID:
            to_pos = None
            last_index = self.settingsList.size() - 1
            if action == xbmcgui.ACTION_MOVE_UP and self.lastSelectedItem == 0 and self.settingsList.topHasFocus():
                to_pos = last_index

            elif action == xbmcgui.ACTION_MOVE_DOWN and self.lastSelectedItem == last_index \
                    and self.settingsList.bottomHasFocus():
                to_pos = 0

            if to_pos is not None:
                self.settingsList.setSelectedItemByPos(to_pos)
                self.lastSelectedItem = to_pos
                return

            self.lastSelectedItem = self.settingsList.control.getSelectedPosition()

        kodigui.BaseDialog.onAction(self, action)

    def onClick(self, controlID):
        if controlID == self.SETTINGS_LIST_ID:
            self.editSetting()

    def onClosed(self):
        util.CRON.cancelReceiver(self)

    def tick(self):
        if self.nonPlayback:
            return

        if not xbmc.getCondVisibility('Player.HasMedia'):
            self.doClose()
            return

    @property
    def qualityOverride(self):
        quality_type = self.video.getQualityType()
        return self.video.settings.getPrefOverride(quality_type, self.video.settings.getQualityIndex(quality_type))

    def showSettings(self, init=False):
        video = self.video
        override = self.qualityOverride
        if override is not None and override < 16:
            current = T((32001, 32017, 32002, 32016, 32003, 32004, 32005, 32015, 32006, 32007, 32008, 32009, 32010,
                         32011)[16 - override])
        else:
            current = u'{0} {1} ({2})'.format(
                plexnet.util.bitrateToString(video.mediaChoice.media.bitrate.asInt() * 1000),
                video.mediaChoice.media.getVideoResolutionString(),
                video.mediaChoice.media.title or T(32001, 'Original')
            )

        audio, subtitle = self.getAudioAndSubtitleInfo()

        options = [
            ('audio', T(32395, 'Audio'), audio),
            ('subs', T(32396, 'Subtitles'), subtitle),
            ('quality', T(32397, 'Quality'), u'{0}'.format(current)),
            ('download_subs', T(33703, "Download subtitles"), ''),
        ]

        if not self.nonPlayback:
            options += [
                ('kodi_video', T(32398, 'Kodi Video Settings'), ''),
                ('kodi_audio', T(32399, 'Kodi Audio Settings'), ''),
            ]
            if util.KODI_VERSION_MAJOR >= 18:
                options.append(('kodi_subtitle', T(32492, 'Kodi Subtitle Settings'), ''))
                if xbmc.getCondVisibility('Player.HasResolutions'):
                    options.append(('kodi_resolutions', T(32968, 'Kodi Resolution Settings'), ''))
            if util.KODI_VERSION_MAJOR >= 20 and xbmc.getCondVisibility('System.HasCMS'):
                options.append(('kodi_colours', T(32967, 'Kodi Colour Settings'), ''))

        if self.viaOSD:
            if self.parent.getProperty("show.PPI"):
                options += [
                    ('stream_info', T(32483, 'Hide Stream Info'), ''),
                ]
            else:
                options += [
                    ('stream_info', T(32484, 'Show Stream Info'), ''),
                ]

        items = []
        for o in options:
            item = kodigui.ManagedListItem(o[1], o[2], data_source=o[0])
            items.append(item)
        if init:
            self.settingsList.reset()
            self.settingsList.addItems(items)
        else:
            self.settingsList.replaceItems(items)

        if self.nonPlayback:
            # we don't have enough items for a scrollbar, increase width
            self.settingsList.setWidth(1000)

        self.setFocusId(self.SETTINGS_LIST_ID)

    def getAudioAndSubtitleInfo(self):
        sas = self.video.selectedAudioStream()
        if sas:
            if len(self.video.audioStreams) > 1:
                audio = sas and u'{0} \u2022 {1} {2}'.format(sas.getTitle(metadata.apiTranslate),
                                                             len(self.video.audioStreams) - 1, T(32307, 'More')) \
                        or T(32309, 'None')
            else:
                audio = sas and sas.getTitle(metadata.apiTranslate) or T(32309, 'None')
        else:
            audio = T(32309, 'None')

        sss = self.video.selectedSubtitleStream(
            forced_subtitles_override=util.getSetting("forced_subtitles_override") and plexnet.util.ACCOUNT.subtitlesForced == 0,
            deselect_subtitles=util.getSetting("disable_subtitle_languages")
        )

        if sss:
            if len(self.video.subtitleStreams) > 1:
                subtitle = u'{0} \u2022 {1} {2}'.format(sss.getTitle(metadata.apiTranslate), len(self.video.subtitleStreams) - 1, T(32307, 'More'))
            else:
                subtitle = sss.getTitle(metadata.apiTranslate)
        else:
            if self.video.subtitleStreams:
                subtitle = u'{0} \u2022 {1} {2}'.format(T(32309, 'None'), len(self.video.subtitleStreams), T(32308, 'Available'))
            else:
                subtitle = T(32309, 'None')

        return audio, subtitle

    def editSetting(self):
        mli = self.settingsList.getSelectedItem()
        if not mli:
            return

        result = mli.dataSource

        if result == 'audio':
            showAudioDialog(self.video, non_playback=self.nonPlayback, session_id=self.sessionID)
        elif result == 'subs':
            showSubtitlesDialog(self.video, non_playback=self.nonPlayback, session_id=self.sessionID)
        elif result == 'download_subs':
            downloaded = self.downloadPlexSubtitles(self.video, non_playback=self.nonPlayback)
            if downloaded:
                self.video.selectStream(downloaded, from_session=not self.nonPlayback, sync_to_server=False)
                self.video.manually_selected_sub_stream = downloaded.id
        elif result == 'quality':
            idx = None
            override = self.qualityOverride
            if override is not None and override < 16:
                idx = 16 - override
            showQualityDialog(self.video, non_playback=self.nonPlayback, selected_idx=idx)
        elif result == 'kodi_video':
            xbmc.executebuiltin('ActivateWindow(OSDVideoSettings)')
        elif result == 'kodi_audio':
            xbmc.executebuiltin('ActivateWindow(OSDAudioSettings)')
        elif result == 'kodi_subtitle':
            xbmc.executebuiltin('ActivateWindow(OSDSubtitleSettings)')
        elif result == 'kodi_colours':
            xbmc.executebuiltin('ActivateWindow(osdcmssettings)')
        elif result == 'kodi_resolutions':
            xbmc.executebuiltin("Action(PlayerResolutionSelect)")
        elif result == "stream_info":
            if self.parent:
                if self.parent.getProperty("show.PPI"):
                    self.parent.hidePPIDialog()
                else:
                    #xbmc.executebuiltin('Action(PlayerProcessInfo)')
                    self.parent.showPPIDialog()
            self.doClose()
            return

        self.showSettings()


def showAudioDialog(video, non_playback=False, session_id=None):
    options = []
    idx = None
    for i, s in enumerate(video.audioStreams):
        if s.isSelected():
            idx = i
        options.append((s, (s.getTitle(metadata.apiTranslate), s.title)))
    choice = showOptionsDialog(T(32395, 'Audio'), options, non_playback=non_playback, selected_idx=idx,
                               trim=False)
    if choice is None:
        return

    video.selectStream(choice, from_session=not non_playback, session_id=session_id)
    video.clearCache()


def showSubtitlesDialog(video, non_playback=False, session_id=None):
    options = [(plexnet.plexstream.NoneStream(), 'None')]
    idx = None
    sss = video.selectedSubtitleStream(
        forced_subtitles_override=util.getSetting("forced_subtitles_override") and plexnet.util.ACCOUNT.subtitlesForced == 0,
        deselect_subtitles=util.getSetting("disable_subtitle_languages")
    )
    for i, s in enumerate(video.subtitleStreams):
        if s == sss:
    #for i, s in enumerate(video.subtitleStreams):
    #    if s.isSelected():
            idx = i + 1
        options.append((s, s.getTitle(metadata.apiTranslate)))

    choice = showOptionsDialog(T(32396, 'Subtitle'), options, non_playback=non_playback, selected_idx=idx)
    if choice is None:
        return

    video.selectStream(choice, from_session=not non_playback, session_id=session_id)
    video.clearCache()
    video.manually_selected_sub_stream = choice.id


def showQualityDialog(video, non_playback=False, selected_idx=None):
    options = []
    video_bitrate = video.mediaChoice.media.bitrate.asInt()

    if video.settings.getPreference('clamp_video_bitrates', True):
        bitrates = list(reversed(video.settings.getGlobal("transcodeVideoBitrates")))[1:]
        for (i, l) in enumerate((32017, 32002, 32016, 32003, 32004, 32005, 32015, 32006, 32007, 32008, 32009, 32010,
                                 32011)):
            br_in_list = int(bitrates[i])
            if br_in_list > video_bitrate:
                if selected_idx is not None:
                    selected_idx -= 1
                continue

            options.append((15 - i, T(l)))
    else:
        options = [(15 - i, T(l)) for (i, l) in enumerate((32017, 32002, 32016, 32003, 32004, 32005, 32015, 32006,
                                                           32007, 32008, 32009, 32010, 32011))]


    options.insert(0, (16, u'{0} {1} ({2})'.format(
                plexnet.util.bitrateToString(video_bitrate * 1000),
                video.mediaChoice.media.getVideoResolutionString(),
                T(32001, 'Original')
            )))

    choice = showOptionsDialog('Quality', options, non_playback=non_playback, selected_idx=selected_idx)
    if choice is None:
        return

    video.settings.setPrefOverride('local_quality2', choice)
    video.settings.setPrefOverride('remote_quality2', choice)
    video.settings.setPrefOverride('online_quality2', choice)


def showDialog(video, non_playback=False, via_osd=False, parent=None):
    w = VideoSettingsDialog.open(video=video, non_playback=non_playback, via_osd=via_osd, parent=parent)
    del w
    util.garbageCollect()
