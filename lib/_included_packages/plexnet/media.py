from __future__ import absolute_import
from . import plexobjects
from . import plexstream
from . import util
from . import exceptions

METADATA_RELATED_TRAILER = 1
METADATA_RELATED_DELETED_SCENE = 2
METADATA_RELATED_INTERVIEW = 3
METADATA_RELATED_MUSIC_VIDEO = 4
METADATA_RELATED_BEHIND_THE_SCENES = 5
METADATA_RELATED_SCENE_OR_SAMPLE = 6
METADATA_RELATED_LIVE_MUSIC_VIDEO = 7
METADATA_RELATED_LYRIC_MUSIC_VIDEO = 8
METADATA_RELATED_CONCERT = 9
METADATA_RELATED_FEATURETTE = 10
METADATA_RELATED_SHORT = 11
METADATA_RELATED_OTHER = 12


class MediaItem(plexobjects.PlexObject):
    def __eq__(self, other):
        return self.ratingKey == other.ratingKey

    def __ne__(self, other):
        return not self.__eq__(other)

    def __hash__(self):
        return hash(self.ratingKey)

    def getIdentifier(self):
        identifier = self.get('identifier') or None

        if identifier is None:
            try:
                identifier = self.container.identifier
            except AttributeError:
                util.DEBUG_LOG("Couldn't get media identifier for {}", self)
                pass

        # HACK
        # PMS doesn't return an identifier for playlist items. If we haven't found
        # an identifier and the key looks like a library item, then we pretend like
        # the identifier was set.
        #
        if identifier is None:  # Modified from Roku code which had no check for None with iPhoto - is that right?
            if self.key.startswith('/library/metadata'):
                identifier = "com.plexapp.plugins.library"
            elif self.isIPhoto():
                identifier = "com.plexapp.plugins.iphoto"

        return identifier

    def getQualityType(self, server=None):
        if self.isOnlineItem():
            return util.QUALITY_ONLINE

        if not server:
            server = self.getServer()

        return util.QUALITY_LOCAL if server.isLocalConnection() else util.QUALITY_REMOTE

    def delete(self):
        if not self.ratingKey:
            return

        from . import plexrequest
        req = plexrequest.PlexRequest(self.server, '/library/metadata/{0}'.format(self.ratingKey), method='DELETE')
        req.getToStringWithTimeout(10)
        self.deleted = req.wasOK()
        return self.deleted

    def exists(self, force_full_check=False):
        if (self.deleted or self.deletedAt) and not force_full_check:
            return False

        # force_full_check is imperfect, as it doesn't check for existence of its mediaparts
        try:
            data = self.server.query('/library/metadata/{0}'.format(self.ratingKey))
        except exceptions.BadRequest:
            # item does not exist anymore
            util.DEBUG_LOG("Item {} doesn't exist.", self.ratingKey)
            return False
        return data is not None and data.attrib.get('size') != '0'

    def relatedHubs(self, data, _itemCls, hubIdentifiers=None, _filter=None):
        hubs = data.find("Related")
        if _filter is None and hubIdentifiers is None:
            raise NotImplemented

        _f = lambda x: x
        if _filter is not None:
            _f = _filter
        if hubIdentifiers is not None:
            hubIds = hubIdentifiers
            if not isinstance(hubIds, (list, set, tuple)):
                hubIds = [hubIds]
            _f = lambda x: x.attrib.get("hubIdentifier", None) in hubIds

        results = []
        if hubs is not None:
            for hub in hubs:
                if hub.attrib.get("size", 0) and _f(hub):
                    results += list(plexobjects.PlexItemList(hub, _itemCls, 'Directory', server=self.server,
                                                             container=self))
        return results

    def fixedDuration(self):
        duration = self.duration.asInt()
        if duration < 1000:
            duration *= 60000
        return duration


class Media(plexobjects.PlexObject):
    TYPE = 'Media'

    def __init__(self, data, initpath=None, server=None, video=None):
        plexobjects.PlexObject.__init__(self, data, initpath=initpath, server=server)
        self.video = video
        self.parts = [MediaPart(elem, initpath=self.initpath, server=self.server, media=self) for elem in data]

    def __repr__(self):
        title = self.video.title.replace(' ', '.')[0:20]
        return '<%s:%s>' % (self.__class__.__name__, title.encode('utf8'))


