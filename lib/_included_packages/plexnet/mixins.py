# coding=utf-8

EAC3JOC_CONST = 7594878993
EAC3JOC_STR = ("".join(list(chr(int(a)-10) for a in [str(EAC3JOC_CONST)[i:i + 2]
                                                     for i in range(0, len(str(EAC3JOC_CONST)), 2)]))).lower()


class AudioCodecMixin(object):
    """
    Imperfect implementation to properly display JOC and DTS variants.
    Plex Analyzer doesn't store JOC flags and XLL, so we're only guessing here.

    This mixin can be used in a MediaItem as well as a PlexStream-like object
    """

    def translateAudioCodec(self, codec=None):
        mc = getattr(self, "mediaChoice")
        streamBase = mc.audioStream if mc else self
        if not any([codec, hasattr(streamBase, "codec")]):
            return ''

        codec = (codec or (streamBase.codec or '')).lower()
        title = streamBase.title.lower()
        fn = ((mc and mc.part.file) or (self.part and getattr(self.part, "file")) or '').lower()

        if codec == "dca-ma" or (codec == "dca" and streamBase.profile == "ma"):
            codec = "DTS-HD MA"
            if "dts-x" in title or "dts:x" in title or "dtsx" in title:
                codec = "DTS:X"
        elif codec == "dts-hd" or (codec == "dca" and streamBase.profile == "hd"):
            codec = "DTS-HD"
        elif codec == "dts-es" or (codec == "dca" and streamBase.profile == "es"):
            codec = "DTS-ES"
        elif codec == "dts-hra" or (codec == "dca" and streamBase.profile == "hra"):
            codec = "DTS-HRA"
        elif codec == 'dca':
            codec = "DTS"
        elif codec == "truehd":
            codec = "TrueHD"
            if EAC3JOC_STR in title:
                codec = "TrueHD {}".format(EAC3JOC_STR.capitalize())
            elif EAC3JOC_STR in fn:
                codec = "TrueHD {}?".format(EAC3JOC_STR.capitalize())
            return codec
        elif codec == "eac3":
            definitely_ertmers = (streamBase and streamBase.bitrate.asInt() >= 768) or EAC3JOC_STR in title
            possible_ertmers = False
            if not definitely_ertmers:
                possible_ertmers = EAC3JOC_STR in fn or streamBase.bitrate.asInt() >= 640

            if definitely_ertmers or possible_ertmers:
                codec = "DD+ {}".format(EAC3JOC_STR.capitalize() + (possible_ertmers and "?" or ""))
                return codec

        return codec.upper()
