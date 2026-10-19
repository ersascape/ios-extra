# ios-extra — current state

Last updated 2026-10-19 after 0092 phone result and 0093 local validation. Read [HANDOFF.md](HANDOFF.md) for how to
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
| 0093 | 11 | 13 GMU buffer pages, mainline HFI layout, 29 ATOS checks | 39293204273 **passed** | not booted |

The user confirmed the home screen after every boot up to 0092. Each stage runs
inside the previous one's window (`sweetgpu=N` includes all lower modes) and undoes
itself except: SMMU `S2CR3`/`CBAR3` (left inert: `SMR3` invalid, `SCTLR` 0), the
GMU RCG (left at `0x602`), and the RSC/PDC configuration of 0091 (left in place).

**The GPU core (GX) has never been powered and nothing has executed on the GPU.**
Rendering is still CPU. The GMU processor has never been released from reset.

## Immediate next action

0092 was temporarily booted at 16:55:16 UTC; ping and complete cached GPU report
received. The user confirmed the home screen. Raw values are in
[docs/GPU_LOG.md](docs/GPU_LOG.md). The 34/48 pre-write differences show the 0091
RSC/PDC configuration did not persist through this boot path. Nine mismatches:
RSCC hidden addresses +0x23034/3c/44 retain 0x82204514/10/20; six PDC MSGID words
read 0x10100 after 0x10108 writes. Stop handshake succeeds (0x01010006).

Step 1 interpretation is written in docs/GPU_GMU_BOOT.md: exact constrained
readbacks, ownership unresolved, stop handshake proven, wake/votes not proven.
0093 (`sweetgpu=11`) implements the separate GMU-buffer / 29-check ATOS test;
normal and ASan/UBSan host tests pass, local arm64 compile 0 of 1 files failed.
Source implementation commit `c053da3cfae8a4fe053499fee7ad01bb68b61cfd` is pushed.
The first CI run 39290944708 skipped while the repo was private overnight. With
public visibility restored at the user's request, full CI
[39293204273](https://github.com/dipa-studio/ios-extra/actions/runs/39293204273)
**passed** on `ab7a61da02cb91b0f87cf1a372939fabf73e3a59` (same patch/source).
CI GPU/RPMh source and staged firmware header match the isolated tree byte-for-byte;
kernel hash and GPU/RPMh symbols verified. Packaged/round-trip-verified image:
`shim/out/shim-boot-0093-gmubuffers.img`, SHA256
`dd4f6de48318e94e0dee5933467a998ec9ec6c90f352f9e050168b3202304f7a`.
**Not booted yet.** Asked the user for a new fastboot; once confirmed run:

```sh
python3 tools/gpu-phone-test.py --image shim/out/shim-boot-0093-gmubuffers.img \
  --sha256 dd4f6de48318e94e0dee5933467a998ec9ec6c90f352f9e050168b3202304f7a \
  --name phone-0093-gmubuffers
```

Require `buffers` checks=29/29, passed=29, inactive=1; distinguish restored=0
with only the known inert S2CR/CBAR difference from a rollback error. Capture every
raw PAR and write/readback from the first complete replay. Ask for home screen.

Source baseline in isolated XNU git: 60d4b0e (validated 0092).
Do not repeat 0092 or release CM3 merely because diagnostics completed.

## Hard constraints (unchanged)

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
