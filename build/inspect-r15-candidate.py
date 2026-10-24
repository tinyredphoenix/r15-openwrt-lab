"""Inspect retained-kernel R15 volume candidates offline; never write a device.

Checks are structural and refer to an historical inventory. They do not establish
boot, signatures, recovery, calibration, or permission to install an image.
"""
import argparse
import hashlib
import json
from pathlib import Path
import re
import struct
import sys
import zlib

STOCK_KERNEL_SHA256 = 'cd43f6c7dbdff5bda8da896380b8b7bfa66e85ba5af6e1601d99d9096b39fcd9'
KERNEL_READ_LIMIT = 0x600000
LEB_BYTES = 126976
MAX_INPUT = 40 * 1024 * 1024


def kernel_info(data):
    if len(data) < 64 or len(data) > KERNEL_READ_LIMIT:
        raise ValueError('Kernel exceeds captured bootloader read limit or is truncated')
    magic, hcrc, stamp, size, load, entry, dcrc, os_id, arch, kind, comp, name = struct.unpack('>7I4B32s', data[:64])
    if magic != 0x27051956 or (os_id, arch, kind, comp) != (5, 5, 2, 1):
        raise ValueError('Expected Linux/MIPS/kernel/gzip legacy uImage')
    header = bytearray(data[:64]); header[4:8] = bytes(4)
    if zlib.crc32(header) != hcrc or size != len(data) - 64 or zlib.crc32(data[64:]) != dcrc:
        raise ValueError('Kernel header/data CRC or payload length mismatch')
    digest = hashlib.sha256(data).hexdigest()
    if digest != STOCK_KERNEL_SHA256:
        raise ValueError('This route requires the exact qualified OEM kernel')
    return {'bytes': len(data), 'sha256': digest, 'header_crc': 'pass', 'data_crc': 'pass',
            'load_address': hex(load), 'entry_address': hex(entry), 'bootloader_read_limit': KERNEL_READ_LIMIT}


def rootfs_info(data):
    if len(data) < 96 or len(data) > MAX_INPUT:
        raise ValueError('Truncated or oversized root filesystem')
    fields = struct.unpack('<5I6H8Q', data[:96])
    magic, inodes, stamp, block_size, fragments = fields[:5]
    compression, block_log, flags, ids, major, minor = fields[5:11]
    root_inode, used, id_table, xattr_table, inode_table, directory_table, fragment_table, lookup_table = fields[11:]
    if magic != 0x73717368 or (major, minor) != (4, 0):
        raise ValueError('Expected little-endian SquashFS 4.0')
    if compression != 4 or block_size != 131072 or block_log != 17:
        raise ValueError('Use the observed XZ/128 KiB SquashFS format')
    if not inodes or not ids or not 96 <= used <= len(data):
        raise ValueError('Invalid SquashFS counts or bytes_used')
    for value in (id_table, xattr_table, inode_table, directory_table, fragment_table, lookup_table):
        if value != 0xffffffffffffffff and not 96 <= value < used:
            raise ValueError('SquashFS table lies outside bytes_used')
    if any(byte not in (0, 255) for byte in data[used:]):
        raise ValueError('Unexpected data after the SquashFS filesystem')
    return {'bytes': len(data), 'bytes_used': used, 'sha256': hashlib.sha256(data).hexdigest(),
            'compression': 'xz', 'block_bytes': block_size,
            'scope': 'Superblock bounds only; complete filesystem walk and boot remain required'}


def parse_ubi(text):
    devices = {}
    for line in text.splitlines():
        match = re.fullmatch(r'/sys/class/ubi/(ubi0(?:_[0-9]+)?)/([a-z_]+)=([^\r\n]+)', line)
        if not match:
            continue
        device, field, value = match.groups()
        record = devices.setdefault(device, {})
        if field in record:
            raise ValueError('Duplicate UBI observation')
        record[field] = value
    return devices


