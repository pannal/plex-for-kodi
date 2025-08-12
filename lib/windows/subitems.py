from __future__ import absolute_import

import gc

from kodi_six import xbmc
from kodi_six import xbmcgui
from plexnet import playlist, util as pnUtil, plexapp

from lib import metadata
from lib import util
from lib.util import T
from . import busy
from . import dropdown
from . import episodes
from . import info
from . import kodigui
from . import musicplayer
from . import opener
from . import pagination
from . import playbacksettings
from . import search
from . import tracks
from . import videoplayer
from . import windowutils
from .mixins import SeasonsMixin, DeleteMediaMixin, RatingsMixin, PlaybackBtnMixin, WatchlistUtilsMixin, ThemeMusicMixin


class RelatedPaginator(pagination.BaseRelatedPaginator):
    def getData(self, offset, amount):
        return self.parentWindow.mediaItem.getRelated(offset=offset, limit=amount)


class ShowWindow(kodigui.ControlledWindow, windowutils.UtilMixin, SeasonsMixin, DeleteMediaMixin, RatingsMixin,
                 PlaybackBtnMixin, WatchlistUtilsMixin, ThemeMusicMixin, playbacksettings.PlaybackSettingsMixin):
    xmlFile = 'script-plex-seasons.xml'
    path = util.ADDON.getAddonInfo('path')
    theme = 'Main'
    res = '1080i'
    width = 1920
    height = 1080

    EXTRA_DIM = util.scaleResolution(329, 185)
    RELATED_DIM = util.scaleResolution(268, 402)
    ROLES_DIM = util.scaleResolution(334, 334)

    SUB_ITEM_LIST_ID = 400

    ROLES_LIST_ID = 401
    EXTRA_LIST_ID = 402
    RELATED_LIST_ID = 403

    OPTIONS_GROUP_ID = 200

    HOME_BUTTON_ID = 201
    SEARCH_BUTTON_ID = 202
    PLAYER_STATUS_BUTTON_ID = 204

    PROGRESS_IMAGE_ID = 250

    INFO_BUTTON_ID = 301
    PLAY_BUTTON_ID = 302
    SHUFFLE_BUTTON_ID = 303
    OPTIONS_BUTTON_ID = 304

    def __init__(self, *args, **kwargs):
        kodigui.ControlledWindow.__init__(self, *args, **kwargs)
        SeasonsMixin.__init__(*args, **kwargs)
        DeleteMediaMixin.__init__(*args, **kwargs)
        PlaybackBtnMixin.__init__(self, *args, **kwargs)
        WatchlistUtilsMixin.__init__(self)
        ThemeMusicMixin.__init__(self)
        self.mediaItem = kwargs.get('media_item')
        self.parentList = kwargs.get('parent_list')
        self.cameFrom = kwargs.get('came_from')
        self.fromWatchlist = kwargs.get('from_watchlist', False)
        self.isExternal = kwargs.get('external_item', False)
        self.directlyFromWatchlist = kwargs.get('directly_from_watchlist')
        self.is_watchlisted = kwargs.get('is_watchlisted')
        self.mediaItems = None
        self.exitCommand = None
        self.lastFocusID = None
        self.lastNonOptionsFocusID = None
        self.manuallySelectedSeason = False
        self.initialized = False
        self.relatedPaginator = None

    def doClose(self):
        self.relatedPaginator = None
        kodigui.ControlledWindow.doClose(self)

    def onFirstInit(self):
        self.focusPlayButton()
        self.subItemListControl = kodigui.ManagedControlList(self, self.SUB_ITEM_LIST_ID, 5)
        self.rolesListControl = kodigui.ManagedControlList(self, self.ROLES_LIST_ID, 5)
        self.extraListControl = kodigui.ManagedControlList(self, self.EXTRA_LIST_ID, 5)
        self.relatedListControl = kodigui.ManagedControlList(self, self.RELATED_LIST_ID, 5)

        self.progressImageControl = self.getControl(self.PROGRESS_IMAGE_ID)

        self.setup()
        self.initialized = True
        self.themeMusicInit(self.mediaItem)

    def onReInit(self):
        PlaybackBtnMixin.onReInit(self)
        self.wl_auto_remove(self.mediaItem)
        self.checkIsWatchlisted(self.mediaItem)
        self.themeMusicReinit(self.mediaItem)

    def setup(self):
        if self.isExternal:
            # fixme, multiple? choice?
            self.mediaItem.related_source = "more-from-credits"
        self.mediaItem.reload(includeExtras=1, includeExtrasCount=10, includeOnDeck=1)
        self.relatedPaginator = RelatedPaginator(self.relatedListControl, leaf_count=int(self.mediaItem.relatedCount),
                                                 parent_window=self)

        self.watchlist_setup(self.mediaItem)
        if self.fromWatchlist:
            self.watchlistItemAvailable(self.mediaItem, shortcut_watchlisted=self.directlyFromWatchlist)
        if not self.directlyFromWatchlist:
            self.checkIsWatchlisted(self.mediaItem)

        self.updateProperties()
        self.setBoolProperty("initialized", True)
        self.fill()
        hasPrev = self.fillExtras()
        hasPrev = self.fillRelated(hasPrev)
        self.fillRoles(hasPrev)

    def updateProperties(self):
        self.setProperty('title', self.mediaItem.title)
        self.setProperty('summary', self.mediaItem.summary)
        self.setProperty('thumb', self.mediaItem.defaultThumb.asTranscodedImageURL(*self.THUMB_DIMS[self.mediaItem.type]['main.thumb']))
        self.updateBackgroundFrom(self.mediaItem)
        self.setProperty('duration', util.durationToText(self.mediaItem.fixedDuration()))
        self.setProperty('info', '')
        self.setProperty('date', self.mediaItem.year)
        self.setBoolProperty('disable_playback', self.fromWatchlist)
        if not self.mediaItem.isWatched:
            self.setProperty('unwatched.count', str(self.mediaItem.unViewedLeafCount) or '')
            self.setBoolProperty('unwatched.count.large', self.mediaItem.unViewedLeafCount > 999)
        else:
            self.setBoolProperty('watched', self.mediaItem.isWatched)

        self.setProperty('extras.header', T(32305, 'Extras'))
        self.setProperty('related.header', T(32306, 'Related Shows') if not self.fromWatchlist else T(34018, 'Related Media'))

        if self.mediaItem.creator:
            self.setProperty('directors', u'{0}    {1}'.format(T(32418, 'Creator').upper(), self.mediaItem.creator))
        elif self.mediaItem.studio:
            self.setProperty('directors', u'{0}    {1}'.format(T(32386, 'Studio').upper(), self.mediaItem.studio))

        cast = self.mediaItem.roles and u' / '.join([r.tag for r in self.mediaItem.roles()][:5]) or ''
        castLabel = T(32419, 'Cast').upper()
        self.setProperty('writers', cast and u'{0}    {1}'.format(castLabel, cast) or '')

        genres = self.mediaItem.genres()
        self.setProperty('info', genres and (u' / '.join([g.tag for g in genres][:3])) or '')

        if self.fromWatchlist and not self.wl_availability:
            self.setProperty('wl_server_availability_verbose',
                             util.cleanLeadingZeros(self.mediaItem.originallyAvailableAt.asDatetime('%B %d, %Y')))

        self.populateRatings(self.mediaItem, self)

        sas = self.mediaItem.selectedAudioStream()
        self.setProperty('audio', sas and sas.getTitle() or 'None')

        sss = self.mediaItem.selectedSubtitleStream(
            forced_subtitles_override=util.getSetting("forced_subtitles_override") and pnUtil.ACCOUNT.subtitlesForced == 0,
            deselect_subtitles=util.getSetting("disable_subtitle_languages"))
        self.setProperty('subtitles', sss and sss.getTitle() or 'None')

        leafcount = self.mediaItem.leafCount.asFloat()
        if leafcount:
            wBase = self.mediaItem.viewedLeafCount.asInt() / leafcount
            for v in self.mediaItem.onDeck:
                if v.viewOffset:
                    wBase += v.viewOffset.asInt() / v.duration.asFloat() / leafcount

            # if we have _any_ progress, display it as the smallest step
            wBase = 0 < wBase < 0.01 and 0.01 or wBase
            width = (int(wBase * self.width)) or 1
            self.progressImageControl.setWidth(width)

    def focusPlayButton(self, extended=False):
        if extended:
            self.setFocusId(self.wl_play_button_id)
            return
        try:
            if not self.getFocusId() == self.PLAY_BUTTON_ID:
                self.setFocusId(self.PLAY_BUTTON_ID)
        except (SystemError, RuntimeError):
            self.setFocusId(self.PLAY_BUTTON_ID)

    def onAction(self, action):
        try:
            controlID = self.getFocusId()

            if not controlID and self.lastFocusID and not action == xbmcgui.ACTION_MOUSE_MOVE:
                self.setFocusId(self.lastFocusID)

            if controlID == self.SUB_ITEM_LIST_ID and action in (xbmcgui.ACTION_MOVE_LEFT, xbmcgui.ACTION_MOVE_RIGHT):
                self.manuallySelectedSeason = True

            elif action == xbmcgui.ACTION_CONTEXT_MENU:
                if controlID == self.SUB_ITEM_LIST_ID:
                    self.optionsButtonClicked(from_item=True)
                    return
                elif not xbmc.getCondVisibility('ControlGroup({0}).HasFocus(0)'.format(self.OPTIONS_GROUP_ID)):
                    self.lastNonOptionsFocusID = self.lastFocusID
                    self.setFocusId(self.OPTIONS_GROUP_ID)
                    return
                else:
                    if self.lastNonOptionsFocusID:
                        self.setFocusId(self.lastNonOptionsFocusID)
                        self.lastNonOptionsFocusID = None
                        return

            elif action in (xbmcgui.ACTION_NAV_BACK, xbmcgui.ACTION_CONTEXT_MENU):
                if not xbmc.getCondVisibility('ControlGroup({0}).HasFocus(0)'.format(
                        self.OPTIONS_GROUP_ID)) and \
                        (not util.addonSettings.fastBack or action == xbmcgui.ACTION_CONTEXT_MENU):
                    if self.getProperty('on.extras'):
                        self.setFocusId(self.OPTIONS_GROUP_ID)
                        return

            if action == xbmcgui.ACTION_LAST_PAGE and xbmc.getCondVisibility('ControlGroup(300).HasFocus(0)'):
                next(self)
            elif action == xbmcgui.ACTION_NEXT_ITEM:
                self.setFocusId(300)
                next(self)
            elif action == xbmcgui.ACTION_FIRST_PAGE and xbmc.getCondVisibility('ControlGroup(300).HasFocus(0)'):
                self.prev()
            elif action == xbmcgui.ACTION_PREV_ITEM:
                self.setFocusId(300)
                self.prev()

            if action == xbmcgui.ACTION_MOVE_UP and (controlID == self.SUB_ITEM_LIST_ID or
                    self.INFO_BUTTON_ID <= controlID <= self.OPTIONS_BUTTON_ID):
                self.updateBackgroundFrom(self.mediaItem)

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
        elif controlID == self.SUB_ITEM_LIST_ID:
            if not self.fromWatchlist:
                self.subItemListClicked()
        elif controlID == self.PLAYER_STATUS_BUTTON_ID:
            self.showAudioPlayer()
        elif controlID == self.EXTRA_LIST_ID:
            self.openItem(self.extraListControl)
        elif controlID == self.RELATED_LIST_ID:
            self.openItem(self.relatedListControl)
        elif controlID == self.ROLES_LIST_ID:
            if not self.fromWatchlist:
                self.roleClicked()
        elif controlID == self.INFO_BUTTON_ID:
            self.infoButtonClicked()
        elif controlID == self.PLAY_BUTTON_ID:
            self.playButtonClicked()
        elif controlID in self.WL_RELEVANT_BTNS and self.fromWatchlist and self.wl_availability:
            self.wl_item_opener(self.mediaItem, self.openItem)
        elif controlID in self.WL_BTN_STATE_BTNS:
            is_watchlisted = self.toggleWatchlist(self.mediaItem)
            self.waitAndSetFocus(self.WL_BTN_STATE_WATCHLISTED if is_watchlisted else self.WL_BTN_STATE_NOT_WATCHLISTED)
        elif controlID == self.SHUFFLE_BUTTON_ID:
            self.shuffleButtonClicked()
        elif controlID == self.OPTIONS_BUTTON_ID:
            self.optionsButtonClicked()
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

    def getMediaItems(self):
        return False

    def next(self):
        if not self._next():
            return
        self.setup()

    __next__ = next

    @busy.dialog()
    def _next(self):
        if self.parentList:
            mli = self.parentList.getListItemByDataSource(self.mediaItem)
            if not mli:
                return False

            pos = mli.pos() + 1
            if not self.parentList.positionIsValid(pos):
                pos = 0

            self.mediaItem = self.parentList.getListItem(pos).dataSource
        else:
            if not self.getMediaItems():
                return False

            if self.mediaItem not in self.mediaItems:
                return False

            pos = self.mediaItems.index(self.mediaItem)
            pos += 1
            if pos >= len(self.mediaItems):
                pos = 0

            self.mediaItem = self.mediaItems[pos]

        return True

    def prev(self):
        if not self._prev():
            return
        self.setup()

    @busy.dialog()
    def _prev(self):
        if self.parentList:
            mli = self.parentList.getListItemByDataSource(self.mediaItem)
            if not mli:
                return False

            pos = mli.pos() - 1
            if pos < 0:
                pos = self.parentList.size() - 1

            self.mediaItem = self.parentList.getListItem(pos).dataSource
        else:
            if not self.getMediaItems():
                return False

            if self.mediaItem not in self.mediaItems:
                return False

            pos = self.mediaItems.index(self.mediaItem)
            pos -= 1
            if pos < 0:
                pos = len(self.mediaItems) - 1

            self.mediaItem = self.mediaItems[pos]

        return True

    def searchButtonClicked(self):
        self.processCommand(search.dialog(self, section_id=self.mediaItem.getLibrarySectionId() or None))

    def openItem(self, control=None, item=None, inherit_from_watchlist=True, server=None, is_watchlisted=False, **kw):
        if not item:
            mli = control.getSelectedItem()
            if not mli:
                return
            item = mli.dataSource

        self.processCommand(opener.open(item, from_watchlist=self.fromWatchlist if inherit_from_watchlist else False,
                                        server=server, is_watchlisted=is_watchlisted, **kw))

    def subItemListClicked(self):
        mli = self.subItemListControl.getSelectedItem()
        if not mli:
            return

        update = False

        w = None
        if self.mediaItem.type == 'show':
            w = episodes.EpisodesWindow.open(season=mli.dataSource, show=self.mediaItem,
                                             parent_list=self.subItemListControl, from_watchlist=self.fromWatchlist)
            update = True
        elif self.mediaItem.type == 'artist':
            w = tracks.AlbumWindow.open(album=mli.dataSource, parent_list=self.subItemListControl)

        if not mli:
            return

        if not mli.dataSource.exists():
            self.subItemListControl.removeItem(mli.pos())

        if not self.subItemListControl.size():
            self.closeWithCommand(w.exitCommand)
            del w
            gc.collect(2)
            return

        if update:
            if mli and mli.dataSource:
                mli.setProperty('unwatched.count', not mli.dataSource.isWatched and str(mli.dataSource.unViewedLeafCount) or '')
            self.mediaItem.reload(includeRelated=1, includeRelatedCount=10, includeExtras=1, includeExtrasCount=10)
            self.updateProperties()

        try:
            self.processCommand(w.exitCommand)
        finally:
            del w
            gc.collect(2)

    def infoButtonClicked(self):
        fallback = 'script.plex/thumb_fallbacks/{0}.png'.format(self.mediaItem.type == 'show' and 'show' or 'music')
        genres = u' / '.join([g.tag for g in util.removeDups(self.mediaItem.genres())][:6])

        w = info.InfoWindow.open(
            title=self.mediaItem.title,
            sub_title=genres,
            thumb=self.mediaItem.defaultThumb,
            thumb_fallback=fallback,
            info=self.mediaItem.summary,
            background=self.getProperty('background'),
            is_square=bool(isinstance(self, ArtistWindow)),
            video=self.mediaItem
        )
        del w
        util.garbageCollect()

    def playButtonClicked(self, shuffle=False):
        if self.playBtnClicked:
            return

        items = self.mediaItem.all(unwatched=True)
        pl = playlist.LocalPlaylist(items, self.mediaItem.getServer())
        resume = False
        if not shuffle and self.mediaItem.type == 'show':
            resume = self.getNextShowEp(pl, items, self.mediaItem.title)
            if resume is None:
                return

        self.playBtnClicked = True
        pl.shuffle(shuffle, first=True)
        videoplayer.play(play_queue=pl, resume=resume, bgm=self.useBGM)

    def shuffleButtonClicked(self):
        self.playButtonClicked(shuffle=True)

    def optionsButtonClicked(self, from_item=None):
        options = []
        if xbmc.getCondVisibility('Player.HasAudio + MusicPlayer.HasNext'):
            options.append({'key': 'play_next', 'display': 'Play Next'})

        item = self.mediaItem
        if from_item:
            sel = self.subItemListControl.getSelectedItem()
            if sel.dataSource:
                item = sel.dataSource

        if not item:
            return

        if item.type != 'artist':
            if item.isWatched:
                options.append({'key': 'mark_unwatched', 'display': T(32318, 'Mark Unplayed')})
            else:
                options.append({'key': 'mark_watched', 'display': T(32319, 'Mark Played')})

            if item.type == "show":
                if options:
                    options.append(dropdown.SEPARATOR)

                options.append({'key': 'playback_settings', 'display': T(32925, 'Playback Settings')})
                if plexapp.ACCOUNT.isAdmin and item.server.allowsMediaDeletion:
                    options.append(dropdown.SEPARATOR)
                    if plexapp.ACCOUNT.isAdmin:
                        options.append({'key': 'refresh', 'display': T(33719, 'Refresh metadata')})
                    options.append({'key': 'delete', 'display': T(32322, 'Delete')})
            elif item.type == "season":
                if plexapp.ACCOUNT.isAdmin and item.server.allowsMediaDeletion:
                    options.append(dropdown.SEPARATOR)
                    if plexapp.ACCOUNT.isAdmin:
                        options.append({'key': 'refresh', 'display': T(33719, 'Refresh metadata')})
                    options.append({'key': 'delete', 'display': T(32975, 'Delete Season')})

        # if xbmc.getCondVisibility('Player.HasAudio') and self.section.TYPE == 'artist':
        #     options.append({'key': 'add_to_queue', 'display': 'Add To Queue'})

        # if False:
        #     options.append({'key': 'add_to_playlist', 'display': 'Add To Playlist'})

        options.append(dropdown.SEPARATOR)

        options.append({'key': 'to_section', 'display': u'Go to {0}'.format(self.mediaItem.getLibrarySectionTitle())})

        if 'items' in util.getSetting('cache_requests'):
            options.append({'key': 'cache_reset', 'display': T(33728, "Clear cache for item")})

        pos = (880, 618)
        if from_item:
            viewPos = self.subItemListControl.getViewPosition()
            optsLen = len(list(filter(None, options)))
            # dropDown handles any overlap with the right window boundary so we don't need to care here
            pos = ((((viewPos + 1) * 218) - 100), 460 if optsLen < 7 else 460 - 66 * (optsLen - 6))

        choice = dropdown.showDropdown(options, pos, close_direction='left')
        if not choice:
            return

        if choice['key'] == 'play_next':
            xbmc.executebuiltin('PlayerControl(Next)')
        elif choice['key'] == 'mark_watched':
            item.markWatched()
            self.wl_auto_remove(self.mediaItem)
            self.checkIsWatchlisted(self.mediaItem)
            self.updateItems()
            self.updateProperties()
            util.MONITOR.watchStatusChanged()
        elif choice['key'] == 'mark_unwatched':
            item.markUnwatched()
            self.updateItems()
            self.updateProperties()
            util.MONITOR.watchStatusChanged()
        elif choice['key'] == 'to_section':
            self.goHome(self.mediaItem.getLibrarySectionId())
        elif choice['key'] == 'playback_settings':
            self.playbackSettings(self.mediaItem, pos, False)
        elif choice['key'] == 'delete':
            if self.delete(item):
                # cheap way of requesting a home hub refresh because of major deletion
                util.MONITOR.watchStatusChanged()
                self.initialized = False
                self.setBoolProperty("initialized", False)
                self.setup()
                self.initialized = True
                self.setFocusId(self.PLAY_BUTTON_ID)
        elif choice['key'] == 'refresh':
            item.refresh()
            self.updateItems()
            self.updateProperties()

        elif choice["key"] == "cache_reset":
            try:
                util.DEBUG_LOG('Clearing requests cache for {}...', item)
                item.clearCache()
                self.updateItems()
                self.updateProperties()
            except Exception as e:
                util.DEBUG_LOG("Couldn't clear cache: {}", e)

    def roleClicked(self):
        mli = self.rolesListControl.getSelectedItem()
        if not mli:
            return

        sectionRoles = busy.widthDialog(mli.dataSource.sectionRoles, '')

        if not sectionRoles:
            util.DEBUG_LOG('No sections found for actor')
            return

        if len(sectionRoles) > 1:
            x, y = self.getRoleItemDDPosition()

            options = [{'role': r, 'display': r.reasonTitle} for r in sectionRoles]
            choice = dropdown.showDropdown(options, (x, y), pos_is_bottom=True)

            if not choice:
                return

            role = choice['role']
        else:
            role = sectionRoles[0]

        self.processCommand(opener.open(role))

    def getRoleItemDDPosition(self):
        y = 980
        if xbmc.getCondVisibility('Control.IsVisible(500)'):
            y += 380
        if xbmc.getCondVisibility('!String.IsEmpty(Window.Property(on.extras))'):
            y -= 200
        if xbmc.getCondVisibility('Integer.IsGreater(Window.Property(hub.focus),0) + Control.IsVisible(500)'):
            y -= 500

        tries = 0
        focus = xbmc.getInfoLabel('Container(401).Position')
        while tries < 2 and focus == '':
            focus = xbmc.getInfoLabel('Container(401).Position')
            xbmc.sleep(250)
            tries += 1

        focus = int(focus)

        x = ((focus + 1) * 304) - 100
        return x, y

    def updateItems(self):
        self.fill(update=True)

    def createListItem(self, obj):
        mli = kodigui.ManagedListItem(
            obj.title or '',
            thumbnailImage=obj.defaultThumb.asTranscodedImageURL(*self.THUMB_DIMS[self.mediaItem.type]['item.thumb']),
            data_source=obj
        )
        return mli

    @busy.dialog()
    def fill(self, update=False):
        self.fillSeasons(self.mediaItem, update=update, do_focus=not self.manuallySelectedSeason)

    def fillExtras(self):
        items = []
        idx = 0

        if not self.mediaItem.extras:
            self.extraListControl.reset()
            return False

        for extra in self.mediaItem.extras():
            mli = kodigui.ManagedListItem(
                extra.title or '',
                metadata.EXTRA_MAP.get(extra.extraType.asInt(), ''),
                thumbnailImage=extra.thumb.asTranscodedImageURL(*self.EXTRA_DIM),
                data_source=extra
            )

            if mli:
                mli.setProperty('index', str(idx))
                mli.setProperty(
                    'thumb.fallback', 'script.plex/thumb_fallbacks/{0}.png'.format(extra.type in ('show', 'season', 'episode') and 'show' or 'movie')
                )
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
            return has_prev

        self.setProperty('divider.{0}'.format(self.RELATED_LIST_ID), has_prev and '1' or '')

        items = self.relatedPaginator.paginate()

        if not items:
            return False

        return True

    def fillRoles(self, has_prev=False):
        items = []
        idx = 0
        if not self.mediaItem.roles:
            self.rolesListControl.reset()
            return has_prev

        self.setProperty('divider.{0}'.format(self.ROLES_LIST_ID), has_prev and '1' or '')

        for role in self.mediaItem.combined_roles:
            mli = kodigui.ManagedListItem(role.tag, role.role or util.TRANSLATED_ROLES[role.translated_role],
                                          thumbnailImage=role.thumb.asTranscodedImageURL(*self.ROLES_DIM),
                                          data_source=role)
            mli.setProperty('index', str(idx))
            items.append(mli)
            idx += 1

        self.rolesListControl.reset()
        self.rolesListControl.addItems(items)
        return True


