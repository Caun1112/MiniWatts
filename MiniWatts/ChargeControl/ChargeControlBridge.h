#import <UIKit/UIKit.h>
NS_ASSUME_NONNULL_BEGIN
/// Returns errno; 0 means spawned, never that charging was changed.
int MWStartChargeService(void);
BOOL MWHasChargePrivileges(void);
NSDictionary<NSString*, id>* MWChargeLaunchDiagnostics(void);
@interface MWChargeWebView : UIView
@property(nonatomic, copy, nullable) void (^eventHandler)(NSString* message);
- (void)loadPage:(NSString*)page;
- (void)stop;
@end
NS_ASSUME_NONNULL_END
