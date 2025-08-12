from __future__ import absolute_import

import os
import datetime

from plexnet.video import Episode, Movie, Clip

from lib import util
from . import kodigui
from . import windowutils


def split2len(s, n):
    def _f(s, n):
        while s:
            yield s[:n]
            s = s[n:]
    return list(_f(s, n))


class InfoWindow(kodigui.ControlledWindow, windowutils.UtilMixin):
    xmlFile = 'script-plex-info.xml'
    path = util.ADDON.getAddonInfo('path')
    theme = 'Main'
    res = '1080i'
    width = 1920
    height = 1080

    PLAYER_STATUS_BUTTON_ID = 204

    THUMB_DIM_POSTER = util.scaleResolution(519, 469)
    THUMB_DIM_SQUARE = util.scaleResolution(519, 519)

    def __init__(self, *args, **kwargs):
        kodigui.ControlledWindow.__init__(self, *args, **kwargs)
        self.title = kwargs.get('title')
        self.subTitle = kwargs.get('sub_title')
        self.thumb = kwargs.get('thumb')
        self.thumb_opts = kwargs.get('thumb_opts', {})
        self.thumbFallback = kwargs.get('thumb_fallback')
        self.info = kwargs.get('info')
        self.background = kwargs.get('background')
        self.isSquare = kwargs.get('is_square')
        self.is16x9 = kwargs.get('is_16x9')
        self.isPoster = not (self.isSquare or self.is16x9)
        self.thumbDim = self.isSquare and self.THUMB_DIM_SQUARE or self.THUMB_DIM_POSTER
        self.video = kwargs.get('video')

    def getVideoInfo(self):
        """
        Append media/part/stream info to summary
        """
        if not isinstance(self.video, (Episode, Movie, Clip)):
            return self.info

        summary = [self.info]
        medias = self.video.media()
        if not medias:
            return self.info

        mediaCount = len(medias)
        onlyOneMedia = mediaCount == 1
        partCount = sum(len(m.parts) for m in medias)
        pcInfo = []
        if not onlyOneMedia:
            pcInfo.append("Files: {}".format(mediaCount))
        if partCount > 1:
            pcInfo.append("Parts: {}".format(partCount))
        pcInfoStr = ", ".join(pcInfo)

        addMedia = ["\n\n\n\nMedia{}\n".format(" ({})".format(pcInfoStr) if pcInfoStr else "")]
        for media_ in medias:
            if not media_.isAccessible():
                addMedia.append("Unavailable: {}\n\n".format(", ".join(os.path.basename(pf.file) for pf in media_.parts)))
                continue

            for part in media_.parts:
                if not part:
                    addMedia.append("Unavailable: {}".format(os.path.basename(part.file)))
                    continue

                pmFolder = part.getPathMappedUrl(return_only_folder=True)
                addMedia.append("File: ")
                splitFnAt = 74
                fnLen = len(os.path.basename(part.file))
                appended = False
                for s in split2len(os.path.basename(part.file), splitFnAt):
                    if fnLen > splitFnAt and not appended:
                        addMedia.append("{}\n".format(s))
                        appended = True
                        continue
                    addMedia.append("{}\n".format(s))
                if pmFolder:
                    addMedia.append("Mapped via: {}\n".format(pmFolder))
                addMedia.append("Added: {}\n".format(datetime.datetime.fromtimestamp(
                    self.video.addedAt.asFloat()).strftime("{} {}".format(util.shortDF, util.timeFormat))))
                addMedia.append("Duration: {}, Size: {}\n".format(util.durationToShortText(int(part.duration)),
                                                                  util.simpleSize(int(part.size))))

                subs = []
                subsOver = 0
                for stream in part.streams:
                    streamtype = stream.streamType.asInt()
                    # video
                    if streamtype == 1:
                        dovi = ""
                        if stream.DOVIPresent:
                            dovi = "Level: {}, Profile: {}, Version: {}, " \
                                   "BL: {}{}, EL: {}, RPU: {}".format(stream.DOVILevel,
                                                                      stream.DOVIProfile,
                                                                      stream.DOVIVersion,
                                                                      stream.DOVIBLPresent,
                                                                      stream.DOVIBLPresent and
                                                                      " (compat ID: {})".format(stream.DOVIBLCompatID)
                                                                      or "",
                                                                      stream.DOVIELPresent,
                                                                      stream.DOVIRPUPresent)
                        addMedia.append("Video: {}x{}, {} {}/{}bit/{}/{}@{} kBit, {} fps{}\n".format(
                            stream.width, stream.height, stream.videoCodecRendering, stream.codec.upper(),
                            stream.bitDepth, stream.chromaSubsampling, stream.colorPrimaries, stream.bitrate,
                            stream.frameRate, dovi and "\nDoVi: {}\n".format(dovi) or ""))
                    # audio
                    elif streamtype == 2:
                        addMedia.append("Audio: {}{}, {}/{}ch@{} kBit, {} Hz\n".format(
                            stream.language,
                            " (default)" if stream.default else "",
                            stream.codec.upper(),
                            stream.channels, stream.bitrate,
                            stream.samplingRate))
                    # subtitle
                    elif streamtype == 3:
                        if len(subs) > 4:
                            subsOver += 1
                            continue
                        subs.append("{} ({})".format(stream.language, stream.codec.upper()))

                if subs:
                    addMedia.append("Subtitles: {}{}\n".format(", ".join(subs),
                                                               subsOver and " (+{})".format(subsOver) or ''))
            if not onlyOneMedia:
                addMedia.append("--------------\n")

        chapters = []
        chOver = 0
        for index, chapter in enumerate(self.video.chapters):
            if len(chapters) > 4:
                chOver += 1
                continue
            chapters.append(chapter.tag or "Chapter #{}".format(str(index+1)))

        if chapters:
            addMedia.append("Chapters: {}{}\n".format(", ".join(chapters), chOver and " (+{})".format(chOver) or ''))

        if self.video.markers:
            addMedia.append("Markers: {}".format(", ".join(name for off, name in sorted(
                (int(marker.startTimeOffset), marker.type) for marker in self.video.markers))))

        return "".join(summary + addMedia)

    def onFirstInit(self):
        self.setProperty('is.poster', self.isPoster and '1' or '')
        self.setProperty('is.square', self.isSquare and '1' or '')
        self.setProperty('is.16x9', self.is16x9 and '1' or '')
        self.setProperty('title.main', self.title)
        self.setProperty('title.sub', self.subTitle)
        self.setProperty('thumb.fallback', self.thumbFallback)
        self.setProperty('thumb', self.thumb.asTranscodedImageURL(*self.thumbDim, **self.thumb_opts))
        self.setProperty('info', self.getVideoInfo())
        self.setProperty('background', self.background)

    def onClick(self, controlID):
        if controlID == self.PLAYER_STATUS_BUTTON_ID:
            self.showAudioPlayer()
