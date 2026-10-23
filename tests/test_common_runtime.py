import hashlib
import importlib.util
import json
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch

spec = importlib.util.spec_from_file_location('common', Path(__file__).parents[1] / 'build/stage-common-runtime.py')
common = importlib.util.module_from_spec(spec)
spec.loader.exec_module(common)


class CommonRuntimeTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.base = Path(self.tmp.name)
        self.source, self.root = self.base / 'source', self.base / 'root'
        self.source.mkdir(); self.root.mkdir()
        (self.source / 'sbin').mkdir()
        self.data = b'#!/bin/sh\nPATH="%PATH%"\n'
        (self.source / 'sbin/hotplug-call').write_bytes(self.data)
        manifest = self.base / 'manifest.json'
        manifest.write_text(json.dumps({'commit': 'test', 'files': [
            {'path': 'sbin/hotplug-call', 'sha256': hashlib.sha256(self.data).hexdigest()}]}))
        self.patcher = patch.object(common, 'MANIFEST', manifest)
        self.patcher.start(); self.addCleanup(self.patcher.stop)

    def test_resolves_path_and_records_transformation(self):
        result = common.stage(self.source, self.root)
        data = (self.root / 'sbin/hotplug-call').read_bytes()
        self.assertNotIn(b'%PATH%', data)
        self.assertIn(common.RUNTIME_PATH.encode(), data)
        self.assertEqual(result['files'][0]['installed_sha256'], hashlib.sha256(data).hexdigest())
        self.assertFalse(result['boot_framework_complete'])

    def test_changed_source_rejected_before_writing(self):
        (self.source / 'sbin/hotplug-call').write_text('changed')
        with self.assertRaisesRegex(ValueError, 'checksum'):
            common.stage(self.source, self.root)
        self.assertEqual(list(self.root.iterdir()), [])

    def test_existing_destination_rejected(self):
        (self.root / 'sbin').mkdir()
        (self.root / 'sbin/hotplug-call').write_text('keep')
        with self.assertRaisesRegex(ValueError, 'collision'):
            common.stage(self.source, self.root)
        self.assertEqual((self.root / 'sbin/hotplug-call').read_text(), 'keep')

    def test_escaping_destination_rejected(self):
        (self.root / 'sbin').symlink_to(self.source / 'sbin', target_is_directory=True)
        # The destination is already present through the link and must be refused.
        with self.assertRaises(ValueError):
            common.stage(self.source, self.root)
