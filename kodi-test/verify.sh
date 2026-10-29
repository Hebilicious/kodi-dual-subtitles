#!/usr/bin/env bash
# End-to-end check of the add-on in a real Kodi (kodi.sh: no window, no sound).
#
# Always: a generated clip with the subtitle files of tests/fixtures/ next to it, driven the way
# a viewer (long press, D-pad) and an agent (JSON-RPC) do, with checks on the add-on's status.
# Screenshots go to $SHOTS for a look at the rendering.
#
# With a Jellyfin server (JELLYFIN_URL, JELLYFIN_API_KEY) and a video in it that has English and
# Thai text subtitles (JELLYFIN_ITEM_ID), also: that item played as a Jellyfin stream, and, with
# JELLYFIN_ITEM_FILE (the same video as a local path), played from the file and matched by name.
#
#   verify.sh            the checks above
#   verify.sh --sync     also has Bazarr re-sync the item's Thai file (BAZARR_URL, BAZARR_API_KEY);
#                        SYNC_BACKUP (the file's local path) is backed up and put back afterwards
set -euo pipefail

here=$(cd "$(dirname "$0")" && pwd)
kodi="$here/kodi.sh"
shots=${SHOTS:-/tmp/kodi-dualsubs-shots}
clip_dir=${CLIP_DIR:-/tmp/kodi-dualsubs-clip}
clip="$clip_dir/clip.mkv"
failures=0

rpc() { "$kodi" rpc "$@" >/dev/null; }
status() { "$kodi" status; }
step() { printf '\n== %s\n' "$*"; }
check() {  # check <description> <jq filter on the status, must be true>
  if status | jq -e "$2" >/dev/null; then
    echo "ok   $1"
  else
    echo "FAIL $1: $(status | jq -c '{state,message,layout,p:.primary,s:.secondary,warnings}')"
    failures=$((failures + 1))
  fi
}
wait_for() {  # wait_for <jq filter> [seconds]
  for _ in $(seq 1 $((${2:-30} * 2))); do
    status | jq -e "$1" >/dev/null 2>&1 && return 0
    sleep 0.5
  done
  return 0
}
seek() { rpc Player.Seek "{\"playerid\":1,\"value\":{\"time\":{\"hours\":0,\"minutes\":$1,\"seconds\":$2}}}"; }
shot() { sleep "${2:-2}"; "$kodi" shot "$shots/$1.png"; echo "     screenshot $shots/$1.png"; }
play() {
  rpc Player.Stop '{"playerid":1}' || true
  sleep 1
  rpc Player.Open "$(jq -nc --arg f "$1" '{item:{file:$f}}')"
  sleep 2
}
apply() { rpc Addons.ExecuteAddon "{\"addonid\":\"script.dualsubtitles\",\"params\":$1}"; }
dismiss_dialogs() {  # Kodi asks once whether to enable the add-on copied into the profile
  for _ in 1 2 3 4 5 6; do
    window=$("$kodi" rpc GUI.GetProperties '{"properties":["currentwindow"]}' | jq -r .result.currentwindow.id)
    [[ $window == 10100 ]] && rpc Input.Back
    sleep 0.5
  done
}

