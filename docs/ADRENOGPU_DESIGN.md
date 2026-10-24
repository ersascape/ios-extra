# AdrenoGPU: design and work plan

Status 2026-10-24. Source inspection and phone measurements are kept apart below. Nothing in this file is
an Apple or Qualcomm statement; hardware facts come from our own boots (`NOTES.md`) and from Mesa's
freedreno sources.

## Goal and constraints

A native GPU driver for the Adreno 810 (A8xx gen 8.3, chip id `0xffff44010000`) in the XNU port on the
Fairphone 6, named **AdrenoGPU**, later carrying a Metal plug-in.

- iOS has no runtime kexts: the driver is built into the kernel image (see the project memory notes).
- The project will move to iOS 27 later (SPTM and TXM). The driver must not rely on development-kernel
  behaviour: no runtime changes to kernel text or page permissions, no writable-executable memory, GPU
  tables and buffers from ordinary kernel allocators, SMMU and GPU register access behind a few small
  functions that a hypervisor layer could intercept.
- Turnip is a host-side test oracle, never a runtime dependency. Shaders come from Mesa ir3 via air2ir3.

## Proven on the phone (measured)

| Capability | Patches |
|---|---|
| GMU firmware, HFI, GPU OOB, SQE start, CP init | up to 0192 |
| CP ring written by the CPU with a fenced `CP_RB_WPTR` write | 0192 |
| Compute dispatches replayed from Mesa captures, repeat and batched | 0194 to 0197 |
| Per-context TTBR0 address space at the captures' original IOVAs, no relocation | 0198 |
| Linux-style submit preamble, idle-aware completion, `CONCURRENT_BIN_DISABLE` cleared | 0201 to 0204 |
| Turnip draws, blits, depth, blending, uniform buffers, vertex and index fetch | 0204 to 0218 |
| GPU copy into the display framebuffer | 0206 |

Texture sampling and the other early-pixel failures had one cause, now measured: the end-of-pass cache
cleans must follow a wait-for-idle after the draw (see decision 3 and `NOTES.md`). Not exercised at all: unprivileged IB execution under a context, several
contexts, GPU interrupts, faults and recovery, power management, GMEM-mode rendering, UBWC.

## Architecture

```
user space   Metal plug-in: PM4 builder (tools/fp6-pm4), ir3 shaders, buffer objects
                |  IOUserClient: createContext / allocBO / mapBO / submit / waitFence
kernel       AdrenoGPU (IOService)  --- one IOUserClient per task
               |-- context   : adrenogpu_vm (page tables), its BOs, its fence timeline
               |-- submit    : preamble + user IB + postamble onto the ring, one ring first
               |-- hardware  : GMU/HFI, SMMU context bank, CP ring, interrupts (today: bsd/dev/sweet_gpu.c)
```

### Decisions

1. **User GPU addresses and a page table per context, no relocation list.** The replay path already runs
   captures with real addresses through TTBR0, so isolation comes from the table: a context's IBs can only
   reach pages mapped in it. Snapintosh's relocation-and-allowlist design exists because its GPU is driven
   through a monitor and a shared window; we do not have that constraint. The cost is that IBs must run
   unprivileged (CP APRIV set, protected registers) so they cannot touch the SMMU or ring; this still has to
   be shown on the phone.
2. **The kernel owns the ring framing.** Every submission is: `CP_THREAD_CONTROL` both and sync,
   `CP_RESET_CONTEXT_STATE`, thread-control BR, `CP_SET_MARKER` 0x101, the user IB by
   `CP_INDIRECT_BUFFER`, thread-control both, `CP_WAIT_FOR_IDLE`, cache cleans, then a fence write. The
   exact words are those of `fp6_replay_submit` in `sweet_gpu.c`. A user stream built for Turnip also needs
   `CONCURRENT_BIN_DISABLE` cleared in its `CP_THREAD_CONTROL` packets; our own builder will not emit it.
3. **Cache maintenance is split between the kernel and the stream.** Measured on 2026-10-24: a draw's
   fragments must drain (`CP_WAIT_FOR_IDLE`) before the CCU and UCHE cleans, so any stream that reads a
   draw's output inside itself (a copy, a sampled texture) needs wait-for-idle, `CCU_CLEAN_COLOR/DEPTH`
   and `CACHE_CLEAN` after the draw. The PM4 builder emits that; the kernel cannot add it from outside the IB.
   The kernel's part: The tests showed results change with the caches cleaned
   before the fence (patch 0214). The postamble cleans CCU colour, CCU depth and the UCHE
   (`CACHE_CLEAN`), and the preamble invalidates UCHE and CCHE (`CACHE_INVALIDATE7`, `CP_CCHE_INVALIDATE`).
   CPU-written buffer pages are cleaned to the point of coherency before a submission that reads them.
