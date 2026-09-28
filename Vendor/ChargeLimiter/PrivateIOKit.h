#pragma once
// Minimal ABI declarations for the private iOS IOKit symbols used by ChargeLimiter.
#include <CoreFoundation/CoreFoundation.h>
#include <mach/mach.h>
typedef mach_port_t io_object_t;
typedef io_object_t io_service_t;
typedef io_object_t io_iterator_t;
typedef kern_return_t IOReturn;
typedef struct IONotificationPort* IONotificationPortRef;
typedef struct __IOHIDEvent* IOHIDEventRef;
typedef struct __IOHIDService* IOHIDServiceRef;
typedef uint32_t IOHIDEventType;
#define IO_OBJECT_NULL MACH_PORT_NULL
#define kIOMasterPortDefault MACH_PORT_NULL
#define kIOReturnSuccess KERN_SUCCESS
#define kIOMatchedNotification "IOServiceMatched"
enum { kIOHIDEventTypeDigitizer = 11, kIOHIDEventFieldDigitizerX = 11 << 16,
       kIOHIDEventFieldDigitizerY = (11 << 16) + 1,
       kIOHIDEventFieldDigitizerEventMask = (11 << 16) + 7,
       kIOHIDDigitizerEventPosition = 4 };
extern "C" {
CFMutableDictionaryRef IOServiceMatching(const char* name);
io_service_t IOServiceGetMatchingService(mach_port_t port, CFDictionaryRef matching);
kern_return_t IORegistryEntryCreateCFProperties(io_object_t entry, CFMutableDictionaryRef* properties, CFAllocatorRef allocator, uint32_t options);
kern_return_t IORegistryEntrySetCFProperties(io_object_t entry, CFTypeRef properties);
kern_return_t IOObjectRelease(io_object_t object);
io_object_t IOIteratorNext(io_iterator_t iterator);
IONotificationPortRef IONotificationPortCreate(mach_port_t port);
void IONotificationPortDestroy(IONotificationPortRef port);
CFRunLoopSourceRef IONotificationPortGetRunLoopSource(IONotificationPortRef port);
kern_return_t IOServiceAddInterestNotification(IONotificationPortRef port, io_service_t service, const char* type, void (*callback)(void*, io_service_t, uint32_t, void*), void* refcon, io_object_t* notification);
kern_return_t IOServiceAddMatchingNotification(IONotificationPortRef port, const char* type, CFDictionaryRef matching, void (*callback)(void*, io_iterator_t), void* refcon, io_iterator_t* notification);
IOHIDEventType IOHIDEventGetType(IOHIDEventRef event);
CFArrayRef IOHIDEventGetChildren(IOHIDEventRef event);
CFIndex IOHIDEventGetIntegerValue(IOHIDEventRef event, uint32_t field);
}
