# coding=utf-8
import six
from collections import OrderedDict
from plexnet import plexapp
from kodi_six import xbmc


class MediaDetails:
    """
    Gathers attributes from a MediaContainer
    """
    details = None
    attribute_map = {
        "container": "part.attrib_container",
        "partDecision": "part.decision",
        "videoResolution": "media.videoResolution",
        "videoBitrate": "video_stream.bitrate",
        "videoCodec": "video_stream.codec",
        "videoStreamDecision": "video_stream.decision",
        "transcodeVideoDecision": "transcode_session.videoDecision",
        "transcodeHWEncoding": "transcode_session.transcodeHwEncoding",
        "audioCodec": "audio_stream.codec",
        "audioBitrate": "audio_stream.bitrate",
        "audioChannels": "audio_stream.channels",
        "audioStreamDecision": "audio_stream.decision",
        "subtitleCodec": "subtitle_stream.codec",
        "subtitleStreamDecision": "subtitle_stream.decision",
        "subtitleLocation": "subtitle_stream.location",
        "subtitleBurn": "subtitle_stream.burn",
        "subtitleAutoSync": "subtitle_stream.should_auto_sync",
    }

    def __init__(self, *args, **kwargs):
        self.details = self.findMediaDetails(*args, **kwargs)

    def attributesFromInstance(self, map, reference_data):
        # gather attribute values
        final_data = {}
        for attribute, dataPath in six.iteritems(map):
            objName, attribName = dataPath.split(".")
            if objName in reference_data:
                obj = reference_data[objName]
                final_data[attribute] = getattr(obj, attribName, None) or None
        return final_data

    def findMediaDetails(self, mediaContainer, mediaChoice, transcodeSession=None):
        """

        """
        reference_data = {
            "media": None,
            "part": None,
            "video_stream": None,
            "audio_stream": None,
            "subtitle_stream": None,
            "transcode_session": transcodeSession or mediaContainer.transcodeSession
        }

        # We can't use mediaChoice here directly, because it doesn't necessarily hold the newest data (in case of
        # an actual MediaContainer from the Session endpoint that data is king)
        # Instead find the media/part/streams which were selected and are held in MediaChoice inside the current
        # mediaContainer
        for media in mediaContainer.media:
            if media.id == mediaChoice.media.id:
                reference_data["media"] = media

                for part in media.parts:
                    if part.id == mediaChoice.part.id:
                        reference_data["part"] = part

                        for stream in part.streams:
                            if mediaChoice.videoStream != None and stream.id == mediaChoice.videoStream.id:
                                reference_data["video_stream"] = stream
                            elif mediaChoice.audioStream != None and stream.id == mediaChoice.audioStream.id:
                                reference_data["audio_stream"] = stream
                            elif mediaChoice.subtitleStream != None and stream.id == mediaChoice.subtitleStream.id:
                                reference_data["subtitle_stream"] = stream

        final_data = {
            "hasVideoStream": bool(reference_data["video_stream"]),
            "hasAudioStream": bool(reference_data["audio_stream"]),
            "hasSubtitleStream": bool(reference_data["subtitle_stream"]),
        }
        final_data.update(self.attributesFromInstance(self.attribute_map, reference_data))

        del reference_data

        return final_data

    def __getattr__(self, item):
        if self.details and item in self.details:
            return self.details[item]
        raise AttributeError("%r object has no attribute %r" % (self.__class__, item))


class MediaDetailsIncomplete(MediaDetails):
    """
    Gathers attributes from a TranscodeSession
    """

    incompleteAttribMap = {
        "container": "transcode_session.attrib_container",
        "videoCodec": "transcode_session.videoCodec",
        "videoStreamDecision": "transcode_session.videoDecision",
        "transcodeVideoDecision": "transcode_session.videoDecision",
        "audioCodec": "transcode_session.audioCodec",
        "audioChannels": "transcode_session.audioChannels",
        "audioStreamDecision": "transcode_session.audioDecision",
        "subtitleStreamDecision": "transcode_session.subtitleDecision",
    }

    def findMediaDetails(self, mediaContainer, mediaChoice, incompleteSessionData=None):
        transcodeSession = mediaContainer._findTranscodeSession(incompleteSessionData)

        # get base data from original mediaChoice media instance
        data = MediaDetails.findMediaDetails(self, mediaContainer, mediaChoice, transcodeSession=transcodeSession)

        decision = "directplay"
        bandwidths = mediaContainer._findBandwidths(incompleteSessionData)

        if transcodeSession:
            decision = "transcode"

            data.update(self.attributesFromInstance(self.incompleteAttribMap, {"transcode_session": transcodeSession}))

            # fill remaining data

            for bw in bandwidths:
                if bw.resolution:
                    data["videoResolution"] = bw.resolution
                    break

            if data["hasVideoStream"]:
                # sadly we don't know the final bitrate for the video/audio streams with incomplete data
                data["videoBitrate"] = "?"

            if data["hasAudioStream"]:
                data["audioBitrate"] = "?"

            if data["hasSubtitleStream"]:
                if data["subtitleStreamDecision"] == "burn":
                    data["subtitleBurn"] = True
                    data["subtitleCodec"] = "burn"

        data["partDecision"] = decision

        return data


