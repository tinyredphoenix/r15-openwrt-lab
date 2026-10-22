"""Collect compiled research IPKs; reject foreign ELFs and unsafe archive paths."""
import hashlib
import io
import json
import os
import re
from email.parser import Parser
from pathlib import Path, PurePosixPath
import shutil
import struct
import sys
import tarfile

ROOT_PACKAGES = ['wpad-basic', 'wpa-cli', 'hostapd-utils', 'busybox', 'procd',
                 'ubox', 'logd', 'ubus', 'ubusd', 'uci', 'netifd', 'dropbear',
                 'dnsmasq', 'jsonfilter']

def safe_path(root, name):
    path = PurePosixPath(name)
    if path.is_absolute() or '..' in path.parts:
        raise ValueError('Unsafe package path: ' + name)
    dest = root.joinpath(*path.parts)
    if not dest.parent.resolve().is_relative_to(root.resolve()):
        raise ValueError('Package path escapes root: ' + name)
    return dest


def unpack_data(data, root):
    with tarfile.open(fileobj=io.BytesIO(data), mode='r:*') as archive:
        for member in archive:
            if member.name in ('.', './'):
                continue
            dest = safe_path(root, member.name)
            dest.parent.mkdir(parents=True, exist_ok=True)
            if member.isdir():
                dest.mkdir(exist_ok=True)
            elif member.isfile():
                if dest.is_symlink():
                    dest.unlink()
                dest.write_bytes(archive.extractfile(member).read())
                dest.chmod(member.mode & 0o777)
            elif member.issym():
                target = member.linkname
                linked = root / target.lstrip('/') if target.startswith('/') else dest.parent / target
                if not linked.resolve().is_relative_to(root.resolve()):
                    raise ValueError('Symlink escapes root: ' + member.name)
                if dest.exists() or dest.is_symlink():
                    dest.unlink()
                # Relocate absolute target links so QEMU and inspection stay inside root.
                dest.symlink_to(os.path.relpath(linked, dest.parent))
            else:
                raise ValueError('Unsupported package member: ' + member.name)


def ipk_payload(path):
    # OpenWrt 21.02's ipkg-build produces a gzipped outer tar archive.
    with tarfile.open(path, mode='r:*') as archive:
        for member in archive:
            if PurePosixPath(member.name).name in ('data.tar.gz', 'data.tar.xz'):
                return archive.extractfile(member).read()
    raise ValueError('No package payload: ' + str(path))


def ipk_metadata(path):
    with tarfile.open(path, mode='r:*') as outer:
        member = next(m for m in outer if PurePosixPath(m.name).name == 'control.tar.gz')
        payload = outer.extractfile(member).read()
    with tarfile.open(fileobj=io.BytesIO(payload), mode='r:*') as inner:
        member = next(m for m in inner if PurePosixPath(m.name).name == 'control')
        return dict(Parser().parsestr(inner.extractfile(member).read().decode()).items())


def dependency_closure(metadata, roots):
    providers = {name: name for name in metadata}
    for name, fields in metadata.items():
        for alias in fields.get('Provides', '').split(','):
            alias = alias.strip().split(' ')[0]
            if alias:
                providers.setdefault(alias, name)
    selected = set()
    pending = list(roots)
    while pending:
        requested = pending.pop()
        alternatives = [re.sub(r'\s*\([^)]*\)', '', p).strip() for p in requested.split('|')]
        name = next((providers[x] for x in alternatives if x in providers), None)
        if name is None:
            raise ValueError('Missing runtime dependency: ' + requested)
        if name in selected:
            continue
        selected.add(name)
        pending.extend(p.strip() for p in metadata[name].get('Depends', '').split(',') if p.strip())
    return selected


def inspect_elf(data):
    if not data.startswith(b'\x7fELF'):
        return None
    if len(data) < 52 or data[4] != 1 or data[5] != 2 or struct.unpack_from('>H', data, 18)[0] != 8:
        raise ValueError('Expected ELF32 big-endian MIPS')
    return {'class': 'ELF32', 'byte_order': 'big', 'machine': 'MIPS'}


