#import "ChargeControlBridge.h"
#import <dlfcn.h>
#import <spawn.h>
#import <sys/wait.h>
#import <fcntl.h>
#import <errno.h>

BOOL MWHasChargePrivileges(void) {
    typedef CFTypeRef (*CreateTask)(CFAllocatorRef);
    typedef CFTypeRef (*CopyEntitlement)(CFTypeRef, CFStringRef, CFErrorRef*);
    CreateTask create = (CreateTask)dlsym(RTLD_DEFAULT, "SecTaskCreateFromSelf");
    CopyEntitlement copy = (CopyEntitlement)dlsym(RTLD_DEFAULT, "SecTaskCopyValueForEntitlement");
    if (!create || !copy) return NO;
    CFTypeRef task = create(kCFAllocatorDefault);
    if (!task) return NO;
    CFTypeRef value = copy(task, CFSTR("com.apple.private.security.no-sandbox"), NULL);
    BOOL allowed = value && CFEqual(value, kCFBooleanTrue);
    if (value) CFRelease(value);
    CFRelease(task);
    return allowed;
}

int MWStartChargeService(void) {
    if (!MWHasChargePrivileges()) return EPERM;
    NSString* path = [NSBundle.mainBundle.bundlePath stringByAppendingPathComponent:@"MiniWattsChargeDaemon"];
    if (![[NSFileManager defaultManager] isExecutableFileAtPath:path]) return ENOENT;
    typedef int (*SetPersona)(const posix_spawnattr_t*, uid_t, uint32_t);
    typedef int (*SetID)(const posix_spawnattr_t*, uid_t);
    SetPersona persona = (SetPersona)dlsym(RTLD_DEFAULT, "posix_spawnattr_set_persona_np");
    SetID uid = (SetID)dlsym(RTLD_DEFAULT, "posix_spawnattr_set_persona_uid_np");
    SetID gid = (SetID)dlsym(RTLD_DEFAULT, "posix_spawnattr_set_persona_gid_np");
    if (!persona || !uid || !gid) return ENOSYS;
    posix_spawnattr_t attr;
    int result = posix_spawnattr_init(&attr);
    if (result) return result;
    result = persona(&attr, 99, 1);
    if (!result) result = uid(&attr, 0);
    if (!result) result = gid(&attr, 0);
    posix_spawn_file_actions_t actions;
    posix_spawn_file_actions_init(&actions);
    posix_spawn_file_actions_addopen(&actions, STDIN_FILENO, "/dev/null", O_RDONLY, 0);
    posix_spawn_file_actions_addopen(&actions, STDOUT_FILENO, "/dev/null", O_WRONLY, 0);
    posix_spawn_file_actions_addopen(&actions, STDERR_FILENO, "/dev/null", O_WRONLY, 0);
    pid_t pid = 0;
    char* args[] = {(char*)path.fileSystemRepresentation, NULL};
    char* env[] = {"PATH=/usr/bin:/bin:/usr/sbin:/sbin", NULL};
    if (!result) result = posix_spawn(&pid, path.fileSystemRepresentation, &actions, &attr, args, env);
    posix_spawn_file_actions_destroy(&actions);
    posix_spawnattr_destroy(&attr);
    if (!result) dispatch_async(dispatch_get_global_queue(QOS_CLASS_UTILITY, 0), ^{ waitpid(pid, NULL, 0); });
    return result;
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
    if (self.eventHandler) self.eventHandler(@"control page loaded");
}
- (void)webView:(UIWebView*)webView didFailLoadWithError:(NSError*)error {
    if (self.eventHandler) self.eventHandler([NSString stringWithFormat:@"control page error domain=%@ code=%ld", error.domain, (long)error.code]);
}
- (BOOL)webView:(UIWebView*)webView shouldStartLoadWithRequest:(NSURLRequest*)request navigationType:(UIWebViewNavigationType)type {
    NSURL* url = request.URL;
    if ([url.scheme isEqual:@"about"]) return YES;
    if ([url.host isEqual:@"127.0.0.1"] && url.port.intValue == 1231 && [url.scheme isEqual:@"http"]) return YES;
    if (type == UIWebViewNavigationTypeLinkClicked && [@[@"https", @"http"] containsObject:url.scheme]) {
        [UIApplication.sharedApplication openURL:url options:@{} completionHandler:nil];
    }
    return NO;
}
@end
#pragma clang diagnostic pop
