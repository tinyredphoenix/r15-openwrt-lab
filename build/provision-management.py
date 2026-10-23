"""Provision a PRIVATE local filesystem copy, never a public cloud artifact/router."""
import importlib.util
import ipaddress
import json
import os
from pathlib import Path
import re
import subprocess
import sys

REPO = Path(__file__).resolve().parents[1]

def openssl(arguments):
    result = subprocess.run(['openssl', *map(str, arguments)], text=True,
                            capture_output=True, timeout=20, env=dict(os.environ, LC_ALL='C'))
    if result.returncode:
        raise ValueError('Management TLS identity validation failed')
    return result.stdout

def provision(root, profile_path, secrets_dir, report_path):
    root=Path(root).resolve(); secrets_dir=Path(secrets_dir)
    if root == Path('/'):
        raise ValueError('Refusing host root')
    spec=importlib.util.spec_from_file_location('management_renderer', REPO/'prototype/r15_repeater.py')
    renderer=importlib.util.module_from_spec(spec);spec.loader.exec_module(renderer)
    profile=json.loads(Path(profile_path).read_text())
    if not profile.get('management',{}).get('ssh_authorized_keys'):
        raise ValueError('An owner SSH public key is required')
    files,_=renderer.render(profile,'wired-first')
    hashed=(secrets_dir/'root-password.sha512').read_text().strip()
    if not re.fullmatch(r'\$6\$(?:rounds=[1-9][0-9]*\$)?[./A-Za-z0-9]{1,16}\$[./A-Za-z0-9]{86}',hashed):
        raise ValueError('Expected a SHA-512 crypt root password hash')
    key=secrets_dir/'uhttpd.key';cert=secrets_dir/'uhttpd.crt'
    if key.stat().st_mode & 0o077:
        raise ValueError('TLS private key must not be accessible to group/others')
    key_pub=openssl(['pkey','-in',key,'-pubout'])
    cert_pub=openssl(['x509','-in',cert,'-pubkey','-noout'])
    if key_pub != cert_pub:
        raise ValueError('TLS certificate/private key mismatch')
    address=str(ipaddress.ip_interface(profile['management']['address']).ip)
    match=openssl(['x509','-in',cert,'-noout','-checkip',address])
    # Some OpenSSL versions return zero even for a negative checkip result.
    if match.strip() != 'IP ' + address + ' does match certificate':
        raise ValueError('TLS certificate does not match management address')
    openssl(['x509','-in',cert,'-noout','-checkend','86400'])
    # Check every target path before opening account/config files or writing.
    names=['etc/passwd','etc/shadow','etc/uhttpd.crt','etc/uhttpd.key',
           'etc/dropbear/authorized_keys','root/.ssh/authorized_keys']
    names += ['etc/config/'+Path(n).name for n in files if n.startswith('openwrt-config/')]
    for name in names:
        target=root
        for component in Path(name).parts:
            target=target/component
            if target.is_symlink():raise ValueError('Symlink in private provisioning target')
    passwd=(root/'etc/passwd').read_text().splitlines()
    account=[x.split(':') for x in passwd if x.startswith('root:')]
    if len(account)!=1 or len(account[0])!=7 or account[0][2:4]!=['0','0'] or account[0][5:]!=['/root','/bin/ash']:
        raise ValueError('Unexpected root account')
    lines=(root/'etc/shadow').read_text().splitlines()
    matches=[i for i,line in enumerate(lines) if line.startswith('root:')]
    if len(matches)!=1:raise ValueError('Expected exactly one root shadow entry')
    fields=lines[matches[0]].split(':')
    if len(fields)!=9:raise ValueError('Malformed root shadow entry')
    fields[1]=hashed;lines[matches[0]]=':'.join(fields)
    writes={'etc/shadow': ('\n'.join(lines)+'\n').encode(),
            'etc/uhttpd.crt': cert.read_bytes(),'etc/uhttpd.key': key.read_bytes(),
            'etc/dropbear/authorized_keys': files['dropbear/authorized_keys'].encode(),
            'root/.ssh/authorized_keys': files['dropbear/authorized_keys'].encode()}
    for name,body in files.items():
        if name.startswith('openwrt-config/'):
            writes['etc/config/'+Path(name).name]=body.encode()
    # Never silently replace another administrative identity in an existing tree.
    for name in ('etc/uhttpd.crt','etc/uhttpd.key','etc/dropbear/authorized_keys','root/.ssh/authorized_keys'):
        target=root/name
        if target.exists() and target.read_bytes() not in (b'',writes[name]):
            raise ValueError('Existing management identity differs')
    for name,body in writes.items():
        target=root/name;target.parent.mkdir(parents=True,exist_ok=True)
        fd=os.open(target,os.O_WRONLY|os.O_CREAT|os.O_TRUNC,0o600)
        with os.fdopen(fd,'wb') as stream:stream.write(body)
        target.chmod(0o600)
    (root/'root').chmod(0o700);(root/'root/.ssh').chmod(0o700)
    (root/'etc/dropbear').chmod(0o700)
    result={'private':True,'password_hash_provisioned':True,'ssh_public_key_provisioned':True,
            'https_identity_validated':True,'http_binding':address,'private_client_key_copied':False,
            'ssh_host_key_generated':False,'services_started':False,'boot_integration_complete':False,
            'firmware_image':False}
    output=Path(report_path);output.write_text(json.dumps(result,indent=2)+'\n');output.chmod(0o600)
    return result

if __name__=='__main__':
    print(json.dumps(provision(*sys.argv[1:]),indent=2))
