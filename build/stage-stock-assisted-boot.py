"""Create private tar inputs for a stock-assisted management boot experiment.

Preserves stock board startup and PID1, adding a background management hook.
No device operations, image authentication, boot validation or installer here.
"""
import argparse
import copy
import hashlib
import importlib.util
import io
import json
from pathlib import Path
import tarfile

STOCK_RCS_SHA256 = '2befa393864a56082be9d98335d1c19155bb15057dba591be25b573fad4de5cf'
HOOK = (b'\n# R15 experimental management; OEM board initialization remains below.\n'
        b'(/bin/sh /opt/r15-openwrt/usr/libexec/r15-stock-management '
        b'/opt/r15-openwrt /run/r15-management 0 '
        b'> /run/r15-management-start.log 2>&1) &\ncommander\n')
HERE = Path(__file__).resolve().parent
spec = importlib.util.spec_from_file_location('merge_root', HERE/'merge-r15-root-tars.py')
merger = importlib.util.module_from_spec(spec); spec.loader.exec_module(merger)


def stage(stock, runtime, host_key, output):
    if output.exists(): raise ValueError('Refusing to overwrite boot stage')
    if host_key.is_symlink() or not host_key.is_file() or host_key.stat().st_mode & 0o077:
        raise ValueError('Host key must be a private regular file')
    secret = host_key.read_bytes()
    if not 32 <= len(secret) <= 16384:
        raise ValueError('Unexpected private host key size')
    runtime_dir = HERE.parent/'prototype/runtime'
    additions = {'rootfs/usr/libexec/'+name: (runtime_dir/name).read_bytes()
                 for name in ('r15-stock-management', 'r15-session-lifecycle.sh', 'r15-caplog.lua', 'r15-network-handoff')}
    additions['rootfs/etc/dropbear/dropbear_ed25519_host_key'] = secret
    output.mkdir(mode=0o700)
    changed = []; owner_key = False
    with tarfile.open(stock, 'r:*') as incoming, tarfile.open(output/'stock-with-hook.tar', 'w', format=tarfile.PAX_FORMAT) as target:
        for original in incoming:
            member = copy.copy(original)
            if merger.canonical(member.name) == 'usr/etc/rcS':
                if not member.isfile(): raise ValueError('Stock rcS is not a regular file')
                data = incoming.extractfile(original).read()
                if hashlib.sha256(data).hexdigest() != STOCK_RCS_SHA256 or data.count(b'\ncommander\n') != 1:
                    raise ValueError('Stock startup does not match the pinned R15 1.06.10 script')
                data = data.replace(b'\ncommander\n', HOOK)
                member.size = len(data); member.pax_headers = dict(member.pax_headers); member.pax_headers.pop('size', None)
                target.addfile(member, io.BytesIO(data)); changed.append('usr/etc/rcS')
            else:
                target.addfile(member, incoming.extractfile(original) if member.isfile() else None)
    if changed != ['usr/etc/rcS']: raise ValueError('Expected one stock startup entry')
    with tarfile.open(runtime, 'r:*') as incoming, tarfile.open(output/'runtime-with-bootstrap.tar', 'w', format=tarfile.PAX_FORMAT) as target:
        for member in incoming:
            name = merger.canonical(member.name)
            if name == 'rootfs/etc/dropbear/authorized_keys':
                if not member.isfile() or not 32 <= member.size <= 65536: raise ValueError('Missing owner SSH key')
                owner_key = True
            if name not in additions:
                target.addfile(member, incoming.extractfile(member) if member.isfile() else None)
        for name, data in additions.items():
            member = tarfile.TarInfo(name); member.size = len(data); member.uid = member.gid = member.mtime = 0
            member.mode = 0o600 if name.endswith('host_key') else 0o755
            target.addfile(member, io.BytesIO(data))
    if not owner_key: raise ValueError('No owner SSH authorization in private runtime')
    merged = merger.merge(output/'stock-with-hook.tar', output/'runtime-with-bootstrap.tar', output/'merged-root.tar')
    result = {'scope': 'Private stock-assisted management boot candidate tar; not full management takeover',
              'stock_files_changed': changed, 'stock_pid1_retained': True, 'oem_board_startup_retained': True,
              'automatic_management_hook': True, 'radio_takeover': False,
              'management': {'address': '192.168.77.1/24', 'ssh_port': 2222, 'https_port': 8443,
                             'ssh': 'owner key only; unit-specific host key', 'configuration': 'volatile RAM copy'},
              'bootstrap_source_sha256': hashlib.sha256(additions['rootfs/usr/libexec/r15-stock-management']).hexdigest(),
              'merge': merged, 'kernel_boot_tested': False, 'flashable': False,
              'remaining': ['Cold startup timing and management checks', 'Boot acknowledgement/rollback before trial selection',
                            'Image/installer validation and inactive-bank staging', 'Full radio management takeover and persistent settings']}
    for path in output.iterdir(): path.chmod(0o600)
    (output/'STAGE.json').write_text(json.dumps(result, indent=2)+'\n'); (output/'STAGE.json').chmod(0o600)
    return result

if __name__ == '__main__':
    p=argparse.ArgumentParser(description=__doc__)
    for name in ('stock', 'runtime', 'host-key', 'output'): p.add_argument('--'+name, type=Path, required=True)
    a=p.parse_args(); print(json.dumps(stage(a.stock,a.runtime,a.host_key,a.output),indent=2))
