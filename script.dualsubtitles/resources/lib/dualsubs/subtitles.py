"""Read subtitle files (SRT, WebVTT, ASS/SSA) into cues.

Every cue's text is ASS text: override tags in braces are allowed and ``\\N`` breaks a line, so
SRT and ASS sources go through the same writer (``assfile.py``).
"""

import re
from dataclasses import dataclass, field


@dataclass
class Cue:
    start: int  # milliseconds
    end: int
    text: str
    style: str = "Default"
    layer: int = 0
    name: str = ""
    margin_l: int = 0
    margin_r: int = 0
    margin_v: int = 0
    effect: str = ""


@dataclass
class Subtitle:
    format: str  # "srt", "vtt" or "ass"
    cues: list
    # ASS only: [Script Info] fields and the styles, each style a dict of its Format fields.
    info: dict = field(default_factory=dict)
    styles: list = field(default_factory=list)

    @property
    def styled(self):
        """An ASS file with styling worth keeping (more than one style, or positioned signs)."""
        return self.format == "ass" and (len(self.styles) > 1 or any(_POSITIONED.search(c.text) for c in self.cues))


class SubtitleError(Exception):
    pass


def decode(data, language=""):
    """Text of a subtitle file. Thai and Japanese files without a BOM are often not UTF-8."""
    if data.startswith(b"\xef\xbb\xbf"):
        return data[3:].decode("utf-8", "replace")
    if data.startswith((b"\xff\xfe", b"\xfe\xff")):
        return data.decode("utf-16", "replace")
    try:
        return data.decode("utf-8")
    except UnicodeDecodeError:
        pass
    legacy = {"th": "cp874", "ja": "cp932", "zh": "gb18030", "ko": "cp949", "ru": "cp1251", "el": "cp1253",
              "ar": "cp1256", "he": "cp1255", "tr": "cp1254", "vi": "cp1258"}.get(language, "cp1252")
    try:
        return data.decode(legacy)
    except UnicodeDecodeError:
        return data.decode("latin-1")


def parse(text, hint=""):
    """Cues of a subtitle file; the format comes from the content, then ``hint`` ("srt", "ass", "vtt")."""
    text = text.lstrip("\ufeff").replace("\r\n", "\n").replace("\r", "\n")
    head = text.lstrip()[:200].lower()
    if head.startswith("[script info]") or "[v4+ styles]" in text[:5000].lower() or hint in ("ass", "ssa"):
        subtitle = parse_ass(text)
    elif head.startswith("webvtt") or hint == "vtt":
        subtitle = parse_vtt(text)
    else:
        subtitle = parse_srt(text)
    if not subtitle.cues:
        raise SubtitleError("no subtitle lines found")
    return subtitle


# --- SRT and WebVTT -------------------------------------------------------------------------

_TIMING = re.compile(
    r"(?:(\d+):)?(\d{1,2}):(\d{2})[,.](\d{1,3})\s*-->\s*(?:(\d+):)?(\d{1,2}):(\d{2})[,.](\d{1,3})"
)
_HTML_TAG = re.compile(r"<(/?)([a-zA-Z]+)[^>]*>")
_VTT_TAG = re.compile(r"</?(?:c|v|lang|ruby|rt)(?:[.\s][^>]*)?>")


def _ms(hours, minutes, seconds, fraction):
    fraction = (fraction or "0").ljust(3, "0")[:3]
    return ((int(hours or 0) * 60 + int(minutes)) * 60 + int(seconds)) * 1000 + int(fraction)


def _html_to_ass(line):
    """SRT keeps <i>, <b> and <u>; other tags (font colours) give way to our style."""

    def tag(match):
        closing, name = match.group(1), match.group(2).lower()
        if name in ("i", "b", "u"):
            return "{\\%s%d}" % (name, 0 if closing else 1)
        return ""

    line = _HTML_TAG.sub(tag, line)
    return line.replace("&amp;", "&").replace("&lt;", "<").replace("&gt;", ">").replace("&nbsp;", "\\h")


def _cues_from_blocks(text, vtt=False):
    cues = []
    lines = text.split("\n")
    i = 0
    while i < len(lines):
        match = _TIMING.search(lines[i])
        if not match:
            i += 1
            continue
        g = match.groups()
        start, end = _ms(*g[0:4]), _ms(*g[4:8])
        i += 1
        body = []
        while i < len(lines) and lines[i].strip() and not _TIMING.search(lines[i]):
            body.append(lines[i].strip())
            i += 1
        # A number line directly before the next timing belongs to the next cue (SRT counters).
        if body and i < len(lines) and _TIMING.search(lines[i]) and body[-1].isdigit():
            body.pop()
        if vtt:
            body = [_VTT_TAG.sub("", line) for line in body]
        text_ass = "\\N".join(_html_to_ass(line) for line in body).strip()
        if text_ass and end > start:
            cues.append(Cue(start, end, text_ass))
    return cues


def parse_srt(text):
    return Subtitle("srt", _cues_from_blocks(text))


