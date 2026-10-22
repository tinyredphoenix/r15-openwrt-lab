"""Exercise uplink failure/reconnect behavior with fake commands, never networking."""
import json
import os
from pathlib import Path
import subprocess
import tempfile
import unittest

WORKER = Path(__file__).parent / 'runtime/r15-radio-worker'

class RadioWorkerTests(unittest.TestCase):
    def run_scenario(self, actions, *, management=True, attach_ok=True, dhcp_ok=True):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            calls = root / 'calls'
            calls.write_text('')
            commands = {
                'ubus': '''#!/bin/sh
printf '%s\\n' "ubus $*" >> "$CALLS"
case "$*" in
 *network.interface.mgmt*) printf '%s\\n' "$MGMT" ;;
 *add_device*) [ "$ATTACH_OK" = 1 ] ;;
esac
''',
                'jsonfilter': '#!/bin/sh\ncat\n',
                'logger': '#!/bin/sh\nexit 0\n',
                'ifup': '#!/bin/sh\nprintf "ifup %s\\n" "$*" >> "$CALLS"\n[ "$DHCP_OK" = 1 ]\n',
                'ifdown': '#!/bin/sh\nprintf "ifdown %s\\n" "$*" >> "$CALLS"\n',
            }
            for name, source in commands.items():
                p = root / name
                p.write_text(source)
                p.chmod(0o700)
            env = dict(os.environ, PATH=str(root) + ':' + os.environ['PATH'],
                       CALLS=str(calls), MGMT='true' if management else 'false',
                       ATTACH_OK=str(int(attach_ok)), DHCP_OK=str(int(dhcp_ok)),
                       R15_SOURCE_ONLY='1', WORKER=str(WORKER))
            result = subprocess.run(['/bin/sh', '-c',
                '. "$WORKER"; ROLE=sta; AP=wlan1; STA=wlan0-vxd; ATTACHED=0; ' + actions],
                env=env, capture_output=True, text=True)
            self.assertEqual(result.returncode, 0, result.stderr)
            return calls.read_text().splitlines(), result.stdout

    def test_reconnect_attaches_again_without_touching_management_or_ap(self):
        calls, _ = self.run_scenario('handle_link connected; handle_link disconnected; handle_link connected')
        self.assertEqual(sum('add_device' in x for x in calls), 2)
        self.assertEqual(sum('remove_device' in x for x in calls), 1)
        self.assertEqual(calls.count('ifup wwan'), 2)
        self.assertEqual(calls.count('ifdown wwan'), 1)
        self.assertTrue(all('mgmt status' in x or 'wwan' in x for x in calls))

    def test_repeated_association_does_not_restart_dhcp(self):
        calls, _ = self.run_scenario('handle_link connected; handle_link connected')
        self.assertEqual(calls.count('ifup wwan'), 1)

    def test_missing_upstream_does_not_start_dhcp_or_change_networks(self):
        calls, _ = self.run_scenario('handle_link disconnected')
        self.assertEqual(calls, [])

    def test_failed_attachment_never_starts_dhcp_and_is_retryable(self):
        calls, _ = self.run_scenario('handle_link connected || :; handle_link connected || :', attach_ok=False)
        self.assertEqual(sum('add_device' in x for x in calls), 2)
        self.assertNotIn('ifup wwan', calls)

    def test_failed_dhcp_detaches_only_uplink(self):
        calls, _ = self.run_scenario('handle_link connected || :', dhcp_ok=False)
        self.assertIn('ifdown wwan', calls)
        self.assertTrue(any('remove_device' in x for x in calls))

    def test_management_failure_prevents_uplink_attachment(self):
        calls, _ = self.run_scenario('handle_link connected', management=False)
        self.assertFalse(any('add_device' in x for x in calls))

    def test_management_failure_after_attachment_detaches_only_uplink(self):
        calls, _ = self.run_scenario('handle_link connected; MGMT=false; handle_link connected')
        self.assertIn('ifdown wwan', calls)
        self.assertEqual(calls.count('ifup wwan'), 1)

    def test_only_observed_cross_radio_pairs_are_allowed(self):
        _, stdout = self.run_scenario('valid_pair; echo $?; AP=wlan0; valid_pair; echo $?')
        self.assertEqual(stdout.splitlines(), ['0', '1'])

if __name__ == '__main__':
    unittest.main()