mkdir -p "$shots" "$clip_dir"
rm -f "$shots"/*.png

step "Test clip with the fixtures"
[[ -f $clip ]] || ffmpeg -loglevel error -y -f lavfi -i testsrc2=size=1920x1080:rate=24 -t 40 \
  -c:v libx264 -preset ultrafast -pix_fmt yuv420p "$clip"
cp "$here/../tests/fixtures/styled.ja.ass" "$clip_dir/clip.ja.ass"
cp "$here/../tests/fixtures/long.th.srt" "$clip_dir/clip.th.srt"
cp "$here/../tests/fixtures/plain.en.srt" "$clip_dir/clip.en.srt"
printf 'not a real image subtitle' >"$clip_dir/clip.fr.sup"
echo "     $clip_dir"

step "Kodi with the add-on"
"$kodi" start
dismiss_dialogs
wait_for '.state == "idle"' 10
check "service running" '.state == "idle"'

step "Auto-apply on start: English primary, Thai secondary, both at the bottom"
play "$clip"
wait_for '.state == "applied"' 30
check "applied from the files next to the video" \
  '.state == "applied" and .primary.language == "en" and .secondary.language == "th" and (.primary.key | startswith("file:"))'
check "both at the bottom by default" '.layout == "stacked"'
seek 0 12
shot 1-stacked 3

step "Agent call: secondary on top"
apply '{"primary":"en","secondary":"th","layout":"top-bottom"}'
wait_for '.layout == "top-bottom"' 15
check "top-bottom" '.state == "applied" and .layout == "top-bottom"'
seek 0 12
shot 2-top-bottom 3

step "Dialog by long press of L, D-pad only: secondary 1 s later"
rpc Input.ButtonEvent '{"button":"l","keymap":"KB","holdtime":1200}'
sleep 3
shot 3-dialog 0
for _ in 1 2 3 4 5; do rpc Input.Down; sleep 0.3; done
rpc Input.Select; sleep 1.5   # Secondary timing
rpc Input.Down; sleep 0.3     # Later by 1 s
rpc Input.Select; sleep 2
rpc Input.Back; sleep 0.7
rpc Input.Back; sleep 1
check "secondary offset +1 s, primary untouched" '.secondary.offset_ms == 1000 and .primary.offset_ms == 0'

step "Same video again: pair, layout and offset remembered"
play "$clip"
wait_for '.state == "applied"' 30
check "remembered" '.state == "applied" and .layout == "top-bottom" and .secondary.offset_ms == 1000'

step "Styled ASS primary keeps its styling; Thai and Japanese wrapped"
apply '{"primary":"ja","secondary":"th"}'
wait_for '.primary.language == "ja"' 15
check "Japanese ASS + Thai SRT" '.state == "applied" and .primary.language == "ja" and .secondary.language == "th"'
seek 0 12
shot 4-ja-kept-th-wrapped 3
apply '{"primary":"en","secondary":"ja","layout":"stacked"}'
wait_for '.secondary.language == "ja"' 15
check "Japanese flattened as the secondary" '.state == "applied" and .secondary.language == "ja"'
seek 0 12
shot 5-en-ja-flattened 3

step "Errors are reported, not swallowed"
apply '{"primary":"ko"}'
wait_for '.state == "error"' 15
check "missing language explained" '.state == "error" and (.message | test("no Korean track"))'
state="${KODI_TEST_HOME:-/tmp/kodi-dualsubs-test}/.kodi/temp/script.dualsubtitles/session.json"
if jq -e '.tracks[] | select(.key == "file:clip.fr.sup") | (.usable == false and (.reason | test("image subtitles")))' \
  "$state" >/dev/null; then
  echo "ok   image subtitle listed as unusable, with the reason"
else
  echo "FAIL image subtitle not marked unusable"
  failures=$((failures + 1))
fi

if [[ -n ${JELLYFIN_URL:-} && -n ${JELLYFIN_API_KEY:-} && -n ${JELLYFIN_ITEM_ID:-} ]]; then
  step "Jellyfin stream: the item id comes from the URL"
  url="$JELLYFIN_URL/Videos/$JELLYFIN_ITEM_ID/stream?static=true&mediaSourceId=$JELLYFIN_ITEM_ID"
  play "$url|X-Emby-Token=$JELLYFIN_API_KEY"
  wait_for '.state == "applied" and (.playing | startswith("http"))' 120
  check "applied from Jellyfin, no key in the status" \
    '.state == "applied" and (.playing | test("Token|api_key") | not) and (.primary.key | startswith("jellyfin:"))'

  if [[ -n ${JELLYFIN_ITEM_FILE:-} ]]; then
    step "Local file that Jellyfin knows: matched by file name"
    play "$JELLYFIN_ITEM_FILE"
    wait_for '.state == "applied" and (.playing | startswith("/"))' 120
    check "applied from Jellyfin" '.state == "applied" and (.primary.key | startswith("jellyfin:"))'
  fi

  if [[ ${1:-} == --sync ]]; then
    step "Sync to audio with Bazarr, the item's Thai file"
    backup=""
    if [[ -n ${SYNC_BACKUP:-} ]]; then
      backup=$(mktemp)
      cp "$SYNC_BACKUP" "$backup"
    fi
    apply '{"primary":"en","secondary":"th"}'
    wait_for '.secondary.language == "th"' 30
    apply '{"action":"sync","track":"secondary"}'
    wait_for '.state == "synced" or .state == "error"' 300
    check "Bazarr synced the Thai file and it was reloaded" '.state == "synced"'
    if [[ -n $backup ]]; then
      cp "$backup" "$SYNC_BACKUP"
      rm -f "$backup"
    fi
  fi
else
  step "Jellyfin checks skipped (set JELLYFIN_URL, JELLYFIN_API_KEY and JELLYFIN_ITEM_ID)"
fi

step "Build time in Kodi's log"
"$kodi" log "applied" | sed -E 's/.*\] //' | tail -8

"$kodi" stop
if ((failures)); then
  echo "$failures check(s) failed"
  exit 1
fi
echo "all checks passed"
