from __future__ import absolute_import
from kodi_six import xbmc
from kodi_six import xbmcgui
from . import kodigui
from . import windowutils

from lib import util
from lib.util import T

import plexnet


class Setting(object):
    type = None
    ID = None
    label = None
    desc = None
    default = None

    def translate(self, val):
        return str(val)

    def get(self):
        return util.getSetting(self.ID, self.default)

    def set(self, val):
        old = self.get()
        if old != val:
            util.DEBUG_LOG('Setting: {0} - changed from [{1}] to [{2}]'.format(self.ID, old, val))
            plexnet.util.APP.trigger('change:{0}'.format(self.ID))
        return util.setSetting(self.ID, val)

    def valueLabel(self):
        return self.translate(self.get())

    def __repr__(self):
        return '<Setting {0}={1}>'.format(self.ID, self.get())


class BasicSetting(Setting):
    def __init__(self, ID, label, default, desc=''):
        self.ID = ID
        self.label = label
        self.default = default
        self.desc = desc

    def description(self, desc):
        self.desc = desc
        return self


class ListSetting(BasicSetting):
    type = 'LIST'
    options = ()

    def translate(self, val):
        return self.options[len(self.options) - 1 - val]

    def optionLabels(self):
        return self.options

    def optionIndex(self):
        return len(self.options) - 1 - self.get()

    def set(self, val):
        BasicSetting.set(self, len(self.options) - 1 - val)


class QualitySetting(ListSetting):
    options = (
        T(32001),
        T(32002),
        T(32003),
        T(32004),
        T(32005),
        T(32006),
        T(32007),
        T(32008),
        T(32009),
        T(32010),
        T(32011),
        T(32012),
        T(32013),
        T(32014),
    )


class ThemeMusicSetting(ListSetting):
    options = [
        T(32481),
    ] + [T(32482) % {"percentage": 10+i} for i in range(0, 100, 10)]


class BoolSetting(BasicSetting):
    type = 'BOOL'


class OptionsSetting(BasicSetting):
    type = 'OPTIONS'

    def __init__(self, ID, label, default, options):
        BasicSetting.__init__(self, ID, label, default)
        self.options = options

    def translate(self, val):
        for ID, label in self.options:
            if ID == val:
                return label

    def optionLabels(self):
        return [o[1] for o in self.options]

    def optionIndex(self):
        val = self.get()
        for i, o in enumerate(self.options):
            if val == o[0]:
                return i

        return 0


class InfoSetting(BasicSetting):
    type = 'INFO'

    def __init__(self, ID, label, info):
        BasicSetting.__init__(self, ID, label, None)
        self.info = info

    def valueLabel(self):
        return self.info


class PlatformSetting(InfoSetting):
    def __init__(self):
        InfoSetting.__init__(self, None, None, None)
        self.ID = 'platfom_version'
        self.label = T(32410, 'Platform Version')

    def valueLabel(self):
        try:
            from lib import distro
            dist = distro.linux_distribution()
            if dist and len(dist) > 1:
                plat = u'{0} {1}'.format(dist[0], dist[1])
            else:
                import platform
                plat = platform.platform()
                plat = u'{0} {1}'.format(plat[0], '.'.join(plat[1].split('.', 2)[:2]))
        except:
            util.ERROR()

        plat = plat.strip()

        if not plat:
            if xbmc.getCondVisibility('System.Platform.Android'):
                plat = 'Android'
            elif xbmc.getCondVisibility('System.Platform.OSX'):
                plat = 'OSX'
            elif xbmc.getCondVisibility('System.Platform.Darwin'):
                plat = 'Darwin'
            elif xbmc.getCondVisibility('System.Platform.Linux.RaspberryPi'):
                plat = 'Linux (RPi)'
            elif xbmc.getCondVisibility('System.Platform.Linux'):
                plat = 'Linux'
            elif xbmc.getCondVisibility('System.Platform.Windows'):
                plat = 'Windows'

        return plat or T(32411, 'Unknown')


class ServerVersionSetting(InfoSetting):
    def valueLabel(self):
        if not plexnet.plexapp.SERVERMANAGER.selectedServer:
            return ''

        return plexnet.plexapp.SERVERMANAGER.selectedServer.rawVersion or ''


class IPSetting(BasicSetting):
    type = 'IP'


class IntegerSetting(BasicSetting):
    type = 'INTEGER'


