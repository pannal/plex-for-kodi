from __future__ import absolute_import
import re
from . import util
from . import captions
from . import http
from . import plexrequest
from . import mediadecisionengine
from . import serverdecision
from lib.util import KODI_VERSION_MAJOR
from lib.cache import CACHE_SIZE

from six.moves import range
from six import ensure_str

DecisionFailure = serverdecision.DecisionFailure


class BasePlayer(object):
    item = None

    def setupObj(self, obj, part, server, force_request_to_server=False):
        # check for path mapping
        url = part.getPathMappedUrl()

        if not url:
            url = server.buildUrl(part.getAbsolutePath("key"))
            # Check if we should include our token or not for this request
            obj.isRequestToServer = force_request_to_server or server.isRequestToServer(url)
            obj.streamUrls = [server.buildUrl(part.getAbsolutePath("key"), obj.isRequestToServer)]
            obj.isMapped = False
        else:
            obj.isRequestToServer = False
            obj.streamUrls = [url]
            obj.isMapped = True


class PlexPlayer(BasePlayer):
    DECISION_ENDPOINT = "/video/:/transcode/universal/decision"

    def __init__(self, item, seekValue=0, forceUpdate=False, session_id=None):
        self.decision = None
        self.seekValue = seekValue
        self.metadata = None
        self.sessionID = session_id
        self.init(item, forceUpdate)

    def init(self, item, forceUpdate=False):
        self.item = item
        self.choice = mediadecisionengine.MediaDecisionEngine().chooseMedia(item, forceUpdate=forceUpdate)
        if self.choice:
            self.media = self.choice.media

    def terminate(self, code, reason):
        util.LOG('TERMINATE PLAYER: ({0}, {1})', code, reason)
        # TODO: Handle this? ---------------------------------------------------------------------------------------------------------- TODO

    @property
    def audioChannels(self):
        """
        Parse Kodi channel setting into channel count
        """
        channelDef = self.item.settings.getGlobal("audioChannels", "2.0")
        major, minor = channelDef.split(".") if "." in channelDef else (channelDef, 0)
        return int(major) + int(minor)

    def rebuild(self, item, decision=None):
        # item.settings = self.item.settings
        oldChoice = self.choice
        self.init(item, True)
        util.LOG("Replacing '{0}' with '{1}' and rebuilding.", oldChoice, self.choice)
        self.build()
        self.decision = decision

    def build(self, forceTranscode=False):
        features = self.item.settings.getPlaybackFeatures()
        if "playback_directplay" in features:
            directPlayPref = self.item.settings.getPreference("playback_directplay_force", False) and 'forced' or 'allow'
        else:
            directPlayPref = 'disabled'

        if forceTranscode or directPlayPref == "disabled" or self.choice.hasBurnedInSubtitles is True:
            directPlay = False
        else:
            directPlay = directPlayPref == "forced" and True or None

        return self._build(directPlay, "playback_remux" in features, features=features)

    def _build(self, directPlay=None, directStream=True, currentPartIndex=None, features=None):
        isForced = directPlay is not None
        if isForced:
            util.LOG(directPlay and "Forced Direct Play" or "Forced Transcode; allowDirectStream={0}".format(directStream))

        directPlay = False if directPlay is False else self.choice.isDirectPlayable

        server = self.item.getServer()

        # A lot of our content metadata is independent of the direct play decision.
        # Add that first.

        obj = util.AttributeDict()
        obj.duration = self.media.duration.asInt()

        videoRes = self.media.getVideoResolution()
        obj.fullHD = videoRes >= 1080
        obj.streamQualities = (videoRes >= 480 and self.item.settings.getGlobal("IsHD")) and ["HD"] or ["SD"]

        frameRate = self.media.videoFrameRate or "24p"
        if frameRate == "24p":
            obj.frameRate = 24
        elif frameRate == "NTSC":
            obj.frameRate = 30

        # Add soft subtitle info
        if self.choice.subtitleDecision == self.choice.SUBTITLES_SOFT_ANY:
            # add sub autosync settings per item
            auto_sync = self.item.playbackSettings.auto_sync
            obj.subtitleUrl = server.buildUrl(self.choice.subtitleStream.getSubtitlePath(auto_sync=auto_sync), True)
        elif self.choice.subtitleDecision == self.choice.SUBTITLES_SOFT_DP:
            obj.subtitleConfig = {'TrackName': "mkv/" + str(self.choice.subtitleStream.index.asInt() + 1)}

        # Create one content metadata object for each part and store them as a
        # linked list. We probably want a doubly linked list, except that it
        # becomes a circular reference nuisance, so we make the current item the
        # base object and singly link in each direction from there.

        baseObj = obj
        prevObj = None
        startOffset = 0

        startPartIndex = currentPartIndex or 0
        for partIndex in range(startPartIndex, len(self.media.parts)):
            isCurrentPart = (currentPartIndex is not None and partIndex == currentPartIndex)
            partObj = util.AttributeDict()
            partObj.update(baseObj)

            partObj.live = False
            partObj.partIndex = partIndex
            partObj.startOffset = startOffset

            part = self.media.parts[partIndex]

            partObj.partDuration = part.duration.asInt()
            partObj.path = ensure_str(part.file)
            partObj.size = part.size and int(part.size) or ''

            if part.isIndexed():
                partObj.sdBifPath = part.getIndexPath("sd")
                partObj.hdBifPath = part.getIndexPath("hd")

            # We have to evaluate every part before playback. Normally we'd expect
            # all parts to be identical, but in reality they can be different.

            if partIndex > 0 and (not isForced and directPlay or not isCurrentPart):
                choice = mediadecisionengine.MediaDecisionEngine().evaluateMediaVideo(self.item, self.media, partIndex)
                canDirectPlay = (choice.isDirectPlayable is True)
            else:
                canDirectPlay = directPlay

            if canDirectPlay:
                partObj = self.buildDirectPlay(partObj, partIndex)
            else:
                transcodeServer = self.item.getTranscodeServer(True, "video")
                if transcodeServer is None:
                    return None
                partObj = self.buildTranscode(transcodeServer, partObj, partIndex, directStream, isCurrentPart,
                                              features=features)

            # Set up our linked list references. If we couldn't build an actual
            # object: fail fast. Otherwise, see if we're at our start offset
            # yet in order to decide if we need to link forwards or backwards.
            # We also need to account for parts missing a duration, by verifying
            # the prevObj is None or if the startOffset has incremented.

            if partObj is None:
                obj = None
                break
            elif prevObj is None or (startOffset > 0 and int(self.seekValue / 1000) >= startOffset):
                obj = partObj
                partObj.prevObj = prevObj
            elif prevObj is not None:
                prevObj.nextPart = partObj

            startOffset = startOffset + int(part.duration.asInt() / 1000)

            prevObj = partObj

        # Only set PlayStart for the initial part, and adjust for the part's offset
        if obj is not None:
            if obj.live:
                # Start the stream at the end. Per Roku, this can be achieved using
                # a number higher than the duration. Using the current time should
                # ensure it's definitely high enough.

                obj.playStart = util.now() + 1800
            else:
                obj.playStart = int(self.seekValue / 1000) - obj.startOffset

        self.metadata = obj

        util.LOG("Constructed video item for playback: {0}", util.cleanObjTokens(dict(obj)))

        return self.metadata

    @property
    def startOffset(self):
        return self.metadata and self.metadata.startOffset or 0

    def offsetIsValid(self, offset_seconds):
        return self.metadata.startOffset <= offset_seconds < self.metadata.startOffset + (self.metadata.partDuration / 1000)

    def isLiveHls(url=None, headers=None):
        # Check to see if this is a live HLS playlist to fix two issues. One is a
        # Roku workaround since it doesn't obey the absence of EXT-X-ENDLIST to
        # start playback at the END of the playlist. The second is for us to know
        # if it's live to modify the functionality and player UI.

        # if IsString(url):
        #     request = createHttpRequest(url, "GET", true)
        #     AddRequestHeaders(request.request, headers)
        #     response = request.GetToStringWithTimeout(10)

        #     ' Inspect one of the media playlist streams if this is a master playlist.
        #     if response.instr("EXT-X-STREAM-INF") > -1 then
        #         Info("Identify live HLS: inspecting the master playlist")
        #         mediaUrl = CreateObject("roRegex", "(^https?://.*$)", "m").Match(response)[1]
        #         if mediaUrl <> invalid then
        #             request = createHttpRequest(mediaUrl, "GET", true)
        #             AddRequestHeaders(request.request, headers)
        #             response = request.GetToStringWithTimeout(10)
        #         end if
        #     end if

        #     isLiveHls = (response.Trim().Len() > 0 and response.instr("EXT-X-ENDLIST") = -1 and response.instr("EXT-X-STREAM-INF") = -1)
        #     Info("Identify live HLS: live=" + isLiveHls.toStr())
        #     return isLiveHls

        return False

    def getServerDecision(self):
        directPlay = not (self.metadata and self.metadata.isTranscoded)
        decisionPath = self.getDecisionPath(directPlay)
        newDecision = None

        if decisionPath:
            server = self.metadata.transcodeServer or self.item.getServer()
            request = plexrequest.PlexRequest(server, decisionPath)
            response = request.getWithTimeout(util.DEFAULT_TIMEOUT)

            if response.isSuccess() and response.container:
                decision = serverdecision.ServerDecision(self, response, self)

                if decision.isSuccess():
                    util.LOG("MDE: Server was happy with client's original decision. {0}", decision)
                    return self
                elif decision.isDecision(True):
                    util.WARN_LOG("MDE: Server was unhappy with client's original decision. {0}".format(decision))
                    return decision.getDecision()
                else:
                    util.LOG("MDE: Server was unbiased about the decision. {0}", decision)

                # Check if the server has provided a new media item to use it. If
                # there is no item, then we'll continue along as if there was no
                # decision made.
                newDecision = decision.getDecision(False)
            else:
                util.WARN_LOG("MDE: Server failed to provide a decision")
                raise DecisionFailure("0", "Can't play back media")
        else:
            util.WARN_LOG("MDE: Server or item does not support decisions")

        return newDecision or self

    def getDecisionPath(self, directPlay=False):
        if not self.item or not self.metadata:
            return None

        features = self.item.settings.getPlaybackFeatures()

        decisionPath = self.metadata.decisionPath
        if not decisionPath:
            server = self.metadata.transcodeServer or self.item.getServer()
            decisionPath = self.buildTranscode(server, util.AttributeDict(),
                                               self.metadata.partIndex,
                                               True,
                                               False,
                                               features=features).decisionPath

        # Modify the decision params based on the transcode url
        if decisionPath:
            if directPlay:
                decisionPath = decisionPath.replace("directPlay=0", "directPlay=1")

                # Clear all subtitle parameters and add the a valid subtitle type based
                # on the video player. This will let the server decide if it can supply
                # sidecar subs, burn or embed w/ an optional transcode.
                for key in ("subtitles", "advancedSubtitles"):
                    decisionPath = re.sub(r'([?&]{0}=)\w+'.format(key), '', decisionPath)
                subType = 'sidecar'  # AppSettings().getBoolPreference("custom_video_player"), "embedded", "sidecar")
                decisionPath = http.addUrlParam(decisionPath, "subtitles=" + subType)

            # Global variables for all decisions
            # Kodi default is 20971520 (20MB)
            decisionPath = http.addUrlParam(decisionPath,
                                            "mediaBufferSize={}".format(str(CACHE_SIZE * 1024)))
            decisionPath = http.addUrlParam(decisionPath, "hasMDE=1")

            decisionPath = http.addUrlParam(decisionPath, 'X-Plex-Client-Profile-Name=Generic')

        return decisionPath

    def getTranscodeReason(self):
        # Combine the server and local MDE decisions
        obj = []
        if self.decision:
            obj.append(self.decision.getDecisionText())
        if self.item:
            obj.append(self.item.transcodeReason)
        reason = ' '.join(obj)
        if not reason:
            return None

        return reason

    def buildTranscodeHls(self, obj):
        util.DEBUG_LOG('buildTranscodeHls()')
        obj.streamFormat = "hls"
        obj.streamBitrates = [0]
        obj.switchingStrategy = "no-adaptation"
        obj.transcodeEndpoint = "/video/:/transcode/universal/start.m3u8"

        builder = http.HttpRequest(obj.transcodeServer.buildUrl(obj.transcodeEndpoint, True))
        builder.extras = []
        builder.addParam("protocol", "hls")

        builder.addParam("X-Plex-Client-Profile-Name", "Generic")

        if self.choice.subtitleDecision == self.choice.SUBTITLES_SOFT_ANY:
            builder.addParam("skipSubtitles", "1")
        else:  # elif self.choice.hasBurnedInSubtitles is True:  # Must burn transcoded because we can't set offset
            captionSize = captions.CAPTIONS.getBurnedSize()
            if captionSize is not None:
                builder.addParam("subtitleSize", captionSize)

        # Augment the server's profile for things that depend on the Roku's configuration.
        if self.item.settings.supportsAudioStream("ac3", 6):
            builder.extras.append("append-transcode-target-audio-codec(type=videoProfile&context=streaming&protocol=hls&audioCodec=ac3)")
            builder.extras.append("add-direct-play-profile(type=videoProfile&container=mkv&videoCodec=*&audioCodec=ac3)")

        return builder

    def buildTranscodeMkv(self, obj, directStream=True):
        util.DEBUG_LOG('buildTranscodeMkv()')
        obj.streamFormat = "mkv"
        obj.streamBitrates = [0]
        obj.transcodeEndpoint = "/video/:/transcode/universal/start.mkv"

        builder = http.HttpRequest(obj.transcodeServer.buildUrl(obj.transcodeEndpoint, True))
        builder.extras = []
        builder.addParam("protocol", "http")
        builder.addParam("copyts", "1")
        builder.addParam("X-Plex-Client-Profile-Name", "Generic")

        obj.subtitleUrl = None

        video_codecs = self.item.settings.getAdditionalCodecs()
        clampToOrig = self.item.settings.getPreference("audio_clamp_to_orig", True)
        useKodiAudio = self.item.settings.getPreference("audio_channels_kodi", False)
        AC3Cond = self.item.settings.getPreference("audio_force_ac3_cond", 'never')
        dtsIsAC3 = self.item.settings.getPreference("audio_ac3dts", True)
        hasAudioChoice = self.choice.audioStream is not None
        forceAC3 = AC3Cond != 'never'

        ach = None
        if AC3Cond in ('2', '3', '5', '6'):
            ach = int(AC3Cond)

        # fixme: still necessary?
        if self.choice.subtitleDecision == self.choice.SUBTITLES_BURN:
            builder.addParam("subtitles", "burn")
            captionSize = captions.CAPTIONS.getBurnedSize()
            if captionSize is not None:
                builder.addParam("subtitleSize", captionSize)

        else:
            # TODO(rob): can we safely assume the id will also be 3 (one based index).
            # If not, we will have to get tricky and select the subtitle stream after
            # video playback starts via roCaptionRenderer: GetSubtitleTracks() and
            # ChangeSubtitleTrack()

            obj.subtitleConfig = {'TrackName': "mkv/3" if hasAudioChoice else "mkv/2"}

            # Allow text conversion of subtitles if we only burn image formats
            #if self.item.settings.getPreference("burn_subtitles") == "image":
            if not self.item.settings.getPreference("burn_ssa", True):
                builder.addParam("advancedSubtitles", "text")

            builder.addParam("subtitles", "auto")

        if not forceAC3:
            if directStream:
                audioCodecs = util.AUDIO_CODECS
            else:
                audioCodecs = util.AUDIO_CODECS_TC

            # filter audio codecs
            disACodecs = self.item.settings.getPreference("audio_disabled_codecs", [])
            if disACodecs:
                audioCodecs = list(set(audioCodecs) - set(disACodecs))

            # force transcode audio codec
            tcACodec = self.item.settings.getPreference("audio_transcode_codec", "default")
            if tcACodec != "default":
                audioCodecs = [tcACodec]
        else:
            if dtsIsAC3:
                audioCodecs = ["ac3", "dca"]
            else:
                audioCodecs = ["ac3",]

        subtitleCodecs = "srt,ssa,ass,mov_text,tx3g,ttxt,text,pgs,vobsub,smi,subrip,eia_608_embedded," \
                         "eia_708_embedded,dvb_subtitle" + (",webvtt" if KODI_VERSION_MAJOR > 19 else '')


        util.LOG('MDE-prep: enabling codecs: {}', audioCodecs)

        # Allow virtually anything in Kodi playback.

        # DP might not do anything here
        # builder.extras.append(
        #     "add-direct-play-profile(type=videoProfile&videoCodec="
        #     "h264,mpeg1video,mpeg2video,mpeg4,msmpeg4v2,msmpeg4v3,vc1,wmv3&container=*&"
        #     "audioCodec="+audioCodecs+"&protocol=http)")

        builder.extras.append(
            "add-transcode-target(type=videoProfile&videoCodec="
            "h264,mpeg1video,mpeg2video,mpeg4,msmpeg4v2,msmpeg4v3,wmv3&container=mkv&"
            "audioCodec={}&subtitleCodec={}&protocol=http&context=streaming)".format(",".join(audioCodecs), subtitleCodecs))

        # builder.extras.append(
        #     "append-transcode-target-audio-codec(type=videoProfile&context=streaming&protocol=http&audioCodec=" +
        #     audioCodecs + ")")

        # if self.item.settings.supportsSurroundSound():
        #     if self.choice.audioStream is not None:
        #         numChannels = self.choice.audioStream.channels.asInt(8)
        #     else:
        #         numChannels = 8
        #
        #     for codec in ("ac3", "eac3", "dca"):
        #         if self.item.settings.supportsAudioStream(codec, numChannels):
        #             builder.extras.append("append-transcode-target-audio-codec(type=videoProfile&context=streaming&protocol=http&audioCodec=" + codec + ")")
        #             builder.extras.append("add-direct-play-profile(type=videoProfile&videoCodec=*&container=mkv&audioCodec=" + codec + ")")
        #             if codec == "dca":
        #                 builder.extras.append(
        #                     "add-limitation(scope=videoAudioCodec&scopeName=dca&type=upperBound&name=audio.channels&value=8&isRequired=false)"
        #                 )
        #
        # for codec in ("ac3", "eac3", "dca"):
        #     builder.extras.append("append-transcode-target-audio-codec(type=videoProfile&context=streaming&protocol=http&audioCodec=" + codec + ")")
        #     builder.extras.append("add-direct-play-profile(type=videoProfile&videoCodec=*&container=mkv&audioCodec=" + codec + ")")

        util.LOG('MDE-prep: settings: clampOrig: {}, kodiAudio: {}, forceAC3: {}, dtsIsAC3: {}'
                 .format(clampToOrig, useKodiAudio, forceAC3, dtsIsAC3))

        # limit audio channels to original stream's audio channel amount
        numChannels = self.choice.audioStream.channels.asInt(8) if hasAudioChoice and \
            self.choice.audioStream.channels else 8

        # limit OPUS to 334kbit
        if numChannels == 8:
            # 7.1
            opusBitrate = 334
        elif numChannels >= 6:
            # 5.1
            opusBitrate = 256
        else:
            # 2
            opusBitrate = 128

        # limit max audio channels to audio stream or kodi (whichever is lower)
        maxAudioChannels = numChannels if not useKodiAudio else min(numChannels, self.audioChannels)

        # if we've got a channel limit for AC3/DTS, apply it
        maxAudioChannels = maxAudioChannels if not ach else min(maxAudioChannels, ach)

        if forceAC3 and hasAudioChoice:
            # limit max audio channels to the above or 6 for AC3 (whichever is lower)
            if self.choice.audioStream.codec != "dca":
                maxAudioChannels = min(6, maxAudioChannels)
            else:
                # allow DTS 6.1 ES
                maxAudioChannels = min(7, maxAudioChannels)

        streamWasAC3 = hasAudioChoice and self.choice.audioStream.codec == "ac3"

        if not forceAC3 and hasAudioChoice:
            # limit audio bitrate to the same bitrate as the current stream's codec
            if clampToOrig and self.choice.audioStream.bitrate:
                util.LOG('MDE-prep: limiting {} to {} kbit'.format(self.choice.audioStream.codec.upper(),
                                                                   self.choice.audioStream.bitrate))
                builder.extras.append(
                    "add-limitation(scope=videoAudioCodec&scopeName={}&"
                    "type=upperBound&name=audio.bitrate&value={})".format(
                        self.choice.audioStream.codec,
                        self.choice.audioStream.bitrate
                    )
                )

            # limit OPUS bitrate
            if hasAudioChoice and self.choice.audioStream.codec != "opus":
                util.LOG('MDE-prep: limiting OPUS bitrate to {} kbit', opusBitrate)
                builder.extras.append(
                    "add-limitation(scope=videoAudioCodec&scopeName=opus&type=upperBound&name=audio.bitrate&"
                    "value={}&isRequired=false)".format(opusBitrate)
                )

        # limit AC3
        if not streamWasAC3 or forceAC3:
            util.LOG('MDE-prep: limiting AC3 to 640 kbit')
            builder.extras.append(
                "add-limitation(scope=videoAudioCodec&scopeName=ac3&type=upperBound&name=audio.bitrate&value=640)"
            )

        util.LOG('MDE-prep: limiting audio channels to {}', maxAudioChannels)
        builder.extras.append(
            "add-limitation(scope=videoAudioCodec&scopeName=*&type=upperBound&"
            "name=audio.channels&value={})".format(maxAudioChannels)
        )

        # AAC sample rate cannot be less than 22050hz (HLS is capable).
        if self.choice.audioStream is not None and self.choice.audioStream.samplingRate.asInt(22050) < 22050:
            builder.extras.append(
                "add-limitation(scope=videoAudioCodec&scopeName=aac&type=lowerBound&"
                "name=audio.samplingRate&value=22050&isRequired=false)")

        # HEVC
        if "allow_hevc" in video_codecs:
            builder.extras.append(
                "append-transcode-target-codec(type=videoProfile&context=streaming&container=mkv&"
                "protocol=http&videoCodec=hevc)")
            # builder.extras.append(
            #     "add-direct-play-profile(type=videoProfile&videoCodec=hevc&container=*&audioCodec=*)")

        # VP9
        if self.item.settings.getGlobal("vp9Support"):
            builder.extras.append(
                "append-transcode-target-codec(type=videoProfile&context=streaming&container=mkv&"
                "protocol=http&videoCodec=vp9)")
            # builder.extras.append(
            #     "add-direct-play-profile(type=videoProfile&videoCodec=vp9&container=*&audioCodec=*)")

        # AV1
        if "allow_av1" in video_codecs:
            builder.extras.append(
                "append-transcode-target-codec(type=videoProfile&context=streaming&container=mkv&"
                "protocol=http&videoCodec=av1)")
            # builder.extras.append(
            #     "add-direct-play-profile(type=videoProfile&videoCodec=av1&container=*&audioCodec=*)")

        # VC1
        if "allow_vc1" in video_codecs:
            builder.extras.append(
                "append-transcode-target-codec(type=videoProfile&context=streaming&container=mkv&"
                "protocol=http&videoCodec=vc1)")

        if self.item.settings.getPreference("disable_hdr", False):
            builder.extras.append(
                "add-limitation(scope=videoTranscodeTarget&scopeName=*&scopeType=videoCodec&context=streaming&protocol=http&"
                "type=match&name=video.colorTrc&list=bt709|bt470m|bt470bg|smpte170m|smpte240m|bt2020-10|bt2020-10"
                "&isRequired=true)")

        return builder

    def buildDirectPlay(self, obj, partIndex):
        util.DEBUG_LOG('buildDirectPlay()')
        part = self.media.parts[partIndex]

        server = self.item.getServer()

        self.setupObj(obj, part, server)
        obj.token = obj.isRequestToServer and server.getToken() or None

        if self.media.protocol == "hls":
            obj.streamFormat = "hls"
            obj.switchingStrategy = "full-adaptation"
            #obj.live = self.isLiveHls(obj.streamUrls[0], self.media.indirectHeaders)
        else:
            obj.streamFormat = self.media.get('container', 'mp4')
            if obj.streamFormat == "mov" or obj.streamFormat == "m4v":
                obj.streamFormat = "mp4"

        obj.streamBitrates = [self.media.bitrate.asInt()]
        obj.isTranscoded = False

        if self.choice.audioStream is not None:
            obj.audioLanguageSelected = self.choice.audioStream.languageCode

        return obj

    def hasMoreParts(self):
        return (self.metadata is not None and self.metadata.nextPart is not None)

    def getNextPartOffset(self):
        return self.metadata.nextPart.startOffset * 1000

    def goToNextPart(self):
        oldPart = self.metadata
        if oldPart is None:
            return

        newPart = oldPart.nextPart
        if newPart is None:
            return

        newPart.prevPart = oldPart
        oldPart.nextPart = None
        self.metadata = newPart

        util.LOG("Next part set for playback: {0}", self.metadata)

    def getBifUrl(self, offset=0):
        server = self.item.getServer()
        startOffset = 0
        for part in self.media.parts:
            duration = part.duration.asInt()
            if startOffset <= offset < startOffset + duration:
                bifUrl = part.getIndexPath("hd") or part.getIndexPath("sd")
                if bifUrl is not None:
                    url = server.buildUrl('{0}/{1}'.format(bifUrl, offset - startOffset), True)
                    return url

            startOffset += duration

        return None

    def buildTranscode(self, server, obj, partIndex, directStream, isCurrentPart, features=None):
        util.DEBUG_LOG('buildTranscode()')
        obj.transcodeServer = server
        obj.isTranscoded = True

        # if server.supportsFeature("mkvTranscode") and self.item.settings.getPreference("transcode_format", 'mkv') != "hls":
        if server.supportsFeature("mkvTranscode"):
            builder = self.buildTranscodeMkv(obj, directStream=directStream)
        else:
            builder = self.buildTranscodeHls(obj)

        if self.item.getServer().TYPE == 'MYPLEXSERVER':
            path = server.swizzleUrl(self.item.getAbsolutePath("key"))
        else:
            path = self.item.getAbsolutePath("key")

        builder.addParam("path", path)

        if self.choice.subtitleStream and self.choice.subtitleStream.should_auto_sync:
            # add sub autosync settings per item
            auto_sync = self.item.playbackSettings.auto_sync
            builder.addParam("autoAdjustSubtitle", auto_sync and '1' or '0')

        part = self.media.parts[partIndex]
        seekOffset = int(self.seekValue / 1000)
        startOffset = obj.get("startOffset", 0)

        # Disabled for HLS due to a Roku bug plexinc/roku-client-issues#776
        if True:  # obj.streamFormat == "mkv":
            # Trust our seekOffset for this part if it's the current part (now playing) or
            # the seekOffset is within the time frame. We have to trust the current part
            # as we may have to rebuild the transcode when seeking, and not all parts
            # have a valid duration.

            if isCurrentPart or len(self.media.parts) <= 1 or (
                seekOffset >= startOffset and seekOffset <= startOffset + int(part.duration.asInt() / 1000)
            ):
                startOffset = seekOffset - startOffset

                # Avoid a perfect storm of PMS and Roku quirks. If we pass an offset to
                # the transcoder,: it'll start transcoding from that point. But if
                # we try to start a few seconds into the video, the Roku seems to want
                # to grab the first segment. The first segment doesn't exist, so PMS
                # returns a 404 (but only if the offset is <= 12s, otherwise it returns
                # a blank segment). If the Roku gets a 404 for the first segment,:
                # it'll fail. So, if we're going to start playing from less than 12
                # seconds, don't bother telling the transcoder. It's not worth the
                # potential failure, let it transcode from the start so that the first
                # segment will always exist.

                # TODO: Probably can remove this (Rick)
                if startOffset <= 12:
                    startOffset = 0
            else:
                startOffset = 0

            builder.addParam("offset", str(startOffset))

        builder.addParam("session", self.sessionID)
        builder.addParam("directStream", directStream and "1" or "0")
        #builder.addParam("directStreamAudio", directStream and "1" or "0")
        builder.addParam("directPlay", "0")

        qualityIndex = self.item.settings.getQualityIndex(self.item.getQualityType(server))
        #builder.addParam("videoQuality", self.item.settings.getGlobal("transcodeVideoQualities")[qualityIndex])
        maxVideoResolution = "allow_4k" in features and (self.item.settings.maxVerticalDPRes == 99999 and "99999x99999" or "3840x2160") or "1920x1080"
        builder.addParam("videoResolution", str(maxVideoResolution))
        builder.addParam("maxVideoBitrate", self.item.settings.getGlobal("transcodeVideoBitrates")[qualityIndex])

        builder.addParam("X-Plex-Session-Id", self.sessionID)
        builder.addParam("X-Plex-Session-Identifier", self.sessionID)
        builder.addParam('X-Plex-Client-Identifier', self.item.settings.getGlobal('clientIdentifier'))

        builder.extras.append(
            "add-limitation(scope=videoCodec&scopeName=*&context=streaming&protocol=http&"
            "type=upperBound&name=video.height&value={}&isRequired=true)".format("allow_4k" in features and str(self.item.settings.maxVerticalDPRes) or
                                                                                 "1088"))

        if self.media.mediaIndex is not None:
            builder.addParam("mediaIndex", str(self.media.mediaIndex))

        builder.addParam("partIndex", str(partIndex))

        # Augment the server's profile for things that depend on the Roku's configuration.
        if self.item.settings.getPreference("h264_level", "auto") != "auto":
            builder.extras.append(
                "add-limitation(scope=videoCodec&scopeName=h264&type=upperBound&name=video.level&value={0}&isRequired=true)".format(
                    self.item.settings.getPreference("h264_level")
                )
            )

        if not self.item.settings.getGlobal("supports1080p60") and self.item.settings.getGlobal("transcodeVideoResolutions")[qualityIndex][0] >= 1920:
            builder.extras.append("add-limitation(scope=videoCodec&scopeName=h264&type=upperBound&name=video.frameRate&value=30&isRequired=false)")

        if builder.extras:
            builder.addParam("X-Plex-Client-Profile-Extra", '+'.join(builder.extras))

        if server.isLocalConnection():
            builder.addParam("location", "lan")

        obj.streamUrls = [builder.getUrl()]

        # Build the decision path now that we have build our stream url, and only if the server supports it.
        if server.supportsFeature("streamingBrain"):
            decisionPath = builder.getRelativeUrl().replace(obj.transcodeEndpoint, self.DECISION_ENDPOINT)
            if decisionPath.startswith(self.DECISION_ENDPOINT):
                obj.decisionPath = decisionPath

        return obj


