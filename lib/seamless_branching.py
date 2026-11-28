# coding=utf-8
"""
Seamless Branching Manager for PlexMod4Kodi

Manages detection and LAV filter control for movies with seamless branching issues.
Seamless branching movies (e.g., movies with IMAX sequences) can have audio dropouts
when played with TrueHD or tms audio tracks on certain platforms.

This module:
- Loads a bundled list of known seamless branching movies
- Optionally loads user-customized additions
- Detects if a movie needs LAV filter workaround
- Provides LAV mode configuration

"""

import os
import json
import fnmatch

from kodi_six import xbmcvfs

from . import util


class SeamlessBranchingManager(object):
    """
    Manages seamless branching movie detection and LAV filter control.

    Loads a bundled JSON file of known seamless branching movies, plus an optional
    user-customized JSON file from the profile directory.
    """

    # File paths
    BUNDLED_DATA_FILE = "seamless_branching.json"
    USER_DATA_FILE = "seamless_branching_user.json"

    # Per-folder force-engage marker filenames. If one of these sits next to the
    # playing media's first Part, engage LAV regardless of curated-list match or
    # audio codec. Only consulted when the part is path-mapped to a local URI
    # (playerObject.metadata.isMapped). Matches service.p3i.sb convention.
    SB_MARKER_FILES = ("SB", "SB.txt")

    # LAV setting ID (CoreELEC U3k B9+)
    LAV_SETTING_ID = "coreelec.amlogic.dolbyvision.audio.seamlessbranch"

    # LAV modes
    LAV_MODE_OFF = 0
    LAV_MODE_SEEK_SYNC = 1
    LAV_MODE_DEBUG = 3
    LAV_MODE_LAV_SB = 4
    LAV_MODE_LAV_FULL = 5

    # Audio detection thresholds
    TMS_EAC3_MIN_BITRATE = 736  # kbps - DD+ with tms is typically 768kbps+; Plex tends to miscalculate audio bitrates sometimes, though

    def __init__(self):
        self.seamless_branching_movies = set()  # Set of IMDB IDs
        self._load_bundled_data()
        self._load_user_data()

    def _load_bundled_data(self):
        """Load the bundled seamless branching movie list"""
        bundled_path = os.path.join(
            util.translatePath(util.ADDON.getAddonInfo("path")),
            "resources",
            self.BUNDLED_DATA_FILE
        )

        if xbmcvfs.exists(bundled_path):
            try:
                f = xbmcvfs.File(bundled_path)
                try:
                    data = json.loads(f.read())
                finally:
                    f.close()

                # Extract IMDB IDs from movie list
                for movie in data.get("movies", []):
                    imdb_id = movie.get("imdb_id")
                    if imdb_id:
                        self.seamless_branching_movies.add(imdb_id)

                util.LOG("Seamless branching: Loaded {} movies from bundled list",
                        len(self.seamless_branching_movies))
            except:
                util.ERROR("Couldn't read bundled seamless_branching.json")

    def _load_user_data(self):
        """Load user-customized seamless branching movie list"""
        user_path = os.path.join(
            util.translatePath(util.ADDON.getAddonInfo("profile")),
            self.USER_DATA_FILE
        )

        if xbmcvfs.exists(user_path):
            try:
                f = xbmcvfs.File(user_path)
                try:
                    data = json.loads(f.read())
                finally:
                    f.close()

                # Count before for logging
                count_before = len(self.seamless_branching_movies)

                # Extract IMDB IDs and add to the set
                for movie in data.get("movies", []):
                    imdb_id = movie.get("imdb_id")
                    if imdb_id:
                        self.seamless_branching_movies.add(imdb_id)

                count_added = len(self.seamless_branching_movies) - count_before
                if count_added > 0:
                    util.LOG("Seamless branching: Loaded {} additional movies from user file",
                            count_added)
            except:
                util.ERROR("Couldn't read user seamless_branching_user.json")

    def get_imdb_id(self, video):
        imdb_id = None
        guid = video.guid

        if "com.plexapp.agents.imdb" in guid:
            imdb_id = guid.split("?lang=")[0][
                guid.index("com.plexapp.agents.imdb://") + len("com.plexapp.agents.imdb://"):]
        elif "plex://movie" in guid:
            # For new Plex agent, check guids array
            for g in video.guids:
                if g.id.startswith('imdb://'):
                    imdb_id = g.id.split('imdb://')[1]
                    break
        return imdb_id

    def _is_truehd_or_tms(self, audio_stream):
        """
        Check if audio stream is TrueHD or tms (DD+ with high bitrate).

        Args:
            audio_stream: Audio stream object with .codec and .bitrate properties

        Returns:
            bool: True if stream is TrueHD or tms
        """
        if not audio_stream:
            return False

        codec = audio_stream.codec
        if not codec:
            return False

        codec_lower = codec.lower()

        # TrueHD always affected (with or without tms metadata)
        if codec_lower == 'truehd':
            return True

        # EAC3 (DD+) only if bitrate indicates tms (768kbps+)
        # Standard DD+ 5.1/7.1 is typically 384-640kbps
        if codec_lower == 'eac3':
            bitrate = getattr(audio_stream, 'bitrate', None)
            if bitrate and bitrate.asInt() >= self.TMS_EAC3_MIN_BITRATE:
                return True

        return False

    def has_sb_marker(self, playerObject):
        """
        Check for an SB or SB.txt marker file next to the playing media's first
        Part. Only meaningful when the part is path-mapped to a local URI;
        relies on playerObject.metadata.isMapped (set by BasePlayer.setupObj
        when PathMappingManager.getPathMappedUrl() resolves).

        Marker semantics (mirrors service.p3i.sb):
        - Empty / whitespace-only file: engage for every file in the folder
          (original behavior).
        - Non-empty: each non-blank/non-comment line is a filename or fnmatch
          glob; engage only when the playing file's basename matches at least
          one entry.

        Returns:
            bool: True if a marker file applies to the playing file.
        """
        try:
            meta = playerObject.metadata
        except AttributeError:
            return False
        if not meta or not getattr(meta, 'isMapped', False):
            return False
        try:
            url = meta.streamUrls[0]
        except (AttributeError, IndexError, TypeError):
            return False
        if not url:
            return False
        folder = os.path.dirname(url)
        if not folder:
            return False
        basename = os.path.basename(url)
        for marker in self.SB_MARKER_FILES:
            marker_path = os.path.join(folder, marker)
            if not xbmcvfs.exists(marker_path):
                continue
            patterns = self._read_marker_patterns(marker_path)
            if patterns is None:
                # Empty / unreadable / no entries -> whole-folder engage.
                return True
            if any(fnmatch.fnmatchcase(basename, p) for p in patterns):
                util.DEBUG_LOG("SB marker {} matched {}", marker_path, basename)
                return True
            util.DEBUG_LOG("SB marker {} present but no entry matched {}", marker_path, basename)
        return False

    def _read_marker_patterns(self, marker_path):
        """Returns the list of patterns from the marker file, or None if the
        file is empty / unreadable / contains nothing but blanks and comments
        (in which case the caller treats marker presence as whole-folder)."""
        try:
            f = xbmcvfs.File(marker_path)
            try:
                data = f.read()
            finally:
                f.close()
        except Exception as exc:
            util.ERROR("SB marker {} unreadable: {}".format(marker_path, exc))
            return None
        if isinstance(data, bytes):
            try:
                data = data.decode("utf-8")
            except UnicodeDecodeError:
                util.DEBUG_LOG("SB marker {} not UTF-8, treating as whole-folder", marker_path)
                return None
        if not data or not data.strip():
            return None
        patterns = []
        for line in data.splitlines():
            s = line.strip()
            if not s or s[0] in ("#", ";"):
                continue
            patterns.append(s)
        return patterns or None

    def is_seamless_branching_movie(self, imdb_id, audio_stream, force_detection=False):
        """
        Determine if a movie requires LAV filter workaround.

        Args:
            imdb_id: IMDB ID of the movie (e.g., "tt0468569")
            audio_stream: Audio stream object from playerObject.choice.audioStream
            [force_detection]: Always return the state even if our current Kodi instance doesn't support SB workarounds

        Returns:
            bool: True if LAV filters should be enabled
        """
        # Check all criteria
        if not force_detection and not util.CE_SB_LAV_SWITCH:
            return False

        if not imdb_id or imdb_id not in self.seamless_branching_movies:
            return False

        if not self._is_truehd_or_tms(audio_stream):
            return False

        return True

    def get_lav_mode(self):
        """
        Get the user-configured LAV mode from addon settings.

        Returns:
            int: LAV mode value (0-5)
        """
        return util.addonSettings.seamlessBranchingLavMode

    def needs_lav_switch(self, mode):
        if mode not in (self.LAV_MODE_LAV_FULL, self.LAV_MODE_LAV_SB):
            return True
        return False


# Global instance
sbm = SeamlessBranchingManager()
