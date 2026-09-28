#!/usr/bin/env python3
"""Verify compiled helper executables and complete control resources in the IPA."""
import json
import struct
import sys
import zipfile

with zipfile.ZipFile(sys.argv[1]) as archive:
    names = archive.namelist()
    app = next(n.removesuffix('Info.plist') for n in names if n.startswith('Payload/') and n.count('/') == 2 and n.endswith('.app/Info.plist'))
    for executable in ['MiniWatts', 'MiniWattsChargeDaemon', 'MiniWattsChargeHUD']:
        data = archive.read(app + executable)
        assert data[:4] == b'\xcf\xfa\xed\xfe', f'{executable}: expected 64-bit Mach-O'
        _, cpu, _, filetype, count, _, _, _ = struct.unpack_from('<8I', data)
        assert cpu == 0x100000c and filetype == 2, f'{executable}: expected arm64 executable'
        offset = 32
        for _ in range(count):
            command, size = struct.unpack_from('<II', data, offset)
            assert command != 0x1d, f'{executable}: contains LC_CODE_SIGNATURE'
            assert size >= 8
            offset += size
        assert archive.getinfo(app + executable).external_attr >> 16 & 0o111, f'{executable}: executable bit missing'
        print(f'{executable}: arm64, executable, unsigned')
    for resource in ['www/index.html', 'www/history.html', 'www/float.html', 'www/help.html', 'www/css/miniwatts.css', 'ThirdPartyLicenses/ChargeLimiter-GPL-3.0.txt', 'BuildCommit.txt']:
        assert app + resource in names, f'Missing {resource}'
    assert app + 'www/test.json' not in names, 'Production IPA includes simulated battery fixture'
    languages = json.loads(archive.read(app + 'www/lang.json'))
    assert 'zh_CN' in languages
    print('Complete control resources, licenses, build revision and Chinese translation present')
