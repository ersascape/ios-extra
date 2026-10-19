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
- Confirm hardware-write steps that are new in kind (the first write to a new block)
  with the user in one line; they have been approving by putting the phone in fastboot.
- Keep device serials, dumps, Apple files and downloaded firmware out of Git.
- Do not add Claude/Codex attribution to commits or docs. Commit messages describe
  the change only. Commit completed changes; push to `main` triggers the CI build.
- Say what you measured vs. what you only read. Do not estimate completion dates
  beyond "N more measured steps".
- Do not write product roadmaps or future-feature lists into NOTES/README.

## State in one paragraph

Patches 0080-0091 are built, phone-tested and documented; 0092 is built (CI
39171199100) and its image is ready but **not booted**. On the phone we have: CX rail
votes + CX power domain, GMU clock tree, GCC bus branches, readable GMU registers
(CM3 held in reset), the 32 KiB GMU firmware copied into GMU TCM and verified,
a readable GPU SMMU in which stream 5 -> context bank 3 with a hand-built 4 KiB page
table translates correctly under the SMMU's own ATOS, readable RSC/PDC registers, and
mainline's A618 RSC/PDC init executed (48 writes, 39 read back, RSC stop handshake
completed). We have **not**: allocated or mapped GMU buffers (HFI/log/debug), released
the GMU processor, powered GX, or run any GPU command. See `NOTES.md` for the table.

## Immediate next action (needs the user)

Ask the user to put the phone in fastboot, then run the 0092 image:

```sh
cd /home/dipa/ios-extra
python3 tools/gpu-phone-test.py \
  --image shim/out/shim-boot-0092-rpmhinit.img \
  --sha256 6fe97291353d16ac2edae5ee679599cf52c7e4e62fd1cb4ddf75408658a1f24c \
  --name phone-0092-rpmhinit
```

It checks the hash and that exactly one fastboot device exists, starts our own
tcpdump of the phone's UDP log (needs `sudo -n`), configures the host USB-ECM side,
boots once, waits for ping + the replay window, stops only its own tcpdump and
prints the `SWEET GPU:` lines (logs land in
`/run/media/dipa/android/ios-extra-work/logs/phone-0092-rpmhinit.{pcap,txt}`).
Look at: `RPMH table pre-write` (did the 0091 programming persist? which entries
differ), `RPMH init bad ...` (up to 16 refused writes), `RPMH init result`. If the
table already matches the mainline values the init is refused ("expected unprogrammed
state") by design — that itself is the answer (persistence).
Then ask whether the home screen came up, and record everything in `NOTES.md` +
`docs/GPU_LOG.md` (raw values, not just conclusions).

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
   per CI-validated baseline (latest `00095cd` = 0091; 0092 is the uncommitted diff).
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
> `fastboot getvar`, never reboot it unannounced. The next action is the pending 0092
> test (`tools/gpu-phone-test.py`, command in `HANDOFF.md`); ask the user for
> fastboot, run it, record the raw values, then continue with the numbered "Next
> steps", one measured patch per phone boot. Test every precondition, keep every
> experiment opt-in (`sweetgpu=N`) and rolled back, distinguish source reading /
> green build / phone result, and add no attribution text to commits or docs.
