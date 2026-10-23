# FP6 Adreno authentication through Metal audit

Source inspection, 2026-10-21. No build or phone validation was performed by this audit.

## Hardware identity and firmware

The selected FP6 stock DT selects `qcom,adreno-gpu-gen8-3-0`, as recorded in
NOTES.md. Fairphone's local graphics-kernel `adreno-gpulist.h:2755` binds that
compatible to `adreno_gen8_hwsched_gpudev` and `gen80300_gmu.bin`,
`gen80300_sqe.fw`, `gen80300_zap.mbn`. Its GMEM is 576 KiB. A740/Gen7 register,
firmware, HFI and command-processor startup sequences cannot establish the FP6
sequence. The recorded phone PAS INIT_IMAGE/MEM_SETUP/AUTH_AND_RESET success is
an authenticated ZAP milestone; GMU execution and GPU command execution remain
unproven.

Fairphone reference files are under
`/home/ersa/Dev/android_kernel_fairphone_sm7635-modules/qcom/opensource/graphics-kernel`.
`gen8_hwsched_first_boot()` in `adreno_gen8_hwsched.c:997` reads SQE/AQE
microcode, initializes the GPU and GMU, boots GMU then boots GPU. Its
`gen8_hwsched_gmu_first_boot():430` establishes CX GDSC/clocks, AHB timeout
handling and CX timer, loads GMU firmware, performs SCM CX register setup,
configures GMU registers/interrupts/bandwidth, starts GMU and starts HFI.
`gen8_hwsched_gpu_boot():755` starts GPU MMU, asserts GPU OOB, programs core
state/interrupts/microcode and boots GPU through the hardware scheduler. This
is the appropriate sequence reference, with Linux services replaced explicitly
by XNU equivalents. Firmware staging alone implements none of those runtime
services.

## OOB prerequisite audit, 2026-10-23

The FP6 DT's selected `qcom,gpu-pwrlevels-0` profile sets
`qcom,initial-pwrlevel = <8>`; row 8 is 362 MHz and has DDR7/DDR8 bus frequency
index 2. Linux `gen8_hwsched_hfi_start()` sends HFI `START`, then
`gen8_hwsched_setup_default_votes()` sends a `GX_BW_PERF_VOTE` for the mapped
GPU performance index and a second vote for the default bus level before the
caller reaches `gen8_hwsched_gpu_boot()` and GPU OOB. Because the GMU-AB
capability query happens after `gen8_hwsched_hfi_start()` returns, the initial
votes use the invalid-AB encoding. XNU's 0178 log showed `START` ACK then OOB
with no intervening power-vote requests. Patch 0179 adds those two requests and
requires ACKs; host validation and local arm64 compilation pass. This is a
source-backed candidate, not proof that missing votes caused the OOB timeout.

The same source audit found that DT exposes GMU clock levels 350 and 650 MHz.
Linux's first-boot path selects `freqs[GMU_MAX_PWRLEVELS - 1]` (650 MHz), then
switches to `freqs[0]` (350 MHz) after HFI initialization. Current XNU selects
350 MHz before releasing CM3 and does not perform the 650-to-350 transition.
The HFI firmware has initialized successfully at 350 MHz in prior phone runs,
so this timing difference remains a separate untested prerequisite question;
no RCG/PLL change is included in 0179.

## Turnip is relevant to the actual FP6 GPU

