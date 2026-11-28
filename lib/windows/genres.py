# coding=utf-8
from __future__ import absolute_import

from plexnet import plexobjects

from lib import util
from lib.util import T
from . import kodigui
from . import opener
from . import search
from . import windowutils


class GenreBrowserWindow(kodigui.ControlledWindow, windowutils.UtilMixin):
    xmlFile = 'script-plex-genres.xml'
    path = util.ADDON.getAddonInfo('path')
    theme = 'Main'
    res = '1080i'
    width = 1920
    height = 1080

    GENRE_PANEL_ID = 101

    HOME_BUTTON_ID = 201
    SEARCH_BUTTON_ID = 202
    PLAYER_STATUS_BUTTON_ID = 204

    def __init__(self, *args, **kwargs):
        kodigui.ControlledWindow.__init__(self, *args, **kwargs)
        windowutils.UtilMixin.__init__(self)
        self.section = kwargs.get('section')
        self.exitCommand = None

    def onFirstInit(self):
        self.genreListControl = kodigui.ManagedControlList(self, self.GENRE_PANEL_ID, 5)
        self.setProperty('screen.title', u'{0} \u00b7 {1}'.format(
            self.section.title.upper(), T(34102, 'Categories').upper()
        ))
        self.fillGenres()
        self.setBoolProperty('initialized', True)
        self.setFocusId(self.GENRE_PANEL_ID)

    def fillGenres(self):
        if self.section.key.startswith('/'):
            path = '{0}/categories'.format(self.section.key)
        else:
            path = '/library/sections/{0}/categories'.format(self.section.key)

        categories = plexobjects.listItems(self.section.server, path, bytag=True)
        if not categories:
            return

        items = []
        for cat in categories:
            mli = kodigui.ManagedListItem(str(cat.title))
            mli.dataSource = cat
            if cat.__dict__.get('thumb'):
                mli.setThumbnailImage(cat.thumb.asURL(includeToken=True))
            items.append(mli)

        self.genreListControl.addItems(items)
        self.setProperty('items.count', str(len(items)))

    def doClose(self, **kw):
        kodigui.ControlledWindow.doClose(self)

    def onClick(self, controlID):
        if controlID == self.HOME_BUTTON_ID:
            self.goHome()
        elif controlID == self.SEARCH_BUTTON_ID:
            self.processCommand(search.dialog(self, section_id=self.section.key))
        elif controlID == self.PLAYER_STATUS_BUTTON_ID:
            self.showAudioPlayer()
        elif controlID == self.GENRE_PANEL_ID:
            self.genreClicked()

    def genreClicked(self):
        mli = self.genreListControl.getSelectedItem()
        if not mli or not mli.dataSource:
            return
        cat = mli.dataSource
        # key is e.g. "/library/sections/2/all?genre=5" — extract the numeric genre ID
        key_str = str(cat.key)
        genre_id = key_str.split('genre=')[-1].split('&')[0] if 'genre=' in key_str else key_str
        filter_ = {'type': 'genre', 'display': T(32379, 'Genre'), 'sub': {'val': genre_id, 'display': str(cat.title)}}
        self.processCommand(opener.sectionClicked(self.section, filter_=filter_))
