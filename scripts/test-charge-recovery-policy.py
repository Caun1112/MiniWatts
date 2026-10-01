#!/usr/bin/env python3
"""Run the daemon's real configuration and battery policy with hardware stubs."""
import pathlib
import subprocess
import tempfile

root = pathlib.Path(__file__).resolve().parents[1]
daemon = (root / 'Vendor/ChargeLimiter/daemon.mm').read_text()


def function(signature):
    start = daemon.index(signature)
    body = daemon.index('{', start)
    depth = 1
    end = body + 1
    while depth:
        depth += (daemon[end] == '{') - (daemon[end] == '}')
        end += 1
    return daemon[start:end]


source = r'''
#import <Foundation/Foundation.h>
#include <dispatch/dispatch.h>
#include <math.h>
#include <errno.h>
#include <unistd.h>
#define LOG_PATH "/nonexistent/miniwatts-test.log"
enum { CL_MODE_PLUG = 1, CL_MODE_EDGE = 2 };
static NSDictionary* bat_info;
static NSMutableDictionary* config;
static NSMutableDictionary* sample;
static NSMutableArray* writes;
static NSString* thermalMode;
static NSString* bundlePath;
static NSString* packageFlavor;
static NSSet* executablePaths;
static NSArray* spawnArgs;
static BOOL g_enable, g_policy_charging, g_enable_floatwnd, g_use_smart;
static BOOL sensorAvailable, hardwareFailure;
static int g_serv_boot, chargeWrites, actions, resets;
@interface TestUPS : NSObject
@property NSDictionary* props;
@end
@implementation TestUPS
@end
static TestUPS* gUPSPS;
@interface TestBundle : NSObject
+ (instancetype)mainBundle;
- (NSDictionary*)infoDictionary;
- (NSString*)bundlePath;
@end
@implementation TestBundle
+ (instancetype)mainBundle { return [TestBundle new]; }
- (NSDictionary*)infoDictionary { return packageFlavor ? @{ @"MWPackageFlavor": packageFlavor } : @{}; }
- (NSString*)bundlePath { return bundlePath; }
@end
@interface TestDefaults : NSObject
- (instancetype)initWithSuiteName:(NSString*)suite;
- (id)objectForKey:(NSString*)key;
@end
@implementation TestDefaults
- (instancetype)initWithSuiteName:(NSString*)suite { return [super init]; }
- (id)objectForKey:(NSString*)key { return thermalMode; }
@end
@interface TestFileManager : NSObject
+ (instancetype)defaultManager;
- (BOOL)isExecutableFileAtPath:(NSString*)path;
@end
@implementation TestFileManager
+ (instancetype)defaultManager { return [TestFileManager new]; }
- (BOOL)isExecutableFileAtPath:(NSString*)path { return [executablePaths containsObject:path]; }
@end
#define NSBundle TestBundle
#define NSUserDefaults TestDefaults
#define NSFileManager TestFileManager
id getlocalKV(NSString* key) { return config[key]; }
void setlocalKV(NSString* key, id val) { [writes addObject:@[key, val]]; config[key] = val; }
NSDictionary* getAllKV() { return config; }
io_service_t getIOPMPSServ() { return sensorAvailable ? 1 : IO_OBJECT_NULL; }
int getBatInfoWithServ(io_service_t service, NSDictionary* __strong* info) {
    if (!service || !sensorAvailable) return -1;
    *info = [sample copy]; return 0;
}
int getBatInfo(NSDictionary* __strong* info) { return getBatInfoWithServ(getIOPMPSServ(), info); }
int setChargeStatus(BOOL flag) {
    chargeWrites++;
    if (hardwareFailure) return -2;
    sample[@"IsCharging"] = @(flag); return 0;
}
int setInflowStatus(BOOL flag) { sample[@"ExternalConnected"] = @(flag); return 0; }
void resetBatteryStatus() { resets++; sample[@"IsCharging"] = @YES; }
void setThermalSimulationMode(NSString* mode) { thermalMode = mode; }
void setPPMSimulationMode(id mode) {}
void updateStatistics() {}
void performAcccharge(BOOL flag) {}
void performAction(NSString* action) { actions++; }
void NSFileLog(NSString* format, ...) {}
BOOL isSmartChargeEnable() { return NO; }
void setSmartChargeEnable(BOOL flag) {}
NSDictionary* getThermalData() { return @{}; }
NSString* getSysVer() { return @"18"; }
NSString* getDevMdoel() { return @"Test"; }
NSString* getAppVer() { return @"1"; }
int get_sys_boottime() { return 0; }
NSString* getThermalSimulationMode() { return thermalMode; }
NSString* getPPMSimulationMode() { return @"off"; }
NSDictionary* getDBData(const char* table, int n, int last) { return @{}; }
int showFloatwnd(BOOL flag) { return 0; }
int spawn(NSArray* args, NSString** out, NSString** err, pid_t* pid, int flags, NSDictionary* params) {
    spawnArgs = args; return 0;
}
@interface Service : NSObject
+ (instancetype)inst;
- (void)initLocalPush;
@end
@implementation Service
+ (instancetype)inst { return [Service new]; }
- (void)initLocalPush {}
@end
'''

