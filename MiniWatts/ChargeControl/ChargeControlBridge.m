#import "ChargeControlBridge.h"
#import <dlfcn.h>
#import <spawn.h>
#import <sys/wait.h>
#import <fcntl.h>
#import <errno.h>
#import <unistd.h>
#import <string.h>

// Capability reporting is diagnostic only. The kernel's spawn result is authoritative.
static NSObject* MWLaunchLock(void) {
    static NSObject* lock;
    static dispatch_once_t once;
    dispatch_once(&once, ^{ lock = [NSObject new]; });
    return lock;
}
static NSMutableDictionary* MWLastLaunch;
static NSMutableData* MWLaunchOutput;
static NSMutableArray* MWLaunchHistory;
static pid_t MWChildPID;
static BOOL MWLaunchPending;
static void MWLaunchState(NSString* stage, int code, pid_t pid) {
    @synchronized (MWLaunchLock()) {
        if (!MWLastLaunch) MWLastLaunch = [NSMutableDictionary new];
        MWLastLaunch[@"stage"] = stage;
        MWLastLaunch[@"errno"] = @(code);
        MWLastLaunch[@"error"] = code ? @(strerror(code)) : @"none";
        MWLastLaunch[@"pid"] = @(pid);
        MWLastLaunch[@"updatedAt"] = [NSISO8601DateFormatter.new stringFromDate:NSDate.date];
    }
}
static NSDictionary* MWEntitlementReport(void) {
    typedef CFTypeRef (*CreateTask)(CFAllocatorRef);
    typedef CFTypeRef (*CopyEntitlement)(CFTypeRef, CFStringRef, CFErrorRef*);
    static void* security;
    static dispatch_once_t once;
    dispatch_once(&once, ^{ security = dlopen("/System/Library/Frameworks/Security.framework/Security", RTLD_LAZY); });
    CreateTask create = security ? (CreateTask)dlsym(security, "SecTaskCreateFromSelf") : NULL;
    CopyEntitlement copy = security ? (CopyEntitlement)dlsym(security, "SecTaskCopyValueForEntitlement") : NULL;
    NSMutableDictionary* result = [NSMutableDictionary new];
    result[@"queryAvailable"] = @(create && copy);
    if (!create || !copy) return result;
    CFTypeRef task = create(kCFAllocatorDefault);
    if (!task) { result[@"queryAvailable"] = @NO; return result; }
    for (NSString* key in @[@"com.apple.private.security.no-sandbox", @"com.apple.private.security.no-container", @"com.apple.private.security.container-required", @"com.apple.private.persona-mgmt", @"platform-application"]) {
        CFErrorRef error = NULL;
        CFTypeRef value = copy(task, (__bridge CFStringRef)key, &error);
        result[key] = value ? CFBridgingRelease(value) : NSNull.null;
        if (error) { result[@"queryError"] = @(CFErrorGetCode(error)); CFRelease(error); }
    }
    CFRelease(task);
    return result;
}
BOOL MWHasChargePrivileges(void) {
    if (geteuid() == 0) return YES;
    NSDictionary* ent = MWEntitlementReport();
    BOOL unsandboxed = [ent[@"com.apple.private.security.no-sandbox"] isEqual:@YES] ||
        [ent[@"com.apple.private.security.no-container"] isEqual:@YES] ||
        [ent[@"com.apple.private.security.container-required"] isEqual:@NO];
    return unsandboxed && [ent[@"com.apple.private.persona-mgmt"] isEqual:@YES];
}
NSDictionary* MWChargeLaunchDiagnostics(void) {
    NSString* path = [NSBundle.mainBundle.bundlePath stringByAppendingPathComponent:@"MiniWattsChargeDaemon"];
    NSMutableDictionary* report = [@{@"uid": @(getuid()), @"euid": @(geteuid()),
        @"entitlements": MWEntitlementReport(),
        @"packageFlavor": [NSBundle.mainBundle objectForInfoDictionaryKey:@"MWPackageFlavor"] ?: @"unknown",
        @"recoveryMode": [[NSBundle.mainBundle objectForInfoDictionaryKey:@"MWPackageFlavor"] isEqual:@"Rootless-DEB"] ? @"launchd" : @"direct",
        @"helperPresent": @([NSFileManager.defaultManager fileExistsAtPath:path]),
        @"helperExecutable": @([NSFileManager.defaultManager isExecutableFileAtPath:path])} mutableCopy];
    @synchronized (MWLaunchLock()) {
        report[@"lastLaunch"] = [MWLastLaunch copy] ?: @{@"stage": @"not_attempted"};
        report[@"helperOutput"] = [[NSString alloc] initWithData:MWLaunchOutput ?: NSData.data encoding:NSUTF8StringEncoding] ?: @"[non-UTF8 output]";
        report[@"childRunning"] = @(MWChildPID > 0);
        report[@"launchHistory"] = [MWLaunchHistory copy] ?: @[];
    }
    NSDictionary* paths = @{
        @"launchdOutput": @"/var/jb/var/log/miniwatts-charge-startup.log",
        @"installOutput": @"/var/jb/var/log/miniwatts-charge-install.log"
    };
    for (NSString* key in paths) {
        NSFileHandle* log = [NSFileHandle fileHandleForReadingAtPath:paths[key]];
        NSString* stateKey = [key stringByAppendingString:@"State"];
        report[stateKey] = [NSFileManager.defaultManager fileExistsAtPath:paths[key]] ? @"unreadable" : @"missing";
        if (log) {
            @try {
                unsigned long long length = [log seekToEndOfFile];
                [log seekToFileOffset:length > 65536 ? length - 65536 : 0];
                report[key] = [[NSString alloc] initWithData:[log readDataToEndOfFile] encoding:NSUTF8StringEncoding] ?: @"[non-UTF8 output]";
                report[stateKey] = length ? @"readable" : @"empty";
            } @catch (NSException* exception) { report[stateKey] = @"read_failed"; }
            [log closeFile];
        }
    }
    return report;
}

