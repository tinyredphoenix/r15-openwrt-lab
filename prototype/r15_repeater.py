#!/usr/bin/env python3
"""Render review-only OpenWrt configurations. Never operate on a router."""
import argparse
import hashlib
import ipaddress
import json
import os
from pathlib import Path
import re
import tempfile


DEVICE = "dlink-r15-a1"
IFNAME = re.compile(r"[A-Za-z0-9_][A-Za-z0-9_.-]{0,14}\Z")
HEX_KEY = re.compile(r"[0-9a-fA-F]{64}\Z")


def interface(value):
    if not isinstance(value, str) or not IFNAME.fullmatch(value):
        raise ValueError("Interface names must be 1–15 plain netdev characters")
    return value


def ssid(value):
    if not isinstance(value, str) or not 1 <= len(value.encode("utf-8")) <= 32:
        raise ValueError("SSID must contain 1–32 UTF-8 bytes")
    return value.encode("utf-8")


def psk(name, key):
    if isinstance(key, str) and HEX_KEY.fullmatch(key):
        return key.lower()
    if not isinstance(key, str) or not 8 <= len(key) <= 63 or any(
        not 32 <= ord(c) <= 126 for c in key
    ):
        raise ValueError("Use an 8–63 printable ASCII WPA2 passphrase or 64 hex PSK")
    return hashlib.pbkdf2_hmac("sha1", key.encode("ascii"), ssid(name), 4096, 32).hex()


def subnet(value):
    address = ipaddress.IPv4Interface(value)
    private = [ipaddress.IPv4Network(n) for n in
               ("10.0.0.0/8", "172.16.0.0/12", "192.168.0.0/16")]
    if address.network.prefixlen != 24 or not any(
        address.network.subnet_of(n) for n in private
    ) or address.ip in (address.network.network_address, address.network.broadcast_address):
        raise ValueError("Use an RFC1918 /24 host address for this prototype")
    if 100 <= (int(address.ip) & 255) <= 149:
        raise ValueError("Router address conflicts with the reserved DHCP range .100–.149")
    return address


def uci(section, kind, values):
    # Every value must be a validated identifier, number, address or fixed literal.
    lines = ["config %s '%s'" % (kind, section)]
    for key, value in values:
        if any(c in str(value) for c in "'\n\r\\"):
            raise ValueError("Unsafe UCI value")
        lines.append("\toption %s '%s'" % (key, value))
    return "\n".join(lines) + "\n\n"


def supplicant_text(data):
    """Match pinned hostap common.c printf_encode, without decoding shell data."""
    escapes = {34: '\\"', 92: '\\\\', 27: '\\e', 10: '\\n', 13: '\\r', 9: '\\t'}
    return ''.join(escapes.get(x, chr(x) if 32 <= x <= 126 else '\\x%02x' % x) for x in data)


