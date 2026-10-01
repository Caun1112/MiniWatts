#!/usr/bin/env python3
"""Run the real rootless recovery and maintainer scripts with isolated commands.

Only absolute installation paths are redirected into a temporary fixture. No
real launchd jobs, charging state, installed applications or package are touched.
"""
import json
import os
from pathlib import Path
import subprocess
import sys
import tempfile
import unittest

ROOT = Path(__file__).resolve().parents[1]
PACKAGE = ROOT / 'packaging/rootless'
LABEL = 'system/org.zhaohe.MiniWatts.charge'

MOCK = r'''
import json, os, subprocess, sys
from pathlib import Path
command = Path(sys.argv[0]).name
args = sys.argv[1:]
with open(os.environ['MW_TEST_EVENTS'], 'a') as log:
    log.write(json.dumps([command, *args]) + '\n')
path = Path(os.environ['MW_TEST_STATE'])
state = json.loads(path.read_text())
def finish(code=0):
    path.write_text(json.dumps(state))
    sys.exit(code)
if command == 'launchctl':
    action = args[0]
    watchdog = '.watchdog' in args[-1]
    job = state['watchdog'] if watchdog else state
    if action == 'enable':
        job['enabled'] = True
    elif action == 'bootout':
        job['registered'] = False
        if not watchdog:
            state['listening'] = False
    elif action == 'bootstrap':
        job['registered'] = True
        if not watchdog and state.get('bootstrap_race'):
            print('another caller already registered the job', file=sys.stderr)
            finish(5)
    elif action == 'kickstart':
        if not job['registered'] or not job['enabled']:
            finish(3)
        if not watchdog:
            if '-k' in args:
                state['stuck_process'] = False
            state['listening'] = not state.get('health_failure') and not state.get('stuck_process')
    elif action == 'print':
        print('job registered=' + str(job['registered']))
        finish(0 if job['registered'] else 3)
    else:
        finish(64)
    finish()
if command == 'MiniWattsChargeDaemon':
    if args == ['ensure-launchd']:
        os.execv('/bin/sh', ['/bin/sh', os.environ['MW_TEST_MANAGER']])
    if args == ['health']:
        finish(0 if state['listening'] else 1)
    if args == ['stop']:
        state['listening'] = False
        finish()
    if args == ['reset']:
        state['hardware_restored'] = True
        finish()
    # A direct daemon launch would lose launchd supervision.
    finish(77)
finish()
'''


