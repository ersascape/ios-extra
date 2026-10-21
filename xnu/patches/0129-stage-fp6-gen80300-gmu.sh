#!/bin/bash
# Stage parsed FP6 Gen8.3 GMU descriptors and payload data; keep firmware out of git.
set -euo pipefail

case "${MACHINE_CONFIG:-}" in FP6) ;; *) exit 0 ;; esac
[[ -d bsd/dev ]] || exit 1
[[ -f patches/fp6-gmu-fw.py ]] || {
    echo 'missing copied FP6 GMU firmware parser in patches/' >&2
    exit 1
}

python3 patches/fp6-gmu-fw.py --output bsd/dev/fp6_gmu_fw.h
