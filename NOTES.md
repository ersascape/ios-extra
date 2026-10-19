# ios-extra — current state

Last updated 2026-10-19 after the 0093 phone test. Read [HANDOFF.md](HANDOFF.md) for how to
continue and [AGENTS.md](AGENTS.md) for the rules. The per-step history (images,
hashes, CI runs, raw numbers) is [docs/GPU_LOG.md](docs/GPU_LOG.md); the hardware and
mainline reference is [docs/GPU_GMU_BOOT.md](docs/GPU_GMU_BOOT.md); the per-patch
design is [docs/GPU_CX_EXPERIMENT.md](docs/GPU_CX_EXPERIMENT.md).

## What this repo is

Driver playground for the XNU/iOS 16 port to the Redmi Note 10 Pro (`sweet`,
SM7150, Adreno 618). The target is a real Adreno driver; the display today is
CPU-rendered. Public repo `dipa-studio/ios-extra`, branch `main`. The user made it
private overnight, then authorized restoring public visibility on 2026-10-19;
GitHub now confirms public. Kernel builds use this repo's GitHub Actions
(`.github/workflows/xnu.yml`, macOS runner, ~6 min).
`/home/dipa/ios-sweet` belongs to other agents: read-only for us.

## Where the GPU bring-up stands (all measured on the phone unless noted)

| Patch | `sweetgpu=` | What it does | CI run | Phone |
| --- | --- | --- | --- | --- |
| 0080 | 1 | read-only GCC/GPUCC clock + GDSC inventory | 39152959124 | ok |
| 0081 | 1 | cache that inventory, replay it over USB | 39154941656 | ok |
| 0082 | 2 | command-DB ARC level tables (`gfx/cx/mx.lvl`) | 39157726409 | ok |
| 0083 | 3 | MX+CX LOW_SVS votes via RPMh ARC, CX GDSC on/off, rollback | 39159151996 | ok |
| 0084 | 4 | GMU clock tree (GPLL0/2 gate, RCG 200 MHz, cx-gmu branch), rollback | 39161422925 | ok (first build refused: wrong precondition) |
| 0085 | 5 | GCC memnoc/ddrss-axi branches + first GMU register reads | 39162789741 | ok |
| 0086 | 6 | GMU firmware (`a630_gmu.bin`, staged at build) into ITCM/DTCM, readback | 39164168730 | ok, 0/8192 mismatches |
| 0087 | 7 | read-only GPU SMMU inventory | 39165446245 | ok |
| 0088-0089 | 8 | stream 5 -> CB3, tiny 4 KiB page table, ATOS check, restore (+ write transcript) | 39167833774 / 39168706195 | translations correct; S2CR3/CBAR3 refuse restore |
| 0090 | 9 | read-only RSC/PDC inventory | 39169517724 | ok |
| 0091 | 10 | mainline A618 RSC/PDC init (48 writes, readback), RSC stop handshake | 39170396365 | handshake ok, 9/48 writes did not read back |
| 0092 | 10 | same, logs every mismatch + reads the table first | 39171199100 | stop handshake ok; all 9 mismatches identified |
| 0093 | 11 | 13 GMU buffer pages, mainline HFI layout, 29 ATOS checks | 39293204273 **passed** | 29/29 ATOS; inactive=1, restored=0 |

The user confirmed the home screen after every boot up to 0092. Each stage runs
inside the previous one's window (`sweetgpu=N` includes all lower modes) and undoes
itself except: SMMU `S2CR3`/`CBAR3` (left inert: `SMR3` invalid, `SCTLR` 0), the
GMU RCG (left at `0x602`), and the RSC/PDC configuration of 0091 (left in place).

**The GPU core (GX) has never been powered and nothing has executed on the GPU.**
Rendering is still CPU. The GMU processor has never been released from reset.

## Immediate next action

0093 phone test passed the memory-map gate: all 29 ATOS checks match; final
SMR/S2CR/SCTLR/CBAR=0/3/0/0x10000, inactive=1, restored=0, FSR/sGFSR=0. Home-screen
confirmation is pending. Raw values and diagnostic limits are in GPU_LOG.
A saved CBAR value again carried dirty upper bits when logged as 64-bit; the actual
store was 32-bit low-word 0. 0094 normalizes narrow expected diagnostics without changing their MMIO value.

0094 implements HANDOFF step 3: a separate opt-in (`sweetgpu=12`) read-only dump
of 29 pre-boot GMU registers, with CM3 still reset and all earlier rollbacks intact.
Normal/sanitized host tests pass; arm64 compile passes. Full CI and phone pending. No GMU release or GX power
has occurred. 0093 source/build/image identity is recorded in GPU_LOG; isolated
source baseline is d3a6423 (validated 0093), with 0094 as its working diff.

## Hard constraints (unchanged)

- Always check `fastboot devices` (serials redacted) before asking for fastboot.
  If exactly one device is already there, announce and run the authorized pending
  temporary test; ask only when none is present, stop if multiple are present.
- Temporary `fastboot boot` only. No flashing, no partition/GPT changes, keep
  bootloaders, recovery, modem, persist and the backups. Never `fastboot getvar`.
  The user must put the phone in fastboot; never reboot it unannounced.
- Keep serials, device dumps and Apple artifacts out of Git. The GMU firmware is
  downloaded at build time (`xnu/patches/0086-stage-gpu-firmware.sh`), never committed.
- Report source reading, a green build and a phone result as three different things.

## Workspace map (outside Git)

`/run/media/dipa/android/ios-extra-work/`: `buildtree/xnu` (isolated XNU tree; local
git commits mark each CI-validated baseline, `sweet_gpu_fw.h` is untracked there),
`out-NNNN/` + `ci-NNNN/` (latest CI kernel and build tree), `gpu-fw/` (linux-firmware
clone `lf/`, mainline v6.12 sources, register xml), `logs/` (`phone-*.pcap/.txt`,
`ci-0081.log` which `tools/xnu-cc.py` needs, sanitized fastboot output), `objects/`,
`shim-out/` (symlinked as `shim/out`). Keep only the latest image/kernel; old ones are
reproducible from the manifests. 136 GB free on the external drive; the home disk is
small, so keep large files external.

## Tools (all tracked, `tools/`)

`gpu-package.py` (kernel -> temporary boot image + manifest), `gpu-phone-test.py`
(capture, boot once, replay window, decode), `gpu-decode-pcap.py` (UDP log from a
pcap), `phone-ecm-host.py` (host side of the USB ECM link), `xnu-cc.py` (single-file
arm64 compile against the CI build tree). Host tests: `python3 -W
error::ResourceWarning -m unittest discover -s tests` (also with
`IOS_EXTRA_CFLAGS="-fsanitize=address,undefined -fno-sanitize-recover=all -g"`).
