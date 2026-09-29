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
#import <objc/runtime.h>
@interface MWTestBundle : NSObject
- (NSString*)bundlePath;
- (id)objectForInfoDictionaryKey:(NSString*)key;
@end
@implementation MWTestBundle
- (NSString*)bundlePath { return @"/nonexistent/miniwatts-test"; }
- (id)objectForInfoDictionaryKey:(NSString*)key { return [key isEqual:@"MWPackageFlavor"] ? @"Rootless-DEB" : nil; }
@end
int main(void) { @autoreleasepool {
    // Reproduce the actual failing package flavor, not a generic macOS bundle.
    MWTestBundle* bundle = [MWTestBundle new];
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
    puts("8 rootless launcher and retry-history checks passed");
} return 0; }
'''
with tempfile.TemporaryDirectory(prefix='miniwatts-launch-test-') as directory:
    path = pathlib.Path(directory)
    (path / 'test.m').write_text(source)
    subprocess.run(['xcrun', 'clang', '-fobjc-arc', '-framework', 'Foundation', str(path / 'test.m'), '-o', str(path / 'test')], check=True)
    subprocess.run([str(path / 'test')], check=True)
