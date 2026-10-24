"""Compile actual procd method tables/registration with inert adapters."""
from pathlib import Path
import re
import shutil
import subprocess
import tempfile
import unittest

REPO=Path(__file__).parents[1]
FIXTURE=REPO/'tests/fixtures/procd-system-2cfc26f.c'
PATCH=REPO/'patches/900-r15-nonpid1-system-api.patch'
PRELUDE=r'''
#include <stdio.h>
#include <stdlib.h>
#include <string.h>
struct ubus_context { int unused; };
struct ubus_method { const char *name; };
struct ubus_object_type { const char *name; const struct ubus_method *methods; unsigned int n_methods; };
struct ubus_object { const struct ubus_object_type *type; const struct ubus_method *methods; unsigned int n_methods; };
static struct ubus_context *_ctx;
static int fake_pid, initramfs;
#define getpid() fake_pid
#define DEBUG(...) ((void)0)
#define ERROR(...) ((void)0)
#define getenv(...) NULL
#define unsetenv(...) ((void)0)
#define ARRAY_SIZE(x) (sizeof(x)/sizeof(x[0]))
#define UBUS_OBJECT_TYPE(name,methods) {name,methods,ARRAY_SIZE(methods)}
#define UBUS_METHOD_NOARG(name,handler) {name}
#define UBUS_METHOD(name,handler,policy) {name}
static int ubus_add_object(struct ubus_context *ctx, struct ubus_object *obj) {
 if(obj->n_methods!=obj->type->n_methods) exit(11);
 for(unsigned int i=0;i<obj->n_methods;i++) {
  if(strcmp(obj->methods[i].name,obj->type->methods[i].name)) exit(12);
  printf("%s\n",obj->methods[i].name);
 }
 return 0;
}
'''
MAIN=r'''
int main(int argc, char **argv) {
 struct ubus_context ctx; fake_pid=atoi(argv[1]); ubus_init_system(&ctx); return 0;
}
'''

class ProcdGuardTests(unittest.TestCase):
    def test_readonly_methods_outside_pid1_and_negative_control(self):
        compiler=shutil.which('cc')
        if not compiler:self.skipTest('C compiler unavailable')
        with tempfile.TemporaryDirectory() as directory:
            root=Path(directory);source=root/'system.c';shutil.copyfile(FIXTURE,source)
            def observe(name):
                text=source.read_text()
                tables=re.findall(r'static (?:const struct ubus_method system_(?:readonly_)?methods\[\]|struct ubus_object_type system_[a-z_]+) =.*?;\n',text,re.S)
                callback=re.search(r'void\s+ubus_init_system\([^\n]*\)\n\{.*?\n\}',text,re.S)
                self.assertIsNotNone(callback)
                obj='\nstatic struct ubus_object system_object={&system_object_type,system_methods,ARRAY_SIZE(system_methods)};\n'
                harness=root/(name+'.c');harness.write_text(PRELUDE+'\n'.join(tables)+obj+callback.group()+MAIN)
                binary=root/name
                result=subprocess.run([compiler,'-std=c99',str(harness),'-o',str(binary)],capture_output=True,text=True)
                self.assertEqual(result.returncode,0,result.stderr)
                return [subprocess.check_output([str(binary),str(pid)],text=True).splitlines() for pid in [1,2,993]]
            all_methods=['board','info','reboot','watchdog','signal','validate_firmware_image','sysupgrade']
            self.assertEqual(observe('unpatched'),[all_methods]*3)
            subprocess.run(['patch','-p1','-i',str(PATCH)],cwd=root,check=True,capture_output=True)
            self.assertEqual(observe('patched'),[all_methods,['board','info'],['board','info']])

            # A dispatch-only guard would still advertise the original ubus type.
            # Detect that regression using the real registration contract.
            patched=source.read_text()
            source.write_text(patched.replace('\t\tsystem_object.type = &system_readonly_type;\n',''))
            with self.assertRaises(subprocess.CalledProcessError):observe('dispatch-only-regression')
