# coding=utf-8
from __future__ import absolute_import
from __future__ import unicode_literals

import json
import sys
import datetime
import types

import plexnet
from kodi_six import xbmc
from kodi_six import xbmcgui
from kodi_six import xbmcaddon
from threading import Timer
from iso639 import languages

import lib.cache
from lib import util
from lib import genres
from lib import actions
from lib.util import T
from . import kodigui
from . import windowutils


UNDEF = "__UNDEF__"

#MAIN_LANGUAGES = [l for l in languages if l.part1]
#SEP_LANGUAGES= [l for l in languages if l.part2t and l not in MAIN_LANGUAGES]

class Setting(object):
    type = None
    ID = None
    label = None
    desc = None
    default = None
    userAware = False
    isThemeRelevant = False
    backport_from = None
    show_cb = None

    def translate(self, val):
        return str(val)

    def should_show(self):
        return self.show_cb() if self.show_cb else True

    def get(self, *args, **kwargs):
        _id = kwargs.pop("_id", UNDEF)
        use_id = _id if _id != UNDEF else self.ID
        default = kwargs.pop("default", UNDEF)
        use_default = default if default != UNDEF else self.default

        value = util.getSetting(use_id, use_default)
        if value == use_default and self.backport_from:
            # fallback set and we're on default
            old_val = util.getSetting(self.backport_from, DEFAULT)

            # old setting was set
            if old_val != DEFAULT:
                # get correct old value
                old_val_cast = util.getSetting(self.backport_from, use_default)
                util.setSetting(self.backport_from, '')

                # old value is different from the new one, set
                if old_val_cast != use_default:
                    self.set(old_val_cast, skip_get=True)
                    value = old_val_cast
        return value

    def emit_events(self, id_, val, **kwargs):
        plexnet.util.APP.trigger('change:{0}'.format(id_), value=val)

    def emit_tr_events(self, id_, val, **kwargs):
        plexnet.util.APP.trigger('theme_relevant_setting', id=id_, value=val, **kwargs)

    def set(self, val, skip_get=False):
        if not skip_get:
            old = Setting.get(self)
            setRet = util.setSetting(self.ID, val)
            if old != val:
                util.DEBUG_LOG('Setting: {0} - changed from [{1}] to [{2}]', self.ID, old, val)
                self.emit_events(self.ID, val)
                if self.isThemeRelevant:
                    self.emit_tr_events(self.ID, val)
        else:
            setRet = util.setSetting(self.ID, val)
        return setRet

    def valueLabel(self):
        return self.translate(self.get())

    def __repr__(self):
        return '<Setting {0}={1}>'.format(self.ID, self.get())


class BasicSetting(Setting):
    def __init__(self, ID, label, default, desc='', theme_relevant=False, backport_from=None, show_cb=None):
        self.ID = ID
        self.label = label
        self.default = default
        self.desc = desc
        self.isThemeRelevant = theme_relevant
        self.backport_from = backport_from
        if show_cb:
            self.show_cb = show_cb
        util.DEFAULT_SETTINGS[ID] = default

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

    def set(self, val, skip_get=False):
        BasicSetting.set(self, len(self.options) - 1 - val, skip_get=skip_get)


