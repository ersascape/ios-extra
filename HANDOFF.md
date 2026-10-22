# Handoff — continue the FP6 GPU bring-up

Current target: Fairphone 6 Adreno 810 Gen8.3. For the active GPU sequence and
current status, see the “Current FP6 GPU path” section at the top of `NOTES.md`.
The A618 notes and patch history below are historical reference material; use the
FP6 docs and `NOTES.md` for current source, build and phone state.

You are taking over an in-progress, hardware-in-the-loop driver bring-up. Read `AGENTS.md`, this
file top to bottom, `NOTES.md` (state), then `docs/GPU_GMU_BOOT.md`
(mainline reference + everything measured). `docs/GPU_LOG.md` is the full history.

## Goal and ground rules

Goal: a real Adreno 618 GPU driver for the user's iOS/XNU port, on a phone they own.
The work so far is a ladder of small, opt-in, fully rolled-back kernel experiments
(`sweetgpu=N`), each built by CI, booted once with a temporary `fastboot boot`, and
read from a UDP log. Keep that discipline: **one question per boot, measured result,
then the next question.** The user prefers slow and careful over fast and clever.

- Never flash, never touch partitions, never `fastboot getvar`. Boot images only via
  `fastboot boot`, only when the user has put the phone in fastboot (`fastboot
  devices` shows exactly one). Do not reboot the phone unannounced. Other agents also
  use the phone and `/home/dipa/ios-sweet`; do not edit that tree.
- **Always check fastboot first:** run `fastboot devices` with serials redacted
  before asking the user to enter fastboot. Exactly one already present means
  announce and run the authorized pending temporary test; ask only if none is
  present, stop if multiple are present. The test helper rechecks before boot.
- Confirm hardware-write steps that are new in kind (the first write to a new block)
  with the user in one line; they have been approving by putting the phone in fastboot.
- Keep device serials, dumps, Apple files and downloaded firmware out of Git.
- Do not add Claude/Codex attribution to commits or docs. Commit messages describe
  the change only. Commit completed changes; push to `main` triggers the CI build.
- Say what you measured vs. what you only read. Do not estimate completion dates
  beyond "N more measured steps".
- Do not write product roadmaps or future-feature lists into NOTES/README.

## Active FP6 GPU state (2026-10-22)

Patch 0159 remains the latest built and phone-tested source: CI `39766804611`
passed and its packaged image booted once. The phone reported
`HFI CORE_FW_START timeout/fault irq=0x4 fw=0x900`; Linux identifies bit 2 as
DBGQ and FW_INIT_RESULT mask `0xe00` as a firmware assertion. The bounded probe
verified CM3 reset. The debug queue payload was not captured. Source inspection
found Linux sends scratch, perf/BW tables and optional feature/log controls
before CORE_FW_START, while patch 0159 sent that command immediately after HFI
controller initialization.

Patches 0160 and 0161 passed CI and were packaged; neither has a phone result.
Patch 0161 dispatches GMU counter and MEM_ALLOC events but refuses allocation.
The local 0162 candidate services only non-secure GMU-only MEM_ALLOC: permanent
kernel backing, live page-table append, cache clean, context TLBIALL/TLBSYNC,
and a Linux-shaped HFI ACK. GPU-access, secure, fence, fixed-MMIO and unsupported
large-alignment requests still reset CM3 safely. Normal and ASan/UBSan host
protocol tests pass, including one successful synthetic GMU-only request and a
GPU-access refusal; the changed source compiles to an arm64 object against CI
buildtree `39775328855` (`0 of 1 files failed`). This does not reveal the phone's
actual descriptor or prove firmware acceptance. CI run `39786196862` failed on
Apple Clang's rejection of a declaration immediately after a C label. The
response buffer is now declared before the label. Corrected commit `4a14fe7`
passed CI `39787950216`; verified kernel SHA256 is
`6d35acc9772c0b0cc740d409505016fd23c5267d230a923a830ca15561678934`. Automatic
image packaging skipped because `FP6_STOCK_DTB_URL` is unset, so the kernel was
locally packaged with the verified product ADT/stock DTB as
`/tmp/ios-extra-run-39787950216/package/fp6-gmu-hfi-memalloc-0162.img`, SHA256
`30fc97daccfa67230e2f2bedac463591b2f310e285b9ac0c2d1fbc1730ed502d`. Header-v2
round-trip passed. No 0162 phone test exists. The user is testing Android, so
defer all device commands. No GPU execution has been demonstrated.

