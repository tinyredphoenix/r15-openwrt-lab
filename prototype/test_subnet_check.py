"""Pure range policy checked against Python's independent IP network model."""
import ipaddress
from pathlib import Path
import random
import subprocess
import tempfile
import unittest

CHECK = Path(__file__).parent / 'runtime/r15-subnet-check'

class SubnetCheckTests(unittest.TestCase):
    def check_range(self, learned, protected=('192.168.77.0/24', '192.168.88.0/24')):
        with tempfile.TemporaryDirectory() as tmp:
            policy = Path(tmp) / 'protected'
            policy.write_text('\n'.join(protected) + '\n')
            return subprocess.run(['/bin/sh', str(CHECK), learned, str(policy)],
                                  capture_output=True).returncode

    def test_management_overlap_and_broader_upstream(self):
        for cidr in ('192.168.77.200/24', '192.168.10.1/16', '0.0.0.0/0'):
            with self.subTest(cidr=cidr): self.assertEqual(self.check_range(cidr), 1)

    def test_client_overlap_including_single_host(self):
        self.assertEqual(self.check_range('192.168.88.250/32'), 1)

    def test_adjacent_networks_and_high_addresses_are_disjoint(self):
        for cidr in ('192.168.76.255/24', '192.168.89.0/24', '255.255.255.255/32'):
            with self.subTest(cidr=cidr): self.assertEqual(self.check_range(cidr), 0)

    def test_invalid_lease_and_missing_prefix_rejected(self):
        for cidr in ('192.168.1.1', '192.168.1.1/33', '192.168.1.1/-1',
                     '192.168.1.1/024', '192.168.01.1/24', '256.1.1.1/24',
                     '192.168.1.1/24;reboot', '', '192.168.1.1/24\n1.2.3.4/24'):
            with self.subTest(cidr=cidr): self.assertEqual(self.check_range(cidr), 2)

    def test_policy_must_have_two_valid_networks(self):
        for policy in ((), ('192.168.77.1/24',), ('192.168.77.1/24', 'invalid'),
                       ('192.168.77.1/24', '192.168.88.1/24', '10.0.0.1/8')):
            with self.subTest(policy=policy): self.assertEqual(self.check_range('192.168.0.5/24', policy), 2)

    def test_full_prefix_range_against_independent_oracle(self):
        rng = random.Random(8198)
        for prefix in range(33):
            for _ in range(3):
                learned = f'{ipaddress.IPv4Address(rng.randrange(2**32))}/{prefix}'
                local = tuple(f'{ipaddress.IPv4Address(rng.randrange(2**32))}/{rng.randrange(33)}' for _ in range(2))
                expected = int(any(ipaddress.ip_network(learned, strict=False).overlaps(
                    ipaddress.ip_network(x, strict=False)) for x in local))
                with self.subTest(learned=learned, local=local):
                    self.assertEqual(self.check_range(learned, local), expected)

if __name__ == '__main__': unittest.main()
