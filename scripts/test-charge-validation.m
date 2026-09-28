#import <Foundation/Foundation.h>
#include <math.h>
#include <unistd.h>
#define LOG_PATH "/nonexistent/miniwatts-test.log"
static NSDictionary* bat_info;
static int g_serv_boot;
static NSMutableDictionary* config;
static int handled;
id getlocalKV(NSString* key) { return config[key]; }
NSDictionary* getAllKV(void) { return config; }
void performAcccharge(BOOL flag) {}
void NSFileLog(NSString* fmt, ...) {}
NSDictionary* handleReq(NSDictionary* req) { handled++; return @{@"status":@0}; }
#include "../Vendor/ChargeLimiter/RequestValidation.h"
static void check(id request, BOOL accepted) {
    int before = handled;
    NSDictionary* result = validatedRequest(request);
    NSCAssert(([result[@"status"] intValue] == 0) == accepted, @"Unexpected result for %@: %@", request, result);
    if (!accepted) NSCAssert(before == handled, @"Invalid request reached hardware handler");
}
int main(void) {
    @autoreleasepool {
        config = [@{@"charge_below":@20, @"charge_above":@80, @"charge_temp_below":@10, @"charge_temp_above":@35, @"temp_mode":@0} mutableCopy];
        check(nil, NO); check(@[], NO); check(@{@"api":@3}, NO);
        check(@{@"api":@"set_charge_status", @"flag":@YES}, YES);
        check(@{@"api":@"set_charge_status", @"flag":@"yes"}, NO);
        check(@{@"api":@"set_charge_status"}, NO);
        check(@{@"api":@"set_conf", @"key":@"charge_below", @"val":@80}, NO);
        check(@{@"api":@"set_conf", @"key":@"charge_below", @"val":@79}, YES);
        check(@{@"api":@"set_conf", @"key":@"charge_above", @"val":@20}, NO);
        check(@{@"api":@"set_conf", @"key":@"charge_above", @"val":@101}, NO);
        check(@{@"api":@"set_conf", @"key":@"charge_temp_above", @"val":@51}, NO);
        check(@{@"api":@"set_conf", @"key":@"charge_temp_below", @"val":@(-1)}, NO);
        check(@{@"api":@"set_conf", @"key":@"charge_temp_below", @"val":@35}, NO);
        check(@{@"api":@"set_conf", @"key":@"unknown", @"val":@YES}, NO);
        check(@{@"api":@"set_conf", @"key":@"mode", @"val":@"invalid"}, NO);
        check(@{@"api":@"set_conf", @"key":@"temp_mode", @"val":@1}, NO);
        check(@{@"api":@"set_conf", @"key":@"temp_mode", @"val":@1, @"vals":@[@50,@95]}, YES);
        check(@{@"api":@"set_conf", @"key":@"temp_mode", @"val":@1, @"vals":@[@95,@50]}, NO);
        check(@{@"api":@"get_statistics", @"conf":@{@"min5; DROP TABLE day":@{@"n":@1,@"last_id":@0}}}, NO);
        check(@{@"api":@"get_statistics", @"conf":@{@"min5":@{@"n":@10001,@"last_id":@0}}}, NO);
        check(@{@"api":@"get_statistics", @"conf":@{@"min5":@{@"n":@10000,@"last_id":@0}}}, YES);
        check(@{@"api":@"get_statistics", @"conf":@{@"min5":@3}}, NO);
        check(@{@"api":@"get_conf", @"key":@[]}, NO);
        config[@"temp_mode"]=@1; config[@"charge_temp_below"]=@50; config[@"charge_temp_above"]=@95;
        check(@{@"api":@"set_conf", @"key":@"charge_temp_above", @"val":@123}, NO);
        check(@{@"api":@"set_conf", @"key":@"charge_temp_below", @"val":@49}, YES);
        bat_info=@{@"Serial":@"private", @"Temperature":@3000};
        NSDictionary* data=validatedRequest(@{@"api":@"get_diagnostics"})[@"data"];
        NSCAssert(data[@"battery"][@"Serial"] == nil, @"Serial leaked into diagnostics");
        puts("25 request validation and redaction checks passed");
    }
}
