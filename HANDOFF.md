# Handoff — continue the FP6 GPU bring-up

Current target: Fairphone 6 Adreno 810 Gen8.3. For the active GPU sequence and
current status, see the “Current FP6 GPU path” section at the top of `NOTES.md`.
The A618 notes and patch history below are historical reference material; use the
FP6 docs and `NOTES.md` for current source, build and phone state.

You are taking over an in-progress, hardware-in-the-loop driver bring-up. Read `AGENTS.md`, this
file top to bottom, `NOTES.md` (state), then `docs/GPU_GMU_BOOT.md`
(mainline reference + everything measured). `docs/GPU_LOG.md` is the full history.

## Where things stand (2026-10-24) and what to do next

The GPU executes real draws on the phone. Read `NOTES.md` (top entries), `docs/ADRENOGPU_DESIGN.md` and
`drivers/adrenogpu/`. Short version:

- **Proven on the phone** (patches 0187 to 0220): GMU/HFI, ring, compute, a per-context TTBR0 address space
  at user addresses, Turnip A810 draws (flat, varying, UBO, blend, depth, textures, vertex and index fetch).
  All ten test scenes render exactly when the stream drains each draw (`TU_DEBUG=syncdraw`).
- **Root cause of the texture failures:** on this part the end-of-pass cache cleans do not wait for the last
  draw's fragments. The stream needs `CP_WAIT_FOR_IDLE`, then `CCU_CLEAN_COLOR/DEPTH` and `CACHE_CLEAN`,
  after a draw (`NOTES.md`, "wait for idle after the draw"). The PM4 builder's pass epilogue does this.
- **AdrenoGPU driver, host-tested cores** (`tests/test_adrenogpu*.py`): `adrenogpu_vm` (page tables, the
  exact descriptor the phone runs), `adrenogpu_ring` (submit framing), `pm4/adrenogpu_pm4` (restore sequence,
  A810 GMEM layout, sysmem pass begin, auto draw, drained pass end). The builder's state matches Turnip's
  A810 state for 134 of 174 registers at the draw; the rest is later pipeline state.

Milestones (details in the design doc): M1 VM core, M2 ring framing: done. M6 PM4 builder: restore, pass and
draw done; **next in M6** the load-action clear (2D engine blit, `emit_2d_clear` in Snapintosh's
`SharedPassState.m`), then shader program state (VS/FS registers from compiled shaders, `emit_program` in its
`ProgramState.m`), vertex fetch, UBOs and textures, each checked against `tools/fp6-pm4-state.py` on a Turnip
capture of the same scene. **Next in the driver:** M3 buffer and context objects on the kernel allocator,
M4 submit with fences, timeout and reset. M5 (the `AdrenoGPU` IOService and user client) exists as source and host
tests (patches 0224 and 0225, not enabled, never booted); what remains is the hardware backend in `sweet_gpu.c`
and a boot self-test, see "Kernel IOKit shell" in the design doc.
**Next on the phone:** put our own builder's flat triangle through the replay path (turn the builder's stream
and a shader blob into a replay entry), compare with the lavapipe grid, then retest the 576 KiB-fitting GMEM
layout (`tools/mesa-a810-sysmem-vpc.patch`) with the drain rule in place.

Host test and capture recipes (nothing here needs the phone):

```sh
python3 -m unittest discover -s tests -q                    # all host tests, including the C cores under ASan/UBSan
python3 tools/fp6-pm4-state.py CAPTURE.rd --regs drivers/adrenogpu/pm4/Fp6A8xxRegs.h   # register state at the draw
python3 tools/gen-a8xx-regs.py --mesa <mesa> --out drivers/adrenogpu/pm4/Fp6A8xxRegs.h # must reproduce byte for byte
```

Scene captures use Mesa at `6a7d3020a781` (`tu: Match SW depth clear value packing with HW`), kept outside `/tmp`
(a reboot clears it) in `~/Dev/mesa-a810` with its venv in `~/Dev/mesa-a810-venv`. Rebuild from nothing:

