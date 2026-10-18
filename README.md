# ios-extra

Driver playground for [ios-sweet](https://github.com/dipa-studio/ios-sweet), the XNU / iOS port for the Redmi Note 10 Pro (`sweet`, SM7150). Made public with the user's approval on 2026-10-18.

Start experiments here, build and test them, then port working changes into `ios-sweet`. This repository has its own Git history and remote.

## Baseline

Imported the tracked files from `ios-sweet` commit [`347e190`](https://github.com/dipa-studio/ios-sweet/commit/347e19018e3e4c0117635e9e444f73659b2ece53) on 2026-10-18, including kernel patches **0001–0079**, the boot shim and build tools. The original snapshot is local commit `919ebb5`.

Local workspace: `/home/dipa/ios-extra`. The existing `/home/dipa/ios-sweet` checkout remains the hardware bring-up reference. Device backups, Apple artifacts, compiled kernels and research build trees were not copied.

## Builds

The repository is public, so kernel patch pushes to `main` can build automatically. A manual build can also be started:

```sh
gh workflow run xnu.yml -R dipa-studio/ios-extra
gh run list -R dipa-studio/ios-extra --workflow xnu.yml
gh run download RUN_ID -R dipa-studio/ios-extra -n xnu-kernel -D xnu/out
```

The workflow retains a guard that skips macOS builds if the repository is made private again.

## Working here

- Read [NOTES.md](NOTES.md) for the current handoff and [AGENTS.md](AGENTS.md) for workspace rules.
- See [the architecture review](docs/ARCHITECTURE.md) for boot, driver interfaces, dependencies and remaining gaps.
- GPU work starts with [the Adreno 618 plan](docs/GPU_PLAN.md): hardware execution, userspace rendering and iOS integration milestones.
- [Probe 0080](docs/GPU_BRINGUP.md) documents the first implementation, register audit and build/test results.
- [Metal loading research](docs/GPU_API_RE.md) records the traced service-to-device-plugin interface in this iOS image.
- Preserve each experiment as a focused commit or branch. New kernel patches start at `0080`; check for upstream numbering changes before porting back.
- Record build IDs, tested boot images, logs and observed results. Keep source review, a successful build and a successful phone test distinct.
- Port selected changes upstream only after they work here and the user asks to integrate them.

The original [setup guide](docs/UPSTREAM_README.md) and [engineering history](docs/UPSTREAM_NOTES.md) are preserved as reference snapshots. Their repository commands refer to the original project and their status sections may be older than the code.
