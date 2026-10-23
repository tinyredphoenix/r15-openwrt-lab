"""DHCP input preflight; no DHCP processes, interfaces or real logs touched."""
import os
import shlex
from pathlib import Path
import subprocess
import tempfile
import unittest

RUNTIME = Path(__file__).parent / 'runtime'

class DhcpGuardTests(unittest.TestCase):
    def run_guard(self, updates=None, event=None):
        with tempfile.TemporaryDirectory() as tmp:
            root=Path(tmp)
            policy=root/'policy';policy.write_text('192.168.77.0/24\n192.168.78.0/24\n')
            env=dict(os.environ, ip='192.168.0.100', subnet='255.255.255.0', mask='24',
                     router='192.168.0.1', staticroutes='', msstaticroutes='', CUSTOMROUTES='', INTERFACE='wwan')
            env.update(updates or {})
            cmd=['/bin/sh',str(RUNTIME/'r15-dhcp-guard'),str(policy),str(RUNTIME/'r15-subnet-check')]
            if event:
                # Test wrapper dispatch with an inert delegate; original OpenWrt
                # protocol code is never executed by these host tests.
                base=root/'base';base.write_text('#!/bin/sh\nprintf "delegated:%s\\n" "$1"\n')
                logger=root/'logger';logger.write_text('#!/bin/sh\nexit 0\n');logger.chmod(0o700)
                wrapper=(RUNTIME/'r15-dhcp.script').read_text()
                wrapper=wrapper.replace('/usr/libexec/r15-openwrt-dhcp.script',str(base))
                wrapper=wrapper.replace('/usr/libexec/r15-dhcp-guard',shlex.quote(str(RUNTIME/'r15-dhcp-guard')))
                wrapper=wrapper.replace('/etc/r15/protected-subnets',str(policy))
                wrapper=wrapper.replace('/usr/libexec/r15-subnet-check',shlex.quote(str(RUNTIME/'r15-subnet-check')))
                runner=root/'wrapper';runner.write_text(wrapper)
                env['PATH']=str(root)+':'+env['PATH']
                cmd=['/bin/sh',str(runner),event]
            return subprocess.run(cmd,env=env,text=True,capture_output=True)

    def test_valid_lease_and_normal_classless_routes(self):
        for values in ({}, {'mask':''}, {'staticroutes':'10.20.0.0/16 192.168.0.1 0.0.0.0/0 192.168.0.1'}):
            with self.subTest(values=values):self.assertEqual(self.run_guard(values).returncode,0)

    def test_conflicting_connected_subnets_rejected_before_delegate(self):
        for ip,mask,subnet in [('192.168.77.100','24','255.255.255.0'),
                               ('192.168.78.100','24','255.255.255.0'),
                               ('192.168.0.100','16','255.255.0.0')]:
            with self.subTest(ip=ip,mask=mask):
                result=self.run_guard({'ip':ip,'mask':mask,'subnet':subnet},event='bound')
                self.assertEqual(result.returncode,0,result.stderr)
                self.assertEqual(result.stdout,'delegated:deconfig\n')

    def test_bad_masks_and_addresses_rejected(self):
        for changes in ({'subnet':'255.0.255.0'}, {'mask':'16'}, {'subnet':''},
                        {'ip':'0.0.0.0'}, {'ip':'224.0.0.1'}, {'ip':'127.0.0.1'},
                        {'ip':'192.168.0.1;reboot'}, {'ip':'192.168.000.1'}):
            with self.subTest(changes=changes):self.assertEqual(self.run_guard(changes).returncode,1)

    def test_classless_routes_cannot_override_reserved_networks(self):
        for key in ('staticroutes','msstaticroutes'):
            for route in ('192.168.77.9/32 192.168.0.1','192.168.0.0/16 192.168.0.1',
                          '10.0.0.0/8 192.168.78.1','10.0.0.0/8', 'invalid 192.168.0.1'):
                with self.subTest(key=key,route=route):self.assertEqual(self.run_guard({key:route}).returncode,1)

    def test_offlink_gateway_cannot_override_management_host(self):
        self.assertEqual(self.run_guard({'router':'192.168.77.100'}).returncode,1)

    def test_wrapper_preserves_valid_renew_and_unrelated_interfaces(self):
        self.assertEqual(self.run_guard(event='renew').stdout,'delegated:renew\n')
        self.assertEqual(self.run_guard({'ip':'bad'},event='deconfig').stdout,'delegated:deconfig\n')
        self.assertEqual(self.run_guard({'INTERFACE':'other','ip':'bad'},event='bound').stdout,'delegated:bound\n')

    def test_invalid_renew_retires_old_lease_instead_of_publishing_new_one(self):
        self.assertEqual(self.run_guard({'staticroutes':'192.168.77.0/24 192.168.0.1'},event='renew').stdout,
                         'delegated:deconfig\n')

if __name__=='__main__':unittest.main()