int MWStartChargeService(void) {
    @synchronized (MWLaunchLock()) {
        if (MWChildPID > 0 || MWLaunchPending) return EALREADY;
        MWLaunchPending = YES;
        if (MWLastLaunch) {
            if (!MWLaunchHistory) MWLaunchHistory = [NSMutableArray new];
            NSMutableDictionary* previous = [MWLastLaunch mutableCopy];
            previous[@"output"] = [[NSString alloc] initWithData:MWLaunchOutput ?: NSData.data encoding:NSUTF8StringEncoding] ?: @"[non-UTF8 output]";
            [MWLaunchHistory addObject:previous];
            if (MWLaunchHistory.count > 4) [MWLaunchHistory removeObjectAtIndex:0];
        }
        MWLastLaunch = [NSMutableDictionary new];
        MWLaunchOutput = [NSMutableData new];
    }
    NSString* path = [NSBundle.mainBundle.bundlePath stringByAppendingPathComponent:@"MiniWattsChargeDaemon"];
    int result = 0;
    pid_t pid = 0;
    NSString* stage = @"helper_lookup";
    posix_spawnattr_t attr;
    posix_spawn_file_actions_t actions;
    BOOL attrReady = NO, actionsReady = NO;
    int output[2] = {-1, -1};
    do {
        if (![NSFileManager.defaultManager isExecutableFileAtPath:path]) { result = ENOENT; break; }
        stage = @"spawn_attributes";
        result = posix_spawnattr_init(&attr);
        if (result) break;
        attrReady = YES;
        result = posix_spawnattr_setflags(&attr, POSIX_SPAWN_CLOEXEC_DEFAULT);
        if (result) break;
        if (geteuid() != 0) {
            typedef int (*SetPersona)(const posix_spawnattr_t*, uid_t, uint32_t);
            typedef int (*SetID)(const posix_spawnattr_t*, uid_t);
            SetPersona persona = (SetPersona)dlsym(RTLD_DEFAULT, "posix_spawnattr_set_persona_np");
            SetID uid = (SetID)dlsym(RTLD_DEFAULT, "posix_spawnattr_set_persona_uid_np");
            SetID gid = (SetID)dlsym(RTLD_DEFAULT, "posix_spawnattr_set_persona_gid_np");
            stage = @"persona_symbols";
            if (!persona || !uid || !gid) { result = ENOSYS; break; }
            stage = @"persona_configuration";
            result = persona(&attr, 99, 1);
            if (!result) result = uid(&attr, 0);
            if (!result) result = gid(&attr, 0);
            if (result) break;
        }
        stage = @"capture_setup";
        if (pipe(output) != 0) { result = errno; break; }
        result = posix_spawn_file_actions_init(&actions);
        if (result) break;
        actionsReady = YES;
        result = posix_spawn_file_actions_addopen(&actions, STDIN_FILENO, "/dev/null", O_RDONLY, 0);
        if (!result) result = posix_spawn_file_actions_adddup2(&actions, output[1], STDOUT_FILENO);
        if (!result) result = posix_spawn_file_actions_adddup2(&actions, output[1], STDERR_FILENO);
        if (!result) result = posix_spawn_file_actions_addclose(&actions, output[0]);
        if (!result) result = posix_spawn_file_actions_addclose(&actions, output[1]);
        if (result) break;
        BOOL rootless = [[NSBundle.mainBundle objectForInfoDictionaryKey:@"MWPackageFlavor"] isEqual:@"Rootless-DEB"];
        // Recovery must return the rootless service to launchd supervision, so it
        // can restart even after the UI exits. The child is only a manager.
        char* args[] = {(char*)path.fileSystemRepresentation, rootless ? "ensure-launchd" : NULL, NULL};
        char* env[] = {"PATH=/var/jb/usr/bin:/var/jb/bin:/var/jb/usr/sbin:/var/jb/sbin:/usr/bin:/bin:/usr/sbin:/sbin", NULL};
        stage = @"posix_spawn";
        result = posix_spawn(&pid, path.fileSystemRepresentation, &actions, &attr, args, env);
    } while (NO);
    if (actionsReady) posix_spawn_file_actions_destroy(&actions);
    if (attrReady) posix_spawnattr_destroy(&attr);
    if (output[1] >= 0) close(output[1]);
    MWLaunchState(result ? stage : @"spawned", result, pid);
    @synchronized (MWLaunchLock()) {
        MWLaunchPending = NO;
        if (!result) MWChildPID = pid;
    }
    if (result) { if (output[0] >= 0) close(output[0]); return result; }
    // Drain continuously, retaining only 64 KiB. Captures dyld and early startup errors
    // even when the HTTP service never opens its socket.
    int readFD = output[0];
    dispatch_async(dispatch_get_global_queue(QOS_CLASS_UTILITY, 0), ^{
        char buffer[4096];
        ssize_t count;
        while (YES) {
            count = read(readFD, buffer, sizeof(buffer));
            if (count < 0 && errno == EINTR) continue;
            if (count <= 0) break;
            @synchronized (MWLaunchLock()) {
                if ([MWLastLaunch[@"pid"] intValue] != pid) break;
                [MWLaunchOutput appendBytes:buffer length:(NSUInteger)count];
                if (MWLaunchOutput.length > 65536) [MWLaunchOutput replaceBytesInRange:NSMakeRange(0, MWLaunchOutput.length - 65536) withBytes:NULL length:0];
            }
        }
        close(readFD);
    });
    dispatch_async(dispatch_get_global_queue(QOS_CLASS_UTILITY, 0), ^{
        int status = 0;
        pid_t waited;
        do { waited = waitpid(pid, &status, 0); } while (waited < 0 && errno == EINTR);
        @synchronized (MWLaunchLock()) {
            if (MWChildPID == pid) {
                MWChildPID = 0;
                MWLastLaunch[@"stage"] = waited < 0 ? @"wait_failed" : @"exited";
                if (waited > 0 && WIFEXITED(status)) MWLastLaunch[@"exitCode"] = @(WEXITSTATUS(status));
                if (waited > 0 && WIFSIGNALED(status)) MWLastLaunch[@"signal"] = @(WTERMSIG(status));
            }
        }
    });
    return 0;
}

