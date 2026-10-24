import copy
import hashlib
import importlib.util
from pathlib import Path
import struct
import unittest
from unittest.mock import patch
import zlib

spec = importlib.util.spec_from_file_location('candidate', Path(__file__).parents[1]/'build/inspect-r15-candidate.py')
m = importlib.util.module_from_spec(spec); spec.loader.exec_module(m)


def fixture():
    payload = b'synthetic kernel; not bootable'
    header = bytearray(struct.pack('>7I4B32s', 0x27051956, 0, 0, len(payload), 0x80010000, 0x80010000,
                                   zlib.crc32(payload), 5, 5, 2, 1, b'fixture'))
    struct.pack_into('>I', header, 4, zlib.crc32(header))
    kernel = bytes(header)+payload
    root = struct.pack('<5I6H8Q', 0x73717368, 1, 0, 131072, 0, 4, 17, 0, 1, 4, 0,
                       0, 128, 100, 0xffffffffffffffff, 100, 110, 0xffffffffffffffff, 0xffffffffffffffff)+bytes(32)
    parts = [{'mtd': 5, 'name': 'ubi_device', 'bytes': 129105920, 'erase_bytes': 131072}]
    lines = ['/sys/class/ubi/ubi0/mtd_num=5', '/sys/class/ubi/ubi0/min_io_size=2048']
    for bank in range(2):
        for prefix, slot, blocks in [('ubi_k', 8+2*bank, 83), ('ubi_r', 9+2*bank, 290)]:
            name = prefix+str(bank)
            parts.append({'mtd': slot, 'name': name, 'bytes': blocks*126976, 'erase_bytes': 126976})
            for key, value in {'name': name, 'type': 'dynamic', 'reserved_ebs': blocks,
                               'usable_eb_size': 126976, 'data_bytes': blocks*126976,
                               'upd_marker': 0, 'corrupted': 0}.items():
                lines.append('/sys/class/ubi/ubi0_'+str(slot-7)+'/'+key+'='+str(value))
    inv = {'flash': {'partitions': parts, 'page_bytes': 2048, 'erase_bytes': 131072},
           'boot': {'cmdline': 'console=ttyS0 ubi.mtd=5 root=31:9 rootfs=squashfs',
                    'active_rootfs_mtd': 9, 'active_rootfs_volume': 'ubi_r0', 'active_kernel_volume': 'ubi_k0'}}
    return inv, '\n'.join(lines), kernel, root


class CandidateTests(unittest.TestCase):
    def setUp(self):
        self.args = fixture()
        self.pin = patch.object(m, 'STOCK_KERNEL_SHA256', hashlib.sha256(self.args[2]).hexdigest())
        self.pin.start(); self.addCleanup(self.pin.stop)

    def reject(self, args):
        with self.assertRaises((ValueError, KeyError)):
            m.inspect(*args)

    def test_offline_report_never_authorizes_writes(self):
        report = m.inspect(*self.args)
        self.assertEqual([t['name'] for t in report['targets']], ['ubi_k1', 'ubi_r1'])
        for key in ('flashable', 'raw_nand_write_allowed', 'ubi_container_reformat_allowed', 'boot_environment_write_allowed'):
            self.assertIs(report[key], False)
        self.assertIn('ubi_device', report['forbidden_targets'])
        self.assertIn('ubi_r0', report['forbidden_targets'])

    def test_bank_one_selects_only_bank_zero(self):
        args = list(copy.deepcopy(self.args)); b = args[0]['boot']
        b.update(cmdline='ubi.mtd=5 root=31:11', active_rootfs_mtd=11,
                 active_rootfs_volume='ubi_r1', active_kernel_volume='ubi_k1')
        self.assertEqual([t['name'] for t in m.inspect(*args)['targets']], ['ubi_k0', 'ubi_r0'])

    def test_ambiguous_or_disagreeing_bank_rejected(self):
        for value in ('ubi.mtd=5 root=31:9 root=31:11', 'ubi.mtd=6 root=31:9', 'ubi.mtd=5 root=31:11'):
            args = list(copy.deepcopy(self.args)); args[0]['boot']['cmdline'] = value; self.reject(args)

    def test_corrupt_or_in_progress_ubi_rejected(self):
        for old, new in [('/corrupted=0', '/corrupted=1'), ('/upd_marker=0', '/upd_marker=1'), ('/type=dynamic', '/type=static')]:
            args = list(self.args); args[1] = args[1].replace(old, new); self.reject(args)

    def test_duplicate_ubi_or_mtd_rejected(self):
        args = list(self.args); args[1] += '\n/sys/class/ubi/ubi0/mtd_num=5'; self.reject(args)
        args = list(copy.deepcopy(self.args)); args[0]['flash']['partitions'].append(args[0]['flash']['partitions'][0]); self.reject(args)

    def test_ubi_geometry_disagreement_rejected(self):
        for old, new in [('/reserved_ebs=83', '/reserved_ebs=84'), ('/usable_eb_size=126976', '/usable_eb_size=131072')]:
            args = list(self.args); args[1] = args[1].replace(old, new); self.reject(args)

    def test_kernel_corruption_or_substitution_rejected(self):
        args = list(self.args); args[2] = args[2][:-1]+b'x'; self.reject(args)
        with patch.object(m, 'STOCK_KERNEL_SHA256', '0'*64): self.reject(self.args)
        args = list(self.args); args[2] += b'padding'; self.reject(args)

    def test_kernel_read_limit_enforced(self):
        with self.assertRaises(ValueError): m.kernel_info(bytes(m.KERNEL_READ_LIMIT+1))

    def test_wrong_squashfs_version_compressor_or_tables_rejected(self):
        for offset, fmt, value in [(0, '<I', 0), (20, '<H', 1), (28, '<H', 3), (40, '<Q', 999), (64, '<Q', 999)]:
            args = list(self.args); root = bytearray(args[3]); struct.pack_into(fmt, root, offset, value)
            args[3] = bytes(root); self.reject(args)

    def test_rootfs_capacity_and_trailing_data_rejected(self):
        args = list(self.args); args[3] += b'non-padding'; self.reject(args)
        args = list(self.args); args[3] += bytes(36823040); self.reject(args)

if __name__ == '__main__': unittest.main()
