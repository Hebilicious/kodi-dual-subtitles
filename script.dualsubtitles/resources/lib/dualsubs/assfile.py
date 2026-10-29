"""Write the one ASS file Kodi draws: both tracks, each with its own style, timing and offset."""

import bisect
import math
from dataclasses import dataclass

from . import subtitles, wrap

# Layouts (F2): both at the bottom with the secondary above (the default), the secondary at the
# top and the primary at the bottom, or the primary alone.
LAYOUTS = ("stacked", "top-bottom", "primary-only")

FONTS = {"th": "Noto Sans Thai", "ja": "Noto Sans JP", "zh": "Noto Sans JP"}
DEFAULT_FONT = "Noto Sans"

_STYLE_FIELDS = ["Name", "Fontname", "Fontsize", "PrimaryColour", "SecondaryColour", "OutlineColour", "BackColour",
                 "Bold", "Italic", "Underline", "StrikeOut", "ScaleX", "ScaleY", "Spacing", "Angle", "BorderStyle",
                 "Outline", "Shadow", "Alignment", "MarginL", "MarginR", "MarginV", "Encoding"]
_STYLE_DEFAULTS = {"Fontname": "Arial", "Fontsize": "20", "PrimaryColour": "&H00FFFFFF", "SecondaryColour": "&H0000FFFF",
                   "OutlineColour": "&H00000000", "BackColour": "&H00000000", "Bold": "0", "Italic": "0",
                   "Underline": "0", "StrikeOut": "0", "ScaleX": "100", "ScaleY": "100", "Spacing": "0", "Angle": "0",
                   "BorderStyle": "1", "Outline": "2", "Shadow": "2", "Alignment": "2", "MarginL": "10",
                   "MarginR": "10", "MarginV": "10", "Encoding": "1"}
# SSA (v4) alignments to the numpad ones of ASS.
_SSA_ALIGNMENT = {"1": "1", "2": "2", "3": "3", "5": "7", "6": "8", "7": "9", "9": "4", "10": "5", "11": "6"}

_HEIGHT = 1080  # Sizes and margins in TrackStyle are pixels of a 1080-line picture.
_WIDTH = 1920
_SIDE_MARGIN = 0.06  # of the width, on each side


@dataclass
class TrackStyle:
    font: str = DEFAULT_FONT
    size: int = 56
    colour: str = "BFBFBF"  # RGB; about 75 % grey, so white text doesn't glare in HDR
    outline: float = 2.5
    outline_colour: str = "000000"
    shadow: float = 1.0
    margin_v: int = 50
    bold: bool = False


@dataclass
class Layer:
    """One track as it goes into the file."""
    subtitle: subtitles.Subtitle
    style: TrackStyle
    offset: int = 0  # milliseconds, added to every cue
    keep_styling: bool = False  # an ASS source drawn with its own styles (F6)


def font_for(language):
    return FONTS.get(language, DEFAULT_FONT)


def ass_colour(rgb, alpha=0):
    rgb = (rgb or "FFFFFF").lstrip("#").upper().rjust(6, "0")[-6:]
    return "&H%02X%s%s%s" % (alpha, rgb[4:6], rgb[2:4], rgb[0:2])