class ArtistWindow(ShowWindow):
    xmlFile = 'script-plex-artist.xml'

    SUB_ITEM_LIST_ID = 400
    EXTRA_LIST_ID = None
    ROLES_LIST_ID = None
    RELATED_LIST_ID = 401

    def onFirstInit(self):
        self.subItemListControl = kodigui.ManagedControlList(self, self.SUB_ITEM_LIST_ID, 5)
        self.relatedListControl = kodigui.ManagedControlList(self, self.RELATED_LIST_ID, 5)

        self.setup()
        self.initialized = True

        self.setFocusId(self.PLAY_BUTTON_ID)

    def setup(self):
        self.relatedPaginator = RelatedPaginator(self.relatedListControl, leaf_count=int(self.mediaItem.relatedCount),
                                                 parent_window=self)
        self.updateProperties()
        self.fill()
        self.fillRelated()

    def playButtonClicked(self, shuffle=False):
        pl = playlist.LocalPlaylist(self.mediaItem.all(), self.mediaItem.getServer(), self.mediaItem)
        pl.startShuffled = shuffle
        self.processCommand(opener.handleOpen(musicplayer.MusicPlayerWindow, track=pl.current(), playlist=pl))

    def updateProperties(self):
        self.setProperty('summary', self.mediaItem.summary)
        self.setProperty('thumb', self.mediaItem.defaultThumb.asTranscodedImageURL(*self.THUMB_DIMS[self.mediaItem.type]['main.thumb']))
        self.setProperty('related.header', T(32960, 'Similar Artists'))
        self.updateBackgroundFrom(self.mediaItem)

    @busy.dialog()
    def fill(self):
        self.mediaItem.reload(includeRelated=1, includeRelatedCount=20)
        self.setProperty('artist.title', self.mediaItem.title)
        genres = u' / '.join([g.tag for g in util.removeDups(self.mediaItem.genres())][:6])
        self.setProperty('artist.genre', genres)
        items = []
        idx = 0
        for album in sorted(self.mediaItem.albums() + list(self.mediaItem.otherAlbums), key=lambda x: x.year):
            mli = self.createListItem(album)
            if mli:
                mli.setProperty('index', str(idx))
                mli.setProperty('year', album.year)
                mli.setProperty('thumb.fallback', 'script.plex/thumb_fallbacks/music.png')
                items.append(mli)
                idx += 1

        self.subItemListControl.reset()
        self.subItemListControl.addItems(items)