```sh
mkdir -p ~/Dev/mesa-a810 && cd ~/Dev/mesa-a810 && git init -q . && git remote add origin https://gitlab.freedesktop.org/mesa/mesa.git
git fetch --depth 1 origin 6a7d3020a781a191e21c35ed9410d9da73e0de4a && git checkout -q FETCH_HEAD
python3 -m venv ~/Dev/mesa-a810-venv && ~/Dev/mesa-a810-venv/bin/pip install meson mako pyyaml packaging ply
export PATH=~/Dev/mesa-a810-venv/bin:$PATH
meson setup build-vk -Dbuildtype=debugoptimized -Dvulkan-drivers=freedreno -Dgallium-drivers= -Dtools=freedreno,drm-shim \
  -Dfreedreno-kmds=msm -Dllvm=disabled -Dopengl=false -Dgles1=disabled -Dgles2=disabled -Dglx=disabled -Degl=disabled \
  -Dplatforms= -Dvulkan-layers= -Dvideo-codecs= && ninja -C build-vk
```

One tree gives everything: `build-vk/src/freedreno/vulkan/freedreno_devenv_icd.x86_64.json` (Turnip), `.../decode/cffdump`,
`.../drm-shim/libfreedreno_noop_drm_shim.so`, `.../computerator/computerator`. Host tools needed: ninja, glslangValidator,
a C compiler, the Vulkan loader. Then, per scene (scenes workspace `~/Dev/mesa-a810/scenes`):

```sh
W=~/Dev/mesa-a810/scenes M=~/Dev/mesa-a810
(cd tools/fp6-vk-scenes && sh build.sh $W/spv)                              # shaders to SPIR-V
gcc -I$M/include -o $W/fp6-vk-scenes tools/fp6-vk-scenes.c -lvulkan -lm
VK_DRIVER_FILES=/usr/share/vulkan/icd.d/lvp_icd.json $W/fp6-vk-scenes NAME $W/spv       # reference grid (lavapipe)
LD_PRELOAD=$M/build-vk/src/freedreno/drm-shim/libfreedreno_noop_drm_shim.so FD_GPU_ID=810 FD_RD_DUMP=enable,full \
  FD_RD_DUMP_PATH=$W/cap/NAME TU_GMEM=622592 TU_DEBUG=sysmem,noubwc,syncdraw \
  VK_DRIVER_FILES=$M/build-vk/src/freedreno/vulkan/freedreno_devenv_icd.x86_64.json $W/fp6-vk-scenes NAME $W/spv  # Turnip A810 capture
python3 tools/fp6-gen-replay.py OUT.h NAME:cap/NAME/*.rd:grid=REF.txt[:inject=KEYS][:post=KEYS] ...
```

Use `TU_DEBUG=...,syncdraw` for captures that must render correctly (the drain rule). `ir3` debug flags such as
`IR3_SHADER_DEBUG=nodescprefetch` are available for A/B variants. The kernel-side checks use a CI build tree:
`gh run download RUN -R ersascape/ios-extra -n xnu-buildtree`, extract, and
`gh run view RUN -R ersascape/ios-extra --log > ci.log`, then `python3 tools/xnu-cc.py ci.log BUILDTREE bsd/dev/FILE.c --per-file`.

