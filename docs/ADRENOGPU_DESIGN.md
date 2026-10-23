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

Open (measured): texture sampling returns wrong texels in the first fragments (about 20 of 256 samples),
for causes not yet found. Not exercised at all: unprivileged IB execution under a context, several
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
3. **Cache maintenance is the kernel's job.** The tests showed results change with the caches cleaned
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

### User client surface (draft)

| Selector | In | Out |
|---|---|---|
| createContext | flags | context id, VA range |
| allocBO | size, flags | BO id |
| mapBO | context, BO, GPU VA, protection | none |
| unmapBO | context, GPU VA | none |
| submit | context, IB GPU VA, dwords, wait fence id list | fence id |
| waitFence | context, fence id, timeout | status |
| destroyContext | context | none |

## Work plan

| Milestone | Content | Verified by |
|---|---|---|
| M1 | `drivers/adrenogpu/adrenogpu_vm.[ch]`: page-table core | host tests (done) |
| M2 | Move the proven ring framing and fence into `adrenogpu_hw` with a packet-builder unit test against the dwords the phone ran | host test |
| M3 | BO and context objects on the kernel allocator; build the replay probe on them | one boot |
| M4 | Submission API with fences, timeout, hang detection and a reset path | boot with an induced hang |
| M5 | `AdrenoGPU` IOService and user client, in-kernel self-test submitting a replayed draw through the client path | boot |
| M6 | PM4 builder in C against the Turnip oracle (`tools/fp6-pm4-state.py`), flat triangle first | host diff, then boot |
| M7 | Interrupts, power management, unprivileged IBs, several contexts | boots |
| M8 | Metal plug-in, shader path, display hand-off | later |

The texture-sampling failure runs in parallel to M2 to M5 and does not block them.
