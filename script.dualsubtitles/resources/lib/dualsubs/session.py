"""The two tracks of the video playing: finding them, choosing, fetching, and loading the
generated file into Kodi.

The service (auto-apply on playback start) and the script (dialog, agent calls) run in separate
Python interpreters, so the state of the video playing is kept in a JSON file in Kodi's temp
folder and fetched tracks are cached there.

Everything Kodi-specific goes through ``kodi`` (``kodiapi.Kodi``, or a fake in the tests).
"""

import hashlib
import json
import os
import time
import uuid

from . import assfile, jellyfin, languages, localfiles, prefs, subtitles, tracks
from .bazarr import Bazarr, BazarrError
from .jellyfin import JellyfinError
from .subtitles import SubtitleError

STATE_FILE = "session.json"


class NotPlaying(Exception):
    pass


class TrackError(Exception):
    """A track that can't be shown, with the reason for the viewer (F11)."""


class Superseded(Exception):
    """Another apply for the same video started after this one."""


class Session:
    def __init__(self, kodi, playing):
        self.kodi = kodi
        self.playing = playing
        self.item = {}  # Jellyfin item: Id, Name, Type, SeriesName, Path
        self.title = ""  # show or film name
        self.episode = False
        self.tracks = []
        self.primary_key = ""
        self.secondary_key = ""
        self.layout = kodi.setting("layout") or "stacked"
        self.offsets = {}  # track key -> ms
        self.keep_styling = kodi.setting_bool("primary_keep_styling")
        self.active = False
        self.generation = 0
        self.token = ""
        self.warnings = []  # why sources were skipped, for the dialog
        self.store = prefs.Store(os.path.join(kodi.profile_dir, "prefs.json"))

    # --- State ------------------------------------------------------------------------------

    @classmethod
    def current(cls, kodi, rediscover=False):
        """Session of the video playing, from the saved state when it is about the same file."""
        playing = kodi.playing_file()
        if not playing:
            raise NotPlaying("nothing is playing")
        session = cls(kodi, playing)
        state = _read_json(os.path.join(kodi.temp_dir, STATE_FILE))
        if not rediscover and state.get("playing") == playing:
            session._restore(state)
        else:
            session.discover()
        return session

    def _restore(self, state):
        self.item = state.get("item") or {}
        self.title = state.get("title", "")
        self.episode = bool(state.get("episode"))
        self.tracks = [tracks.Track.from_dict(t) for t in state.get("tracks", [])]
        self.primary_key = state.get("primary_key", "")
        self.secondary_key = state.get("secondary_key", "")
        self.layout = state.get("layout", self.layout)
        self.offsets = {k: int(v) for k, v in (state.get("offsets") or {}).items()}
        self.keep_styling = state.get("keep_styling", self.keep_styling)
        self.active = bool(state.get("active"))
        self.generation = int(state.get("generation", 0))
        self.token = state.get("token", "")
        self.warnings = state.get("warnings", [])

    def save_state(self):
        os.makedirs(self.kodi.temp_dir, exist_ok=True)
        state = {
            "playing": self.playing, "item": self.item, "title": self.title, "episode": self.episode,
            "tracks": [t.to_dict() for t in self.tracks], "primary_key": self.primary_key,
            "secondary_key": self.secondary_key, "layout": self.layout, "offsets": self.offsets,
            "keep_styling": self.keep_styling, "active": self.active, "generation": self.generation,
            "token": self.token, "warnings": self.warnings, "time": time.time(),
        }
        _write_json(os.path.join(self.kodi.temp_dir, STATE_FILE), state)

    @property
    def title_key(self):
        return prefs.title_key(self.title if self.episode else "", self.title)

    @property
    def file_key(self):
        if self.item.get("Id"):
            return "jellyfin:" + self.item["Id"]
        return "path:" + localfiles.split_path(self.playing)[1].lower()

    def track(self, key):
        return next((t for t in self.tracks if t.key == key), None)

    @property
    def primary(self):
        return self.track(self.primary_key)

    @property
    def secondary(self):
        return self.track(self.secondary_key)

    # --- Finding the tracks -----------------------------------------------------------------

    def discover(self):
        """Tracks of the video playing: Jellyfin's when it knows the item, else files beside it."""
        self.warnings = []
        server = self.jellyfin()
        if server.configured:
            try:
                item = server.find_item(self.playing)
                if item:
                    self.item = {k: item.get(k) for k in ("Id", "Name", "Type", "SeriesName", "Path")}
                    self.tracks = server.tracks(item, self.playing)
                else:
                    self.warnings.append("Jellyfin doesn't know this file; using the files next to it")
            except JellyfinError as error:
                self.warnings.append(str(error))
        if not self.item:
            self.tracks = localfiles.find(self.playing, self.kodi.listdir)
        info = self.kodi.video_info()
        self.episode = bool(info.get("show")) or self.item.get("Type") == "Episode"
        self.title = self.item.get("SeriesName") or info.get("show") or self.item.get("Name") or info.get("title") \
            or localfiles.split_path(self.playing)[1]
        remembered = self.store.file(self.file_key)
        self.offsets = {k: int(v) for k, v in (remembered.get("offsets") or {}).items()}
        self.token = uuid.uuid4().hex

    def jellyfin(self):
        return jellyfin.Jellyfin(self.kodi.setting("jellyfin_url"), self.kodi.setting("jellyfin_api_key"),
                                 device_id=self.kodi.device_id, version=self.kodi.version)

    def bazarr(self):
        return Bazarr(self.kodi.setting("bazarr_url"), self.kodi.setting("bazarr_api_key"))

    # --- Choosing ---------------------------------------------------------------------------

    def choose(self, primary_language=None, secondary_language=None, layout=None):
        """Pick tracks: languages given (agent), or remembered for the file, the title, or the defaults.

        Returns False when no track matches.
        """
        title_pref = self.store.title(self.title_key)
        file_pref = self.store.file(self.file_key)
        if primary_language is not None or secondary_language is not None:
            primary_order = [primary_language] if primary_language else []
            secondary_order = [secondary_language] if secondary_language else []
            file_pref = {}
        else:
            primary_order = _order(title_pref.get("primary"), self.kodi.setting("primary_languages"))
            secondary_order = _order(title_pref.get("secondary"), self.kodi.setting("secondary_languages"))
            if "secondary" in title_pref and not title_pref["secondary"]:
                secondary_order = []  # this title was set to one track
        primary, secondary = tracks.choose(self.tracks, primary_order, secondary_order, file_pref)
        if file_pref and file_pref.get("secondary_key") == "":
            secondary = None
        self.layout = layout or title_pref.get("layout") or self.kodi.setting("layout") or "stacked"
        self.primary_key = primary.key if primary else ""
        self.secondary_key = secondary.key if secondary else ""
        return primary is not None

    def remember(self):
        primary, secondary = self.primary, self.secondary
        self.store.set_title(self.title_key, primary.language if primary else "",
                             secondary.language if secondary else "", self.layout)
        self.store.set_file(self.file_key, self.primary_key, self.secondary_key, self.offsets)
        self.store.save()

    # --- Fetching ---------------------------------------------------------------------------

    def _cache_path(self, track):
        digest = hashlib.sha1((self.file_key + "|" + track.key).encode("utf-8")).hexdigest()[:16]
        return os.path.join(self.kodi.temp_dir, "cache", digest)

    def load(self, track, progress=None):
        """Parsed text of a track, fetched once per video and kept in Kodi's temp folder."""
        if not track.usable:
            raise TrackError("%s: %s" % (track.label(), track.reason))
        cache = self._cache_path(track)
        cached = _read_json(cache + ".json")
        if cached.get("key") == track.key and os.path.exists(cache + ".txt"):
            with open(cache + ".txt", encoding="utf-8") as handle:
                text, fmt = handle.read(), cached.get("format", "")
        else:
            text, fmt = self._fetch(track, progress)
            os.makedirs(os.path.dirname(cache), exist_ok=True)
            with open(cache + ".txt", "w", encoding="utf-8") as handle:
                handle.write(text)
            _write_json(cache + ".json", {"key": track.key, "format": fmt})
        try:
            return subtitles.parse(text, fmt)
        except SubtitleError as error:
            raise TrackError("%s: %s" % (track.label(), error))

    def _fetch(self, track, progress):
        if track.source == "jellyfin":
            if progress and not track.external:
                progress("Jellyfin is extracting %s from the video (first time only)" %
                         languages.name(track.language))
            try:
                data, fmt = self.jellyfin().fetch(track, timeout=int(self.kodi.setting("fetch_timeout") or 600))
            except JellyfinError as error:
                raise TrackError("%s: download failed: %s" % (track.label(), error))
        else:
            try:
                data = self.kodi.read_file(track.location)
            except OSError as error:
                raise TrackError("%s: can't read the file: %s" % (track.label(), error))
            fmt = track.codec
        return subtitles.decode(data, track.language), fmt

    def forget_cache(self, track):
        for suffix in (".txt", ".json"):
            try:
                os.remove(self._cache_path(track) + suffix)
            except OSError:
                pass

    # --- Applying ---------------------------------------------------------------------------

    def style(self, role, language):
        prefix = "primary_" if role == "primary" else "secondary_"
        return assfile.TrackStyle(
            font=assfile.font_for(language),
            size=int(self.kodi.setting(prefix + "size") or 56),
            colour=self.kodi.setting(prefix + "colour") or "BFBFBF",
            outline=float(self.kodi.setting(prefix + "outline") or 2.5),
            margin_v=int(self.kodi.setting(prefix + "margin") or 50),
        )

    def build(self, progress=None):
        """Text of the ASS file for the current choice."""
        primary, secondary = self.primary, self.secondary
        if primary is None:
            raise TrackError("no primary track chosen")
        primary_layer = assfile.Layer(self.load(primary, progress), self.style("primary", primary.language),
                                      self.offsets.get(primary.key, 0), self.keep_styling)
        secondary_layer = None
        if secondary is not None and self.layout != "primary-only":
            secondary_layer = assfile.Layer(self.load(secondary, progress),
                                            self.style("secondary", secondary.language),
                                            self.offsets.get(secondary.key, 0))
        return assfile.build(primary_layer, secondary_layer, self.layout, title=self.describe())

    def apply(self, progress=None, remember=True):
        """Build the file and load it into the player; the video keeps playing (F8)."""
        started = time.time()
        text = self.build(progress)
        if self.kodi.playing_file() != self.playing:
            raise NotPlaying("the video changed")
        state = _read_json(os.path.join(self.kodi.temp_dir, STATE_FILE))
        if state.get("playing") == self.playing and state.get("token") != self.token and \
                state.get("time", 0) > started and state.get("active"):
            raise Superseded("another change was applied meanwhile")
        self.generation += 1
        path = os.path.join(self.kodi.temp_dir, "Dual subtitles %d.ass" % self.generation)
        with open(path, "w", encoding="utf-8") as handle:
            handle.write(text)
        self.kodi.load_subtitles(path)
        self._remove_old_files(path)
        self.active = True
        self.save_state()
        if remember:
            self.remember()
        self.kodi.set_status(self.status())
        self.kodi.log("applied %s in %d ms" % (self.describe(), (time.time() - started) * 1000))
        return path

    def off(self):
        self.kodi.hide_subtitles()
        self.active = False
        self.save_state()
        self.kodi.set_status(self.status())

    def _remove_old_files(self, keep):
        for name in os.listdir(self.kodi.temp_dir):
            path = os.path.join(self.kodi.temp_dir, name)
            if name.startswith("Dual subtitles ") and name.endswith(".ass") and path != keep:
                try:
                    os.remove(path)
                except OSError:
                    pass

    # --- Sync (F10) -------------------------------------------------------------------------

    def sync(self, track):
        """Have Bazarr re-sync a subtitle file to the audio, then reload it."""
        if not (track.external and track.path):
            raise TrackError("only subtitle files on the server can be synced; %s is inside the video"
                             % track.label())
        try:
            self.bazarr().sync(track.path, self.item.get("Path") or "", track.language, self.episode)
        except BazarrError as error:
            raise TrackError("sync failed: %s" % error)
        self.forget_cache(track)
        self.offsets.pop(track.key, None)

    # --- Describing -------------------------------------------------------------------------

    def describe(self):
        """"Thai + English": the top (secondary) language first, as on screen."""
        primary, secondary = self.primary, self.secondary
        names = []
        if secondary is not None and self.layout != "primary-only":
            names.append(languages.name(secondary.language))
        if primary is not None:
            names.append(languages.name(primary.language))
        return " + ".join(names) or "no subtitles"

    def status(self):
        def track_status(track):
            if track is None:
                return None
            return {"key": track.key, "language": track.language, "label": track.label(),
                    "offset_ms": self.offsets.get(track.key, 0)}

        return {"state": "applied" if self.active else "off", "title": self.title, "playing": public_path(self.playing),
                "primary": track_status(self.primary), "secondary": track_status(self.secondary),
                "layout": self.layout, "warnings": self.warnings, "time": int(time.time())}


def _order(remembered, setting):
    order = [remembered] if remembered else []
    return order + [code for code in languages.parse_list(setting) if code not in order]


def _read_json(path):
    try:
        with open(path, encoding="utf-8") as handle:
            return json.load(handle)
    except (OSError, ValueError):
        return {}


def _write_json(path, data):
    temporary = path + ".tmp"
    with open(temporary, "w", encoding="utf-8") as handle:
        json.dump(data, handle, ensure_ascii=False)
    os.replace(temporary, path)


def public_path(path):
    """A playing path without what may carry a key: Kodi's "|header=…" suffix and the query."""
    return path.split("|")[0].split("?")[0]
