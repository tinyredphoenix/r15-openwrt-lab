"""Stage a hash-pinned subset of generic OpenWrt service shell helpers.

Never install SDK board files, boot entrypoints, wireless scripts or upgraders.
Source files retain their upstream OpenWrt licensing.
"""
import hashlib
import json
from pathlib import Path
import sys

MANIFEST = Path(__file__).with_name('common-runtime-manifest.json')
RUNTIME_PATH = '/usr/sbin:/usr/bin:/sbin:/bin'


def stage(source, root):
    source = source.resolve()
    root = root.resolve()
    manifest = json.loads(MANIFEST.read_text())
    prepared = []
    for record in manifest['files']:
        name = record['path']
        incoming, target = source / name, root / name
        if incoming.is_symlink() or not incoming.resolve().is_relative_to(source):
            raise ValueError('Linked or escaping helper source: ' + name)
        data = incoming.read_bytes()
        if hashlib.sha256(data).hexdigest() != record['sha256']:
            raise ValueError('Helper source checksum mismatch: ' + name)
        if target.exists() or target.is_symlink():
            raise ValueError('Refusing helper collision: ' + name)
        if not target.parent.resolve().is_relative_to(root):
            raise ValueError('Helper destination escapes root: ' + name)
        if name == 'sbin/hotplug-call':
            if data.count(b'%PATH%') != 1:
                raise ValueError('Unexpected hotplug PATH template')
            data = data.replace(b'%PATH%', RUNTIME_PATH.encode())
        if b'%PATH%' in data:
            raise ValueError('Unresolved helper template: ' + name)
        prepared.append((target, data, {**record, 'installed_sha256': hashlib.sha256(data).hexdigest()}))
    for target, data, _ in prepared:
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_bytes(data)
        target.chmod(0o755 if target.relative_to(root).as_posix() in
                     ('etc/rc.common', 'sbin/hotplug-call', 'bin/ipcalc.sh') else 0o644)
    return {'commit': manifest['commit'], 'files': [record for _, _, record in prepared],
            'hotplug_path': RUNTIME_PATH, 'boot_framework_complete': False}


if __name__ == '__main__':
    source, root, report_path = map(Path, sys.argv[1:])
    report = stage(source, root)
    report_path.write_text(json.dumps(report, indent=2) + '\n')
