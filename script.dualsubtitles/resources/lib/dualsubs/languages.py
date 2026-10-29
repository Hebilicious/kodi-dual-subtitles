"""Language codes: Jellyfin and Kodi say "tha", "Thai" or "th-TH"; everything here uses "th"."""

# ISO 639-1 code -> (English name, ISO 639-2 codes, bibliographic and terminological).
LANGUAGES = {
    "ar": ("Arabic", ("ara",)),
    "bg": ("Bulgarian", ("bul",)),
    "ca": ("Catalan", ("cat",)),
    "cs": ("Czech", ("cze", "ces")),
    "da": ("Danish", ("dan",)),
    "de": ("German", ("ger", "deu")),
    "el": ("Greek", ("gre", "ell")),
    "en": ("English", ("eng",)),
    "es": ("Spanish", ("spa",)),
    "et": ("Estonian", ("est",)),
    "fa": ("Persian", ("per", "fas")),
    "fi": ("Finnish", ("fin",)),
    "fil": ("Filipino", ("fil", "tgl")),
    "fr": ("French", ("fre", "fra")),
    "he": ("Hebrew", ("heb",)),
    "hi": ("Hindi", ("hin",)),
    "hr": ("Croatian", ("hrv",)),
    "hu": ("Hungarian", ("hun",)),
    "id": ("Indonesian", ("ind",)),
    "is": ("Icelandic", ("ice", "isl")),
    "it": ("Italian", ("ita",)),
    "ja": ("Japanese", ("jpn",)),
    "km": ("Khmer", ("khm",)),
    "ko": ("Korean", ("kor",)),
    "lo": ("Lao", ("lao",)),
    "lt": ("Lithuanian", ("lit",)),
    "lv": ("Latvian", ("lav",)),
    "ms": ("Malay", ("may", "msa")),
    "my": ("Burmese", ("bur", "mya")),
    "nl": ("Dutch", ("dut", "nld")),
    "no": ("Norwegian", ("nor", "nob", "nno")),
    "pl": ("Polish", ("pol",)),
    "pt": ("Portuguese", ("por",)),
    "ro": ("Romanian", ("rum", "ron")),
    "ru": ("Russian", ("rus",)),
    "sk": ("Slovak", ("slo", "slk")),
    "sl": ("Slovenian", ("slv",)),
    "sr": ("Serbian", ("srp",)),
    "sv": ("Swedish", ("swe",)),
    "th": ("Thai", ("tha",)),
    "tr": ("Turkish", ("tur",)),
    "uk": ("Ukrainian", ("ukr",)),
    "vi": ("Vietnamese", ("vie",)),
    "zh": ("Chinese", ("chi", "zho", "cmn", "yue")),
}

_BY_ALIAS = {}
for _code, (_name, _codes) in LANGUAGES.items():
    _BY_ALIAS[_code] = _code
    _BY_ALIAS[_name.lower()] = _code
    for _alias in _codes:
        _BY_ALIAS[_alias] = _code
# Names some files and servers use instead of the code.
_BY_ALIAS.update({"jp": "ja", "jap": "ja", "cn": "zh", "chs": "zh", "cht": "zh", "pob": "pt", "pb": "pt"})


def normalize(value):
    """Two-letter code for a code or name, "" when unknown or empty."""
    if not value:
        return ""
    value = value.strip().lower().replace("_", "-")
    if value in _BY_ALIAS:
        return _BY_ALIAS[value]
    base = value.split("-")[0]  # "th-th", "pt-br", "zh-hans"
    return _BY_ALIAS.get(base, "")


def name(code):
    """English name of a two-letter code, or the code itself."""
    entry = LANGUAGES.get(code)
    return entry[0] if entry else (code or "Unknown")


def parse_list(text):
    """"th, en" or "Thai,English" -> ["th", "en"], unknown entries dropped."""
    codes = []
    for part in (text or "").replace(";", ",").split(","):
        code = normalize(part)
        if code and code not in codes:
            codes.append(code)
    return codes
