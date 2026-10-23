"""Offline tests of isolation, configuration encoding and unsafe-profile rejection."""
import base64
import copy
import hashlib
import json
from pathlib import Path
import subprocess
import sys
import tempfile
import unittest

from r15_repeater import psk, render


ROOT = Path(__file__).resolve().parent


class RepeaterTests(unittest.TestCase):
    def setUp(self):
        self.profile = json.loads((ROOT / "profile.example.json").read_text())

    def test_rendered_subnet_policy_uses_normalized_local_networks(self):
        files, _ = render(self.profile, "repeater")
        import ipaddress
        expected = [str(ipaddress.ip_interface(self.profile[x]["address"]).network)
                    for x in ("management", "downstream")]
        self.assertEqual(files["radio-config/protected-subnets"].splitlines(), expected)
        self.assertIn("runtime/r15-subnet-check", files)
        wired, _ = render(self.profile, "wired-first")
        self.assertNotIn("runtime/r15-subnet-check", wired)

    def test_web_and_rpc_config_are_management_scoped_with_no_radio_dependency(self):
        files, manifest = render(self.profile, "wired-first")
        http = files['openwrt-config/uhttpd']
        self.assertIn("list listen_http '192.168.77.1:80'", http)
        self.assertIn("list listen_https '192.168.77.1:443'", http)
        self.assertNotIn('0.0.0.0', http)
        self.assertIn("option redirect_https '1'", http)
        self.assertIn("option password '$p$root'", files['openwrt-config/rpcd'])
        self.assertTrue(any('LuCI root password' in x for x in manifest['blockers']))

    def test_management_survives_missing_or_broken_radio_configuration(self):
        wired, _ = render(self.profile, "wired-first")
        broken = copy.deepcopy(self.profile)
        del broken["upstream"]
        broken["downstream"] = {"invalid": "radio setup must not gate wired access"}
        other, _ = render(broken, "wired-first")
        self.assertEqual(wired, other)
        self.assertFalse(any(p.startswith("radio-config/") for p in wired))

    def test_repeater_changes_do_not_change_management_or_ssh(self):
        first, _ = render(self.profile, "repeater")
        self.profile["upstream"].update(ssid="Other Tenda", key="different-password")
        self.profile["downstream"].update(ssid="Other R15", channel=11)
        second, _ = render(self.profile, "repeater")
        for name in ("network", "firewall", "dhcp", "dropbear", "wireless"):
            self.assertEqual(first["openwrt-config/" + name], second["openwrt-config/" + name])
        self.assertIn("option Interface 'mgmt'", first["openwrt-config/dropbear"])
        firewall = first["openwrt-config/firewall"]
        self.assertIn("option src 'lan'\n\toption dest 'wwan'", firewall)
        self.assertNotIn("option dest 'mgmt'", firewall)

    def test_management_port_cannot_be_reused_for_wifi(self):
        self.profile["upstream"]["interface"] = "unverified0"
        with self.assertRaisesRegex(ValueError, "management"):
            render(self.profile, "repeater")

    def test_wired_dhcp_instance_has_no_radio_network_dependency(self):
        wired, _ = render(self.profile, "wired-first")
        radio, _ = render(self.profile, "repeater")
        dhcp = wired["openwrt-config/dhcp"]
        self.assertIn("option instance 'mgmt_dns'", dhcp)
        self.assertNotIn("'lan'", dhcp)
        self.assertNotIn("'wwan'", dhcp)
        self.assertTrue(radio["openwrt-config/dhcp"].startswith(dhcp))
        self.assertIn("option instance 'lan_dns'", radio["openwrt-config/dhcp"])

    def test_reject_subnet_conflicts_and_dhcp_router_collision(self):
        for change in ("downstream", "upstream", "dhcp"):
            with self.subTest(change=change):
                profile = copy.deepcopy(self.profile)
                if change == "downstream":
                    profile["downstream"]["address"] = "192.168.77.2/24"
                elif change == "upstream":
                    profile["known_upstream_subnets"] = ["192.168.77.0/24"]
                else:
                    profile["management"]["address"] = "192.168.77.100/24"
                with self.assertRaises(ValueError):
                    render(profile, "repeater")

    def test_reject_same_radio_and_command_injection(self):
        for change in ("same-radio", "ifname", "password-newline", "ap-channel"):
            with self.subTest(change=change):
                profile = copy.deepcopy(self.profile)
                if change == "same-radio":
                    profile["upstream"]["band"] = profile["downstream"]["band"]
                elif change == "ifname":
                    profile["upstream"]["interface"] = "wlan0;reboot"
                elif change == "password-newline":
                    profile["upstream"]["key"] = "password\nnetwork={"
                else:
                    profile["downstream"]["channel"] = "6\ninterface=br-mgmt"
                with self.assertRaises(ValueError):
                    render(profile, "repeater")

    def test_psk_matches_known_wpa_vector(self):
        # Published IEEE/password WPA-PSK vector; independent of rendering.
        self.assertEqual(psk("IEEE", "password"),
                         "f42c6fc52df0ebef9ebb4b90b38a5f902e83fe1b135a70e23aed762e9710a12e")

    def test_same_radio_uses_one_coordinator_and_pins_selected_bssid(self):
        profile = json.loads((ROOT / 'profile.same-radio.example.json').read_text())
        profile['upstream']['bssid'] = '02:11:22:33:44:55'
        for band, ap, sta, channel in [('2g', 'wlan1', 'wlan1-vxd', 1),
                                       ('5g', 'wlan0', 'wlan0-vxd', 40)]:
            with self.subTest(band=band):
                profile['upstream'].update(band=band, interface=sta)
                profile['downstream'].update(band=band, interface=ap, channel=channel)
                files, manifest = render(profile, 'repeater')
                init = files['runtime/r15-radio.init']
                self.assertEqual(init.count('procd_open_instance'), 1)
                self.assertIn('r15-radio-coordinator ' + ap + ' ' + sta, init)
                self.assertNotIn('r15-radio-worker ap', init)
                self.assertIn('bssid=02:11:22:33:44:55', files['radio-config/wpa_supplicant.conf'])
                self.assertIn('runtime/r15-radio-coordinator', files)
                self.assertFalse(manifest['flashable'])
                self.assertFalse(manifest['installable_overlay'])

    def test_same_radio_discovers_ssid_without_bssid_or_manual_channel(self):
        profile = json.loads((ROOT / 'profile.same-radio.example.json').read_text())
        profile['upstream'].pop('bssid', None)
        profile['downstream'].pop('channel', None)
        files, _ = render(profile, 'repeater')
        self.assertNotIn('bssid=', files['radio-config/wpa_supplicant.conf'])
        self.assertIn('wlan1 wlan1-vxd auto', files['runtime/r15-radio.init'])
        self.assertEqual(files['radio-config/upstream-ssid'], 'EXAMPLE-TENDA\n')

    def test_radio_uci_stores_derived_keys_and_byte_encoded_names(self):
        profile = json.loads((ROOT / 'profile.same-radio.example.json').read_text())
        profile['upstream']['ssid'] = "Naman's \u00e9\nrouter"
        profile['downstream']['ssid'] = 'quote"\\name'
        files, _ = render(profile, 'repeater')
        config = files['openwrt-config/r15_radio']
        self.assertIn(profile['upstream']['ssid'].encode().hex(), config)
        self.assertIn(profile['downstream']['ssid'].encode().hex(), config)
        self.assertNotIn(profile['upstream']['key'], config)
        self.assertIn(psk(profile['upstream']['ssid'], profile['upstream']['key']), config)
        self.assertNotIn('option channel', config)
        self.assertIn('runtime/r15-radio-config.lua', files)

    def test_control_ssid_encoding_is_literal_for_quotes_controls_and_utf8(self):
        from r15_repeater import supplicant_text
        self.assertEqual(supplicant_text(bytes([34, 92, 27, 10, 13, 9, 1, 255])),
                         r'\"\\\e\n\r\t\x01\xff')
        self.assertEqual(supplicant_text('café'.encode()), r'caf\xc3\xa9')

    def test_same_radio_requires_reviewed_pair_and_unicast_bssid(self):
        base = json.loads((ROOT / 'profile.same-radio.example.json').read_text())
        for bad in [None, 0, '03:11:22:33:44:55', '00:00:00:00:00:00',
                    '02:11:22:33:44:55;reboot', '02:11:22:33:44:55\n']:
            profile = copy.deepcopy(base)
            profile['upstream']['bssid'] = bad
            with self.subTest(bssid=bad), self.assertRaises(ValueError):
                render(profile, 'repeater')
        base['upstream']['interface'] = 'wlan0-vxd'
        with self.assertRaisesRegex(ValueError, 'observed'):
            render(base, 'repeater')

    def test_wired_first_does_not_enable_same_radio_controller(self):
        profile = json.loads((ROOT / 'profile.same-radio.example.json').read_text())
        files, _ = render(profile, 'wired-first')
        self.assertFalse(any(name.startswith(('runtime/', 'radio-config/')) for name in files))

    def test_ssid_directive_injection_is_encoded_as_data(self):
        name = 'quote"\ninterface=br-mgmt'
        self.profile["downstream"]["ssid"] = name
        files, _ = render(self.profile, "repeater")
        config = files["radio-config/hostapd.conf"]
        self.assertIn("ssid2=" + name.encode().hex() + "\n", config)
        self.assertNotIn("\ninterface=br-mgmt", config)
        for content in files.values():
            self.assertNotIn(self.profile["upstream"]["key"], content)

    def test_valid_public_key_and_no_secret_requirement_in_wired_stage(self):
        wire = bytes.fromhex("0000000b") + b"ssh-ed25519" + bytes.fromhex("00000020") + bytes(range(32))
        key = "ssh-ed25519 " + base64.b64encode(wire).decode() + " test-only"
        self.profile["management"]["ssh_authorized_keys"] = [key]
        files, manifest = render(self.profile, "wired-first")
        self.assertEqual(files["dropbear/authorized_keys"], key + "\n")
        self.assertFalse(any("public key" in x for x in manifest["blockers"]))
        self.profile["management"]["ssh_authorized_keys"] = ["ssh-ed25519 invalid"]
        with self.assertRaises(ValueError):
            render(self.profile, "wired-first")

    def test_output_is_private_hashed_and_refuses_overwrite(self):
        with tempfile.TemporaryDirectory() as tmp:
            target = Path(tmp) / "review"
            cmd = [sys.executable, str(ROOT / "r15_repeater.py"), "--profile",
                   str(ROOT / "profile.example.json"), "--stage", "repeater", "--output", str(target)]
            result = subprocess.run(cmd, capture_output=True, text=True)
            self.assertEqual(result.returncode, 0, result.stderr)
            self.assertEqual(target.stat().st_mode & 0o777, 0o700)
            manifest = json.loads((target / "manifest.json").read_text())
            self.assertIs(manifest["flashable"], False)
            self.assertIs(manifest["installable_overlay"], False)
            self.assertTrue(manifest["blockers"])
            for name, entry in manifest["files"].items():
                path = target / name
                self.assertEqual(path.stat().st_mode & 0o777, 0o600)
                self.assertEqual(hashlib.sha256(path.read_bytes()).hexdigest(), entry["sha256"])
            before = (target / "manifest.json").read_bytes()
            self.assertEqual(subprocess.run(cmd, capture_output=True).returncode, 2)
            self.assertEqual(before, (target / "manifest.json").read_bytes())


if __name__ == "__main__":
    unittest.main()