The generated header becomes a patch against `bsd/dev/fp6_gpu_replay_data.h` (see patches 0216 to 0220 for the
pattern: stage the previous header in a scratch git repo, copy the new one in, `git diff` without the `index`
lines), the test list in `tests/test_gpu_probe.py` gets the new patch, CI builds, and the image is packaged with
`tools/fp6-package.py` (`--allow-no-product`, the stock DTB and the init ramdisk from an earlier run's package) and
booted once with `tools/gpu-phone-test.py --capture-mode user`. Boot arguments for replays:
`fp6pas=1 rd=md0 fp6usb=2 fp6smmu=2 fp6smmupower=1 fp6smmuirq=1 fp6gmuload=1 fp6gmuboot=1 fp6gmunopreempt=1
fp6gpuexec=1 fp6gpuring=1 fp6gpucompute=1 fp6gpureplay=1 fp6gpureplaycb=1`, plus `fp6gpureplayonly=PREFIX` and
`fp6gpureplayrepeat=N` to select captures. The kernel currently clears `CONCURRENT_BIN_DISABLE` in replayed streams
(`fp6gpureplaycb=1`); a stream our own builder produces should not contain it.

Open: the true A810 sysmem layout (Mesa's needs 608 KiB, the part has 576 KiB, and a smaller VPC layout drew
nothing for depth before the drain fix); interrupts, power management, unprivileged IB execution, faults and
recovery, several contexts; UBWC and GMEM-mode rendering. The project will later move to iOS 27 (SPTM and TXM),
so the driver must not need writable-executable memory or runtime kernel-text changes.

## Goal and ground rules

Goal: bring up the Fairphone 6 Adreno 810 (Gen8.3) from authenticated firmware
through GMU/HFI, GPU memory and command execution (write/readback and draw/readback),
then an A810-compatible Metal rendering path. Work in `/home/ersa/Dev/ios-extra-main`
on `main`, remote `ersascape/ios-extra`; use the user's current goal as authoritative.
Use one temporary `fastboot boot` per measured hardware question, capture USB logs,
and distinguish source, host, CI and phone evidence. Do not treat a software model as
device proof.

- Boot kernel images only via `fastboot boot`, only when exactly one phone is in
  fastboot. The user explicitly authorized one write of the identified Tegu iOS
  rootfs to `userdata` on 2026-10-22; it completed and must not be repeated.
  Never change GPT or write bootloader, boot, recovery, modem or persist. Never
  run `fastboot getvar`. Do not reboot the phone unannounced. Other agents also
  use the phone and `/home/dipa/ios-sweet`; do not edit that tree.
- **Always check fastboot first:** run `fastboot devices` with serials redacted
  before asking the user to enter fastboot. Exactly one already present means
  announce and run the authorized pending temporary test; ask only if none is
  present, stop if multiple are present. The test helper rechecks before boot.
- Confirm hardware-write steps that are new in kind (the first write to a new block)
  with the user in one line; they have been approving by putting the phone in fastboot.
- Keep device serials, dumps, Apple files and downloaded firmware out of Git.
- The display is a BOE NT37705 AMOLED (command mode). Do not risk burn-in or panel
  damage: display probes are read-only unless the user approves a specific write;
  never hold a static image, never send panel on-commands, reset the panel or change
  brightness/DSI/DPU timing without explicit confirmation of that step.
- Do not add Claude/Codex attribution to commits or docs. Commit messages describe
  the change only. Commit completed changes; push to `main` triggers the CI build.
- Say what you measured vs. what you only read. Do not estimate completion dates
  beyond "N more measured steps".
- Do not write product roadmaps or future-feature lists into NOTES/README.

## Current FP6 GPU state (2026-10-23)

Patch 0179 is built, CI-passed and phone-tested. Both Linux-matching default
HFI votes ACKed; GPU OOB returned ACK bit 31, and read-only `RBBM_STATUS`
returned `0x00000001`. This is the first measured OOB completion and GPU status
read. The bounded probe submitted no GPU command, then verified CM3 reset and
retained SID/context/clock votes. No GPU execution or GPU-master DMA/readback,
draw or Metal output has been measured yet. Exact CI, image and USB-log records
are in `NOTES.md` and `docs/GPU_LOG.md`.

The clock audit remains open: Linux starts GMU at 650 MHz then switches to
350 MHz after HFI, while XNU uses 350 MHz before firmware release. Patch 0179
did not change clocks; the successful OOB result means the next step can move
past diagnosis of the basic OOB timeout toward a bounded GPU/SQE startup and
command completion measurement, following the Fairphone Linux sequence.

Patch 0178 commit `7b13c1483a57d39abb63db3df9eb5b678635589d` passed CI
`39901607539`. CI kernel SHA256 is
`31a576142f70b0c10257a80b411fc8bfc8b2ab97dbc8c2753fd7f9cb55d1aabf`; ADT
SHA256 is `78b5c4022739f417881702d761b43bf2ca8ec10ebd00fe9584ce01c37b93a583`.
The CI buildtree source exactly matches the locally validated change. CI
skipped image packaging because `FP6_STOCK_DTB_URL` is unset. The exact kernel
and ADT were packaged with the verified stock DTB and the matching 16,635-byte
static init as
`/tmp/ios-extra-run-39901607539/package-correct/fp6-gmu-hfi-start-before-oob-0178.img`
(SHA256 `be2f2e9217db28ad2c1c53b70706614351c41dbbd5ced34aee1fe0cdf9e72618`).
One temporary `fastboot boot` succeeded with user-mode USB capture and ping;
no flash or EDL was used. The 96-packet decoded log and raw UDP are
`/tmp/ios-extra-run-39901607539/logs/phone-0178-hfi-start-before-oob.txt` and
`.udp`, both SHA256
`fe5ab3ff3e0ed8634bc4e8d1d7e60cf2113a6db4b60f380bf91f9e599cd10b64`.

Phone measured: HFI `START` request id 10, sequence 7, was ACKed before GPU
OOB. OOB still timed out; request bit 30 appeared transiently but no ACK
appeared. HFI queues were empty after processing, firmware remained alive, GX
stayed off, and CM3 reset was verified. No GPU command, DMA, memory
write/readback, draw or Metal output. The HFI/OOB ordering correction alone
does not fix the timeout. Source inspection shows the Gen8.3/A810 profile does
not enable GMU warmboot. Audit the remaining default-vote behavior and the GMU
clock/OOB prerequisites against FP6 Linux before the next patch. Phone is
currently in the temporary XNU boot; check `fastboot devices` before any next
test and request fastboot only if none is present.

## Historical FP6 GPU state at patch 0170 (2026-10-23)

Patch 0170 was the last measured run before 0173. CI `39842360411` passed, and the
header-v2 diagnostic image is
`/tmp/ios-extra-run-39842360411/package-correct/fp6-cb0-reinit-0170.img`
(SHA-256 `678ae82e3565a403f33abfa0b1ba6ae4629325637e918da158e9d087a15f90a8`).
The bounded `fastboot boot` succeeded and captured 113 UDP packets. Decoded log
and raw packet file are under `/tmp/ios-extra-run-39842360411/logs/`;
both have SHA-256
`8f4552a25b5c20f67db78e2620c3e9eaf851c07004b5e89d3197cccdeec50216`.
No flash or EDL command was issued. CM3 reset was verified. The phone remains
in the temporary XNU boot; no autonomous fastboot return has been tested.

Phone evidence: GMU firmware ran (`FW_INIT_RESULT=0x100`), HFI initialized,
and six HFI startup requests plus the bootstrap DDR vote were acknowledged.
The guarded CB0 takeover passed readback, SID0 was enabled on group 1, and the
SID5->CB2 route remained intact. XNU serviced the real GPU-access allocation
events for kinds 2, 14, 15, kind 1 (four buffers), 3 and 4, and GMU-only kind
16. It then stopped at kind 5 / flags `0x1007` / 3,670,016 bytes and reset CM3.
The allocation is secure preemption memory. Fairphone Linux maps it through
`kgsl_allocate_secure()` and transfers ownership to `VMID_CP_PIXEL` using
`hyp_assign_table()`; do not satisfy it with normal pages or clear its secure
flag. No HFI START ACK, GPU core boot, GPU DMA, command write/readback, draw or
Metal output has been measured.

Source review confirms Linux omits the HFI preemption control and skips
`gen8_preemption_init()` in its one-ring path when preemption is disabled.
Patch 0171 adds opt-in `fp6gmunopreempt=1`, preserving default A810
preemption. Host, sanitizer, full-suite and local arm64 compile checks pass.
Commit `3d05098ff1095f58ceec2769340f51a315f45f98` passed CI `39845816435`.
The rebuilt header-v2 image is
`/tmp/ios-extra-run-39845816435/repackage/fp6-hfi-no-preempt-0171.img`,
SHA-256 `bc489958ba715a53ccf4a8c489e3051600de6856ce38c9e89271fe06961a45da`.
Its one temporary phone boot reached the HFI `START` ACK without secure kind 5;
the bounded probe then reset CM3 before GPU core/SQE startup. The decoded USB
log and image details are at the top of `NOTES.md` and in `docs/GPU_LOG.md`.
This does not prove GPU execution. The next implementation boundary is Gen8.3
GPU/SQE startup after HFI start. Do not reboot the phone unannounced. Check
`fastboot devices` before asking the user, and require exactly one device before
the helper's single temporary boot. Continue using the ramdisk and `/tmp` logs.
No flash, `fastboot getvar`, or EDL commands.

The 2026-10-23 Linux SQE source review is recorded in
`docs/FP6_ADRENO_METAL_AUDIT.md`: KGSL strips the first four bytes of the raw
`gen80300_sqe.fw` header, copies the remaining payload into GPU-readable memory,
programs the SQE base, starts SQE, then sends CP init. The local pinned artifact
is only in `/tmp`; do not add it to Git. This is a source finding, not a measured
GPU start.

Historical patch-by-patch evidence and earlier image identities are in
`NOTES.md` and `docs/GPU_LOG.md`. The Linux bring-up/source audit is in
`docs/FP6_ADRENO_METAL_AUDIT.md`; `docs/GPU_GMU_BOOT.md` is A618-specific.

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