class MediaDetailsHolder:
    """
    Holds information about the currently selected MediaContainer (self.original) and the currently playing
    MediaContainer (self.session)
    """
    session = None
    original = None

    def __init__(self, originalMedia, sessionMedia, mediaChoice, incompleteSessionData=None):
        if incompleteSessionData:
            self.session = MediaDetailsIncomplete(originalMedia, mediaChoice,
                                                  incompleteSessionData=incompleteSessionData)
        else:
            self.session = MediaDetails(sessionMedia, mediaChoice)
        self.original = MediaDetails(originalMedia, mediaChoice)


ATTRIBUTE_TYPES = OrderedDict()


def registerAttributeType(cls):
    ATTRIBUTE_TYPES[cls.name] = cls
    return cls


def normRes(res):
    try:
        int(res)
    except:
        pass
    else:
        res += "p"
    return res


class DPAttribute:
    """
    An attribute reference to source.attr
    """
    def __init__(self, attr, source="details.original"):
        self.attr = attr
        self.attrWithPath = "%s.%s" % (source, attr) if source else attr

    def __call__(self, *args, **kwargs):
        return self.value(*args, **kwargs)

    def resolve(self, instance_or_value, obj):
        """
        Resolve attribute to value based on the given type.
        Returns value or Attribute.value()

        :param instance_or_value: Attribute instance or value
        :param obj: VideoSessionInfo instance
        :return:
        """
        return instance_or_value.value(obj) if isinstance(instance_or_value, DPAttribute) else instance_or_value

    def value(self, obj):
        """
        Returns value of the given path based on obj

        :param obj: VideoSessionInfo instance
        :return:
        """
        o = obj
        for p in self.attrWithPath.split("."):
            o = getattr(o, p, None)

        return o


class DPAttributeOriginal(DPAttribute):
    pass


class DPAttributeSession(DPAttribute):
    def __init__(self, attr):
        DPAttribute.__init__(self, attr, source="details.session")


class DPAttributesDiffer(DPAttribute):
    def __init__(self, attr, formatTrue=u"%(val1)s->%(val2)s", formatFalse=u"%(val1)s",
                 valueFormatter=lambda i, v1, v2: [v1, v2]):
        DPAttribute.__init__(self, attr)
        self.formatTrue = formatTrue
        self.formatFalse = formatFalse
        self.valueFormatter = valueFormatter

    def value(self, obj):
        """
        Returns formatted value if values differ, otherwise the original value based on attr

        :param obj: VideoSessionInfo instance
        :return:
        """
        val1 = getattr(obj.details.original, self.attr, None)
        val2 = getattr(obj.details.session, self.attr, None)
        formatted_val1, formatted_val2 = self.valueFormatter(obj, val1, val2)

        if formatted_val2 and formatted_val1 != formatted_val2:
            return self.formatTrue % {"val1": formatted_val1, "val2": formatted_val2}
        if not formatted_val1:
            return ""
        return (self.formatFalse % {"val1": formatted_val1, "val2": formatted_val2}) if self.formatFalse else formatted_val1


class DPAttributeExists(DPAttribute):
    def __init__(self, attr, source="details.session", returnValue=None):
        DPAttribute.__init__(self, attr, source=source)
        self.returnValue = returnValue

    def value(self, obj):
        """
        Returns returnValue, which may also be an Attribute instance, in case attr exists on obj

        :param obj:  VideoSessionInfo instance
        :return:
        """
        result = DPAttribute.value(self, obj)
        if self.returnValue and result:
            return self.resolve(self.returnValue, obj)

        return result


class DPAttributeEqualsValue(DPAttribute):
    def __init__(self, attr, compareTo, retVal, retValFalse=None, source="details.session", fallback=None):
        DPAttribute.__init__(self, attr, source=source)
        self.compareTo = compareTo
        self.retVal = retVal
        self.retValFalse = retValFalse
        self.fallback = fallback

    def value(self, obj):
        """
        Returns retVal, which may also be an Attribute, if attr's value equals compareTo's value. compareTo may also
        be an Attribute.

        :param obj: VideoSessionInfo instance
        :return:
        """
        result = DPAttribute.value(self, obj)
        if result == self.resolve(self.compareTo, obj):
            return self.resolve(self.retVal, obj)
        elif result is None and self.fallback is not None:
            return self.resolve(self.fallback, obj)
        elif self.retValFalse is not None:
            return self.resolve(self.retValFalse, obj)


class DPAttributeMapped(DPAttribute):
    def __init__(self):
        pass

    def value(self, obj):
        p = xbmc.Player()
        if p.isPlaying():
            f = p.getPlayingFile()
            prot = f.split("://")[0]
            if prot == f:
                ret = "path mapped"
            elif prot.startswith("http"):
                ret = prot
            else:
                ret = "mapped ({})".format(prot)
            return ret


