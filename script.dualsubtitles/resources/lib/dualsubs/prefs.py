"""Remembered choices (F4): the language pair and layout per show or film, offsets per file.

Stored as JSON in the add-on's profile folder:

    {"titles":  {"show:frieren": {"primary": "en", "secondary": "th", "layout": "stacked"}},
     "files":   {"<file key>": {"primary_key": "jellyfin:…:3", "secondary_key": "…",
                                "offsets": {"jellyfin:…:3": -2000}}}}

The global default (language order and layout) is in the add-on settings.
"""

import json
import os
import re
import time

_MAX_FILES = 2000  # oldest file entries are dropped past this


def title_key(show, film):
    """"show:<name>" for an episode, "film:<name>" for anything else."""
    if show:
        return "show:" + _slug(show)
    return "film:" + _slug(film) if film else ""


def _slug(text):
    return re.sub(r"\s+", " ", (text or "").strip().lower())


class Store:
    def __init__(self, path):
        self.path = path
        self.data = {"titles": {}, "files": {}}
        try:
            with open(path, encoding="utf-8") as handle:
                loaded = json.load(handle)
            self.data["titles"].update(loaded.get("titles", {}))
            self.data["files"].update(loaded.get("files", {}))
        except (OSError, ValueError):
            pass

    def save(self):
        files = self.data["files"]
        if len(files) > _MAX_FILES:
            for key in sorted(files, key=lambda k: files[k].get("time", 0))[: len(files) - _MAX_FILES]:
                del files[key]
        os.makedirs(os.path.dirname(self.path), exist_ok=True)
        temporary = self.path + ".tmp"
        with open(temporary, "w", encoding="utf-8") as handle:
            json.dump(self.data, handle, ensure_ascii=False, indent=1, sort_keys=True)
        os.replace(temporary, self.path)

    def title(self, key):
        return dict(self.data["titles"].get(key, {})) if key else {}

    def set_title(self, key, primary, secondary, layout):
        if key:
            self.data["titles"][key] = {"primary": primary or "", "secondary": secondary or "", "layout": layout}

    def file(self, key):
        return self.data["files"].get(key, {})

    def set_file(self, key, primary_key, secondary_key, offsets):
        entry = {"primary_key": primary_key or "", "secondary_key": secondary_key or "",
                 "offsets": {k: v for k, v in offsets.items() if v}, "time": int(time.time())}
        self.data["files"][key] = entry
