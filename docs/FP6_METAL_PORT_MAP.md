# FP6 Adreno 810 → Metal: port map

Source inspection only unless marked **phone**. Linux references are the
`qualcomm-linux/kgsl` Gen8 sources used throughout `FP6_ADRENO_METAL_AUDIT.md`;
UniXNU references are the local checkout at `/home/ersa/Dev/UniXNU`.

## Measured so far (phone)

GMU/HFI start, default votes, GPU OOB, SQE start, CP init and a `CP_MEM_WRITE`
read back by the CPU (0188–0191; `NOTES.md`). All of it runs through a one-shot
raw-HFI probe in `bsd/dev/sweet_gpu.c`, with one global SMMU context (SID0/CB0,
TTBR1 global window). Nothing has been measured for per-process page tables,
registered contexts, context-queue submission, shaders or a draw.

## The stack that already exists (UniXNU)

`Metal API → NativeMetal → metal2vulkan (AIR→SPIR-V) → Turnip (Darwin KMD) →
NativeAdreno (IOKit) → GPU`, with `AirNir` as the offline AIR→NIR→IR3 path.
UniXNU reports a composited desktop on A740 (sheng); that is its claim, not an
FP6 observation.

## What is A7xx/A740-specific in NativeAdreno

| Area | A740 implementation | Gen8.3 / A810 (Linux source) |
|---|---|---|
| Submission | Ringbuffer, `a7xx_submit()` framing, `CP_EVENT_WRITE7` fences (`NativeAdrenoRing.cpp`, `NativeAdrenoSubmit.cpp`) | hwsched: per-context HFI registration, GMU context queue, `H2F_MSG_ISSUE_CMD` with IB list, doorbell via `GMUCX_HOST2GMU_INTR_SET` (`gen8_hwsched_submit_drawobj`) |
| Context | Ring-local | `H2F_MSG_REGISTER_CONTEXT` (ctxt id, flags, **TTBR0 | ASID**, context bank), then `H2F_MSG_CONTEXT_POINTERS` (SOP/EOP memstore addresses, GMU context-queue address) |
| Power/boot | A740 GMU/RPMh sequence (`NativeAdrenoPwrup*`, `A740HwInit.h`) | the sequence measured in `sweet_gpu.c` (HFI tables, votes, OOB) |
| Start-up registers | `A740HwInit.h` | APRIV (`0x0f`, BR `0x6f`), UCHE trap bases, `gen8_3_0_nonctxt_regs[]`: now in `sweet_gpu.c`; protect table and HWCG still not ported |
| Compiler target | `fd_dev_gen == 7`, chip `0x43050a01` (`kits/AirNir/MesaBackend.c`) | Mesa profile `Adreno (TM) 810`, chip `0xffff44010000`, `CHIP.A8XX` (pinned Mesa `6a7d302`); machine code is not interchangeable with A740 |

## Adreno work still required before Metal can run (ordered)

1. Per-process GPU page table: a TTBR0 domain on a context bank other than the
   global SID0/CB0 window, with ASID, and the HFI register message pointing at it.
2. Memstore and GMU context queue allocation; `REGISTER_CONTEXT` +
   `CONTEXT_POINTERS` ACKs (phone).
3. `ISSUE_CMD` carrying one IB that holds the `CP_MEM_WRITE` already proven,
   completed by the GMU and read back (phone). This replaces the ring.
4. A compute dispatch with a hand-assembled A8xx shader and readback, then a
   draw with readback (phone).
5. Remaining `gen8_start()` items: CP protect table, HWCG, power-up register
   list (`CP_ME_INIT` bit 8).
6. An IOKit client ABI for BO alloc/map, queue create, submit and fence wait that
   Turnip's `tu_knl_darwin.cc` can target for Gen8.3.

## Snapintosh (Gen8 reference, inspected 2026-10-23)

Source inspection of public MIT repos, shallow-cloned outside this tree
(`Acelogic/Snapintosh` `2c60b47`, `Snapintosh/SnapAdreno` `3985c26`,
`SnapMetal` `40a1864`, `air2ir3` `55865cc`). It boots Apple macOS 27 under an EL2
monitor on a Snapdragon X2 Elite (Adreno X2-90, a8xx, chip `0x44070041`), so it
targets macOS, not iOS, and a different a8xx part than the A810.

- **Kernel (`SnapAdreno`):** an IOGPU accelerator plus an IOMobileFramebuffer
  display driver. The GPU is powered and the GMU booted by an external host tool;
  the monitor/kext adopts a state with the GMU running, GPU OOB held, SQE
  started and one ring whose read/write pointers agree.
- **Submission:** a single ringbuffer, not hwsched context queues. Packets are
  written to the ring, `CP_RB_WPTR` is a fenced write (retry once if
  `GMU_AHB_FENCE_STATUS` bit 0 reports a dropped write), ring wrap is padded
  with `CP_NOP`, and the fence is a `CP_MEM_WRITE`. On a8xx it brackets work with
  `CP_THREAD_CONTROL` (BR thread, sync) and `CP_WAIT_FOR_IDLE`.
- **Metal (`SnapMetal`, `AdrenoMetal.bundle`):** a Metal device/command-buffer/
  encoder implementation emitting hand-written Adreno PM4, talking to the kext
  through IOGPU. 20k lines.
- **Shaders (`air2ir3`):** AIR → NIR → Mesa ir3 for a8xx via a pinned, patched
  Mesa; cache and binding ABI documented. Needs macOS tooling for its tests.
- **Licensing:** the repos are MIT, but the kext build also compiles
  `compat/adreno-ib-tables.h`, which is GPL-2.0-only (Linux-derived), making a
  built kext GPL-2.0. Read for design; do not copy that table into this tree.

Open question this raises for FP6: the GMU firmware here is the downstream
hwsched build (`gen80300_gmu.bin`); whether it also accepts a host-driven ring
the way Snapintosh's setup does is unmeasured. A small phone experiment (program
`CP_RB_*`, write one `CP_MEM_WRITE` to a host ring, fenced `CP_RB_WPTR`) would
answer it before committing to the context-queue path in step 1–3 above.

## Metal-side work, in dependency order

- AirNir: lift the `fd_dev_gen == 7` gate only together with an A8xx device
  profile and a qualified host build (LLVM 23.1.3, pinned Mesa, as
  `scripts/build-air-nir-host.py` requires). Removing the gate alone proves
  nothing about Gen8 machine code.
- Turnip A8xx: confirm the pinned Mesa creates an A810 device and compiles the
  shaders the desktop needs.
- NativeMetal / metal2vulkan: unchanged until a Gen8.3 NativeAdreno exists to
  run them; IOSurface import, presentation and shader coverage still need
  inspection.

No Metal code is validated on FP6 yet. The next measured step is item 1–3
above.