def inspect(inventory, ubi_text, kernel, rootfs):
    parts = inventory['flash']['partitions']
    indexed = {p['mtd']: p for p in parts}
    if len(indexed) != len(parts):
        raise ValueError('Duplicate MTD identity')
    expected = {5: 'ubi_device', 8: 'ubi_k0', 9: 'ubi_r0', 10: 'ubi_k1', 11: 'ubi_r1'}
    if any(indexed.get(n, {}).get('name') != name for n, name in expected.items()):
        raise ValueError('Inventory does not match the observed R15 bank mapping')
    if inventory['flash']['page_bytes'] != 2048 or inventory['flash']['erase_bytes'] != 131072:
        raise ValueError('Unexpected physical NAND geometry')
    cmdline = inventory['boot']['cmdline']
    roots = re.findall(r'(?:^|\s)root=31:(\d+)(?=\s|$)', cmdline)
    parents = re.findall(r'(?:^|\s)ubi.mtd=(\d+)(?=\s|$)', cmdline)
    if len(roots) != 1 or roots[0] not in ('9', '11') or parents != ['5']:
        raise ValueError('Unrecognized or ambiguous captured boot arguments')
    active = 0 if roots[0] == '9' else 1
    boot = inventory['boot']
    if (boot['active_rootfs_mtd'], boot['active_rootfs_volume'], boot['active_kernel_volume']) != (int(roots[0]), 'ubi_r'+str(active), 'ubi_k'+str(active)):
        raise ValueError('Captured active bank fields disagree')
    ubi = parse_ubi(ubi_text)
    if ubi.get('ubi0', {}).get('mtd_num') != '5' or ubi['ubi0'].get('min_io_size') != '2048':
        raise ValueError('UBI parent identity or minimum I/O does not match')
    target = 1 - active
    images = {'kernel': kernel_info(kernel), 'rootfs': rootfs_info(rootfs)}
    targets = []
    for label, prefix, mtd in [('kernel', 'ubi_k', 8+2*target), ('rootfs', 'ubi_r', 9+2*target)]:
        name = prefix+str(target)
        matches = [(dev, record) for dev, record in ubi.items() if record.get('name') == name]
        if len(matches) != 1:
            raise ValueError('Missing or ambiguous target UBI volume: '+name)
        dev, record = matches[0]
        capacity = int(record['reserved_ebs']) * int(record['usable_eb_size'])
        if (record.get('type'), record.get('upd_marker'), record.get('corrupted')) != ('dynamic', '0', '0'):
            raise ValueError('Target volume is damaged, updating, or unexpected type')
        if int(record['usable_eb_size']) != LEB_BYTES or capacity != indexed[mtd]['bytes'] or int(record['data_bytes']) != capacity:
            raise ValueError('UBI/MTD capacity observations disagree')
        if indexed[mtd]['erase_bytes'] != LEB_BYTES or images[label]['bytes'] > capacity:
            raise ValueError('Image exceeds target logical capacity or LEB mismatch')
        targets.append({'image': label, 'name': name, 'observed_volume': dev, 'capacity_bytes': capacity,
                        'image_bytes': images[label]['bytes'], 'unused_bytes': capacity-images[label]['bytes']})
    return {'scope': 'Offline structural candidate and historical inactive-bank mapping only',
            'active_bank_observed': active, 'inactive_bank_observed': target, 'targets': targets, 'images': images,
            'forbidden_targets': [p['name'] for p in parts if p['name'] not in {t['name'] for t in targets}],
            'ubi_container_reformat_allowed': False, 'raw_nand_write_allowed': False,
            'boot_environment_write_allowed': False, 'image_packaging_validated': False,
            'custom_boot_validated': False, 'flashable': False,
            'remaining': ['Fresh device identity/bank recheck before any future installer',
                          'Full filesystem integrity and custom board/service startup',
                          'Per-unit data preservation, boot acknowledgement and watchdog contract',
                          'Accepted update packaging and independent recovery qualification',
                          'UBI update interruption/recovery and bank selection qualification']}


def bounded(path):
    with path.open('rb') as stream:
        data = stream.read(MAX_INPUT+1)
    if len(data) > MAX_INPUT:
        raise ValueError('Input exceeds bounded candidate size')
    return data


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    for name in ('inventory', 'ubi', 'kernel', 'rootfs'):
        parser.add_argument('--'+name, type=Path, required=True)
    args = parser.parse_args()
    try:
        report = inspect(json.loads(bounded(args.inventory)), bounded(args.ubi).decode(), bounded(args.kernel), bounded(args.rootfs))
    except (ValueError, KeyError, TypeError, OSError, struct.error) as error:
        print(json.dumps({'error': str(error), 'flashable': False}), file=sys.stderr)
        return 1
    print(json.dumps(report, indent=2))
    return 0

if __name__ == '__main__':
    sys.exit(main())
