#!/usr/bin/env python3
"""Run the real Foundation-only launcher against missing and executable helpers.
No iOS app is built locally; all IPA/DEB builds remain in GitHub Actions.
"""
import pathlib
import subprocess
import tempfile

root = pathlib.Path(__file__).resolve().parents[1]
source = (root / 'MiniWatts/ChargeControl/ChargeControlBridge.m').read_text()
source = source.split('// UIWebView is intentional:')[0].replace('#import "ChargeControlBridge.h"', '#import <Foundation/Foundation.h>')
source = '''
#import <Foundation/Foundation.h>
#include <unistd.h>
// Model a helper whose persona was already elevated. Actual spawning, stdout
// capture, waitpid and child exit handling remain unchanged and run on macOS.
static BOOL MWTestPrivileged;
static uid_t MWTestGetEUID(void) { return MWTestPrivileged ? 0 : geteuid(); }
#define geteuid MWTestGetEUID
''' + source + r'''
#import <objc/runtime.h>
@interface MWTestBundle : NSObject
@property NSString* testPath;
@property NSString* flavor;
- (NSString*)bundlePath;
- (id)objectForInfoDictionaryKey:(NSString*)key;
@end
@implementation MWTestBundle
- (NSString*)bundlePath { return self.testPath; }
- (id)objectForInfoDictionaryKey:(NSString*)key { return [key isEqual:@"MWPackageFlavor"] ? self.flavor : nil; }
@end
static NSDictionary* waitForChildExit(void) {
    for (int i=0; i<1000; i++) {
        NSDictionary* report = MWChargeLaunchDiagnostics();
        if ([report[@"lastLaunch"][@"stage"] isEqual:@"exited"] &&
            [report[@"helperOutput"] hasSuffix:@"OUTPUT_END\n"]) return report;
        usleep(5000);
    }
    NSCAssert(NO, @"Launcher did not capture/reap the child: %@", MWChargeLaunchDiagnostics());
    return nil;
}
int main(int argc, char** argv) { @autoreleasepool {
    // Reproduce the actual failing package flavor, not a generic macOS bundle.
    MWTestBundle* bundle = [MWTestBundle new];
    NSString* fixture = @(argv[1]);
    bundle.testPath = [fixture stringByAppendingPathComponent:@"missing"];
    bundle.flavor = @"Rootless-DEB";
    Method method = class_getClassMethod(NSBundle.class, @selector(mainBundle));
    method_setImplementation(method, imp_implementationWithBlock(^id(id cls) { return bundle; }));
    int code = MWStartChargeService();
    NSCAssert(code == ENOENT, @"Missing helper must reach lookup, not synthetic permission denial");
    NSDictionary* report = MWChargeLaunchDiagnostics();
    NSCAssert([report[@"lastLaunch"][@"stage"] isEqual:@"helper_lookup"], @"Missing launch stage");
    NSCAssert([report[@"lastLaunch"][@"errno"] intValue] == ENOENT, @"Wrong launch error");
    NSCAssert(report[@"entitlements"] != nil, @"Missing entitlement diagnostics");
    NSCAssert([report[@"childRunning"] isEqual:@NO], @"Missing helper cannot be running");
    NSCAssert(MWStartChargeService() == ENOENT, @"Retry should still reach lookup");
    NSDictionary* retried = MWChargeLaunchDiagnostics();
    NSCAssert([retried[@"launchHistory"] count] == 1, @"Retry discarded previous launch failure");
    NSCAssert([retried[@"launchHistory"][0][@"stage"] isEqual:@"helper_lookup"], @"Previous failure stage lost");

    bundle.testPath = fixture;
    MWTestPrivileged = YES;
    NSString* argumentFile = [fixture stringByAppendingPathComponent:@"MiniWattsChargeDaemon.args"];
    for (int attempt=0; attempt<6; attempt++) {
        NSCAssert(MWStartChargeService() == 0, @"A prior failed recovery must permit another attempt");
        NSCAssert(MWStartChargeService() == EALREADY, @"Concurrent recovery must not spawn a second manager");
        report = waitForChildExit();
        NSString* arguments = [NSString stringWithContentsOfFile:argumentFile encoding:NSUTF8StringEncoding error:nil];
        NSCAssert([arguments isEqual:@"ensure-launchd\n"], @"Rootless recovery started an unsupervised daemon: %@", arguments);
        NSCAssert([report[@"recoveryMode"] isEqual:@"launchd"], @"Wrong rootless recovery diagnostic");
        NSCAssert([report[@"lastLaunch"][@"exitCode"] intValue] == 23, @"Management failure must remain visible");
        NSCAssert([report[@"childRunning"] isEqual:@NO], @"Exited management child still marked running");
        NSCAssert([report[@"helperOutput"] length] == 65536, @"Verbose management output must retain only its bounded tail");
    }
    NSCAssert([report[@"launchHistory"] count] == 4, @"Retry history must remain bounded");
    NSCAssert([report[@"launchHistory"][3][@"exitCode"] intValue] == 23, @"Prior management failure lost");
    NSCAssert([report[@"launchHistory"][3][@"output"] hasSuffix:@"OUTPUT_END\n"], @"Prior recovery output lost");

    bundle.flavor = @"TrollStore";
    NSCAssert(MWStartChargeService() == 0, @"TrollStore direct launch regressed");
    report = waitForChildExit();
    NSString* arguments = [NSString stringWithContentsOfFile:argumentFile encoding:NSUTF8StringEncoding error:nil];
    NSCAssert([arguments isEqual:@"\n"], @"TrollStore direct launch must not require rootless launchd paths");
    NSCAssert([report[@"recoveryMode"] isEqual:@"direct"], @"Wrong TrollStore recovery diagnostic");
    NSCAssert([report[@"lastLaunch"][@"exitCode"] intValue] == 0, @"Wrong direct child exit status");
    puts("Rootless managed recovery, real child capture/exit/retry, bounded history and TrollStore compatibility checks passed");
} return 0; }
'''
with tempfile.TemporaryDirectory(prefix='miniwatts-launch-test-') as directory:
    path = pathlib.Path(directory)
    helper = path / 'MiniWattsChargeDaemon'
    helper.write_text(r'''#!/bin/sh
printf '%s\n' "$@" > "$0.args"
dd if=/dev/zero bs=70000 count=1 2>/dev/null | tr '\000' 'x'
printf 'OUTPUT_END\n'
sleep 0.1
if [ "$#" = 1 ] && [ "$1" = ensure-launchd ]; then exit 23; fi
exit 0
''')
    helper.chmod(0o755)
    (path / 'test.m').write_text(source)
    subprocess.run(['xcrun', 'clang', '-fobjc-arc', '-framework', 'Foundation', str(path / 'test.m'), '-o', str(path / 'test')], check=True)
    subprocess.run([str(path / 'test'), str(path)], check=True, timeout=30)