class MediaPart(plexobjects.PlexObject):
    TYPE = 'Part'

    def __init__(self, data, initpath=None, server=None, media=None):
        plexobjects.PlexObject.__init__(self, data, initpath=initpath, server=server)
        self.media = media
        self.streams = [MediaPartStream.parse(e, initpath=self.initpath, server=server, part=self) for e in data if e.tag == 'Stream']

    def __repr__(self):
        return '<%s:%s>' % (self.__class__.__name__, self.id)

    @property
    def audioStreams(self):
        return list(filter(lambda x: x.streamType.asInt() == plexstream.PlexStream.TYPE_AUDIO, self.streams))

    def selectedStream(self, stream_type):
        streams = [x for x in self.streams if stream_type == x.type]
        selected = list([x for x in streams if x.selected is True])
        if len(selected) == 0:
            return None
        return selected[0]


class MediaPartStream(plexstream.PlexStream):
    TYPE = None
    STREAMTYPE = None

    def __init__(self, data, initpath=None, server=None, part=None, **kwargs):
        plexobjects.PlexObject.__init__(self, data, initpath, server, **kwargs)
        self.part = part

    @staticmethod
    def parse(data, initpath=None, server=None, part=None, **kwargs):
        STREAMCLS = {
            1: VideoStream,
            2: AudioStream,
            3: SubtitleStream
        }
        stype = int(data.attrib.get('streamType'))
        cls = STREAMCLS.get(stype, MediaPartStream)
        return cls(data, initpath=initpath, server=server, part=part, **kwargs)

    @staticmethod
    def rebuild(s):
        return MediaPartStream.parse(s.data, initpath=s.initpath, server=s.server, part=s.part)

    def __repr__(self):
        return '<%s:%s>' % (self.__class__.__name__, self.id)


class VideoStream(MediaPartStream):
    TYPE = 'videostream'
    STREAMTYPE = plexstream.PlexStream.TYPE_VIDEO


class AudioStream(MediaPartStream):
    TYPE = 'audiostream'
    STREAMTYPE = plexstream.PlexStream.TYPE_AUDIO


class SubtitleStream(MediaPartStream):
    TYPE = 'subtitlestream'
    STREAMTYPE = plexstream.PlexStream.TYPE_SUBTITLE

    def __init__(self, data, initpath=None, server=None, part=None):
        super(MediaPartStream, self).__init__(data, initpath=initpath, server=server, part=part)
        self.force_auto_sync = None
        self.init_auto_sync(part=part)

    def init_auto_sync(self, part=None, video=None):
        if not (part or video):
            return
        self._should_auto_sync = self.canAutoSync.asBool() and util.INTERFACE.playbackManager(
            part.media).auto_sync if part and part.media else video.playbackSettings.auto_sync if video else util.INTERFACE.getPreference('auto_sync', user=True)

    @property
    def should_auto_sync(self):
        return self.force_auto_sync if self.force_auto_sync is not None else self._should_auto_sync

    @property
    def should_auto_sync_unforced(self):
        return self._should_auto_sync

    @should_auto_sync.setter
    def should_auto_sync(self, value):
        self._should_auto_sync = value


class TranscodeSession(plexobjects.PlexObject):
    TYPE = 'TranscodeSession'


class MediaTag(plexobjects.PlexObject):
    TYPE = None
    ID = 'None'
    virtual = False

    def __repr__(self):
        tag = self.tag.replace(' ', '.')[0:20]
        return '<%s:%s:%s:%s>' % (self.__class__.__name__, self.id, tag, self.virtual)

    def __eq__(self, other):
        if other.__class__ != self.__class__:
            return False

        return self.id == other.id

    def __ne__(self, other):
        return not self.__eq__(other)


class Collection(MediaTag):
    TYPE = 'Collection'
    FILTER = 'collection'


class Location(MediaTag):
    TYPE = 'Location'
    FILTER = 'location'


class Country(MediaTag):
    TYPE = 'Country'
    FILTER = 'country'


class Genre(MediaTag):
    TYPE = 'Genre'
    FILTER = 'genre'
    ID = '1'


class Rating(MediaTag):
    TYPE = 'Rating'


class Mood(MediaTag):
    TYPE = 'Mood'
    FILTER = 'mood'



