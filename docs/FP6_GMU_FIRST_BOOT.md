# FP6 Gen8.3 GMU first boot: facts for implementation

Register sequence from source review; the first phone attempt and its stop
point are recorded in `NOTES.md`. FP6 GPU: Adreno 810, KGSL Gen8.3
(`qcom,adreno-gpu-gen8-3-0`), firmware `gen80300_gmu.bin`, hardware-scheduler
(`adreno_gen8_hwsched`) path. KGSL is GPL-2.0: these are register facts and
sequences used as reference, not copied code. Paths below are in the Fairphone
`graphics-kernel` module (`adreno_gen8_gmu.c`, `adreno_gen8_hwsched.c`,
`adreno_gen8_hwsched_hfi.c`, `adreno_gen8_hfi.c`, `gen8_reg.h`, `adreno_hfi.h`).

## Address conversion

KGSL register indices are dwords from `kgsl_3d0_reg_memory` (0x3d00000).
GMU window offset = `idx*4 - 0x37000` (window base 0x3d37000). Check:
`CM3_SYSRESET` idx 0x1f800 -> +0x47000 (matches 0135/0136). `cx_misc`
(0x3d9e000) and `rscc` (0x3d50000) are separate mappings (`idx*4`); GBIF is in
the main 0x3d00000 region.

| Register | idx | GMU window |
|---|---|---|
| ICACHE_CONFIG / DCACHE_CONFIG | 0x1f400 / 0x1f401 | +0x46000 / +0x46004 |
| SYS_BUS_CONFIG | 0x1f40f | +0x4603c |
| RPMH_POWER_STATE | 0x1f7e9 | +0x46fa4 |
| CX_FAL_INTF / CX_FALNEXT_INTF | 0x1f7ec / 0x1f7ed | +0x46fb0 / +0x46fb4 |
| CM3_SYSRESET | 0x1f800 | +0x47000 |
| CM3_BOOT_CONFIG | 0x1f801 | +0x47004 |
| CM3_FW_INIT_RESULT | 0x1f81c | +0x47070 |
| CM3_CFG | 0x1f82d | +0x470b4 |
| HFI_CTRL_STATUS | 0x1f980 | +0x47600 |
| HFI_QTBL_INFO / HFI_QTBL_ADDR | 0x1f984 / 0x1f985 | +0x47610 / +0x47614 |
| HFI_CTRL_INIT | 0x1f986 | +0x47618 |
| GMU2HOST_INTR_CLR / INFO / MASK | 0x1f991 / 0x1f992 / 0x1f993 | +0x47644 / +0x47648 / +0x4764c |
| HOST2GMU_INTR_SET | 0x1f994 | +0x47650 |
| GENERAL_8 / 9 / 10 / 11 | 0x1f9c8..0x1f9cb | +0x47720 .. +0x4772c |
| POWER_COUNTER_SELECT_XOCLK_0 | 0x1fc40 | +0x48100 |
| AO_HOST_INTERRUPT_CLR / MASK | 0x23b04 / 0x23b06 | +0x57c10 / +0x57c18 |
| RSCC_CONTROL_REQ / ACK | 0x23b07 / 0x23b08 | +0x57c1c / +0x57c20 |
| AHB_FENCE_CTRL / RANGE_0 / STATUS_CLR | 0x23b10 / 0x23b11 / 0x23b14 | +0x57c40 / +0x57c44 / +0x57c50 |
| CM3_ITCM_START / DTCM_START | 0x1b400 / 0x1c400 | +0x36000 / +0x3a000 |

GBIF: `GBIF_CX_CONFIG` 0x3d0f000, `QSB_SIDE0..3` 0x3d0f00c..0x3d0f018,
`GBIF_HALT` 0x3d0f114, `GBIF_HALT_ACK` 0x3d0f118. cx_misc: AHB timeout
controls 0x3d9e040..0x3d9e050, AO counter 0x3d9e200/0x3d9e204.

## First boot (hwsched), after CX GDSC and GMU clocks, firmware in TCM

1. Optional: AOP QMP ACD state, AHB timeout detection (cx_misc 0x40..0x50 =
   0x1b00 | timeout), CX timer sync, SCM `gpu_init_cx_regs`
   (STD call FID 0x42002801, x2 = 0xb; availability FID 0x42000101 with
   x2 = 0x02002801; unavailable is ignored by KGSL).
