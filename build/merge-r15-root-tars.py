"""Merge a stock root tar and a private rootfs/ runtime under opt/r15-openwrt.

Tar-to-tar only: never extracts members, follows links, or installs a boot hook.
The resulting filesystem seed preserves stock startup and is not flashable.
"""
import argparse
import copy
import hashlib
import json
from pathlib import Path, PurePosixPath
import tarfile

PREFIX = 'opt/r15-openwrt'
MAX_EXPANDED = 256 * 1024 * 1024


def canonical(name):
    while name.startswith('./'):
        name = name[2:]
    if name in ('', '.'):
        return '.'
    path = PurePosixPath(name)
    if path.is_absolute() or '..' in path.parts or '\x00' in name:
        raise ValueError('Unsafe tar path')
    return path.as_posix()


def merge(stock, runtime, output):
    if output.exists():
        raise ValueError('Refusing to replace output')
    seen = set(); counts = {'stock': 0, 'runtime': 0}; expanded = 0; created = False
    try:
        with output.open('xb') as stream:
            created = True
            output.chmod(0o600)
            with tarfile.open(fileobj=stream, mode='w', format=tarfile.PAX_FORMAT) as target:
                with tarfile.open(stock, 'r:*') as archive:
                    for member in archive:
                        name = canonical(member.name)
                        if name in seen or name == PREFIX or name.startswith(PREFIX+'/'):
                            raise ValueError('Stock duplicate or runtime namespace collision')
                        if name == 'opt' and not member.isdir():
                            raise ValueError('Stock opt is not a directory')
                        seen.add(name); expanded += member.size
                        if expanded > MAX_EXPANDED:
                            raise ValueError('Expanded archive limit exceeded')
                        target.addfile(member, archive.extractfile(member) if member.isfile() else None)
                        counts['stock'] += 1
                with tarfile.open(runtime, 'r:*') as archive:
                    runtime_seen = set()
                    for original in archive:
                        source = canonical(original.name)
                        if source != 'rootfs' and not source.startswith('rootfs/'):
                            continue
                        if source in runtime_seen:
                            raise ValueError('Duplicate runtime member')
                        runtime_seen.add(source)
                        if original.uid != 0 or original.gid != 0:
                            raise ValueError('Runtime ownership must be explicitly root/root')
                        if not (original.isfile() or original.isdir() or original.issym() or original.islnk()):
                            raise ValueError('Unexpected runtime special file')
                        member = copy.copy(original)
                        suffix = source.removeprefix('rootfs').lstrip('/')
                        member.name = PREFIX+('/'+suffix if suffix else '')
                        member.pax_headers = dict(member.pax_headers)
                        member.pax_headers.pop('path', None); member.pax_headers.pop('linkpath', None)
                        if member.islnk():
                            link = canonical(member.linkname)
                            if not link.startswith('rootfs/'):
                                raise ValueError('Runtime hard link escapes rootfs')
                            member.linkname = PREFIX+'/'+link[len('rootfs/'):]
                        expanded += member.size
                        if expanded > MAX_EXPANDED:
                            raise ValueError('Expanded archive limit exceeded')
                        target.addfile(member, archive.extractfile(original) if member.isfile() else None)
                        counts['runtime'] += 1
                    if 'rootfs' not in runtime_seen or counts['runtime'] < 2:
                        raise ValueError('Runtime rootfs tree missing')
    except BaseException:
        if created: output.unlink(missing_ok=True)
        raise
    with output.open('rb') as stream:
        digest = hashlib.file_digest(stream, 'sha256').hexdigest()
    return {'scope': 'Private stock-startup filesystem seed with nested OpenWrt userspace',
            'counts': counts, 'expanded_regular_bytes': expanded,
            'output_sha256': digest,
            'runtime_prefix': PREFIX, 'stock_startup_changed': False,
            'automatic_runtime_start': False, 'flashable': False}


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('stock', type=Path); parser.add_argument('runtime', type=Path); parser.add_argument('output', type=Path)
    args = parser.parse_args()
    print(json.dumps(merge(args.stock, args.runtime, args.output), indent=2))

if __name__ == '__main__': main()