// UIWebView is intentional: upstream documents WKWebView's container requirement
// breaking privileged/no-container installations on iOS 16+. Only loopback pages
// are loaded here; external links are handed to the system browser.
#pragma clang diagnostic push
#pragma clang diagnostic ignored "-Wdeprecated-declarations"
@interface MWChargeWebView () <UIWebViewDelegate>
@property(nonatomic, strong) UIWebView* web;
@end
@implementation MWChargeWebView
- (instancetype)initWithFrame:(CGRect)frame {
    if ((self = [super initWithFrame:frame])) {
        _web = [[UIWebView alloc] initWithFrame:self.bounds];
        _web.autoresizingMask = UIViewAutoresizingFlexibleWidth | UIViewAutoresizingFlexibleHeight;
        _web.delegate = self;
        _web.opaque = NO;
        _web.backgroundColor = UIColor.clearColor;
        [self addSubview:_web];
    }
    return self;
}
- (void)loadPage:(NSString*)page {
    if (![@[@"index.html", @"history.html", @"help.html"] containsObject:page]) return;
    NSURL* url = [NSURL URLWithString:[@"http://127.0.0.1:1231/" stringByAppendingString:page]];
    [self.web loadRequest:[NSURLRequest requestWithURL:url cachePolicy:NSURLRequestReloadIgnoringLocalCacheData timeoutInterval:8]];
}
- (void)stop { [self.web stopLoading]; self.web.delegate = nil; [self.web loadHTMLString:@"" baseURL:nil]; }
- (void)webViewDidFinishLoad:(UIWebView*)webView {
    [webView stringByEvaluatingJavaScriptFromString:@"window.set_pb=function(s){location.href='miniwatts-copy://text?value='+encodeURIComponent(s);};window.onerror=function(m,u,l){location.href='miniwatts-log://error?value='+encodeURIComponent(m+' line='+l);};"];
    if (self.eventHandler) self.eventHandler(@"control page loaded");
}
- (void)webView:(UIWebView*)webView didFailLoadWithError:(NSError*)error {
    if (self.eventHandler) self.eventHandler([NSString stringWithFormat:@"control page error domain=%@ code=%ld", error.domain, (long)error.code]);
}
- (BOOL)webView:(UIWebView*)webView shouldStartLoadWithRequest:(NSURLRequest*)request navigationType:(UIWebViewNavigationType)type {
    NSURL* url = request.URL;
    if ([@[@"miniwatts-copy", @"miniwatts-log"] containsObject:url.scheme]) {
        NSURLComponents* parts = [NSURLComponents componentsWithURL:url resolvingAgainstBaseURL:NO];
        for (NSURLQueryItem* item in parts.queryItems) if ([item.name isEqual:@"value"]) {
            if ([url.scheme isEqual:@"miniwatts-copy"]) UIPasteboard.generalPasteboard.string = item.value;
            else if (self.eventHandler) self.eventHandler(item.value ?: @"web error");
        }
        return NO;
    }
    if ([url.scheme isEqual:@"about"]) return YES;
    if ([url.host isEqual:@"127.0.0.1"] && url.port.intValue == 1231 && [url.scheme isEqual:@"http"]) return YES;
    if (type == UIWebViewNavigationTypeLinkClicked && [@[@"https", @"http"] containsObject:url.scheme]) {
        [UIApplication.sharedApplication openURL:url options:@{} completionHandler:nil];
    }
    return NO;
}
@end
#pragma clang diagnostic pop