class RootlessLifecycle(unittest.TestCase):
    def setUp(self):
        self.temporary = tempfile.TemporaryDirectory(prefix='miniwatts-maintainer-test-')
        self.addCleanup(self.temporary.cleanup)
        self.path = Path(self.temporary.name)
        self.rootless = self.path / 'rootless'
        self.app = self.rootless / 'Applications/MiniWatts.app'
        self.app.mkdir(parents=True)
        self.events_path = self.path / 'events.jsonl'
        self.events_path.touch()
        self.state_path = self.path / 'state.json'
        self.state_path.write_text(json.dumps({
            'registered': False, 'enabled': False, 'listening': False,
            'watchdog': {'registered': False, 'enabled': False},
        }))
        self.mockbin = self.path / 'bin'
        self.mockbin.mkdir()
        for executable in [self.rootless / 'bin/launchctl', self.rootless / 'usr/bin/uicache',
                           self.app / 'MiniWattsChargeDaemon', self.mockbin / 'sleep',
                           self.rootless / 'usr/bin/sleep']:
            executable.parent.mkdir(parents=True, exist_ok=True)
            executable.write_text('#!' + sys.executable + '\n' + MOCK)
            executable.chmod(0o755)
        self.manager = self.app / 'MiniWattsChargeLaunch'
        self.scripts = {}
        for name in ['MiniWattsChargeLaunch', 'postinst', 'prerm']:
            destination = self.manager if name == 'MiniWattsChargeLaunch' else self.path / name
            source = (PACKAGE / name).read_text()
            # Never allow the fallback to address the host's real launchctl.
            source = source.replace('/var/jb', str(self.rootless))
            source = source.replace('ctl=/bin/launchctl', 'ctl=' + str(self.rootless / 'bin/launchctl'))
            destination.write_text(source)
            destination.chmod(0o755)
            self.scripts[name] = destination
        self.environment = dict(os.environ,
            MW_TEST_EVENTS=str(self.events_path), MW_TEST_STATE=str(self.state_path),
            MW_TEST_MANAGER=str(self.manager), PATH=str(self.mockbin) + ':/usr/bin:/bin')

    def invoke(self, name, *arguments):
        return subprocess.run(['/bin/sh', str(self.scripts[name]), *arguments],
            env=self.environment, text=True, capture_output=True, timeout=15)

    def state(self):
        return json.loads(self.state_path.read_text())

    def alter_state(self, **changes):
        state = self.state()
        state.update(changes)
        self.state_path.write_text(json.dumps(state))

    def events(self):
        return [json.loads(line) for line in self.events_path.read_text().splitlines()]

    def assert_supervised(self):
        state = self.state()
        self.assertTrue(state['enabled'] and state['registered'] and state['listening'], state)
        calls = self.events()
        self.assertIn(['launchctl', 'enable', LABEL], calls)
        self.assertTrue(any(call[:2] == ['launchctl', 'kickstart'] for call in calls), calls)
        self.assertNotIn(['MiniWattsChargeDaemon'], calls)
        self.assertFalse(any(call[0] == 'MiniWatts' for call in calls))

    def test_configure_starts_supervised_service_without_opening_app(self):
        result = self.invoke('postinst', 'configure')
        self.assertEqual(result.returncode, 0, result.stdout + result.stderr)
        self.assert_supervised()
        self.assertIn(['uicache', '-p', str(self.app)], self.events())
        self.assertTrue(self.state()['watchdog']['registered'])

    def test_recovery_preserves_a_running_service(self):
        self.alter_state(registered=True, enabled=True, listening=True)
        result = self.invoke('MiniWattsChargeLaunch')
        self.assertEqual(result.returncode, 0, result.stdout + result.stderr)
        self.assertTrue(self.state()['listening'])
        calls = self.events()
        self.assertFalse(any(call[:2] == ['launchctl', 'bootout'] for call in calls), calls)
        self.assertFalse(any(call[0] == 'launchctl' and '-k' in call for call in calls), calls)

    def test_recovery_restarts_crashed_registered_service(self):
        self.alter_state(registered=True, enabled=True, listening=False)
        result = self.invoke('MiniWattsChargeLaunch')
        self.assertEqual(result.returncode, 0, result.stdout + result.stderr)
        self.assert_supervised()

    def test_registration_race_still_checks_actual_service_health(self):
        self.alter_state(bootstrap_race=True)
        result = self.invoke('MiniWattsChargeLaunch')
        self.assertEqual(result.returncode, 0, result.stdout + result.stderr)
        self.assert_supervised()
        self.assertTrue(any(call[:2] == ['launchctl', 'bootstrap'] for call in self.events()))

    def test_successful_launchctl_with_no_listener_reports_failure(self):
        self.alter_state(health_failure=True)
        result = self.invoke('MiniWattsChargeLaunch')
        self.assertNotEqual(result.returncode, 0, result.stdout + result.stderr)
        self.assertFalse(self.state()['listening'])
        self.assertTrue(any(call == ['MiniWattsChargeDaemon', 'health'] for call in self.events()))
        self.assertIn('listener_ready=0', result.stdout + result.stderr)

    def test_unresponsive_registered_process_is_restarted_after_health_failures(self):
        self.alter_state(registered=True, enabled=True, listening=False, stuck_process=True)
        result = self.invoke('MiniWattsChargeLaunch')
        self.assertEqual(result.returncode, 0, result.stdout + result.stderr)
        self.assert_supervised()
        calls = self.events()
        force_restart = calls.index(['launchctl', 'kickstart', '-k', LABEL])
        health_failures = [call for call in calls[:force_restart] if call == ['MiniWattsChargeDaemon', 'health']]
        self.assertGreaterEqual(len(health_failures), 2)

    def test_install_keeps_truthful_failure_log_and_registers_future_recovery(self):
        self.alter_state(health_failure=True)
        result = self.invoke('postinst', 'configure')
        self.assertEqual(result.returncode, 0, result.stdout + result.stderr)
        self.assertFalse(self.state()['listening'])
        self.assertTrue(self.state()['watchdog']['registered'])
        self.assertIn('listener_ready=0', result.stdout + result.stderr)

    def test_upgrade_restores_hardware_then_resumes_supervision(self):
        self.alter_state(registered=True, enabled=True, listening=True)
        result = self.invoke('prerm', 'upgrade')
        self.assertEqual(result.returncode, 0, result.stdout + result.stderr)
        calls = self.events()
        stop = calls.index(['MiniWattsChargeDaemon', 'stop'])
        reset = calls.index(['MiniWattsChargeDaemon', 'reset'])
        bootout = next(i for i, call in enumerate(calls) if call[:2] == ['launchctl', 'bootout'])
        self.assertLess(bootout, stop)
        self.assertLess(stop, reset)
        self.assertFalse(self.state()['listening'])
        self.assertTrue(self.state()['hardware_restored'])
        self.assertNotIn(['uicache', '-u', str(self.app)], calls)
        result = self.invoke('postinst', 'configure')
        self.assertEqual(result.returncode, 0, result.stdout + result.stderr)
        self.assert_supervised()

    def test_remove_stops_service_restores_hardware_and_unregisters_icon(self):
        self.alter_state(registered=True, enabled=True, listening=True)
        result = self.invoke('prerm', 'remove')
        self.assertEqual(result.returncode, 0, result.stdout + result.stderr)
        self.assertFalse(self.state()['registered'] or self.state()['listening'])
        self.assertFalse(self.state()['watchdog']['registered'])
        self.assertTrue(self.state()['hardware_restored'])
        self.assertIn(['uicache', '-u', str(self.app)], self.events())
        calls = self.events()
        watchdog_stop = next(i for i, call in enumerate(calls)
            if call[:2] == ['launchctl', 'bootout'] and '.watchdog.' in call[-1])
        service_stop = next(i for i, call in enumerate(calls)
            if call[:2] == ['launchctl', 'bootout'] and call[-1].endswith('.charge.plist'))
        self.assertLess(watchdog_stop, service_stop)

    def test_irrelevant_maintainer_operations_do_nothing(self):
        for name, operation in [('postinst', 'triggered'), ('prerm', 'failed-upgrade')]:
            result = self.invoke(name, operation)
            self.assertEqual(result.returncode, 0, result.stdout + result.stderr)
        self.assertEqual(self.events(), [])


if __name__ == '__main__':
    unittest.main()
