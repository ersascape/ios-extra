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

## Gen8.3 HFI-to-GPU boundary (source review, 2026-10-22)

The current XNU candidate 0160 stops after its `START` HFI transaction. The
Fairphone Gen8.3 source shows the required cold-boot path continues through
`gen8_hwsched_hfi_start()` (`adreno_gen8_hwsched_hfi.c:2138`): after
`CORE_FW_START`, query/enable the context queue and register the hardware-fence
client, send HW_FENCE control, initialize preemption and LPAC, enable AQE when
the core supports it, then send `START`. While waiting for that `START` ACK,
the GMU can interleave F2H `MEM_ALLOC` and `GMU_CNTR_REGISTER` requests. Linux
creates and maps backing for the former; counter registration failure is
allowed and answered with zero offsets. The XNU probe currently treats every
queue-1 packet as a final ACK, so it cannot complete this exchange. The first
required runtime extension is an event-aware HFI dispatcher plus correctly
mapped memory for the actual allocation descriptors; a pre-mapped GMU-only
arena cannot satisfy descriptors requiring GPU access.

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

The existing Darwin patch uses NativeAdreno ABI version 1. Direct discovery
uses `NativeAdrenoGpuPublished`; its system-plugin route defaults to
`IOAcceleratorES` open type `0x4147` and a tunnel selector. These publication and
sandbox integration choices need review for the FP6 OS build. They do not
replace the kernel functionality behind the ABI or prove compatibility with
all Apple's accelerator contracts.
