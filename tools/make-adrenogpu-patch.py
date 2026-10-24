#!/usr/bin/env python3
"""Generate the XNU patch that adds the AdrenoGPU cores (drivers/adrenogpu) to the kernel.

  make-adrenogpu-patch.py [--check] [OUT.patch]

The cores in drivers/adrenogpu are the single source: the patch adds them as bsd/dev/adrenogpu_*.[ch] and lists
the .c files in bsd/conf/files. `--check` compares the checked-in patch with what the sources would produce
(tests/test_adrenogpu_patch.py does the same).
"""
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
DRIVER = ROOT / 'drivers' / 'adrenogpu'
CORES = ['adrenogpu_vm.h', 'adrenogpu_vm.c', 'adrenogpu_ctx.h', 'adrenogpu_ctx.c',
         'adrenogpu_ring.h', 'adrenogpu_ring.c']
DEFAULT_OUT = ROOT / 'xnu' / 'patches' / '0221-adrenogpu-cores.patch'

FILES_HUNK = """diff --git a/bsd/conf/files b/bsd/conf/files
--- a/bsd/conf/files
+++ b/bsd/conf/files
@@ -115,6 +115,9 @@
 bsd/dev/qcom_geni.c\t\t\tstandard
 bsd/dev/fp6_touch.c\t\t\tstandard
 bsd/dev/fp6_keys.c\t\t\tstandard
+bsd/dev/adrenogpu_vm.c\t\t\tstandard
+bsd/dev/adrenogpu_ctx.c\t\t\tstandard
+bsd/dev/adrenogpu_ring.c\t\t\tstandard
 bsd/dev/mem.c\t\t\t\tstandard
 bsd/dev/munge.c \t\t\toptional config_requires_u32_munging
 bsd/dev/unix_startup.c\t\t\tstandard
"""


def new_file_diff(name):
    lines = (DRIVER / name).read_text().splitlines()
    body = ''.join('+' + line + '\n' for line in lines)
    return ('diff --git a/bsd/dev/{n} b/bsd/dev/{n}\nnew file mode 100644\n--- /dev/null\n+++ b/bsd/dev/{n}\n'
            '@@ -0,0 +1,{c} @@\n{b}').format(n=name, c=len(lines), b=body)


def generate():
    return ''.join(new_file_diff(n) for n in CORES) + FILES_HUNK


def main():
    args = sys.argv[1:]
    check = '--check' in args
    args = [a for a in args if a != '--check']
    out = Path(args[0]) if args else DEFAULT_OUT
    text = generate()
    if check:
        if out.read_text() != text:
            raise SystemExit('%s is out of date; run tools/make-adrenogpu-patch.py' % out)
        return
    out.write_text(text)
    print('wrote', out)


if __name__ == '__main__':
    main()
