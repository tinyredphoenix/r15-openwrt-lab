"""Run bounded userspace-only checks under QEMU; start no network daemons."""
import importlib.util
import json
import re
from pathlib import Path
import subprocess
import sys
import tempfile


def invoke(root, program, args=(), *, input=None, accepted=(0,)):
    result = subprocess.run(['qemu-mips', '-L', str(root), str(root / program), *map(str, args)],
                            input=input, text=True, capture_output=True, timeout=20)
    if result.returncode not in accepted:
        raise RuntimeError(f'{program} exited {result.returncode}: {result.stderr[:1000]}')
    return result


def check(root, output):
    root = root.resolve()
    checks = {}
    # OpenWrt's minimal BusyBox disables the optional --list/installer support.
    # Dispatch the required applets themselves; --help starts no networking.
    for applet in ('ip', 'udhcpc', 'mktemp'):
        result = invoke(root, 'bin/busybox', [applet, '--help'], accepted=(0, 1))
        if not re.search(r'Usage:\s*' + applet + r'\b', result.stdout + result.stderr):
            raise RuntimeError('Required BusyBox applet help unavailable: ' + applet)
    checks['busybox_required_applets'] = ['ash', 'ip', 'udhcpc', 'mktemp']
    repository = Path(__file__).resolve().parents[1]
    invoke(root, 'bin/busybox', ['ash', '-n', repository / 'prototype/runtime/r15-radio-worker'])
    checks['radio_worker_busybox_syntax'] = 'pass'
    for relative in ('lib/netifd/dhcp.script', 'usr/libexec/r15-openwrt-dhcp.script',
                     'usr/libexec/r15-subnet-check', 'usr/libexec/r15-dhcp-guard',
                     'usr/libexec/r15-radio-launch'):
        invoke(root, 'bin/busybox', ['ash', '-n', root / relative])
    checks['dhcp_preflight_target_syntax'] = 'pass; no DHCP event script executed'

    invoke(root, 'bin/busybox', ['ash', '-n', repository / 'prototype/runtime/r15-radio-coordinator'])
    checks['radio_coordinator_busybox_syntax'] = 'pass'
    subnet_helper = repository / 'prototype/runtime/r15-subnet-check'
    invoke(root, 'bin/busybox', ['ash', '-n', subnet_helper])
    # Execute the embedded range arithmetic in target awk, never a host awk
    # launched by an emulated shell. Synthetic files contain no owner data.
    subnet_source = subnet_helper.read_text()
    marker = "LC_ALL=C awk -v learned=\"$1\" '"
    ending = "' \"$2\"\n"
    if subnet_source.count(marker) != 1 or not subnet_source.endswith(ending):
        raise RuntimeError('Unexpected subnet checker wrapper')
    subnet_awk = subnet_source.split(marker, 1)[1][:-len(ending)]
    with tempfile.TemporaryDirectory() as subnet_tmp:
        protected = Path(subnet_tmp) / 'protected'
        protected.write_text('192.168.77.0/24\n192.168.88.0/24\n')
        for cidr, expected in [('192.168.0.10/24', 0), ('192.168.77.1/24', 1),
                               ('192.168.88.254/32', 1), ('192.168.0.1/16', 1),
                               ('0.0.0.0/0', 1), ('192.168.0.1/33', 2)]:
            result = invoke(root, 'bin/busybox', ['awk', '-v', 'learned=' + cidr,
                            subnet_awk, protected], accepted=(0, 1, 2))
            if result.returncode != expected:
                raise RuntimeError('Target subnet policy mismatch: ' + cidr)
    checks['radio_subnet_target_awk'] = 'pass; six synthetic range/rejection cases'
    # Execute the observed failure/recovery sequence in the target ash itself.
    # Every observation/actuator is a shell stub; no host utility, daemon,
    # interface, process stop or network request is dispatched by this fixture.
    policy_fixture = r'''
R15_SOURCE_ONLY=1
R15_WORKER_LIBRARY=$1
. "$2"
AP=wlan1; STA=wlan1-vxd; BSSID=02:11:22:33:44:55
ROLE=sta; ATTACHED=1; READY=0; FAILURES=0; NEED_REJOIN=0
REJOIN_WAIT=0; ALIGN_WAIT=0; PENDING_FREQ=
TFREQ=2452; TCARRIER=1
management_up() { return 0; }
read_station() { STATE=COMPLETED; SFREQ=2412; SBSSID=$BSSID; CARRIER=$TCARRIER; }
read_ap() { APSTATE=ENABLED; AFREQ=$TFREQ; }
scan_frequency() { SCANFREQ=2412; return 0; }
handle_link() {
 case "$1:$ATTACHED" in
  disconnected:1) echo detach; ATTACHED=0 ;;
  connected:0) echo attach; ATTACHED=1 ;;
 esac
}
align_ap() { echo "align:$1"; }
rejoin_station() { echo rejoin; }
request_scan() { echo scan; }
lease_up() { return 0; }
lease_network_safe() { return 0; }
probe_uplink() { echo probe; }
rlog() { echo unexpected-log; }
coordinate_tick || exit 1
echo "ready:$READY"
TFREQ=2412; TCARRIER=0
coordinate_tick || exit 1
echo "ready:$READY"
TCARRIER=1
coordinate_tick || exit 1
echo "ready:$READY"
'''
    policy = invoke(root, 'bin/busybox', ['ash', '-s', '--',
        repository / 'prototype/runtime/r15-radio-worker',
        repository / 'prototype/runtime/r15-radio-coordinator'], input=policy_fixture)
    expected = ['detach', 'align:2412', 'ready:0', 'rejoin', 'ready:0',
                'attach', 'probe', 'ready:1']
    if policy.stdout.splitlines() != expected:
        raise RuntimeError('Target radio policy failure/recovery sequence failed: ' + policy.stdout)
    checks['radio_coordinator_target_policy'] = 'pass; target ash with shell-only fake adapters'
    invoke(root, 'bin/busybox', ['ash', '-n', repository / 'prototype/runtime/r15-health'])
    checks['health_probe_busybox_syntax'] = 'pass'
    helpers = json.loads((repository / 'build/common-runtime-manifest.json').read_text())
    for record in helpers['files']:
        invoke(root, 'bin/busybox', ['ash', '-n', root / record['path']])
    checks['common_service_helper_busybox_syntax'] = [r['path'] for r in helpers['files']]
    # Execute only the helper's embedded AWK with the target BusyBox. Running
    # the shell wrapper under QEMU could dispatch the host's awk via PATH.
    ipcalc = (root / 'bin/ipcalc.sh').read_text()
    prefix, suffix = 'awk -f - $* <<EOF\n', '\nEOF\n'
    if ipcalc.count(prefix) != 1 or not ipcalc.endswith(suffix):
        raise RuntimeError('Unexpected pinned ipcalc wrapper')
    awk = ipcalc.split(prefix, 1)[1][:-len(suffix)] + '\n'
    calculations = [(['192.168.77.1', '255.255.255.0'],
                     {'NETWORK': '192.168.77.0', 'BROADCAST': '192.168.77.255', 'PREFIX': '24'}),
                    (['10.20.30.40/16'], {'NETWORK': '10.20.0.0', 'NETMASK': '255.255.0.0', 'PREFIX': '16'}),
                    (['192.168.77.1', '24', '100', '49'], {'START': '192.168.77.100', 'END': '192.168.77.149'})]
    for args, expected in calculations:
        result = invoke(root, 'bin/busybox', ['awk', '-f', '-', *args], input=awk)
        actual = dict(line.split('=', 1) for line in result.stdout.splitlines())
        if any(actual.get(key) != value for key, value in expected.items()):
            raise RuntimeError('Target ipcalc arithmetic failed: ' + result.stdout)
    checks['ipcalc_target_awk'] = 'pass; dotted mask, CIDR and management DHCP range'
    # Source-verified -h exits before fw3 builds state, connects to ubus or
    # touches netfilter. Never call start/stop/flush/print under user emulation.
    firewall = invoke(root, 'sbin/fw3', ['-h'], accepted=(1,))
    if 'fw3 [-4]' not in firewall.stderr:
        raise RuntimeError('Missing firewall3 help output')
    checks['firewall_help'] = 'pass; help-only, no firewall state accessed'
    for program in ('iptables', 'ip6tables'):
        version = invoke(root, 'usr/sbin/' + program, ['--version'])
        if not re.search(r'^' + program + r' v[0-9].*\(legacy\)', version.stdout):
            raise RuntimeError('Expected legacy xtables version: ' + program)
        checks[program + '_version'] = version.stdout.strip()
    checks['firewall_rules_enforced'] = False
    dropbear = invoke(root, 'usr/sbin/dropbear', ['-V'], accepted=(0, 1))
    if 'Dropbear v' not in dropbear.stdout + dropbear.stderr:
        raise RuntimeError('Missing Dropbear version output')
    checks['dropbear_version'] = (dropbear.stdout + dropbear.stderr).strip()
    dnsmasq = invoke(root, 'usr/sbin/dnsmasq', ['--version'])
    if 'Dnsmasq version' not in dnsmasq.stdout:
        raise RuntimeError('Missing dnsmasq version output')
    checks['dnsmasq_version'] = dnsmasq.stdout.splitlines()[0]
    parsed = invoke(root, 'usr/bin/jsonfilter', ['-e', '@.up'], input='{"up":true}\n')
    if parsed.stdout.strip() != 'true':
        raise RuntimeError('Management-status JSON parser did not return true')
    checks['management_status_json'] = 'pass'
    routes = {'route': [
        {'target': '0.0.0.0', 'table': 199, 'nexthop': '192.0.2.199'},
        {'target': '0.0.0.0', 'nexthop': '192.0.2.1'},
        {'target': '192.0.2.0', 'nexthop': '192.0.2.2'}]}
    gateway = invoke(root, 'usr/bin/jsonfilter',
        ['-e', '@.route[@.target="0.0.0.0" && !@.table].nexthop'], input=json.dumps(routes))
    if gateway.stdout.strip() != '192.0.2.1':
        raise RuntimeError('Radio gateway selector did not isolate the main default route')
    checks['radio_gateway_json'] = 'pass; synthetic input only, no route or radio operation'
    interface = invoke(root, 'usr/bin/jsonfilter', ['-e', '@["ipv4-address"][0].address'],
        input=json.dumps({'ipv4-address': [{'address': '192.0.2.10', 'mask': 24}]}))
    if interface.stdout.strip() != '192.0.2.10':
        raise RuntimeError('Radio IPv4 address selector did not return the learned address')
    checks['radio_lease_json'] = 'pass; synthetic input only'
    lease_fixture = json.dumps({'ipv4-address': [{'address': '192.0.2.10', 'mask': 24}]})
    prefix = invoke(root, 'usr/bin/jsonfilter', ['-e', '@["ipv4-address"][0].mask'], input=lease_fixture)
    addresses = invoke(root, 'usr/bin/jsonfilter', ['-e', '@["ipv4-address"][*].address'], input=lease_fixture)
    if prefix.stdout.strip() != '24' or addresses.stdout.splitlines() != ['192.0.2.10']:
        raise RuntimeError('Lease prefix/cardinality JSON selection failed')
    checks['radio_lease_shape_json'] = 'pass; synthetic prefix/address cardinality'

    # Keys and temporary config stay outside artifacts and are removed on exit.
    with tempfile.TemporaryDirectory(prefix='r15-userspace-check-') as tmp:
        temporary = Path(tmp)
        key = temporary / 'ephemeral_ed25519'
        invoke(root, 'usr/bin/dropbearkey', ['-t', 'ed25519', '-f', key])
        public = invoke(root, 'usr/bin/dropbearkey', ['-y', '-f', key]).stdout
        if not any(line.startswith('ssh-ed25519 ') for line in public.splitlines()):
            raise RuntimeError('Ed25519 key generation/public-key export failed')
        checks['ed25519_generation'] = 'pass; temporary test key deleted, not published'
        spec = importlib.util.spec_from_file_location('renderer', repository / 'prototype/r15_repeater.py')
        renderer = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(renderer)
        profile = json.loads((repository / 'prototype/profile.stock-observed.example.json').read_text())
        rendered, _ = renderer.render(profile, 'wired-first')
        config = temporary / 'config'
        state = temporary / 'state'
        config.mkdir(); state.mkdir()
        for name in ('network', 'dhcp', 'dropbear', 'firewall', 'uhttpd', 'rpcd'):
            (config / name).write_text(rendered['openwrt-config/' + name])
            result = invoke(root, 'sbin/uci', ['-c', config, '-P', state, 'export', name])
            if 'package ' + name not in result.stdout:
                raise RuntimeError('UCI failed to export ' + name)
        checks['renderer_uci_parsing'] = ['network', 'dhcp', 'dropbear', 'firewall', 'uhttpd', 'rpcd']
        same = json.loads((repository / 'prototype/profile.same-radio.example.json').read_text())
        same['upstream']['ssid'] = "owner's \u00e9\nSSID"
        same_files, _ = renderer.render(same, 'repeater')
        (config / 'r15_radio').write_text(same_files['openwrt-config/r15_radio'])
        invoke(root, 'sbin/uci', ['-c', config, '-P', state, 'export', 'r15_radio'])
        radio_uci = invoke(root, 'usr/bin/lua', ['-', root, config, state,
            root / 'usr/libexec/r15-radio-config.lua'], input=r"""
package.cpath=arg[1]..'/usr/lib/lua/?.so;'..arg[1]..'/usr/lib/lua/?/init.so'
local cursor=require('uci').cursor(arg[2],arg[3])
local radio=assert(loadfile(arg[4]))()
local profile=radio.from_uci(cursor)
assert(profile.ap=='wlan1' and profile.sta=='wlan1-vxd' and profile.bssid=='auto')
assert(profile.supplicant:find('ssid=6f776e6572277320c3a90a53534944',1,true))
print('radio-uci-pass')
""")
        if radio_uci.stdout.strip() != 'radio-uci-pass':
            raise RuntimeError('Target UCI radio profile round-trip failed')
        checks['radio_uci_target_roundtrip'] = 'pass; actual UCI parser, quote/newline/UTF-8 SSID, no commit or service apply'
        dns_config = temporary / 'dnsmasq.conf'
        dns_config.write_text('port=0\ninterface=br-mgmt\nbind-dynamic\n'
                              'dhcp-range=192.168.77.100,192.168.77.149,255.255.255.0,1h\n'
                              'dhcp-option=3\ndhcp-option=6\n')
        invoke(root, 'usr/sbin/dnsmasq', ['--test', '--conf-file=' + str(dns_config)])
        dns_config.write_text('not-a-dnsmasq-option=true\n')
        bad = invoke(root, 'usr/sbin/dnsmasq', ['--test', '--conf-file=' + str(dns_config)],
                     accepted=tuple(range(1, 126)))
        if 'bad option' not in bad.stderr.lower():
            raise RuntimeError('Invalid-config negative control did not report a bad option')
        checks['management_dhcp_syntax'] = 'pass, including no-default-route/DNS options and invalid-config rejection'
    luci_files = sorted((root / 'usr/lib/lua/luci').rglob('*.lua'))
    if not luci_files or not (root / 'www/cgi-bin/luci').is_file():
        raise RuntimeError('LuCI dispatcher/assets were not collected')
    # Parse without executing controller code, loading modules or serving HTTP.
    lua = invoke(root, 'usr/bin/lua', ['-', *luci_files],
                 input='for i=1,#arg do assert(loadfile(arg[i])) end\nprint("syntax-only")\n')
    if lua.stdout.strip() != 'syntax-only':
        raise RuntimeError('Unexpected Lua syntax-check result')
    checks['luci_target_lua_syntax'] = {'files': len(luci_files), 'executed_controllers': False}
    radio_lua = invoke(root, 'usr/bin/lua', ['-', root, root / 'usr/libexec/r15-radio-config.lua'], input=r"""
package.cpath=arg[1]..'/usr/lib/lua/?.so;'..arg[1]..'/usr/lib/lua/?/init.so'
local radio=assert(loadfile(arg[2]))()
assert(radio.psk('IEEE','password')=='f42c6fc52df0ebef9ebb4b90b38a5f902e83fe1b135a70e23aed762e9710a12e')
assert(radio.control_ssid('quote'..string.char(34,92,10))=='quote'..string.char(92,34,92,92,92,110))
assert(radio.control_ssid(string.char(195,169))==string.char(92)..'xc3'..string.char(92)..'xa9')
local result=radio.render({band='2g',upstream_ssid='EXAMPLE',upstream_key=string.rep('a',64),
                          ap_ssid='test\ninterface=bad',ap_key=string.rep('b',64)})
assert(result.bssid=='auto' and result.ap=='wlan1' and result.sta=='wlan1-vxd')
assert(not result.hostapd:find('\ninterface=bad',1,true))
assert(result.hostapd:find('ssid2=',1,true))
assert(not pcall(radio.render,{band='bad'}))
assert(not pcall(radio.psk,'IEEE','short'))
assert(not pcall(radio.render,{band='2g',upstream_ssid='a',upstream_key=string.rep('a',64),
    ap_ssid='b',ap_key=string.rep('b',64),bssid='03:11:22:33:44:55'}))
local section={['.name']='repeater',['.type']='repeater',enabled='1',country='IN',
    encryption='psk2+ccmp',band='5g',upstream_ssid_hex='49276d0a',
    upstream_key=string.rep('a',64),ap_ssid_hex='6170',ap_key=string.rep('b',64)}
local fake={foreach=function(self,package,kind,callback)
    assert(package=='r15_radio' and kind=='repeater'); callback(section)
end}
local uci_render=radio.from_uci(fake)
assert(uci_render.ap=='wlan0' and uci_render.sta=='wlan0-vxd')
assert(uci_render.upstream_text=="I'm"..string.char(92)..'n'..string.char(10))
section.enabled='0'; assert(radio.from_uci(fake)==nil)
section.enabled='1'; section.channel='36'; assert(not pcall(radio.from_uci,fake)); section.channel=nil
section.country='US'; assert(not pcall(radio.from_uci,fake)); section.country='IN'
section.encryption='none'; assert(not pcall(radio.from_uci,fake)); section.encryption='psk2+ccmp'
section.upstream_ssid_hex='abc'; assert(not pcall(radio.from_uci,fake))
section.upstream_ssid_hex='gg'; assert(not pcall(radio.from_uci,fake))
assert(not pcall(radio.from_uci,{foreach=function() end}))
assert(not pcall(radio.from_uci,{foreach=function(self,p,k,cb) cb(section);cb(section) end}))
print('radio-config-pass')
""")
    if radio_lua.stdout.strip() != 'radio-config-pass':
        raise RuntimeError('Target radio configuration/PSK check failed')
    checks['radio_config_target_lua'] = 'pass; WPA2 known vector, encoding, validation and private config rendering only'

    checks['scope'] = 'Userspace execution only: no SSH listener, DHCP daemon, init, mounts, or network changes'
    checks['kernel_and_hardware_tested'] = False
    (output / 'management-checks.json').write_text(json.dumps(checks, indent=2) + '\n')
    print(json.dumps(checks, indent=2))


if __name__ == '__main__':
    check(Path(sys.argv[1]), Path(sys.argv[2]))