def management_files(profile):
    management = profile["management"]
    address = subnet(management["address"])
    for value in profile.get("known_upstream_subnets", []):
        if ipaddress.IPv4Network(value, strict=False).overlaps(address.network):
            raise ValueError("Upstream overlaps the reserved management network")
    ports = management["wired_ports"]
    if not isinstance(ports, list) or not ports or len(set(ports)) != len(ports):
        raise ValueError("Reserve at least one distinct wired port for management")
    for port in ports:
        interface(port)
    if any(p in ("lo", "br-mgmt", "br-lan") or p.startswith(("wlan", "phy")) for p in ports):
        raise ValueError("Management must reserve a wired netdev, not Wi-Fi or a generated bridge")
    network = uci("loopback", "interface", [("ifname", "lo"), ("proto", "static"),
                                             ("ipaddr", "127.0.0.1"), ("netmask", "255.0.0.0")])
    # Legacy ifname bridge syntax targets the vendor-kernel/OpenWrt 21.02 route.
    network += uci("mgmt", "interface", [("type", "bridge"), ("ifname", " ".join(ports)),
                     ("proto", "static"), ("ipaddr", str(address.ip)),
                     ("netmask", str(address.netmask)), ("force_link", "1"), ("delegate", "0")])
    firewall = uci("defaults", "defaults", [("input", "REJECT"), ("output", "ACCEPT"),
                                             ("forward", "REJECT"), ("syn_flood", "1")])
    firewall += uci("mgmt", "zone", [("name", "mgmt"), ("network", "mgmt"),
                        ("input", "ACCEPT"), ("output", "ACCEPT"), ("forward", "REJECT")])
    dhcp = uci("mgmt_dns", "dnsmasq", [("port", "0"), ("noresolv", "1"), ("localuse", "0"),
                       ("nonwildcard", "1"), ("interface", "mgmt"), ("leasefile", "/tmp/mgmt.leases")])
    dhcp += uci("mgmt", "dhcp", [("instance", "mgmt_dns"), ("interface", "mgmt"), ("start", "100"),
                                ("limit", "50"), ("leasetime", "1h")])
    # A management cable must not replace a laptop's working Internet route/DNS.
    dhcp += "\tlist dhcp_option '3'\n\tlist dhcp_option '6'\n\n"
    keys = management.get("ssh_authorized_keys", [])
    if not isinstance(keys, list):
        raise ValueError("SSH public keys must be a list")
    import base64
    import struct
    for key in keys:
        if not isinstance(key, str) or "\n" in key or "\r" in key:
            raise ValueError("One SSH public key per string")
        fields = key.split()
        if len(fields) < 2 or fields[0] != "ssh-ed25519":
            raise ValueError("This prototype accepts plain ssh-ed25519 public keys")
        try:
            raw = base64.b64decode(fields[1], validate=True)
        except (ValueError, TypeError) as exc:
            raise ValueError("Invalid SSH public key encoding") from exc
        expected = struct.pack(">I", 11) + b"ssh-ed25519" + struct.pack(">I", 32)
        if len(raw) != len(expected) + 32 or not raw.startswith(expected):
            raise ValueError("Invalid Ed25519 SSH public key structure")
    dropbear = uci("management", "dropbear", [("Interface", "mgmt"), ("Port", "22"),
                          ("PasswordAuth", "off"), ("RootPasswordAuth", "off")])
    return {
        "openwrt-config/network": network,
        "openwrt-config/firewall": firewall,
        "openwrt-config/dhcp": dhcp,
        "openwrt-config/dropbear": dropbear,
        "openwrt-config/uhttpd": uci("management", "uhttpd", [
            ("redirect_https", "1"), ("home", "/www"), ("cgi_prefix", "/cgi-bin"),
            ("ubus_prefix", "/ubus"), ("cert", "/etc/uhttpd.crt"),
            ("key", "/etc/uhttpd.key"), ("no_dirlists", "1"),
            ("script_timeout", "60"), ("network_timeout", "30")]) +
            "\tlist listen_http '" + str(address.ip) + ":80'\n" +
            "\tlist listen_https '" + str(address.ip) + ":443'\n",
        "openwrt-config/rpcd": uci("rpcd", "rpcd", [
            ("socket", "/var/run/ubus/ubus.sock"), ("timeout", "30")]) +
            uci("root", "login", [("username", "root"), ("password", "$p$root")]) +
            "\tlist read '*'\n\tlist write '*'\n",
        "openwrt-config/wireless": "# No netifd-managed radios in this prototype.\n",
        "dropbear/authorized_keys": "\n".join(keys) + ("\n" if keys else ""),
    }, address, ports


