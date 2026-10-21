#!/bin/bash
# Stage parsed FP6 Gen8.3 GMU descriptors and payload data; keep firmware out of git.
set -euo pipefail

case "${MACHINE_CONFIG:-}" in FP6) ;; *) exit 0 ;; esac
[[ -d bsd/dev ]] || exit 1
script_dir=$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)
cp "$script_dir/fp6_gmu_loader.h" bsd/dev/fp6_gmu_loader.h
[[ -f "$script_dir/fp6-gmu-fw.py" ]] || {
    echo "missing FP6 GMU firmware parser beside $0" >&2
    exit 1
}

if [[ -n "${FP6_GMU_SOURCE:-}" ]]; then
    python3 "$script_dir/fp6-gmu-fw.py" --source "$FP6_GMU_SOURCE" \
        --output bsd/dev/fp6_gmu_fw.h
else
    python3 "$script_dir/fp6-gmu-fw.py" --output bsd/dev/fp6_gmu_fw.h
fi
