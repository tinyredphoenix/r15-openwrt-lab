import importlib.util
import json
from pathlib import Path
import tempfile
import unittest

REPO=Path(__file__).parents[1]
spec=importlib.util.spec_from_file_location('luci_stage',REPO/'build/stage-luci-radio.py')
stage=importlib.util.module_from_spec(spec);spec.loader.exec_module(stage)

class LuciStagingTests(unittest.TestCase):
    def setUp(self):
        self.tmp=tempfile.TemporaryDirectory();self.addCleanup(self.tmp.cleanup)
        self.base=Path(self.tmp.name).resolve();self.root=self.base/'root';self.root.mkdir()
        self.report=self.base/'report.json'

    def test_repeatable_staging_has_explicit_unqualified_runtime(self):
        first=stage.stage(self.root,self.report)
        self.assertEqual(first,stage.stage(self.root,self.report))
        self.assertFalse(first['executed']);self.assertFalse(first['radio_apply_tested'])
        self.assertEqual(len(first['files']),3)

    def test_unexpected_existing_file_prevents_any_partial_write(self):
        target=self.root/stage.FILES['acl.json'];target.parent.mkdir(parents=True)
        target.write_text('owner content')
        with self.assertRaises(ValueError):stage.stage(self.root,self.report)
        self.assertEqual(target.read_text(),'owner content')
        self.assertFalse((self.root/stage.FILES['repeater.lua']).exists())

    def test_link_cannot_redirect_installation(self):
        outside=self.base/'outside';outside.mkdir();(self.root/'usr').symlink_to(outside)
        with self.assertRaises(ValueError):stage.stage(self.root,self.report)
        self.assertEqual(list(outside.iterdir()),[])

    def test_menu_requires_authenticated_acl_and_cbi_post(self):
        menu=json.loads((REPO/'prototype/luci/menu.json').read_text())
        self.assertEqual(len(menu),1)
        entry=next(iter(menu.values()))
        self.assertEqual(entry['action']['post'],{'cbi.submit':True})
        name=entry['depends']['acl'][0]
        acl=json.loads((REPO/'prototype/luci/acl.json').read_text())[name]
        self.assertEqual(acl['read'],{'uci':['r15_radio']})
        self.assertEqual(acl['write'],{'uci':['r15_radio']})
