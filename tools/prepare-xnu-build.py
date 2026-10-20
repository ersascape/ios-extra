#!/usr/bin/env python3
"""Prepare the pinned macOS 13.5 build harness with a strict patch series."""
from pathlib import Path
import argparse
import shutil

ROOT = Path(__file__).resolve().parents[1]
UPSTREAM = {'kas_info.patch', 'machine_routines.patch',
            'skywalk_ventura.patch', 'syntax_checker_ventura.patch'}


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('directory', type=Path)
    args = parser.parse_args()
    patch_dir = args.directory / 'patches'
    missing = UPSTREAM - {p.name for p in patch_dir.glob('*.patch')}
    if missing:
        raise SystemExit(f'pinned harness patches missing: {sorted(missing)}')
    # Other harness patches target Monterey/Sonoma or duplicate our TrustCache stub.
    for path in patch_dir.glob('*.patch'):
        if path.name not in UPSTREAM:
            path.unlink()
    for pattern in ('*.patch', '*.sh'):
        for path in (ROOT / 'xnu/patches').glob(pattern):
            shutil.copyfile(path, patch_dir / path.name)
    script = args.directory / 'build.sh'
    text = script.read_text()
    old = 'warning "Skipping patch ${PATCH} (already upstream, previously applied, or malformed): ${APPLY_CHECK}"'
    if text.count(old) != 1:
        raise SystemExit('pinned harness patch loop changed')
    text = text.replace(old, 'error "Required patch failed: ${PATCH}: ${APPLY_CHECK}"\n                exit 1')
    text = text.replace('ARCHS="x86_64 arm64e" VALID_ARCHS="x86_64 arm64e"',
                        'ARCHS="x86_64 arm64e arm64" VALID_ARCHS="x86_64 arm64e arm64"')
    script.write_text(text)
    print(f'Prepared {len(list(patch_dir.glob("*.patch")))} required patches; failures abort the build')


if __name__ == '__main__':
    main()
