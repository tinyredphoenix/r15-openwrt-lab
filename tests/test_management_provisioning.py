"""Private offline provisioning rejects identity mismatches before writes."""
import base64
import importlib.util
import json
from pathlib import Path
import shutil
import struct
import subprocess
import tempfile
import unittest

REPO=Path(__file__).parents[1]

class ManagementProvisioningTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.tls=tempfile.TemporaryDirectory();cls.addClassCleanup(cls.tls.cleanup)
        cls.identity=Path(cls.tls.name)
        subprocess.run(['openssl','req','-x509','-newkey','rsa:2048','-nodes','-sha256','-days','2',
                        '-subj','/CN=temporary test','-addext','subjectAltName=IP:192.168.77.1',
                        '-keyout',str(cls.identity/'uhttpd.key'),'-out',str(cls.identity/'uhttpd.crt')],
                       check=True,stdout=subprocess.DEVNULL,stderr=subprocess.DEVNULL)

    def setUp(self):
        self.tmp=tempfile.TemporaryDirectory();self.addCleanup(self.tmp.cleanup)
        self.base=Path(self.tmp.name);self.root=self.base/'root';(self.root/'etc').mkdir(parents=True)
        self.shadow=self.root/'etc/shadow';self.shadow.write_text('root:*:0:0:99999:7:::\nnobody:*:0:0:99999:7:::\n')
        (self.root/'etc/passwd').write_text('root:x:0:0:root:/root:/bin/ash\n')
        self.secrets=self.base/'secrets';self.secrets.mkdir()
        for name in ('uhttpd.key','uhttpd.crt'):shutil.copyfile(self.identity/name,self.secrets/name)
        (self.secrets/'uhttpd.key').chmod(0o600)
        (self.secrets/'root-password.sha512').write_text('$6$testSalt$'+'A'*86+'\n')
        self.profile=json.loads((REPO/'prototype/profile.same-radio.example.json').read_text())
        wire=struct.pack('>I',11)+b'ssh-ed25519'+struct.pack('>I',32)+bytes(range(32))
        self.profile['management']['ssh_authorized_keys']=['ssh-ed25519 '+base64.b64encode(wire).decode()]
        self.profilepath=self.base/'profile.json'
        spec=importlib.util.spec_from_file_location('provision',REPO/'build/provision-management.py')
        self.module=importlib.util.module_from_spec(spec);spec.loader.exec_module(self.module)
        self.report=self.base/'report.json'

    def provision(self):
        self.profilepath.write_text(json.dumps(self.profile))
        return self.module.provision(self.root,self.profilepath,self.secrets,self.report)

    def test_valid_private_provisioning_keeps_client_private_key_off_target(self):
        self.provision();self.provision()
        self.assertTrue(self.shadow.read_text().startswith('root:$6$'))
        self.assertIn('nobody:*:',self.shadow.read_text())
        self.assertEqual(self.shadow.stat().st_mode & 0o777,0o600)
        self.assertEqual((self.root/'root/.ssh').stat().st_mode & 0o777,0o700)
        result=json.loads(self.report.read_text())
        self.assertFalse(result['private_client_key_copied'])
        self.assertFalse(result['services_started'])
        self.assertIn("list listen_https '192.168.77.1:443'",(self.root/'etc/config/uhttpd').read_text())

    def test_missing_owner_key_cannot_create_inaccessible_configuration(self):
        self.profile['management']['ssh_authorized_keys']=[]
        with self.assertRaises(ValueError):self.provision()
        self.assertTrue(self.shadow.read_text().startswith('root:*:'))

    def test_certificate_for_wrong_address_does_not_provision(self):
        self.profile['management']['address']='192.168.99.1/24'
        with self.assertRaises(ValueError):self.provision()
        self.assertFalse((self.root/'etc/uhttpd.key').exists())

    def test_mismatched_certificate_and_key_are_rejected_before_writes(self):
        subprocess.run(['openssl','genpkey','-algorithm','RSA','-pkeyopt','rsa_keygen_bits:2048',
                        '-out',str(self.secrets/'uhttpd.key')],check=True,
                       stdout=subprocess.DEVNULL,stderr=subprocess.DEVNULL)
        (self.secrets/'uhttpd.key').chmod(0o600)
        with self.assertRaises(ValueError):self.provision()
        self.assertTrue(self.shadow.read_text().startswith('root:*:'))
        self.assertFalse((self.root/'etc/uhttpd.crt').exists())

    def test_publicly_readable_tls_private_key_is_rejected(self):
        (self.secrets/'uhttpd.key').chmod(0o644)
        with self.assertRaises(ValueError):self.provision()
        self.assertFalse(self.report.exists())

    def test_existing_identity_is_not_silently_replaced(self):
        (self.root/'etc/uhttpd.key').write_text('different identity')
        with self.assertRaises(ValueError):self.provision()
        self.assertTrue(self.shadow.read_text().startswith('root:*:'))
        self.assertEqual((self.root/'etc/uhttpd.key').read_text(),'different identity')

    def test_symlink_cannot_redirect_shadow_write(self):
        self.shadow.unlink();outside=self.base/'outside';outside.write_text('unchanged')
        self.shadow.symlink_to(outside)
        with self.assertRaises(ValueError):self.provision()
        self.assertEqual(outside.read_text(),'unchanged')

if __name__=='__main__':unittest.main()
