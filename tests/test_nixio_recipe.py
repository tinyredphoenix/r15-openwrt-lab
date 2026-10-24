"""Reproduce real nixio recipe/submake TLS propagation without compiling it."""
from pathlib import Path
import shutil
import subprocess
import tempfile
import unittest

REPO=Path(__file__).parents[1]
FIXTURES=REPO/'tests/fixtures'

class NixioRecipeTests(unittest.TestCase):
    def test_openssl_reaches_actual_src_makefile_and_negative_control(self):
        with tempfile.TemporaryDirectory() as tmp:
            root=Path(tmp);feed=root/'feed';package=feed/'libs/luci-lib-nixio';src=package/'src';src.mkdir(parents=True)
            (root/'rules.mk').write_text('')
            # Reproduce the SDK reset followed by LuCI's normal PIC append.
            (feed/'luci.mk').write_text('''MAKE_VARS = CFLAGS="-DTEST_DEFAULT_FLAGS"
MAKE_VARS += FPIC="-fPIC"
.PHONY: show
show:
\t@$(MAKE_VARS) $(MAKE) -s -n -C src NIXIO_SHADOW=yes CC=cc compile
''')
            shutil.copyfile(FIXTURES/'nixio-recipe-e4c4633.mk',package/'Makefile')
            shutil.copyfile(FIXTURES/'nixio-src-e4c4633.mk',src/'Makefile')
            for name in 'nixio socket sockopt bind address protoent poll io file splice process syslog bit binary fs user tls-crypto tls-context tls-socket'.split():
                (src/(name+'.c')).write_text('/* inert dry-run prerequisite */\n')
            def commands():
                result=subprocess.run(['make','-s','show','TOPDIR='+str(root),'CONFIG_PACKAGE_luci-lib-nixio_openssl=y'],cwd=package,text=True,capture_output=True)
                self.assertEqual(result.returncode,0,result.stderr)
                return result.stdout
            before=commands()
            self.assertIn('-DNO_TLS',before)
            self.assertNotIn('-lcrypto',before)
            subprocess.run(['patch','-p1','-i',str(REPO/'patches/901-nixio-export-tls-provider.patch')],cwd=feed,check=True,capture_output=True)
            after=commands()
            self.assertNotIn('-DNO_TLS',after)
            self.assertIn('tls-crypto.o',after)
            self.assertIn('-lssl -lcrypto',after)
            self.assertIn('-DTEST_DEFAULT_FLAGS',after)
            self.assertIn('-fPIC',after)