class QualitySetting(ListSetting):
    options = (
        T(32001),
        T(32017),
        T(32002),
        T(32016),
        T(32003),
        T(32004),
        T(32005),
        T(32015),
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


class PlayedThresholdSetting(ListSetting):
    options = ['{} %'.format(perc) for perc in range(70, 100, 5)]


class BoolSetting(BasicSetting):
    type = 'BOOL'


class UserAwareSetting(BasicSetting):
    """
    A user-aware BoolSetting
    """
    userAware = True

    def __init__(self, *args, **kwargs):
        super(UserAwareSetting, self).__init__(*args, **kwargs)
        util.USER_SETTINGS.append(self.ID)

    @property
    def userAwareID(self):
        if plexnet.plexapp.ACCOUNT and plexnet.plexapp.ACCOUNT.ID:
            return '{}.{}'.format(self.ID, plexnet.plexapp.ACCOUNT.ID)
        return 'USER_AWARE'

    def emit_events(self, id_, val, **kwargs):
        plexnet.util.APP.trigger('change:{0}'.format(self.ID), key=self.userAwareID, value=val, skey=self.ID)

    def get(self, *args, **kwargs):
        _id = kwargs.pop("_id", UNDEF)
        default = kwargs.pop("default", UNDEF)
        return super(UserAwareSetting, self).get(*args,
                                                 _id=_id if _id != UNDEF else self.userAwareID, default=default,
                                                 **kwargs)

    def set(self, val, skip_get=False):
        if not skip_get:
            old = self.get(_id=self.userAwareID)
            if old != val:
                util.DEBUG_LOG('Setting: {0} - changed from [{1}] to [{2}]', self.userAwareID, old, val)
                self.emit_events(self.userAwareID, val)
                if self.isThemeRelevant:
                    self.emit_tr_events(self.userAwareID, val)
        return util.setSetting(self.userAwareID, val)


class BoolUserSetting(UserAwareSetting, BoolSetting):
    pass


class OptionsSetting(BasicSetting):
    type = 'OPTIONS'

    def __init__(self, ID, label, default, options, **kwargs):
        BasicSetting.__init__(self, ID, label, default, **kwargs)
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


DEFAULT = "__DEFAULT__"


class MultiOptionsSetting(OptionsSetting):
    type = 'MULTI'
    valueLabelDelim = ', '
    noneOption = None

    def __init__(self, ID, label, default, options, none_option=None, **kwargs):
        super(MultiOptionsSetting, self).__init__(ID, label, [], options, **kwargs)
        self.default = default
        self.noneOption = none_option
        util.JSON_SETTINGS.append(self.ID)

        # fixme: not sure why we initialize default with an empty list in the supercall
        util.DEFAULT_SETTINGS[ID] = default

    def get(self, *args, **kwargs):
        with_default = kwargs.pop('with_default', True)
        val = super(MultiOptionsSetting, self).get(*args, default=DEFAULT, **kwargs)
        if val and val != DEFAULT:
            try:
                return json.loads(val)
            except json.decoder.JSONDecodeError:
                # fallback for legacy settings that weren't json
                for o in self.options:
                    if o[0] == val:
                        return [val]
        elif val == DEFAULT:
            # backport old separated options
            ret = self.default[:]
            for o in self.options:
                lval = util.getSetting(o[0], DEFAULT)
                # we only support backporting booleans right now
                if lval != DEFAULT:
                    if lval == "true" and o[0] not in self.default:
                        ret.append(o[0])
                    elif lval == "false" and o[0] in self.default:
                        ret.remove(o[0])

            if ret != self.default:
                self.set(ret, skip_get=True)
                return ret
        return with_default and self.default or []

    def set(self, val, skip_get=False):
        super(MultiOptionsSetting, self).set(json.dumps(val), skip_get=skip_get)

    def translate(self, val, return_str=False, delim=", "):
        if isinstance(val, (list, tuple, set)):
            # keep options order
            data = [super(MultiOptionsSetting, self).translate(o[0]) for o in self.options if o[0] in val]
            if return_str:
                return delim.join(data)
            return data
        return super(MultiOptionsSetting, self).translate(val)

    def valueLabel(self, values=None):
        vals = values or self.get()
        if vals:
            return self.translate(vals, return_str=True, delim=self.valueLabelDelim)
        return T(33056, "None")

    def optionIndex(self):
        val = self.get()
        ret = []
        for i, o in enumerate(self.options):
            if o[0] in val:
                ret.append(i)
        return ret


class MultiUAOptionsSetting(MultiOptionsSetting, UserAwareSetting):
    pass


class KCMSetting(OptionsSetting):
    key = None

    def emit_events(self, id_, val, **kwargs):
        plexnet.util.APP.trigger('change:{0}'.format(self.ID), value=val)

    def get(self, *args, **kwargs):
        return getattr(lib.cache.kcm, self.key)

    def set(self, val, skip_get=False):
        if not skip_get:
            old = self.get()
            if old != val:
                util.DEBUG_LOG('Setting: {0} - changed from [{1}] to [{2}]', self.ID, old, val)
                self.emit_events(self.ID, val)

        lib.cache.kcm.write(**{self.key: val})


class BufferSetting(KCMSetting):
    key = "memorySize"


class ReadFactorSetting(KCMSetting):
    key = "readFactor"


class InfoSetting(BasicSetting):
    type = 'INFO'

    def __init__(self, ID, label, info):
        BasicSetting.__init__(self, ID, label, None)
        self.info = info

    def valueLabel(self):
        if isinstance(self.info, types.FunctionType):
            return self.info()
        return self.info


class PlatformSetting(InfoSetting):
    def __init__(self):
        InfoSetting.__init__(self, None, None, None)
        self.ID = 'platfom_version'
        self.label = T(32410, 'Platform Version')

    def valueLabel(self):
        plat = None
        try:
            if sys.version_info[0] >= 3:
                from lib import distro
                dist = distro.linux_distribution()
                if dist and len(dist) > 1:
                    plat = u'{0} {1}'.format(dist[0], dist[1])
            else:
                import platform
                dist = platform. dist()
                if dist and len(dist) > 1:
                   plat = u'{0} {1}'.format(dist[0], dist[1])
                else:
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


class KeySetting(BasicSetting):
    type = 'STRING'

    def value_setter(self):
        w = SchnorchelDialog()
        timeout = Timer(w.timeout, w.close)
        timeout.start()
        w.doModal()
        timeout.cancel()
        choice = w.key
        del w
        return choice

    def get(self, as_code=False, *args, **kwargs):
        code = super(KeySetting, self).get(default=None, *args, **kwargs)
        if as_code:
            return code

        if code is not None and code != "None":
            ak = actions.ActionKey(int(code))
            return ak

class Settings(object):
    SETTINGS = {
        'main': (
            T(32000, 'Main'), (
                BoolSetting('kiosk.mode', T(32043, 'Start Plex On Kodi Startup'), False),
                OptionsSetting(
                    'kiosk.delay', T(33651, 'Start Delay'),
                    0,
                    [(0, T(32481))] + [
                        (a, T(33091).format(sec_or_ms=a, unit_s_or_ms="s")) for a in
                        list(range(1, 11, 1)) + list(range(15, 125, 5))]
                ),
                BoolSetting(
                    'auto_signin', T(32038, 'Automatically Sign In'), False
                ).description(
                    T(32100, 'Skip user selection and pin entry on startup.')
                ),
                BoolSetting(
                    'search_use_kodi_kbd', T(32955, 'Use Kodi keyboard for searching'), False
                ),
                ThemeMusicSetting('theme_music', T(32480, 'Theme music'), 5),
                BoolSetting(
                    'theme_music_loop', T(33737, 'Loop theme music'), True
                ),
                PlayedThresholdSetting('played_threshold', T(33501, 'Video played threshold'), 1,
                                       show_cb=lambda: plexnet.plexapp.SERVERMANAGER.selectedServer.prefs.get("LibraryVideoPlayedThreshold", None) is None
                                       ).description(
                    T(
                        33502,
                        "Set this to the same value as your Plex server (Settings>Library>Video played threshold) to av"
                        "oid certain pitfalls, Default: 90 %"
                    )
                ),
                OptionsSetting(
                    'played_threshold_behaviour',
                    T(34022, 'Video play completion behaviour'),
                    3,
                    (
                        (0, T(34024, 'at selected threshold percentage')),
                        (1, T(34025, 'at final credits marker position')),
                        (2, T(34025, 'at first credits marker position')),
                        (3, T(34026, 'earliest between threshold percent and first credits marker')),
                    ),
                    show_cb=lambda: plexnet.plexapp.SERVERMANAGER.selectedServer.prefs.get(
                        "LibraryVideoPlayedAtBehaviour", None) is None
                ).description(T(34023, "Decide whether to use end credits markers to determine the 'watched' "
                                       "state of video items. When markers are not available the selected threshold "
                                       "percentage will be used.")),
                BoolSetting('use_alternate_seek2', T(33667, 'Use alternate seek'), util.altSeekRecommended).description(
                    T(33668, 'ATTENTION: Only enable this if you have reproducible audio issues after '
                             'seeking/resuming.\n\nUse an alternative seek method in videos, which can help in '
                             'problematic scenarios; brings its own issues/quirks. Disabled by default (enabled by '
                             'default for CoreELEC and LG WebOS)'
                )),
                BoolSetting(
                    'assume_resume', T(33711, 'Always resume media'), True
                ).description(
                    T(33712, 'When playback of an in-progress media is requested, resume it by default instead'
                             ' of asking whether to resume or start from the beginning.')
                ),
                BoolSetting(
                    'home_inprogress_resume', T(33713, 'Home: Resume in-progress items'), True
                ).description(
                    T(33714, 'Resume in-progress items directly instead of visiting the media.')
                ),
            )
        ),
        'video': (
            T(32053, 'Video'), (
                QualitySetting('local_quality2', T(32020, 'Local Quality'), 16),
                QualitySetting('remote_quality2', T(32021, 'Remote Quality'), 16),
                QualitySetting('online_quality2', T(32022, 'Online Quality'), 16),
                MultiOptionsSetting(
                    'playback_features', T(33058, ''),
                    ["playback_directplay", "playback_remux", "allow_4k"],
                    (
                        ('playback_directplay', T(32025, '')),
                        ('playback_remux', T(32026, '')),
                        ('allow_4k', T(32036, '')),
                    )
                ).description(T(33060, "").format(
                    feature_ds=T(32026, ''),
                    desc_ds=T(32979, ''),
                    feature_4k=T(32036, ''),
                    desc_4k=T(32102, ''))),
                BoolSetting(
                    'disable_hdr', T(33660, 'Disable HDR'), False
                ).description(T(33661, "If you don't want your client to handle HDR (or HDR-fallback), "
                                       "enable this to force transcoding. Doesn't apply to DV Profile 5.")
                ),
                BoolSetting(
                    'clamp_video_bitrates', T(33685, 'Clamp video bitrate'), True
                ).description(T(33686, "Only show bitrate targets lower than the current video's bitrate.")
                ),
                MultiOptionsSetting(
                    'allowed_codecs', T(33059, ''),
                    ["allow_hevc", "allow_vc1"],
                    [
                        ('allow_hevc', T(32037, '')),
                        ('allow_vc1', T(32977, '')),
                    ] + ([('allow_av1', T(32601, ''))] if util.KODI_VERSION_MAJOR >= 20 else [])
                ).description(T(33061, "")),
            )
        ),
        'audio': (
            T(32931, 'Audio/Subtitles'), (
                BoolSetting('audio_clamp_to_orig', T(32058, 'Never exceed original audio codec'), True).description(
                    T(32059, 'When transcoding audio, never exceed the original audio bitrate or channel '
                             'count on the same codec.')
                ),
                BoolSetting('audio_channels_kodi', T(32060, 'Use Kodi audio channels'),
                            False).description(
                    T(32061, 'When transcoding audio, target the audio channels set in Kodi.')
                ),
                OptionsSetting(
                    'audio_force_ac3_cond',
                    T(32062, 'Transcode audio to AC3'),
                    'never',
                    (
                        ('never', T(32033, 'Never')),
                        ('always', T(32028, 'Always')),
                        ('2', '>2.0'),
                        ('3', '>2.1'),
                        ('5', '>5.0'),
                        ('6', '>5.1'),
                    )
                ).description(
                    T(32063, 'Transcode audio to AC3 in certain conditions (useful for passthrough).')
                ),
                BoolSetting('audio_ac3dts', T(32064, 'Treat DTS like AC3'),
                            True).description(
                    T(32065, 'When force AC3 settings are enabled, treat DTS the same as AC3 '
                             '(useful for Optical passthrough)')
                ),
                MultiOptionsSetting(
                    'audio_disabled_codecs', T(33665, 'Disable audio codecs'),
                    [],
                    list(sorted([(a, "{} ({})".format(b, a)) for a, b in plexnet.util.AUDIO_CODECS_VERB.items()]))
                ).description(
                    T(33666, "Audio codecs you can't play back. Disables Direct Play for such media items, "
                             "enables Direct Stream if possible, transcodes audio stream to compatible format.")
                ),
                OptionsSetting(
                    'audio_transcode_codec', T(33733, 'Transcode target codec'),
                    "default",
                    [("default", T(32030, 'Auto'))] + list(sorted([(a, "{} ({})".format(b, a)) for a, b in plexnet.util.AUDIO_CODECS_TC_VERB.items()]))
                ).description(
                    T(33734, "Sets the target codec when transcoding/direct streaming. Overridden when "
                             "\"Transcode audio to AC3\" is set.")
                ),
                BoolSetting('audio_hires', T(33079, ''),
                            True).description(
                    T(33080, '')
                ),
                MultiOptionsSetting(
                    'disable_subtitle_languages', T(33691, "Native languages"),
                    [],
                    [(b, a) for a, b in sorted([(l.name, l.part2t) for l in languages if l.part1])]  # +
                    # [(b, a) for a, b in sorted([(l.name, l.part2t) for l in SEP_LANGUAGES])]
                ).description(
                    T(33692, "When you usually watch things in a different language with subtitles, but are a"
                             " native speaker of other languages, which you don't need subtitles for, prevent Plex "
                             "from auto-selecting subtitles for those languages.")
                ),
                OptionsSetting(
                    'subtitle_download_from',
                    T(33693, 'Download subtitles using'),
                    'plex',
                    (
                        ('ask', T(33694, 'Ask')),
                        ('plex', 'Plex'),
                        ('kodi', 'Kodi'),
                    )
                ).description(T(33695, "Where do you want to download subtitles from? Note: Currently this "
                                       "only applies to the subtitle quick actions in the player. The subtitle download"
                                       " in stream settings always uses Plex as a source.")),
                BoolSetting('subtitle_download_fallback', T(33701, 'Fallback to Kodi'),
                            True).description(
                    T(33702, "When no subtitles are found via the Plex subtitle search, fall back to Kodi "
                             "subtitle search. Note: Currently this only applies to the subtitle quick actions in the "
                             "player. The subtitle download in stream settings always uses Plex as a source.")
                ),
                OptionsSetting(
                    'burn_subtitles',
                    T(32031, 'Burn-in Subtitles'),
                    'auto',
                    (('auto', T(32030, 'Auto')), ('image', T(32029, 'Only Image Formats')),
                     ('always', T(32028, 'Always')))
                ),
                BoolSetting('burn_ssa', T(32944, 'Burn-in SSA subtitles'),
                            True).description(
                    T(32945, 'When Direct Streaming instruct the Plex Server to burn in SSA/ASS subtitles (thus '
                             'transcoding the video stream). If disabled it will not touch the video stream, but '
                             'will convert the subtitle to unstyled text.')
                ),
                BoolSetting('auto_sync', T(33655, 'Auto-Sync Subtitles'),
                            True).description(
                    T(33656, 'Only for External SRT subtitles. The PMS setting for voice activity detection '
                             'has to be enabled for this to work.')
                ),
                BoolSetting('forced_subtitles_override', T(32941, 'Forced subtitles fix'),
                            False).description(
                    T(32493, 'When a media file has a forced/foreign subtitle for a subtitle-enabled language, the Plex'
                             ' Media Server preselects it. This behaviour is usually not necessary and not configurable'
                             '. This setting fixes that by ignoring the PMSs decision and selecting the same language '
                             'without a forced flag if possible.')
                ),
                BoolSetting('calculate_oshash', T(32958, 'Calculate OpenSubtitles.com hash'),
                            False).description(
                    T(32959, '')
                ),
            )
        ),
        'ui': (
            T(32467, 'User Interface'), (
                OptionsSetting(
                    'theme',
                    T(32983, 'Theme'),
                    util.DEF_THEME,
                    (
                        ('modern', T(32985, 'Modern')),
                        ('modern-dotted', T(32986, 'Modern (dotted)')),
                        ('modern-colored', T(32989, 'Modern (colored)')),
                        ('classic', T(32987, 'Classic')),
                        ('custom', T(32988, 'Custom')),
                    ), theme_relevant=True
                ).description(
                    T(32984, 'stub')
                ),
                OptionsSetting(
                    'watched_indicators', T(33022, ''),
                    "modern_2024",
                    (
                        ('classic', T(32987, 'Classic')),
                        ('modern', T(32985, 'Modern')),
                        ('modern_2024', T(33076, 'Modern (2024)')),
                    ),
                    theme_relevant=True
                ).description(
                    T(33023, "")
                ),
                BoolSetting(
                    'hide_aw_bg', T(33024, ''), False, theme_relevant=True
                ).description(
                    T(33025, "")
                ),
                BoolSetting(
                    'scale_indicators', T(33077, ''), True, theme_relevant=True
                ).description(
                    T(33078, "")
                ),
                BoolUserSetting(
                    'use_watchlist', T(34007, 'Use Watchlist'), True
                ).description(
                    T(34008, "Activates the current user's Plex watchlist as a section item. Adds watchlist "
                             "functionality to certain media screens. Per-user setting. Default: On")
                ),
                BoolUserSetting(
                    'watchlist_auto_remove', T(34009, 'Watchlist auto-remove'), True
                ).description(
                    T(34010, "Automatically remove fully watched items from watchlist. Default: On")
                ),
                MultiOptionsSetting(
                    'show_ratings', T(33709, 'Show ratings for'),
                    ["series", "movies"],
                    [
                        ('series', T(32393, 'TV Shows')),
                        ('movies', T(32348, 'Movies')),
                    ]
                ),
                MultiOptionsSetting(
                    'show_reviews1', T(33710, 'Show reviews for'),
                    ["watched", "unwatched"],
                    [
                        ('watched', T(33718, 'Watched')),
                        ('unwatched', T(33010, 'Unwatched')),
                    ]
                ),
                MultiOptionsSetting(
                    'no_episode_spoilers4', T(33006, ''),
                    ['unwatched', 'blur_images', 'hide_summary'],
                    (
                        ('unwatched', T(33010, '')),
                        ('in_progress', T(33011, '')),
                        ('no_unwatched_episode_titles', T(33012, '')),
                        ('blur_images', T(33706, '')),
                        ('blur_resume_images', T(33707, '')),
                        ('blur_chapters', T(33081, '')),
                        ('hide_summary', T(33708, '')),
                        ('hide_ratings', T(33705, '')),
                    )
                ).description(T(33007, "")),
                MultiOptionsSetting(
                    'spoilers_allowed_genres2', T(33016, ''),
                    ["Reality", "Game Show", "Documentary", "Sport"],
                    [(g, g) for g in genres.GENRES_TV]
                ).description(T(33017, "")),
                BoolSetting(
                    'hubs_use_new_continue_watching', T(32998, ''), False
                ).description(
                    T(32999, "")
                ),
                BoolSetting(
                    'home_confirm_actions', T(33663, 'Home: Confirm item actions'), True
                ).description(
                    T(33664, "When acting on items in the Home view, such as mark played, hide from continue "
                             "watching etc., show a confirmation dialog.")
                ),
                BoolSetting(
                    'hub_season_thumbnails', T(33740, 'Home: Episodes season thumbnails'), True
                ).description(
                    T(33741, "Use season thumbnails/posters when displaying episodes in hubs instead of "
                             "the TV show's.")
                ),
                BoolSetting(
                    'hubs_round_robin', T(33043, ''), False
                ).description(
                    T(33044, "").format(util.addonSettings.hubsRrMax)
                ),
                BoolSetting(
                    'hubs_bifurcation_lines', T(32961, 'Show hub bifurcation lines'), False
                ).description(
                    T(32962, "Visually separate hubs horizontally using a thin line.")
                ),
                BoolSetting(
                    'path_mapping_indicators', T(33032, 'Show path mapping indicators'), True
                ).description(
                    T(33033, "When path mapping is active for a library, display an indicator.")
                ),
                KeySetting('map_button_home', T(33085), None).description(T(33087))
            )
        ),
        'player': (
            T(32940, 'Player UI'), (
                BoolSetting('player_official', T(33045, 'Behave like official Plex clients'), True).description(
                    T(33046, '')),
                BoolSetting('no_osd_time_spoilers', T(33004, ''), False, backport_from="no_spoilers").description(
                    T(33005, '')),
                MultiUAOptionsSetting(
                    'player_show_buttons', T(33057, 'Show buttons'),
                    ['subtitle_downloads', 'skip_intro', 'skip_credits'],
                    (
                        ('subtitle_downloads', T(32932, 'Show subtitle quick-actions button')),
                        ('video_show_ffwdrwd', T(32933, 'Show FFWD/RWD buttons')),
                        ('video_show_repeat', T(32934, 'Show repeat button')),
                        ('video_show_shuffle', T(32935, 'Show shuffle button')),
                        ('skip_intro', T(32495, 'Skip Intro')),
                        ('skip_credits', T(32496, 'Skip Credits')),
                    )
                ).description(T(32939, 'Only applies to video player UI')),
                MultiUAOptionsSetting(
                    'fast_pause_resume', T(34012, 'Fast pause/resume'),
                    [],
                    (
                        ('paused', T(34013, 'when paused')),
                        ('playing', T(34014, 'when playing')),
                    )
                ).description(T(34015, 'User-specific. Use OK/ENTER button to pause instead of showing the OSD'
                                       ' (which can then only be accessed using DOWN), or resume when paused. '
                                       'Only works with \'Behave like official Plex clients\' enabled.')),
                OptionsSetting(
                    'video_show_playlist', T(32936, 'Show playlist button'), 'eponly',
                    (
                        ('always', T(32035, 'Always')), ('eponly', T(32938, 'Only for Episodes/Playlists')),
                        ('never', T(32033, 'Never'))
                    )
                ).description(T(33088, 'Only applies to video player UI')),
                OptionsSetting(
                    'video_show_prevnext', T(32937, 'Show prev/next button'), 'eponly',
                    (
                        ('always', T(32035, 'Always')), ('eponly', T(32938, 'Only for Episodes/Playlists')),
                        ('never', T(32033, 'Never'))
                    )
                ).description(T(33088, 'Only applies to video player UI')),
                OptionsSetting(
                    'resume_seek_behind', T(33089, ''), 0,
                    [(0, T(32481))] + [
                        (a, T(33091).format(sec_or_ms=a if a < 1000 else int(a / 1000),
                                            unit_s_or_ms="ms" if a < 1000 else "s")) for a in
                        [100] + list(range(250, 1000, 250)) + list(range(1000, 61000, 1000))]
                ).description(T(33090, '')),
                BoolSetting('resume_seek_behind_pause', T(33092, ''), False).description(
                    T(33095, '')),
                OptionsSetting(
                    'resume_seek_behind_after', T(33093, ''), 0,
                    [(0, T(32481))] + [
                        (a, T(33091).format(sec_or_ms=a if a < 1000 else int(a / 1000),
                                            unit_s_or_ms="ms" if a < 1000 else "s")) for a in
                        list(range(250, 1000, 250)) + list(range(1000, 61000, 1000))]
                ).description(T(33094, '')),
                BoolSetting('resume_seek_behind_onlydp', T(33096, ''), True).description(
                    T(33097, '')),
                OptionsSetting(
                    'player_stop_on_idle',
                    T(32946, 'Stop video playback on idle after'),
                    0,
                    ((0, T(32033, 'Never')), (30, '30s'), (60, '1m'), (120, '2m'), (300, '5m'), (600, '10m'),
                     (900, '15m'), (1200, '20m'), (1800, '30m'), (2700, '45m'), (3600, '1h'),)
                ),
                BoolSetting(
                    'player_stop_on_screensaver', T(32947, 'Stop video playback on screensaver'), False
                ),
            )
        ),
        'player_user': (
            T(32631, 'Playback (user-specific)'), (
                BoolUserSetting(
                    'show_chapters', T(33601, 'Show video chapters'), True
                ).description(
                    T(33602, 'If available, show video chapters from the video-file instead of the '
                             'timeline-big-seek-steps.')
                ),
                BoolUserSetting(
                    'virtual_chapters', T(33603, 'Use virtual chapters'), True
                ).description(
                    T(33604, 'When the above is enabled and no video chapters are available, simulate them by using the'
                             ' markers identified by the Plex Server (Intro, Credits).')
                ),
                BoolUserSetting(
                    'auto_skip_in_transcode', T(32948, 'Allow auto-skip when transcoding'), True
                ).description(
                    T(32949, 'When transcoding/DirectStreaming, allow auto-skip functionality.')
                ),
                BoolUserSetting(
                    'post_play_auto', T(32039, 'Post Play Auto Play'), True
                ).description(
                    T(
                        32101,
                        "If enabled, when playback ends and there is a 'Next Up' item available, it will be automatical"
                        "ly be played after a {} second delay."
                    ).format(util.addonSettings.postplayTimeout)
                ),
                BoolUserSetting(
                    'post_play_never', T(33652, 'Never show Post Play'), False
                ),
                BoolUserSetting(
                    'binge_mode', T(33618, 'TV binge-viewing mode'), False
                ).description(
                    T(33619, 'Automatically skips episode intros, credits and tries to skip episode recaps. Doesn\'t '
                             'skip the intro of the first episode of a season and doesn\'t skip the final credits of a '
                             'show.\n\nCan be disabled/enabled per TV show.'
                             '\n\nOverrides any playback setting below.')
                ),
                BoolUserSetting(
                    'auto_skip_intro', T(32522, 'Automatically Skip Intro'), False
                ).description(
                    T(32523, 'Automatically skip intros if available. Doesn\'t override enabled binge mode.\nCan be disabled/enabled per TV show.')
                ),
                BoolUserSetting(
                    'auto_skip_credits', T(32526, 'Auto Skip Credits'), False
                ).description(
                    T(32527, 'Automatically skip credits if available. Doesn\'t override enabled binge mode.\nCan be disabled/enabled per TV show.')
                ),
                BoolUserSetting(
                    'show_intro_skip_early', T(33505, 'Show intro skip button early'), False
                ).description(
                    T(33506, 'Show the intro skip button from the start of a video with an intro marker. The auto-skipp'
                             'ing setting applies. Doesn\'t override enabled binge mode.\nCan be disabled/enabled per TV show.')
                ),
                BoolUserSetting(
                    'skip_post_play_tv', T(32973, 'Episodes: Skip Post Play screen'), False
                ).description(
                    T(32974, 'When finishing an episode, don\'t show Post Play but go to the next one immediately.'
                             '\nCan be disabled/enabled per TV show. Doesn\'t override enabled binge mode. '
                             'Overrides the Post Play setting.')
                ),
            )
        ),
        'network': (
            T(33624, 'Network'), (
                OptionsSetting(
                    'allow_insecure', T(32032), 'never',
                    (('never', T(32033)), ('same_network', T(32034)), ('always', T(32035)))
                ).description(
                    T(32104, 'When to connect to servers with no secure connections...')
                ),
                BoolSetting('smart_discover_local', T(33625, 'Smart LAN/local server discovery'), True)
                    .description(
                    T(33626, "Checks whether servers returned from Plex.tv are actually local/in your LAN. "
                             "For specific setups (e.g. Docker) Plex.tv might not properly detect a local "
                             "server.\n\nNOTE: Only works on Kodi 19 or above."
                      )
                ),
                BoolSetting('prefer_local', T(33627, 'Prefer LAN/local servers over security'), False)
                    .description(
                    T(33628, "Prioritizes local connections over secure ones. Needs the proper setting in \"Allow "
                             "Insecure Connections\" and the Plex Server's \"Secure connections\" at \"Preferred\". "
                             "Can be used to enforce manual servers."
                      )
                ),
                BoolSetting('gdm_discovery', T(32042, 'Server Discovery (GDM)'), False),
                OptionsSetting(
                    'handle_plexdirect', T(32990), 'ask',
                    (('ask', T(32991)), ('always', T(32035)), ('never', T(32033)))
                ).description(
                    T(32992, 'stub')
                ),
                IPSetting('manual_ip_0', T(32044, 'Connection 1 IP'), ''),
                IntegerSetting('manual_port_0', T(32045, 'Connection 1 Port'), 32400),
                IPSetting('manual_ip_1', T(32046, 'Connection 2 IP'), ''),
                IntegerSetting('manual_port_1', T(32047, 'Connection 2 Port'), 32400),
            )
        ),
        'system': (
            T(33600, 'System'), (
                BoolSetting('auto_update_check', T(33672, 'Check for updates'), True)
                .description(T(33673, "Automatically check for updates periodically. If installed from a "
                                      "Kodi repository and the Update Source setting is set to Repository, Kodi "
                                      "itself will handle the updating of this addon. "
                                      "Needs a Kodi restart when changed.")) if not util.FROM_KODI_REPOSITORY else None,
                BoolSetting('update_check_startup', T(33674, 'Check for updates on start'), True)
                .description(T(33675, "Automatically check for updates on startup. "
                                      "Doesn't do much when Update source is Repository."
                                      "Needs a Kodi restart when changed.")) if not util.FROM_KODI_REPOSITORY else None,
                OptionsSetting(
                    'update_source',
                    T(33676, 'Update source'),
                    'repository',
                    (('beta', T(33678, 'Beta')), ('stable', T(33679, 'Stable')),
                     ('repository', T(33680, 'Repository')))
                ).description(T(33677, 'Specifies the update mode. Will immediately check for a new version '
                                       'when changed and closing settings.\nDefault: Repository\n\nBeta: Bleeding '
                                       'edge (possibly unstable)\nStable: Stable branch (faster than Repository)\n'
                                       'Repository: Kodi repository (official (slow) or Don\'t Panic)')
                              ) if not util.FROM_KODI_REPOSITORY else None,
                MultiOptionsSetting(
                    'cache_requests', T(33724, 'Cache Plex data for'),
                    [],
                    [
                        ('items', T(33723, 'Media Items')),
                        ('libraries', T(33722, 'Libraries')),
                    ]
                ).description(T(33727, "Store Plex server responses for items and library views in a local "
                                       "SQLite database. Doesn't cache anything else (Home/Hubs are always up to date)."
                                       " Massively speeds up consecutive visits to items and libraries. Certain "
                                       "important events, such as watch state changes, automatically delete the item "
                                       "cache and its corresponding library cache. The complete cache gets cleared "
                                       "when exiting the addon. (Default: Off)")),
                BoolSetting('persist_requests_cache', T(33725, 'Persist cached Plex data'), False)
                .description(T(33726, "Instead of clearing the cache when exiting the addon, persist it "
                                      "instead. Warning: You'll most likely encounter missing items in libraries "
                                      "or outdated data. Use the corresponding menu functionalities to clear the "
                                      "cache for specific items or libraries.")),
                BoolSetting('exit_default_is_quit', T(32965, 'Start Plex On Kodi Startup'), False)
                .description(T(32966, "stub")),
                BoolSetting('path_mapping', T(33000, ''), True).description(T(33001, '')),
                BufferSetting('cache_size',
                              T(33613, 'Kodi Buffer Size (MB)'),
                              20,
                              [(mem, '{} MB'.format(mem)) for mem in lib.cache.kcm.viableOptions])
                .description(
                    '{}{}'.format(T(33614, 'stub1').format(
                        lib.cache.kcm.free, lib.cache.kcm.recMax),
                        '' if lib.cache.kcm.useModernAPI else ' ' + T(32954, 'stub2'))
                ) if not util.FROM_KODI_REPOSITORY or lib.cache.kcm.useModernAPI else None,
                ReadFactorSetting('readfactor',
                                  T(32922, 'Kodi Cache Readfactor'),
                                  4,
                                  [(rf, str(rf) if rf > 0 else T(32976, 'stub')) for rf in lib.cache.kcm.readFactorOpts])
                .description(
                    T(32923, 'Sets the Kodi cache readfactor value. Default: {0}, recommended: {1}.'
                             'With "Slow connection" enabled this will be set to {2}, as otherwise the cache doesn\'t'
                             'fill fast/aggressively enough.').format(lib.cache.kcm.defRF,
                                                                      lib.cache.kcm.recRFRange,
                                                                      lib.cache.kcm.defRFSM)
                ) if not util.FROM_KODI_REPOSITORY or lib.cache.kcm.useModernAPI else None,
                BoolSetting(
                    'slow_connection', T(32915, 'Slow connection'), False
                ).description(T(32916, "Use with a wonky/slow connection, "
                                       "e.g. in a hotel room. Adjusts the UI to visually "
                                       "wait for item refreshes and waits for the buffer to fill when starting "
                                       "playback.")),
                OptionsSetting(
                    'action_on_sleep',
                    T(32700, 'Action on Sleep event'),
                    'none',
                    (('none', T(32702, 'Nothing')), ('stop', T(32703, 'Stop playback')),
                     ('quit', T(32704, 'Quit Kodi')), ('reboot', T(32426, 'Reboot')),
                     ('shutdown', T(32423, 'Shutdown')),
                     ('hibernate', T(32425, 'Hibernate')), ('suspend', T(32424, 'Suspend')),
                     ('cecstandby', T(32705, 'CEC Standby')), ('logoff', T(32421, 'Sign Out')))
                ).description(T(32701, 'When Kodi receives a sleep event from the system, run the following action.')),
                OptionsSetting(
                    'action_on_wake',
                    T(33070, 'Action on Wake event'),
                    util.altSeekRecommended and 'wait_5' or 'wait_1',
                    [('none', T(32702, 'Nothing')), ('restart', T(33071, 'Restart PM4K'))]
                    + [('wait_{}'.format(s), T(33072, '').format(s)) for s in [1, 2, 3] + list(range(5, 65, 5))]
                ).description(T(33075, '')),
                BoolSetting('debug', T(32024, 'Debug Logging'), False),
                BoolSetting('dump_config', T(33642, 'Debug Logging'), False).description(T(33643)),
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
                InfoSetting('screen_res', T(32056, 'Screen Resolution'),
                            xbmc.getInfoLabel('System.ScreenResolution').split('-')[0].strip()),
                ServerVersionSetting('server_version', T(32057, 'Current Server Version'), None),
                InfoSetting('addon_path', T(33616, 'Addon Path'), util.ADDON.getAddonInfo("path")),
                InfoSetting('userdata_path', T(33617, 'Userdata/Profile Path'),
                            util.translatePath("special://profile")),
                InfoSetting('service_status', T(33689, 'Service running'),
                            lambda: "{} ({})".format(
                                util.getGlobalProperty("service.started") and T(32328, "Yes") or T(32329, "No"),
                                util.getGlobalProperty("service.version"))),
                InfoSetting('i_last_update_check', T(33690, "Last update check"),
                            lambda: util.getGlobalProperty('last_update_check', datetime.datetime.fromtimestamp(0).strftime('%Y-%m-%dT%H:%M:%S.%f'))),
            )
        ),
    }

    SECTION_IDS = ('main', 'video', 'audio', 'ui', 'player', 'player_user', 'network', 'system', 'about')

    def __getitem__(self, key):
        return self.SETTINGS[key]


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
        self.lastFocusID = None
        self.checkSection()

    def onAction(self, action):
        try:
            self.checkSection()
            controlID = self.getFocusId()
            if action in (xbmcgui.ACTION_STOP, xbmcgui.ACTION_CONTEXT_MENU):
                self.editSetting(clear=True)
                return
            elif action in (xbmcgui.ACTION_NAV_BACK, xbmcgui.ACTION_PREVIOUS_MENU):
                if controlID == self.OPTIONS_LIST_ID:
                    self.setFocusId(self.SETTINGS_LIST_ID)
                    return
                elif controlID == self.SETTINGS_LIST_ID:
                    self.setFocusId(self.SECTION_LIST_ID)
                    return
                # elif not xbmc.getCondVisibility('ControlGroup({0}).HasFocus(0)'.format(self.TOP_GROUP_ID)):
                #     self.setFocusId(self.TOP_GROUP_ID)
                #     return
            elif action == xbmcgui.ACTION_MOVE_RIGHT:
                if self.lastFocusID == self.SECTION_LIST_ID:
                    if self.lastSection != 'about':
                        self.setFocusId(self.SETTINGS_LIST_ID)
                    return
                elif self.lastFocusID == self.SETTINGS_LIST_ID:
                    self.editSetting(from_right=True)
                    return
        except:
            util.ERROR()

        kodigui.BaseWindow.onAction(self, action)

    def onClick(self, controlID):
        if controlID == self.SECTION_LIST_ID:
            if self.lastSection != 'about':
                self.setFocusId(self.SETTINGS_LIST_ID)
        elif controlID == self.SETTINGS_LIST_ID:
            self.editSetting()
        elif controlID == self.OPTIONS_LIST_ID:
            self.changeSetting()
        elif controlID == self.CLOSE_BUTTON_ID:
            self.doClose()
        elif controlID == self.PLAYER_STATUS_BUTTON_ID:
            self.showAudioPlayer()

    def onFocus(self, controlID):
        self.lastFocusID = controlID

    def checkSection(self):
        mli = self.sectionList.getSelectedItem()
        if not mli:
            return

        if mli.dataSource == self.lastSection:
            return

        self.lastSection = mli.dataSource
        self.showSettings(self.lastSection)
        self.setProperty('section.about', self.lastSection == 'about' and '1' or '')
        util.DEBUG_LOG('Settings: Changed section ({0})', self.lastSection)

    def showSections(self):
        items = []
        for sectionID in self.settings.SECTION_IDS:
            label = self.settings[sectionID][0]
            item = kodigui.ManagedListItem(label, data_source=sectionID)
            items.append(item)
        items[-1].setProperty('is.last', '1')

        self.sectionList.addItems(items)

    def showSettings(self, section):
        settings = self.settings[section][1]
        if not settings:
            return self.settingsList.reset()

        items = []
        for setting in settings:
            if setting is None or not setting.should_show():
                continue

            item = kodigui.ManagedListItem(setting.label, setting.type != 'BOOL' and setting.valueLabel() or '',
                                           data_source=setting)
            item.setProperty('description', setting.desc)
            if setting.type == 'BOOL':
                item.setProperty('checkbox', '1')
                item.setProperty('checkbox.checked', setting.get() and '1' or '')
            elif setting.type == 'BUTTON':
                item.setProperty('button', '1')

            if setting.userAware:
                item.setProperty('useraware', '1')

            items.append(item)

        self.settingsList.reset()
        self.settingsList.addItems(items)

    def editSetting(self, from_right=False, clear=False):
        mli = self.settingsList.getSelectedItem()
        if not mli:
            return

        setting = mli.dataSource

        if clear and setting.type != 'STRING':
            return

        if setting.type in ('LIST', 'OPTIONS', 'MULTI'):
            self.fillList(setting)
        elif setting.type == 'BOOL' and not from_right:
            self.toggleBool(mli, setting)
        elif setting.type == 'IP' and not from_right:
            self.editIP(mli, setting)
        elif setting.type == 'INTEGER' and not from_right:
            self.editInteger(mli, setting)
        elif setting.type == 'STRING' and not from_right:
            self.editString(mli, setting, clear=clear)
        elif setting.type == 'BUTTON':
            self.buttonDialog(mli, setting)

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
        elif setting.type == 'MULTI':
            values = setting.get()
            if optionItem.dataSource in values:
                values.remove(optionItem.dataSource)
                optionItem.setProperty('checkbox.checked', '')
            else:
                values.append(optionItem.dataSource)
                optionItem.setProperty('checkbox.checked', '1')
            setting.set(values)
            mli.setLabel2(setting.valueLabel(values=values))

        if setting.type != 'MULTI':
            self.setFocusId(self.SETTINGS_LIST_ID)

    def fillList(self, setting):
        mli = self.settingsList.getSelectedItem()
        if not mli:
            return

        items = []
        if setting.type == 'LIST':
            for label in setting.optionLabels():
                items.append(kodigui.ManagedListItem(label))
        elif setting.type in ('OPTIONS', 'MULTI'):
            for ID, label in setting.options:
                items.append(kodigui.ManagedListItem(label, data_source=ID))

        self.optionsList.reset()
        self.optionsList.addItems(items)
        idx = setting.optionIndex()
        if isinstance(idx, int):
            idx = [idx]
        for _idx in idx:
            if setting.type == 'MULTI':
                self.optionsList[_idx].setProperty('checkbox.checked', '1')
        if idx:
            self.optionsList.selectItem(idx[-1])
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

    def editString(self, mli, setting, clear=False):
        if clear:
            setting.set(None)
            mli.setLabel2(T(32447, "None"))
            return
        if hasattr(setting, "value_setter"):
            result = setting.value_setter()
            if result is not None:
                setting.set(result.code)
                mli.setLabel2(str(result))
            return
        else:
            result = xbmcgui.Dialog().input(T(32417, 'Enter Port Number'), str(setting.get()), xbmcgui.INPUT_STRING)
        if result is None:
            return
        elif result == -1:
            setting.set(None)
            return

        setting.set(result)
        mli.setLabel2(str(result))


class SchnorchelDialog(xbmcgui.WindowXMLDialog):
    """
    inspired by https://github.com/pkscout/script.keymap/blob/main/editor.py
    """

    def __new__(cls, *args, **kwargs):
        gui_api = tuple(map(int, xbmcaddon.Addon('xbmc.gui').getAddonInfo('version').split('.')))
        file_name = "DialogNotification.xml" if gui_api >= (5, 11, 0) else "DialogKaiToast.xml"
        return super(SchnorchelDialog, cls).__new__(cls, file_name, "")

    def __init__(self, timeout=10):
        self.key = None
        self.timeout = timeout
        self._winID = None

        self.setProperty("no.image", "1")

    def onInit(self):
        ctrl1, ctrl2 = 401, 402
        if util.SKIN_PLEXTUARY:
            ctrl1, ctrl2 = 1401, 1402
        try:
            self.getControl(ctrl1).addLabel(T(33085))
            self.getControl(ctrl2).addLabel(T(33086).format(self.timeout))
        except AttributeError:
            self.getControl(ctrl1).setLabel(T(33085))
            self.getControl(ctrl2).setLabel(T(33086).format(self.timeout))

    def setProperty(self, key, value):
        if not self._winID:
            self._winID = xbmcgui.getCurrentWindowId()

        try:
            xbmcgui.Window(self._winID).setProperty(key, value)
            xbmcgui.WindowXML.setProperty(self, key, value)
        except RuntimeError:
            xbmc.log('kodigui.BaseWindow.setProperty: Missing window', xbmc.LOGDEBUG)

    def onAction(self, action):
        code = action.getButtonCode()
        action_id = action.getId()
        self.key = None
        if action_id not in (xbmcgui.ACTION_SELECT_ITEM, xbmcgui.ACTION_NAV_BACK, xbmcgui.ACTION_PREVIOUS_MENU):
            self.key = None if code == 0 else actions.ActionKey(code)
        elif action_id in (xbmcgui.ACTION_NAV_BACK, xbmcgui.ACTION_PREVIOUS_MENU):
            self.key = None
        else:
            self.key = -1
        self.close()
        return


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
    options = [(16 - i, T(l)) for (i, l) in enumerate((32001, 32017, 32002, 32016, 32003, 32004, 32005, 32015, 32006,
                                                       32007, 32008, 32009, 32010, 32011))]

    choice = showOptionsDialog(T(32397, 'Quality'), options)
    if choice is None:
        return

    video.settings.setPrefOverride('local_quality2', choice)
    video.settings.setPrefOverride('remote_quality2', choice)
    video.settings.setPrefOverride('online_quality2', choice)


def openWindow():
    w = SettingsWindow.open()
    del w
