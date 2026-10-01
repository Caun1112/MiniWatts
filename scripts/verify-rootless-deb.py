#!/usr/bin/env python3
"""Inspect the produced Debian archive without installing it or requiring dpkg."""
import io
import pathlib
import plistlib
import sys
import tarfile

raw = pathlib.Path(sys.argv[1]).read_bytes()
assert raw.startswith(b'!<arch>\n'), 'Not a Debian ar archive'
entries = {}
pos = 8
while pos < len(raw):
    header = raw[pos:pos+60]
    assert len(header) == 60 and header[58:60] == b'`\n'
    name = header[:16].decode().strip().rstrip('/')
    size = int(header[48:58])
    entries[name] = raw[pos+60:pos+60+size]
    pos += 60 + size + size % 2
assert entries['debian-binary'] == b'2.0\n'
def read_tar(prefix):
    name = next(n for n in entries if n.startswith(prefix))
    tar = tarfile.open(fileobj=io.BytesIO(entries[name]), mode='r:*')
    members = {m.name.removeprefix('./'): m for m in tar.getmembers()}
    return tar, members

data, files = read_tar('data.tar')
for name, entry in files.items():
    assert name in ('', '.', 'var', 'var/jb') or name.startswith('var/jb/'), name
    assert '..' not in pathlib.PurePosixPath(name).parts, name
    assert entry.uid == 0 and entry.gid == 0, (name, entry.uid, entry.gid)
root = 'var/jb/Applications/MiniWatts.app/'
info = plistlib.loads(data.extractfile(files[root+'Info.plist']).read())
assert info['MWPackageFlavor'] == 'Rootless-DEB'
for executable in ['MiniWatts', 'MiniWattsChargeDaemon', 'MiniWattsChargeHUD', 'MiniWattsChargeLaunch']:
    assert files[root+executable].mode & 0o111
service = 'var/jb/Library/LaunchDaemons/org.zhaohe.MiniWatts.charge.plist'
assert files[service].mode == 0o644
launch = plistlib.loads(data.extractfile(files[service]).read())
assert launch['UserName'] == 'root' and launch['RunAtLoad'] is True
assert launch['KeepAlive'] is True
assert launch['ProgramArguments'] == ['/var/jb/Applications/MiniWatts.app/MiniWattsChargeDaemon']
watchdog_path = 'var/jb/Library/LaunchDaemons/org.zhaohe.MiniWatts.charge.watchdog.plist'
assert files[watchdog_path].mode == 0o644
watchdog = plistlib.loads(data.extractfile(files[watchdog_path]).read())
assert watchdog['UserName'] == 'root' and watchdog['RunAtLoad'] is True
assert watchdog['StartInterval'] == 30
assert watchdog['ProgramArguments'] == ['/var/jb/Applications/MiniWatts.app/MiniWattsChargeDaemon', 'watchdog']
assert data.extractfile(files[root+'MiniWattsChargeLaunch']).read().startswith(b'#!/bin/sh\n')
control, metadata = read_tar('control.tar')
fields = control.extractfile(metadata['control']).read().decode()
assert 'Architecture: iphoneos-arm64' in fields
for script in ['postinst', 'prerm']:
    assert metadata[script].mode & 0o111
print('DEB archive: rootless ownership, supervised service, recovery watchdog and executable lifecycle scripts verified')
