#!/bin/bash
# Called by GitHub Actions through build-ipa.sh. No signing or external SDK needed.
set -euo pipefail
cd "$(dirname "$0")/.."
APP="${1:?app bundle destination}"
SDK="$(xcrun --sdk iphoneos --show-sdk-path)"
OUT="$PWD/build/charge-service"
mkdir -p "$OUT" "$APP"
VENDOR="$PWD/Vendor/ChargeLimiter"
WEB="$PWD/Vendor/GCDWebServer"
FLAGS=(-arch arm64 -isysroot "$SDK" -miphoneos-version-min=17.0 -fobjc-arc -fblocks -Os -DNDEBUG=1 -DGCDWEBSERVER_ENABLE_BACKGROUND_MODE=0 -Wno-deprecated-declarations -ffile-prefix-map="$PWD"=/MiniWatts -I"$VENDOR" -I"$WEB/Core" -I"$WEB/Requests" -I"$WEB/Responses")
OBJS=()
for source in "$WEB"/{Core,Requests,Responses}/*.m; do
  obj="$OUT/$(basename "$source").o"
  xcrun --sdk iphoneos clang "${FLAGS[@]}" -c "$source" -o "$obj"
  OBJS+=("$obj")
done
LIBS=(-framework Foundation -framework UIKit -framework CoreGraphics -framework CoreFoundation -framework CFNetwork -framework MobileCoreServices -framework UserNotifications -framework JavaScriptCore -lsqlite3 -lz "$VENDOR/IOKit.tbd" "$VENDOR/BackBoardServices.tbd" "$VENDOR/GraphicsServices.tbd" -Wl,-no_adhoc_codesign)
xcrun --sdk iphoneos clang++ "${FLAGS[@]}" -std=c++17 "$VENDOR/daemon.mm" "$VENDOR/utils.mm" "${OBJS[@]}" "${LIBS[@]}" -o "$APP/MiniWattsChargeDaemon"
xcrun --sdk iphoneos clang++ "${FLAGS[@]}" -std=c++17 "$VENDOR/ui.mm" "$VENDOR/utils.mm" "${LIBS[@]}" -o "$APP/MiniWattsChargeHUD"
xcrun strip -S -x "$APP/MiniWattsChargeDaemon" "$APP/MiniWattsChargeHUD"
cp -R "$VENDOR/www" "$APP/www"
rm -f "$APP/www/test.json"
cp -R LICENSES "$APP/ThirdPartyLicenses"
printf '%s\n' "$(git rev-parse HEAD)" > "$APP/BuildCommit.txt"
