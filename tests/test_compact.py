import hashlib
import importlib.util
import json
from pathlib import Path
import tempfile
import unittest

spec = importlib.util.spec_from_file_location('compact', Path(__file__).parents[1] / 'build/compact-runtime.py')
m = importlib.util.module_from_spec(spec)
spec.loader.exec_module(m)


class CompactTests(unittest.TestCase):
    def fixture(self, root):
        source = root / 'source'; source.mkdir()
        names = [*m.REQUIRED, 'packages/example.ipk', 'sources/large.tar.gz']
        for name in names:
            path = source / name; path.parent.mkdir(parents=True, exist_ok=True); path.write_bytes(b'fixture')
        (source / 'build-report.json').write_text(json.dumps({'flashable': False, 'hardware_tested': False}))
        (source / 'SHA256SUMS').write_text(''.join(hashlib.sha256((source / n).read_bytes()).hexdigest()+'  ./'+n+'\n' for n in names))
        return source

    def test_only_verified_runtime_is_copied_with_traceable_provenance(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp); source = self.fixture(root); out = root / 'out'
            result = m.compact(source, out, '123', 'a'*40)
            self.assertIs(result['flashable'], False)
            self.assertFalse((out / 'sources').exists())
            self.assertEqual(json.loads((out / 'PROVENANCE.json').read_text())['source_run'], 123)
            for line in (out / 'SHA256SUMS').read_text().splitlines():
                digest, name = line.split(maxsplit=1)
                self.assertEqual(hashlib.sha256((out/name).read_bytes()).hexdigest(), digest)

    def test_corruption_prevents_output_creation(self):
        with tempfile.TemporaryDirectory() as tmp:
            root=Path(tmp); source=self.fixture(root); (source/'userspace-research.tar.gz').write_bytes(b'corrupt')
            with self.assertRaisesRegex(ValueError, 'checksum mismatch'): m.compact(source,root/'out','123','a'*40)
            self.assertFalse((root/'out').exists())

    def test_linked_runtime_file_is_rejected(self):
        with tempfile.TemporaryDirectory() as tmp:
            root=Path(tmp); source=self.fixture(root); target=source/'pins.env';target.unlink();target.symlink_to(source/'sdk.config')
            with self.assertRaisesRegex(ValueError, 'linked runtime'):m.compact(source,root/'out','123','a'*40)

    def test_manifest_traversal_is_rejected(self):
        with tempfile.TemporaryDirectory() as tmp:
            root=Path(tmp);source=self.fixture(root)
            with (source/'SHA256SUMS').open('a') as out:out.write('a'*64+'  ../outside\n')
            with self.assertRaisesRegex(ValueError, 'Unsafe'):m.compact(source,root/'out','123','a'*40)