class Role(MediaTag):
    TYPE = 'Role'
    FILTER = 'actor'
    ID = '6'
    translated_role = ''

    def sectionRoles(self):
        hubs = self.server.hubs(count=10, search_query=self.tag)
        for hub in hubs:
            if hub.type == self.FILTER:
                break
        else:
            return None

        roles = []

        for actor in hub.items:
            if actor.id == self.id:
                roles.append(actor)

        return roles or None

    def getDetails(self):
        """
        Fetch full actor metadata including biography, birth date, photo, etc.
        Uses /library/people/{personId} endpoint per Plex API docs.
        The personId can be either the PMS tag id or the tagKey (hex portion of plex guid).
        Returns a dict with actor details.
        """
        if not self.tag:
            return self._getBasicDetails()

        # Start with basic info that we'll augment
        result = self._getBasicDetails()
        tag_key = None

        try:
            # Try using the tag id first (this is typically available from Role objects)
            person_id = self.id
            
            # If we have a tagKey (from newer API responses), that's preferred
            if hasattr(self, 'tagKey') and self.tagKey:
                person_id = self.tagKey
                tag_key = self.tagKey
            
            path = '/library/people/{0}'.format(person_id)
            data = self.server.query(path)
            
            if data is not None:
                # Debug: Log the raw response structure
                util.DEBUG_LOG('Actor API response tag: {0}, attribs: {1}'.format(data.tag, list(data.attrib.keys())))
                for child in data:
                    util.DEBUG_LOG('  Child element: {0}, attribs: {1}'.format(child.tag, dict(child.attrib)))
                
                # The response contains a Directory element with person details
                for directory in data.findall('Directory'):
                    util.DEBUG_LOG('Found actor details for {0} via /library/people endpoint'.format(self.tag))
                    # Get tagKey from response if we don't have it
                    if not tag_key:
                        tag_key = directory.get('tagKey', '')
                    result = {
                        'id': directory.get('ratingKey', directory.get('id', self.id)),
                        'name': directory.get('tag', directory.get('title', self.tag)),
                        'thumb': directory.get('thumb', str(self.thumb) if self.thumb else ''),
                        'summary': directory.get('summary', ''),
                        'birthDate': directory.get('birthDate', ''),
                        'deathDate': directory.get('deathDate', ''),
                        'birthPlace': directory.get('birthPlace', ''),
                        'role': getattr(self, 'role', ''),
                        'tagKey': tag_key or '',
                    }
                    break
                
        except Exception as e:
            util.DEBUG_LOG('Failed to fetch actor details from local PMS for {0}: {1}'.format(self.tag, e))

        # If local PMS didn't yield a tagKey (actor not in library), resolve via Discover people search
        if not tag_key and not util.LOCAL_MODE:
            tag_key = self._resolveTagKeyViaDiscover(self.tag)
            if tag_key:
                result['tagKey'] = tag_key

        # If we have a tagKey and no biography yet, try the online metadata provider
        # (never in local mode; these use requests directly and bypass the transport block)
        if tag_key and not result.get('summary') and not util.LOCAL_MODE:
            try:
                # Query the metadata provider for rich actor details
                # The tagKey is the actor's GUID on plex.tv
                from . import plexapp
                account = plexapp.ACCOUNT
                if account and account.authToken:
                    import requests
                    
                    # Try multiple possible endpoints
                    endpoints = [
                        'https://discover.provider.plex.tv/library/people/{0}'.format(tag_key),
                        'https://metadata.provider.plex.tv/library/metadata/{0}'.format(tag_key),
                        'https://discover.provider.plex.tv/library/metadata/{0}'.format(tag_key),
                    ]
                    
                    headers = {
                        'X-Plex-Token': account.authToken,
                        'Accept': 'application/xml'
                    }
                    
                    for url in endpoints:
                        util.DEBUG_LOG('Trying actor metadata from: {0}'.format(url))
                        try:
                            response = requests.get(url, headers=headers, timeout=5)
                            
                            if response.status_code == 200:
                                import xml.etree.ElementTree as ET
                                data = ET.fromstring(response.content)
                                util.DEBUG_LOG('Metadata response from {0}: tag={1}, children={2}'.format(
                                    url.split('/')[2], data.tag, [c.tag for c in data]))
                                
                                for elem in list(data.findall('Directory')) + list(data.findall('Metadata')) + list(data):
                                    if elem.get('summary') or elem.get('birthDate'):
                                        util.DEBUG_LOG('Found rich actor metadata!')
                                        result['summary'] = elem.get('summary', result.get('summary', ''))
                                        result['birthDate'] = elem.get('birthDate', result.get('birthDate', ''))
                                        result['deathDate'] = elem.get('deathDate', result.get('deathDate', ''))
                                        result['birthPlace'] = elem.get('birthPlace', result.get('birthPlace', ''))
                                        if elem.get('thumb'):
                                            result['thumb'] = elem.get('thumb')
                                        break
                                
                                # If we found data, stop trying other endpoints
                                if result.get('summary') or result.get('birthDate'):
                                    break
                            else:
                                util.DEBUG_LOG('  Status {0}'.format(response.status_code))
                        except Exception as e:
                            util.DEBUG_LOG('  Error: {0}'.format(e))
                            continue
                            
            except Exception as e:
                util.DEBUG_LOG('Failed to fetch actor metadata from plex.tv for {0}: {1}'.format(self.tag, e))

        return result

    def _resolveTagKeyViaDiscover(self, name):
        """
        Resolve an actor's tagKey via Plex Discover people search.
        Returns the tagKey of the highest-score result, or None.
        """
        if not name or util.LOCAL_MODE:
            return None
        try:
            from . import plexapp
            account = plexapp.ACCOUNT
            if not account or not account.authToken:
                return None

            import requests
            url = 'https://discover.provider.plex.tv/library/search'
            params = {
                'query': name,
                'searchTypes': 'people',
                'searchProviders': 'discover',
                'limit': 5,
            }
            headers = {
                'X-Plex-Token': account.authToken,
                'Accept': 'application/json',
            }
            response = requests.get(url, params=params, headers=headers, timeout=5)
            if response.status_code != 200:
                util.DEBUG_LOG('_resolveTagKeyViaDiscover: status {0} for {1}', response.status_code, name)
                return None

            data = response.json()
            container = data.get('MediaContainer', {})
            results = container.get('SearchResult', []) or container.get('SearchResults', [])

            best = None
            best_score = -1.0
            for sr in results:
                try:
                    score = float(sr.get('score', 0) or 0)
                except (TypeError, ValueError):
                    score = 0.0
                candidates = []
                if isinstance(sr.get('Metadata'), dict):
                    candidates.append(sr['Metadata'])
                elif isinstance(sr.get('Metadata'), list):
                    candidates.extend(sr['Metadata'])
                if isinstance(sr.get('Directory'), dict):
                    candidates.append(sr['Directory'])
                elif isinstance(sr.get('Directory'), list):
                    candidates.extend(sr['Directory'])
                if not candidates:
                    candidates.append(sr)
                for entry in candidates:
                    tk = entry.get('tagKey') or entry.get('metadataId') or entry.get('id')
                    if tk and score > best_score:
                        best = tk
                        best_score = score
                        break

            if best:
                util.DEBUG_LOG('_resolveTagKeyViaDiscover: resolved tagKey {0} for {1} (score={2})',
                               best, name, best_score)
            else:
                util.DEBUG_LOG('_resolveTagKeyViaDiscover: no match for {0}', name)
            return best
        except Exception as e:
            util.DEBUG_LOG('_resolveTagKeyViaDiscover: failed for {0}: {1}', name, e)
            return None

    def _getBasicDetails(self):
        """Return basic info from the Role object when API call fails or is unavailable."""
        return {
            'id': self.id,
            'name': self.tag,
            'thumb': str(self.thumb) if self.thumb else '',
            'summary': '',
            'birthDate': '',
            'deathDate': '',
            'birthPlace': '',
            'role': getattr(self, 'role', ''),
        }

    def getFilmography(self, media_type=None, start=None, size=None):
        """
        Get movies/shows this actor appears in from your library.
        Uses /library/people/{personId}/media endpoint per Plex API docs.
        
        Args:
            media_type: 'movie', 'show', or None for all
            start: Starting offset for pagination (X-Plex-Container-Start)
            size: Number of items to fetch (X-Plex-Container-Size)
        
        Returns:
            dict with 'items', 'offset', 'size', 'totalSize', and 'more' keys
        
        Note: The Plex discover API does not provide an endpoint for actor filmography,
        so only local library content is returned.
        """
        items = []
        result = {
            'items': items,
            'offset': start or 0,
            'size': 0,
            'totalSize': 0,
            'more': False
        }
        
        try:
            # Use the proper people media endpoint
            person_id = self.id
            if hasattr(self, 'tagKey') and self.tagKey:
                person_id = self.tagKey
            
            path = '/library/people/{0}/media'.format(person_id)
            
            # Add pagination headers as query params
            args = {}
            if size is not None:
                args['X-Plex-Container-Start'] = start if start is not None else 0
                args['X-Plex-Container-Size'] = size
            
            if args:
                path += util.joinArgs(args)
            
            data = self.server.query(path)
            
            if data is not None:
                # Get pagination info from response
                result['offset'] = int(data.get('offset', start or 0))
                result['size'] = int(data.get('size', 0))
                result['totalSize'] = int(data.get('totalSize', 0))
                
                # Debug: Log the raw response structure
                util.DEBUG_LOG('Filmography API response: offset={0}, size={1}, totalSize={2}'.format(
                    result['offset'], result['size'], result['totalSize']))
                
                from . import video  # Import here to avoid circular imports
                
                # Look for Video elements (what the API actually returns) AND Metadata elements
                for elem in list(data.findall('Video')) + list(data.findall('Metadata')) + list(data.findall('Directory')):
                    item_type = elem.get('type', '')
                    
                    # Filter by media type if specified
                    if media_type:
                        if media_type == 'movie' and item_type != 'movie':
                            continue
                        if media_type == 'show' and item_type != 'show':
                            continue
                    
                    # Only include movies and shows
                    if item_type in ('movie', 'show'):
                        # Create appropriate media object
                        if item_type == 'movie':
                            item = video.Movie(elem, self.initpath, self.server)
                        else:
                            item = video.Show(elem, self.initpath, self.server)
                        items.append(item)
                
                # Calculate if there are more items
                result['size'] = len(items)
                result['more'] = (result['offset'] + result['size']) < result['totalSize']
                
                util.DEBUG_LOG('Found {0} filmography items for {1} (more={2})'.format(
                    len(items), self.tag, result['more']))
        except Exception as e:
            util.DEBUG_LOG('Failed to fetch filmography for {0}: {1}'.format(self.tag, e))
            # Fallback to search-based approach
            fallback_items = self._getFilmographyViaSearch(media_type)
            result['items'] = fallback_items
            result['size'] = len(fallback_items)
            result['totalSize'] = len(fallback_items)
            result['more'] = False
        
        return result
    
    def _getFilmographyViaSearch(self, media_type=None):
        """Fallback filmography fetch using hub search."""
        hubs = self.server.hubs(count=50, search_query=self.tag)
        items = []

        for hub in hubs:
            if media_type:
                if media_type == 'movie' and hub.type != 'movie':
                    continue
                if media_type == 'show' and hub.type != 'show':
                    continue

            if hub.type in ('movie', 'show'):
                for item in hub.items:
                    items.append(item)

        return items

    def getDiscoverCredits(self, credit_type=None):
        """
        Fetch full filmography from Plex's discover API (not just local library).

        Args:
            credit_type: None to return all credit groups, or a string like
                         'actor', 'director', 'producer' to filter to one group.

        Returns:
            When credit_type is None: list of (type_name, credits) tuples for each
            group the API returns, in API order.
            When credit_type is set: flat list of credit dicts for that type only.
            Returns empty list if tagKey is not available or request fails.
        """
        tag_key = getattr(self, 'tagKey', None)
        if not tag_key:
            util.DEBUG_LOG('getDiscoverCredits: No tagKey available for {0}'.format(self.tag))
            return []

        if util.LOCAL_MODE:
            return []

        try:
            from . import plexapp
            account = plexapp.ACCOUNT
            if not account or not account.authToken:
                util.DEBUG_LOG('getDiscoverCredits: No auth token available')
                return []

            import requests
            url = 'https://discover.provider.plex.tv/library/people/{0}/credits'.format(tag_key)
            headers = {
                'X-Plex-Token': account.authToken,
                'Accept': 'application/json'
            }

            response = requests.get(url, headers=headers, timeout=10)
            if response.status_code != 200:
                util.DEBUG_LOG('getDiscoverCredits: Status {0} for {1}'.format(response.status_code, self.tag))
                return []

            data = response.json()
            container = data.get('MediaContainer', {})
            credit_groups = container.get('CreditGroup', [])

            if credit_type is not None:
                # Legacy single-type mode
                for group in credit_groups:
                    if group.get('type', '').lower() == credit_type.lower():
                        credits = group.get('Credit', [])
                        util.DEBUG_LOG('getDiscoverCredits: Found {0} {1} credits for {2}'.format(
                            len(credits), credit_type, self.tag))
                        return credits
                return []

            # Return all groups as (type, credits) tuples
            result = []
            for group in credit_groups:
                group_type = group.get('type', '')
                credits = group.get('Credit', [])
                if credits:
                    result.append((group_type, credits))
            util.DEBUG_LOG('getDiscoverCredits: Found {0} credit groups for {1}: {2}'.format(
                len(result), self.tag, [r[0] for r in result]))
            return result

        except Exception as e:
            util.DEBUG_LOG('getDiscoverCredits: Failed for {0}: {1}'.format(self.tag, e))
            return []

    @staticmethod
    def checkLibraryPresence(server, guids):
        """
        Batch-check which plex GUIDs exist in the user's library.

        Args:
            server: PlexServer instance to query
            guids: list of plex GUIDs (e.g. ['plex://movie/5d7769d0...', ...])

        Returns:
            set of GUIDs that ARE in the library
        """
        from .compat import quote_plus

        present = set()
        # Batch in groups of 10 (matching Plex Web's behaviour)
        batch_size = 10
        for i in range(0, len(guids), batch_size):
            batch = guids[i:i + batch_size]
            # URL-encode each GUID and join with commas
            encoded = ','.join(quote_plus(g) for g in batch)
            path = '/library/metadata/{0}'.format(encoded)
            try:
                data = server.query(path)
                if data is not None:
                    # 200 response — all items in this batch are in the library
                    # Extract the GUIDs from the response to be precise
                    for elem in data:
                        guid = elem.get('guid', '')
                        if guid:
                            present.add(guid)
                    # If no guid attributes in response, assume all batch GUIDs are present
                    if not present.intersection(set(batch)):
                        present.update(batch)
            except Exception:
                # 404 or error — none of these items are in the library
                pass

        util.DEBUG_LOG('checkLibraryPresence: {0}/{1} GUIDs found in library'.format(
            len(present), len(guids)))
        return present


