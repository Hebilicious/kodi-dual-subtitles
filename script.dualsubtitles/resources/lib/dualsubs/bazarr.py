"""Bazarr: re-sync one subtitle file to the video's audio on the server (F10)."""

import json
import posixpath
import urllib.error
import urllib.parse
import urllib.request


class BazarrError(Exception):
    pass


class Bazarr:
    def __init__(self, url, api_key, timeout=20):
        self.url = (url or "").rstrip("/")
        self.api_key = api_key or ""
        self.timeout = timeout

    @property
    def configured(self):
        return bool(self.url and self.api_key)

    def _request(self, path, query=None, method="GET", timeout=None):
        if not self.configured:
            raise BazarrError("Bazarr address or API key not set in the add-on settings")
        url = self.url + "/api/" + path
        if query:
            url += "?" + urllib.parse.urlencode(query, doseq=True)
        request = urllib.request.Request(url, method=method, headers={"X-API-KEY": self.api_key})
        try:
            with urllib.request.urlopen(request, timeout=timeout or self.timeout) as response:
                body = response.read()
        except urllib.error.HTTPError as error:
            detail = error.read().decode("utf-8", "replace")[:200]
            raise BazarrError("Bazarr answered %d: %s" % (error.code, detail))
        except (urllib.error.URLError, OSError) as error:
            raise BazarrError("can't reach Bazarr at %s (%s)" % (self.url, getattr(error, "reason", error)))
        try:
            return json.loads(body.decode("utf-8")) if body else {}
        except ValueError:
            return {}

    def find(self, subtitle_path, video_path, is_episode):
        """(media type, Bazarr id, subtitle entry) for a subtitle file Bazarr knows."""
        if is_episode:
            series_folder = posixpath.dirname(posixpath.dirname(video_path))
            for series in self._request("series").get("data", []):
                if posixpath.normpath(series.get("path", "")) in (series_folder, posixpath.dirname(video_path)):
                    episodes = self._request("episodes", {"seriesid[]": series["sonarrSeriesId"]}).get("data", [])
                    for episode in episodes:
                        entry = _subtitle_in(episode, subtitle_path)
                        if entry:
                            return "episode", episode["sonarrEpisodeId"], entry
        else:
            for movie in self._request("movies").get("data", []):
                entry = _subtitle_in(movie, subtitle_path)
                if entry:
                    return "movie", movie["radarrId"], entry
        raise BazarrError("Bazarr doesn't manage %s" % posixpath.basename(subtitle_path))

    def sync(self, subtitle_path, video_path, language, is_episode):
        """Ask Bazarr to align the file to the audio; returns once it's done (it takes a minute)."""
        kind, media_id, entry = self.find(subtitle_path, video_path, is_episode)
        self._request("subtitles", {
            "action": "sync", "language": entry.get("code2") or language, "path": entry["path"], "type": kind,
            "id": media_id, "forced": str(bool(entry.get("forced"))), "hi": str(bool(entry.get("hi"))),
        }, method="PATCH", timeout=600)


def _subtitle_in(media, subtitle_path):
    name = posixpath.basename(subtitle_path)
    for entry in media.get("subtitles") or []:
        path = entry.get("path") or ""
        if path and (path == subtitle_path or posixpath.basename(path) == name):
            return entry
    return None
