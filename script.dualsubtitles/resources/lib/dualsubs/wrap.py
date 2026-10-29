"""Wrap lines in scripts written without spaces (Thai, Japanese, Chinese).

libass wraps only at spaces, so a long Thai or Japanese line would run off the screen. Lines in
those scripts are wrapped here, with ``\\N``, at word boundaries (Thai) or between characters
(Japanese and Chinese, except before closing punctuation). Widths are estimates in em; lines in
other scripts are left to libass.
"""

import re
import unicodedata

from . import thai

# Japanese line-breaking rules (kinsoku): no line starts with these, none ends with the opening ones.
_NO_START = set("、。，．・：；？！?!ー）)」』】〉》〕］｝ゃゅょっぁぃぅぇぉャュョッァィゥェォヮヵヶ〜…‥ゝゞヽヾ々")
_NO_END = set("（(「『【〈《〔［｛")
_TAG = re.compile(r"(\{[^}]*\})")


def is_wide(char):
    return unicodedata.east_asian_width(char) in ("W", "F")


def needs_wrapping(text):
    return any(thai.is_thai(c) or is_wide(c) for c in text)


_widths = {}


def char_width(char):
    """Advance of one character in em, roughly as Noto Sans draws it."""
    width = _widths.get(char)
    if width is None:
        width = _widths[char] = _char_width(char)
    return width


def _char_width(char):
    if char in "​‌‍" or unicodedata.combining(char) or unicodedata.category(char) in ("Mn", "Me"):
        return 0.0
    if thai._is_mark(char):
        return 0.0
    if is_wide(char):
        return 1.0
    if thai.is_thai(char):
        return 0.6
    if char == " " or char == " ":
        return 0.26
    if char.isupper() or char in "mwMW@%":
        return 0.68
    if char in "ijlI.,;:'!|":
        return 0.28
    return 0.55


def text_width(text):
    if "{" in text:
        text = _TAG.sub("", text)
    return sum(map(char_width, text))


def _pieces(text):
    """Break opportunities of one line: a list of (piece, is_space), tags glued to the next piece."""
    pieces = []
    pending_tags = ""
    for part in _TAG.split(text):
        if not part:
            continue
        if part.startswith("{") and part.endswith("}"):
            pending_tags += part
            continue
        for chunk in _split_chunk(part):
            pieces.append(pending_tags + chunk)
            pending_tags = ""
    if pending_tags:
        if pieces:
            pieces[-1] += pending_tags
        else:
            pieces.append(pending_tags)
    return pieces


def _split_chunk(text):
    """Split plain text into unbreakable pieces; a space is a piece of its own."""
    pieces = []
    i, n = 0, len(text)
    while i < n:
        char = text[i]
        if char == " ":
            pieces.append(" ")
            i += 1
        elif thai.is_thai(char):
            j = i
            while j < n and (thai.is_thai(text[j]) or text[j] in "​"):
                j += 1
            run = text[i:j].replace("​", "")
            pieces.extend(thai.segment(run))
            i = j
        elif is_wide(char):
            pieces.append(char)
            i += 1
        else:
            j = i
            while j < n and text[j] != " " and not thai.is_thai(text[j]) and not is_wide(text[j]):
                j += 1
            pieces.append(text[i:j])
            i = j
    # Glue pieces that must not start a line to the piece before, and opening ones to the next.
    glued = []
    for piece in pieces:
        if glued and glued[-1] != " " and piece != " " and (piece[0] in _NO_START or glued[-1][-1] in _NO_END
                                                           or not _breakable_between(glued[-1], piece)):
            glued[-1] += piece
        else:
            glued.append(piece)
    return glued


def _breakable_between(left, right):
    """Whether a line may break between two pieces written without a space.

    Latin words and numbers stay together ("100%", "TV!"). Japanese breaks before kanji,
    katakana and punctuation, but not before hiragana, which ends the phrase before it (短|い),
    nor inside a katakana word.
    """
    a, b = left[-1], right[0]
    if (is_hiragana(b) and is_wide(a)) or (is_katakana(a) and is_katakana(b)):
        return False
    if thai.is_thai(a) or thai.is_thai(b) or is_wide(a) or is_wide(b):
        return True
    return False


def is_hiragana(char):
    return "\u3041" <= char <= "\u309f"


def wrap_line(line, max_em):
    """``line`` with ``\\N`` inserted so no part is wider than ``max_em``, lines kept even."""
    total = text_width(line)
    if total <= max_em or not needs_wrapping(line):
        return line
    pieces = _pieces(line)
    count = int(total // max_em) + 1
    target = min(max_em, total / count * 1.08)
    lines, current, width = [], [], 0.0
    for piece in pieces:
        piece_width = text_width(piece)
        if piece_width > max_em and len(piece) > 1:
            # A phrase longer than a line (a long hiragana run): break it anywhere.
            for char in piece:
                current, width = _add(lines, current, width, char, text_width(char), target, count, max_em)
            continue
        if piece == " ":
            if current:
                current.append(piece)
                width += piece_width
            continue
        current, width = _add(lines, current, width, piece, piece_width, target, count, max_em)
    if current:
        lines.append("".join(current).rstrip())
    return "\\N".join(line for line in lines if line)


_wrapped = {}


def wrap(text, max_em):
    """Wrap every ``\\N``-separated line of an ASS text.

    Results are kept for the process, so rebuilding after an offset or layout change (the dialog
    nudges timing live) doesn't segment the Thai text again.
    """
    key = (text, round(max_em, 2))
    result = _wrapped.get(key)
    if result is None:
        if len(_wrapped) > 20000:
            _wrapped.clear()
        result = _wrapped[key] = "\\N".join(wrap_line(line, max_em) for line in text.split("\\N"))
    return result


def _add(lines, current, width, piece, piece_width, target, count, max_em):
    """Put a piece on the current line, or start a new line with it."""
    over_target = width + piece_width > target and len(lines) < count - 1
    if current and (over_target or width + piece_width > max_em):
        lines.append("".join(current).rstrip())
        current, width = [], 0.0
    current.append(piece)
    return current, width + piece_width


def is_katakana(char):
    return "゠" <= char <= "ヿ"