Pinned upstream Mesa revision inspected:
`6a7d3020a781a191e21c35ed9410d9da73e0de4a`.
Its [freedreno_devices.py](https://chromium.googlesource.com/external/gitlab.freedesktop.org/mesa/mesa/+/6a7d3020a781a191e21c35ed9410d9da73e0de4a/src/freedreno/common/freedreno_devices.py)
contains `Adreno (TM) 810`, chip ID `0xffff44010000`, `CHIP.A8XX`, with A8xx
Gen1 properties and one CCU/slice. Therefore there is an upstream hardware
profile worth using; an Android binary or a fork claiming A810 support is not
needed as the initial architectural reference. Confirm the runtime chip ID
matches before selecting this profile. A profile entry alone proves neither
Vulkan conformance nor working rendering on this FP6 XNU port.

Mesa's same file explicitly says most A8xx non-context register programming
moves into the kernel. Turnip expects a functioning kernel GPU driver; it does
not authenticate firmware, power the GMU, construct the system SMMU ownership
policy or recover a dead GPU for us.

Mesa's [Freedreno documentation](https://chromium.googlesource.com/external/gitlab.freedesktop.org/mesa/mesa/+/6a7d3020a781a191e21c35ed9410d9da73e0de4a/docs/drivers/freedreno.rst)
identifies the shared shader compiler, image layout and register/command tools.
Reuse candidates include NIR transformations, IR3 compilation, A8xx device
properties, Vulkan pipeline/descriptor/image handling and command generation.
These should stay in userspace rather than being copied into early platform
initialization code.

## A Darwin backend already exists in UniXNU

Local UniXNU contains `patches/mesa/turnip-darwin-kmd.patch`, which adds
`tu_knl_darwin.cc`, Darwin enumeration and build integration. It uses an IOKit
NativeAdreno user client for BO allocation/import/mapping/cache ownership,
command submission and synchronization. This is much more useful than starting
an entirely new Linux ioctl emulation layer. It must be reviewed and adapted
to a pinned Mesa revision and our own kernel ABI.

Upstream [tu_knl.h](https://chromium.googlesource.com/external/gitlab.freedesktop.org/mesa/mesa/+/6a7d3020a781a191e21c35ed9410d9da73e0de4a/src/freedreno/vulkan/tu_knl.h)
defines the actual boundary: device facts/status/timestamps; queue create/close;
BO allocate/map/import/export/free and metadata; submission entries; queue
submission/wait; sparse VA operations. A first usable backend can explicitly
reject unsupported sparse/external-memory features and advertise only features
it implements. It must preserve correct memory visibility, lifetime and fence
semantics for every advertised operation.

NativeAdreno is explicitly an A740 driver in its README. Reusable parts include
ABI records, IOKit client dispatch, resource lifetime and memory/cache/fence
patterns. Replace A740 power, SMMU ownership assumptions, firmware/HFI, CP
initialization and GPU target facts with verified FP6 Gen8.3 implementations.
Do not copy its A740 board profile and call that FP6 support.

## Metal boundary

Local NativeMetal at `6dcd4cbb69eb5625988706de42aa8ad3009b8ee7` describes a
runtime path `Metal API -> metal2vulkan -> Turnip -> NativeAdreno` and publishes
through `MTLAddDevice`. Its README reports a composited desktop on sheng; that
is an upstream claim, not an FP6 observation. Inspect the integration,
IOSurface import, synchronization, presentation and system shader coverage
before adopting it.

Local AirNir at `032a867b5dc3121164bbd706e4e81e3b9fcd2b8f` explicitly describes
an offline AIR/metallib -> NIR -> A740 IR3 compiler and says it is not the
runtime path. Its parsing and interface/constant-state handling are research
inputs. Its generated A740 machine code must not be used as A810 code. A8xx
compilation should use the correct upstream device target and be validated on
the actual hardware.

## Implementation order and proof

1. Complete SMMU register programming and translation verification; distinguish
   context ATS verification from actual SID5/TBU or GMU accesses. Preserve the
   photographed readback failure as a real blocker, not a successful mapping.
2. Implement the Gen8.3 runtime memory, clocks/power, SCM setup, firmware upload,
   GMU start and HFI handshake. Require firmware-produced version/status and a
   command/reply before claiming GMU execution.
3. Implement Gen8.3 SQE/GPU initialization and hardware-scheduler submission.
   Verify GPU writes a known value to a mapped allocation and signals completion;
   then run a minimal draw/readback. Require bounded timeouts and retained fault
   state on failure.
4. Publish kernel BO/VA/queue/fence/cache ABI. Adapt the existing Darwin Turnip
   backend and run its buffer fill, compute and image draw/readback through that
   same ABI. Keep the A810 target explicit.
5. Integrate NativeMetal's frontend/translation and IOSurface presentation.
   Validate actual app and compositor shader/resource classes, then system UI
   presentation. A successful raw GPU draw or Vulkan triangle does not prove
   full Metal or SpringBoard support.

The immediate SMMU/GMU work remains necessary whichever userspace frontend is
chosen. Turnip meaningfully reduces the later compiler/rendering implementation;
it does not remove the current hardware startup task.

## Gen8.3 IOMMU and GPU boot ordering (source review, 2026-10-23)

Fairphone's `kgsl_iommu_setup_context()` allocates and attaches the GPU user
domain during KGSL IOMMU probe. `iommu_probe_user_context()` then creates the
default pagetable, installs its TTBR0 on the user context, and applies the
SMMU aperture before the first GMU boot. In contrast,
`kgsl_iommu_start()` runs later and mainly applies fault policy/PRR state; it is
not where Linux first constructs the context. This is consistent with the
FP6's GPU-reserved CB0 being distinct from the GMU's later CB2 test context,
but it does not identify who left the measured disabled CB0 register values.

The FP6 catalog selects `adreno_gen8_hwsched_gpudev`, so its cold-boot path is
the hardware-scheduler path. `gen8_hwsched_first_boot()` reads SQE firmware,
initializes Gen8 state, runs `gen8_hwsched_gmu_first_boot()`, then
`gen8_hwsched_gpu_boot()`. GPU boot starts the MMU, takes GMU GPU OOB, calls
`gen8_start()`, enables GPU IRQs, programs the SQE base and asks the scheduler
to boot. On cold boot, the scheduler sends a warmboot-scratch HFI request,
submits `CP_ME_INIT` as `H2F_MSG_ISSUE_CMD_RAW` through GMU HFI, waits for the
GPU busy indication to clear, loads/authenticates ZAP and leaves secure mode.
This is not the legacy `gen8_gpu_boot()` path, which directly programs a
ringbuffer and submits CP init through that ring.

The Gen8 CP init packet is 10 dwords total: `CP_THREAD_CONTROL`, then
`CP_ME_INIT` with seven payload dwords, including the GPU address of the
power-up register list. The A810 register-list backing and its contents must be
GPU-visible before that command. HFI `MEM_ALLOC` can arrive before GPU command
processing starts; XNU must publish every requested mapping before replying,
and retain backing until a proven quiesce.

Patch 0170 has now replaced the measured disabled/unrouted CB0 state under
explicit guards and the phone read back the GPU TTBR1 context and SID0 route.
The same boot serviced multiple real GPU-access HFI allocations. This proves
that firmware/HFI progressed through those allocation events, but not that the
GPU master fetched a PTE or performed DMA.

The next measured boundary is secure preemption memory. The actual request was
kind 5 (`CSW_PRIV_SECURE`), flags `0x1007`, size 3,670,016. Fairphone Linux
routes `GFX_SECURE` to `kgsl_allocate_secure()`, which invokes secure-buffer
allocation and `hyp_assign_table()` to transfer pages from HLOS to
`VMID_CP_PIXEL`. XNU currently has no matching protected-page allocator; do not
map ordinary pages or acknowledge the secure descriptor with a normal PA.

The Gen8 source confirms a non-preempting path: `enable_preemption()` returns
without sending `HFI_FEATURE_PREEMPTION` when the feature is disabled. Then
`gen8_ringbuffer_init()` creates one ring and returns before
`gen8_preemption_init()`, which allocates secure CSW records. Patch 0171 adds an
opt-in `fp6gmunopreempt=1` probe that skips only that HFI command; normal A810
preemption remains the default. Host normal/ASan tests, the full suite and local
arm64 compilation pass. CI and phone validation are pending. The probe will
measure whether GMU firmware still requests secure kind 5; it does not yet
initialize a GPU ring or prove execution.

## Gen8.3 HFI-to-GPU boundary (source review, 2026-10-22)

The 0160 XNU candidate stopped after its `START` HFI transaction. Patch 0161
adds an event-aware waiter: it answers `GMU_CNTR_REGISTER` with Linux's
supported zero-offset response, then waits for the original command ACK. It
validates generic ACKs against the echoed request header and success status,
matching the Linux service path.

The firmware can also request `MEM_ALLOC` while `START` is pending. Patch 0161
decoded and logged the descriptor, then reset CM3 without replying. Candidate
patch 0162 now services only non-secure GMU-only kernel allocations: it creates
permanent backing, appends the mapping to the live GMU page tables, cleans the
tables, performs context TLBIALL/TLBSYNC, and replies with the GMU address.
Requests requiring GPU access, secure memory, hardware-fence memory, fixed MMIO,
or unsupported size alignment still fail closed. The updated host peer models
one successful GMU-only exchange and one GPU-access refusal. Neither test
establishes the phone's real descriptor or firmware acceptance; Android is
currently in use and there is no 0162 phone observation.

The Fairphone module tree at `54c948d9b30c2ba01835e64c36b68b80692554ac`
shows why the request flags decide the allocator. `get_mem_alloc_entry()`
allocates GMU-only memory from kernel pages and maps it into the GMU VMA. With
`GFX_ACC`, it allocates a GPU global buffer; with `GMU_ACC` as well, it also
imports that buffer into the GMU address space. The GMU VMA ranges are
`0x60000000..0x7fffffff` for noncached kernel buffers,
`0xc0000000..0xdfffffff` for the extended range, and
`0x4000..0x00ffffff` for cacheable mappings. XNU now has a narrow live-map path
for GMU-only HFI allocations, provided firmware is blocked awaiting that HFI
reply. Requests with `GFX_ACC` still need the GPU-side allocation and mapping
path. The actual descriptor and cache/permission requirements must be read from
the phone log before widening the supported set.

The Fairphone Gen8.3 source shows the required cold-boot path continues through
`gen8_hwsched_hfi_start()` (`adreno_gen8_hwsched_hfi.c:2138`): after
`CORE_FW_START`, query/enable the context queue and register the hardware-fence
client, send HW_FENCE control, initialize preemption and LPAC, enable AQE when
the core supports it, then send `START`. The A810 profile does not advertise
LPAC/AQE, and XNU does not enable HW_FENCE without its required service. While
waiting for the `START` ACK, the GMU can interleave F2H `MEM_ALLOC` and
`GMU_CNTR_REGISTER` requests. Linux creates and maps backing for the former;
counter registration failure is allowed and answered with zero offsets. XNU's
event-aware dispatcher handles those request types, with GPU-access allocation
support limited to the mapped GPU domain and live GMU mapping.

The first 0165 phone exchange reached firmware-running and HFI-initialized
states, then returned `0x0001030f` (ACK type, ID 15, size 3) in response to the
first post-start TABLE request. Linux's generic H2F path identifies ACKs with
ID 126, but this device response is labeled with the command ID. Patch 0166
accepts either label and still validates the echoed request and zero status;
the phone has not yet verified those payload fields. Service replies remain
distinct: ACK type plus the original event ID (20 for MEM_ALLOC, 110 for
GMU_CNTR_REGISTER), with the request header echoed. The counter response is six
dwords; Linux explicitly sends zero low/high offsets when it cannot reserve a
counter, then continues waiting for the `START` ACK.

Once HFI startup completes, the reference calls `gen8_hwsched_gpu_boot()`
(`adreno_gen8_hwsched.c:755`): start the GPU MMU, acquire GMU GPU OOB, run
`gen8_start()`, enable GPU IRQs, program SQE/AQE instruction bases, and boot
the scheduler. Gen8 ring startup (`adreno_gen8.c:1430`) sets ring and scratch
addresses, starts SQE, sends CP initialization, authenticates ZAP, and leaves
secure mode. The Gen8 `CP_ME_INIT` packet has seven payload dwords and a
power-up register-list address; it differs from the eight-payload A6xx example
below. The next GPU test therefore must be built from the FP6 Gen8 source and
firmware, not copied from an older Adreno command sequence.

The local Hackintosh A642L reference (`redwood_adreno.c:2808-2945`) does show a
useful *proof shape*: after its own SMMU/SQE setup, it issues a known-value
`CP_MEM_WRITE`, flushes CPU visibility, and checks the word; then it submits a
2D clear with cache-flush events, reads pixels back, and presents them. This is
measured A642L work, not A810 evidence. It gives us the order of acceptance
checks for the eventual execution milestone while the actual FP6 packet,
memory, scheduling and synchronization details remain governed by the Gen8.3
Linux source.

Additional concrete AirNir boundary: `kits/AirNir/MesaBackend.c:29` refuses any
`fd_dev_gen(&id) != 7`; `scripts/build-air-nir-host.py:22` fixes the tested chip
at `0x43050a01`. The backend accepts vertex/fragment only and requires
`IR3_DBG_ASM_ROUNDTRIP`. `Frontend.cpp` labels itself a strict straight-line
vertex/fragment frontend and refuses unsupported constructs. Thus parser/NIR
frontend reuse is sensible, but removing the generation guard alone would not
prove correct Gen8 machine code, resource ABI, full AIR coverage or execution.
The build script explicitly records host-only output and no generated ISA
execution.

## Gen8.3 SQE firmware staging details (source review, 2026-10-23)

Fairphone's `adreno_get_firmware()` reads the raw firmware with
`request_firmware()`, allocates a GPU-readable global buffer of `fw->size - 4`,
copies bytes starting at offset 4, and records the microcode version from the
four-word header. `gen80300_sqe.fw` is selected by the A810-compatible
`qcom,adreno-gpu-gen8-3-0` catalog entry. The SQE payload must therefore be
staged without its first four header bytes; the complete file is not the
instruction payload. Linux then programs `GEN8_CP_SQE_INSTR_BASE_LO/HI`, sets
`GEN8_CP_SQE_CNTL` to start the engine, and sends CP initialization through the
ring. The hardware-scheduler path also programs the SQE base before scheduler
boot. A future XNU implementation needs a GPU-visible, correctly mapped payload
allocation and explicit cache visibility before those register writes; merely
including the firmware blob or writing the base registers is insufficient.

The pinned FairBlobs raw artifact inspected locally was 84,564 bytes, SHA-256
`38fd00147e8b752dd29c53a0badac8f94b1dbd89dc06f5b1c372d3428cd1b906`; it stays
in `/tmp` and is not committed. This is source/artifact inspection only: the
phone has not run SQE, and GPU execution remains unproven.

Patch 0181 was built in CI run `39908276809` and tested once with
`fp6gpuexec=1`. The phone repeated the measured HFI startup, both default votes
and GPU OOB ACK, then printed `permanent GPU buffer mapping failed`. It stopped
before programming the SQE registers, sending any HFI raw CP command, or
checking a GPU memory write. CM3 reset was verified and SID/context/clock votes
were retained. The failure log did not separate VA reservation, physical
backing allocation and page-table publication, so its cause is unresolved.

Patch 0182 changed SQE backing to individual 4 KiB physical pages mapped into
one contiguous GPU virtual range. CI `39909842939` passed, and one temporary
phone boot confirmed the pagewise map, SQE base programming and the HFI raw
`CP_THREAD_CONTROL` + `CP_ME_INIT` path. The command returned the idle
indication (`GPU_CX_BUSY_STATUS=0x71000000`, `RBBM_STATUS=1`), but the next
idle check stayed busy (`0x70880004`) for 200 ms before `CP_MEM_WRITE`. The
write was refused before submission, so there is no GPU memory write/readback
result yet. Exact image, source, checksums and capture are in `GPU_LOG.md` and
`NOTES.md`.

The 0182 code is only Linux-derived: it leaves CP_ME_INIT power-up-list bit 8
clear, passes a zero-filled placeholder list and does not run `gen8_start()`.
Linux A810 HWSCHED runs `gen8_start()` before SQE setup, enables bit 8 with an
initialized `cpu_gpu_lock` list, then configures IRQs and submits CP init.
Patch 0183 passed CI `39912182367` and one phone boot. Read-only snapshots
showed CB0 FSR moving from `0x400` after GMU firmware init to `0x408` directly
after CP init; busy=`0x70880004`, busy2=`0x12`, RBBM=`0x00880005`. These values
were unchanged after writing the no-ZAP secure-trust register. Patch 0184
passed CI `39913744029` and one phone boot. It measured FAR=`0x1ff800000b000`,
the first SQE instruction page, with FSYNR0=`0x00040043` and FSYNR1=`0`.
Linux ARM SMMUv2 definitions decode FSR `0x408` as UUT+PF and FSYNR0 as
PLVL=3, read access, IND set, S1CBNDX=4. This is a real context fault on the
SQE fetch; it is not evidence that CP consumed valid firmware. The SMMU reports
IDR0.NTS=0 and the configured context is stage 1; the [ARM SMMUv2
specification](https://documentation-service.arm.com/static/5f900d34f86e16515cdc08fb)
defines S1CBNDX as unknown in this configuration, so `4` does not identify
CB4. The next snapshot reads CBFRSYNRA0, CB0 SCTLR/TTBR0/TCR and CBAR/CBA2R, then
compares the live stream route and SQE page-table descriptors. Do not yet
attribute the fault to the omitted `gen8_start()` or power-up-list setup.
`CP_MEM_WRITE` was refused, and there is still no GPU write/readback, draw, or
Metal output.

Patch 0185 targets the first testable cause: ARM defines FSYNR0.IND as
instruction rather than data, while Linux defines FSR bit 3 as a permission
fault. The GPU global PTE helper sets PXN and UXN on all pages. Patch 0185
adds an explicit execute flag for SQE firmware pages only; data buffers stay
execute-never. Host PTE tests and arm64 compilation against the 0184 CI
buildtree pass. CI and phone validation are pending, so this remains a
source-supported hypothesis rather than a confirmed fix. If the fault
persists, inspect CBFRSYNRA0, live CB0 configuration and SQE descriptors.

Even a passing memory word would prove only the first GPU command write, not
draw/readback or Metal.

### A810 coldboot command order checked against current Linux source

The measured 0179 OOB ACK means the next path begins after GMU/HFI startup. The
SM7635 source makes the remaining order explicit:

1. `gen8_hwsched_gpu_boot()` starts the GPU MMU, acquires GPU OOB, runs
   `gen8_start()`, enables GPU IRQs and programs the SQE instruction base.
2. The coldboot branch calls scratch set/query helpers, but
   `gen8_hwsched_hfi_send_warmboot_cmd()` returns without sending when
   `warmboot_enabled` is false. The A810 profile omits `ADRENO_GMU_WARMBOOT`,
   and the first-boot HFI setup only queries/enables warmboot when that feature
   is present, so these scratch calls are no-ops for the default A810 profile.
3. `gen8_hwsched_cp_init()` sends `H2F_MSG_ISSUE_CMD_RAW` with the exact Gen8
   `CP_THREAD_CONTROL` + `CP_ME_INIT` packet, waits up to 200 ms for
   `GEN8_GMUAO_GPU_CX_BUSY_STATUS[23]` to clear, authenticates ZAP and switches
   to unsecure mode (or clears `RBBM_SECVID_TRUST_CNTL` if ZAP is not loaded).
   Its CP init register-list address must refer to a GPU-visible, initialized
   power-up list.

The A810 core profile advertises IFPC, content protection, preemption and ACD;
it does not advertise AQE or LPAC. It sets GMEM to 576 KiB, highest bank bit
15, hub clock 200 MHz and hang-detect cycles `0xcfffff`. Disabling HFI
preemption for the diagnostic does not disable IFPC or remove the need to
respect the core profile's power-up state.

Re-fetched the exact SQE input to `/tmp/gen80300_sqe.fw` from the FairBlobs
commit pinned by the adjacent ZAP staging script (`e58a5be8fa0fb6bc5a5f2e29cc01c036ccf75710`):
84,564 bytes, SHA-256
`38fd00147e8b752dd29c53a0badac8f94b1dbd89dc06f5b1c372d3428cd1b906`. Linux
copies bytes `[4:]` (84,560 bytes, 21,140 dwords) to GPU-readable memory; the
four-byte header is not part of the SQE instruction stream. This is still
source/artifact verification only, not evidence of SQE execution on the phone.

The next code entry point is the successful OOB branch in
`fp6_gmu_first_boot()`. Patch 0179 measures GMU/HFI, both default votes, GPU
OOB ACK and a readable GPU status register, then currently clears OOB and
resets CM3. The next implementation must retain the live GPU long enough to
stage the SQE payload and correctly mapped power-up register list, apply the
A810 `gen8_start()` register setup and GPU IRQ configuration, execute the
coldboot HFI scratch / CP init / ZAP / unsecure sequence, and establish a
bounded command completion. Preserve reset containment and permanently retain
all published mappings if any startup wait fails. The 0179 phone log is the
baseline; it proves no GPU command execution.

The existing Darwin patch uses NativeAdreno ABI version 1. Direct discovery
uses `NativeAdrenoGpuPublished`; its system-plugin route defaults to
`IOAcceleratorES` open type `0x4147` and a tunnel selector. These publication and
sandbox integration choices need review for the FP6 OS build. They do not
replace the kernel functionality behind the ABI or prove compatibility with
all Apple's accelerator contracts.

## GPU global memory and split SMMU translation (source review, 2026-10-22)

Fairphone's SM7635 kernel confirms the FP6 GPU uses the `qcom,adreno-smmu`
path. `kgsl_iommu_check_config()` enables `KGSL_MMU_IOPGTABLE` for that
compatible. `qcom_adreno_smmu_init_context()` enables split TTBR0/TTBR1 only
for the GPU device (SID 0), and the regular ARM SMMU setup selects
`QCOM_ARM_64_LPAE_S1` using the SMMU's VA/PA widths and supported page sizes.
The implementation allocates GPU contexts from CB0/CB1; non-GPU clients start
at CB2. The measured FP6 SMMU reports UBS=48-bit VA and OAS=36-bit PA. This
differs from the 32-bit, TTBR0-only GMU domain in XNU patch 0162, which uses a
client context at CB2 or above.

KGSL's global page table uses `KGSL_IOMMU_SPLIT_TABLE_BASE`
(`0x0001ff8000000000`) when the Adreno SMMU I/O page-table path is active.
Global allocations occupy a 20 MiB aperture there. For SMMU mapping, KGSL
sign-extends the high VA into the TTBR1 canonical range, then maps backing
scatterlist pages into the GPU user context (and LPAC context when present).
`kgsl_allocate_global()` requests system memory; it is not inherently one
physically contiguous allocation. The HFI response retains the GPU address.

The Linux S1 permissions are `READ|WRITE|NOEXEC` by default, with write
removed for `GPUREADONLY`, privileged access added for `GFX_PRIV`, and cache
attributes selected by KGSL flags. The QCOM LPAE walker emits nG, AP and
shareability attributes from those flags. XNU's current 0162 mapping only
supports the GMU's 32-bit `0x60000000..0x7fffffff` aperture and does not create
a GPU SID 0 mapping. A GPU-access HFI reply therefore needs a separate GPU
TTBR1-capable page-table/domain on a GPU-reserved bank (CB0 or CB1), plus
matching cache ownership; adding only another GMU mapping or reusing its
32-bit table would return an unusable GPU address.

This is source inspection only. No code, build, or phone result is claimed.