def parse_vtt(text):
    # Drop NOTE, STYLE and REGION blocks, which have no timing line but may contain "-->"-free text.
    return Subtitle("vtt", _cues_from_blocks(text, vtt=True))


# --- ASS / SSA ------------------------------------------------------------------------------

_POSITIONED = re.compile(r"\\(?:pos|move|org|clip|iclip|p[1-9])\b")
_ASS_TIME = re.compile(r"(\d+):(\d{1,2}):(\d{1,2})[.:](\d{1,3})")


def _ass_ms(value):
    match = _ASS_TIME.match(value.strip())
    if not match:
        raise ValueError(value)
    h, m, s, frac = match.groups()
    # Centiseconds per the spec ("0:01:02.50"); some writers use milliseconds.
    return ((int(h) * 60 + int(m)) * 60 + int(s)) * 1000 + int(frac.ljust(3, "0")[:3])


def _int(value):
    try:
        return int(float(value))
    except (TypeError, ValueError):
        return 0


def parse_ass(text):
    info, styles, cues = {}, [], []
    section = ""
    style_format = event_format = None
    for raw in text.split("\n"):
        line = raw.strip()
        if not line or line.startswith(";"):
            continue
        if line.startswith("[") and line.endswith("]"):
            section = line[1:-1].strip().lower()
            continue
        key, _, value = line.partition(":")
        key, value = key.strip(), value.strip()
        if section == "script info":
            if key and not key.startswith("!"):
                info[key] = value
        elif section in ("v4+ styles", "v4 styles", "v4 styles+"):
            if key.lower() == "format":
                style_format = [f.strip() for f in value.split(",")]
            elif key.lower() == "style" and style_format:
                values = [v.strip() for v in value.split(",", len(style_format) - 1)]
                styles.append(dict(zip(style_format, values)))
        elif section == "events":
            if key.lower() == "format":
                event_format = [f.strip().lower() for f in value.split(",")]
            elif key.lower() == "dialogue":
                fields = event_format or ["layer", "start", "end", "style", "name", "marginl", "marginr",
                                          "marginv", "effect", "text"]
                values = value.split(",", len(fields) - 1)
                if len(values) < len(fields):
                    continue
                event = dict(zip(fields, values))
                try:
                    start, end = _ass_ms(event["start"]), _ass_ms(event["end"])
                except (KeyError, ValueError):
                    continue
                if end <= start:
                    continue
                cues.append(Cue(
                    start, end, event.get("text", ""),
                    style=event.get("style", "Default").strip().lstrip("*") or "Default",
                    layer=_int(event.get("layer", event.get("marked", 0))),
                    name=event.get("name", event.get("actor", "")),
                    margin_l=_int(event.get("marginl")),
                    margin_r=_int(event.get("marginr")),
                    margin_v=_int(event.get("marginv")),
                    effect=event.get("effect", ""),
                ))
    return Subtitle("ass", cues, info, styles)


# --- Flattening -----------------------------------------------------------------------------

# Style names of lines that aren't dialogue: signs, songs, karaoke, titles, translator notes.
_NON_DIALOGUE_STYLE = re.compile(r"sign|song|lyric|kara|\bop\b|\bed\b|^op|^ed|opening|ending|title|note|insert|screen",
                                 re.IGNORECASE)
_OVERRIDE = re.compile(r"\{[^}]*\}")
_KEEP_TAGS = re.compile(r"\\([ibu])([01])")


def plain_cues(subtitle):
    """Dialogue only, as plain text with italics: for a track drawn in our own style.

    Signs, songs and positioned or drawn lines are left out, and the copies an ASS file stacks
    for its outline effects are merged.
    """
    if subtitle.format != "ass":
        return [Cue(c.start, c.end, c.text) for c in subtitle.cues]
    seen, cues = set(), []
    for cue in subtitle.cues:
        if _NON_DIALOGUE_STYLE.search(cue.style) or _POSITIONED.search(cue.text) or cue.effect.strip():
            continue
        text = _OVERRIDE.sub(_kept_tags, cue.text).replace("\\n", " ").strip()
        text = re.sub(r"(\\N)+$", "", re.sub(r"^(\\N)+", "", text))
        if not _OVERRIDE.sub("", text).replace("\\N", "").replace("\\h", "").strip():
            continue
        key = (cue.start, cue.end, text)
        if key in seen:
            continue
        seen.add(key)
        cues.append(Cue(cue.start, cue.end, text))
    cues.sort(key=lambda c: (c.start, c.end))
    return cues


def _kept_tags(match):
    tags = "".join("\\%s%s" % pair for pair in _KEEP_TAGS.findall(match.group(0)))
    return "{%s}" % tags if tags else ""


def strip_tags(text):
    """Visible text of an ASS text: no override blocks, ``\\N`` as newlines."""
    return _OVERRIDE.sub("", text).replace("\\N", "\n").replace("\\n", " ").replace("\\h", "\u00a0")


def is_positioned(text):
    """A line placed or drawn by its own tags (\\pos, \\move, \\clip, drawings): a sign, not dialogue."""
    return bool(_POSITIONED.search(text))
