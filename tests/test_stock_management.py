from pathlib import Path
import subprocess
import unittest

SCRIPT=Path(__file__).parents[1]/'prototype/runtime/r15-stock-management'
class StartupGuards(unittest.TestCase):
    def test_rejects_unowned_roots_before_any_operation(self):
        for root in ['/', '/tmp/arbitrary', '/opt/r15-openwrt/../other', '/run/r15-phase3-aaaaaaaaaaaZ/rootfs']:
            r=subprocess.run(['/bin/sh',str(SCRIPT),root,'/run/r15-management','0'],capture_output=True)
            self.assertEqual(r.returncode,90)
    def test_rejects_unowned_state_paths_before_any_operation(self):
        for state in ['/', '/run', '/tmp/other', '/run/r15-management-test-nothex000000']:
            r=subprocess.run(['/bin/sh',str(SCRIPT),'/opt/r15-openwrt',state,'0'],capture_output=True)
            self.assertEqual(r.returncode,91)
    def test_rejects_invalid_lifetimes_before_any_operation(self):
        for lifetime in ['-1','3601','bad','2;reboot','999999999999999999999999999']:
            r=subprocess.run(['/bin/sh',str(SCRIPT),'/opt/r15-openwrt','/run/r15-management',lifetime],capture_output=True)
            self.assertEqual(r.returncode,92)
if __name__=='__main__':unittest.main()
