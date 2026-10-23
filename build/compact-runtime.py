"""Copy hash-verified runtime outputs; leave large source archives in their run."""
import argparse
import hashlib
import json
from pathlib import Path, PurePosixPath
import re
import shutil

REQUIRED = ('userspace-research.tar.gz', 'build-report.json', 'management-checks.json',
            'DO-NOT-FLASH.txt', 'pins.env', 'sdk.config')


def compact(source, output, run, commit):
    source = source.resolve()
    if output.exists():
        raise ValueError('Refusing to overwrite output directory')
    if not re.fullmatch(r'[1-9][0-9]*', str(run)) or not re.fullmatch(r'[0-9a-f]{40}', commit):
        raise ValueError('Invalid source run/commit identity')
    expected = {}
    for line in (source / 'SHA256SUMS').read_text().splitlines():
        digest, name = line.split(maxsplit=1)
        name = name.removeprefix('*').removeprefix('./')
        path = PurePosixPath(name)
        if not re.fullmatch('[0-9a-f]{64}', digest) or path.is_absolute() or '..' in path.parts or name in expected:
            raise ValueError('Unsafe or duplicate checksum entry')
        expected[name] = digest
    selected = set(REQUIRED)
    selected.update(p.relative_to(source).as_posix() for p in (source / 'packages').glob('*.ipk'))
    selected.update(p.name for p in source.glob('*-version.txt'))
    if not any(name.startswith('packages/') for name in selected):
        raise ValueError('No runtime packages')
    for name in sorted(selected):
        path = source / name
        if path.is_symlink() or not path.is_file() or not path.resolve().is_relative_to(source):
            raise ValueError('Missing or linked runtime file: ' + name)
        if name not in expected or hashlib.sha256(path.read_bytes()).hexdigest() != expected[name]:
            raise ValueError('Runtime checksum mismatch: ' + name)
    report = json.loads((source / 'build-report.json').read_text())
    if report.get('flashable') is not False or report.get('hardware_tested') is not False:
        raise ValueError('Expected explicitly non-flashable research outputs')
    output.mkdir(parents=True)
    for name in sorted(selected):
        dest = output / name
        dest.parent.mkdir(parents=True, exist_ok=True)
        shutil.copyfile(source / name, dest)
    provenance = {'source_run': int(run), 'source_commit': commit,
                  'source_url': 'https://github.com/tinyredphoenix/r15-openwrt-lab/actions/runs/' + str(run),
                  'source_archives': 'Retained with full artifact in source run', 'flashable': False,
                  'original_manifest_sha256': hashlib.sha256((source / 'SHA256SUMS').read_bytes()).hexdigest()}
    (output / 'PROVENANCE.json').write_text(json.dumps(provenance, indent=2) + '\n')
    names = sorted(selected | {'PROVENANCE.json'})
    (output / 'SHA256SUMS').write_text(''.join(hashlib.sha256((output / name).read_bytes()).hexdigest() + '  ' + name + '\n' for name in names))
    return {'runtime_files': len(names), 'bytes': sum((output / name).stat().st_size for name in names), 'flashable': False}


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('source', type=Path)
    parser.add_argument('output', type=Path)
    parser.add_argument('--source-run', required=True)
    parser.add_argument('--source-commit', required=True)
    args = parser.parse_args()
    print(json.dumps(compact(args.source, args.output, args.source_run, args.source_commit)))
