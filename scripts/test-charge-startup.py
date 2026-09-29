#!/usr/bin/env python3
"""Exercise the actual memory-limit parser and singleton lock under ASan."""
import pathlib
import subprocess
import tempfile

utils = pathlib.Path('Vendor/ChargeLimiter/utils.mm').read_text()
body = utils[utils.index('int32_t get_mem_limit('):utils.index('\nint set_mem_limit(')]
root = pathlib.Path.cwd()
source = r'''
#include <cassert>
#include <cstdlib>
#include <cstdint>
#include <cstring>
#include <cstdio>
#include <sys/wait.h>
#include "ServiceLock.h"
#define MEMORYSTATUS_CMD_GET_PRIORITY_LIST 1
struct memorystatus_priority_entry_t { int pid, priority; uint64_t user_data; int limit, state; };
static int scenario;
int memorystatus_control(unsigned, int, unsigned, void* buffer, size_t size) {
    if (!buffer) return scenario == 2 ? -1 : sizeof(memorystatus_priority_entry_t);
    if (scenario == 3) return -1;
    if (scenario == 4) return (int)size+100;
    memorystatus_priority_entry_t entry = {42, 0, 0, 80, 0};
    memcpy(buffer, &entry, sizeof(entry));
    return sizeof(entry);
}
''' + body + r'''
int main(int argc, char** argv) {
    scenario=0; assert(get_mem_limit(42)==80);
    // This used to walk sizeof(entry) records despite only allocating one.
    assert(get_mem_limit(99)==-1);
    scenario=2; assert(get_mem_limit(42)==-1);
    scenario=3; assert(get_mem_limit(42)==-1);
    scenario=4; assert(get_mem_limit(42)==-1);
    int lock=acquireServiceLock(argv[1]); assert(lock>=0);
    assert(acquireServiceLock(argv[1])<0);
    pid_t child=fork(); assert(child>=0);
    if (!child) { close(lock); _exit(acquireServiceLock(argv[1])<0 ? 0 : 1); }
    int status; assert(waitpid(child,&status,0)==child && WIFEXITED(status) && WEXITSTATUS(status)==0);
    close(lock);
    lock=acquireServiceLock(argv[1]); assert(lock>=0); close(lock);
    assert(acquireServiceLock("/nonexistent/miniwatts/lock")<0);
    puts("Memory bounds and cross-process single-instance recovery checks passed (ASan)");
}
'''
with tempfile.TemporaryDirectory(prefix='miniwatts-startup-') as folder:
    folder = pathlib.Path(folder)
    (folder/'test.cpp').write_text(source)
    subprocess.run(['xcrun','clang++','-std=c++17','-fsanitize=address','-g','-I'+str(root/'Vendor/ChargeLimiter'),str(folder/'test.cpp'),'-o',str(folder/'test')],check=True)
    subprocess.run([str(folder/'test'),str(folder/'daemon.lock')],check=True)
