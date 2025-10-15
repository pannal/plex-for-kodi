# encoding: utf-8
from __future__ import absolute_import
from . import plexobjects
from . import util
from .mixins import AudioCodecMixin
from six import ensure_str


class PlexStream(plexobjects.PlexObject, AudioCodecMixin):
    # Constants
    TYPE_UNKNOWN = 0
    TYPE_VIDEO = 1
    TYPE_AUDIO = 2
    TYPE_SUBTITLE = 3
    TYPE_LYRICS = 4

    should_auto_sync = False

    streamTypeNames = (
        "Unknown", "VideoStream", "AudioStream", "SubtitleStream", "LyricsStream"
    )

    # We have limited font support, so make a very modest effort at using
    # English names for common unsupported languages.

    SAFE_LANGUAGE_NAMES = {
        'ara': "Arabic",
        'arm': "Armenian",
        'bel': "Belarusian",
        'ben': "Bengali",
        'bul': "Bulgarian",
        'chi': "Chinese",
        'cze': "Czech",
        'gre': "Greek",
        'heb': "Hebrew",
        'hin': "Hindi",
        'jpn': "Japanese",
        'kor': "Korean",
        'rus': "Russian",
        'srp': "Serbian",
        'tha': "Thai",
        'ukr': "Ukrainian",
        'yid': "Yiddish"
    }

    def __init__(self, data, initpath=None, server=None, container=None, part=None):
        super(PlexStream, self).__init__(data, initpath, server, container)
        self.part = part

    def reload(self):
        pass

    def getTitle(self, translate_func=util.dummyTranslate):
        streamType = self.streamType.asInt()

        if streamType == self.TYPE_SUBTITLE \
                and util.INTERFACE.getPreference('subtitle_use_extended_title', True) \
                and self.extendedDisplayTitle:
            return self.extendedDisplayTitle

        title = self.getLanguageName(translate_func)

        if streamType == self.TYPE_VIDEO:
            title = self.getCodec() or translate_func("Unknown")
        elif streamType == self.TYPE_AUDIO:
            codec = self.translateAudioCodec((self.codec or '').lower())
            channels = self.getChannels(translate_func)

            if codec != "" and channels != "":
                title += u" ({0} {1})".format(codec, channels)
            elif codec != "" or channels != "":
                title += u" ({0}{1})".format(codec, channels)
        elif streamType == self.TYPE_SUBTITLE:
            extras = []

            codec = self.getCodec()
            if codec:
                extras.append(codec)

            if self.sdh:
                title += " {}".format(translate_func("SDH"))

            if not self.key:
                extras.append(translate_func("Embedded"))

            if self.forced.asBool():
                extras.append(translate_func("Forced"))

            if len(extras) > 0:
                title += u" ({0})".format('/'.join(extras))
        elif streamType == self.TYPE_LYRICS:
            title = translate_func("Lyrics")
            if self.format:
                title += u" ({0})".format(self.format)

        return title

    def getCodec(self):
        return (self.codec or '').upper()

    def getChannels(self, translate_func=util.dummyTranslate):
        channels = self.channels.asInt()

        if channels == 1:
            return translate_func("Mono")
        elif channels == 2:
            return translate_func("Stereo")
        elif channels > 0:
            return "{0}.1".format(channels - 1)
        else:
            return ""

    def getLanguageName(self, translate_func=util.dummyTranslate):
        code = self.languageCode

        if not code:
            return translate_func("Unknown")

        return self.SAFE_LANGUAGE_NAMES.get(code) or self.language or "Unknown"

    def getSubtitlePath(self, auto_sync=None):
        query = "?encoding=utf-8"

        if self.codec == "smi":
            query += "&format=srt"

        if self.should_auto_sync and auto_sync in (True, None):
            query += "&autoAdjustSubtitle=1"

        return self.key + query

    def getSubtitleServerPath(self, auto_sync=None):
        if not self.key:
            return None

        return self.getServer().buildUrl(self.getSubtitlePath(auto_sync=auto_sync), True)

    @property
    def embedded(self):
        return not bool(self.getSubtitleServerPath())

    def isSelected(self):
        return self.selected.asBool()

    def setSelected(self, selected):
        self.selected = plexobjects.PlexValue(selected and '1' or '0')

    @property
    def sdh(self):
        return self.hearingImpaired or "SDH" in self.title or "SDH" in self.displayTitle \
               or "SDH" in self.extendedDisplayTitle

    @property
    def videoCodecRendering(self):
        render = "sdr"

        if self.DOVIProfile == "8" and self.DOVIBLCompatID == "1":
            render = "dv p8.1/hdr"
        elif self.DOVIProfile == "8" and self.DOVIBLCompatID == "2":
            render = "dv p8.2/sdr"
        elif self.DOVIProfile == "8" and self.DOVIBLCompatID == "4":
            render = "dv p8.4/hlg"
        elif self.DOVIProfile == "7":
            render = "dv p7/hdr"
        elif self.DOVIProfile == "5":
            render = "dv p5"
        elif self.DOVIProfile:
            render = "dv p{}".format(self.DOVIProfile)
        elif self.colorTrc == "smpte2084":
            render = "hdr"
        elif self.colorTrc == "arib-std-b67":
            render = "hlg"

        return render.upper()

    def __str__(self):
        return ensure_str(self.getTitle())

    def __repr__(self):
        return '<{}: {}>'.format(self.streamTypeNames[self.streamType.asInt()], str(self))

    def __eq__(self, other):
        if not other:
            return False

        if self.__class__ != other.__class__:
            return False

        for attr in ("streamType", "language", "codec", "channels", "index", "key"):
            if getattr(self, attr) != getattr(other, attr):
                return False
        return True


# Synthetic subtitle stream for 'none'

class NoneStream(PlexStream):
    def __init__(self, *args, **kwargs):
        PlexStream.__init__(self, None, *args, **kwargs)
        self.id = plexobjects.PlexValue("0")
        self.streamType = plexobjects.PlexValue(str(self.TYPE_SUBTITLE))

    def getTitle(self, translate_func=util.dummyTranslate):
        return translate_func("None")


NONE_STREAM = NoneStream()