4. **One ring, polled fence first.** A fence is a dword the GPU writes after the postamble. Interrupts,
   timeouts and hang recovery come after the first user-visible draw works.
5. **Context switch.** Today `TTBR0` is written directly while the GPU is idle
   (`fp6_replay_activate`). Switching between busy contexts needs `CP_SMMU_TABLE_UPDATE` on the ring as Linux
   does; that is unproven here and is a milestone of its own.
6. **Memory.** BOs are page lists from the kernel allocator, mapped into a context with `adrenogpu_vm_map`,
   with explicit read/write/execute bits. Descriptors keep the format already validated on the phone.

### User client surface

Every method takes and returns 64-bit IOKit scalars; no structures. Handles are 32-bit (generation in the high
half, slot in the low half) and are checked to fit; a client can only name objects it created.

| Selector | Scalars in | Scalars out | Notes |
|---|---|---|---|
| 0 createContext | flags (0) | context, va_lo, va_hi | one VA range for every context, fixed by the device |
| 1 destroyContext | context | none | EBUSY while the context has jobs in flight |
| 2 allocBO | size, flags (0) | BO, size | size rounded up to 4 KiB; zeroed, write-combined, wired |
| 3 freeBO | BO | none | EBUSY while the buffer is mapped in a context |
| 4 mapBO | context, BO, gpu_va, prot | none | whole buffer, page aligned, inside the range; prot 1 write, 2 execute |
| 5 unmapBO | context, gpu_va | none | the va a buffer was mapped at; EBUSY while jobs are in flight |
| 6 submit | context, ib_va, ib_dwords, flags (0) | fence | IB inside one mapping, dword aligned, 1 to 0xfffff dwords |
| 7 waitFence | context, fence, timeout_us | status | status 0 signalled, 1 lost to a GPU reset; EINVAL above 60 s; kIOReturnTimeout |

CPU access to a buffer is `IOConnectMapMemory64` with the BO handle as the memory type (`clientMemoryForType`).

Changes against the first draft, and why: the wait-fence list on `submit` is gone (one ring runs jobs in
order, so ordering across contexts is implicit, and the cores have no dependency tracking); `submit` takes
`flags` but the only defined value is 0 (the framing's A/B test flags are not for user space); `allocBO`
returns the rounded size; `mapBO` maps whole buffers only (the context core maps whole buffer objects); `waitFence`
reports a fence lost to a reset instead of failing the call.

## Kernel IOKit shell (M5)

Source inspection of this XNU tree, 2026-10-24 (not phone-tested):

- **What exists.** The tree has no PCI or platform GPU family. Built-in IOService subclasses are registered the
  same way each time: a personality in `gIOKernelConfigTables` (`iokit/KernelConfigTables.cpp`, FP6 block) with
  `IOProviderClass` `IOResources` or `IOPlatformDevice`, the class in `iokit/Kernel/arm/*.cpp` listed in
  `iokit/conf/files.arm64`. `IOCoreSurfaceRoot` (`SweetSurface.cpp`, patch 0046) is the closest model: an
  `IOService` on `IOResources` that sets `kIOUserClientClassKey` and calls `registerService()`, with an
  `IOUserClient` subclass using `initWithTask` / `clientClose` / `externalMethod`. `SweetCPU` (patch 0065) starts
  its work from `start()` without waiting there. Nothing GPU-related exists in IOKit: the GPU is driven by the BSD
  probe in `bsd/dev/sweet_gpu.c`, which is entered from a boot-argument-gated function.
- **Registration and start path chosen.** The classes are compiled in (`iokit/Kernel/arm/AdrenoGPU.cpp`, FP6
  only) but get **no personality**. A personality would make IOKit instantiate and start the class at boot,
  before a hardware backend exists, which would add boot behaviour and would need a way to hand the class its
  hardware table. Instead the bring-up code calls `adrenogpu_iokit_start(hw_ops, hw_info)` (declared in
  `bsd/dev/adrenogpu_iokit.h`) once it has a running GPU. That function returns at once unless the boot argument
  `adrenogpu=1` is present, then allocates `AdrenoGPU`, attaches it to `IOResources` (the same provider
  `IOCoreSurfaceRoot` matches on), calls `start()`, and `start()` publishes it (`kIOUserClientClassKey` =
  `AdrenoGPUUserClient`, `registerService()`). `IOServiceOpen(IOServiceMatching("AdrenoGPU"))` from user space then
  creates one `AdrenoGPUUserClient` per connection through the default `newUserClient`. Nothing calls
  `adrenogpu_iokit_start` yet; `tests/test_adrenogpu_patch.py` asserts that no other patch does and that no
  personality names the class.
- **Layering.** `adrenogpu_dev` (patch 0224, pure C, `drivers/adrenogpu/adrenogpu_dev.[ch]`) holds everything that
  can be tested without IOKit: the client table, handle tables with generations, ownership, argument validation,
  quotas, the IB and mapping checks, the submit path onto `adrenogpu_sched`, context switching only while idle,
  fence status, and teardown. `AdrenoGPU.cpp` (patch 0225) is a thin shell: one `IOLock` around every core call,
  the memory table (kernel allocators, `IOBufferMemoryDescriptor`), `IOReturn` mapping, the polling `waitFence`,
  and the user client that narrows scalars with `adrenogpu_arg32`.
- **Hardware contract** (`struct adrenogpu_hw_ops` plus `struct adrenogpu_hw_info`, `adrenogpu_dev.h`). The
  backend, to be written in `sweet_gpu.c` (not done here), supplies: the ring (CPU view, dwords, current write
  pointer), the fence word's GPU address (and optionally its physical page, which is then mapped read-only into
  every context outside the user VA range), the hang timeout in `mach_absolute_time` units, and six functions:
  `read_rptr` (CP_RB_RPTR), `read_fence` (the dword the GPU writes), `write_wptr` (order the ring writes, then
  the fenced CP_RB_WPTR write), `tlb_invalidate`, `activate` (program a context's TTBR0 while the GPU is idle;
  0 parks the bank before tables are freed), and `reset` (reset GPU and ring, return the new write pointer). The
  core never touches registers, takes no lock the backend could invert, and never blocks in a hardware call.
  Everything is in function pointers, so an SPTM or hypervisor layer can later sit behind `activate`,
  `tlb_invalidate` and the page-table publication without touching the core. The memory table
  (`adrenogpu_mem_ops`) is the second seam: tables and buffers come from ordinary allocators, never from
  executable memory.
