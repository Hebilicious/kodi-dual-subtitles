# Kodi dual subtitles

A Kodi add-on that shows two subtitle tracks of the video playing at the same time, for example
Thai above English, each with its own style, position and timing. The tracks come from Jellyfin or
from the subtitle files next to the video. Kodi draws them itself, so the video keeps playing
directly, with no conversion on the server.

- Kodi 21 (Omega) and later, pure Python: one zip for CoreELEC, LibreELEC, Android TV, webOS and
  desktops.
- Live per-track timing, three layouts, a remembered pair per show or film.
- Thai and Japanese fonts included; long Thai and Japanese lines are wrapped between words.
- Usable with a D-pad, and by scripts or agents through JSON-RPC.

What it is for and what it must do: [`docs/requirements.md`](docs/requirements.md).

## Install

Download the zip from the [releases](../../releases), or build it:

```sh
proto install                 # pinned moon and Python
moon run dualsubs:build       # dist/script.dualsubtitles-<version>.zip
```

In Kodi: Settings → System → Add-ons → turn on "Unknown sources", then Add-ons → Install from zip
file. Then, in the add-on's settings (Add-ons → My add-ons → Programs → Dual subtitles):

| Setting | |
|---|---|
| Jellyfin server address and API key | Where the tracks of the video playing come from (Dashboard → API keys). Leave empty to use only the files next to the video |
| Primary and secondary languages | Defaults, in order of preference: `en` and `th`. Codes or names, separated by commas |
| Layout | Both at the bottom with the secondary above (default), secondary on top, or primary only |
| Style | Size, colour, outline and margin of each track. The default colour is a 75 % grey, which doesn't glare in HDR |
| Bazarr address and API key | Optional, for "Sync to the audio". The Kodi device must reach Bazarr's web port |

## Use

- **During playback**, long-press **L**, **C**, **Menu** or the remote's **Subtitle** button (any
  other key can map `RunScript(script.dualsubtitles)`; the add-on is also in Add-ons → Programs).
  The list sets the primary and secondary tracks, swaps them, picks the layout, nudges each
  track's timing by ±0.1 s or ±1 s, switches a styled (ASS) primary between its own styling and
  plain dialogue, opens the style settings, and asks Bazarr to sync a track to the audio. Each
  change shows at once, without restarting the video.
- **When a video starts**, the pair remembered for its show or film is applied, or else the
  default languages, with a short notice ("Thai + English").
- **Scripts and agents** use Kodi's JSON-RPC after starting playback:

  ```json
  {"jsonrpc": "2.0", "id": 1, "method": "Addons.ExecuteAddon",
   "params": {"addonid": "script.dualsubtitles",
              "params": {"primary": "en", "secondary": "th", "layout": "stacked"}}}
  ```

  `primary` and `secondary` are language codes or names (`secondary: "none"` for one track);
  `layout` is `stacked`, `top-bottom` or `primary-only`; `action` can be `off`, `status`, or
  `sync` with `track: "primary"` or `"secondary"`. The result is JSON in the Home window property
  `DualSubtitles.Status`; read it with `XBMC.GetInfoLabels` and the label
  `Window(Home).Property(DualSubtitles.Status)`. Its `state` is `applied`, `error` (with a
  `message`), `synced`, `working` or `off`.

## How it works

1. **Tracks**: from Jellyfin when it knows the video (the item id in a Jellyfin stream URL, as
   the Jellyfin for Kodi add-on plays it, or else the file name matched against the library), or
   else the subtitle files next to the video (`Movie.th.srt`, `Subs/…`). Image tracks (PGS,
   VobSub) are listed as unusable, with the reason.
2. **One ASS file** in Kodi's temp folder, with a `Primary` and a `Secondary` style; every cue keeps
   its own times plus its track's offset. Kodi loads it with `Player.setSubtitles` and draws it
   with libass. It is rebuilt on every change, in about 30 ms.
3. **ASS sources**: the primary keeps its own styling (signs, karaoke) by default, or is
   flattened to plain dialogue; the secondary is always flattened.
4. **Fonts**: Noto Sans, Noto Sans Thai and Noto Sans JP ship in the add-on. Its service copies
   them to `special://home/media/Fonts/`, where Kodi's libass finds them.
5. **Wrapping**: libass in Kodi wraps only at spaces. The add-on wraps Thai between words, using
   ICU's Thai dictionary (about 10 MB in memory), and Japanese between phrases.
6. **Memory**: the language pair and layout per show or film, the tracks and offsets per file, in
   `addon_data/script.dualsubtitles/prefs.json`.

| Code | What |
|---|---|
| `script.dualsubtitles/addon.xml` | A script (dialog, JSON-RPC calls) and a service (auto-apply, fonts, key) |
| `resources/lib/dualsubs/subtitles.py` | SRT, WebVTT and ASS parsing; flattening ASS to dialogue |
| `…/assfile.py` | Writes the combined ASS file: layouts, styles, offsets |
| `…/wrap.py`, `…/thai.py` | Wrapping for Thai (word segmentation) and Japanese |
| `…/tracks.py`, `…/jellyfin.py`, `…/localfiles.py`, `…/bazarr.py` | Tracks, where they come from, choosing a pair; Bazarr sync |
| `…/session.py` | The video playing: choose, fetch (cached in Kodi's temp), apply, remember |
| `…/dialog.py`, `…/script.py`, `…/service.py`, `…/kodiapi.py` | The Kodi side |
| `build.sh` | The installable zip, with the fonts and the dictionary (pinned downloads, checksums checked) |
| `tests/` | Unit tests; `kodi-test/` runs the add-on in a real Kodi |

## Develop

```sh
moon run dualsubs:check    # unit tests, compile, XML, shell syntax
moon run dualsubs:verify   # the add-on in a real Kodi, headless
```

`kodi-test/verify.sh` starts Kodi under Xvfb with a throwaway profile (`/tmp/kodi-dualsubs-test`,
JSON-RPC on `127.0.0.1:8099`), installs the zip, plays a generated clip with the files of
`tests/fixtures/` next to it, drives the add-on like a viewer (long press, D-pad) and like a
script (JSON-RPC), checks its status, and saves screenshots to `/tmp/kodi-dualsubs-shots/`. With
`JELLYFIN_URL`, `JELLYFIN_API_KEY` and `JELLYFIN_ITEM_ID` (a video with English and Thai text
subtitles), it also plays that item from Jellyfin; `--sync` with `BAZARR_URL` and
`BAZARR_API_KEY` adds the Bazarr sync (see the script's header). `kodi-test/kodi.sh` runs single
steps: `start`, `rpc`, `status`, `shot`, `log`, `stop`.

It needs `kodi`, `Xvfb`, ImageMagick's `import`, `ffmpeg`, `jq`, `curl` and `unzip`. Kodi embeds
the system Python: with another Python first in `PATH` (proto's, pyenv's), Kodi loads that one's
standard library and add-ons fail with `No module named 'math'`, so `kodi.sh` starts Kodi with the
system `PATH`.

## Status

Tested in Kodi 21.3 on Linux: every check of `verify.sh --sync` passes. A 2-hour film with 1,800
cues per track builds in about 40 ms on a desktop, and in about 150 ms the first time when a fifth
of the Thai lines need wrapping (dictionary loading included); after that, about 30 ms per change.
Not measured yet on TV hardware, nor with HDR or Dolby Vision playback.

## License

MIT for the code ([LICENSE](LICENSE)). The zip also carries the Noto fonts (SIL Open Font License
1.1) and ICU's Thai dictionary (Unicode License V3), with their license files.
