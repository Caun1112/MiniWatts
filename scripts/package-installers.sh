#!/bin/bash
# GitHub Actions only: derive an entitlement-bearing TrollStore IPA and rootless
# DEB from the verified unsigned IPA. Uses ad-hoc signatures, never a certificate.
set -euo pipefail
cd "$(dirname "$0")/.."
BASE="$PWD/build/export/MiniWatts-unsigned.ipa"
WORK="$PWD/build/installers"
rm -rf "$WORK"
mkdir -p "$WORK"
unzip -q "$BASE" -d "$WORK/trollstore"
APP="$WORK/trollstore/Payload/MiniWatts.app"
/usr/libexec/PlistBuddy -c 'Add :MWPackageFlavor string TrollStore' "$APP/Info.plist"
# Keep the app's data container; only helpers use no-container.
python3 - <<'PY'
import plistlib
from pathlib import Path
ent=plistlib.loads(Path('scripts/ChargeControl.entitlements').read_bytes())
ent.pop('get-task-allow',None)
Path('build/installers/helper.entitlements').write_bytes(plistlib.dumps(ent))
ent.pop('com.apple.private.security.no-container',None)
Path('build/installers/app.entitlements').write_bytes(plistlib.dumps(ent))
PY
sign_app() {
  local bundle="$1"
  while IFS= read -r -d '' ext; do
    codesign --force --sign - --timestamp=none --generate-entitlement-der --entitlements Widget/Widget.entitlements "$ext"
  done < <(find "$bundle/PlugIns" -name '*.appex' -type d -print0)
  for helper in MiniWattsChargeDaemon MiniWattsChargeHUD; do
    codesign --force --sign - --timestamp=none --generate-entitlement-der --entitlements "$WORK/helper.entitlements" "$bundle/$helper"
  done
  codesign --force --sign - --timestamp=none --generate-entitlement-der --entitlements "$WORK/app.entitlements" "$bundle"
}
sign_app "$APP"
(cd "$WORK/trollstore" && zip -qry "$WORK/../export/MiniWatts-TrollStore.ipa" Payload)
STAGE="$WORK/rootless"
mkdir -p "$STAGE/var/jb/Applications" "$STAGE/var/jb/Library/LaunchDaemons" "$STAGE/DEBIAN"
cp -R "$APP" "$STAGE/var/jb/Applications/"
DEB_APP="$STAGE/var/jb/Applications/MiniWatts.app"
/usr/libexec/PlistBuddy -c 'Set :MWPackageFlavor Rootless-DEB' "$DEB_APP/Info.plist"
sign_app "$DEB_APP"
cp packaging/rootless/org.zhaohe.MiniWatts.charge.plist "$STAGE/var/jb/Library/LaunchDaemons/"
cp packaging/rootless/{postinst,prerm} "$STAGE/DEBIAN/"
VERSION=$(/usr/libexec/PlistBuddy -c 'Print :CFBundleShortVersionString' "$APP/Info.plist")
NUMBER=$(/usr/libexec/PlistBuddy -c 'Print :CFBundleVersion' "$APP/Info.plist")
cat > "$STAGE/DEBIAN/control" <<CONTROL
Package: org.zhaohe.miniwatts
Name: MiniWatts
Version: $VERSION-$NUMBER
Architecture: iphoneos-arm64
Description: MiniWatts battery monitor with ChargeLimiter and a rootless launch daemon.
Maintainer: MiniWatts contributors
Section: Utilities
Depends: firmware (>= 17.0)
Homepage: https://github.com/Caun1112/MiniWatts
CONTROL
chmod 0755 "$STAGE/DEBIAN/postinst" "$STAGE/DEBIAN/prerm"
chmod 0644 "$STAGE/var/jb/Library/LaunchDaemons/org.zhaohe.MiniWatts.charge.plist"
command -v dpkg-deb >/dev/null || { echo 'dpkg-deb is required on the Actions runner' >&2; exit 1; }
dpkg-deb --root-owner-group -Zgzip -b "$STAGE" "$PWD/build/export/MiniWatts-rootless.deb"
python3 scripts/verify-installers.py "$APP" "$STAGE"
