# ChargeLimiter integration

Vendored from https://github.com/lich4/ChargeLimiter at
27d42eb1789744eee8e68cf69a806d2465bd2cd4 (1.7), GPL-3.0.
GCDWebServer 3.5.4, commit 1c36bf07c848476111d523057a3a63b05328ce2a,
is vendored in ../GCDWebServer under its BSD license.

MiniWatts changes: port 1231; isolated miniwatts-charge settings/database/log;
native SwiftUI entry and diagnostics; themed complete upstream web UI;
separate daemon/HUD executables; stock SDK ABI declarations; validated/serialized
HTTP requests; bounded logs; hardware return logging; connectivity restoration;
nil sensor guards; current Xcode compilation and unsigned packaging.

All source is included. No prebuilt upstream binaries are redistributed.
The private APIs and HUD need device validation; a successful build does not prove
hardware compatibility. UIWebView is retained because upstream documents WKWebView
container incompatibility in privileged iOS installations.
