#!/usr/bin/env python3
"""Enable stderr diagnostics for selected launchd jobs during bring-up.

  patch-launchd-plist.py IN.plist OUT.plist LABEL [LABEL ...]

IN is /System/Library/xpc/launchd.plist (binary plist, read by launchd when
booted with launchd_unsecure_cache=1). For every job whose Label is given,
stdout/stderr go to /dev/null and the environment asks Apple's frameworks to
write diagnostics to stderr. Do not direct launchd jobs to /dev/console:
launchd cannot open it as the mobile user and refuses to spawn the job. On a
SWEET kernel, sweetnull=backboardd,SpringBoard tees those /dev/null writes to
the kernel console. Other kernels discard the redirected output.
OS_ACTIVITY_DT_MODE=YES enables os_log output on stderr and
CFLOG_FORCE_STDERR=1 enables CFLog/NSLog output there.

Every job's _PanicOnCrash key is also renamed (_PanicOnCrasX), so a crashing
daemon does not panic the system during bring-up.
"""
import plistlib, sys

LOG_ENV = {'OS_ACTIVITY_DT_MODE': 'YES', 'CFLOG_FORCE_STDERR': '1'}


def main():
    src, dst, labels = sys.argv[1], sys.argv[2], set(sys.argv[3:])
    with open(src, 'rb') as f:
        plist = plistlib.load(f)
    found = set()
    for job in plist['LaunchDaemons'].values():
        if '_PanicOnCrash' in job:
            job['_PanicOnCrasX'] = job.pop('_PanicOnCrash')
        label = job.get('Label')
        if label in labels:
            job['StandardOutPath'] = '/dev/null'
            job['StandardErrorPath'] = '/dev/null'
            job.setdefault('EnvironmentVariables', {}).update(LOG_ENV)
            found.add(label)
    missing = labels - found
    if missing:
        sys.exit(f'jobs not found: {", ".join(sorted(missing))}')
    with open(dst, 'wb') as f:
        plistlib.dump(plist, f, fmt=plistlib.FMT_BINARY)
    print(f'{dst}: bring-up diagnostics configured for {", ".join(sorted(found))}')


if __name__ == '__main__':
    main()