- Work in this checkout on `main`; remote is `ersascape/ios-extra`. The goal is
  FP6 Adreno 810 GMU firmware/HFI, then bounded GPU execution and an A810 Metal
  path. `NOTES.md` and `docs/GPU_LOG.md` contain the full state and evidence.
- Commit `6c248dda7cc4b1fc7dae519898e41ef730de0282` passed CI run
  `39730474027`. Kernel SHA256 is
  `1dccb4fb5992417c37b73c28fc74d49e30c2f7dc8b3e2050fd5b8cfd08a02228`.
  Its temporary image was
  `/tmp/ios-extra-run-39730474027/package/fp6-gmu-timer-wcomb.img`, SHA256
  `f2b92b5fcfeb6af4e86a953dae8202b12abda5c1f700e8a9c59cd51d69137845`.
- Phone result: CX timer still refused `valid=0/16`, with `read=0..0` and
  `write=0..0`; all samples were discarded as backward. Firmware upload,
  SCM, CM3 release and HFI did not run. SMMU context test passed and remained
  contained. The matching pcap/text hashes and exact path are in `NOTES.md`.
- The current uncommitted follow-up (check `git status`) switches the timer
  sample source from raw CNTPCT to XNU's nonspeculative `ml_get_hwclock()`
  (CNTVCT) and records backward counts/raw samples. Host and sanitizer probes
  pass; system-Clang AArch64 compile against build 39730474027 reports 0/1
  failures. No CI or phone result exists for this follow-up yet.
- The USB test helper has also been changed to make one bounded `pkexec`
  authorization cover ECM setup, capture and cleanup; setup failures abort
  without retrying authorization. The previous root tcpdump may still be
  running. Pass its exact pcap path with `--stop-pcap` on the next test; the
  helper will stop only a tcpdump whose command line names that file.
- Next: run focused checks, commit/push the combined follow-up once, verify its
  single CI build and package a temporary image. Check `fastboot devices`
  immediately before the phone test; the prior boot means fastboot state is
  not assumed. Do not flash or use `fastboot getvar`.

## FP6 continuation update (2026-10-22)

The active branch has advanced past the timer follow-up above. Patch 0153 passed
CI `39745254929` and one phone test, as recorded at the top of `NOTES.md`.
Commit `0c5bd24` passed CI `39750406760`; its image failed closed before CM3
release because the BCM lookup incorrectly used ARC cmd-db ID 3. Commit
`4f68fcb` changed it to BCM ID 5, passed CI `39752494051`, and was packaged as
`/tmp/ios-extra-run-39752494051/package/fp6-gmu-bootstrap-ddr-vote-cmdb5.img`
(SHA256 `fe97c9fadae1388605b37124550677f596201c3f51bdc151afd6e80d4f835494`).
Patch 0155 passed CI `39755620038` and a temporary phone boot. SH0/MC0 BCM ID 5
validation succeeds, then the cmd-db parser reports missing ACV. It sends no vote
and keeps CM3 reset. Linux `cmd_db_get_header()` searches all populated slave IDs;
candidate patch 0156 mirrors that ordered lookup and passes its expanded host
fixture, but still needs CI and phone validation. Exact image/log evidence is in
`NOTES.md` and `docs/GPU_LOG.md`. Do not assume fastboot. This is not GPU
execution: HFI traffic, GMU DMA, GPU command execution and Metal remain
unimplemented.

## State in one paragraph

The material below is historical ios-sweet 0080–0098 handoff context, not the
active FP6 continuation. Use the active state above and NOTES.md for current work.

Patches 0080-0092 are built and phone-tested. 0092 was temporarily booted on
2026-10-19 at 16:55:16 UTC; the user confirmed the home screen. It reproduced all
nine constrained RSC/PDC readbacks and a successful stop handshake (0x01010006).
The init state did not persist through this boot path. Raw report in GPU_LOG;
step 1 interpretation and limits in GPU_GMU_BOOT. CM3 remains held in reset and GX
has never been powered. 0093 passed its phone test at 17:43:38 UTC: all 29 ATOS checks, inactive=1,
restored=0 with the known inert S2CR/CBAR residue, FSR/sGFSR=0; raw values in GPU_LOG.
The user confirmed the home screen, but reports missing wallpaper and some white
Settings/widgets (see NOTES); cause unestablished. Continue GPU as requested.
0094 completed at 18:01:14 UTC; all 29 pre-boot registers read, home screen
confirmed. Post-stop REQ=0/ACK=1/SEQ_BUSY=1; power CTRL=0x09c40406, hysts=0x000a2710;
CM3 reset=1, version/busy/init=0. Raw dump in GPU_LOG; source interpretation in
GPU_GMU_BOOT. No CM3 release or GX power has occurred.