class Settings(object):
    SETTINGS = {
        'main': (
            T(32000, 'Main'), (
                BoolSetting(
                    'auto_signin', T(32038, 'Automatically Sign In'), False
                ).description(
                    T(32100, 'Skip user selection and pin entry on startup.')
                ),
                BoolSetting(
                    'post_play_auto', T(32039, 'Post Play Auto Play'), True
                ).description(
                    T(
                        32101,
                        "If enabled, when playback ends and there is a 'Next Up' item available, it will be automatically be played after a 15 second delay."
                    )
                ),
                ThemeMusicSetting('theme_music', T(32480, 'Theme music'), 5),
            )
        ),
        'audio': (
            T(32048, 'Audio'),
            ()
        ),
        'video': (
            T(32053, 'Video'), (
                QualitySetting('local_quality', T(32020, 'Local Quality'), 13),
                QualitySetting('remote_quality', T(32021, 'Remote Quality'), 8),
                QualitySetting('online_quality', T(32022, 'Online Quality'), 13),
                BoolSetting('playback_directplay', T(32025, 'Allow Direct Play'), True),
                BoolSetting('playback_remux', T(32026, 'Allow Direct Stream'), True),
                BoolSetting('allow_4k', T(32036, 'Allow 4K'), True).description(
                    T(32102, 'Enable this if your hardware can handle 4K playback. Disable it to force transcoding.')
                ),
                BoolSetting('allow_hevc', T(32037, 'Allow HEVC (h265)'), False).description(
                    T(32103, 'Enable this if your hardware can handle HEVC/h265. Disable it to force transcoding.')
                )
            )
        ),
        'subtitles': (
            T(32396, 'Subtitles'), (
                OptionsSetting(
                    'burn_subtitles',
                    T(32031, 'Burn Subtitles (Direct Play Only)'),
                    'auto',
                    (('auto', T(32030, 'Auto')), ('image', T(32029, 'Only Image Formats')), ('always', T(32028, 'Always')))
                ),
                BoolSetting('subtitle_downloads', T(32040, 'Enable Subtitle Downloading'), False)
            )
        ),
        'advanced': (
            T(32049, 'Advanced'), (
                OptionsSetting(
                    'allow_insecure', T(32032), 'never', (('never', T(32033)), ('same_network', T(32034)), ('always', T(32035)))
                ).description(
                    T(32104, 'When to connect to servers with no secure connections...')
                ),
                BoolSetting('gdm_discovery', T(32042, 'Server Discovery (GDM)'), True),
                BoolSetting('kiosk.mode', T(32043, 'Start Plex On Kodi Startup'), False),
                BoolSetting('debug', T(32024, 'Debug Logging'), False),
                BoolSetting(
                    'auto_skip_intro', T(32522, 'Auto Skip Intro'), False
                ).description(
                    T(3523, 'Automatically skip intros if available.')
                ),
                IntegerSetting(
                    'skip_intro_button_timeout', T(32521, 'Skip Intro Button Timeout'), 10
                ).description(
                    T(32524, 'Set how long the skip intro button shows for.')
                ),
            )
        ),
        'manual': (
            T(32050, 'Manual Servers'), (
                IPSetting('manual_ip_0', T(32044, 'Connection 1 IP'), ''),
                IntegerSetting('manual_port_0', T(32045, 'Connection 1 Port'), 32400),
                IPSetting('manual_ip_1', T(32046, 'Connection 2 IP'), ''),
                IntegerSetting('manual_port_1', T(32047, 'Connection 2 Port'), 32400)
            )
        ),
        'privacy': (
            T(32051, 'Privacy'),
            ()
        ),
        'about': (
            T(32052, 'About'), (
                InfoSetting('addon_version', T(32054, 'Addon Version'), util.ADDON.getAddonInfo('version')),
                InfoSetting('kodi_version', T(32055, 'Kodi Version'), xbmc.getInfoLabel('System.BuildVersion')),
                PlatformSetting(),
                InfoSetting('screen_res', T(32056, 'Screen Resolution'), xbmc.getInfoLabel('System.ScreenResolution').split('-')[0].strip()),
                ServerVersionSetting('server_version', T(32057, 'Current Server Version'), None)
            )
        ),
    }

    SECTION_IDS = ('main', 'video', 'subtitles', 'advanced', 'manual', 'about')

    def __getitem__(self, key):
        return self.SETTINGS[key]

# enable AV1 setting if kodi nexus
if util.KODI_VERSION_MAJOR >= 20:
    videoSettings = list(Settings.SETTINGS["video"])
    videoSettings[1] = tuple(list(videoSettings[1]) + [
        BoolSetting('allow_av1', T(32601, 'Allow AV1'), False).description(
            T(32103,
              'Enable this if your hardware can handle AV1. Disable it to force transcoding.')
        )
    ])
    Settings.SETTINGS["video"] = (videoSettings[0], videoSettings[1])


