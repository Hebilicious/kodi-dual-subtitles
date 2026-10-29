"""Subtitle files next to the video ("Movie.th.srt", "Subs/Movie.en.forced.ass"), for files played
from a share without Jellyfin."""

import posixpath

from . import languages
from .tracks import Track, classify

EXTENSIONS = {"srt": "subrip", "ass": "ass", "ssa": "ssa", "vtt": "webvtt", "sup": "sup", "sub": "dvdsub"}
_SUBFOLDERS = ("subs", "subtitles")
_HI_TAGS = {"sdh", "hi", "cc"}


def split_path(path):
    """(folder, file name) of a local path or a Kodi URL (smb://, nfs://)."""
    path = path.replace("\\", "/")
    folder, name = posixpath.split(path)
    return folder + "/", name


def find(video_path, listdir):
    """Tracks for the files next to ``video_path``.

    ``listdir(folder)`` returns (folders, files), like ``xbmcvfs.listdir``; folders end with "/".
    """
    folder, video_name = split_path(video_path)
    stem = video_name.rsplit(".", 1)[0]
    found = []
    try:
        dirs, files = listdir(folder)
    except Exception:  # an unreadable folder just has no side files
        return []
    candidates = [(folder, name) for name in files]
    for sub in dirs:
        if sub.strip("/").lower() in _SUBFOLDERS:
            sub_folder = folder + sub.strip("/") + "/"
            try:
                sub_dirs, sub_files = listdir(sub_folder)
            except Exception:
                continue
            candidates += [(sub_folder, name) for name in sub_files]
            for inner in sub_dirs:  # "Subs/<episode name>/2_English.srt"
                if inner.strip("/") == stem:
                    try:
                        candidates += [(sub_folder + stem + "/", n) for n in listdir(sub_folder + stem + "/")[1]]
                    except Exception:
                        pass
    for where, name in sorted(candidates):
        extension = name.rsplit(".", 1)[-1].lower() if "." in name else ""
        if extension not in EXTENSIONS:
            continue
        base = name[: -len(extension) - 1]
        in_episode_folder = where.rstrip("/").endswith("/" + stem)
        if not in_episode_folder and not base.lower().startswith(stem.lower()):
            continue
        tags = [t for t in base[len(stem):].lower().replace("_", ".").replace("-", ".").split(".") if t] \
            if not in_episode_folder else [t for t in base.lower().replace("_", ".").split(".") if t]
        language = next((languages.normalize(t) for t in tags if languages.normalize(t)), "")
        codec = EXTENSIONS[extension]
        if extension == "sub" and (name[:-3] + "idx") not in [n for _, n in candidates]:
            codec = "microdvd"  # a .sub without .idx is MicroDVD text
        usable, reason = classify(codec)
        found.append(Track(
            key="file:" + name,
            source="file",
            language=language,
            title=name,
            codec=codec if codec != "subrip" else "srt",
            external=True,
            forced="forced" in tags,
            hearing_impaired=bool(_HI_TAGS & set(tags)),
            usable=usable and codec != "microdvd",
            reason=reason or ("MicroDVD subtitles aren't supported" if codec == "microdvd" else ""),
            location=where + name,
        ))
    return found
