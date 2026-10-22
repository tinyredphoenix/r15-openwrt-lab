"""Collect compiled research IPKs; reject foreign ELFs and unsafe archive paths."""
import hashlib
import io
import json
import os
from pathlib import Path, PurePosixPath
import shutil
import struct
import sys
import tarfile


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
    for package in sorted((sdk / 'bin').rglob('*.ipk')):
        if package.name.startswith(('kmod-', 'kernel_')):
            continue
        digest = hashlib.sha256(package.read_bytes()).hexdigest()
        if package.name in seen:
            if seen[package.name] != digest:
                raise ValueError('Conflicting package: ' + package.name)
            continue
        seen[package.name] = digest
        shutil.copyfile(package, packages / package.name)
        unpack_data(ipk_payload(package), root)
        records.append({'name': package.name, 'bytes': package.stat().st_size, 'sha256': digest})
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
    result = {'flashable': False, 'hardware_tested': False,
              'scope': 'Wireless userspace tools only; no kernel or board image',
              'sdk_target': 'realtek/generic', 'package_architecture': 'mips_4kec',
              'soc_compatibility': 'ISA candidate for RTL8198D; driver/runtime compatibility unverified',
              'association_patch_marker_present': True, 'packages': records, 'elf_files': elf}
    (output / 'build-report.json').write_text(json.dumps(result, indent=2) + '\n')
    print(json.dumps({'packages': len(records), 'mips_elf_files': len(elf), 'flashable': False}))


if __name__ == '__main__':
    collect(Path(sys.argv[1]).resolve(), Path(sys.argv[2]).resolve())
