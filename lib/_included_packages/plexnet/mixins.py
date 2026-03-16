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

    MIN_JOC_BITRATE = 736 # should be 768, but Plex tends to miscalculate audio bitrates sometimes, though

    def translateAudioCodec(self, codec=None):
        mc = getattr(self, "mediaChoice")
        streamBase = mc.audioStream if mc else self
        if not any([codec, hasattr(streamBase, "codec")]):
            return ''

        codec = (codec or (streamBase.codec or '')).lower()
        title = streamBase.title.lower()
        ref_part = (mc and mc.part) or self.part
        fn = (ref_part and ref_part.file or '').lower()
        as_count = ref_part and len(ref_part.audioStreams)

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
            definitely_ertmers = (streamBase and streamBase.bitrate.asInt() >= self.MIN_JOC_BITRATE) or EAC3JOC_STR in title
            possible_ertmers = False
            if not definitely_ertmers:
                possible_ertmers = EAC3JOC_STR in fn
                # if we only have one audio stream or our selected stream is the default stream, assume the tag in the
                # filename is correct
                if possible_ertmers and (as_count == 1 or (streamBase and (streamBase.selected.asBool() and streamBase.default.asBool()))):
                    definitely_ertmers = True
                    possible_ertmers = False

            if definitely_ertmers or possible_ertmers:
                codec = "DD+ {}".format(EAC3JOC_STR.capitalize() + (possible_ertmers and "?" or ""))
                return codec

        return codec.upper()
