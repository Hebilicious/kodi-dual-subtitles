"""Jellyfin: which item is playing, its subtitle tracks, and their text in SRT or ASS."""

import json
import os
import re
import time
import urllib.error
import urllib.parse
import urllib.request

from . import languages
from .tracks import Track, classify

_ID_IN_URL = [re.compile(r"/(?:videos|items|audio)/([0-9a-f]{32})(?:/|$|\?)", re.IGNORECASE),
              re.compile(r"[?&](?:id|itemid|item_id)=([0-9a-f]{32})", re.IGNORECASE)]
_LIBRARY_TTL = 600  # seconds a library listing is reused to match file names


class JellyfinError(Exception):
    pass


class Jellyfin:
    def __init__(self, url, api_key, device_id="kodi-dual-subtitles", version="1.0.0", timeout=20):
        self.url = (url or "").rstrip("/")
        self.api_key = api_key or ""
        self.device_id = device_id
        self.version = version
        self.timeout = timeout
        self._library = None
        self._library_time = 0

    @property
    def configured(self):
        return bool(self.url and self.api_key)

    def _request(self, path, query=None, timeout=None, raw=False, method="GET"):
        if not self.configured:
            raise JellyfinError("Jellyfin server or API key not set in the add-on settings")
        url = self.url + path
        if query:
            url += "?" + urllib.parse.urlencode(query, doseq=True)
        auth = 'MediaBrowser Client="Kodi dual subtitles", Device="Kodi", DeviceId="%s", Version="%s", Token="%s"' % (
            self.device_id, self.version, self.api_key)
        request = urllib.request.Request(url, method=method, headers={"Authorization": auth, "Accept": "*/*"})
        try:
            with urllib.request.urlopen(request, timeout=timeout or self.timeout) as response:
                body = response.read()
        except urllib.error.HTTPError as error:
            raise JellyfinError("Jellyfin answered %d for %s" % (error.code, path))
        except (urllib.error.URLError, OSError) as error:
            raise JellyfinError("can't reach Jellyfin at %s (%s)" % (self.url, getattr(error, "reason", error)))
        if raw:
            return body
        try:
            return json.loads(body.decode("utf-8")) if body else {}
        except ValueError:
            raise JellyfinError("Jellyfin sent something that isn't JSON for %s" % path)

    # --- Which item is playing -------------------------------------------------------------

    @staticmethod
    def id_from_url(path):
        """The item id in a Jellyfin stream URL or a Jellyfin for Kodi plugin path."""
        for pattern in _ID_IN_URL:
            match = pattern.search(path or "")
            if match:
                return match.group(1).lower()
        return ""

    def find_item(self, playing_path):
        """Item of the file Kodi is playing: from the URL, or else by file name in the library."""
        item_id = self.id_from_url(playing_path)
        if item_id:
            return self.item(item_id)
        name = _basename(playing_path)
        if not name:
            return None
        for item in self._library_items():
            if _basename(item.get("Path", "")) == name:
                return self.item(item["Id"])
        return None

    def _library_items(self):
        if self._library is None or time.time() - self._library_time > _LIBRARY_TTL:
            data = self._request("/Items", {"Recursive": "true", "IncludeItemTypes": "Movie,Episode,Video",
                                            "Fields": "Path", "EnableImages": "false", "EnableUserData": "false"},
                                 timeout=60)
            self._library = data.get("Items", [])
            self._library_time = time.time()
        return self._library

    def item(self, item_id):
        data = self._request("/Items", {"Ids": item_id, "Fields": "Path,ProviderIds"})
        items = data.get("Items") or []
        return items[0] if items else None

    # --- Tracks ----------------------------------------------------------------------------

    def tracks(self, item, playing_path=""):
        """Subtitle tracks of an item's media source (the one playing when there are several)."""
        info = self._request("/Items/%s/PlaybackInfo" % item["Id"])
        sources = info.get("MediaSources") or []
        if not sources:
            raise JellyfinError("Jellyfin lists no media source for %s" % item.get("Name", item["Id"]))
        source = sources[0]
        wanted = self.id_from_url(playing_path) and _query_value(playing_path, "mediaSourceId")
        name = _basename(playing_path)
        for candidate in sources:
            if candidate.get("Id") == wanted or (name and _basename(candidate.get("Path", "")) == name):
                source = candidate
                break
        result = []
        for stream in source.get("MediaStreams") or []:
            if stream.get("Type") != "Subtitle":
                continue
            codec = (stream.get("Codec") or "").lower()
            usable, reason = classify(codec)
            if usable and stream.get("IsTextSubtitleStream") is False:
                usable, reason = False, "Jellyfin says this track isn't text"
            result.append(Track(
                key="jellyfin:%s:%d" % (source.get("Id", ""), stream["Index"]),
                source="jellyfin",
                language=languages.normalize(stream.get("Language")),
                title=stream.get("Title") or "",
                codec=codec,
                external=bool(stream.get("IsExternal")),
                forced=bool(stream.get("IsForced")),
                hearing_impaired=bool(stream.get("IsHearingImpaired")),
                usable=usable,
                reason=reason,
                location="%s/%s/%d" % (item["Id"], source.get("Id", item["Id"]), stream["Index"]),
                path=stream.get("Path") or "",
            ))
        return result

    def fetch(self, track, timeout=600):
        """Text of a track: ASS for styled sources, SRT for the rest.

        The first fetch of an embedded track makes Jellyfin read the whole video to extract it,
        which takes minutes for a big file; it is cached on the server afterwards.
        """
        item_id, source_id, index = track.location.split("/")
        fmt = "ass" if track.styled else "srt"
        path = "/Videos/%s/%s/Subtitles/%s/0/Stream.%s" % (item_id, source_id, index, fmt)
        return self._request(path, timeout=timeout, raw=True), fmt


def _basename(path):
    path = urllib.parse.unquote((path or "").split("?")[0]).replace("\\", "/")
    return os.path.basename(path).lower()


def _query_value(url, name):
    query = urllib.parse.urlparse(url or "").query
    for key, value in urllib.parse.parse_qsl(query):
        if key.lower() == name.lower():
            return value
    return ""
