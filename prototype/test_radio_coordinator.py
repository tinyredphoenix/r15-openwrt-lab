"""Reproduce R15 radio failure sequences with fake adapters; no networking."""
import os
from pathlib import Path
import subprocess
import tempfile
import unittest

ROOT = Path(__file__).parent
COORD = ROOT / 'runtime/r15-radio-coordinator'
WORKER = ROOT / 'runtime/r15-radio-worker'
ADAPTERS = r'''
management_up() { [ "$MGMT" = 1 ]; }
read_station() { STATE=$TSTATE; SFREQ=$TFREQ; SBSSID=$TBSSID; CARRIER=$TCARRIER; }
read_ap() { APSTATE=$TAPSTATE; AFREQ=$TAFREQ; }
scan_frequency() { SCANFREQ=$TSCANFREQ; [ "$SCAN_OK" = 1 ]; }
handle_link() {
 case "$1:$ATTACHED" in
  connected:0) echo ATTACH >> "$CALLS"; ATTACHED=1 ;;
  disconnected:1) echo DETACH >> "$CALLS"; ATTACHED=0 ;;
 esac
}
align_ap() { echo "ALIGN $1" >> "$CALLS"; [ "$ALIGN_OK" = 1 ]; }
rejoin_station() { echo REJOIN >> "$CALLS"; [ "$REJOIN_OK" = 1 ]; }
request_scan() { echo SCAN >> "$CALLS"; }
lease_up() { [ "$LEASE" = 1 ]; }
lease_network_safe() { [ "$SUBNET_OK" = 1 ]; }
probe_uplink() { echo PROBE >> "$CALLS"; [ "$PROBE_OK" = 1 ]; }
rlog() { echo "LOG $1" >> "$CALLS"; }
'''