2. Register config (`gen8_gmu_register_config`):
   `RPMH_POWER_STATE`=0xf, `CX_FALNEXT_INTF`=1, `CX_FAL_INTF`=1,
   `CM3_FW_INIT_RESULT`=0, `CM3_BOOT_CONFIG`=2, `HFI_QTBL_ADDR`=HFI GMU VA,
   `HFI_QTBL_INFO`=1, `AHB_FENCE_RANGE_0`=0x80c808a0, `CM3_CFG`=0x4052,
   GBIF `QSB_SIDE0..3`=0x00071e20, `GBIF_CX_CONFIG`=0x20023000,
   `GBIF_HALT`=BIT(3), `GENERAL_11`=VRB GMU VA, `GENERAL_9`=0,
   `GENERAL_10`=0x08030000 (GMU rev 8.3.0),
   `GENERAL_8`=(log GMU VA & ~0xfff) | 0xf (64 KiB log),
   `SYS_BUS_CONFIG`=1, `ICACHE_CONFIG`=1, `DCACHE_CONFIG`=1.
3. Version: DTCM +0x3fe0..+0x3ff0 (core/pwr/HFI versions; HFI version selects
   message formats). No minimum check for gen8_3_0.
4. Polled bring-up: keep `GMU2HOST_INTR_MASK` and `AO_HOST_INTERRUPT_MASK` all
   ones; clear both CLR registers.
5. Release: `CM3_SYSRESET`=0, barrier, poll `CM3_FW_INIT_RESULT` until
   `(v & 0x1ff) == 0x100` (100 us steps, 100 ms). `v & 0xe00` = firmware
   reset/NMI (assert).
6. HFI: `HFI_CTRL_INIT`=1, poll `HFI_CTRL_STATUS` bit0 (100 ms).

KGSL hwsched first boot runs the GMU at its top table rate (650 MHz); the
current FP6 clock path uses the 350 MHz table rate.

No host RSCC/PDC init on Gen8 (firmware/AOP). The RSCC wake handshake
(`RSCC_CONTROL_REQ`=BIT1, ACK BIT1, rscc `SEQ_BUSY_DRV0` 0x3d50404 == 0) is
used only after a sleep sequence.

Before permitting the GMU to become an SMMU master, inspect the SMMU global
fault interrupt independently. The stock FP6 DT assigns global SPI 0x2a1
(GIC INTID 705); GMU AO/HFI masks do not cover it. Patch 0146's
`fp6smmuirq=1` only reads GICD enable, pending, and trigger configuration. It
does not contain or mask the source. The 2026-10-22 first-start attempt stopped
before upload at inherited GMU core clock `0x2001`; CM3 reset had not yet been
checked. Patch 0147 adds that reset check before changing a clock source. Retest
proceeds only if CM3 reset is confirmed; buffers remain mapped through the
bounded start and verified reset.

## HFI (hwsched)

- Queue table: header 6 dwords {version 0, size dwords, qhdr0_offset 6,
  qhdr_size 12, num_q, num_active_q}; 17 queue headers of 12 dwords {status,
  start_addr, type = id|prio<<8|rtype<<16|stype<<24, queue_size dwords,
  msg_size, unused x5, read_index, write_index}. Queue 0 H2F command, 1 F2H
  message, 2 debug, 3..16 dispatch. Each queue 4 KiB (1024 dwords) at
  `0x350 + i*0x1000`; allocation 70,488 bytes noncached, GMU VA first-fit
  from 0x60000000, read/write/priv.
- The XNU allocator uses 16 KiB CPU pages. The local HFI follow-up will set
  WCOMB on all five CPU pages covering its 0x12000-byte allocation before the
  queue headers are initialized. This concerns CPU cache attributes; the GMU
  page-table granule remains the separately configured 4 KiB.
- Other GMU buffers: log 64 KiB noncached, VRB 4 KiB (dword0 = 0x400 size,
  dword2 = trace buffer VA), trace 16 KiB; firmware preallocation blocks at
  their fixed VAs.
- Header: `id | size_dwords<<8 | type<<16 | seqnum<<20` (type 0 command,
  1 ack, seqnum from 1). Messages padded to 4 dwords with 0xfafafafa; write
  index published after a barrier, then `HOST2GMU_INTR_SET`=1.
- Ack: {ack header, echoed request header, result (non-zero = failure),
  return type}. Polling: `GMU2HOST_INTR_INFO` bit0 (raw, works masked),
  clear with `GMU2HOST_INTR_CLR` bit0, then read the message queue.
- IDs: START 10, FEATURE_CTRL 11, GET_VALUE 12, SET_VALUE 13,
  CORE_FW_START 14, TABLE 15, BW_VOTE_TBL 3, PERF_TBL 4, F2H MEM_ALLOC 20,
  F2H ERR 100, DEBUG 101, LOG_BLOCK 102, GMU_CNTR_REGISTER 110.
