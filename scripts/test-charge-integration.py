#!/usr/bin/env python3
"""Source/package contracts; hardware behavior must be tested on an iOS device."""
import json
import plistlib
import re
import unittest
from pathlib import Path
ROOT = Path(__file__).resolve().parents[1]
VENDOR = ROOT / 'Vendor/ChargeLimiter'

class IntegrationContracts(unittest.TestCase):
    def test_all_upstream_configuration_controls_retained(self):
        js = (VENDOR / 'www/js/app.js').read_text()
        validator = (VENDOR / 'RequestValidation.h').read_text()
        keys = set(re.findall(r'key:\s*"([a-z_]+)"', js))
        self.assertGreater(len(keys), 20)
        self.assertFalse([k for k in keys if '@"' + k + '"' not in validator])

    def test_all_pages_and_local_assets_exist(self):
        for html in (VENDOR / 'www').glob('*.html'):
            for asset in re.findall(r'(?:src|href)="([^"{}]+)"', html.read_text()):
                if asset.startswith(('http:', 'https:', '#', 'javascript:', 'safari:', 'mailto:')): continue
                if asset in ('favicon.ico',) or '.' in asset:
                    self.assertTrue((html.parent / asset.split('?')[0].lstrip('/')).exists(), (html.name, asset))

    def test_private_helpers_are_packaged_before_ipa(self):
        script = (ROOT / 'scripts/build-ipa.sh').read_text()
        self.assertLess(script.index('./scripts/build-charge-service.sh'), script.index('zip -qry'))
        build = (ROOT / 'scripts/build-charge-service.sh').read_text()
        for name in ['MiniWattsChargeDaemon', 'MiniWattsChargeHUD', 'www', 'BuildCommit.txt', '-no_adhoc_codesign']:
            self.assertIn(name, build)
        self.assertIn('@"MiniWattsChargeHUD"', (VENDOR / 'daemon.mm').read_text())
        self.assertIn('@"MiniWattsChargeDaemon"', (VENDOR / 'ui.mm').read_text())

    def test_loopback_isolated_from_upstream(self):
        self.assertIn('GSERV_PORT      1231', (VENDOR / 'common.h').read_text())
        self.assertIn('@"BindToLocalhost": @YES', (VENDOR / 'daemon.mm').read_text())
        self.assertNotIn('/var/root/aldente.', (VENDOR / 'common.h').read_text())
        self.assertIn('dispatch_sync(dispatch_get_main_queue()', (VENDOR / 'daemon.mm').read_text())

    def test_privileges_and_url_registration(self):
        info = plistlib.loads((ROOT / 'MiniWatts/Info.plist').read_bytes())
        self.assertEqual(info['CFBundleURLTypes'][0]['CFBundleURLSchemes'], ['miniwatts', 'cl'])
        ent = plistlib.loads((ROOT / 'scripts/ChargeControl.entitlements').read_bytes())
        for key in ['com.apple.private.powersource-write', 'com.apple.private.persona-mgmt', 'com.apple.private.security.no-sandbox']:
            self.assertTrue(ent[key])
        self.assertNotIn('application-identifier', ent)

    def test_diagnostics_no_service_required(self):
        source = (ROOT / 'MiniWatts/ChargeControl/DiagnosticLog.swift').read_text()
        for marker in ['524288', 'redacted', 'Serial'.lower(), 'unavailable', 'userDescription']:
            self.assertIn(marker, source)
        self.assertIn('DiagnosticsView()', (ROOT / 'MiniWatts/Features/Debug/SettingsView.swift').read_text())

if __name__ == '__main__': unittest.main()
