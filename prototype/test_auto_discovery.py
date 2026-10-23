"""Discovery uses exact control-interface SSID text, security and fresh BSS data."""
import shlex
import unittest
import test_radio_coordinator as policy_tests

class AutoDiscoveryTests(unittest.TestCase):
    scenario = policy_tests.CoordinatorTests.scenario
    # Reuse the bounded shell harness, not its inherited test methods.
    def run_auto(self, rows, bss, action='auto_scan_frequency; rc=$?; echo "$rc:$BSSID:$SCANFREQ"'):
        setup = 'AUTO_BSS=1; SSID_TEXT=' + shlex.quote(r'Test\nWiFi')
        setup += '\nROWS=' + shlex.quote(rows) + '\nENTRY=' + shlex.quote(bss)
        setup += '''
wcli() { case "$1" in scan_results) printf '%s\\n' "$ROWS" ;; bss) printf '%s\\n' "$ENTRY" ;; esac; }
'''
        return self.scenario(action, setup=setup, adapters='')[1]

    def test_discovery_filters_other_ssids_and_open_networks(self):
        rows = '\n'.join([
            '02:00:00:00:00:01\t2412\t-10\t[ESS]\tTest\\nWiFi',
            '02:00:00:00:00:02\t2412\t-20\t[WPA2-PSK-CCMP][ESS]\tOther',
            '02:00:00:00:00:03\t2462\t-40\t[WPA2-PSK-CCMP][ESS]\tTest\\nWiFi'])
        bss = 'bssid=02:00:00:00:00:03\nssid=Test\\nWiFi\nflags=[WPA2-PSK-CCMP][ESS]\nfreq=2462\nage=2'
        self.assertEqual(self.run_auto(rows,bss), ['0:02:00:00:00:00:03:2462'])

    def test_discovery_does_not_reuse_stale_scan(self):
        row='02:00:00:00:00:03\t2462\t-40\t[WPA2-PSK-CCMP][ESS]\tTest\\nWiFi'
        bss='bssid=02:00:00:00:00:03\nssid=Test\\nWiFi\nflags=[WPA2-PSK-CCMP][ESS]\nfreq=2462\nage=31'
        self.assertTrue(self.run_auto(row,bss)[0].startswith('1:'))

    def test_auto_association_accepts_new_bssid_only_with_exact_ssid_and_security(self):
        action='''STATION='ssid=Test\\nWiFi
id=0
key_mgmt=WPA2-PSK
pairwise_cipher=CCMP
group_cipher=CCMP'
SBSSID=02:aa:bb:cc:dd:ee
station_matches; echo "$?:$BSSID"
STATION='ssid=Other
id=0
key_mgmt=WPA2-PSK
pairwise_cipher=CCMP
group_cipher=CCMP'
station_matches; echo $?
STATION='ssid=Test\\nWiFi
id=0
key_mgmt=NONE
pairwise_cipher=NONE
group_cipher=NONE'
station_matches; echo $?'''
        self.assertEqual(self.run_auto('', '', action), ['0:02:aa:bb:cc:dd:ee','1','1'])

