"""Install the custom LuCI radio page into research rootfs; execute no target code."""
import hashlib
import json
from pathlib import Path
import sys

REPO=Path(__file__).resolve().parents[1]
FILES={
 'repeater.lua':'usr/lib/lua/luci/model/cbi/r15/repeater.lua',
 'menu.json':'usr/share/luci/menu.d/luci-app-r15-repeater.json',
 'acl.json':'usr/share/rpcd/acl.d/luci-app-r15-repeater.json',
}

def stage(root,report):
    root=Path(root).resolve()
    source=REPO/'prototype/luci'
    payload={target:(source/name).read_bytes() for name,target in FILES.items()}
    for name,target in FILES.items():
        path=root/target
        for component in (path,*path.parents):
            if component==root:break
            if component.is_symlink():raise ValueError('Linked LuCI staging path')
        if path.exists() and path.read_bytes()!=payload[target]:
            raise ValueError('Existing LuCI file differs; use a fresh assembly')
    records={}
    for target,data in payload.items():
        path=root/target;path.parent.mkdir(parents=True,exist_ok=True)
        path.write_bytes(data);path.chmod(0o644)
        records[target]={'sha256':hashlib.sha256(data).hexdigest(),'bytes':len(data)}
    result={'files':records,'executed':False,'web_login_tested':False,'radio_apply_tested':False}
    Path(report).write_text(json.dumps(result,indent=2)+'\n')
    return result

if __name__=='__main__':
    print(json.dumps(stage(Path(sys.argv[1]),Path(sys.argv[2])),indent=2))
