"""Stage reviewed DHCP preflight around the exact OpenWrt script, never execute it."""
import hashlib
import json
from pathlib import Path
import shutil
import sys

REPO = Path(__file__).resolve().parents[1]

def stage(root, report):
    root = Path(root).resolve()
    manifest = json.loads((REPO / 'build/dhcp-script-manifest.json').read_text())
    original = root / manifest['path']
    destination = root / 'usr/libexec/r15-openwrt-dhcp.script'
    helpers = ['r15-subnet-check', 'r15-dhcp-guard']
    targets = [original, destination] + [root/'usr/libexec'/x for x in helpers]
    # Reject symlinked components before any writes to the assembled tree.
    for target in targets:
        if any(p.is_symlink() for p in [target, *target.parents] if p != root.parent):
            raise ValueError('Symlink in DHCP staging path')
    wrapper = (REPO/'prototype/runtime/r15-dhcp.script').read_bytes()
    if hashlib.sha256(original.read_bytes()).hexdigest() == manifest['sha256']:
        if destination.exists():
            raise ValueError('Unexpected preexisting DHCP delegate')
        source = original.read_bytes()
    elif original.read_bytes() == wrapper and destination.is_file():
        source = destination.read_bytes()
    else:
        raise ValueError('OpenWrt DHCP script does not match pinned source')
    if hashlib.sha256(source).hexdigest() != manifest['sha256']:
        raise ValueError('OpenWrt DHCP delegate does not match pinned source')
    destination.parent.mkdir(parents=True, exist_ok=True)
    destination.write_bytes(source); destination.chmod(0o755)
    for helper in helpers:
        target=root/'usr/libexec'/helper
        shutil.copyfile(REPO/'prototype/runtime'/helper, target); target.chmod(0o755)
    original.write_bytes(wrapper); original.chmod(0o755)
    result={'original_sha256':manifest['sha256'], 'wrapper_sha256':hashlib.sha256(wrapper).hexdigest(),
            'staged_helpers':helpers,'executed':False,'protected_subnets_provisioned':False,
            'missing_policy_behavior':'Reject WWAN bound/renew; no lease publication',
            'firmware_image':False}
    Path(report).write_text(json.dumps(result,indent=2)+'\n')
    return result

if __name__ == '__main__':
    print(json.dumps(stage(Path(sys.argv[1]),Path(sys.argv[2])),indent=2))