## Immediate next action

0095 completed at 18:18:46 UTC; user confirmed home screen. RSC wake ACK=3,
BUSY=0, stop STATUS=0x01010006, full sampled state restored, GX off and CM3 reset.
0096 passed at 18:39:28 UTC, home screen confirmed. Six read-only words:
AO_HOST_INTERRUPT_MASK=0, GMU2HOST_INTR_MASK=0, both pending statuses=0,
AO_AHB_FENCE_CTRL=0, RPMH_POWER_STATE=0x0f. Full CI 39303111412 passed on
edd2b796ed7ff02434c42942c490543c17f95456; verified artifacts/image in GPU_LOG.
0097 stopped at the strict first mask guard at 18:53:52 UTC: wrote AO mask
0xffffffff, got 0x3f, restored 0. Second mask untouched. All lower checks/cleanup
pass; user confirmed the home screen. Green CI 39305068882, source
01dbc6e5571eacdca32f7c0d60bc34ce0d77ab00. 0098 implements only this exact
measured AO tuple, keeps writing all ones, then tests the second mask (mode 15).
Normal/sanitized host suites and arm64 object compile pass. Full CI/artifact
verification/package/phone remain. No 0098 image or phone result yet. Still no CM3
release. Read the raw report and source interpretation in GPU_LOG.

The larger first-start draft is only external (`gmu-first-start-draft.patch` under
`ios-extra-work`, based on 0095). It had an arm64 object compile, but no host tests,
full CI or phone validation. It omits interrupt protection and must not be applied
unchanged. Use the measured IRQ/fence values and finish both mask proofs before revising the
bounded CM3-start patch. Also resolve SMMU global-fault interrupts (see below). No first-start image exists; CM3 has never run.

## Exact continuation for 0098

The user is stopping for the usage limit. **Do not boot again in this session.**
On resume, check **CI 39307039113**, source **edab65c998a917d5e450b730aa4d0ff2e8e6032e**:
`gh run view 39307039113 -R dipa-studio/ios-extra --json status,conclusion,headSha`.
It was in progress when documented; no green result is claimed. Do not treat
local tests or a queued run as a green build. Once green, download `xnu-kernel`
and `xnu-buildtree` to `ios-extra-work/{out-0098,ci-0098}`; verify SHA256SUMS,
byte-compare GPU/firmware-header/RPMh sources with the isolated tree, and check
both symbols. Then package using the **CI's head SHA**, not a later docs commit:

```sh
python3 tools/gpu-package.py --kernel /run/media/dipa/android/ios-extra-work/out-0098/kernel.development.sweet --patch 0098 --mode 15 --name irqmask --ci-run 39307039113 --commit edab65c998a917d5e450b730aa4d0ff2e8e6032e
```

Only after verification/package, always check `fastboot devices` with serials
redacted. If one is already there, announce/run the authorized temporary test;
otherwise ask for fastboot. Use `tools/gpu-phone-test.py` with
`shim/out/shim-boot-0098-irqmask.img`, the exact SHA from manifest-0098.json and
log name `phone-0098-irqmask`. Read report 1, record both raw mask writes/restores,
ask for home screen, then decide from the measured second-mask readback. Do not
assume that it accepts all ones just because the host model does.

First-start draft review (not validated or in a phone image):

- External draft SHA256 028a3c1ba51a043a82cd20c9c7f8b9f6d86b497f8345df7e7e90ea0262bfd0a2,
  based on 0095; detailed external `gmu-first-start-draft-notes.txt` preserved.
- Add source masks before release; snapshot status, reset CM3 immediately after
  the bounded FW_INIT poll, then clear/restore/unmask in tested order. W1C clear
  writes are new and need source offsets and failure coverage.
- A failed reset must not fall through normal SMMU/clock/CX cleanup while claiming
  quiescence. Choose/test explicit containment through every cleanup layer. Keep
  DMA backing permanent; do not copy logs or reuse RAM while the master may run.
- Clean/invalidate before DMA, no CPU buffer access while running, reset/quiesce
  then invalidate/copy the log. Static log storage; no 16 KiB stack allocation.
- SMMU global sCR0 GFIE/GCFGFIE bits 2/5 are set in 0x00200626; context CFIE is
  clear in SCTLR=0x27. GMU masks do not cover unmatched-stream global faults.
  Preserve fault recording/translation and measure containment before first DMA.
  pe_fiq.c does not clear inherited SPI enables; GIC Group 1 alone proves nothing
  about individual sources. No new GIC or sCR0 write has been made.
