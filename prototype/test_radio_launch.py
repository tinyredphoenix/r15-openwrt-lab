"""Exercise actual launcher ownership/cleanup with inert substitute programs."""
import json
import os
from pathlib import Path
import subprocess
import signal
import time
import tempfile
import unittest

SOURCE=Path(__file__).parent/'runtime/r15-radio-launch'

class RadioLaunchTests(unittest.TestCase):
    def run_case(self, prepare=0, child=0, selection='wlan1 wlan1-vxd auto', terminate=False):
        with tempfile.TemporaryDirectory() as tmp:
            root=Path(tmp); bin=root/'bin';bin.mkdir(); work=root/'run';work.mkdir()
            fake=bin/'lua'
            fake.write_text('''#!/usr/bin/env python3
import os,sys
from pathlib import Path
p=Path(sys.argv[2]);p.joinpath('selection').write_text(os.environ['SELECTION']+'\\n')
for name in ['hostapd.conf','wpa_supplicant.conf','upstream-ssid']:p.joinpath(name).write_text('synthetic')
sys.exit(int(os.environ['PREPARE']))
''');fake.chmod(0o755)
            logger=bin/'logger';logger.write_text('#!/bin/sh\nexit 0\n');logger.chmod(0o755)
            coordinator=root/'coordinator'
            coordinator.write_text('''#!/usr/bin/env python3
import json,os,sys,signal,time
from pathlib import Path
p=Path(sys.argv[4])
Path(os.environ['CAPTURE']).write_text(json.dumps({'args':sys.argv[1:],'directory_mode':p.stat().st_mode & 511,'file_mode':(p/'hostapd.conf').stat().st_mode & 511}))
if os.environ.get('CHILD_WAIT')=='1':
 def stop(sig,frame):
  Path(os.environ['STOPPED']).write_text('stopped'); sys.exit(0)
 signal.signal(signal.SIGTERM,stop)
 Path(os.environ['READY']).write_text('ready')
 while True:time.sleep(0.01)
sys.exit(int(os.environ['CHILD_STATUS']))
''');coordinator.chmod(0o755)
            # Relocate only hard-coded installation paths in the test copy.
            script=SOURCE.read_text().replace('/var/run/r15-uci.',str(work/'r15-uci.')).replace('/usr/libexec/r15-radio-coordinator',str(coordinator))
            launch=root/'launch';launch.write_text(script)
            capture=root/'capture.json'
            env=dict(os.environ,PATH=str(bin)+os.pathsep+os.environ['PATH'],PREPARE=str(prepare),CHILD_STATUS=str(child),SELECTION=selection,CAPTURE=str(capture))
            if terminate:
                env.update(CHILD_WAIT='1',READY=str(root/'ready'),STOPPED=str(root/'stopped'))
                process=subprocess.Popen(['/bin/sh',str(launch)],env=env,stdout=subprocess.PIPE,stderr=subprocess.PIPE,text=True)
                try:
                    deadline=time.monotonic()+5
                    while not (root/'ready').exists() and time.monotonic()<deadline:
                        time.sleep(0.01)
                    self.assertTrue((root/'ready').exists(), 'owned child did not start')
                    process.send_signal(signal.SIGTERM)
                    stdout,stderr=process.communicate(timeout=5)
                    result=subprocess.CompletedProcess(process.args,process.returncode,stdout,stderr)
                    self.assertTrue((root/'stopped').exists(), 'TERM did not reach owned controller')
                finally:
                    if process.poll() is None:process.kill();process.wait()
            else:
                result=subprocess.run(['/bin/sh',str(launch)],env=env,capture_output=True,text=True,timeout=10)
            self.assertEqual(list(work.iterdir()),[], 'private snapshot leaked after exit')
            record=json.loads(capture.read_text()) if capture.exists() else None
            return result,record

    def test_snapshot_private_and_passed_to_owned_controller(self):
        result,record=self.run_case()
        self.assertEqual(result.returncode,0,result.stderr)
        self.assertEqual(record['args'][:3],['wlan1','wlan1-vxd','auto'])
        self.assertEqual(record['directory_mode'],0o700)
        self.assertEqual(record['file_mode'],0o600)

    def test_child_error_propagated_after_cleanup(self):
        result,record=self.run_case(child=7)
        self.assertEqual(result.returncode,7);self.assertIsNotNone(record)

    def test_invalid_configuration_never_starts_controller(self):
        result,record=self.run_case(prepare=1)
        self.assertEqual(result.returncode,1);self.assertIsNone(record)

    def test_disabled_profile_exits_without_starting_controller(self):
        result,record=self.run_case(prepare=3)
        self.assertEqual(result.returncode,0);self.assertIsNone(record)

    def test_unexpected_radio_pair_never_starts_controller(self):
        result,record=self.run_case(selection='br-mgmt eth0 auto')
        self.assertEqual(result.returncode,1);self.assertIsNone(record)

    def test_stop_signal_reaches_owned_child_before_snapshot_cleanup(self):
        result,record=self.run_case(terminate=True)
        self.assertEqual(result.returncode,0,result.stderr)
        self.assertIsNotNone(record)
