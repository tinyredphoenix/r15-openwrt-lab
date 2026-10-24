from pathlib import Path
import subprocess,tempfile,unittest
RUNTIME=Path(__file__).parents[1]/'prototype/runtime'
def function(name,source):
 start=source.index(name+'() {');end=source.index('\n}\n',start)+3
 return source[start:end]
class HandoffOwnership(unittest.TestCase):
 def test_invalid_band_never_reaches_device_operations(self):
  r=subprocess.run(['sh',str(RUNTIME/'r15-network-handoff'),'unexpected'],capture_output=True)
  self.assertEqual(r.returncode,89)
 def test_cleanup_stops_only_network_records_and_own_mounts(self):
  with tempfile.TemporaryDirectory() as directory:
   log=Path(directory)
   (log/'owned.tsv').write_text('network 501 123\n');(log/'loggers.tsv').write_text('logger 502 124\n');(log/'mounts.tsv').write_text('/opt/r15-openwrt/sys\n')
   script='''LOG=$1
cleanup() { echo UNSAFE; return 99; }
stop_records() { echo "stop:$1:$2"; }
owned() { return 1; }
starttime() { echo different-process; }
kill() { echo "UNEXPECTED-KILL:$*"; }
umount() { echo "unmount:$1"; }
'''+function('network_cleanup',(RUNTIME/'r15-network-handoff').read_text())+'\nnetwork_cleanup\n'
   r=subprocess.run(['sh','-s','--',directory],input=script,text=True,capture_output=True)
   self.assertEqual(r.returncode,0,r.stderr)
   self.assertEqual(r.stdout.splitlines(),['stop:TERM:'+str(log/'owned.tsv'),'stop:KILL:'+str(log/'owned.tsv'),'unmount:/opt/r15-openwrt/sys'])
 def test_management_repairs_route_even_when_alias_survives(self):
  text=function('ensure_management',(RUNTIME/'r15-stock-management').read_text())
  script='''ip() {
case "$*" in
'link set dev br0 up') return 0 ;;
'-4 addr show dev br0') echo '    inet 192.168.77.1/24 scope global br0'; return 0 ;;
'route replace 192.168.77.0/24 dev br0 src 192.168.77.1') echo REPAIRED; return 0 ;;
*) echo "UNEXPECTED:$*"; return 99 ;;
esac
}
'''+text.replace('[ -d /sys/class/net/br0/brif ] || return 1','true')+'\nensure_management\n'
  r=subprocess.run(['sh'],input=script,text=True,capture_output=True)
  self.assertEqual(r.returncode,0,r.stderr);self.assertEqual(r.stdout,'REPAIRED\n')
if __name__=='__main__':unittest.main()
