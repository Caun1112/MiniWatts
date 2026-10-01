// MiniWatts integration, 2026. Validate every native, web and Shortcuts request.
static BOOL validConfig(NSString* key, id value) {
    NSArray* booleans = @[@"enable", @"always_on", @"floatwnd", @"floatwnd_auto", @"disable_smart_charge", @"enable_temp", @"acc_charge", @"acc_charge_airmode", @"acc_charge_wifi", @"acc_charge_blue", @"acc_charge_bright", @"acc_charge_lpm", @"adv_prefer_smart", @"adv_predictive_inhibit_charge", @"adv_disable_inflow", @"adv_limit_inflow", @"adv_thermal_mode_lock"];
    if ([booleans containsObject:key]) return [value isKindOfClass:NSNumber.class] && ([value isEqual:@0] || [value isEqual:@1]);
    if ([key isEqual:@"temp_mode"]) return [value isEqual:@0] || [value isEqual:@1];
    if ([key isEqual:@"mode"]) return [@[@"charge_on_plug", @"edge_trigger"] containsObject:value];
    if ([key isEqual:@"action"]) return [@[@"", @"noti"] containsObject:value];
    if ([@[@"adv_limit_inflow_mode", @"adv_def_thermal_mode", @"ppm_simulate_mode"] containsObject:key])
        return [@[@"off", @"nominal", @"light", @"moderate", @"heavy"] containsObject:value];
    if ([key isEqual:@"lang"]) return [value isKindOfClass:NSString.class] && [value length] <= 16;
    if (![value isKindOfClass:NSNumber.class] || !isfinite([value doubleValue])) return NO;
    double n = [value doubleValue];
    if ([key isEqual:@"update_freq"]) return n >= 1 && n <= 600;
    if ([key isEqual:@"charge_below"]) return n >= 5 && n < [getlocalKV(@"charge_above") doubleValue];
    if ([key isEqual:@"charge_above"]) return n <= 100 && n > [getlocalKV(@"charge_below") doubleValue];
    BOOL fahrenheit = [getlocalKV(@"temp_mode") boolValue];
    double c = fahrenheit ? (n - 32) / 1.8 : n;
    if ([key isEqual:@"charge_temp_below"]) return c >= 0 && n < [getlocalKV(@"charge_temp_above") doubleValue];
    if ([key isEqual:@"charge_temp_above"]) return c <= 50 && n > [getlocalKV(@"charge_temp_below") doubleValue];
    return NO;
}

NSDictionary* validatedRequest(id request) {
    NSDictionary* invalid = @{@"status": @-20, @"error": @"Invalid request or threshold range"};
    if (![request isKindOfClass:NSDictionary.class]) return invalid;
    NSString* api = request[@"api"];
    if (![api isKindOfClass:NSString.class]) return invalid;
    if ([api isEqual:@"get_diagnostics"]) {
        NSMutableDictionary* battery = [bat_info mutableCopy] ?: [NSMutableDictionary new];
        [battery removeObjectForKey:@"Serial"];
        NSString* log = [NSString stringWithContentsOfFile:@LOG_PATH encoding:NSUTF8StringEncoding error:nil] ?: @"No daemon log";
        if (log.length > 131072) log = [log substringFromIndex:log.length - 131072];
        return @{@"status": @0, @"data": @{@"battery": battery, @"config": getAllKV() ?: @{}, @"log": log, @"uid": @(getuid()), @"uptime_since": @(g_serv_boot)}};
    }
    if ([api isEqual:@"get_conf"]) {
        id key = request[@"key"];
        if (key && ![key isKindOfClass:NSString.class]) return invalid;
    } else if ([api isEqual:@"set_conf"]) {
        NSString* key = request[@"key"];
        id value = request[@"val"];
        if (![key isKindOfClass:NSString.class] || !value || !validConfig(key, value)) return invalid;
        if ([key isEqual:@"temp_mode"]) {
            NSArray* vals = request[@"vals"];
            if (![vals isKindOfClass:NSArray.class] || vals.count != 2 ||
                ![vals[0] isKindOfClass:NSNumber.class] || ![vals[1] isKindOfClass:NSNumber.class]) return invalid;
            double low = [vals[0] doubleValue], high = [vals[1] doubleValue];
            if ([value boolValue]) { low = (low-32)/1.8; high = (high-32)/1.8; }
            if (!isfinite(low) || !isfinite(high) || low < 0 || high > 50 || low >= high) return invalid;
        }
        if ([key isEqual:@"acc_charge"] && ![value boolValue]) performAcccharge(NO);
    } else if ([api isEqual:@"get_statistics"]) {
        NSDictionary* conf = request[@"conf"];
        if (![conf isKindOfClass:NSDictionary.class] || conf.count > 4) return invalid;
        for (NSString* table in conf) {
            if (![@[@"min5", @"hour", @"day", @"month"] containsObject:table]) return invalid;
            NSDictionary* c = conf[table];
            if (![c isKindOfClass:NSDictionary.class] || ![c[@"n"] isKindOfClass:NSNumber.class] || ![c[@"last_id"] isKindOfClass:NSNumber.class]) return invalid;
            if ([c[@"n"] intValue] < 1 || [c[@"n"] intValue] > 10000 || [c[@"last_id"] longLongValue] < 0) return invalid;
        }
    } else if ([@[@"set_charge_status", @"set_inflow_status"] containsObject:api]) {
        if (!validConfig(@"enable", request[@"flag"])) return invalid;
    } else if (![@[@"get_bat_info", @"reset_conf"] containsObject:api]) return invalid;
    NSDictionary* result = handleReq(request);
    if (![api hasPrefix:@"get_"]) NSFileLog(@"request %@ key=%@ value=%@ result=%@", api, request[@"key"] ?: @"-", request[@"val"] ?: request[@"flag"] ?: @"-", result);
    return result;
}
