# Requirements

What the add-on is for and what it must do. The code refers to these numbers (F1 to F11).

## Problem

Some viewers watch with two subtitle languages at once: Japanese-audio anime with Thai and
English subtitles, or a film where one viewer reads one language and another a second one.
Jellyfin's web client shows a secondary track only for plain-text files, the Jellyfin Android TV
app has no secondary track, and Kodi shows one subtitle stream at a time. Kodi runs on CoreELEC
boxes, Android TV and webOS, so one Kodi add-on covers all of them.

## Goals

1. Show any two subtitle tracks of what's playing at the same time, chosen during playback.
2. Each track keeps its own timing; no pre-merged files, no pairs decided ahead of time.
3. The server never converts the video: the subtitles are drawn by Kodi, the video plays directly.
4. Remember choices: a show's language pair and layout apply again on the next episode.
5. Scripts and agents can set the pair after starting playback.

Not in scope: image subtitles (PGS, VobSub) as a source, translation, streaming apps, more than
two tracks.

## Functional requirements

| # | Requirement |
|---|---|
| F1 | A dialog during playback, opened by a key, lists the video's subtitle tracks (language, name, embedded or file, format). The viewer picks a **primary** and an optional **secondary** track with a D-pad only |
| F2 | Layouts: both at the bottom with the secondary above (default), secondary at the top and primary at the bottom, or primary only. Per track: font size, colour, outline, vertical margin |
| F3 | Each track keeps its own cue timings, with an offset per track changed live in steps of 100 ms and 1 s |
| F4 | Preferences per show or film, then a global default ordered by language. Offsets per file |
| F5 | When playback starts and a preference matches the available tracks, apply it and show a short notice |
| F6 | A styled ASS source keeps its own styling (signs, karaoke) as the primary track, or is flattened to plain dialogue in the add-on's style (always for the secondary, so the two don't collide) |
| F7 | Thai and Japanese render correctly: the add-on ships fonts that cover both and doesn't depend on the skin's or the OS's |
| F8 | Seek, pause, chapter jumps and audio-track changes keep both tracks in sync; changing a track doesn't restart playback |
| F9 | A JSON-RPC entry point (`Addons.ExecuteAddon`) to set the pair, with the result readable afterwards |
| F10 | "Sync to audio" asks Bazarr to re-sync a subtitle file on the server, then reloads it |
| F11 | A track that can't be used (image subtitles, download failure) says why instead of failing silently |

## Sources

1. **Jellyfin**: `GET /Items/{id}/PlaybackInfo` lists the subtitle streams, and Jellyfin serves any
   text stream, embedded or external, as SRT or ASS
   (`/Videos/{id}/{mediaSourceId}/Subtitles/{index}/0/Stream.ass`).
2. **Files next to the video** (`Movie.th.srt`, `Subs/`), when playing without Jellyfin.

## Rendering

Kodi draws one subtitle stream at a time, with libass. The add-on fetches both tracks as text,
writes one ASS file with a style per track, each event keeping its own times plus the track's
offset, loads it with `xbmc.Player().setSubtitles()`, and rebuilds it on every change.

- **HDR**: white text glares on an OLED in HDR; the default colour is a 75 % grey with a dark outline.
- **Line breaking**: libass in Kodi wraps only at spaces. Thai has no spaces between words and
  Japanese none at all, so the add-on wraps those lines itself (Thai by dictionary segmentation).

## Targets

- Kodi 21 (Omega) and later, pure Python, one package for every platform.
- Building the file for a 2-hour film with two tracks: under 300 ms on a low-end TV box.
- No network calls during playback once the tracks are loaded, except for F10.
- Memory: under 30 MB above Kodi's own.
