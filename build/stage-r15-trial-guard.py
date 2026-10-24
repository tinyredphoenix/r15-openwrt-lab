"""Add explicit no-auto-commit policy to the private management boot seed."""
import argparse,copy,hashlib,io,json
from pathlib import Path
import tarfile

ENV_SHA='bc812e769d43a679bf086cef09105097a3b54c384560e01d500b6bcd079d22df'
FW_LOADED_SHA='9706d076216a6e504fef66254185925a50cb8b16ed9322a9b15a1e77c31a37b7'
HERE=Path(__file__).resolve().parent

def stage(source,output):
    if output.exists():raise ValueError('Refusing to overwrite trial stage')
    prior=json.loads((source/'STAGE.json').read_text())
    if not prior['automatic_management_hook'] or not prior['stock_pid1_retained']:raise ValueError('Expected management boot seed')
    output.mkdir(mode=0o700)
    templates={name:(HERE.parent/'prototype/runtime'/name).read_bytes() for name in ('r15-trial-env-guard','r15-trial-fw-loaded')}
    seen=set();changed=[];env=None
    with tarfile.open(source/'merged-root.tar') as incoming,tarfile.open(output/'merged-root.tar','w',format=tarfile.PAX_FORMAT) as target:
        for original in incoming:
            name=original.name.removeprefix('./');seen.add(name);member=copy.copy(original)
            data=None
            if name=='usr/bin/fw_printenv':
                if not member.isfile():raise ValueError('Expected original environment binary')
                env=incoming.extractfile(original).read()
                if hashlib.sha256(env).hexdigest()!=ENV_SHA:raise ValueError('Environment binary mismatch')
                data=env
            elif name=='usr/bin/fw_setenv':
                if not member.issym() or member.linkname!='fw_printenv':raise ValueError('Expected original writer symlink')
                member.type=tarfile.REGTYPE;member.linkname='';member.mode=0o755;data=templates['r15-trial-env-guard'];changed.append(name)
            elif name=='etc/scripts/fw_loaded.sh':
                old=incoming.extractfile(original).read()
                if hashlib.sha256(old).hexdigest()!=FW_LOADED_SHA:raise ValueError('Legacy acknowledgement script mismatch')
                data=templates['r15-trial-fw-loaded'];changed.append(name)
            if name.startswith('usr/libexec/r15-env-tool'):raise ValueError('Operator tool namespace already exists')
            if data is not None:
                member.size=len(data);member.pax_headers={k:v for k,v in member.pax_headers.items() if k not in ('size','linkpath')}
                target.addfile(member,io.BytesIO(data))
            else:target.addfile(member,incoming.extractfile(original) if member.isfile() else None)
        if env is None or sorted(changed)!=['etc/scripts/fw_loaded.sh','usr/bin/fw_setenv']:raise ValueError('Missing acknowledgement entry points')
        for name in ('usr/libexec','usr/libexec/r15-env-tool'):
            if name not in seen:
                member=tarfile.TarInfo(name);member.type=tarfile.DIRTYPE;member.mode=0o750;target.addfile(member)
        member=tarfile.TarInfo('usr/libexec/r15-env-tool/fw_setenv');member.mode=0o750;member.size=len(env);target.addfile(member,io.BytesIO(env))
    prior.update({'scope':'Private stock-assisted management trial; explicit boot commit only',
                  'stock_files_changed':prior['stock_files_changed']+changed,
                  'automatic_boot_commit_suppressed':True,'original_env_tool_sha256':ENV_SHA,
                  'explicit_env_writer':'/usr/libexec/r15-env-tool/fw_setenv',
                  'guard_scope':'Known commander fw_setenv acknowledgement and rc35 fw_loaded nv path; not a proof that all vendor software is incapable of any env write',
                  'cold_boot_tested':False,'flashable':False})
    prior['remaining']=['Stage/readback guarded rootfs','Fresh redundant environment backup and controlled trial boot',
                        'Observe commit remains on original bank before explicit acceptance','Full radio takeover and persistent OpenWrt settings']
    (output/'STAGE.json').write_text(json.dumps(prior,indent=2)+'\n')
    for f in output.iterdir():f.chmod(0o600)
    return prior
if __name__=='__main__':
    p=argparse.ArgumentParser(description=__doc__);p.add_argument('source',type=Path);p.add_argument('output',type=Path);a=p.parse_args();print(json.dumps(stage(a.source,a.output),indent=2))