class SettingsWindow(kodigui.BaseWindow, windowutils.UtilMixin):
    xmlFile = 'script-plex-settings.xml'
    path = util.ADDON.getAddonInfo('path')
    theme = 'Main'
    res = '1080i'
    width = 1920
    height = 1080

    SECTION_LIST_ID = 75
    SETTINGS_LIST_ID = 100
    OPTIONS_LIST_ID = 125
    TOP_GROUP_ID = 200

    CLOSE_BUTTON_ID = 201
    PLAYER_STATUS_BUTTON_ID = 204

    def onFirstInit(self):
        self.settings = Settings()
        self.sectionList = kodigui.ManagedControlList(self, self.SECTION_LIST_ID, 6)
        self.settingsList = kodigui.ManagedControlList(self, self.SETTINGS_LIST_ID, 6)
        self.optionsList = kodigui.ManagedControlList(self, self.OPTIONS_LIST_ID, 6)

        self.setProperty('heading', T(32343, 'Settings'))
        self.showSections()
        self.setFocusId(75)
        self.lastSection = None
        self.checkSection()

    def onAction(self, action):
        try:
            self.checkSection()
            controlID = self.getFocusId()
            if action in (xbmcgui.ACTION_NAV_BACK, xbmcgui.ACTION_PREVIOUS_MENU):
                if self.getFocusId() == self.OPTIONS_LIST_ID:
                    self.setFocusId(self.SETTINGS_LIST_ID)
                    return
                # elif not xbmc.getCondVisibility('ControlGroup({0}).HasFocus(0)'.format(self.TOP_GROUP_ID)):
                #     self.setFocusId(self.TOP_GROUP_ID)
                #     return
            elif action == xbmcgui.ACTION_MOVE_RIGHT and controlID == 150:
                self.editSetting(from_right=True)
        except:
            util.ERROR()

        kodigui.BaseWindow.onAction(self, action)

    def onClick(self, controlID):
        if controlID == self.SECTION_LIST_ID:
            self.setFocusId(self.SETTINGS_LIST_ID)
        elif controlID == self.SETTINGS_LIST_ID:
            self.editSetting()
        elif controlID == self.OPTIONS_LIST_ID:
            self.changeSetting()
        elif controlID == self.CLOSE_BUTTON_ID:
            self.doClose()
        elif controlID == self.PLAYER_STATUS_BUTTON_ID:
            self.showAudioPlayer()

    def checkSection(self):
        mli = self.sectionList.getSelectedItem()
        if not mli:
            return

        if mli.dataSource == self.lastSection:
            return

        self.lastSection = mli.dataSource
        self.showSettings(self.lastSection)
        self.setProperty('section.about', self.lastSection == 'about' and '1' or '')
        util.DEBUG_LOG('Settings: Changed section ({0})'.format(self.lastSection))

    def showSections(self):
        items = []
        for sectionID in self.settings.SECTION_IDS:
            label = self.settings[sectionID][0]
            item = kodigui.ManagedListItem(label, data_source=sectionID)
            items.append(item)

        self.sectionList.addItems(items)

    def showSettings(self, section):
        settings = self.settings[section][1]
        if not settings:
            return self.settingsList.reset()

        items = []
        for setting in settings:
            item = kodigui.ManagedListItem(setting.label, setting.type != 'BOOL' and setting.valueLabel() or '', data_source=setting)
            item.setProperty('description', setting.desc)
            if setting.type == 'BOOL':
                item.setProperty('checkbox', '1')
                item.setProperty('checkbox.checked', setting.get() and '1' or '')

            items.append(item)

        self.settingsList.reset()
        self.settingsList.addItems(items)

    def editSetting(self, from_right=False):
        mli = self.settingsList.getSelectedItem()
        if not mli:
            return

        setting = mli.dataSource

        if setting.type in ('LIST', 'OPTIONS'):
            self.fillList(setting)
        elif setting.type == 'BOOL' and not from_right:
            self.toggleBool(mli, setting)
        elif setting.type == 'IP' and not from_right:
            self.editIP(mli, setting)
        elif setting.type == 'INTEGER' and not from_right:
            self.editInteger(mli, setting)

    def changeSetting(self):
        optionItem = self.optionsList.getSelectedItem()
        if not optionItem:
            return

        mli = self.settingsList.getSelectedItem()
        if not mli:
            return

        setting = mli.dataSource

        if setting.type == 'LIST':
            setting.set(optionItem.pos())
            mli.setLabel2(setting.valueLabel())
        elif setting.type == 'OPTIONS':
            setting.set(optionItem.dataSource)
            mli.setLabel2(setting.valueLabel())

        self.setFocusId(self.SETTINGS_LIST_ID)

    def fillList(self, setting):
        items = []
        if setting.type == 'LIST':
            for label in setting.optionLabels():
                items.append(kodigui.ManagedListItem(label))
        elif setting.type == 'OPTIONS':
            for ID, label in setting.options:
                items.append(kodigui.ManagedListItem(label, data_source=ID))

        self.optionsList.reset()
        self.optionsList.addItems(items)
        self.optionsList.selectItem(setting.optionIndex())
        self.setFocusId(self.OPTIONS_LIST_ID)

    def toggleBool(self, mli, setting):
        setting.set(not setting.get())
        mli.setProperty('checkbox.checked', setting.get() and '1' or '')

    def editIP(self, mli, setting):
        current = setting.get()
        edit = True
        if current:
            edit = xbmcgui.Dialog().yesno(
                T(32412, 'Edit Or Clear'),
                T(32413, 'Edit IP address or clear the current setting?'),
                nolabel=T(32414, 'Clear'),
                yeslabel=T(32415, 'Edit')
            )

        if edit:
            result = xbmcgui.Dialog().input(T(32416, 'Enter IP Address'), current, xbmcgui.INPUT_IPADDRESS)
            if not result:
                return
        else:
            result = ''

        setting.set(result)
        mli.setLabel2(result)

    def editInteger(self, mli, setting):
        result = xbmcgui.Dialog().input(T(32417, 'Enter Port Number'), str(setting.get()), xbmcgui.INPUT_NUMERIC)
        if not result:
            return
        setting.set(int(result))
        mli.setLabel2(result)


