import hashlib,importlib.util,json,tarfile,tempfile,subprocess,io
from pathlib import Path
import unittest
from unittest.mock import patch

ROOT=Path(__file__).parents[1]
s=importlib.util.spec_from_file_location('trial',ROOT/'build/stage-r15-trial-guard.py');m=importlib.util.module_from_spec(s);s.loader.exec_module(m)
class TrialGuardTests(unittest.TestCase):
 def test_guard_defers_only_known_auto_commit(self):
  script=ROOT/'prototype/runtime/r15-trial-env-guard'
  for args,code in [(['sw_commit','0'],0),(['sw_commit','1'],0),(['sw_tryactive','1'],1),(['sw_commit','bad'],1),([],1)]:
   r=subprocess.run(['/bin/sh',str(script),*args],capture_output=True);self.assertEqual(r.returncode,code)
 def test_stager_preserves_original_tool_outside_default_path(self):
  with tempfile.TemporaryDirectory() as tmp:
   source=Path(tmp)/'source';source.mkdir();out=Path(tmp)/'output';binary=b'fixture env binary';loaded=b'fixture old ack'
   (source/'STAGE.json').write_text(json.dumps({'automatic_management_hook':True,'stock_pid1_retained':True,'stock_files_changed':['usr/etc/rcS']}))
   with tarfile.open(source/'merged-root.tar','w') as t:
    for name,data in [('usr/bin/fw_printenv',binary),('etc/scripts/fw_loaded.sh',loaded)]:
     x=tarfile.TarInfo(name);x.size=len(data);x.mode=0o755;t.addfile(x,io.BytesIO(data))
    x=tarfile.TarInfo('usr/bin/fw_setenv');x.type=tarfile.SYMTYPE;x.linkname='fw_printenv';t.addfile(x)
   with patch.object(m,'ENV_SHA',hashlib.sha256(binary).hexdigest()),patch.object(m,'FW_LOADED_SHA',hashlib.sha256(loaded).hexdigest()):
    report=m.stage(source,out)
   self.assertTrue(report['automatic_boot_commit_suppressed'])
   with tarfile.open(out/'merged-root.tar') as t:
    self.assertEqual(t.extractfile('usr/bin/fw_printenv').read(),binary)
    self.assertEqual(t.extractfile('usr/libexec/r15-env-tool/fw_setenv').read(),binary)
    self.assertTrue(t.getmember('usr/bin/fw_setenv').isfile())
    self.assertIn(b'automatic boot commit deferred',t.extractfile('usr/bin/fw_setenv').read())
    self.assertNotIn(b'nv setenv',t.extractfile('etc/scripts/fw_loaded.sh').read())
if __name__=='__main__':unittest.main()
