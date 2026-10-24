import hashlib,importlib.util,json,tarfile,tempfile,unittest
from pathlib import Path
from unittest.mock import patch
spec=importlib.util.spec_from_file_location('base',Path(__file__).parents[1]/'build/stage-openwrt-base.py');m=importlib.util.module_from_spec(spec);spec.loader.exec_module(m)
class StandardBase(unittest.TestCase):
 def setUp(self):
  self.temp=tempfile.TemporaryDirectory();self.addCleanup(self.temp.cleanup);self.root=Path(self.temp.name);self.source=self.root/'source';self.source.mkdir();self.manifest=self.root/'manifest.json';self.files=[]
  p=patch.object(m,'MANIFEST',self.manifest);p.start();self.addCleanup(p.stop)
 def add(self,name,data,mode='100644',actual_symlink=False):
  p=self.source/name;p.parent.mkdir(parents=True,exist_ok=True)
  if actual_symlink:p.symlink_to(data.decode())
  else:p.write_bytes(data)
  self.files.append({'path':name,'mode':mode,'sha256':hashlib.sha256(data).hexdigest(),'git_blob':hashlib.sha1(('blob '+str(len(data))+'\0').encode()+data).hexdigest()})
  self.manifest.write_text(json.dumps({'commit':'test','files':self.files}))
 def assemble(self,suffix=''):
  return m.assemble(self.source,self.root/('base'+suffix+'.tar'),self.root/('report'+suffix+'.json'))
 def test_packages_standard_init_and_console_reproducibly(self):
  self.add('etc/preinit',b'#!/bin/sh\nPATH="%PATH%"\n',mode='100755');a=self.assemble();b=self.assemble('2');self.assertEqual(a['tar_sha256'],b['tar_sha256'])
  with tarfile.open(self.root/'base.tar') as t:
   self.assertNotIn(b'%PATH%',t.extractfile('etc/preinit').read());node=t.getmember('dev/console');self.assertTrue(node.ischr());self.assertEqual((node.devmajor,node.devminor),(5,1));self.assertEqual(t.getmember('etc/preinit').mode,0o755)
  self.assertFalse(a['flashable']);self.assertFalse(a['custom_pid1_wrapper'])
 def test_source_mismatch_cannot_create_partial_output(self):
  self.add('etc/preinit',b'original');(self.source/'etc/preinit').write_bytes(b'changed')
  with self.assertRaises(ValueError):self.assemble()
  self.assertFalse((self.root/'base.tar').exists())
 def test_reads_git_symlink_target_without_following_it(self):
  self.add('etc/os-release',b'../usr/lib/os-release','120000',actual_symlink=True);self.assemble()
  with tarfile.open(self.root/'base.tar') as t:self.assertEqual(t.getmember('etc/os-release').linkname,'../usr/lib/os-release')
 def test_rejects_escaping_symlink(self):
  self.add('etc/danger',b'../../outside','120000')
  with self.assertRaises(ValueError):self.assemble()
if __name__=='__main__':unittest.main()