def render(profile, stage):
    if stage not in ("wired-first", "repeater"):
        raise ValueError("Unknown prototype stage")
    if profile.get("device") != DEVICE or profile.get("country") != "IN":
        raise ValueError("This prototype is scoped to R15 A1 / India")
    files, management, reserved = management_files(profile)
    pending = ["Physical wired-port mapping and switch initialization unverified",
               "Independent bootloader recovery and accepted stock image unverified",
               "Watchdog handoff and boot-success confirmation requirements unverified",
               "Complete recoverable per-unit flash/calibration preservation not qualified",
               "RAM-only kernel/Ethernet/SSH boot test not performed",
               "Actual custom boot and safe update handling unverified"]
    pending.append("LuCI root password, HTTPS identity and actual web/RPC service startup not provisioned or qualified")
    if not profile["management"].get("ssh_authorized_keys"):
        pending.append("No owner SSH public key configured: SSH login would be unavailable")
    if stage == "repeater":
        upstream, downstream = profile["upstream"], profile["downstream"]
        if upstream["band"] not in ("2g", "5g") or downstream["band"] not in ("2g", "5g"):
            raise ValueError("Unknown radio band")
        same_radio = upstream["band"] == downstream["band"]
        uplink, ap = interface(upstream["interface"]), interface(downstream["interface"])
        selected_bssid = upstream.get("bssid", "")
        if same_radio:
            expected = ("wlan1", "wlan1-vxd") if upstream["band"] == "2g" else ("wlan0", "wlan0-vxd")
            if (ap, uplink) != expected:
                raise ValueError("Same-radio mode requires the observed AP/VXD interface pair")
            if not isinstance(selected_bssid, str) or (selected_bssid and not re.fullmatch(r"(?:[0-9a-fA-F]{2}:){5}[0-9a-fA-F]{2}", selected_bssid)):
                raise ValueError("Invalid optional upstream BSSID")
            selected_bssid = selected_bssid.lower()
            if selected_bssid and (int(selected_bssid[:2], 16) & 1 or selected_bssid == "00:00:00:00:00:00"):
                raise ValueError("Select a nonzero unicast upstream BSSID")
        if len({uplink, ap, *reserved}) != len(reserved) + 2 or any(
            name in ("lo", "br-mgmt", "br-lan") for name in (uplink, ap)
        ):
            raise ValueError("Wi-Fi interfaces must be distinct and cannot consume management ports/bridges")
        lan = subnet(downstream["address"])
        if lan.network.overlaps(management.network):
            raise ValueError("Downstream network overlaps the reserved management network")
        for value in profile.get("known_upstream_subnets", []):
            net = ipaddress.IPv4Network(value, strict=False)
            if net.overlaps(management.network) or net.overlaps(lan.network):
                raise ValueError("Upstream overlaps a local network")
        channel = downstream.get("channel", 1 if downstream["band"] == "2g" else 36)
        choices = (1, 6, 11) if downstream["band"] == "2g" else (36, 40, 44, 48)
        if type(channel) is not int or channel not in choices:
            raise ValueError("Use a conservative fixed 20 MHz prototype AP channel")
        sta_key, ap_key = psk(upstream["ssid"], upstream["key"]), psk(downstream["ssid"], downstream["key"])
        files["radio-config/wpa_supplicant.conf"] = (
            "ctrl_interface=/var/run/r15-wpa\ncountry=IN\nap_scan=1\nnetwork={\n"
            "\tssid=%s\n\tscan_ssid=1\n\tproto=RSN\n\tkey_mgmt=WPA-PSK\n"
            "\tpairwise=CCMP\n\tgroup=CCMP\n\tpsk=%s\n}\n" % (ssid(upstream["ssid"]).hex(), sta_key))
        files["radio-config/upstream-ssid"] = supplicant_text(ssid(upstream["ssid"])) + "\n"
        if same_radio and selected_bssid:
            files["radio-config/wpa_supplicant.conf"] = files["radio-config/wpa_supplicant.conf"].replace(
                "network={\n", "network={\n\tbssid=" + selected_bssid + "\n", 1)
        files["radio-config/hostapd.conf"] = (
            "driver=nl80211\ninterface=%s\nbridge=br-lan\nctrl_interface=/var/run/r15-hostapd\n"
            "ssid2=%s\ncountry_code=IN\nieee80211d=1\nhw_mode=%s\nchannel=%d\n"
            "ieee80211n=1\nwmm_enabled=1\nauth_algs=1\nwpa=2\n"
            "wpa_key_mgmt=WPA-PSK\nrsn_pairwise=CCMP\nwpa_psk=%s\n" % (
                ap, ssid(downstream["ssid"]).hex(), "g" if downstream["band"] == "2g" else "a", channel, ap_key))
        files["radio-config/protected-subnets"] = str(management.network) + "\n" + str(lan.network) + "\n"
        files["runtime/r15-subnet-check"] = (
            Path(__file__).parent / "runtime/r15-subnet-check").read_text()
        for helper in ("r15-dhcp-guard", "r15-dhcp.script"):
            files["runtime/" + helper] = (Path(__file__).parent / "runtime" / helper).read_text()
        files["runtime/r15-radio-worker"] = (
            Path(__file__).parent / "runtime/r15-radio-worker").read_text()
        files["runtime/r15-radio.init"] = (
            "#!/bin/sh /etc/rc.common\nUSE_PROCD=1\nSTART=80\nSTOP=10\n"
            "start_service() {\n"
            "    procd_open_instance ap\n"
            "    procd_set_param command /usr/libexec/r15-radio-worker ap %s %s\n"
            "    procd_set_param respawn 3600 5 5\n"
            "    procd_set_param stdout 1\n    procd_set_param stderr 1\n"
            "    procd_close_instance\n"
            "    procd_open_instance sta\n"
            "    procd_set_param command /usr/libexec/r15-radio-worker sta %s %s\n"
            "    procd_set_param respawn 3600 5 5\n"
            "    procd_set_param stdout 1\n    procd_set_param stderr 1\n"
            "    procd_close_instance\n}\n" % (ap, uplink, ap, uplink))
        if same_radio:
            files["runtime/r15-radio-coordinator"] = (
                Path(__file__).parent / "runtime/r15-radio-coordinator").read_text()
            files["runtime/r15-radio-config.lua"] = (
                Path(__file__).parent / "runtime/r15-radio-config.lua").read_text()
            # Store derived PSKs rather than duplicating plaintext passphrases.
            # This schema is consumed by our adapter, never the mac80211 backend.
            radio_options = [("enabled", "1"), ("country", "IN"),
                ("encryption", "psk2+ccmp"), ("band", upstream["band"]),
                ("upstream_ssid_hex", ssid(upstream["ssid"]).hex()), ("upstream_key", sta_key),
                ("ap_ssid_hex", ssid(downstream["ssid"]).hex()), ("ap_key", ap_key)]
            if selected_bssid:
                radio_options.append(("bssid", selected_bssid))
            files["openwrt-config/r15_radio"] = uci("repeater", "repeater", radio_options)
            for helper in ("r15-radio-launch", "r15-radio.init"):
                files["runtime/" + helper] = (Path(__file__).parent / "runtime" / helper).read_text()
        # No static ifname: vendor Wi-Fi must be attached as an external device
        # by a future board-specific backend, rather than recreated by netifd.
        files["openwrt-config/network"] += uci("lan", "interface", [("type", "bridge"),
            ("bridge_empty", "1"), ("proto", "static"), ("ipaddr", str(lan.ip)),
            ("netmask", str(lan.netmask)), ("delegate", "0")])
        files["openwrt-config/network"] += uci("wwan", "interface", [("proto", "dhcp"), ("auto", "0")])
        files["openwrt-config/firewall"] += uci("lan", "zone", [("name", "lan"),
            ("network", "lan"), ("input", "ACCEPT"), ("output", "ACCEPT"), ("forward", "REJECT")])
        files["openwrt-config/firewall"] += uci("wwan", "zone", [("name", "wwan"),
            ("network", "wwan"), ("input", "REJECT"), ("output", "ACCEPT"),
            ("forward", "REJECT"), ("masq", "1"), ("mtu_fix", "1")])
        files["openwrt-config/firewall"] += uci("lan_to_wwan", "forwarding", [("src", "lan"), ("dest", "wwan")])
        files["openwrt-config/firewall"] += uci("dhcp_reply", "rule", [("src", "wwan"),
            ("proto", "udp"), ("src_port", "67"), ("dest_port", "68"), ("family", "ipv4"), ("target", "ACCEPT")])
        files["openwrt-config/dhcp"] += uci("lan_dns", "dnsmasq", [("domainneeded", "1"),
            ("boguspriv", "1"), ("localservice", "1"), ("localuse", "1"),
            ("nonwildcard", "1"), ("interface", "lan"), ("leasefile", "/tmp/lan.leases")])
        files["openwrt-config/dhcp"] += uci("lan", "dhcp", [("instance", "lan_dns"), ("interface", "lan"),
            ("start", "100"), ("limit", "50"), ("leasetime", "12h")])
        files["openwrt-config/dhcp"] += uci("wwan", "dhcp", [("interface", "wwan"), ("ignore", "1")])
        pending += ["Radio-to-netdev mapping, RF tables and per-unit MAC initialization unverified",
                    "Custom hostapd AP startup on the R15 not qualified; prior runtime AP tests retained OEM hostapd",
                    "Radio worker and external-device reconnect implemented; target execution and procd integration untested",
                    "Board driver/MAC/RF initialization and board-startup-verified prerequisite not implemented",
                    "Learned connected-subnet rejection implemented for same-radio coordinator; DHCP route window and classless routes remain unprotected; cross-radio worker lacks this guard"]
        if same_radio:
            pending += ["Same-radio coordinator has offline tests only; target execution and custom AP startup are unqualified",
                        "SSID discovery and optional BSSID pinning implemented; roaming and DFS/high-band coordination unqualified",
                        "Dedicated radio UCI reader and supervised reload entry implemented; actual apply and LuCI form remain unqualified",
                        "Gateway ICMP health policy requires validation; no Internet or production readiness is inferred"]
    laptop = management.network.network_address + (2 if (int(management.ip) & 255) != 2 else 3)
    files["REVIEW-ONLY.txt"] = (
        "NOT FIRMWARE. NOT AN INSTALLABLE OVERLAY. DO NOT COPY TO A ROUTER.\n"
        "These are configuration inputs for a future R15 build, not a rootfs.\n"
        "No kernel, init system, driver backend, boot metadata or update handler is included.\n"
        "Candidate wired address: %s; direct laptop fallback: %s/24.\n" % (
            management.ip, laptop) +
        "Port names are unverified placeholders in the example profile.\n"
        "Wired-first must be tested before radios. SSH requires an owner public key.\n"
        "Radio configuration files contain PSKs equivalent to passwords. Keep this directory private.\n")
    manifest = {"device": DEVICE, "stage": stage, "architecture": "MIPS32r2 big-endian",
                "configuration_dialect": "OpenWrt 21.02 / firewall3 (vendor-kernel research route)",
                "flashable": False, "installable_overlay": False,
                "management_address": str(management), "reserved_wired_ports": reserved,
                "blockers": pending,
                "files": {p: {"bytes": len(v.encode()), "sha256": hashlib.sha256(v.encode()).hexdigest()}
                          for p, v in sorted(files.items())}}
    return files, manifest


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--profile", required=True, type=Path)
    parser.add_argument("--stage", required=True, choices=("wired-first", "repeater"))
    parser.add_argument("--output", required=True, type=Path)
    args = parser.parse_args()
    try:
        files, manifest = render(json.loads(args.profile.read_text()), args.stage)
        target = args.output.absolute()
        if target.exists() or target.is_symlink():
            raise ValueError("Output already exists; choose a new directory")
        target.parent.mkdir(parents=True, exist_ok=True)
        with tempfile.TemporaryDirectory(prefix=".r15-render-", dir=target.parent) as work:
            staging = Path(work) / "bundle"
            staging.mkdir(mode=0o700)
            for name, content in {**files, "manifest.json": json.dumps(manifest, indent=2) + "\n"}.items():
                dest = staging / name
                dest.parent.mkdir(parents=True, exist_ok=True, mode=0o700)
                dest.write_text(content)
                dest.chmod(0o600)
            os.rename(staging, target)
        print("Review-only bundle: %s\nFlashable: no\nUnresolved prerequisites: %d" % (target, len(manifest["blockers"])))
    except (ValueError, KeyError, TypeError, OSError) as exc:
        parser.exit(2, "Cannot render profile: %s\n" % exc)


if __name__ == "__main__":
    main()
