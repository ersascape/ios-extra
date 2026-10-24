#!/usr/bin/env python3
"""Generate the XNU patches that add the AdrenoGPU sources (drivers/adrenogpu) to the kernel.

  make-adrenogpu-patch.py [--check] [OUT.patch]     the cores, patch 0221 (the default)
  make-adrenogpu-patch.py [--check] --all           every patch below, written to xnu/patches

  0221  adrenogpu_vm, _ctx, _ring, _sched  -> bsd/dev, bsd/conf/files
  0224  adrenogpu_dev (the device core)    -> bsd/dev, bsd/conf/files
  0225  the IOKit shell AdrenoGPU.cpp and adrenogpu_iokit.h -> iokit/Kernel/arm, bsd/dev, iokit/conf/files.arm64

The sources in drivers/adrenogpu are the single source: each patch adds them as new files and registers the
compilation units. `--check` compares the checked-in patch with what the sources would produce
(tests/test_adrenogpu_patch.py does the same). Patches 0224 and 0225 apply on top of 0221.
"""
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
DRIVER = ROOT / 'drivers' / 'adrenogpu'
CORES = ['adrenogpu_vm.h', 'adrenogpu_vm.c', 'adrenogpu_ctx.h', 'adrenogpu_ctx.c',
         'adrenogpu_ring.h', 'adrenogpu_ring.c', 'adrenogpu_sched.h', 'adrenogpu_sched.c']
DEFAULT_OUT = ROOT / 'xnu' / 'patches' / '0221-adrenogpu-cores.patch'

FILES_HUNK = """diff --git a/bsd/conf/files b/bsd/conf/files
--- a/bsd/conf/files
+++ b/bsd/conf/files
@@ -115,6 +115,10 @@
 bsd/dev/qcom_geni.c\t\t\tstandard
 bsd/dev/fp6_touch.c\t\t\tstandard
 bsd/dev/fp6_keys.c\t\t\tstandard
+bsd/dev/adrenogpu_vm.c\t\t\tstandard
+bsd/dev/adrenogpu_ctx.c\t\t\tstandard
+bsd/dev/adrenogpu_ring.c\t\t\tstandard
+bsd/dev/adrenogpu_sched.c\t\t\tstandard
 bsd/dev/mem.c\t\t\t\tstandard
 bsd/dev/munge.c \t\t\toptional config_requires_u32_munging
 bsd/dev/unix_startup.c\t\t\tstandard
"""


DEV_CORE = ['adrenogpu_dev.h', 'adrenogpu_dev.c']
DEV_HUNK = """diff --git a/bsd/conf/files b/bsd/conf/files
--- a/bsd/conf/files
+++ b/bsd/conf/files
@@ -119,6 +119,7 @@
 bsd/dev/adrenogpu_ctx.c\t\t\tstandard
 bsd/dev/adrenogpu_ring.c\t\t\tstandard
 bsd/dev/adrenogpu_sched.c\t\t\tstandard
+bsd/dev/adrenogpu_dev.c\t\t\tstandard
 bsd/dev/mem.c\t\t\t\tstandard
 bsd/dev/munge.c \t\t\toptional config_requires_u32_munging
 bsd/dev/unix_startup.c\t\t\tstandard
"""
# (source in drivers/adrenogpu, destination in the XNU tree)
SHELL = [('adrenogpu_iokit.h', 'bsd/dev/adrenogpu_iokit.h'), ('AdrenoGPU.cpp', 'iokit/Kernel/arm/AdrenoGPU.cpp')]
SHELL_HUNK = """diff --git a/iokit/conf/files.arm64 b/iokit/conf/files.arm64
--- a/iokit/conf/files.arm64
+++ b/iokit/conf/files.arm64
@@ -15,6 +15,7 @@
 iokit/Kernel/arm/SweetWatchdog.cpp                               optional iokitcpp
 iokit/Kernel/arm/SweetSurface.cpp                                optional iokitcpp
 iokit/Kernel/arm/SweetFramebuffer.cpp                            optional iokitcpp
+iokit/Kernel/arm/AdrenoGPU.cpp                                   optional iokitcpp
 iokit/Kernel/arm/SweetBattery.cpp                                optional iokitcpp
 iokit/Kernel/arm/hid/SweetHID.cpp                                optional iokitcpp
 iokit/Kernel/arm/hid/IOHIDEvent.cpp                              optional iokitcpp
"""
DEV_OUT = ROOT / 'xnu' / 'patches' / '0224-adrenogpu-device-core.patch'
SHELL_OUT = ROOT / 'xnu' / 'patches' / '0225-adrenogpu-iokit-shell.patch'


def new_file_diff(name, dest=None):
    dest = dest or 'bsd/dev/' + name
    lines = (DRIVER / name).read_text().splitlines()
    body = ''.join('+' + line + '\n' for line in lines)
    return ('diff --git a/{d} b/{d}\nnew file mode 100644\n--- /dev/null\n+++ b/{d}\n'
            '@@ -0,0 +1,{c} @@\n{b}').format(d=dest, c=len(lines), b=body)


def generate():
    return ''.join(new_file_diff(n) for n in CORES) + FILES_HUNK


def generate_dev():
    return ''.join(new_file_diff(n) for n in DEV_CORE) + DEV_HUNK


def generate_shell():
    return ''.join(new_file_diff(src, dest) for src, dest in SHELL) + SHELL_HUNK


def main():
    args = sys.argv[1:]
    check = '--check' in args
    everything = '--all' in args
    args = [a for a in args if a not in ('--check', '--all')]
    if everything:
        jobs = [(DEFAULT_OUT, generate()), (DEV_OUT, generate_dev()), (SHELL_OUT, generate_shell())]
    else:
        jobs = [(Path(args[0]) if args else DEFAULT_OUT, generate())]
    for out, text in jobs:
        if check:
            if out.read_text() != text:
                raise SystemExit('%s is out of date; run tools/make-adrenogpu-patch.py' % out)
            continue
        out.write_text(text)
        print('wrote', out)


if __name__ == '__main__':
    main()