class CoordinatorTests(unittest.TestCase):
    def scenario(self, action, setup='', adapters=ADAPTERS):
        with tempfile.TemporaryDirectory() as tmp:
            calls=Path(tmp)/'calls';calls.write_text('')
            env=dict(os.environ,R15_SOURCE_ONLY='1',R15_WORKER_LIBRARY=str(WORKER),COORD=str(COORD),CALLS=str(calls))
            script='''. "$COORD"
AP=wlan1; STA=wlan1-vxd; BSSID=02:11:22:33:44:55
ROLE=sta; READY=0; ATTACHED=0; FAILURES=0; NEED_REJOIN=0
REJOIN_WAIT=0; ALIGN_WAIT=0; PENDING_FREQ=
MGMT=1; TSTATE=COMPLETED; TFREQ=2412; TBSSID=$BSSID; TCARRIER=1
TAPSTATE=ENABLED; TAFREQ=2412; TSCANFREQ=2412; SCAN_OK=1
ALIGN_OK=1; REJOIN_OK=1; LEASE=1; PROBE_OK=1; SUBNET_OK=1
'''+adapters+'\n'+setup+'\n'+action
            r=subprocess.run(['/bin/sh','-c',script],env=env,capture_output=True,text=True)
            self.assertEqual(r.returncode,0,r.stderr)
            return calls.read_text().splitlines(),r.stdout.splitlines()

    def test_initial_scan_config_disables_association_without_changing_source(self):
        calls,out=self.scenario('''CONFIGDIR=${CALLS%/*}; SCANCONF=$CONFIGDIR/start.conf
printf 'ctrl_interface=/var/run/r15-wpa\\nnetwork={\\nssid=74657374\\n}\\n' > "$CONFIGDIR/wpa_supplicant.conf"
prepare_scan_config || exit 1
grep '^disabled=' "$CONFIGDIR/wpa_supplicant.conf" && exit 1
sed -n '/disabled=/p' "$SCANCONF"''',adapters='')
        self.assertEqual(out,['\tdisabled=1'])

    def test_initial_pair_enables_association_only_after_scan_and_aligned_ap(self):
        adapters=ADAPTERS+'''
prepare_scan_config() { echo DISABLED_CONFIG >> "$CALLS"; }
wpa_supplicant() { :; }
kill() { return 0; }
select_scan_frequency() { echo FRESH_SCAN >> "$CALLS"; SCANFREQ=5200; }
align_ap() { echo "ALIGN $1" >> "$CALLS"; TEST_AP_FREQ=$1; }
start_ap() { echo START_AP >> "$CALLS"; APCHILD=123; }
read_ap() { AFREQ=${TEST_AP_FREQ:-5180}; echo "AP_ENABLED $AFREQ" >> "$CALLS"; APSTATE=ENABLED; }
wcli() { echo "WCLI $*" >> "$CALLS"; echo OK; }
'''
        calls,out=self.scenario('start_aligned_pair',adapters=adapters)
        self.assertEqual(calls,['DISABLED_CONFIG','START_AP','SCAN','FRESH_SCAN','AP_ENABLED 5180','ALIGN 5200','AP_ENABLED 5200','WCLI enable_network 0'])

    def test_ap_channel_failure_requires_rejoin_and_carrier_before_ready(self):
        calls,out=self.scenario('''ATTACHED=1; TAFREQ=2452; coordinate_tick; echo "$READY"
TAFREQ=2412; TCARRIER=0; coordinate_tick; echo "$READY"
TCARRIER=1; coordinate_tick; echo "$READY"''')
        self.assertEqual(calls,['DETACH','ALIGN 2412','REJOIN','ATTACH','PROBE'])
        self.assertEqual(out,['0','0','1'])

    def test_completed_without_carrier_cannot_attach_dhcp(self):
        calls,out=self.scenario('coordinate_tick; echo "$READY:$ATTACHED"',setup='TCARRIER=0')
        self.assertEqual(calls,['REJOIN']);self.assertEqual(out,['0:0'])

    def test_missing_fresh_scan_holds_uplink_without_touching_ap(self):
        calls,out=self.scenario('coordinate_tick; echo "$READY:$ATTACHED"',setup='TSTATE=DISCONNECTED; SCAN_OK=0; ATTACHED=1')
        self.assertEqual(calls,['DETACH','SCAN']);self.assertEqual(out,['0:0'])

    def test_dhcp_pending_does_not_mark_ready_or_restart_repeatedly(self):
        calls,out=self.scenario('coordinate_tick; coordinate_tick; echo "$READY:$ATTACHED"',setup='LEASE=0')
        self.assertEqual(calls,['ATTACH']);self.assertEqual(out,['0:1'])

    def test_repeated_probe_failure_detaches_only_uplink(self):
        calls,out=self.scenario('''coordinate_tick; PROBE_OK=0
coordinate_tick; coordinate_tick; echo "$ATTACHED:$READY"
coordinate_tick; echo "$ATTACHED:$READY"''')
        self.assertEqual(out,['1:0','0:0'])
        self.assertEqual(calls,['ATTACH','PROBE','PROBE','PROBE','PROBE','DETACH','SCAN'])

    def test_failed_data_path_forces_reassociation_even_if_driver_reports_connected(self):
        calls, out = self.scenario('PROBE_OK=0\ncoordinate_tick; coordinate_tick; coordinate_tick\necho "$NEED_REJOIN:$ATTACHED"\ncoordinate_tick; echo "$NEED_REJOIN:$READY"')
        self.assertEqual(out, ['1:0', '0:0'])
        self.assertEqual(calls[-3:], ['DETACH', 'SCAN', 'REJOIN'])

    def test_management_loss_does_not_restart_ap_or_management(self):
        calls,out=self.scenario('coordinate_tick; echo "$READY:$ATTACHED"',setup='MGMT=0; ATTACHED=1; READY=1')
        self.assertEqual(calls,['DETACH']);self.assertEqual(out,['0:0'])

    def test_alignment_waits_once_and_fails_if_ap_never_follows_channel(self):
        calls,out=self.scenario('''coordinate_tick
n=0; while [ "$n" -lt 13 ]; do coordinate_tick; rc=$?; n=$((n+1)); done
echo "$rc:$READY"''',setup='TAFREQ=2452')
        self.assertEqual(calls,['ALIGN 2412']);self.assertEqual(out,['1:0'])

    def test_unreviewed_five_ghz_frequency_is_not_applied(self):
        calls,out=self.scenario('coordinate_tick; echo "$READY:$ATTACHED"',setup='AP=wlan0; STA=wlan0-vxd; TFREQ=5500; ATTACHED=1')
        self.assertEqual(calls[0],'DETACH');self.assertEqual(out,['0:0'])
        self.assertFalse(any(x.startswith(('ALIGN','ATTACH','PROBE')) for x in calls))

    def test_ap_that_never_finishes_starting_cannot_attach_dhcp(self):
        calls, out = self.scenario('''n=0
while [ "$n" -lt 13 ]; do coordinate_tick; rc=$?; n=$((n+1)); done
echo "$rc:$READY:$ATTACHED"''', setup='TAPSTATE=ACS')
        self.assertEqual(calls, [])
        self.assertEqual(out, ['1:0:0'])

    def test_clean_shutdown_invalidates_informational_ready_file(self):
        calls, out = self.scenario('''APCONF="${CALLS%/*}/hostapd.conf"
STACHILD=; APCHILD=; READY=1; ATTACHED=1
publish_state; coordinator_cleanup
grep '^ready=' "${CALLS%/*}/link-state"''')
        self.assertEqual(calls, ['DETACH'])
        self.assertEqual(out, ['ready=0'])

    def test_wrong_upstream_bssid_is_not_accepted_as_ready(self):
        calls,out=self.scenario('coordinate_tick; echo "$READY:$ATTACHED"',setup='TBSSID=02:aa:bb:cc:dd:ee')
        self.assertEqual(calls,['SCAN']);self.assertEqual(out,['0:0'])

    def test_actual_scan_parser_rejects_stale_wrong_or_invalid_entries(self):
        _,out=self.scenario('''wcli() { printf 'bssid=%s\\nfreq=%s\\nage=%s\\n' "$ENTRY" "$FREQ" "$AGE_INPUT"; }
ENTRY=$BSSID; FREQ=2412; AGE_INPUT=2; scan_frequency; echo $?
AGE_INPUT=31; scan_frequency; echo $?
AGE_INPUT=2; ENTRY=02:aa:bb:cc:dd:ee; scan_frequency; echo $?
ENTRY=$BSSID; FREQ='2412;reboot'; scan_frequency; echo $?''',adapters='')
        self.assertEqual(out,['0','1','1','1'])

    def test_interface_and_bssid_validation(self):
        _,out=self.scenario('''valid_same_pair; echo $?
STA=wlan0-vxd; valid_same_pair; echo $?
STA=wlan1-vxd; BSSID=03:11:22:33:44:55; valid_same_pair; echo $?
BSSID='02:11:22:33:44:55;reboot'; valid_same_pair; echo $?''')
        self.assertEqual(out,['0','1','1','1'])

    def test_ipv4_data_is_validated_without_execution(self):
        _, out = self.scenario("""valid_ipv4 192.0.2.10; echo $?
valid_ipv4 999.0.2.10; echo $?
valid_ipv4 '192.0.2.10;reboot'; echo $?
valid_ipv4 0.0.0.0; echo $?
valid_ipv4 ''; echo $?""", adapters='')
        self.assertEqual(out, ['0', '1', '1', '1', '1'])

    def test_upstream_reboot_scan_can_move_ap_to_new_channel(self):
        for ap, sta, old, new in [('wlan1', 'wlan1-vxd', 2412, 2462),
                                  ('wlan0', 'wlan0-vxd', 5200, 5240)]:
            with self.subTest(ap=ap):
                calls, out = self.scenario('coordinate_tick; echo "$READY:$ATTACHED"',
                    setup=f'AP={ap}; STA={sta}; TSTATE=DISCONNECTED; TAFREQ={old}; TSCANFREQ={new}; ATTACHED=1')
                self.assertEqual(calls, ['DETACH', f'ALIGN {new}'])
                self.assertEqual(out, ['0:0'])

    def test_negotiated_channel_change_overrides_old_scan_channel(self):
        calls, out = self.scenario('coordinate_tick; echo "$READY:$ATTACHED"',
            setup='TFREQ=2462; TAFREQ=2412; TSCANFREQ=2412; ATTACHED=1')
        self.assertEqual(calls, ['DETACH', 'ALIGN 2462'])
        self.assertEqual(out, ['0:0'])

    def test_conflicting_or_invalid_lease_detaches_without_probe(self):
        calls, out = self.scenario('coordinate_tick; rc=$?; echo "$rc:$READY:$ATTACHED"',
                                   setup='SUBNET_OK=0')
        self.assertEqual(out, ['1:0:0'])
        self.assertEqual(calls[:2], ['ATTACH', 'DETACH'])
        self.assertFalse(any(x.startswith(('PROBE', 'ALIGN', 'REJOIN')) for x in calls))

    def test_shell_syntax(self):
        self.assertEqual(subprocess.run(['/bin/sh','-n',str(COORD)],capture_output=True).returncode,0)

if __name__=='__main__':unittest.main()