- **Isolation and teardown rules.** Every handle names an object owned by one client; another client's handle
  answers `kIOReturnNotPermitted`, a stale one `kIOReturnNotFound`. A buffer cannot be freed while mapped, and a
  mapping, a context or a client's memory is never released while a job of that context is in flight, because the
  GPU may still read it. Client death (`clientClose`, `clientDied` and `didTerminate` all end in one idempotent
  teardown) refuses new work, waits for the client's jobs up to a close timeout (2 s), then resets the GPU, which
  fails every in-flight job (of all clients: one ring, one reset), and only then frees contexts, mappings and
  buffers. If the reset itself fails the device is marked wedged and that memory is deliberately leaked rather
  than freed under a running GPU. User buffers keep their IOKit mapping alive after `freeBO`, which is safe because
  a buffer is unmapped from every GPU context before it can be freed.
- **Open questions that need the phone.** (1) Whether the CP writes the fence from the ring with the kernel's
  address or needs it mapped in each context's table (the `fence_map_pa` option covers the second). (2) Whether
  write-combined buffers need no cache clean before the GPU reads them (otherwise set `bo_publish`; it is called
  for every buffer mapped in the submitting context). (3) Whether `IOBufferMemoryDescriptor` buffers smaller than
  a kernel page (16 KiB) map into user space with the expected length. (4) Switching between busy contexts
  (`CP_SMMU_TABLE_UPDATE`); today a submit for another context while jobs are in flight answers busy. (5) An
  entitlement check on `IOServiceOpen` (not implemented; any task can open the service once it is started). (6)
  Hang recovery is run from the next call into the driver (submit, wait, close); there is no timer thread until
  interrupts exist (M7).

## Work plan

| Milestone | Content | Verified by |
|---|---|---|
| M1 | `drivers/adrenogpu/adrenogpu_vm.[ch]`: page-table core | host tests (done) |
| M2 | Move the proven ring framing and fence into `adrenogpu_hw` with a packet-builder unit test against the dwords the phone ran | host test |
| M3 | BO and context objects on the kernel allocator; build the replay probe on them | one boot |
| M4 | Submission API with fences, timeout, hang detection and a reset path | boot with an induced hang |
| M5 | `AdrenoGPU` IOService and user client (`adrenogpu_dev` core, patch 0224; IOKit shell, patch 0225): source, host tests, compile check; not enabled at boot. Next: the `sweet_gpu.c` hardware backend and an in-kernel self-test submitting a replayed draw through the client path | host tests and xnu-cc done; boot pending |
| M6 | PM4 builder in C against the Turnip oracle (`tools/fp6-pm4-state.py`), flat triangle first | host diff, then boot |
| M7 | Interrupts, power management, unprivileged IBs, several contexts | boots |
| M8 | Metal plug-in, shader path, display hand-off | later |

The texture-sampling failure runs in parallel to M2 to M5 and does not block them.
