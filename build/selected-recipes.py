"""Select SDK userspace recipes without building unrelated board/base packages."""
import re
from pathlib import Path
import sys


def recipes(config, packageinfo):
    selected = set(re.findall(r'^CONFIG_PACKAGE_([^=\n]+)=[ym]$', config, re.M))
    source = None
    found = {}
    for line in packageinfo.splitlines():
        if line.startswith('Source-Makefile: '):
            source = line.split(': ', 1)[1]
        elif line.startswith('Package: '):
            name = line.split(': ', 1)[1]
            if name in selected:
                if not source or not re.fullmatch(r'package/(?:[A-Za-z0-9_+.-]+/)+Makefile', source):
                    raise ValueError('Unexpected SDK recipe path')
                if '..' in source.split('/'):
                    raise ValueError('SDK recipe traversal')
                if name in found and found[name] != source:
                    raise ValueError('Ambiguous selected SDK package: ' + name)
                found[name] = source
    # Kernel dependencies are accounted for separately by the IPK collector.
    # Generic base-files performs board/signing work, not userspace packaging.
    result = sorted({path.removesuffix('/Makefile') + '/compile'
        for name, path in found.items()
        if name != 'kernel' and not name.startswith('kmod-') and
           not path.startswith(('package/kernel/', 'package/base-files/'))})
    if 'cgi-io' not in found or 'luci' not in found:
        raise ValueError('Selected LuCI/CGI runtime metadata missing')
    return result


if __name__ == '__main__':
    sdk = Path(sys.argv[1])
    print('\n'.join(recipes((sdk / '.config').read_text(), (sdk / 'tmp/.packageinfo').read_text())))