def collect(sdk, output):
    root = output / 'rootfs'
    if root.exists():
        raise ValueError('Output rootfs already exists; use a clean artifact directory')
    root.mkdir(parents=True)
    packages = output / 'packages'
    packages.mkdir()
    records = []
    seen = {}
    available = {}
    metadata = {}
    for package in sorted((sdk / 'bin').rglob('*.ipk')):
        if package.name.startswith(('kmod-', 'kernel_')):
            continue
        digest = hashlib.sha256(package.read_bytes()).hexdigest()
        if package.name in seen:
            if seen[package.name] != digest:
                raise ValueError('Conflicting package: ' + package.name)
            continue
        seen[package.name] = digest
        fields = ipk_metadata(package)
        name = fields['Package']
        if name in available:
            raise ValueError('Multiple versions of package: ' + name)
        available[name] = package
        metadata[name] = fields
    selected = dependency_closure(metadata, ROOT_PACKAGES)
    for name in sorted(selected):
        package = available[name]
        digest = seen[package.name]
        shutil.copyfile(package, packages / package.name)
        unpack_data(ipk_payload(package), root)
        records.append({'name': package.name, 'bytes': package.stat().st_size, 'sha256': digest,
                        'license': metadata[name].get('License'),
                        'depends': metadata[name].get('Depends', '')})
    for prefix in ('wpad-basic_', 'wpa-cli_', 'hostapd-utils_', 'libc_'):
        if not any(p['name'].startswith(prefix) for p in records):
            raise ValueError('Missing compiled package: ' + prefix)
    elf = []
    for path in sorted(root.rglob('*')):
        if path.is_symlink() or not path.is_file():
            continue
        data = path.read_bytes()
        info = inspect_elf(data)
        if info:
            elf.append({'path': str(path.relative_to(root)), 'bytes': len(data), **info})
        if path.suffix == '.ko':
            raise ValueError('Kernel module unexpectedly present')
    wpad = root / 'usr/sbin/wpad'
    if b'rtl8192cd assoc-resp offload' not in wpad.read_bytes():
        raise ValueError('Association-response patch is absent from compiled wpad')
    # Retain exact downloaded source archives for inspecting/rebuilding dependencies.
    sources = output / 'sources'
    sources.mkdir()
    for path in sorted((sdk / 'dl').glob('*')):
        if path.is_file() and not path.name.startswith('.'):
            shutil.copyfile(path, sources / path.name)
    # Preserve distribution recipe/patch changes alongside upstream archives.
    # In particular, a BusyBox upstream tarball alone omits OpenWrt's patches.
    with tarfile.open(sources / 'openwrt-package-recipes.tar.gz', 'w:gz') as archive:
        archive.add(sdk / 'package', arcname='package')
    result = {'flashable': False, 'hardware_tested': False,
              'scope': 'Wireless and management userspace; no board boot integration or kernel',
              'sdk_target': 'realtek/generic', 'package_architecture': 'mips_4kec',
              'soc_compatibility': 'ISA candidate for RTL8198D; driver/runtime compatibility unverified',
              'association_patch_marker_present': True, 'packages': records, 'elf_files': elf}
    result['root_packages'] = ROOT_PACKAGES
    result['boot_framework_complete'] = False
    result['excluded_board_files'] = 'SDK base-files is intentionally excluded: it targets RTL838x switches, not R15'
    result['regular_file_bytes'] = sum(p.stat().st_size for p in root.rglob('*')
                                       if p.is_file() and not p.is_symlink())
    (output / 'build-report.json').write_text(json.dumps(result, indent=2) + '\n')
    print(json.dumps({'packages': len(records), 'mips_elf_files': len(elf), 'flashable': False}))


if __name__ == '__main__':
    collect(Path(sys.argv[1]).resolve(), Path(sys.argv[2]).resolve())
