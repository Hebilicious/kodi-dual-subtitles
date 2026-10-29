#!/usr/bin/env bash
# A throwaway Kodi for testing the add-on: no window on the screen (Xvfb), no
# sound, its own profile under $KODI_TEST_HOME, JSON-RPC on 127.0.0.1:$KODI_TEST_PORT.
#
#   kodi.sh start                 build the zip, install it in a fresh profile, start Kodi
#   kodi.sh rpc <method> [json]   one JSON-RPC call, prints the result
#   kodi.sh status                the add-on's status property
#   kodi.sh shot <file.png>       screenshot of the Kodi screen
#   kodi.sh log [pattern]         the add-on's lines of Kodi's log
#   kodi.sh stop
#
# Optional: JELLYFIN_URL and JELLYFIN_API_KEY, BAZARR_URL and BAZARR_API_KEY go into the test
# profile's add-on settings (file mode 600), never to the output.
set -euo pipefail

here=$(cd "$(dirname "$0")" && pwd)
home=${KODI_TEST_HOME:-/tmp/kodi-dualsubs-test}
port=${KODI_TEST_PORT:-8099}
display=${KODI_TEST_DISPLAY:-:97}
addon=script.dualsubtitles

rpc() {
  local method=$1 params=${2:-"{}"}
  curl -fsS -m 30 -H 'Content-Type: application/json' \
    -d "{\"jsonrpc\":\"2.0\",\"id\":1,\"method\":\"$method\",\"params\":$params}" \
    "http://127.0.0.1:$port/jsonrpc"
}

wait_for_rpc() {
  for _ in $(seq 1 120); do
    rpc JSONRPC.Ping >/dev/null 2>&1 && return 0
    sleep 0.5
  done
  echo "Kodi's JSON-RPC didn't come up; see $home/.kodi/temp/kodi.log" >&2
  return 1
}

write_settings() {
  mkdir -p "$home/.kodi/userdata/addon_data/$addon"
  (
    umask 077
    cat >"$home/.kodi/userdata/addon_data/$addon/settings.xml" <<XML
<settings version="2">
    <setting id="jellyfin_url">${JELLYFIN_URL:-}</setting>
    <setting id="jellyfin_api_key">${JELLYFIN_API_KEY:-}</setting>
    <setting id="bazarr_url">${BAZARR_URL:-}</setting>
    <setting id="bazarr_api_key">${BAZARR_API_KEY:-}</setting>
</settings>
XML
  )
}

start() {
  stop >/dev/null 2>&1 || true
  rm -rf "$home"
  mkdir -p "$home/.kodi/userdata" "$home/.kodi/addons"
  zip=$(bash "$here/../build.sh" | tail -1)
  unzip -q -o "$zip" -d "$home/.kodi/addons"
  cat >"$home/.kodi/userdata/guisettings.xml" <<XML
<settings version="2">
    <setting id="services.webserver">true</setting>
    <setting id="services.webserverport">$port</setting>
    <setting id="services.webserverauthentication">false</setting>
    <setting id="debug.screenshotpath">$home/screenshots/</setting>
    <setting id="videoplayer.usevaapi">false</setting>
</settings>
XML
  write_settings
  Xvfb "$display" -screen 0 1920x1080x24 -nolisten tcp >"$home/xvfb.log" 2>&1 &
  echo $! >"$home/xvfb.pid"
  sleep 1
  # The system PATH: Kodi embeds the system Python and would load proto's standard library instead.
  PATH=/usr/local/bin:/usr/bin:/bin HOME=$home DISPLAY=$display KODI_AE_SINK=NULL LIBGL_ALWAYS_SOFTWARE=1 \
    setsid kodi --windowing=x11 >"$home/kodi.out" 2>&1 &
  echo $! >"$home/kodi.pid"
  wait_for_rpc
  # Add-ons copied into the profile start disabled; enabling one starts its service.
  rpc Addons.SetAddonEnabled "{\"addonid\":\"$addon\",\"enabled\":true}" >/dev/null
  echo "Kodi is up: profile $home, JSON-RPC 127.0.0.1:$port, display $display"
}

stop() {
  rpc Application.Quit >/dev/null 2>&1 || true
  for _ in $(seq 1 40); do
    [[ -n $(test_kodi_pids) ]] || break
    sleep 0.5
  done
  for pid in $(test_kodi_pids); do kill -9 "$pid"; done
  if [[ -f "$home/xvfb.pid" ]]; then
    kill "$(cat "$home/xvfb.pid")" 2>/dev/null || true
    rm -f "$home/xvfb.pid"
  fi
  rm -f "$home/kodi.pid"
}

# Kodi processes of this test profile only (not a Kodi the user runs).
test_kodi_pids() {
  local pid
  for pid in $(pgrep -x kodi.bin); do
    tr "\\0" "\\n" <"/proc/$pid/environ" 2>/dev/null | grep -qx "HOME=$home" && echo "$pid"
  done
  return 0
}

case ${1:-} in
  start) start ;;
  stop) stop ;;
  rpc) shift; rpc "$@"; echo ;;
  status)
    rpc XBMC.GetInfoLabels '{"labels":["Window(Home).Property(DualSubtitles.Status)"]}' |
      jq -r '.result["Window(Home).Property(DualSubtitles.Status)"]'
    ;;
  shot) DISPLAY=$display import -window root "$2" ;;
  log)
    # Only the add-on's lines, with anything key-like cut out.
    grep -a -E "${2:-$addon}" "$home/.kodi/temp/kodi.log" | sed -E 's/(api_key|Token|X-Emby-Token|X-API-KEY)=[^&" ]*/\1=…/g'
    ;;
  *) sed -n '2,12p' "$0"; exit 3 ;;
esac