- All per-write failures, exact cached/live preconditions, second-map failure,
  release/init timeout, reset failure, log validity and every unwind need host
  tests. Single-file draft compilation is not full validation.

## Next steps (each is its own measured patch; do not merge steps)

1. **RSC/PDC readback diagnosis — 0092 measured and documented.** Three hidden
   addresses retain existing routing values; six MSGID words lose length bit 3.
   Ownership (fixed hardware vs secure/EL2 filtering) is unresolved, so do not
   claim bare-metal mainline would necessarily read the same. Exact signatures
   and limits are in `docs/GPU_GMU_BOOT.md`; stop completes. 0095 subsequently proved wake/stop.
2. **GMU buffers — 0093 measured.** Dummy 4 KiB at IOVA 0x60000000, debug/log/HFI
   16 KiB each at 0x60001000/0x60005000/0x60009000, mainline legacy HFI layout.
   ATOS passes both ends of all 13 pages and three faults (29 checks). Map is
   disabled before cleanup; S2CR3/CBAR3 retain only the known inert encodings.
3. **Read-only pre-boot dump — 0094/0096 measured; 0097/0098 test IRQ masking.**
   All 29 original offsets readable;
   nonzero stopped-state ACK/BUSY and power-control/hyst defaults recorded.
   CM3 remains reset. See GPU_LOG for raw values, GPU_GMU_BOOT for interpretation.
4. **0095 RSC wake/stop measured and fully restored (CM3 held reset).**
   After both GMU mask/restore proofs (0097 stopped; 0098 pending) and SMMU
   global-fault containment, **GMU start, one bounded attempt** (mainline steps 2-12 in the doc): TCM retention,
   RSCC wake handshake (`REQ=BIT(1)`, ACK bit 1, `SEQ_BUSY`==0), fw (already done),
   boot config, HFI table address, fence range, `CM3_CFG=0x4052`, chip id, log
   address, power config, then `SYSRESET` 1 -> 0 and poll `FW_INIT_RESULT` (10 ms
   bound). Record `FW_INIT_RESULT`, `FW_BUSY`, `GENERAL_*`, the AO interrupt status and
   the log buffer contents. **Always** end by writing `SYSRESET=1` again, then the
   existing rollbacks. The ordering of reads/writes and the exact expected init word
   (`0xbabeface` vs `(x & 0x1ff)==0x100`) depend on the firmware version word at GMU
   `+0xAFE0`; read it and decide, do not assume.
5. Only after the GMU boots and idles cleanly: GX power-up (GMU-driven OOB
   `BOOT_SLUMBER` / GX vote indexes), HFI messages, SQE/CP microcode
   (`a630_sqe.fw`, 34188 bytes, same linux-firmware commit), secure-zap question,
   then the first CP command that writes a value to memory.
6. Much later (not started, no code): the iOS-side Metal plugin boundary traced in
   `docs/GPU_API_RE.md` / `docs/GPU_EXTERNAL_DRIVERS.md`.

If a step hangs or faults the boot, the phone returns to fastboot after a power cycle;
the persistent log (`tools/sweet-log-pull.sh` from recovery) and the "reading X"
announce lines are the evidence. Make the next build smaller, not bigger.

## How to implement a step (the loop)

1. Edit `bsd/dev/sweet_gpu.c` (and, if needed, `sweet_rpmh.c`) in the **isolated tree**
   `/run/media/dipa/android/ios-extra-work/buildtree/xnu`. Its local git has one commit
   per CI-validated baseline (latest `c242eb7` = measured 0097; isolated source has the 0098 diff,
   committed as a patch in main at `edab65c`).
   Before starting a new step, commit the validated state there:
   `git add -A bsd/dev/sweet_gpu.c && git -c user.name=ios-extra -c
   user.email=ios-extra@localhost commit -m "Validated 009N baseline"`. The untracked
   `bsd/dev/sweet_gpu_fw.h` is generated by `xnu/patches/0086-stage-gpu-firmware.sh`
   (run it from that tree with `MACHINE_CONFIG=SWEET`).
2. Compile for arm64 against the CI headers:
   `W=/run/media/dipa/android/ios-extra-work; XNU_CC_OBJDIR=$W/objects python3
   tools/xnu-cc.py $W/logs/ci-0081.log $W/buildtree bsd/dev/sweet_gpu.c` — must say
   `0 of N files failed`.
