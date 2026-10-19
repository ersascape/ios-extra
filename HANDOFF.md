# Handoff — continue the Adreno 618 bring-up

You are taking over an in-progress, hardware-in-the-loop driver bring-up. Read this
file top to bottom, then `AGENTS.md`, `NOTES.md` (state), `docs/GPU_GMU_BOOT.md`
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

## State in one paragraph

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

Split step 4 into a smaller bounded RSC wake/stop test first (new patch 0095,
mode 13), leaving CM3 held in reset. This checks ACK bit 1 and SEQ_BUSY=0 under
the exact known nine constrained readbacks before a firmware start. 0095 is implemented; all 57 precondition refusals, timeout/rollback/GX scenarios,
normal and sanitized host suites pass; local arm64 compile passes. CI-build and
package it next; no 0095 image/phone result yet.
Always check fastboot before asking for it. User confirmed 0094 home screen.

## Next steps (each is its own measured patch; do not merge steps)

1. **Understand the 9 refused RSC/PDC writes.** Decide from 0092 whether they are
   hardware-owned registers (ignore them, as mainline would observe the same) or
   something the hypervisor filters (then see whether the RSC sequencer still works:
   it did complete the stop handshake). Gate: a written explanation in
   `docs/GPU_GMU_BOOT.md`.
2. **GMU buffers.** Allocate (kernel contiguous memory, as `sweet_gpu.c` already does
   for the page-table test) dummy 4 KiB, debug 16 KiB, log 16 KiB, HFI 16 KiB; build
   the HFI queue table exactly as `a6xx_hfi_init` (layout in `docs/GPU_GMU_BOOT.md`);
   map them in the GMU context bank at IOVA `0x60000000` (dummy) and consecutive
   addresses from `0x60001000`; verify every page with ATOS; clean the CPU cache. Keep
   stream-5 matching but remember S2CR3/CBAR3 are already set (SMR3 invalid). Gate:
   ATOS returns the right physical page for every mapped page and faults elsewhere.
3. **Read-only pre-boot dump** of all GMU registers the start sequence will write
   (`docs/GPU_GMU_BOOT.md` table), so surprises show up before writing.
4. **GMU start, one bounded attempt** (mainline steps 2-12 in the doc): TCM retention,
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
   per CI-validated baseline (latest `85017d8` = 0094; 0095 is the uncommitted diff).
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
> `fastboot getvar`, never reboot it unannounced. The next action is the pending 0094
> read-only test (`tools/gpu-phone-test.py`, command in `HANDOFF.md`); always check
> fastboot first, ask only if none is present, run it, record raw values, then continue with the numbered "Next
> steps", one measured patch per phone boot. Test every precondition, keep every
> experiment opt-in (`sweetgpu=N`) and rolled back, distinguish source reading /
> green build / phone result, and add no attribution text to commits or docs.
