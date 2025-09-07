from __future__ import absolute_import

import os

from kodi_six import xbmc
from kodi_six import xbmcgui
from plexnet import plexplayer, media, util as pnUtil, plexapp, plexlibrary

from lib import metadata
from lib import util
from lib.util import T
from . import busy
from . import dropdown
from . import info
from . import kodigui
from . import opener
from . import optionsdialog
from . import pagination
from . import playersettings
from . import search
from . import videoplayer
from . import windowutils
from .mixins.ratings import RatingsMixin
from .mixins.playbackbtn import PlaybackBtnMixin
from .mixins.thememusic import ThemeMusicMixin
from .mixins.watchlist import WatchlistUtilsMixin
from .mixins.roles import RolesMixin
from .mixins.common import CommonMixin

VIDEO_RELOAD_KW = dict(includeExtras=1, includeExtrasCount=10, includeChapters=1, includeReviews=1)


class RelatedPaginator(pagination.BaseRelatedPaginator):
    def getData(self, offset, amount):
        return self.parentWindow.video.getRelated(offset=offset, limit=amount)


class PrePlayWindow(kodigui.ControlledWindow, windowutils.UtilMixin, RatingsMixin, PlaybackBtnMixin, ThemeMusicMixin,
                    RolesMixin, CommonMixin, WatchlistUtilsMixin):
    xmlFile = 'script-plex-pre_play.xml'
    path = util.ADDON.getAddonInfo('path')
    theme = 'Main'
    res = '1080i'
    width = 1920
    height = 1080

    THUMB_POSTER_DIM = util.scaleResolution(347, 518)
    RELATED_DIM = util.scaleResolution(268, 402)
    EXTRA_DIM = util.scaleResolution(329, 185)
    ROLES_DIM = util.scaleResolution(334, 334)
    PREVIEW_DIM = util.scaleResolution(343, 193)

    ROLES_LIST_ID = 400
    REVIEWS_LIST_ID = 401
    EXTRA_LIST_ID = 402
    RELATED_LIST_ID = 403

    OPTIONS_GROUP_ID = 200
    PROGRESS_IMAGE_ID = 250

    HOME_BUTTON_ID = 201
    SEARCH_BUTTON_ID = 202

    MAIN_BUTTON_GROUP_ID = 300
    INFO_BUTTON_ID = 304
    PLAY_BUTTON_ID = 302
    TRAILER_BUTTON_ID = 303
    SETTINGS_BUTTON_ID = 305
    OPTIONS_BUTTON_ID = 306
    MEDIA_BUTTON_ID = 307

    POSSIBLE_PLAY_BUTTON_IDS = [302, 2302, 2303, 2304, 2305]

    PLAYER_STATUS_BUTTON_ID = 204

    def __init__(self, *args, **kwargs):
        kodigui.ControlledWindow.__init__(self, *args, **kwargs)
        PlaybackBtnMixin.__init__(self)
        WatchlistUtilsMixin.__init__(self)
        self.video = kwargs.get('video')
        self.parentList = kwargs.get('parent_list')
        self.fromWatchlist = kwargs.get('from_watchlist', False)
        self.isExternal = kwargs.get('external_item', False)
        self.directlyFromWatchlist = kwargs.get('directly_from_watchlist')
        self.is_watchlisted = kwargs.get('is_watchlisted', False)
        self.startOver = kwargs.get('start_over')
        self.videos = None
        self.exitCommand = None
        self.trailer = None
        self.lastFocusID = None
        self.lastNonOptionsFocusID = None
        self.initialized = False
        self.relatedPaginator = None
        self.openedWithAutoPlay = False
        self.needs_related_divider = False
        self.fromPlayback = False
        self.useBGM = False

    def doClose(self, **kw):
        self.relatedPaginator = None
        kodigui.ControlledWindow.doClose(self)

    def onFirstInit(self):
        self.extraListControl = kodigui.ManagedControlList(self, self.EXTRA_LIST_ID, 5)
        self.relatedListControl = kodigui.ManagedControlList(self, self.RELATED_LIST_ID, 5)
        self.rolesListControl = kodigui.ManagedControlList(self, self.ROLES_LIST_ID, 5)
        self.reviewsListControl = kodigui.ManagedControlList(self, self.REVIEWS_LIST_ID, 5)
        self.setBoolProperty("is_watchlisted", self.is_watchlisted)

        self.progressImageControl = self.getControl(self.PROGRESS_IMAGE_ID)
        self.setup()
        self.initialized = True

        if not util.getSetting("slow_connection") and not self.openedWithAutoPlay:
            self.themeMusicInit(self.video, locations=[os.path.dirname(s.part.file) for s in self.video.videoStreams])

    def doAutoPlay(self):
        # First reload the video to get all the other info
        self.video.reload(checkFiles=1, **VIDEO_RELOAD_KW)
        self.openedWithAutoPlay = True
        return self.playVideo(from_auto_play=True)

    @busy.dialog()
    def onReInit(self):
        PlaybackBtnMixin.onReInit(self)
        self.themeMusicReinit(self.video)
        self.initialized = False
        if util.getSetting("slow_connection"):
            self.progressImageControl.setWidth(1)
            self.setProperty('remainingTime', T(32914, "Loading"))
        self.video.reload(checkFiles=1, fromMediaChoice=self.video.mediaChoice is not None, **VIDEO_RELOAD_KW)
        removed_from_wl = False
        if self.fromPlayback:
            removed_from_wl = self.wl_auto_remove(self.video)
        self.fromPlayback = False
        self.refreshInfo(from_reinit=True)

        if not removed_from_wl:
            self.checkIsWatchlisted(self.video)
        self.initialized = True

    def refreshInfo(self, from_reinit=False):
        oldFocusId = self.getFocusId()

        util.setGlobalProperty('hide.resume', '' if self.video.viewOffset.asInt() else '1')
        # skip setting background when coming from reinit (other window) if we've focused something other than main
        self.setInfo(skip_bg=from_reinit and not (self.PLAY_BUTTON_ID <= oldFocusId <= self.MEDIA_BUTTON_ID))
        show_reviews = util.getSetting('show_reviews1')
        if show_reviews:
            if "watched" in show_reviews and "unwatched" not in show_reviews:
                self.fillReviews()

        self.fillRelated(self.needs_related_divider)
        xbmc.sleep(100)

        if oldFocusId == self.PLAY_BUTTON_ID:
            self.focusPlayButton()

    def onAction(self, action):
        try:
            controlID = self.getFocusId()

            if not controlID and self.lastFocusID and not action == xbmcgui.ACTION_MOUSE_MOVE:
                self.setFocusId(self.lastFocusID)

            if action == xbmcgui.ACTION_CONTEXT_MENU:
                if controlID == self.PLAY_BUTTON_ID:
                    self.playVideo(force_resume_menu=True)
                    return

                if not xbmc.getCondVisibility('ControlGroup({0}).HasFocus(0)'.format(self.OPTIONS_GROUP_ID)):
                    self.lastNonOptionsFocusID = self.lastFocusID
                    self.setFocusId(self.OPTIONS_GROUP_ID)
                    return
                else:
                    if self.lastNonOptionsFocusID:
                        self.setFocusId(self.lastNonOptionsFocusID)
                        self.lastNonOptionsFocusID = None
                        return

            elif action == xbmcgui.ACTION_NAV_BACK:
                if (not xbmc.getCondVisibility('ControlGroup({0}).HasFocus(0)'.format(
                        self.OPTIONS_GROUP_ID)) or not controlID) and \
                        not util.addonSettings.fastBack:
                    if self.getProperty('on.extras'):
                        self.setFocusId(self.OPTIONS_GROUP_ID)
                        return

            elif self.isWatchedAction(action) and xbmc.getCondVisibility('ControlGroup({}).HasFocus(0)'.format(self.MAIN_BUTTON_GROUP_ID)):
                self.toggleWatched(self.video)
                return

            elif action == xbmcgui.ACTION_LAST_PAGE and xbmc.getCondVisibility('ControlGroup({}).HasFocus(0)'.format(self.MAIN_BUTTON_GROUP_ID)):
                next(self)
            elif action == xbmcgui.ACTION_NEXT_ITEM:
                self.setFocusId(300)
                next(self)
            elif action == xbmcgui.ACTION_FIRST_PAGE and xbmc.getCondVisibility('ControlGroup({}).HasFocus(0)'.format(self.MAIN_BUTTON_GROUP_ID)):
                self.prev()
            elif action == xbmcgui.ACTION_PREV_ITEM:
                self.setFocusId(300)
                self.prev()

            elif action == xbmcgui.ACTION_MOVE_UP and controlID in (self.REVIEWS_LIST_ID,
                                                                    self.ROLES_LIST_ID,
                                                                    self.EXTRA_LIST_ID):
                self.updateBackgroundFrom(self.video)

            if controlID == self.RELATED_LIST_ID:
                if self.relatedPaginator.boundaryHit:
                    self.relatedPaginator.paginate()
                    return
                elif action in (xbmcgui.ACTION_MOVE_LEFT, xbmcgui.ACTION_MOVE_RIGHT):
                    self.updateBackgroundFrom(self.relatedListControl.getSelectedItem().dataSource)
        except:
            util.ERROR()

        kodigui.ControlledWindow.onAction(self, action)

    def onClick(self, controlID):
        if controlID == self.HOME_BUTTON_ID:
            self.goHome()
        elif controlID == self.EXTRA_LIST_ID:
            self.openItem(self.extraListControl)
        elif controlID == self.RELATED_LIST_ID:
            self.openItem(self.relatedListControl)
        elif controlID == self.ROLES_LIST_ID:
            if self.fromWatchlist:
                return
            if not self.roleClicked():
                return
        elif controlID == self.PLAY_BUTTON_ID:
            self.playVideo()
        elif controlID in self.WL_RELEVANT_BTNS and self.fromWatchlist and self.wl_availability:
            self.wl_item_opener(self.video, self.openItem)
        elif controlID in self.WL_BTN_STATE_BTNS:
            is_watchlisted = self.toggleWatchlist(self.video)
            self.waitAndSetFocus(self.WL_BTN_STATE_WATCHLISTED if is_watchlisted else self.WL_BTN_STATE_NOT_WATCHLISTED)
        elif controlID == self.PLAYER_STATUS_BUTTON_ID:
            self.showAudioPlayer()
        elif controlID == self.INFO_BUTTON_ID:
            self.infoButtonClicked()
        elif controlID == self.SETTINGS_BUTTON_ID:
            self.settingsButtonClicked()
        elif controlID == self.TRAILER_BUTTON_ID:
            self.openItem(item=self.trailer)
        elif controlID == self.OPTIONS_BUTTON_ID:
            self.optionsButtonClicked()
        elif controlID == self.MEDIA_BUTTON_ID:
            self.mediaButtonClicked()
        elif controlID == self.SEARCH_BUTTON_ID:
            self.searchButtonClicked()

    def onFocus(self, controlID):
        self.lastFocusID = controlID

        if 399 < controlID < 500:
            self.setProperty('hub.focus', str(controlID - 400))

            if controlID == self.RELATED_LIST_ID:
                self.updateBackgroundFrom(self.relatedListControl.getSelectedItem().dataSource)

        if xbmc.getCondVisibility('ControlGroup(50).HasFocus(0) + ControlGroup(300).HasFocus(0)'):
            self.setProperty('on.extras', '')
        elif xbmc.getCondVisibility('ControlGroup(50).HasFocus(0) + !ControlGroup(300).HasFocus(0)'):
            self.setProperty('on.extras', '1')

    def toggleWatched(self, item, state=None, **kw):
        watched = super(PrePlayWindow, self).toggleWatched(item, state=state, **kw)
        if watched is None:
            return

        if watched:
            self.wl_auto_remove(self.video)
            self.checkIsWatchlisted(self.video)
        self.refreshInfo()
        util.MONITOR.watchStatusChanged()

    def searchButtonClicked(self):
        self.processCommand(search.dialog(self, section_id=self.video.getLibrarySectionId() or None))

    def settingsButtonClicked(self):
        if not self.video.mediaChoice:
            playerObject = plexplayer.PlexPlayer(self.video)
            playerObject.build()
        playersettings.showDialog(video=self.video, non_playback=True)
        self.setAudioAndSubtitleInfo()

    def infoButtonClicked(self):
        opener.handleOpen(
            info.InfoWindow,
            title=self.video.defaultTitle,
            sub_title=self.getProperty('info'),
            thumb=self.video.type == 'episode' and self.video.thumb or self.video.defaultThumb,
            thumb_fallback='script.plex/thumb_fallbacks/{0}.png'.format(self.video.type == 'episode' and 'show' or 'movie'),
            info=self.video.summary,
            background=self.getProperty('background'),
            is_16x9=self.video.type == 'episode',
            video=self.video
        )

    def optionsButtonClicked(self):
        options = []

        inProgress = self.video.viewOffset.asInt()
        if not self.video.isWatched or inProgress:
            options.append({'key': 'mark_watched', 'display': T(32319, 'Mark Played')})
        if self.video.isWatched or inProgress:
            options.append({'key': 'mark_unwatched', 'display': T(32318, 'Mark Unplayed')})

        options.append(dropdown.SEPARATOR)

        if self.video.type == 'episode':
            options.append({'key': 'to_season', 'display': T(32400, 'Go to Season')})
            options.append({'key': 'to_show', 'display': T(32323, 'Go to Show')})

        if self.video.type in ('episode', 'movie'):
            options.append({'key': 'to_section', 'display': T(32324, u'Go to {0}').format(self.video.getLibrarySectionTitle())})

        if plexapp.ACCOUNT.isAdmin:
            options.append(dropdown.SEPARATOR)
            options.append({'key': 'refresh', 'display': T(33719, 'Refresh metadata')})

            if self.video.server.allowsMediaDeletion:
                options.append({'key': 'delete', 'display': T(32322, 'Delete')})

        if 'items' in util.getSetting('cache_requests'):
            options.append({'key': 'cache_reset', 'display': T(33728, "Clear cache for item")})
        # if xbmc.getCondVisibility('Player.HasAudio') and self.section.TYPE == 'artist':
        #     options.append({'key': 'add_to_queue', 'display': 'Add To Queue'})

        # if False:
        #     options.append({'key': 'add_to_playlist', 'display': 'Add To Playlist'})
        posy = 880
        if not util.getGlobalProperty('hide.resume'):
            posy += 106
        if self.getProperty('trailer.button'):
            posy += 106
        choice = dropdown.showDropdown(options, (posy, 618), close_direction='left')
        if not choice:
            return

        if choice['key'] == 'play_next':
            xbmc.executebuiltin('PlayerControl(Next)')
        elif choice['key'] == 'mark_watched':
            self.toggleWatched(self.video, state=True, **VIDEO_RELOAD_KW)
        elif choice['key'] == 'mark_unwatched':
            self.toggleWatched(self.video, state=False, **VIDEO_RELOAD_KW)
        elif choice['key'] == 'to_season':
            self.processCommand(opener.open(self.video.parentRatingKey))
        elif choice['key'] == 'to_show':
            self.processCommand(opener.open(self.video.grandparentRatingKey))
        elif choice['key'] == 'to_section':
            self.cameFrom = "library"
            section = plexlibrary.LibrarySection.fromFilter(self.video)
            self.processCommand(opener.sectionClicked(section,
                                                      came_from=self.video.ratingKey)
                                )
        elif choice['key'] == 'delete':
            self.delete()
        elif choice['key'] == 'refresh':
            self.video.refresh()
            self.refreshInfo()
        elif choice["key"] == "cache_reset":
            try:
                util.DEBUG_LOG('Clearing requests cache for {}...', self.video)
                self.video.clearCache()
                self.refreshInfo()
            except Exception as e:
                util.DEBUG_LOG("Couldn't clear cache: {}", e)

    def mediaButtonClicked(self):
        options = []
        for media in self.video.media:
            ind = ''
            if self.video.mediaChoice and media.id == self.video.mediaChoice.media.id:
                ind = 'script.plex/home/device/check.png'
            options.append({'key': media, 'display': media.versionString(), 'indicator': ind})
        choice = dropdown.showDropdown(options, header=T(32450, 'Choose Version'), with_indicator=True)
        if not choice:
            return False

        for media in self.video.media:
            media.set('selected', '')

        self.video.setMediaChoice(choice['key'])
        choice['key'].set('selected', 1)
        pnUtil.INTERFACE.playbackManager(self.video, key="media_version", value=choice['key'].id)
        self.setInfo()

    def delete(self):
        button = optionsdialog.show(
            T(32326, 'Really delete?'),
            T(33035, "Delete {}: {}?").format(type(self.video).__name__, self.video.defaultTitle),
            T(32328, 'Yes'),
            T(32329, 'No')
        )

        if button != 0:
            return

        if self._delete():
            self.doClose()
        else:
            util.messageDialog(T(32330, 'Message'), T(32331, 'There was a problem while attempting to delete the media.'))

    @busy.dialog()
    def _delete(self):
        success = self.video.delete()
        util.LOG('Media DELETE: {0} - {1}', self.video, success and 'SUCCESS' or 'FAILED')
        return success

    def getVideos(self):
        if not self.videos:
            if self.video.TYPE == 'episode':
                self.videos = self.video.show().episodes()

        if not self.videos:
            return False

        return True

    def next(self):
        if not self._next():
            return
        self.setup()

    __next__ = next

    @busy.dialog()
    def _next(self):
        if self.parentList:
            mli = self.parentList.getListItemByDataSource(self.video)
            if not mli:
                return False

            pos = mli.pos() + 1
            if not self.parentList.positionIsValid(pos):
                pos = 0

            self.video = self.parentList.getListItem(pos).dataSource
        else:
            if not self.getVideos():
                return False

            if self.video not in self.videos:
                return False

            pos = self.videos.index(self.video)
            pos += 1
            if pos >= len(self.videos):
                pos = 0

            self.video = self.videos[pos]

        return True

    def prev(self):
        if not self._prev():
            return
        self.setup()

    @busy.dialog()
    def _prev(self):
        if self.parentList:
            mli = self.parentList.getListItemByDataSource(self.video)
            if not mli:
                return False

            pos = mli.pos() - 1
            if pos < 0:
                pos = self.parentList.size() - 1

            self.video = self.parentList.getListItem(pos).dataSource
        else:
            if not self.getVideos():
                return False

            if self.video not in self.videos:
                return False

            pos = self.videos.index(self.video)
            pos -= 1
            if pos < 0:
                pos = len(self.videos) - 1

            self.video = self.videos[pos]

        return True

    def playVideo(self, from_auto_play=False, force_resume_menu=False):
        if self.playBtnClicked:
            return

        if not self.video.available():
            util.messageDialog(T(32312, 'Unavailable'), T(32313, 'This item is currently unavailable.'))
            return

        resume = False
        if self.video.viewOffset.asInt() and not self.startOver:
            if not util.getSetting('assume_resume') or force_resume_menu:
                choice = dropdown.showDropdown(
                    options=[
                        {'key': 'resume', 'display': T(32429, 'Resume from {0}').format(util.timeDisplay(self.video.viewOffset.asInt()).lstrip('0').lstrip(':'))},
                        {'key': 'play', 'display': T(32317, 'Play from beginning')}
                    ],
                    pos=(660, 441),
                    close_direction='none',
                    set_dropdown_prop=False,
                    header=T(32314, 'In Progress'),
                    dialog_props=from_auto_play and self.dialogProps or None
                )

                if not choice:
                    return

                if choice['key'] == 'resume':
                    resume = True
            else:
                resume = True

        if not from_auto_play:
            self.playBtnClicked = True

        self.fromPlayback = True
        self.processCommand(videoplayer.play(video=self.video, resume=resume, bgm=self.useBGM))
        return True

    def openItem(self, control=None, item=None, inherit_from_watchlist=True, server=None, is_watchlisted=False, **kw):
        if not item:
            mli = control.getSelectedItem()
            if not mli:
                return
            item = mli.dataSource

        self.processCommand(opener.open(item, from_watchlist=self.fromWatchlist if inherit_from_watchlist else False,
                                        server=server, is_watchlisted=is_watchlisted, **kw))

    def focusPlayButton(self, extended=False):
        if extended:
            self.setFocusId(self.wl_play_button_id)
            return
        try:
            if not self.getFocusId() == self.PLAY_BUTTON_ID:
                self.setFocusId(self.PLAY_BUTTON_ID)
        except (SystemError, RuntimeError):
            self.setFocusId(self.PLAY_BUTTON_ID)

    @busy.dialog()
    def setup(self):
        self.focusPlayButton()
        self.watchlist_setup(self.video)

        util.DEBUG_LOG('PrePlay: Showing video info: {0}', self.video)
        if self.video.type == 'episode':
            self.setProperty('preview.yes', '1')
        elif self.video.type == 'movie':
            self.setProperty('preview.no', '1')

        if self.isExternal:
            # fixme, multiple? choice?
            self.video.related_source = "more-from-credits"
        self.video.reload(checkFiles=1, **VIDEO_RELOAD_KW)
        try:
            self.relatedPaginator = RelatedPaginator(self.relatedListControl, leaf_count=int(self.video.relatedCount),
                                                     parent_window=self)
        except ValueError:
            raise util.NoDataException

        if self.fromWatchlist:
            self.watchlistItemAvailable(self.video, shortcut_watchlisted=self.directlyFromWatchlist)
        if not self.directlyFromWatchlist:
            self.checkIsWatchlisted(self.video)

        self.setInfo()
        self.setBoolProperty("initialized", True)
        hasRoles = self.fillRoles()
        hasReviews = self.fillReviews()
        hasExtras = self.fillExtras()
        self.needs_related_divider = hasRoles and not hasExtras and not hasReviews
        self.fillRelated(self.needs_related_divider)

    def setInfo(self, skip_bg=False):
        if not skip_bg:
            self.updateBackgroundFrom(self.video)
        self.setProperty('title', self.video.title)
        self.setProperty('duration', self.video.duration and util.durationToText(self.video.duration.asInt()))
        self.setProperty('summary', self.video.summary.strip().replace('\t', ' '))
        self.setProperty('unwatched', not self.video.isWatched and '1' or '')
        self.setBoolProperty('watched', self.video.isFullyWatched)
        self.setBoolProperty('disable_playback', self.fromWatchlist)

        directors = u' / '.join([d.tag for d in self.video.directors()][:3])
        directorsLabel = len(self.video.directors) > 1 and T(32401, u'DIRECTORS').upper() or T(32383, u'DIRECTOR').upper()
        self.setProperty('directors', directors and u'{0}    {1}'.format(directorsLabel, directors) or '')
        writers = u' / '.join([r.tag for r in self.video.writers()][:3])
        writersLabel = len(self.video.writers) > 1 and T(32403, u'WRITERS').upper() or T(32402, u'WRITER').upper()
        self.setProperty('writers',
                         writers and u'{0}{1}    {2}'.format(directors and '    ' or '', writersLabel, writers) or '')

        # fixme: can this ever happen?
        if self.video.type == 'episode':
            self.setProperty('content.rating', '')
            self.setProperty('thumb', self.video.defaultThumb.asTranscodedImageURL(*self.THUMB_POSTER_DIM))
            self.setProperty('preview', self.video.thumb.asTranscodedImageURL(*self.PREVIEW_DIM))
            self.setProperty('info', u'{0} {1}'.format(T(32303, 'Season').format(self.video.parentIndex), T(32304, 'Episode').format(self.video.index)))
            self.setProperty('date', util.cleanLeadingZeros(self.video.originallyAvailableAt.asDatetime('%B %d, %Y')))
            self.setProperty('related.header', T(32306, 'Related Shows'))
        elif self.video.type == 'movie':
            self.setProperty('title', self.video.defaultTitle)
            self.setProperty('preview', '')
            self.setProperty('thumb', self.video.thumb.asTranscodedImageURL(*self.THUMB_POSTER_DIM))
            genres = u' / '.join([g.tag for g in self.video.genres()][:3])
            self.setProperty('info', genres)
            self.setProperty('date', self.video.year)
            if self.fromWatchlist and not self.wl_availability:
                self.setProperty('wl_server_availability_verbose', util.cleanLeadingZeros(self.video.originallyAvailableAt.asDatetime('%B %d, %Y')))
            self.setProperty('content.rating', self.video.contentRating.split('/', 1)[-1])

            cast = u' / '.join([r.tag for r in self.video.roles()][:5])
            castLabel = 'CAST'
            self.setProperty('cast', cast and u'{0}    {1}'.format(castLabel, cast) or '')
            self.setProperty('related.header', T(32404, 'Related Movies') if not self.fromWatchlist else T(34018, 'Related Media'))

        if self.fromWatchlist:
            self.setProperty('studios', u' / '.join([r.tag for r in self.video.studios()][:2]))
        self.setProperty('video.res', self.video.resolutionString())
        self.setProperty('audio.codec', self.video.audioCodecString())
        self.setProperty('video.codec', self.video.videoCodecString())
        self.setProperty('video.rendering', self.video.videoCodecRendering)
        self.setProperty('audio.channels', self.video.audioChannelsString(metadata.apiTranslate))
        self.setBoolProperty('media.multiple', len(list(filter(lambda x: x.isAccessible(), self.video.media()))) > 1)

        self.populateRatings(self.video, self)

        if not self.fromWatchlist:
            self.setAudioAndSubtitleInfo()

            self.setProperty('unavailable', all(not v.isAccessible() for v in self.video.media()) and '1' or '')

            if self.video.viewOffset.asInt():
                width = self.video.viewOffset.asInt() and (1 + int((self.video.viewOffset.asInt() / self.video.duration.asFloat()) * self.width)) or 1
                self.progressImageControl.setWidth(width)
            else:
                self.progressImageControl.setWidth(1)

            if self.video.viewOffset.asInt():
                self.setProperty('remainingTime', T(33615, "{time} left").format(time=self.video.remainingTimeString))
            else:
                self.setProperty('remainingTime', '')

    def setAudioAndSubtitleInfo(self):
        sas = self.video.selectedAudioStream()

        if sas:
            if len(self.video.audioStreams) > 1:
                self.setProperty(
                    'audio', sas and u'{0} \u2022 {1} {2}'.format(sas.getTitle(metadata.apiTranslate),
                                                                  len(self.video.audioStreams) - 1, T(32307, 'More'))
                    or T(32309, 'None')
                )
            else:
                self.setProperty('audio', sas and sas.getTitle(metadata.apiTranslate) or T(32309, 'None'))

        sss = self.video.selectedSubtitleStream(
            forced_subtitles_override=util.getSetting("forced_subtitles_override") and pnUtil.ACCOUNT.subtitlesForced == 0,
            deselect_subtitles=util.getSetting("disable_subtitle_languages"))
        if sss:
            if len(self.video.subtitleStreams) > 1:
                self.setProperty(
                    'subtitles', u'{0} \u2022 {1} {2}'.format(sss.getTitle(metadata.apiTranslate), len(self.video.subtitleStreams) - 1, T(32307, 'More'))
                )
            else:
                self.setProperty('subtitles', sss.getTitle(metadata.apiTranslate))
        else:
            if self.video.subtitleStreams:
                self.setProperty('subtitles', u'{0} \u2022 {1} {2}'.format(T(32309, 'None'), len(self.video.subtitleStreams), T(32308, 'Available')))
            else:
                self.setProperty('subtitles', T(32309, u'None'))

    def createListItem(self, obj):
        mli = kodigui.ManagedListItem(obj.title or '', thumbnailImage=obj.thumb.asTranscodedImageURL(*self.EXTRA_DIM), data_source=obj)
        return mli

    def fillExtras(self, has_prev=False):
        items = []
        idx = 0

        if not self.video.extras:
            if self.fromWatchlist:
                self.video.fetchExternalExtras()

            if not self.video.extras:
                self.extraListControl.reset()
                return False

        for extra in self.video.extras:
            if not self.trailer and extra.extraType.asInt() == media.METADATA_RELATED_TRAILER:
                self.trailer = extra
                self.setProperty('trailer.button', '1')
                continue

            mli = self.createListItem(extra)
            if mli:
                mli.setProperty('index', str(idx))
                mli.setProperty(
                    'thumb.fallback', 'script.plex/thumb_fallbacks/{0}.png'.format(extra.type in ('show', 'season', 'episode') and 'show' or 'movie')
                )
                mli.setProperty('extra.duration', extra.duration and util.simplifiedTimeDisplay(extra.duration.asInt()))
                items.append(mli)
                idx += 1

        if not items:
            return False

        self.extraListControl.reset()
        self.extraListControl.addItems(items)

        return True

    def fillRelated(self, has_prev=False):
        if not self.relatedPaginator.leafCount:
            self.relatedListControl.reset()
            return False

        items = self.relatedPaginator.paginate()

        if not items:
            return False

        return True

    def fillRoles(self, has_prev=False):
        items = []
        idx = 0

        if not self.video.roles:
            self.rolesListControl.reset()
            return False

        for role in self.video.combined_roles:
            mli = kodigui.ManagedListItem(role.tag, role.role or util.TRANSLATED_ROLES[role.translated_role],
                                          thumbnailImage=role.thumb.asTranscodedImageURL(*self.ROLES_DIM),
                                          data_source=role)
            mli.setProperty('index', str(idx))
            items.append(mli)
            idx += 1

        if not items:
            return False

        self.rolesListControl.reset()
        self.rolesListControl.addItems(items)
        return True

    def fillReviews(self, has_prev=False):
        items = []
        idx = 0

        show_reviews = util.getSetting('show_reviews1')
        fully_watched = self.video.isFullyWatched

        if (not show_reviews or not self.video.reviews or
                ("unwatched" not in show_reviews and not fully_watched) or
                ("watched" not in show_reviews and fully_watched)):
            self.reviewsListControl.reset()
            return False

        for review in self.video.reviews():
            mli = kodigui.ManagedListItem(review.source, review.tag, thumbnailImage=review.ratingImage())
            mli.setProperty('index', str(idx))
            mli.setProperty('text', review.text)
            items.append(mli)
            idx += 1

        if not items:
            return False

        self.reviewsListControl.reset()
        self.reviewsListControl.addItems(items)
        return True

class PrePlayWindowWL(PrePlayWindow):
    xmlFile = 'script-plex-pre_play-wl.xml'
