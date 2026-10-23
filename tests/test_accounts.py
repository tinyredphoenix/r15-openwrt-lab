import importlib.util
from pathlib import Path
import tempfile
import unittest

spec = importlib.util.spec_from_file_location('collector_accounts', Path(__file__).parents[1] / 'build/collect-userspace.py')
m = importlib.util.module_from_spec(spec)
spec.loader.exec_module(m)


class AccountTests(unittest.TestCase):
    def test_service_ids_are_explicit_and_passwords_locked(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            report = m.stage_accounts({'ubusd': {'Require-User': 'ubus=81:ubus=81'},
                                       'procd': {'Require-User': ':dialout=20 :audio=29'}}, root)
            self.assertIn('ubus:x:81:81:ubus:/var/run/ubus:/bin/false', (root/'etc/passwd').read_text())
            self.assertIn('root:x:0:0:root:/root:/bin/ash', (root/'etc/passwd').read_text())
            self.assertTrue(all(line.split(':')[1] == '*' for line in (root/'etc/shadow').read_text().splitlines()))
            self.assertEqual((root/'etc/shadow').stat().st_mode & 0o777, 0o600)
            self.assertFalse(report['owner_ssh_key_provisioned'])

    def test_privileged_conflicting_and_ambiguous_ids_rejected(self):
        for value in ('bad=0:bad=10', 'root=10:bad=10', 'bad=10:root=10',
                      'one=10:one=10 two=10:two=11', 'one=10:one=10 two=11:two=10',
                      'dynamic:dynamic', 'bad=10:bad=65534', 'bad=10:bad=10;reboot'):
            with self.subTest(value=value), tempfile.TemporaryDirectory() as tmp:
                root = Path(tmp)
                with self.assertRaises(ValueError):
                    m.stage_accounts({'p': {'Require-User': value}}, root)
                self.assertEqual(list(root.iterdir()), [])

    def test_existing_identity_file_is_never_overwritten(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp); (root/'etc').mkdir()
            (root/'etc/passwd').write_text('keep')
            with self.assertRaisesRegex(ValueError, 'collision'):
                m.stage_accounts({}, root)
            self.assertEqual((root/'etc/passwd').read_text(), 'keep')
            self.assertFalse((root/'etc/shadow').exists())
