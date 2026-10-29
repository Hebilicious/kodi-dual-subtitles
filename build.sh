#!/usr/bin/env bash
# Packages the add-on for Kodi: script.dualsubtitles/ plus the fonts (Noto Sans, Noto Sans Thai,
# Noto Sans JP) and ICU's Thai dictionary, downloaded once at pinned versions and checked.
# Writes dist/script.dualsubtitles-<version>.zip, installable with Kodi's "Install from zip file".
set -euo pipefail

here=$(cd "$(dirname "$0")" && pwd)
cache=${XDG_CACHE_HOME:-$HOME/.cache}/kodi-dual-subtitles
noto=https://raw.githubusercontent.com/notofonts/notofonts.github.io/c1d3718e2a0eb25c2567a694ee017061fdaa5f51/fonts
cjk=https://raw.githubusercontent.com/notofonts/noto-cjk/f8d157532fbfaeda587e826d4cd5b21a49186f7c/Sans
icu=https://raw.githubusercontent.com/unicode-org/icu/ad110a2381f1b75bfb875fb0b672b7c38dce4e4b

# name, URL, SHA-256, where it goes in the add-on
assets=(
  "NotoSans-Regular.ttf $noto/NotoSans/hinted/ttf/NotoSans-Regular.ttf 478c558ea716033cd60c03438f628dfa75694dcf6b5f6d505a2f05fd2b4f3823 resources/fonts"
  "NotoSansThai-Regular.ttf $noto/NotoSansThai/hinted/ttf/NotoSansThai-Regular.ttf 61cf814eec46b294d6ea4401ac295d0cecd5207bd2331dcc5a15e7301d30ee44 resources/fonts"
  "NotoSansJP-Regular.otf $cjk/SubsetOTF/JP/NotoSansJP-Regular.otf dff723ba59d57d136764a04b9b2d03205544f7cd785a711442d6d2d085ac5073 resources/fonts"
  "OFL.txt $cjk/LICENSE 6a73f9541c2de74158c0e7cf6b0a58ef774f5a780bf191f2d7ec9cc53efe2bf2 resources/fonts"
  "thaidict.txt $icu/icu4c/source/data/brkitr/dictionaries/thaidict.txt 3166abde40c0f44ab91c28f5ce96d7d1472cb7882e1c0bda0a72f8f69dba4274 resources/data"
  "ICU-LICENSE.txt $icu/LICENSE e09827667e0bb3c808b2a463548ba814a5e6249b67353234d70c8dfc2bcc417d resources/data"
)

version=$(sed -n 's/.*<addon id="script.dualsubtitles"[^>]* version="\([^"]*\)".*/\1/p' "$here/script.dualsubtitles/addon.xml")
stage="$here/dist/stage/script.dualsubtitles"
zip="$here/dist/script.dualsubtitles-$version.zip"

rm -rf "$here/dist/stage" "$zip"
mkdir -p "$cache" "$stage"
cp -r "$here/script.dualsubtitles/." "$stage/"
find "$stage" -name __pycache__ -prune -exec rm -rf {} +

for asset in "${assets[@]}"; do
  read -r name url sha folder <<<"$asset"
  if ! echo "$sha  $cache/$name" | sha256sum --check --status 2>/dev/null; then
    curl -fsSL -o "$cache/$name.part" "$url"
    echo "$sha  $cache/$name.part" | sha256sum --check --quiet
    mv "$cache/$name.part" "$cache/$name"
  fi
  mkdir -p "$stage/$folder"
  cp "$cache/$name" "$stage/$folder/$name"
done

(cd "$here/dist/stage" && zip -qr "$zip" script.dualsubtitles)
rm -rf "$here/dist/stage"
echo "$zip"
