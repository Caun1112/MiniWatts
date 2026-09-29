#pragma once
#include <sys/file.h>
#include <fcntl.h>
#include <signal.h>
#include <errno.h>
#include <unistd.h>
#include <stdio.h>
#include <stdlib.h>
#include <string.h>

// Every launch path (launchd or foreground recovery) shares one root-owned lock.
// CLOEXEC prevents the HUD from inheriting it and pinning a dead daemon's lock.
static int acquireServiceLock(const char* path) {
    int fd = open(path, O_CREAT | O_RDWR | O_CLOEXEC | O_NOFOLLOW, 0600);
    if (fd < 0) return -1;
    if (flock(fd, LOCK_EX | LOCK_NB) != 0) { int e = errno; close(fd); errno = e; return -1; }
    char pid[32];
    int count = snprintf(pid, sizeof(pid), "%d\n", getpid());
    if (ftruncate(fd, 0) || write(fd, pid, count) != count) {
        int e = errno; close(fd); errno = e ? e : EIO; return -1;
    }
    return fd;
}
