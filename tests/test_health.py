from pathlib import Path
import subprocess
import tempfile
import unittest

HEALTH=Path(__file__).parents[1] / 'prototype/runtime/r15-health'

class HealthTests(unittest.TestCase):
    def probe(self, values):
        with tempfile.TemporaryDirectory() as tmp:
            root=Path(tmp)
            for name,value in values.items():
                p=root/name;p.parent.mkdir(parents=True,exist_ok=True);p.write_text(value)
            result=subprocess.run(['/bin/sh',str(HEALTH),'--root',str(root)],text=True,capture_output=True)
            self.assertEqual(result.returncode,0,result.stderr)
            return dict(line.split('=',1) for line in result.stdout.splitlines())

    def test_missing_sensors_are_not_reported_as_healthy_power(self):
        data=self.probe({})
        self.assertEqual(data['uptime_seconds'],'unknown')
        self.assertEqual(data['power.voltage_monitor'],'not-exposed')
        self.assertEqual(data['power.supply_integrity'],'unknown')
        self.assertEqual(data['net.wlan0.present'],'no')

    def test_link_counters_and_sensor_do_not_overclaim_antenna_or_supply_health(self):
        data=self.probe({'proc/uptime':'123.45 100.0\n',
                         'proc/meminfo':'MemTotal: 123456 kB\nMemAvailable: 3210 kB\n',
                         'sys/class/net/wlan0/carrier':'1\n',
                         'sys/class/net/wlan0/statistics/rx_bytes':'4294967297\n',
                         'sys/class/hwmon/hwmon0/in0_input':'12000\n'})
        self.assertEqual(data['uptime_seconds'],'123.45')
        self.assertEqual(data['memory.MemTotal_kib'],'123456')
        self.assertEqual(data['net.wlan0.rx_bytes'],'4294967297')
        self.assertEqual(data['power.sensor1_raw_mv'],'12000')
        self.assertEqual(data['power.supply_integrity'],'unknown')
        self.assertEqual(data['radio.antenna_chains'],'not-validated')

    def test_malformed_readings_are_data_not_commands(self):
        data=self.probe({'proc/uptime':'invalid-value 0\n',
                         'sys/class/net/wlan1/carrier':'$(unexpected-command)\n'})
        self.assertEqual(data['uptime_seconds'],'unknown')
        self.assertEqual(data['net.wlan1.carrier'],'unknown')

if __name__=='__main__':unittest.main()