class PlexAudioPlayer(BasePlayer):
    def __init__(self, item=None, session_id=None):
        self.item = item
        self.choice = None
        self.sessionID = session_id
        self.containerFormats = {
            'aac': "es.aac-adts"
        }

        self.lyrics = None  # createLyrics(item, self.media)

    def build(self, item, directPlay=None):
        item = item or self.item
        self.choice = choice = mediadecisionengine.MediaDecisionEngine().chooseMedia(item)
        directPlay = directPlay or choice.isDirectPlayable

        obj = util.AttributeDict()

        if directPlay:
            obj = self.buildDirectPlay(item, choice, obj)
        else:
            obj = self.buildTranscode(item, choice, obj)

        util.LOG("Constructed audio item for playback: {0}", util.cleanObjTokens(dict(obj)))

        return obj

    def buildTranscode(self, item, choice, obj):
        transcodeServer = item.getTranscodeServer(True, "audio")
        if not transcodeServer:
            return None

        obj.streamFormat = "mp3"
        obj.isTranscoded = True
        obj.transcodeServer = transcodeServer
        obj.transcodeEndpoint = "/music/:/transcode/universal/start.m3u8"

        builder = http.HttpRequest(transcodeServer.buildUrl(obj.transcodeEndpoint, True))
        builder.addParam("protocol", "http")
        builder.addParam("path", item.getAbsolutePath("key"))
        builder.addParam("session", self.sessionID and self.sessionID or item.getGlobal("clientIdentifier"))
        builder.addParam("directPlay", "0")
        builder.addParam("directStream", "0")

        # this works, but currently shows "Direct Play" in Plex Web, even though it's clearly transcoding
        builder.addParam("X-Plex-Platform", "Generic")
        builder.extras = ["add-transcode-target(type=musicProfile&audioCodec=mp3&container=mp3&"
                          "context=streaming&protocol=http)"]

        builder.addParam("X-Plex-Client-Profile-Extra", '+'.join(builder.extras))

        obj.url = builder.getUrl()

        return obj

    def buildDirectPlay(self, item, choice, obj):
        if choice.part:
            self.setupObj(obj, choice.part, item.getServer(), force_request_to_server=True)
            obj.url = obj.streamUrls[0]

            # Set and override the stream format if applicable
            obj.streamFormat = choice.media.get('container', 'mp3')
            if self.containerFormats.get(obj.streamFormat):
                obj.streamFormat = self.containerFormats[obj.streamFormat]

            # If we're direct playing a FLAC, bitrate can be required, and supposedly
            # this is the only way to do it. plexinc/roku-client#48
            #
            bitrate = choice.media.bitrate.asInt()
            if bitrate > 0:
                obj.streams = [{'url': obj.url, 'bitrate': bitrate}]

            return obj

        # We may as well fallback to transcoding if we could not direct play
        return self.buildTranscode(item, choice, obj)

    def getLyrics(self):
        return self.lyrics

    def hasLyrics(self):
        return False
        return self.lyrics.isAvailable()


class PlexPhotoPlayer(object):
    def __init__(self, item):
        self.item = item
        self.choice = item
        self.media = item.media()[0]
        self.metadata = None

    def build(self, item=None):
        item = item or self.item
        media = item.media()[0]
        if media.parts and media.parts[0]:
            obj = util.AttributeDict()

            part = media.parts[0]
            path = part.key or part.thumb
            server = item.getServer()

            obj.url = server.buildUrl(path, True)
            obj.enableBlur = server.supportsPhotoTranscoding

            util.DEBUG_LOG("Constructed photo item for playback: {0}",
                           lambda: util.cleanObjTokens(dict(obj)))

            self.metadata = obj

        return self.metadata
