from pathlib import Path
import subprocess
import tempfile
import unittest

SCRIPT=Path(__file__).parents[1]/'prototype/runtime/r15-stage-inactive'
class WriterTests(unittest.TestCase):
    def run_fixture(self, fail):
        # Source real ordering logic; replace every device actuator/observer.
        body='''R15_STAGE_SOURCE_ONLY=1
. "$1"
BASE=/tmp/inert-fixture
ROOTFS_BYTES=100; ROOTFS_SHA=fixture; KERNEL_SHA=fixture
phase() { echo "phase:$1"; }
update_volume() { echo "update:$1"; [ "$FAIL" != "update:$1" ]; }
verify_written() { echo "verify:$1"; [ "$FAIL" != "verify:$1" ]; }
FAIL=$2
write_images
'''
        return subprocess.run(['/bin/sh','-c',body,'fixture',str(SCRIPT),fail],capture_output=True,text=True)
    def test_updates_only_inactive_pair_and_verifies_each(self):
        r=self.run_fixture('none'); self.assertEqual(r.returncode,0)
        self.assertEqual([x for x in r.stdout.splitlines() if x.startswith(('update:','verify:'))],
                         ['update:/dev/ubi0_4','verify:/dev/ubi0_4','update:/dev/ubi0_3','verify:/dev/ubi0_3'])
    def test_root_failure_prevents_kernel_write(self):
        for fail,code in [('update:/dev/ubi0_4',140),('verify:/dev/ubi0_4',141)]:
            r=self.run_fixture(fail); self.assertEqual(r.returncode,code)
            self.assertNotIn('update:/dev/ubi0_3',r.stdout)
    def test_kernel_failure_not_marked_complete(self):
        for fail,code in [('update:/dev/ubi0_3',142),('verify:/dev/ubi0_3',143)]:
            r=self.run_fixture(fail); self.assertEqual(r.returncode,code)
            self.assertNotIn('inactive-pair-readback-passed',r.stdout)
    def test_rejects_action_and_arbitrary_state_path(self):
        for args,code in [([],90),(['--write-inactive-only','/tmp/not-owned'],91)]:
            r=subprocess.run(['/bin/sh',str(SCRIPT),*args],capture_output=True);self.assertEqual(r.returncode,code)
    def test_duplicate_and_injected_manifest_rejected(self):
        with tempfile.TemporaryDirectory() as tmp:
            f=Path(tmp)/'manifest'
            for text in ['boot_id=x\nboot_id=y\n','unexpected=x\n','kernel_sha=$(reboot)\n']:
                f.write_text(text)
                r=subprocess.run(['/bin/sh','-c','R15_STAGE_SOURCE_ONLY=1; . "$1"; parse_manifest "$2"','fixture',str(SCRIPT),str(f)],capture_output=True)
                self.assertNotEqual(r.returncode,0)
if __name__=='__main__':unittest.main()
