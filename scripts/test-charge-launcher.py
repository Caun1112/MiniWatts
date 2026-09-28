#!/usr/bin/env python3
"""Run the real Foundation-only launcher against a missing helper on macOS.
No iOS app is built locally; all IPA/DEB builds remain in GitHub Actions.
"""
import pathlib
import subprocess
import tempfile

source = pathlib.Path('MiniWatts/ChargeControl/ChargeControlBridge.m').read_text()
source = source.split('// UIWebView is intentional:')[0].replace('#import "ChargeControlBridge.h"', '#import <Foundation/Foundation.h>')
source += '''
int main(void) { @autoreleasepool {
    int code = MWStartChargeService();
    NSCAssert(code == ENOENT, @"Missing helper must reach lookup, not synthetic permission denial");
    NSDictionary* report = MWChargeLaunchDiagnostics();
    NSCAssert([report[@"lastLaunch"][@"stage"] isEqual:@"helper_lookup"], @"Missing launch stage");
    NSCAssert([report[@"lastLaunch"][@"errno"] intValue] == ENOENT, @"Wrong launch error");
    NSCAssert(report[@"entitlements"] != nil, @"Missing entitlement diagnostics");
    NSCAssert([report[@"childRunning"] isEqual:@NO], @"Missing helper cannot be running");
    puts("5 launcher preflight regression checks passed");
} return 0; }
'''
with tempfile.TemporaryDirectory(prefix='miniwatts-launch-test-') as directory:
    path = pathlib.Path(directory)
    (path / 'test.m').write_text(source)
    subprocess.run(['xcrun', 'clang', '-fobjc-arc', '-framework', 'Foundation', str(path / 'test.m'), '-o', str(path / 'test')], check=True)
    subprocess.run([str(path / 'test')], check=True)
