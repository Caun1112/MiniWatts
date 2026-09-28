#!/usr/bin/env python3
"""Validate actual embedded entitlements, ad-hoc identity and rootless layout."""
import pathlib
import plistlib
import subprocess
import sys


def check_bundle(app, flavor):
    info = plistlib.loads((app / 'Info.plist').read_bytes())
    assert info['MWPackageFlavor'] == flavor
    for binary in ['MiniWatts', 'MiniWattsChargeDaemon', 'MiniWattsChargeHUD']:
        path = app / binary
        ent = plistlib.loads(subprocess.check_output(['codesign', '-d', '--entitlements', ':-', str(path)], stderr=subprocess.DEVNULL))
        for key in ['com.apple.private.security.no-sandbox', 'com.apple.private.persona-mgmt']:
            assert ent.get(key) is True, (path, key)
        if binary != 'MiniWatts':
            assert ent.get('com.apple.private.powersource-write') is True
        else:
            assert ent.get('com.apple.security.application-groups') == ['group.org.zhaohe.MiniWatts']
            assert not ent.get('com.apple.private.security.no-container')
        assert 'com.apple.developer.team-identifier' not in ent
        assert not ent.get('get-task-allow')
        detail = subprocess.run(['codesign', '-dvv', str(path)], capture_output=True, text=True, check=True).stderr
        assert 'Signature=adhoc' in detail and 'Authority=' not in detail, detail
        subprocess.run(['codesign', '--verify', str(path)], check=True)
        print(flavor, binary, ': ad-hoc signature and required entitlements verified')
    for extension in (app / 'PlugIns').glob('*.appex'):
        ent = plistlib.loads(subprocess.check_output(['codesign', '-d', '--entitlements', ':-', str(extension)], stderr=subprocess.DEVNULL))
        assert ent['com.apple.security.application-groups'] == ['group.org.zhaohe.MiniWatts']
        assert 'com.apple.private.security.no-sandbox' not in ent
        subprocess.run(['codesign', '--verify', str(extension)], check=True)
    assert not list(app.rglob('embedded.mobileprovision'))

check_bundle(pathlib.Path(sys.argv[1]), 'TrollStore')
stage = pathlib.Path(sys.argv[2])
check_bundle(stage / 'var/jb/Applications/MiniWatts.app', 'Rootless-DEB')
launch = plistlib.loads((stage / 'var/jb/Library/LaunchDaemons/org.zhaohe.MiniWatts.charge.plist').read_bytes())
assert launch['UserName'] == 'root'
assert launch['ProgramArguments'] == ['/var/jb/Applications/MiniWatts.app/MiniWattsChargeDaemon']
control = (stage / 'DEBIAN/control').read_text()
assert 'Architecture: iphoneos-arm64' in control
assert 'Depends: firmware (>= 17.0)' in control
for script in ['postinst', 'prerm']:
    assert (stage / 'DEBIAN' / script).stat().st_mode & 0o111
print('Rootless launchd service, package architecture and lifecycle scripts verified')
