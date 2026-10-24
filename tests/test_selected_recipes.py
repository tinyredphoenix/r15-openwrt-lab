import importlib.util
from pathlib import Path
import unittest

spec=importlib.util.spec_from_file_location('recipes',Path(__file__).parents[1]/'build/selected-recipes.py')
m=importlib.util.module_from_spec(spec);spec.loader.exec_module(m)
BASE='''Source-Makefile: package/feeds/luci/luci/Makefile
Package: luci
Source-Makefile: package/feeds/luci/cgi-io/Makefile
Package: cgi-io
'''
CONFIG='CONFIG_PACKAGE_luci=y\nCONFIG_PACKAGE_cgi-io=y\n'

class SelectedRecipesTests(unittest.TestCase):
    def test_only_selected_userspace_and_one_invocation_per_recipe(self):
        info=BASE+'''Source-Makefile: package/network/services/example/Makefile
Package: one
Package: two
Source-Makefile: package/base-files/Makefile
Package: base-files
Source-Makefile: package/kernel/mac80211/Makefile
Package: kmod-cfg80211
Source-Makefile: package/unselected/Makefile
Package: ignored
'''
        result=m.recipes(CONFIG+''.join('CONFIG_PACKAGE_'+p+'=y\n' for p in ['one','two','base-files','kmod-cfg80211']),info)
        self.assertEqual(result,['package/feeds/luci/cgi-io/compile','package/feeds/luci/luci/compile','package/network/services/example/compile'])

    def test_runtime_metadata_required(self):
        with self.assertRaises(ValueError):m.recipes('CONFIG_PACKAGE_luci=y\n',BASE)

    def test_traversal_or_shell_recipe_rejected(self):
        for path in ['package/../outside/Makefile','package/a;touch/Makefile','/tmp/Makefile']:
            with self.subTest(path=path),self.assertRaises(ValueError):
                m.recipes(CONFIG,BASE.replace('package/feeds/luci/cgi-io/Makefile',path))

    def test_ambiguous_recipe_rejected(self):
        with self.assertRaises(ValueError):
            m.recipes(CONFIG,BASE+'Source-Makefile: package/other/Makefile\nPackage: luci\n')

    def test_sdk_optional_modules_are_not_selected_for_runtime_build(self):
        info=BASE+'Source-Makefile: package/optional/Makefile\nPackage: optional\n'
        self.assertNotIn('package/optional/compile',m.recipes(CONFIG+'CONFIG_PACKAGE_optional=m\n',info))