def ass_time(ms):
    ms = max(0, int(round(ms / 10.0)) * 10)
    hours, ms = divmod(ms, 3600000)
    minutes, ms = divmod(ms, 60000)
    seconds, ms = divmod(ms, 1000)
    return "%d:%02d:%02d.%02d" % (hours, minutes, seconds, ms // 10)


def build(primary, secondary=None, layout="stacked", title="Dual subtitles"):
    """Text of the ASS file for a primary and an optional secondary layer."""
    if layout == "primary-only":
        secondary = None
    kept = primary if primary is not None and primary.keep_styling and primary.subtitle.format == "ass" else None
    play_x, play_y = _play_res(kept.subtitle) if kept else (_WIDTH, _HEIGHT)
    scale = play_y / float(_HEIGHT)

    info = [("Title", title), ("ScriptType", "v4.00+"), ("PlayResX", str(play_x)), ("PlayResY", str(play_y)),
            ("WrapStyle", "0"), ("ScaledBorderAndShadow", "yes")]
    if kept:
        for key in ("WrapStyle", "ScaledBorderAndShadow", "YCbCr Matrix", "LayoutResX", "LayoutResY"):
            if key in kept.subtitle.info:
                info = [(k, v) for k, v in info if k != key] + [(key, kept.subtitle.info[key])]

    styles, events = [], []
    primary_cues = []
    if primary is not None:
        if kept:
            prefix = "P-"
            legacy = kept.subtitle.info.get("ScriptType", "").lower() == "v4.00"
            for style in kept.subtitle.styles:
                styles.append(_source_style(style, prefix, legacy))
            by_name = {s.get("Name", ""): s for s in kept.subtitle.styles}
            fallback = kept.subtitle.styles[0].get("Name", "Default") if kept.subtitle.styles else "Default"
            for cue in kept.subtitle.cues:
                name = cue.style if cue.style in by_name else fallback
                _wrap_source_cue(cue, by_name.get(name, {}), play_x)
                events.append(_event(cue, prefix + name, primary.offset, cue.margin_v))
            if not kept.subtitle.styles:
                styles.append(_style_line("P-Default", primary.style, 2, scale))
        else:
            styles.append(_style_line("Primary", primary.style, 2, scale))
            primary_cues = _shifted(_wrapped(subtitles.plain_cues(primary.subtitle), primary.style, scale, play_x),
                                    primary.offset)
            events.extend(_event(cue, "Primary", 0, 0) for cue in primary_cues)

    if secondary is not None:
        alignment = 8 if layout == "top-bottom" else 2
        styles.append(_style_line("Secondary", secondary.style, alignment, scale))
        cues = _shifted(_wrapped(subtitles.plain_cues(secondary.subtitle), secondary.style, scale, play_x),
                        secondary.offset)
        below = _PrimaryLines(primary_cues, primary.style, scale, play_x) if primary is not None else None
        for cue in cues:
            margin = 0
            if layout == "stacked" and primary is not None:
                lines = 1 if kept else below.during(cue)
                margin = _above_primary(lines, primary.style, secondary.style, scale)
            events.append(_event(cue, "Secondary", 0, margin, layer=1))

    events.sort(key=lambda line: line[0])
    out = ["[Script Info]", "; Written by the Kodi dual subtitles add-on"]
    out += ["%s: %s" % pair for pair in info]
    out += ["", "[V4+ Styles]", "Format: " + ", ".join(_STYLE_FIELDS)]
    out += styles
    out += ["", "[Events]", "Format: Layer, Start, End, Style, Name, MarginL, MarginR, MarginV, Effect, Text"]
    out += [line for _, line in events]
    return "\n".join(out) + "\n"


def _play_res(subtitle):
    x = int(float(subtitle.info.get("PlayResX", 0) or 0))
    y = int(float(subtitle.info.get("PlayResY", 0) or 0))
    if not x and not y:
        return 384, 288  # libass's default when a file sets neither
    if not y:
        y = 1024 if x == 1280 else int(round(x * 3 / 4.0))
    if not x:
        x = 1280 if y == 1024 else int(round(y * 4 / 3.0))
    return x, y


def _style_line(name, style, alignment, scale):
    values = {
        "Name": name, "Fontname": style.font, "Fontsize": "%d" % round(style.size * scale),
        "PrimaryColour": ass_colour(style.colour), "SecondaryColour": ass_colour(style.colour),
        "OutlineColour": ass_colour(style.outline_colour), "BackColour": ass_colour("000000", 0x80),
        "Bold": "-1" if style.bold else "0", "Italic": "0", "Underline": "0", "StrikeOut": "0",
        "ScaleX": "100", "ScaleY": "100", "Spacing": "0", "Angle": "0", "BorderStyle": "1",
        "Outline": "%g" % round(style.outline * scale, 2), "Shadow": "%g" % round(style.shadow * scale, 2),
        "Alignment": str(alignment), "MarginL": "%d" % round(_WIDTH * _SIDE_MARGIN * scale),
        "MarginR": "%d" % round(_WIDTH * _SIDE_MARGIN * scale), "MarginV": "%d" % round(style.margin_v * scale),
        "Encoding": "1",
    }
    return "Style: " + ",".join(values[f] for f in _STYLE_FIELDS)


def _source_style(style, prefix, legacy):
    values = dict(_STYLE_DEFAULTS)
    values.update({k: v for k, v in style.items() if k in _STYLE_DEFAULTS})
    if legacy:
        values["Alignment"] = _SSA_ALIGNMENT.get(values["Alignment"], "2")
    values["Name"] = prefix + style.get("Name", "Default").lstrip("*")
    return "Style: " + ",".join(values[f].replace(",", ";") for f in _STYLE_FIELDS)


def _max_em(style, scale, play_x):
    width = play_x * (1 - 2 * _SIDE_MARGIN)
    return width / (style.size * scale) * 0.95


def _wrapped(cues, style, scale, play_x):
    max_em = _max_em(style, scale, play_x)
    for cue in cues:
        if wrap.needs_wrapping(cue.text):
            cue.text = wrap.wrap(cue.text, max_em)
    return cues


def _wrap_source_cue(cue, style, play_x):
    """Wrap a Japanese or Thai line of a kept ASS source, unless it is positioned (a sign)."""
    if not wrap.needs_wrapping(cue.text) or subtitles.is_positioned(cue.text):
        return
    try:
        size = float(style.get("Fontsize", 20))
        margins = (cue.margin_l or float(style.get("MarginL", 10))) + (cue.margin_r or float(style.get("MarginR", 10)))
    except ValueError:
        return
    if size > 0:
        cue.text = wrap.wrap(cue.text, (play_x - margins) / size * 0.95)


def _shifted(cues, offset):
    shifted = []
    for cue in cues:
        start, end = cue.start + offset, cue.end + offset
        if end <= 0:
            continue
        cue.start, cue.end = max(0, start), end
        shifted.append(cue)
    return shifted


def _lines(cue, style, scale, play_x):
    """Lines a cue takes on screen: its breaks, plus the wraps libass will add."""
    max_em = _max_em(style, scale, play_x)
    return sum(max(1, math.ceil(wrap.text_width(part) / max_em)) for part in cue.text.split("\\N"))


class _PrimaryLines:
    """How many primary lines are on screen during a secondary cue (stacked layout).

    At least one, so the secondary line doesn't jump down and up between primary lines.
    """

    def __init__(self, cues, style, scale, play_x):
        ordered = sorted(cues, key=lambda c: c.start)
        self.starts = [c.start for c in ordered]
        self.cues = [(c.start, c.end, _lines(c, style, scale, play_x)) for c in ordered]
        self.longest = max([end - start for start, end, _ in self.cues] or [0])

    def during(self, cue):
        lines = 1
        i = bisect.bisect_left(self.starts, cue.end) - 1
        while i >= 0 and self.cues[i][0] > cue.start - self.longest:
            start, end, count = self.cues[i]
            if end > cue.start:
                lines = max(lines, count)
            i -= 1
        return lines


def _above_primary(lines, primary_style, secondary_style, scale):
    """MarginV that puts a secondary cue just above that many primary lines."""
    line_height = primary_style.size * 1.25 + primary_style.outline * 2
    gap = secondary_style.size * 0.25
    return int(round((primary_style.margin_v + lines * line_height + gap) * scale))


def _event(cue, style, offset, margin_v, layer=None):
    start, end = cue.start + offset, cue.end + offset
    line = "Dialogue: %d,%s,%s,%s,%s,%d,%d,%d,%s,%s" % (
        cue.layer if layer is None else layer, ass_time(start), ass_time(end), style, cue.name.replace(",", " "),
        cue.margin_l, cue.margin_r, margin_v, cue.effect, cue.text)
    return start, line
