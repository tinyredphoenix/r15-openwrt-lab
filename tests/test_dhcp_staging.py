"""Pin the DHCP delegate and reject unexpected staging paths/content."""
import hashlib
import importlib.util
import json
from pathlib import Path
import tempfile
import unittest

SCRIPT=Path(__file__).parents[1]/'build/stage-dhcp-guard.py'

class DhcpStagingTests(unittest.TestCase):
    def setUp(self):
        self.tmp=tempfile.TemporaryDirectory();self.addCleanup(self.tmp.cleanup)
        self.base=Path(self.tmp.name).resolve();self.root=self.base/'root';self.root.mkdir()
        spec=importlib.util.spec_from_file_location('dhcp_stage',SCRIPT)
        self.module=importlib.util.module_from_spec(spec);spec.loader.exec_module(self.module)
        self.repo=self.base/'repo';(self.repo/'build').mkdir(parents=True)
        self.runtime=self.repo/'prototype/runtime';self.runtime.mkdir(parents=True)
        for name in ('r15-subnet-check','r15-dhcp-guard','r15-dhcp.script'):
            (self.runtime/name).write_text('#!/bin/sh\n# inert '+name+'\n')
        self.original=self.root/'lib/netifd/dhcp.script';self.original.parent.mkdir(parents=True)
        self.payload=b'#!/bin/sh\n# inert original protocol fixture\n';self.original.write_bytes(self.payload)
        (self.repo/'build/dhcp-script-manifest.json').write_text(json.dumps({
            'path':'lib/netifd/dhcp.script','sha256':hashlib.sha256(self.payload).hexdigest()}))
        self.module.REPO=self.repo
        self.report=self.base/'report.json'

    def stage(self):return self.module.stage(self.root,self.report)

    def test_staging_preserves_exact_base_and_is_repeatable(self):
        self.stage();self.stage()
        self.assertEqual((self.root/'usr/libexec/r15-openwrt-dhcp.script').read_bytes(),self.payload)
        self.assertEqual(self.original.read_bytes(),(self.runtime/'r15-dhcp.script').read_bytes())
        self.assertFalse(json.loads(self.report.read_text())['executed'])

    def test_unexpected_base_is_rejected_without_overwrite(self):
        self.original.write_text('unexpected')
        with self.assertRaises(ValueError):self.stage()
        self.assertEqual(self.original.read_text(),'unexpected')
        self.assertFalse((self.root/'usr/libexec').exists())

    def test_modified_saved_delegate_is_rejected(self):
        self.stage();(self.root/'usr/libexec/r15-openwrt-dhcp.script').write_text('tampered')
        with self.assertRaises(ValueError):self.stage()

    def test_symlink_target_cannot_redirect_writes(self):
        outside=self.base/'outside';outside.mkdir()
        (self.root/'usr').mkdir();(self.root/'usr/libexec').symlink_to(outside,target_is_directory=True)
        with self.assertRaises(ValueError):self.stage()
        self.assertEqual(list(outside.iterdir()),[])
        self.assertEqual(self.original.read_bytes(),self.payload)

    def test_preexisting_delegate_is_not_silently_replaced(self):
        dest=self.root/'usr/libexec/r15-openwrt-dhcp.script';dest.parent.mkdir(parents=True);dest.write_text('owner data')
        with self.assertRaises(ValueError):self.stage()
        self.assertEqual(dest.read_text(),'owner data')

if __name__=='__main__':unittest.main()