class ComputedPPIValue:
    """
    Holds the final computed attribute data for display
    """
    name = None
    data = None
    displayCondition = None
    dataPoints = []

    @property
    def label(self):
        return self.name

    @property
    def value(self):
        return ", ".join([x for x in self.data if x not in (None, "")])

    def __str__(self):
        return "%s: %s" % (self.label, self.value)

    def __repr__(self):
        return str(self)


@registerAttributeType
class ModePPI(ComputedPPIValue):
    name = "Mode"
    dataPoints = [
        DPAttributeSession("partDecision"),
        DPAttributeEqualsValue("local", "1",
                               DPAttribute("server_is_local", source="details"),
                               DPAttribute("server_is_local", source="details"),
                               source="session.player",
                               fallback=DPAttribute("server_is_local", source="details")),
        #DPAttribute("location", source="session.session"),
        #DPAttribute("server_is_local", source="details"),
        DPAttributeMapped()
    ]


@registerAttributeType
class ContainerPPI(ComputedPPIValue):
    name = "Container"
    dataPoints = [
        DPAttributesDiffer("container"),
    ]


@registerAttributeType
class VideoPPI(ComputedPPIValue):
    name = "Video"
    displayCondition = DPAttributeExists("hasVideoStream", source="details.original")
    dataPoints = [
        DPAttributesDiffer("videoCodec"),
        DPAttributesDiffer("videoResolution", valueFormatter=lambda i, v1, v2: [normRes(v1), normRes(v2)]),
        DPAttributesDiffer("videoBitrate", formatTrue=u"%(val1)s->%(val2)skbit", formatFalse=u"%(val1)skbit",
                           valueFormatter=lambda i, v1, v2: [v1, v2 if v2 != "2147483647" else "?"]),
        lambda i: [
            (i.details.session.videoStreamDecision + " HW")
            if i.details.session.transcodeVideoDecision == "transcode" and i.details.session.transcodeHWEncoding
            else i.details.session.videoStreamDecision
        ]
    ]


@registerAttributeType
class AudioPPI(ComputedPPIValue):
    name = "Audio"
    displayCondition = DPAttributeExists("hasAudioStream", source="details.original")
    dataPoints = [
        DPAttributesDiffer("audioCodec"),
        DPAttributesDiffer("audioBitrate", formatTrue=u"%(val1)s->%(val2)skbit", formatFalse=u"%(val1)skbit"),
        DPAttributesDiffer("audioChannels", formatTrue=u"%(val1)s->%(val2)sch", formatFalse=u"%(val1)sch"),
        DPAttributeExists("audioStreamDecision")
    ]


@registerAttributeType
class SubtitlesPPI(ComputedPPIValue):
    name = "Subtitles"
    displayCondition = DPAttributeExists("hasSubtitleStream", source="details.original")
    dataPoints = [
        DPAttributesDiffer("subtitleCodec", valueFormatter=lambda i, v1, v2: [v1,
                                                                        "burn" if i.details.session.subtitleBurn else v2]),
        DPAttributeEqualsValue("subtitleStreamDecision", "burn", DPAttribute("subtitleStreamDecision")),
        DPAttributeExists("subtitleLocation"),
        DPAttributesDiffer("subtitleAutoSync", valueFormatter=lambda i, v1, v2: [v1 and "auto-sync" or None, None]),
    ]


@registerAttributeType
class UserPPI(ComputedPPIValue):
    name = "User"
    dataPoints = [
        lambda i: [u"%s @ %s" % (plexapp.ACCOUNT.title or plexapp.ACCOUNT.username or ' ', i.mediaItem.server.name)]
    ]


class SessionAttributes(OrderedDict):
    """
    Computes all the PPI instances' values
    """
    def __init__(self, ref, *args, **kwargs):
        self.ref = ref
        OrderedDict.__init__(self, *args, **kwargs)

        for name, cls in six.iteritems(ATTRIBUTE_TYPES):
            self[name] = instance = cls()
            instance.data = []
            if not instance.displayCondition or instance.displayCondition(self.ref):
                for dp in instance.dataPoints:
                    try:
                        # dataPoint may be a lambda or a DataPoint instance
                        result = dp(self.ref)

                        # result may be list or value
                        if result is not None:
                            if isinstance(result, list):
                                instance.data += result
                            else:
                                instance.data.append(result)
                    except:
                        pass


class VideoSessionInfo:
    def __init__(self, sessionMediaContainer, mediaContainer, server_is_local, incompleteSessionData=False):
        self.mediaItem = mediaContainer
        self.session = sessionMediaContainer
        self.details = MediaDetailsHolder(self.mediaItem, self.session, mediaContainer.mediaChoice,
                                          incompleteSessionData=incompleteSessionData)
        self.details.server_is_local = server_is_local and "lan (verified)" or "remote"
        self.attributes = SessionAttributes(self)

