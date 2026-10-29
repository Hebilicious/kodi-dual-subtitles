"""Subtitle tracks of the item playing, from Jellyfin or from files next to the video, and the
choice of a primary and a secondary track from preferences."""

from dataclasses import asdict, dataclass

from . import languages

TEXT_CODECS = {"srt", "subrip", "ass", "ssa", "vtt", "webvtt", "mov_text", "text", "sub", "microdvd", "ttml", "smi"}
IMAGE_CODECS = {"pgs", "pgssub", "hdmv_pgs_subtitle", "dvdsub", "dvd_subtitle", "vobsub", "dvbsub", "dvb_subtitle",
                "xsub", "sup"}
CODEC_NAMES = {"subrip": "SRT", "srt": "SRT", "ass": "ASS", "ssa": "SSA", "webvtt": "VTT", "vtt": "VTT",
               "mov_text": "MP4 text", "pgssub": "PGS", "hdmv_pgs_subtitle": "PGS", "pgs": "PGS", "dvdsub": "VobSub",
               "dvd_subtitle": "VobSub", "vobsub": "VobSub", "dvbsub": "DVB"}


@dataclass
class Track:
    key: str  # stable for the item: "jellyfin:3", "file:Movie.th.srt"
    source: str  # "jellyfin" or "file"
    language: str  # two-letter code, "" when unknown
    title: str
    codec: str
    external: bool
    forced: bool = False
    hearing_impaired: bool = False
    usable: bool = True
    reason: str = ""  # why it can't be used (F11)
    location: str = ""  # Jellyfin stream index, or the file's path
    path: str = ""  # the file on the server, for an external track (Bazarr sync)

    @property
    def styled(self):
        return self.codec in ("ass", "ssa")

    def label(self):
        parts = [languages.name(self.language) if self.language else "Unknown language"]
        if self.title and self.title.lower() not in (self.language, languages.name(self.language).lower()):
            parts.append(self.title)
        parts.append(CODEC_NAMES.get(self.codec, self.codec.upper()))
        parts.append("file" if self.external else "embedded")
        if self.forced:
            parts.append("forced")
        if self.hearing_impaired:
            parts.append("SDH")
        return " · ".join(parts)

    def to_dict(self):
        return asdict(self)

    @classmethod
    def from_dict(cls, data):
        return cls(**data)


def classify(codec):
    """(usable, reason) of a codec name from Jellyfin or a file extension."""
    codec = (codec or "").lower()
    if codec in IMAGE_CODECS:
        return False, "image subtitles (%s) can't be drawn as text; Bazarr adds text files for these" % \
            CODEC_NAMES.get(codec, codec.upper())
    if codec and codec not in TEXT_CODECS:
        return False, "unsupported subtitle format (%s)" % codec
    return True, ""


def _rank(track):
    """Sort key among tracks of one language: full dialogue first, then files (Bazarr's, synced to
    the audio) before embedded tracks, then styled ASS before plain text."""
    title = (track.title or "").lower()
    partial = track.forced or any(word in title for word in ("sign", "song", "forced", "commentary"))
    return (partial, track.hearing_impaired, not track.external, not track.styled)


def best_for(tracks, language, exclude=()):
    candidates = [t for t in tracks if t.usable and t.language == language and t.key not in exclude]
    return sorted(candidates, key=_rank)[0] if candidates else None


def choose(tracks, primary_languages, secondary_languages, remembered=None):
    """(primary, secondary) tracks from remembered keys for this file, or else by language order.

    ``remembered`` holds the track keys chosen before for this item, which win when still there.
    """
    by_key = {t.key: t for t in tracks if t.usable}
    remembered = remembered or {}
    primary = by_key.get(remembered.get("primary_key"))
    if primary is None:
        for language in primary_languages:
            primary = best_for(tracks, language)
            if primary:
                break
    secondary = by_key.get(remembered.get("secondary_key"))
    if secondary is not None and primary is not None and secondary.key == primary.key:
        secondary = None
    if secondary is None and primary is not None:
        for language in secondary_languages:
            if language == primary.language:
                continue
            secondary = best_for(tracks, language, exclude={primary.key})
            if secondary:
                break
    return primary, secondary