class SelectDialog(kodigui.BaseDialog, util.CronReceiver):
    xmlFile = 'script-plex-settings_select_dialog.xml'
    path = util.ADDON.getAddonInfo('path')
    theme = 'Main'
    res = '1080i'
    width = 1920
    height = 1080

    OPTIONS_LIST_ID = 100

    def __init__(self, *args, **kwargs):
        kodigui.BaseDialog.__init__(self, *args, **kwargs)
        self.heading = kwargs.get('heading')
        self.options = kwargs.get('options')
        self.choice = None

    def onFirstInit(self):
        self.optionsList = kodigui.ManagedControlList(self, self.OPTIONS_LIST_ID, 8)
        self.setProperty('heading', self.heading)
        self.showOptions()
        util.CRON.registerReceiver(self)

    def onAction(self, action):
        try:
            if not xbmc.getCondVisibility('Player.HasMedia'):
                self.doClose()
                return
        except:
            util.ERROR()

        kodigui.BaseDialog.onAction(self, action)

    def onClick(self, controlID):
        if controlID == self.OPTIONS_LIST_ID:
            self.setChoice()

    def onClosed(self):
        util.CRON.cancelReceiver(self)

    def tick(self):
        if not xbmc.getCondVisibility('Player.HasMedia'):
            self.doClose()
            return

    def setChoice(self):
        mli = self.optionsList.getSelectedItem()
        if not mli:
            return

        self.choice = self.options[self.optionsList.getSelectedPosition()][0]
        self.doClose()

    def showOptions(self):
        items = []
        for o in self.options:
            item = kodigui.ManagedListItem(o[1], data_source=o[0])
            items.append(item)

        self.optionsList.reset()
        self.optionsList.addItems(items)

        self.setFocusId(self.OPTIONS_LIST_ID)


def showOptionsDialog(heading, options):
    w = SelectDialog.open(heading=heading, options=options)
    choice = w.choice
    del w
    return choice


def showAudioDialog(video):
    options = [(s, s.getTitle()) for s in video.audioStreams]
    choice = showOptionsDialog(T(32048, 'Audio'), options)
    if choice is None:
        return

    video.selectStream(choice)


def showSubtitlesDialog(video):
    options = [(s, s.getTitle()) for s in video.subtitleStreams]
    options.insert(0, (plexnet.plexstream.NoneStream(), 'None'))
    choice = showOptionsDialog(T(32396, 'Subtitles'), options)
    if choice is None:
        return

    video.selectStream(choice)


def showQualityDialog(video):
    options = [(13 - i, T(l)) for (i, l) in enumerate((32001, 32002, 32003, 32004, 32005, 32006, 32007, 32008, 32009,
                                                       32010, 32011))]

    choice = showOptionsDialog(T(32397, 'Quality'), options)
    if choice is None:
        return

    video.settings.setPrefOverride('local_quality', choice)
    video.settings.setPrefOverride('remote_quality', choice)
    video.settings.setPrefOverride('online_quality', choice)


def openWindow():
    w = SettingsWindow.open()
    del w
