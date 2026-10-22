"""Run bounded userspace-only checks under QEMU; start no network daemons."""
import importlib.util
import json
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
    applets = invoke(root, 'bin/busybox', ['--list']).stdout.splitlines()
    for applet in ('ash', 'ip', 'udhcpc'):
        if applet not in applets:
            raise RuntimeError('Required BusyBox applet missing: ' + applet)
    checks['busybox_required_applets'] = ['ash', 'ip', 'udhcpc']
    repository = Path(__file__).resolve().parents[1]
    invoke(root, 'bin/busybox', ['ash', '-n', repository / 'prototype/runtime/r15-radio-worker'])
    checks['radio_worker_busybox_syntax'] = 'pass'
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
        for name in ('network', 'dhcp', 'dropbear', 'firewall'):
            (config / name).write_text(rendered['openwrt-config/' + name])
            result = invoke(root, 'sbin/uci', ['-c', config, '-P', state, 'export', name])
            if 'package ' + name not in result.stdout:
                raise RuntimeError('UCI failed to export ' + name)
        checks['renderer_uci_parsing'] = ['network', 'dhcp', 'dropbear', 'firewall']
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
    checks['scope'] = 'Userspace execution only: no SSH listener, DHCP daemon, init, mounts, or network changes'
    checks['kernel_and_hardware_tested'] = False
    (output / 'management-checks.json').write_text(json.dumps(checks, indent=2) + '\n')
    print(json.dumps(checks, indent=2))


if __name__ == '__main__':
    check(Path(sys.argv[1]), Path(sys.argv[2]))
