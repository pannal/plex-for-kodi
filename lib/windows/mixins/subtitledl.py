# coding=utf-8
from six import ensure_str

import lib.windows.dialog
from lib import util
from lib.i18n import T
from lib.windows import busy, kodigui
from lib.windows.dialog import showOptionsDialog
from plexnet import util as pnUtil

PLEX_LEGACY_LANGUAGE_MAP = {
    "pb": ("pt", "pt-BR"),
}


class PlexSubtitleDownloadMixin(object):
    def __init__(self, *args, **kwargs):
        super(PlexSubtitleDownloadMixin, self).__init__()

    @staticmethod
    def get_subtitle_language_tuple():
        from iso639 import languages
        lang_code_parse, lang_code = PLEX_LEGACY_LANGUAGE_MAP.get(pnUtil.ACCOUNT.subtitlesLanguage,
                                                                  (pnUtil.ACCOUNT.subtitlesLanguage,
                                                                   pnUtil.ACCOUNT.subtitlesLanguage))
        language = languages.get(part1=lang_code_parse)
        return language, lang_code_parse, lang_code


    def downloadPlexSubtitles(self, video, non_playback=False):
        """

        @param video:
        @return: False if user backed out, None if no subtitles found, or the downloaded subtitle stream
        """
        language, lang_code_parse, lang_code = PlexSubtitleDownloadMixin.get_subtitle_language_tuple()


        util.DEBUG_LOG("Using language {} for subtitle search", ensure_str(str(language.name)))

        subs = None
        with busy.BusyBlockingContext(delay=True):
            subs = video.findSubtitles(language=lang_code,
                                       hearing_impaired=pnUtil.ACCOUNT.subtitlesSDH,
                                       forced=pnUtil.ACCOUNT.subtitlesForced)

        if subs:
            with kodigui.WindowProperty(self, 'settings.visible', '1'):
                options = []
                sk_to_k = {}
                for sub in sorted(subs, key=lambda s: s.score.asInt(), reverse=True):
                    info = ""
                    if sub.hearingImpaired.asInt() or sub.forced.asInt():
                        add = []
                        if sub.hearingImpaired.asInt():
                            add.append(T(33698, "HI"))
                        if sub.forced.asInt():
                            add.append(T(33699, "forced"))
                        info = " ({})".format(", ".join(add))
                    sk_to_k[sub.sourceKey] = sub.key
                    options.append((sub.sourceKey, (T(33697, "{provider_title}, Score: {subtitle_score}{subtitle_info}").format(
                        provider_title=sub.providerTitle,
                        subtitle_score=sub.score,
                        subtitle_info=info), sub.title)))
                choice = showOptionsDialog(T(33700, "Download subtitles: {}").format(ensure_str(language.name)),
                                                              options, trim=False, non_playback=non_playback)
                if choice is None:
                    return False

                with busy.BusyBlockingContext(delay=True):
                    video.downloadSubtitles(sk_to_k[choice])
                    tries = 0
                    sub_downloaded = False
                    util.DEBUG_LOG("Waiting for subtitle download: {}", choice)
                    while tries < 20:
                        for stream in video.findSubtitles(language=lang_code,
                                                          hearing_impaired=pnUtil.ACCOUNT.subtitlesSDH,
                                                          forced=pnUtil.ACCOUNT.subtitlesForced):
                            if stream.downloaded.asBool() and stream.sourceKey == choice:
                                util.DEBUG_LOG("Subtitle downloaded: {}", stream.extendedDisplayTitle)
                                sub_downloaded = stream
                                break
                        if sub_downloaded:
                            break
                        tries += 1
                        util.MONITOR.waitForAbort(0.25)
                    # stream will be auto selected
                    video.clearCache()
                    video.reload(includeExternalMedia=1, includeChapters=1, skipRefresh=1)
                    # reselect fresh media
                    media = [m for m in video.media() if m.ratingKey == video.mediaChoice.media.ratingKey][0]
                    video.setMediaChoice(media=media, partIndex=video.mediaChoice.partIndex)
                    # double reload is probably not necessary
                    video.reload(fromMediaChoice=True, forceSubtitlesFromPlex=stream, skipRefresh=1)
                    for stream in video.subtitleStreams:
                        if stream.selected.asBool():
                            util.DEBUG_LOG("Selecting subtitle: {}", stream.extendedDisplayTitle)
                            return stream
        else:
            util.showNotification(util.T(33696, "No Subtitles found."),
                                  time_ms=1500, header=util.T(32396, "Subtitles"))

