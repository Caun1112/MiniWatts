#!/usr/bin/env python3
"""Exercise the actual daemon HTTP health probe against a local fixture server.

Only the target port and initial socket-availability check are substituted. The
Foundation request, identity validation and timeout implementation run unchanged.
"""
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
import json
from pathlib import Path
import subprocess
import tempfile
import threading
import time
import unittest

ROOT = Path(__file__).resolve().parents[1]
VALID_REPLY = {'status': 0, 'data': {'backend': 'MiniWatts.ChargeLimiter', 'protocol': 1}}


class FixtureHandler(BaseHTTPRequestHandler):
    def log_message(self, *_):
        pass

    def do_POST(self):
        body = self.rfile.read(int(self.headers.get('Content-Length', 0)))
        self.server.requests.append((self.path, json.loads(body), self.headers.get('Content-Type')))
        status, response, behavior = self.server.reply
        if behavior == 'abort':
            self.close_connection = True
            return
        if behavior == 'stall':
            self.server.release_response.wait(8)
        data = response if isinstance(response, bytes) else json.dumps(response).encode()
        try:
            self.send_response(status)
            self.send_header('Content-Type', 'application/json')
            self.send_header('Content-Length', str(len(data)))
            self.end_headers()
            self.wfile.write(data)
        except (BrokenPipeError, ConnectionResetError):
            pass # Expected when a timed-out probe cancels its request.


class ChargeHealth(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.server = ThreadingHTTPServer(('127.0.0.1', 0), FixtureHandler)
        cls.server.daemon_threads = True
        cls.server.requests = []
        cls.server.release_response = threading.Event()
        cls.server.reply = (200, VALID_REPLY, '')
        cls.worker = threading.Thread(target=cls.server.serve_forever, daemon=True)
        cls.worker.start()
        cls.fixture = tempfile.TemporaryDirectory(prefix='miniwatts-health-test-')
        path = Path(cls.fixture.name)
        daemon = (ROOT / 'Vendor/ChargeLimiter/daemon.mm').read_text()
        probe = daemon[daemon.index('static BOOL chargeServiceHealthy()'):daemon.index('\nstatic int ensureRootlessChargeService()')]
        probe = probe.replace('http://127.0.0.1:1231/', 'http://127.0.0.1:' + str(cls.server.server_port) + '/')
        source = r'''
#import <Foundation/Foundation.h>
#include <string.h>
#define GSERV_PORT 1231
static BOOL MWFixturePortOpen;
static BOOL localPortOpen(int port) { return MWFixturePortOpen; }
''' + probe + r'''
int main(int argc, char** argv) { @autoreleasepool {
    NSCAssert(argc == 3, @"Expected health and socket availability arguments");
    MWFixturePortOpen = strcmp(argv[2], "open") == 0;
    BOOL expected = strcmp(argv[1], "healthy") == 0;
    BOOL actual = chargeServiceHealthy();
    NSCAssert(actual == expected, @"Incorrect health result: expected %d got %d", expected, actual);
    printf("healthy=%d\n", actual);
} return 0; }
'''
        (path / 'test.m').write_text(source)
        cls.executable = path / 'test'
        subprocess.run(['xcrun', 'clang', '-fobjc-arc', '-framework', 'Foundation',
                        str(path / 'test.m'), '-o', str(cls.executable)], check=True)

    @classmethod
    def tearDownClass(cls):
        cls.server.release_response.set()
        cls.server.shutdown()
        cls.server.server_close()
        cls.worker.join(timeout=3)
        cls.fixture.cleanup()

    def setUp(self):
        self.server.requests.clear()
        self.server.release_response.clear()
        self.server.reply = (200, VALID_REPLY, '')

    def probe(self, expected=False, port_open=True):
        result = subprocess.run([str(self.executable), 'healthy' if expected else 'unhealthy',
                                 'open' if port_open else 'closed'], text=True,
                                capture_output=True, timeout=8)
        self.assertEqual(result.returncode, 0, result.stdout + result.stderr)

    def test_expected_backend_and_protocol_is_healthy(self):
        self.probe(expected=True)
        self.assertEqual(self.server.requests, [('/', {'api': 'get_conf'}, 'application/json')])

    def test_wrong_backend_is_not_mistaken_for_the_charge_daemon(self):
        self.server.reply = (200, {'status': 0, 'data': {'backend': 'another.service', 'protocol': 1}}, '')
        self.probe()

    def test_wrong_or_missing_protocol_is_unhealthy(self):
        for protocol in [None, 2, '1']:
            with self.subTest(protocol=protocol):
                self.server.reply = (200, {'status': 0, 'data': {'backend': 'MiniWatts.ChargeLimiter', 'protocol': protocol}}, '')
                self.probe()

    def test_http_failure_is_unhealthy_even_with_a_valid_identity(self):
        self.server.reply = (503, VALID_REPLY, '')
        self.probe()

    def test_invalid_json_reply_shape_or_backend_status_is_unhealthy(self):
        for reply in [b'{broken json', [], {'status': 0, 'data': []},
                      {'status': 1, 'data': VALID_REPLY['data']}, {'data': VALID_REPLY['data']}]:
            with self.subTest(reply=reply):
                self.server.reply = (200, reply, '')
                self.probe()

    def test_closed_port_returns_without_making_an_http_request(self):
        self.probe(port_open=False)
        self.assertEqual(self.server.requests, [])

    def test_aborted_response_is_unhealthy(self):
        self.server.reply = (200, VALID_REPLY, 'abort')
        self.probe()

    def test_stalled_response_has_a_bounded_timeout(self):
        self.server.reply = (200, VALID_REPLY, 'stall')
        started = time.monotonic()
        try:
            self.probe()
            self.assertLess(time.monotonic() - started, 6)
            self.assertTrue(self.server.requests)
        finally:
            self.server.release_response.set()


if __name__ == '__main__':
    unittest.main()
