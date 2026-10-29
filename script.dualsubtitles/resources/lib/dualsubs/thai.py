"""Thai word boundaries, so a long Thai line can be wrapped between words.

Thai has no spaces between words and libass wraps only at spaces. Words come from ICU's Thai
dictionary (``resources/data/thaidict.txt``, put there by ``build.sh``), by dictionary matching
that prefers the fewest unknown characters, then the fewest words. Without the dictionary, or
for unknown words, lines can still break between character clusters, never inside one.
"""

import os

_LEADING_VOWELS = "เแโใไ"  # เ แ โ ใ ไ: written before their consonant
_FOLLOWING = "ะาำๅๆฯ"  # ะ า ำ ๅ ๆ ฯ: never start a cluster
_MAX_WORD = 20

_words = None
_dictionary_path = os.path.join(os.path.dirname(__file__), "..", "..", "data", "thaidict.txt")


def is_thai(char):
    return "฀" <= char <= "๿"


def _is_mark(char):
    # Vowels above and below, tone marks, thanthakhat: they sit on the consonant before them.
    code = ord(char)
    return code == 0x0E31 or 0x0E34 <= code <= 0x0E3A or 0x0E47 <= code <= 0x0E4E


def can_break_before(run, i):
    """Whether a Thai run may be split before index ``i`` without cutting a character cluster."""
    if i <= 0 or i >= len(run):
        return False
    char, before = run[i], run[i - 1]
    if _is_mark(char) or char in _FOLLOWING or before in _LEADING_VOWELS:
        return False
    return True


def load_words(path=None):
    global _words
    if _words is None or path:
        words = set()
        try:
            with open(path or _dictionary_path, encoding="utf-8-sig") as handle:
                for line in handle:
                    word = line.strip()
                    if word and not word.startswith("#") and is_thai(word[0]):
                        words.add(word)
        except OSError:
            pass
        _words = words
    return _words


def segment(run, words=None):
    """Split a run of Thai characters into words (unknown stretches split at cluster boundaries)."""
    words = load_words() if words is None else words
    prefixes = _prefixes(words)
    n = len(run)
    breaks = [j == n or can_break_before(run, j) for j in range(n + 1)]
    # best[i] = (unknown characters, pieces, previous index) for the best split of run[:i].
    best = [None] * (n + 1)
    best[0] = (0, 0, -1)
    for i in range(n):
        if best[i] is None:
            continue
        unknown, pieces, _ = best[i]
        for j in range(i + 1, min(n, i + _MAX_WORD) + 1):
            candidate = run[i:j]
            if candidate not in prefixes:
                break  # no word starts like this; longer ones won't either
            if breaks[j] and candidate in words:
                _relax(best, j, (unknown, pieces + 1, i))
        # One cluster as an unknown piece.
        j = i + 1
        while not breaks[j]:
            j += 1
        _relax(best, j, (unknown + (j - i), pieces + 1, i))
    pieces, i = [], n
    while i > 0:
        previous = best[i][2]
        pieces.append(run[previous:i])
        i = previous
    pieces.reverse()
    return _merge_unknown(pieces, words)


_prefix_cache = {}


def _prefixes(words):
    """Every beginning of every word (about 5 MB for ICU's dictionary), kept per word set."""
    key = (id(words), len(words))
    if key not in _prefix_cache:
        _prefix_cache.clear()
        _prefix_cache[key] = {word[:k] for word in words for k in range(1, len(word) + 1)}
    return _prefix_cache[key]


def _relax(best, j, candidate):
    if best[j] is None or candidate[:2] < best[j][:2]:
        best[j] = candidate


def _merge_unknown(pieces, words):
    """Join neighbouring unknown clusters, up to a short word's length, so a name stays whole."""
    merged = []
    for piece in pieces:
        if merged and piece not in words and merged[-1] not in words and len(merged[-1]) + len(piece) <= 8:
            merged[-1] += piece
        else:
            merged.append(piece)
    return merged
