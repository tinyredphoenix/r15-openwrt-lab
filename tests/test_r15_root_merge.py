import importlib.util
import io
from pathlib import Path
import tarfile
import tempfile
import unittest

spec = importlib.util.spec_from_file_location('merge', Path(__file__).parents[1]/'build/merge-r15-root-tars.py')
m = importlib.util.module_from_spec(spec); spec.loader.exec_module(m)


def archive(path, entries):
    with tarfile.open(path, 'w') as tar:
        for name, kind, data in entries:
            info = tarfile.TarInfo(name); info.type = kind; info.mode = 0o755
            if kind == tarfile.REGTYPE:
                info.size = len(data); tar.addfile(info, io.BytesIO(data))
            else:
                if kind in (tarfile.SYMTYPE, tarfile.LNKTYPE): info.linkname = data
                tar.addfile(info)


class MergeTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory(); self.addCleanup(self.tmp.cleanup)
        self.root = Path(self.tmp.name); self.stock = self.root/'stock.tar'; self.runtime = self.root/'runtime.tar'; self.out = self.root/'out.tar'
        self.stock_entries = [('usr/etc/rcS', tarfile.REGTYPE, b'unchanged startup'), ('sbin/init', tarfile.SYMTYPE, '/bin/busybox')]
        self.runtime_entries = [('rootfs', tarfile.DIRTYPE, ''), ('rootfs/bin/busybox', tarfile.REGTYPE, b'fixture'), ('rootfs/bin/ash', tarfile.SYMTYPE, 'busybox')]
        archive(self.stock, self.stock_entries); archive(self.runtime, self.runtime_entries)

    def test_preserves_startup_and_nests_runtime(self):
        result = m.merge(self.stock, self.runtime, self.out)
        self.assertFalse(result['flashable']); self.assertFalse(result['automatic_runtime_start'])
        with tarfile.open(self.out) as tar:
            self.assertEqual(tar.extractfile('usr/etc/rcS').read(), b'unchanged startup')
            self.assertEqual(tar.getmember('sbin/init').linkname, '/bin/busybox')
            self.assertEqual(tar.extractfile('opt/r15-openwrt/bin/busybox').read(), b'fixture')
            self.assertEqual(tar.getmember('opt/r15-openwrt/bin/ash').linkname, 'busybox')
        self.assertEqual(self.out.stat().st_mode & 0o777, 0o600)

    def test_protected_namespace_collision_rejected(self):
        for entry in [('opt', tarfile.SYMTYPE, '/tmp'), ('opt/r15-openwrt/a', tarfile.REGTYPE, b'x')]:
            archive(self.stock, self.stock_entries+[entry])
            with self.assertRaises(ValueError): m.merge(self.stock, self.runtime, self.out)
            self.assertFalse(self.out.exists())

    def test_path_escape_and_duplicate_rejected(self):
        for entries in [self.stock_entries+[('../escape', tarfile.REGTYPE, b'x')], self.stock_entries*2]:
            archive(self.stock, entries)
            with self.assertRaises(ValueError): m.merge(self.stock, self.runtime, self.out)
            self.assertFalse(self.out.exists())

    def test_existing_output_untouched(self):
        self.out.write_bytes(b'keep')
        with self.assertRaises(ValueError): m.merge(self.stock, self.runtime, self.out)
        self.assertEqual(self.out.read_bytes(), b'keep')

    def test_runtime_hard_link_retargeted_and_escape_rejected(self):
        archive(self.runtime, self.runtime_entries+[('rootfs/copy', tarfile.LNKTYPE, 'rootfs/bin/busybox')])
        m.merge(self.stock, self.runtime, self.out)
        with tarfile.open(self.out) as tar: self.assertEqual(tar.getmember('opt/r15-openwrt/copy').linkname, 'opt/r15-openwrt/bin/busybox')
        self.out.unlink()
        archive(self.runtime, self.runtime_entries+[('rootfs/copy', tarfile.LNKTYPE, 'usr/etc/rcS')])
        with self.assertRaises(ValueError): m.merge(self.stock, self.runtime, self.out)

    def test_missing_runtime_or_special_file_rejected(self):
        for entries in [[], self.runtime_entries+[('rootfs/dev/fake', tarfile.CHRTYPE, '')]]:
            archive(self.runtime, entries)
            with self.assertRaises(ValueError): m.merge(self.stock, self.runtime, self.out)

if __name__ == '__main__': unittest.main()