3. Write the patch: `git diff > xnu/patches/00NN-<name>.patch` in the isolated tree
   (diff against the previous baseline commit; regenerate after *every* later edit —
   the host tests apply the patch files, not your working copy; check with
   `git diff | cmp - xnu/patches/00NN-*.patch`).
4. Extend `tests/test_gpu_probe.py` (the C harness `#include`s the real
   `sweet_gpu.c` built from the patches, with simulated MMIO: GCC/GPUCC arrays, GMU,
   SMMU incl. an ATOS walker, PDC) and `tests/test_rpmh_arc.py`. Add refusal cases:
   every precondition must have a test proving *nothing is written* when it fails.
   Run normally and with `IOS_EXTRA_CFLAGS="-fsanitize=address,undefined
   -fno-sanitize-recover=all -g"`.
5. Update `docs/GPU_CX_EXPERIMENT.md` (design), commit, `git push`. CI starts
   automatically on pushes touching `xnu/patches/**`. Watch with
   `gh run watch RUN -R dipa-studio/ios-extra`; a green run takes ~6 min.
6. Download: `gh run download RUN -R dipa-studio/ios-extra -n xnu-kernel -D
   $W/out-00NN` (check `SHA256SUMS`) and `-n xnu-buildtree -D $W/ci-00NN`; extract
   `bsd/dev/sweet_gpu.c` from `buildtree.tgz` and `cmp` it with the isolated tree
   (proves CI built exactly what you tested); verify `llvm-nm` (`~/swift/usr/bin`)
   shows `_sweet_gpu_probe` / `_sweet_rpmh_arc_set`.
7. Package: `python3 tools/gpu-package.py --kernel $W/out-00NN/kernel.development.sweet
   --patch 00NN --mode N --name label --ci-run RUN --commit $(git rev-parse HEAD)`.
8. Boot: `tools/gpu-phone-test.py` as above. Record raw values, then prune old
   kernels/images (`out-*`, `ci-*`, `shim/out/shim-boot-*`) keeping the latest.

Commit message style: describe the change; no attribution lines. Docs and notes use
the user's words "home screen" for the boot confirmation they give.

## Pitfalls we hit (so you don't)

- A precondition based on an assumption failed once: `ahb`/`cxo` branches are already
  enabled by ABL (0084). **Measure first** with a read-only mode, then write.
- All results are printed after the whole experiment, from a cached snapshot (the USB
  logger replays it at ~5/15/30 s). A fault mid-experiment loses the cache; only the
  "reading X ..." lines printed just before risky reads reach the console ring.
  Whether they survive a bus fault is unverified.
- `pkill -f <path>` from a Bash tool kills your own shell (exit 144). Match by
  `/proc/<pid>/comm` + cmdline instead (what `gpu-phone-test.py` does).
- `raw.githubusercontent.com` returns 429 under load; use git.kernel.org plain URLs.
- Host test traps: the harness asserts barrier-instruction counts, so adding
  `gpu_read64`/`gpu_write64` changed the counts; simulated MMIO arrays start with a
  pattern (`0xa5…|index`), so tests that need "all zero" must clear the words they care
  about; the ATOS model treats any change of the ATS1PR word as a request.
- GR0/GR1 SMMU reads may return junk in the upper 32 bits (see the doc); mask to 32 bit.
- Writes that read back different values are information, not failures: log them.
- Always read the whole `SWEET GPU:` log from the *first* replay report; later
  reports are the same cached data.

## Prompt to paste into the new agent

> You are continuing a hardware bring-up of the Adreno 618 GPU for an XNU/iOS port on
> a Redmi Note 10 Pro. Work in `/home/dipa/ios-extra` (public repo
> `dipa-studio/ios-extra`). Read, in order: `AGENTS.md`, `HANDOFF.md`, `NOTES.md`,
> `docs/GPU_GMU_BOOT.md`; `docs/GPU_LOG.md` is history. Do not touch
> `/home/dipa/ios-sweet`. The phone is only ever booted with a temporary
> `fastboot boot` after the user puts it in fastboot; never flash, never run
> `fastboot getvar`, never reboot it unannounced. The next action is to verify the 0098 full CI build, package its image, then
> test it (`tools/gpu-phone-test.py`, command in `HANDOFF.md`); always check
> fastboot first, ask only if none is present, run it, record raw values, then continue with the numbered "Next
> steps", one measured patch per phone boot. Test every precondition, keep every
> experiment opt-in (`sweetgpu=N`) and rolled back, distinguish source reading /
> green build / phone result, and add no attribution text to commits or docs.
