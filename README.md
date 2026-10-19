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

- Read [HANDOFF.md](HANDOFF.md) to continue the work, [NOTES.md](NOTES.md) for the current state and [AGENTS.md](AGENTS.md) for workspace rules; [docs/GPU_LOG.md](docs/GPU_LOG.md) is the step-by-step history.
- See [the architecture review](docs/ARCHITECTURE.md) for boot, driver interfaces, dependencies and remaining gaps.
- GPU work starts with [the Adreno 618 plan](docs/GPU_PLAN.md): hardware execution, userspace rendering and iOS integration milestones.
- [Probe 0080](docs/GPU_BRINGUP.md) documents the first implementation, register audit and build/test results.
- [Inventory replay 0081](docs/GPU_REPORT_REPLAY.md) preserves the boot measurements and reprints them after USB configuration to recover missing early log lines.
- [ARC inventory 0082](docs/GPU_ARC_INVENTORY.md) adds an opt-in snapshot of GPU rail resource addresses and raw level tables, without power votes.
- [Per-patch design 0083-0092](docs/GPU_CX_EXPERIMENT.md): CX power, GMU clocks and registers, firmware in TCM, SMMU context + ATOS, RSC/PDC init, each opt-in and rolled back.
- [GMU boot reference](docs/GPU_GMU_BOOT.md): the mainline Linux start sequence for this GPU next to every value measured on the phone, address/offset tables and the remaining unknowns.
- [Power and firmware audit](docs/GPU_POWER_SEQUENCE.md) maps the A618 startup dependencies and the remaining ARC, GMU and SMMU contracts.
- [Metal loading research](docs/GPU_API_RE.md) records the traced service-to-device-plugin interface in this iOS image.
- [Asahi, NVIDIA and metal2vulkan audit](docs/GPU_EXTERNAL_DRIVERS.md) identifies reusable API/compiler pieces and the remaining iOS/Adreno integration work.
- Preserve each experiment as a focused commit or branch. New kernel patches start at `0080`; check for upstream numbering changes before porting back.
- Record build IDs, tested boot images, logs and observed results. Keep source review, a successful build and a successful phone test distinct.
- Port selected changes upstream only after they work here and the user asks to integrate them.

The original [setup guide](docs/UPSTREAM_README.md) and [engineering history](docs/UPSTREAM_NOTES.md) are preserved as reference snapshots. Their repository commands refer to the original project and their status sections may be older than the code.