- Start order: perf table (TABLE id 15 when HFI >= 2.6.1), BW table, optional
  ACD/BCL/IFPC, FEATURE_CTRL HWSCHED and KPROF, SET_VALUE LOG_GROUP,
  CORE_FW_START {hdr, 0}, START (id 10) whose loop also answers F2H MEM_ALLOC
  and GMU_CNTR_REGISTER. Perf/BW tables need cmd-db `gfx.lvl/cx.lvl/mx.lvl`
  and BCM `SH0/MC0/ACV/CN0` aux data.
- MEM_ALLOC: F2H {hdr, version, desc{gpu_addr, flags, mem_kind,
  host_mem_handle, gmu_mem_handle, gmu_addr, size, align}}; reply is an ack
  with the descriptor filled (gmu_addr, size, host handle = gmu handle).

## Failure and teardown

Signatures: FW_INIT_RESULT never 0x100 (stuck in reset); `& 0xe00` (assert);
`HFI_CTRL_STATUS` bit0 stays 0; ack timeout; ack result non-zero;
`GMU2HOST_INTR_INFO` bit15 (CM3 fault); AO bits 0/3/5.
Safe stop when the GMU never came up: `CM3_SYSRESET`=1, mask and clear
GMU2HOST/AO interrupts, `AHB_FENCE_STATUS_CLR`=7 then `AHB_FENCE_CTRL`=0,
undo any GBIF halt, then clocks and CX power in reverse order; keep the GMU
SMMU mappings.

## Runtime review and bounded probe correction (2026-10-22)

Patch 0149 reserves the missing 16 KiB trace allocation, publishes its Gen8
hwsched v1 header and places its GMU VA in VRB dword 2. The trace metadata is
`0x40000001` (drop mode in bits 31:30 and version 1), threshold 80 percent,
timeout 5 ms and log type 1. The packed 64-bit cookie starts at dword 8.
Reference: `kgsl_gmu_core.c:gmu_core_trace_header_init`,
`kgsl_gmu_core.h:struct gmu_trace_header`, and
`adreno_gen8_hwsched.c:gen8_hwsched_gmu_memory_init`.

The probe now requests and verifies CM3 reset after both successful HFI
initialization and failures. It does not yet service HFI commands or interrupts,
so successful HFI initialization must not leave firmware running indefinitely.
SID, translation tables, backing allocations and clock votes remain retained,
including when reset readback fails. A reset readback alone does not establish
that outstanding DMA transactions have drained. Firmware reset/NMI bits take
precedence over the ready field; `FW_INIT_RESULT=0x300` is a failure.
The dedicated host test injects successful HFI, rejected reset, combined
ready/fault bits and firmware/HFI timeouts; it also checks the trace header.
These are modeled results, not phone observations.

Patch 0150 implements the CX timer synchronization
(`adreno_gen8.c:gen8_cx_timer_init`) and optional SCM CX register setup
(`gen8_scm_gpu_init_cx_regs`). The timer uses the Linux 16-sample
`cntpct`/write-latency algorithm, seeds the `cx_misc` AO counter, then adds
readback/rate checks. SCM availability is queried and the port requests
ALWAYS_EN|TSENSE (`0x9`); BCL and CLX are not requested. These are source and
host-model results until a CI build and phone observation are recorded. CI
`39728088129` built 0150, but the phone run refused at the timer sample guard
(`valid=0/16` at 19.2 MHz), before firmware upload. The follow-up diagnosis
found that the original guard discarded equal read/write tick costs; 0151
accepts zero-skew samples and records raw timing ranges. It is host-tested and
locally cross-compiled, but not yet built by CI or phone-tested. The same local
follow-up marks the five CPU 16 KiB pages backing the 0x12000-byte shared HFI
allocation as `VM_WIMG_WCOMB` before queue initialization and domain publish.
It verifies physical contiguity and only converts default-cached pages (or
accepts pages already WCOMB), then checks every resulting attribute. This
matches Linux's write-combined HFI mapping and avoids stale cached CPU lines
overwriting GMU queue indices. Host tests and a system-Clang AArch64 compile
against the exact 39728088129 XNU build tree pass; no CI build or phone result
for this combined update exists yet.
Minimum DDR bandwidth voting before CM3 release remains unimplemented
(`gen8_hwsched_gmu_first_boot`). GMU interrupt
masks do not mask the SMMU global fault interrupt. The read-only GIC inspection
in 0146 must not be described as interrupt containment.

After HFI initialization the port still needs command/reply processing,
performance and bandwidth tables, start-time memory requests, GPU MMU/OOB,
Gen8 SQE initialization and hardware scheduler boot/submission. Existing
NativeAdreno targets A740; its BO/queue/fence ABI and Darwin Turnip backend are
reuse candidates, while its board register setup and GPU target require an
explicit Gen8.3 implementation. No Metal execution is established by this
probe.