class Similar(MediaTag):
    TYPE = 'Similar'
    FILTER = 'similar'


class Director(Role):
    TYPE = 'Director'
    FILTER = 'director'
    ID = '4'
    translated_role = 'Director'


class Producer(Role):
    TYPE = 'Producer'
    FILTER = 'producer'
    translated_role = 'Producer'


class Writer(Role):
    TYPE = 'Writer'
    FILTER = 'writer'
    translated_role = 'Writer'


class Guid(MediaTag):
    TYPE = 'Guid'
    FILTER = 'guid'


class Chapter(MediaTag):
    TYPE = 'Chapter'
    
    def startTime(self):
        return self.get('startTimeOffset', -1).asInt()


class Bandwidth(plexobjects.PlexObject):
    TYPE = 'Bandwidth'


class Marker(MediaTag):
    TYPE = 'Marker'
    FILTER = 'Marker'

    def __repr__(self):
        return '<%s:%s:%s:%s>' % (self.__class__.__name__, self.id, self.type, self.final and "final" or "")


class Review(MediaTag):
    TYPE = 'Review'
    FILTER = 'Review'

    def ratingImage(self):
        # only rottentomatoes currently supported
        img = str(self.image)
        if not img or not img.startswith("rottentomatoes://"):
            return ''

        return img.split('rottentomatoes://')[1]


class Studio(MediaTag):
    TYPE = 'Studio'
    FILTER = 'Studio'


class RelatedMixin(object):
    _relatedCount = None
    related_source = "similar"

    @property
    def relatedCount(self):
        if self._relatedCount is None:
            related = self.getRelated(0, 0 if self.related_source == "similar" else 36)
            if related is not None:
                self._relatedCount = related.totalSize
            else:
                self._relatedCount = 0

        return self._relatedCount

    @property
    def related(self):
        return self.getRelated(0, 8)

    def getRelated(self, offset=None, limit=None, _max=36):
        path = '/library/metadata/{}/{}'.format(self.ratingKey, self.related_source)
        try:
            return plexobjects.listItems(self.server, path, offset=offset, limit=limit, params={"count": _max},
                                         cachable=self.cachable, cache_ref=self.cacheRef, not_cachable=self._not_cachable)
        except exceptions.BadRequest:
            util.DEBUG_LOG("Invalid related items response returned for {}", self)
            return None
