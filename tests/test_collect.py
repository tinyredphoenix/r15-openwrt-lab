import importlib.util
import io
from pathlib import Path
import struct
import tarfile
import tempfile
import unittest

spec = importlib.util.spec_from_file_location('collector', Path(__file__).parents[1] / 'build/collect-userspace.py')
m = importlib.util.module_from_spec(spec)
spec.loader.exec_module(m)

class CollectorTests(unittest.TestCase):
    def test_closure_excludes_unrequested_packages_and_resolves_abi_aliases(self):
        packages = {'wpad': {'Depends': 'libc, libubus (>= 1)'},
                    'libc': {}, 'libubus20210630': {'Provides': 'libubus', 'Depends': 'libc'},
                    'openssl': {}}
        self.assertEqual(m.dependency_closure(packages, ['wpad']),
                         {'wpad', 'libc', 'libubus20210630'})

    def test_missing_dependency_prevents_incomplete_artifact(self):
        with self.assertRaisesRegex(ValueError, 'Missing runtime dependency'):
            m.dependency_closure({'wpad': {'Depends': 'missing-lib'}}, ['wpad'])

    def test_foreign_or_truncated_elf_rejected(self):
        data = bytearray(52)
        data[:6] = b'\x7fELF\x01\x02'
        struct.pack_into('>H', data, 18, 8)
        self.assertEqual(m.inspect_elf(data)['byte_order'], 'big')
        for bad in [data[:20], bytes(data[:5]) + b'\x01' + bytes(data[6:]), b'\x7fELF\x02' + bytes(data[5:])]:
            with self.assertRaises(ValueError): m.inspect_elf(bad)

    def test_traversal_is_rejected(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp).resolve()
            for path in ['../secret', '/etc/password', 'lib/../../secret']:
                with self.assertRaises(ValueError): m.safe_path(root, path)

    def test_absolute_library_link_is_relocated_inside_root(self):
        stream = io.BytesIO()
        with tarfile.open(fileobj=stream, mode='w') as tar:
            file = tarfile.TarInfo('lib/libc.so'); file.size=3
            tar.addfile(file, io.BytesIO(b'abc'))
            link = tarfile.TarInfo('lib/ld-musl-mips-sf.so.1')
            link.type=tarfile.SYMTYPE; link.linkname='/lib/libc.so'
            tar.addfile(link)
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp).resolve(); m.unpack_data(stream.getvalue(), root)
            self.assertEqual((root / 'lib/ld-musl-mips-sf.so.1').read_bytes(), b'abc')
            self.assertTrue((root / 'lib/ld-musl-mips-sf.so.1').resolve().is_relative_to(root))

    def test_escape_symlink_is_rejected(self):
        stream=io.BytesIO()
        with tarfile.open(fileobj=stream,mode='w') as tar:
            link=tarfile.TarInfo('lib/escape'); link.type=tarfile.SYMTYPE; link.linkname='../../outside'
            tar.addfile(link)
        with tempfile.TemporaryDirectory() as tmp:
            with self.assertRaises(ValueError): m.unpack_data(stream.getvalue(),Path(tmp))

if __name__ == '__main__': unittest.main()