source += '\n\n'.join(function(signature) for signature in [
    'static BOOL supportsAlwaysOn()',
    'static BOOL isAdaptorConnect(',
    'static BOOL isAdaptorNewConnect(',
    'static BOOL isAdaptorNewDisconnect(',
    'static void applyAutomaticThermalMode(',
    'static int setBatteryStatus(',
    'static void onBatteryEventEnd()',
    'static float getTempAsC(',
    'static void onBatteryEvent(',
    'static void initConf(',
    'NSDictionary* handleReq(NSDictionary* nsreq) {',
    'static int ensureRootlessChargeService()',
])
source += '\n#include "RequestValidation.h"\n'
source += r'''
static void check(BOOL condition, NSString* label) {
    NSCAssert(condition, @"%@", label);
}
static NSDictionary* set(NSString* key, id value) {
    return validatedRequest(@{@"api": @"set_conf", @"key": key, @"val": value});
}
static void resetFixture() {
    config = [NSMutableDictionary new]; writes = [NSMutableArray new];
    sample = [@{@"CurrentCapacity": @50, @"IsCharging": @YES,
                @"ExternalConnected": @YES, @"ExternalChargeCapable": @YES,
                @"Temperature": @2500, @"InstantAmperage": @1000} mutableCopy];
    bat_info = nil; sensorAvailable = YES; hardwareFailure = NO;
    g_enable = NO; g_policy_charging = NO; gUPSPS = nil;
    chargeWrites = actions = resets = 0; thermalMode = @"off";
    bundlePath = @"/var/jb/Applications/MiniWatts.app"; packageFlavor = @"Rootless-DEB";
    executablePaths = [NSSet setWithObject:@"/var/jb/bin/sh"];
    initConf(NO); [writes removeAllObjects];
}
int main() {
    @autoreleasepool {
        resetFixture();
        check(!g_enable && ![config[@"always_on"] boolValue], @"new installation is opt-in");
        check([set(@"always_on", @YES)[@"status"] intValue] == 0 && g_enable, @"always-on enables control");
        check([writes[0][0] isEqual:@"enable"] && [writes[1][0] isEqual:@"always_on"], @"enable persists before always-on");
        config[@"enable"] = @NO; g_enable = NO; initConf(NO);
        check(g_enable && [config[@"enable"] boolValue], @"restart restores always-on without app");
        [writes removeAllObjects]; set(@"enable", @NO);
        check(!g_enable && ![config[@"always_on"] boolValue], @"manual disable cancels recovery");
        check([writes[0][0] isEqual:@"always_on"] && [writes[1][0] isEqual:@"enable"], @"cancellation persists first");
        initConf(NO); check(!g_enable, @"manual disable survives restart");
        set(@"always_on", @YES); set(@"always_on", @NO);
        check(g_enable && ![config[@"always_on"] boolValue], @"disabling recovery leaves manual control enabled");
        check([set(@"always_on", @2)[@"status"] intValue] == -20, @"boolean validation applies to recovery");
        resetFixture(); bundlePath = @"/var/containers/Bundle/Application/id/MiniWatts.app"; packageFlavor = @"TrollStore";
        check(!supportsAlwaysOn(), @"TrollStore has no boot recovery support");
        check([set(@"always_on", @YES)[@"status"] intValue] == -22 && writes.count == 0, @"unsupported recovery cannot persist");
        check([set(@"always_on", @NO)[@"status"] intValue] == 0, @"unsupported package can clear migrated setting");
        packageFlavor = @"Rootless-DEB"; check(supportsAlwaysOn(), @"package flavor supports resolved preboot path");
        resetFixture(); config[@"always_on"] = @YES; initConf(NO); bat_info = nil;
        sample[@"CurrentCapacity"] = @90; onBatteryEvent(1);
        check(![sample[@"IsCharging"] boolValue] && chargeWrites == 1, @"restart immediately enforces upper charge threshold");
        resetFixture(); g_enable = YES; sample[@"IsCharging"] = @NO; onBatteryEvent(1);
        check([sample[@"IsCharging"] boolValue], @"startup applies preconnected adapter in plug mode");
        resetFixture(); g_enable = YES; config[@"mode"] = @"edge_trigger"; onBatteryEvent(1);
        check(![sample[@"IsCharging"] boolValue], @"startup applies preconnected adapter in edge mode");
        resetFixture(); g_enable = YES; sensorAvailable = NO; onBatteryEvent(0);
        check(chargeWrites == 0, @"late sensor makes no hardware write");
        sensorAvailable = YES; sample[@"CurrentCapacity"] = @90; onBatteryEvent(1);
        check(chargeWrites == 1, @"periodic recovery applies after sensor becomes available");
        resetFixture(); g_enable = YES; [sample removeObjectForKey:@"CurrentCapacity"]; onBatteryEvent(1);
        check(chargeWrites == 0, @"missing capacity never means empty battery");
        sample[@"CurrentCapacity"] = @(NAN); onBatteryEvent(1);
        check(chargeWrites == 0, @"invalid capacity never triggers hardware");
        sample[@"CurrentCapacity"] = @90; [sample removeObjectForKey:@"ExternalChargeCapable"]; onBatteryEvent(1);
        check(chargeWrites == 0, @"missing adapter state never triggers hardware");
        resetFixture(); g_enable = YES; config[@"enable_temp"] = @YES;
        [sample removeObjectForKey:@"Temperature"]; onBatteryEvent(1);
        check(chargeWrites == 0, @"missing enabled temperature sensor never triggers hardware");
        sample[@"Temperature"] = @(NAN); onBatteryEvent(1);
        check(chargeWrites == 0, @"invalid temperature never triggers hardware");
        resetFixture(); g_enable = YES; sample[@"CurrentCapacity"] = @10; sample[@"IsCharging"] = @NO;
        onBatteryEvent(1); onBatteryEvent(1);
        check(chargeWrites == 1 && actions == 1, @"recovery polling does not repeat low-capacity start notifications");
        resetFixture(); g_enable = YES; bat_info = [sample copy];
        set(@"adv_limit_inflow", @YES);
        check([thermalMode isEqual:@"moderate"], @"limit applies immediately during existing charge session");
        set(@"adv_limit_inflow_mode", @"heavy");
        check([thermalMode isEqual:@"heavy"], @"mode change applies immediately");
        set(@"adv_limit_inflow", @NO);
        check([thermalMode isEqual:@"off"], @"disable immediately restores default thermal mode");
        set(@"adv_limit_inflow", @YES); sample[@"ExternalChargeCapable"] = @NO; sample[@"IsCharging"] = @NO; onBatteryEvent(1);
        check([thermalMode isEqual:@"off"], @"unplug removes charging thermal simulation");
        sample[@"ExternalChargeCapable"] = @YES; sample[@"IsCharging"] = @YES; onBatteryEvent(1);
        set(@"adv_thermal_mode_lock", @YES);
        check([thermalMode isEqual:@"off"], @"thermal lock remains authoritative");
        set(@"adv_thermal_mode_lock", @NO); set(@"enable", @NO);
        thermalMode = @"heavy"; set(@"adv_limit_inflow", @NO);
        check([thermalMode isEqual:@"off"], @"limit disable restores thermal while main control off");
        resetFixture(); g_enable = YES; config[@"adv_limit_inflow"] = @YES;
        hardwareFailure = YES; sample[@"IsCharging"] = @NO; onBatteryEvent(1);
        check([thermalMode isEqual:@"off"], @"failed charge start cannot enable charging thermal simulation");
        resetFixture(); bat_info = [sample copy]; NSDictionary* history = bat_info;
        sample[@"InstantAmperage"] = @500;
        NSDictionary* current = handleReq(@{@"api": @"get_bat_info"})[@"data"];
        check([current[@"InstantAmperage"] intValue] == 500 && bat_info == history && [bat_info[@"InstantAmperage"] intValue] == 1000, @"live sensor read preserves plug edge history");
        resetFixture(); check(ensureRootlessChargeService() == 0 && [spawnArgs[0] isEqual:@"/var/jb/bin/sh"], @"rootless shell preferred");
        executablePaths = [NSSet setWithObject:@"/var/jb/usr/bin/sh"];
        check(ensureRootlessChargeService() == 0 && [spawnArgs[0] isEqual:@"/var/jb/usr/bin/sh"], @"alternate rootless shell supported");
        executablePaths = [NSSet setWithObject:@"/bin/sh"];
        check(ensureRootlessChargeService() == 0 && [spawnArgs[0] isEqual:@"/bin/sh"], @"stock shell fallback supported");
        executablePaths = [NSSet set]; check(ensureRootlessChargeService() == ENOENT, @"missing shell reports failure");
        puts("Always-on persistence, reboot policy, sensor recovery, live current and thermal checks passed");
    }
}
'''

with tempfile.TemporaryDirectory(prefix='miniwatts-recovery-policy-') as folder:
    folder = pathlib.Path(folder)
    (folder / 'policy.mm').write_text(source)
    subprocess.run(['xcrun', 'clang++', '-fobjc-arc', '-fblocks', '-std=c++17',
                    '-framework', 'Foundation', '-I' + str(root / 'Vendor/ChargeLimiter'),
                    str(folder / 'policy.mm'), '-o', str(folder / 'policy')], check=True)
    subprocess.run([str(folder / 'policy')], check=True)
