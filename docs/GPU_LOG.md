## FP6 request-ID HFI ACK follow-up 0166 (2026-10-22)

- Patch 0166 accepts HFI ACK type responses identified by either the original
  request ID or generic ID 126. It keeps the echoed request header and zero
  status checks. The host peer models the measured 3-dword TABLE response
  (`id=15`, type 1) and generic-ID responses for the other requests. GPU probe
  tests pass normally and under ASan/UBSan; `tests/test_fp6_gmu_boot.py` passes.
- Commit `af030f8aabc5eeff3f1e0da673b0579ab70976f3` passed CI run
  `39821513140`; build and FP6 packaging jobs succeeded. The local bounded
  RAM-disk image uses the same ADT, verified Volcano DTB and command line as
  0165: `/tmp/ios-extra-run-39821513140/package/fp6-gmu-hfi-ack-0166.img`,
  SHA-256 `4d06ee27cd0c25778841923c04c2e61e5aaddb0421cd0e5de794e2cfb2d33ee7`.
- Phone test used the bounded user-mode ECM logger, avoiding the pkexec timeout.
  It booted successfully, answered ping, and captured
  `/tmp/ios-extra-run-39821513140/logs/phone-0166-hfi-request-id-ack-usercap2.txt`
  (SHA-256 `e8b772c189f5815f5cb1c42d95afc49411870ca600956e3355b9688e2886bc91`).
  Six request-ID ACKs passed: GPU perf TABLE, DDR/CNOC TABLE, config requests
  IDs 11/11/14, and preemption ID 11; the initial DDR BCM vote was acknowledged.
  Firmware state was `FW_INIT_RESULT=0x100`, `HFI_CTRL_STATUS=1`; version was
  `0x20070001`. Context-queue capability was not queried because the DTCM HFI
  version read as zero in this boot.
- The first GPU global allocation event reached XNU with kind 2, handle 2,
  VA `0x1ff8000000000`, PA `0x903e5c000`. `fp6_gpu_global_context_enable()`
  refused before writing because CB0 or its selected fault-routed SID0 group
  was not clean. The earlier inventory counted `0/22` banks active, but did not
  include CB0 FSR or TTBR1 in its activity predicate; therefore the exact field
  is unknown from this log. The bounded probe then reset CM3 and verified reset.
  This is the new blocker; no global map, DMA, GPU command, draw, or Metal result
  was reached. Next change should print all CB0 fields and selected group values,
  then permit clearing only a stale W1C FSR if SCTLR is disabled and all mapping
  controls are zero. Keep refusing any active/unknown translation context.

## FP6 CB0/SID0 refusal diagnostics candidate 0167 (2026-10-22)

- Commit `d3945d021d4f4013e8f966dfca41158d125cdae8` passed CI run
  `39827421127`; kernel SHA-256
  `abe30b248c2b311fc83c10838e3bb2a51ae14719bec7b68700f64ccc32694445`.
  Packaged the exact CI kernel, ADT, stock Volcano DTB and bounded RAM-disk init
  in `/tmp/ios-extra-run-39827421127/package/fp6-gmu-hfi-diag-0167.img`
  (SHA-256 `65452f75f388850b624a1c1904f4676f9b56fa0aa062981500dc081447480b50`);
  header-v2 round-trip passed. `python3 tests/test_gpu_probe.py` also passes,
  including the deliberate dirty-CBAR refusal-before-write case.
- One bounded phone boot completed the six previously observed HFI ACKs and
  received `MEM_ALLOC` kind 2, handle 2, VA `0x1ff8000000000`, PA `0x903e5c000`.
  0167 refused before SMMU writes. At refusal, selected group 1/24 had
  `SMR=0`, `S2CR=0x20000`; CB0 was `CBAR=0`, `CBA2R=0`,
  `SCTLR=0x2ff54314`, `TCR=0x7d0e6f8c`, `TCR2=0x00010065`,
  `TTBR0=0x11f173774fcb6d7a`, `TTBR1=0xdc20c8a1af8db1f4`,
  `MAIR0=0x079fae8a`, `MAIR1=0x8899bf1f`, `FSR=0`. CM3 reset was verified.
  Log SHA-256 is `87eee3625cbd8f913153b9e065b025b43a2211fc72a14d0fe200d517ad752b36`
  at `/tmp/ios-extra-run-39827421127/logs/phone-0167-cb0-sid0-diagnostics.txt`.
- Rechecked the exact packaged DTB with `dtc`: `kgsl-smmu@3da0000` has
  `reg=<0x03da0000 0x40000>`. Measured `IDR1=0x40000016` yields 4 KiB pages
  and NUMPAGENDXB=4; Fairphone Linux's `arm_smmu_page()` therefore places CB0
  at `+0x20000`, matching the XNU calculation and the declared resource size.
  The previous `context banks with nonzero state=0/22` scan was before explicit
  SMMU power-up, so it cannot establish powered CB0 cleanliness. Next probe must
  capture powered CB0 and all stream-group SMR/S2CR values before test setup,
  then compare them with the post-HFI values. No GPU mapping, DMA, command
  execution, draw or Metal has been demonstrated. Do not clear/overwrite these
  unexplained context fields yet.

## FP6 post-CORE_FW_START HFI candidate 0165 (2026-10-22)

- User-requested rootfs write: verified Tegu sparse image from
  `/home/ersa/Dev/ios-extra/research/fp6-rootfs-tegu-20261021/` was flashed to
  the existing `userdata` partition. SHA-256
  `a1c6f7da616520841c4d56ac2a147940c5c93a0b4406cb1c9ae6832d64338f7c` matched
  the recorded image; all 16 sparse chunks completed `OKAY`. Redacted fastboot
  transcript: `/tmp/fastboot-flash-fp6-rootfs-20261022.log`. Previous userdata
  was overwritten. This is a storage operation, not a GPU observation.
- One 0165 RAM-disk boot was captured with the bounded USB helper. The decoded
  phone log is `/tmp/ios-extra-run-39814973566/logs/phone-0165-gmu-hfi-start-resume.txt`
  (SHA-256 `616da7d037e14403ef9064c347b978b8d7efe9d9df56ce1d89c515358e4f8e50`);
  the pcap is in the same directory. It measured `FW_INIT_RESULT=0x100`,
  `HFI_CTRL_STATUS=1`, and firmware `0x20070001`. The first HFI response was
  `id=15 type=1 size=3 hdr=0x0001030f`, returned to the GPU performance TABLE
  request. Patch 0161 only recognized generic ACK ID 126, so it reported the
  valid request-ID response as unexpected and stopped. The probe verified CM3
  reset. No START ACK, GX power-on, GPU command, DMA readback, or draw was
  observed.
- Patch 0166 recognizes both the request ID and generic ACK ID, while keeping
  the existing echoed-header and status checks. `tests/test_gpu_probe.py` passes
  normally and under ASan/UBSan; `tests/test_fp6_gmu_boot.py` passes. These are
  host-model results. Patch 0166 needs a phone boot to verify the echoed header
  and status dwords from the real TABLE response, then test the remaining HFI
  startup messages.

- Source review of Fairphone SM7635 graphics-kernel commit
  `54c948d9b30c2ba01835e64c36b68b80692554ac` confirms Gen8 HFI version minor
  7 uses the inline ACK layout: result at dword 2 and GMU status at dword 3.
  The measured firmware version `0x20070001` therefore needs that parser. The
  A810 `gen8_3_0` profile advertises preemption level 1 and does not advertise
  LPAC or AQE. Linux queries context-queue support for HFI minor >= 3, sends
  preemption feature 2 with data `0xD`, and sends `H2F_MSG_START` as one dword.
- Patch 0165 implements those steps after `CORE_FW_START`, while preserving
  HFI event handling for MEM_ALLOC and counter-registration requests. It leaves
  HW_FENCE disabled because Linux obtains that backing from a separate hardware
  fence service that XNU does not implement. It does not yet start GX or submit
  GPU commands.
- Host HFI queue peer and ACK-format checks pass, as do the GMU domain, GPU
  global-domain, and normal plus ASan/UBSan GPU probe tests. Local arm64 compile
  of `sweet_gpu.c` against CI buildtree `39793471917` reports `0 of 1 files
  failed`. Commit `b96b41b2ea432f65a9164f279a7ab5e61cc8b014` passed CI run
  `39814973566`; verified kernel SHA-256 is
  `916d0e406f6425d1681b3522c6e2403ca2b4c16342ac8dbc1355efa5da7891a8`.
  CI skipped image packaging because `FP6_STOCK_DTB_URL` is unset. The exact CI
  kernel and ADT were locally packaged with the verified stock Volcano DTB and
  bounded RAM-disk init; header-v2 checks passed. Image
  `/tmp/ios-extra-run-39814973566/package/fp6-gmu-hfi-start-0165.img`, SHA-256
  `1f1575412a97639396691ccfbc7898022937818b6bba4f5097d54fe25733de4f`.
  Its `rd=md0` boot args select the bounded probe. There is no 0165 phone test,
  firmware acceptance, GPU execution, readback, draw or Metal result yet.

## FP6 GPU global HFI allocation candidate 0164 (2026-10-22)

- Commit `cacda42725fd0945a6a8df96bf28e27b8d8a2868` passed CI run
  `39807392802`; XNU build and FP6 workflow passed. Kernel SHA-256
  `34e4835aa437df8ecd101fe0b98aba7b18e5a80094ab71ad860976dec0cc7539`.
  The workflow skipped its temporary image because `FP6_STOCK_DTB_URL` is not
  configured. Downloading the `xnu-buildtree` artifact separately returned
  HTTP 503 because of the GitHub account egress limit.
- Locally packaged with the CI ADT, verified stock Volcano DTB and minimal
  RAM-disk init. Header-v2 round-trip passed. Image
  `/tmp/ios-extra-run-39807392802/package/fp6-gmu-hfi-gfx-0164.img`, SHA-256
  `125860c6c4aa898cb40b5039558d146408d5f5c468fef12c96a979bb6c63b4cc`.
  It uses `rd=md0` and enables the SMMU/GMU HFI path with USB logging. No flash
  is involved. `fastboot devices` returned no device, so there is no phone
  observation yet.
- Host tests exercise a synthetic `GFX_ACC` allocation and verify the ACK's
  GPU VA against its published TTBR1 page-table walk. Hardware request values,
  firmware acceptance, GPU execution and Metal are still unverified.

# GPU bring-up log (chronological, newest first)

## Source audit — GMU cacheable flag and SMMU PTE attributes (2026-10-22)


Read-only Fairphone Gen8.3 source review resolved whether XNU's GMU page-table
PTE should set an AttrIndx bit for `HFI_MEMFLAG_GMU_CACHEABLE`. In
`adreno_gen8_hwsched_hfi.c`, `get_attrs()` returns `IOMMU_READ` and adds only
`IOMMU_PRIV` / `IOMMU_WRITE` from the HFI flags; it does not add
`IOMMU_CACHE`. In `drivers/iommu/io-pgtable-arm.c`, the S1 mapping selects
MAIR AttrIndx 1 only for `IOMMU_CACHE`, otherwise AttrIndx 0. The flag instead
chooses between the GMU cacheable VA aperture (`0x4000..0x00ffffff`) and the
noncached kernel apertures (`0x60000000..0x7fffffff`, extended
`0xc0000000..0xdfffffff`). XNU's GMU MAIR0 value `0x44` defines AttrIndx 0 as
Normal Non-cacheable, so the existing AttrIndx-0 PTE matches this Linux policy.
No driver PTE change was justified.

Added host assertions in `tests/test_fp6_gmu_domain.py` for AttrIndx 0 on both
window classes while checking the cached-window metadata. The focused test passes; its optional pinned-firmware integration skips because
that local firmware blob is unavailable. No build or phone test was run for this
source-only correction; `fastboot devices` returned zero devices.

The same source trace identifies the current HFI stopping point. XNU's 0164
path sends the prerequisite tables/features, then `CORE_FW_START`, with the
event dispatcher available while waiting. Linux `gen8_hwsched_hfi_start()`
continues by enabling the context queue and hardware-fence client, sending
HW_FENCE control, configuring preemption/LPAC/AQE, and sending `START`. XNU
does not yet perform those post-CORE_FW_START steps. The phone must first show
whether 0164 receives the CORE_FW_START ACK and which real MEM_ALLOC descriptors
arrive; only then can the next command sequence be matched safely.

The Gen8 source also shows why `HFI_MEMKIND_HW_FENCE` cannot be answered with
ordinary allocated pages: `adreno_hwsched_register_hw_fence()` obtains the
fence queue descriptor from `msm_hw_fence_register()` and builds its memdesc
from the service's device and CPU addresses. The MEM_ALLOC handler reuses that
pre-registered memdesc. XNU has no matching service, and 0164 rejects this
allocation kind. Leave the HW_FENCE feature disabled while advancing context
queue startup; add the feature only with its external memory contract.


## FP6 HFI GMU allocation permissions review (2026-10-22)

- Compared the XNU GMU-only allocation path with Fairphone Gen8
  `adreno_gen8_hwsched_hfi.c:get_attrs()` and the fork's QCOM ARM64 S1
  `arm_lpae_prot_to_pte()`. Linux always maps read access, adds write access
  only for `GMU_WRITEABLE`, and adds privileged-only access only for
  `GMU_PRIV`; QCOM ARM64 S1 encodes read-only and unprivileged access in AP.
  The prior XNU candidate mapped every request privileged and writable.
- Updated the persistent domain allocator to carry access attributes per range
  and build nG/AF/outer-shareable PTEs with request-derived AP bits. Existing
  firmware/HFI boot mappings keep their prior privileged RW default. The HFI
  allocator now passes the descriptor's GMU permission flags through.
- Host domain and HFI tests verify read-only/unprivileged defaults and
  privileged/RW flags, while GPU-access allocations remain refused. Normal and
  ASan/UBSan tests pass; broad GPU probe tests pass; `sweet_gpu.c` cross-compiles
  against CI buildtree `39787950216` (`0 of 1 files failed`). CI `39792609801`
  stopped before compilation because the edited 0133 patch's added-file line
  count was stale. Corrected commit `42e746f` passed CI `39793471917` (XNU build
  and FP6 workflow). Kernel SHA256 is
  `e4dbf5cb1acfd17f19273cf1bdd0baf53f790e88a856bd37127c2a54abcdbd2c`; the
  extracted build source contains the updated permission-aware mapping. Locally
  packaged image
  `/tmp/ios-extra-run-39793471917/package/fp6-gmu-hfi-memalloc-permissions.img`
  SHA256 `897b67af46ec1b0da14dc927a5a3234ed462abed90be3874500a391093f18e22`
  passed header-v2 round-trip. It is not phone-tested. Firmware's actual
  descriptor remains unknown; device commands are deferred while the user tests
  Android.

## FP6 patch 0162 GMU-only HFI allocation candidate — 2026-10-22

- Patch 0162 extends 0161's event dispatcher to service the narrow Linux
  GMU-only kernel-memory case: a permanent backing range is added to the live
  GMU SMMU page tables, cleaned, followed by context TLBIALL/TLBSYNC and a
  bounded sync poll. It then returns the host handle, GMU IOVA and mapped size
  in an HFI ACK. Requests with GPU access, secure memory, hardware-fence kind,
  fixed MMIO kind or size alignment above 4 KiB fail closed and cause CM3 reset.
- Host harness simulates a 4 KiB kind-2/flags-0 request at the noncached GMU
  window. CPU table walk reaches the allocated PA, TLBI and sync are issued,
  service ACK is sent, START receives its ACK, and CM3 reset is verified. A
  simulated `GFX_ACC` request is refused without a mapping or service reply;
  the bounded reset path verifies. Normal and ASan/UBSan runs pass, as does the
  broad GPU probe suite. Arm64 object compile against CI buildtree
  `39775328855` reports `0 of 1 files failed`; patch application check passes.
- The request values above are test-fixture values, not phone observations.
  The phone's actual descriptor and firmware response are still unknown. The
  first CI attempt, `39786196862`, failed because Apple Clang rejects a C
  declaration immediately after the `reply:` label. The response array was
  moved to the function's initial declarations. Normal and ASan/UBSan host
  tests pass again and arm64 object compile reports `0 of 1 files failed` after
  the fix. Corrected commit `4a14fe7` passed CI `39787950216`; kernel SHA256
  is `6d35acc9772c0b0cc740d409505016fd23c5267d230a923a830ca15561678934`.
  CI packaging skipped because `FP6_STOCK_DTB_URL` is unset. The kernel was
  locally packaged with the verified product ADT and stock Volcano DTB at
  `/tmp/ios-extra-run-39787950216/package/fp6-gmu-hfi-memalloc-0162.img`,
  SHA256 `30fc97daccfa67230e2f2bedac463591b2f310e285b9ac0c2d1fbc1730ed502d`;
  header-v2 round-trip passed. No hardware test has been made, and phone
  commands are deferred while the user is testing Android. It does not
  demonstrate GPU DMA, command execution, rendering, or Metal.

## FP6 patch 0160 source/host review (2026-10-22)

- Candidate patch 0160 adds the Linux Gen8 HFI performance and bandwidth tables,
  HWSCHED/KPROF controls, and `CORE_FW_START` request path after 0159's
  firmware assertion. Review against Fairphone KGSL and stock FP6 DTS corrected
  the GPU point to 362 MHz, added both average/X and peak/Y BCM vote fields,
  disabled ACV perfmode for a shortened DDR table, and validates zero ARC rows.
- Host HFI model checks the five-request ordering, table values, sequence/ACK
  matching, mismatched ACK rejection and reset/fault cases. `test_fp6_gmu_boot.py`
  and its ASan/UBSan run pass; `test_gpu_probe.py` passes. Local XNU compile
  against CI buildtree `39766804611` reports `0 of 1 files failed`.
- Commit `5243eb1f6e8b0590e580fd66e604ea34a5faa0f2` passed CI `39775328855`.
  Kernel SHA256 `ddce0dae8fd220bcd9a238b3500cf5693af4c46bd72ee0d18dd123f1bfca4d14`.
  CI image packaging skipped because its generated ADT has no `/product`
  artwork traits. Locally packaged with the existing verified product ADT and
  stock DTB; header-v2 round-trip passed. Image
  `/tmp/ios-extra-run-39775328855/package/fp6-gmu-hfi-prerequisites/fp6-gmu-hfi-prerequisites.img`,
  SHA256 `f63635017fa022319c4f6c6a6cb29224aec193edea49372eb4dc13ae85c2db8e`.
- No 0160 phone result. Optional
  ACD/BCL/CLX/IFPC startup inputs and F2H MEM_ALLOC servicing remain absent.
  Phone testing is deferred while the user tests Android.

## FP6 patch 0159 CORE_FW_START firmware fault (2026-10-22)

- Patch 0159 mirrors Linux Gen8 queue 0 submission: `H2F_MSG_CORE_FW_START`,
  sequence 1, 2-dword request, 4-dword queue alignment, host-to-GMU message
  doorbell, and message-queue ACK validation. The HFI buffer transitions through
  clean/invalidate before GMU ownership and invalidate after its interrupt.
- Commit `78ce55ec29dd66de6ffdb93eb5c487436de77303` passed CI
  `39766804611`; kernel SHA256
  `3f3aa08c6fc98403b768a2887e7703934afdca26d683f229062c30c6f8801aa0`.
  Packaged image SHA256
  `d68b056515ffc18677842c0dea5bcc51f1dd4a8f11b069ba9341fa4af29c7b08`.
- One temporary boot captured 101 UDP packets. Decoded log SHA256
  `ff9b450dc47e29d15f87cabc192b1862198892b543810de72bf99203412b220c`; pcap
  SHA256 `c828b23c0d2c4be46919d8b00cd9cea3b6bf0b9c9a61a5ce68f5608de6db9008`.
- Phone: `HFI_CTRL_STATUS=1`, then
  `HFI CORE_FW_START timeout/fault irq=0x00000004 fw=0x00000900`; bounded stop
  verified CM3 reset. Linux identifies GMU2HOST bit 2 as DBGQ; FW_INIT_RESULT
  bits `0xe00` indicate firmware assertion. The debug queue payload was not
  captured, so the assertion reason is still unknown.
- Source inspection found Linux `gen8_hwsched_hfi_start()` submits warmboot
  scratch, GPU performance and BW tables, optional feature controls and log
  settings before CORE_FW_START. Phone firmware reports HFI version
  `0x20070001` (2.7.1), so GPU performance uses `H2F_MSG_TABLE`. Linux derives
  performance entries from the selected GPU pwrlevel bin and live `gfx.lvl`,
  `cx.lvl`, `mx.lvl` ARC cmd-db values; bandwidth entries use DDR levels and
  SH0/MC0/ACV BCM metadata. Patch 0159 sent CORE_FW_START without these
  prerequisites. The next implementation must source those exact inputs and
  preserve debug-queue data on failure, instead of guessing table values.
- If firmware returns `F2H_MSG_MEM_ALLOC` instead of the expected ACK, the code
  logs the unexpected message and resets GMU. Linux dynamically allocates/maps
  those descriptors; the phone response must establish the required allocation
  kinds, sizes, flags, and GMU addresses before XNU can answer safely.

## FP6 patch 0158 fixed ACV vote and GMU/HFI controller startup (2026-10-22)

- Commit `548673a33b397ef80cdbc701cd503903ab63118a` passed CI
  `39762347940`. Verified kernel SHA256 before local packaging. Temporary image
  `/tmp/ios-extra-run-39762347940/package/fp6-gmu-bootstrap-acv-width.img`,
  SHA256 `0c2e73788e98d3a0bbe768ee54e9f4989e3e88973cb2e82d7438ad76ae3f6c10`.
- One temporary `fastboot boot` succeeded and captured 92 UDP packets. Decoded
  log SHA256 `199a1032353ab16000e60d3424fc72edcc8d99e9941872be251fa66e56791526`;
  pcap SHA256 `50e7f70104ca136dfc74a27e3642c725c7b953cca30328a1dedc9108a42c025a`.
  Files are under `/tmp/ios-extra-run-39762347940/logs/`.
- Runtime records: SH0 `addr=0x50004 width=32`, MC0 `addr=0x50000 width=8`,
  ACV `addr=0x50068 width=0` (fixed), all using requested peak
  `ib_kbps=2136718`. The TCS reported `DDR BCM vote acknowledged slot=0
  retained`. CM3 was released; firmware reported `FW_INIT_RESULT=0x100
  (running)` and `HFI_CTRL_STATUS=1 (HFI initialized)`. The bounded probe then
  verified CM3 reset and retained persistent context/clock votes.
- This establishes the fixed-width ACV parsing/vote path, first GMU firmware
  execution, and HFI controller initialization. It does not establish HFI
  message exchange, GMU DMA, GPU command execution, render/readback, or Metal.
  Optional `GPU_INIT_CX_REGS` SCM service remains unavailable and is nonfatal.
- Next: implement a bounded HFI startup message and pre-mapped MEM_ALLOC path
  with explicit cache ownership. Keep the first GPU execution step to a bounded
  memory write/readback.

## FP6 patch 0157 cmd-db diagnostic phone result

- CI `39760355071` passed; temporary image
  `/tmp/ios-extra-run-39760355071/package/fp6-gmu-cmdb-diagnostic.img`, SHA256
  `bd3a24bce181fcc7c4510ba73a6157d126d15274bfaead9f82bfe8049d822476`.
- One boot captured 95 packets. Log SHA256
  `2eff12f71f275bc4d48dab5fe2d7491312535e0f940dede1fb72436ed76253f1`;
  pcap SHA256 `d6f144827081c75eaf3ce03d4f11e2b7c277c743e857a4847e4476de96c447b2`.
- Read-only cmd-db diagnostics found ACV at BCM ID 5 / address `0x00050068`,
  with valid aux length 8, `unit=1`, `width=0`, `vcd=12`. Parser rejected width 0
  unconditionally. Linux Gen8 marks ACV fixed and doesn't use width. Patch 0158
  permits zero width only for fixed entries; variable SH0/MC0 still require a
  nonzero width. Patch 0158 passed CI and phone validation, documented above.

## FP6 patch 0156 Linux cmd-db lookup retest (CI + phone)

- CI `39758346968` passed for commit `8c8c00233ce086caf4ef840f02948d8e9520153c`;
  kernel SHA256 `72a9a9d0166fd390caf96beeec39d4e08671f3285e18acadbbb58b0229cd5683`.
  Locally packaged image SHA256
  `1cf437c943cb94edbaaa5e0a0f6e62709f57c2d61bab4f9e3a2e2065c55f97fa`.
- One temporary boot captured 92 UDP packets. Log SHA256
  `b40b04abf1a055af6b0906434b68b1550f1978b2b6914edbd1f67fc9621a3e84`;
  pcap SHA256 `2d44cac32e7e86131ea4fea5ac735d1b4510278acc1866b6229bc838d237e0e4`.
- Linux-style scan of all populated cmd-db slave headers still fails on ACV.
  The fail-closed path sends no vote and keeps CM3 reset. Candidate patch 0157
  adds bounded read-only header and ACV/A-name record/aux diagnostics on lookup
  failure, plus a host assertion that missing ACV never submits an RSC command.
  ASan/UBSan passes; CI/phone validation pending.

## FP6 patch 0155 BCM address-ID correction (CI + phone)

- Commit `8462f999359f501ec523daaf1852693e3f384db6` passed CI `39755620038`;
  kernel SHA256 `72a9a9d0166fd390caf96beeec39d4e08671f3285e18acadbbb58b0229cd5683`.
  CI skipped packaging because the stock-DTB URL is unset. Local temporary image
  package round-trip passed with the verified ADT and Volcano DTB:
  `/tmp/ios-extra-run-39755620038/package/fp6-gmu-bcm-address-id.img`, SHA256
  `0d4ff5ab9ee7aef5a1139841bcf6a909ed20d0be7ac73c65b43cf7899bbbf24a`.
- One authorized temporary boot reached USB ECM and captured 93 UDP packets.
  Decoded log SHA256 `6a7bb87ec85d75558f95e9b1e81e6ec5d75e13657054ce097c0ed47a56e7ca0e`;
  pcap SHA256 `d437f9b66424434075057c7951f4fa7a40967c6f57f2f1e9e78d3d99b72b2ea7`.
  Full files are in `/tmp/ios-extra-run-39755620038/logs/`.
- 0155 fixed the BCM slave-ID check: it passes SH0 and MC0, then reports
  `bootstrap BCM metadata missing name=ACV`. No TCS vote was sent and CM3 stayed
  reset. Linux `cmd_db_get_header()` scans populated slave headers in order,
  while the old parser only scanned ID 5. Candidate patch 0156 mirrors that
  lookup and tracks the selected header ID; SH0/MC0 must remain BCM ID 5, and
  address/header plus aux data are checked. Its ASan/UBSan fixture places ACV in
  the next ARC header and passes; it dry-runs against CI buildtree 39755620038.
  CI and phone validation are pending. No firmware execution, HFI exchange, GPU
  command or render was tested.


## FP6 patch 0154: Linux-matched bootstrap DDR vote (source + host only)

- Fairphone Linux `gen8_gmu_device_start()` submits the default pwrlevel
  `bus_min` as a peak-only ICC vote before CM3 release. The verified FP6 value
  is `0x209a8e` kB/s (= 2,136,718 kB/s). Linux Gen8 constructs DDR BCM
  commands for SH0 (width 16), MC0 (width 4), and fixed ACV using runtime cmd-db
  addresses and aux `unit/width/vcd` data; the command encoding and VCD commit
  rules match the candidate implementation.
- Patch 0154 reads and bounds-checks those cmd-db records, validates RPMh RSC
  v3 and an idle ACTIVE TCS, emits the minimum vote, waits for command status
  and TCS idle, then holds the vote. An uncertain transaction stops before
  CM3 release and quarantines the slot. This is an active write sourced from
  Linux; no hardware result exists yet.
- `tests/test_fp6_gmu_boot.py` passes with UBSan and models the BCM records,
  vote calculation, RPMh acknowledgment, FW_INIT and bounded reset. The patch
  applies to the exact XNU file from CI run `39745254929`. GPU execution is
  still not implemented.
- First hardware attempt used CI `39750406760`, image SHA256
  `6093f7f39acac3cb034dc926b94655b100784511f4575b45facc10572d6a3647`. The
  screen showed `bootstrap BCM metadata missing name=SH0`; fail-closed logic
  stopped before CM3 release and no BCM write occurred. No USB ECM/pcap was
  available. Review found BCM entries use cmd-db slave ID 5, while the
  candidate searched ARC ID 3. The subsequent CI `39752494051` log does not
  contain a metadata-missing line; source review found it silently rejected
  BCM resource addresses because the separate address check still required ID
  3, and the test fixture modeled `0x300xx` addresses. Patch 0155 changes that
  check to ID 5 and the fixture to `0x500xx`; ASan/UBSan host test and patch
  application after 0154 pass. Rebuild and phone retry are pending.
- CI `39752494051` / commit `4f68fcb...` included the ID-5 correction and
  passed; image SHA256 `fe97c9fadae1388605b37124550677f596201c3f51bdc151afd6e80d4f835494`
  was temporarily booted with `fp6usb=2`. The 96-packet USB log shows the
  software SMMU walk, clocks, timer, persistent firmware upload and optional
  SCM-unavailable message all behaved as before. BCM lookup still failed at
  SH0; CM3 was not released and no BCM write occurred. Decoded log SHA256
  `dc1eb8596dfaee7c70f0c8a40f056468c235fbf2b9f513361d10cd68aae2f602`;
  pcap SHA256 `c94751cca1fbba39e8129d11d3e3da7ae9ff5bb782498d522cd0a652f918b4d9`.
  The next investigation is the live BCM record/header interpretation, not
  another guessed write. Full continuation is in `FP6_GPU_CONTINUATION.md`.

## FP6 CX timer USB diagnosis and seed fix (2026-10-22)

- CI run `39735265609` passed for `089d4ef39822e751ada55eae9bc53f3ccc4472f2`.
  Image `/tmp/ios-extra-run-39735265609/package/fp6-gmu-timer-diagnostics.img`,
  SHA256 `b5a30a6bce20a730c39529ae08121ddfdbe29c614ad42477b3a21ed9de6c9fef`;
  it was used for one temporary `fastboot boot`, with no partition writes.
- USB capture artifacts are under `/tmp/ios-extra-run-39735265609/logs/`.
  Pcap SHA256 `d297cbf17896b9e36d0afc4709ae6ead0b1eeff7fb7709a9cfdba6a12aca0851`;
  decoded text SHA256 `729d365b3edab8c39364aca208c58e2673738594498b8dfb438ebba4c643af32`.
  The 405-packet capture confirms CPU time advanced while CX remained static at
  its seed. That is why XNU's post-seed advance check refused firmware upload.
- Patch 0152 follows Linux `gen8_cx_timer_init()`: seed the CX counter and
  proceed without an extra CX readback, offset, advance or rate gate. The host
  test models the measured static counter and passes. Commit
  `09a398b2d85e1a38e17558003ecdb3e0faa64dc1` passed CI run `39739290127`;
  kernel SHA256 `9a5d96ef3eb2a2d9b6e854cdaf05852fce850ca18fe57e87e4376364e770a630`.
  The packaged header-v2 image
  `/tmp/ios-extra-run-39739290127/package/fp6-gmu-cxtimer-linux-seed.img` has
  SHA256 `1062709ab0ab0d7a88b8bc5a15a25a3141b5bb4b48557c19741a54b6272ec881`;
  it includes product ADT `4da4226e6b9ac393ff22b66a304d9172d6be2bfd6d558348a47379c51aab1d80`
  and DTB `8198534128258bfe7b05bbb5b227affc181aa49b376884c08eae8564fce124e3`.
- Initial checks found the device in `fastbootd`, then absent, so no boot was
  issued at that point. A later explicitly authorized test booted 0152 once;
  its result is recorded below. No partition write occurred.
- Linux Gen8 votes minimum DDR bandwidth after GMU firmware/version setup and
  before GMU start/HFI. The current XNU RPMh path handles ARC/VRM, not the
  interconnect/BCM vote; that is the next source and hardware step after the
  timer fix is measured on device.
- The 0152 phone test was run once from bootloader fastboot. `fastboot boot`
  returned OKAY, but the phone panicked before USB ECM appeared. User-provided
  panic: `phystokv_range: illegal pa: 0x3df4000 phys base 0x900000000 size
  0x100000000` at `arm_vm_init.c:406`. No pcap exists; the fastboot transcript
  is `/tmp/ios-extra-run-39739290127/logs/phone-0152-linux-cxtimer-seed-fastboot.txt`.
  No second boot/recovery command was issued.
- Likely source-order suspect, not confirmed without a stack: the newly reached
  HFI backing-page WCOMB change calls `pmap_set_cache_attributes()`, which can
  call `phystokv_range()` on the page PA. The address is outside the configured
  RAM window. Wait for/inspect the full panic backtrace before altering memory
  allocation or cache attributes.
- Follow-up against the exact CI `39739290127` buildtree: `0x3df4000` is the
  offset `0x903df4000 - 0x900000000`, within the configured high-RAM window if
  interpreted as a base-relative page number. XNU's `pmap_find_phys()` PTE walk
  returns an absolute `ppnum_t` and `ptoa_64()` reconstructs a PA; `pa_index()`
  is explicitly relative to `vm_first_phys`. This makes an index-versus-absolute
  page-number mixup a concrete lead, but does not identify the panic caller.
  No stack or pcap is available, so no allocator/cache change is justified yet.
- Separate read-only review of HackiOS: its Mesa Freedreno Darwin port adapts
  MSM DRM calls to an IOKit user client; its XNU service implements GEM buffers,
  submission and fence waits. AIR translates to NIR/ir3, while Apple's Metal
  object/submission ABI remains separate. Reference commits and file paths are
  in `NOTES.md`.

## FP6 HFI cache-path isolation (0153, 2026-10-22)

- The only new operation after the previously successful 0149 HFI-controller
  boot that rewrote a CPU page's WIMG type was 0150's
  `pmap_set_cache_attributes(..., VM_WIMG_WCOMB)` for the HFI backing pages.
  XNU routes that API through cache-attribute page-table updates; this matches
  the panic's `phystokv_range()` failure shape, although the absent panic stack
  means causality remains unproven.
- Patch 0153 removes that WIMG rewrite for the bounded `HFI_CTRL_INIT` probe.
  CPU-initialized buffers remain ordinary cached memory and use the existing
  `fp6_gmu_domain_publish()` clean before the GMU is routed. This is sufficient
  for the current probe, which does not exchange HFI messages or inspect
  GMU-written queue state. Any later HFI messaging must explicitly clean CPU
  writes before handing a queue to the GMU and invalidate GMU-written cache
  lines before CPU reads; it cannot assume this probe's cache policy is enough.
- `tests/test_fp6_gmu_boot.py` passes normally and with ASan/UBSan; it now
  verifies publication still occurs and the integrated source no longer calls
  `pmap_set_cache_attributes()`. `git diff --check` passes. `sweet_gpu.c`
  compiles with system Clang against the exact CI buildtree from run
  `39739290127` (`0 of 1 files failed`). The repository's configured Swift
  Clang is absent, so the local replay used `/usr/bin/clang`.
- Commit `e53c66ab499d75d2101b1736ffbb85a7642e64f8` passed CI run
  `39745254929`; packaging was skipped because `FP6_STOCK_DTB_URL` is unset.
  The verified CI kernel was locally packaged as
  `/tmp/ios-extra-run-39745254929/package/fp6-gmu-hfi-cache-isolation.img`
  (SHA256 `cca41889433f9c1005ddf0aa79513f5be29f49a0bbb1b49808bc150de0d18c5e`).
- One temporary phone boot produced a complete USB log (411 packets, 121,789
  bytes) and reached launchd without the prior panic. The phone confirms
  `FW_INIT_RESULT=0x100`, `HFI_CTRL_STATUS=1`, and verified CM3 reset after the
  bounded probe; see the exact hashes and limits in the current-state entry in
  `NOTES.md`. This supports 0153 as the fix for the observed panic, but the
  panic stack was unavailable, so it does not prove the original call site.
  HFI messages, GMU DMA and GPU execution have not been tested.

## FP6 Gen8 minimum DDR vote source trace (2026-10-22)

- Local Fairphone source at kernel commit `9535e0f08` and its checked-out
  graphics-kernel module show `gen8_gmu_device_start()` calling
  `icc_set_bw(path, 0, kBps_to_icc(ddr_table[default_pwrlevel.bus_min]))`
  after firmware/version/config setup and before CM3 start/HFI. The verified
  FP6 stock DT has initial pwrlevel 8, `bus_min=2`, and DDR table value
  `0x209a8e` kB/s (about 2.14 GB/s). This is a peak-only bootstrap request.
- The later Gen8 HFI bandwidth table is constructed for DDR BCMs SH0/MC0/ACV
  and optional CN0. KGSL uses runtime cmd-db resource addresses and aux fields
  `unit`, `width`, and `vcd` to scale votes and group commits. The cmd-db is
  runtime AOP memory at `0x81c60000`; the per-BCM metadata is not in the stock
  DT or source checkout. A bounded read-only metadata capture is required
  before implementing direct XNU BCM commands. No vote values should be
  guessed. The initial vote must precede GMU start; the HFI bandwidth table is
  delivered later during HFI startup.

This is the full per-step record that used to be `NOTES.md`: exact images, hashes,
CI runs, phone results and the reasoning at the time. The current state and the next
action are in [NOTES.md](../NOTES.md) and [HANDOFF.md](../HANDOFF.md). Entries that say
"not yet built/booted" were true when written; newer entries supersede them.

## FP6 0150 follow-up: phone counter reads backward (2026-10-22)

- CI run `39730474027` passed for `6c248dd`. Kernel SHA256
  `1dccb4fb5992417c37b73c28fc74d49e30c2f7dc8b3e2050fd5b8cfd08a02228`.
  Header-v2 image
  `/tmp/ios-extra-run-39730474027/package/fp6-gmu-timer-wcomb.img` SHA256
  `f2b92b5fcfeb6af4e86a953dae8202b12abda5c1f700e8a9c59cd51d69137845`.
- Phone console and USB log both show timer refusal `valid=0/16`,
  `zero=0 shorter=0 outlier=0 read=0..0 write=0..0`; all samples were
  discarded before timing-cost collection. Firmware upload, SCM CX setup, CM3
  release and HFI_CTRL did not run. The SMMU software table-walk test passed
  but stayed contained (`route_live=0`, bank reserved).
- Capture: 705 UDP packets, 168,631 log bytes. Pcap
  `/tmp/ios-extra-run-39730474027/logs/phone-0150-timer-wcomb.pcap`, SHA256
  `048725f34765776a36d4ce5cbc13733854bbf47875ed30b491ca095e15f59dfe`; decoded
  text SHA256
  `e14fbf9b65b5a6dd6ff6f4d6d791f254933d0530ec79ad71d8d7bcbc94aed83a`.
- XNU's `ml_get_hwclock()` calls its nonspeculative CNTVCT timebase. The prior
  FP6 code read raw CNTPCT; because the phone run discarded every sample as
  backward, the next local change uses `ml_get_hwclock()` and prints backward
  counters plus the last counter triple. This is a source-based diagnosis, not
  yet CI-built or phone-tested.
- The test helper's ECM loop retried two separate `pkexec` commands every
  100 ms after setup failure, and capture/cleanup used additional elevated
  commands. The helper is revised to do interface setup, capture, and
  exact-path stale-capture cleanup in one bounded root invocation, with no
  authorization retries or follow-up kill prompt. The previous root tcpdump
  is still live because the attempted cleanup authorization was denied; the
  next authorized run can stop only its exact pcap path before capturing anew.

## FP6 0150 follow-up: zero-skew timer and HFI CPU cache attributes (2026-10-22)

- The latest console photo reproduces the USB log result: timer validation
  refused `valid=0/16 CNTFRQ=19200000`; later SMMU context test remained
  contained (`route_live=0`, bank reserved). Firmware upload, SCM CX setup,
  CM3 release and HFI_CTRL were not attempted.
- Local patch follow-up now accepts equal CPU/CX access costs as zero-skew
  samples, which the 19.2 MHz timer can produce through quantization. It logs
  read/write ranges and counts shorter/outlier samples. Host fault-injection
  exercises a 16/16 zero-skew case and passes normally and under ASan/UBSan.
- It also converts the five 16 KiB CPU pages backing the 0x12000-byte shared
  HFI allocation to `VM_WIMG_WCOMB` before writing queue headers. It confirms
  physical contiguity, only accepts pages currently DEFAULT or WCOMB, applies
  the pmap attribute, and verifies all five pages before SMMU domain publish.
  This is XNU's CPU cache policy; GMU translation remains 4 KiB. The pmap
  functions are declared explicitly because the BSD-visible header config
  omitted their prototypes.
- `test_fp6_gmu_boot.py`, `test_gpu_probe.py`, `test_rpmh_arc.py` and
  `test_xnu_cc.py` pass. Both C harnesses pass with ASan/UBSan. System-Clang
  AArch64 single-file compilation against the exact 39728088129 build tree
  reports 0/1 failed. These are local source checks only: no CI build or
  phone test exists for this update yet. The complete patch is tracked at
  `xnu/patches/0150-fp6-gmu-cx-timer-scm.patch` but remains uncommitted.

## FP6 0150 timer preflight — CI green, phone stopped safely (2026-10-22)

- Commit `c1de4a39ed6dfc2307311fc9d09115f1d3085f5a`, CI
  [39728088129](https://github.com/ersascape/ios-extra/actions/runs/39728088129)
  passed. Kernel SHA256SUMS verified. CI image packaging skipped because
  `FP6_STOCK_DTB_URL` is not configured; locally packaged with the verified
  product ADT and stock DTB. Header-v2 image `/tmp/ios-extra-run-39728088129/package/fp6-gmu-cxtimer-scm`
  SHA256 `ff170c41e125c5f1e91431f14a281db4dfe7855d4e55c8d92274f747d489ebd8`.
- Checked `fastboot devices`: one target. Captured USB ECM before issuing a
  single `fastboot boot`; serial was redacted from saved command output. Phone
  reached launchd and answered ECM ping. No partition or flash operation.
- Phone log confirms inherited GMU clock `0x2001`, CM3 reset asserted, MX
  floor acknowledged, GPLL0 600 MHz, GMU350/HUB200 enabled, then
  `CX timer refused valid=0/16 CNTFRQ=19200000` and firmware upload refused.
  SCM CX setup and CM3 release were not reached. The following SMMU context
  test passed and contained (`route_live=0`, `bank_reserved=1`).
- Pcap `/tmp/ios-extra-run-39728088129/logs/phone-0150-cxtimer-scm.pcap`
  SHA256 `e7d6cc8bcaaa7c35b1923a85765e551ee93ebc1eedcf0732bdbc318575949c10`;
  decoded text SHA256
  `36c5f8cb4638a0a5436b49e14538160d7907f309f1c6e2a793328bc06ec74a89`.
- The sampler had rejected `write_cost == read_cost`; zero-skew equality is
  plausible at 19.2 MHz counter resolution. The local follow-up accepts equal
  tick costs and records read/write ranges plus shorter/outlier counts. Normal
  and ASan/UBSan tests cover all-zero skew; a system-Clang AArch64 syntax compile
  against run 39728088129 buildtree passes. The update is not yet in CI or on
  the phone.

## 0098 CI started at handoff — 2026-10-19

- Implementation/checks/handoff commit `edab65c998a917d5e450b730aa4d0ff2e8e6032e` pushed.
- [CI 39307039113](https://github.com/dipa-studio/ios-extra/actions/runs/39307039113)
  is **in progress**, not yet verified green. No 0098 download, package, image
  hash or phone result exists. HANDOFF pins this exact run/head and package command.
- User confirmed 0097 home screen and requested documentation before stopping
  for the usage limit. No further phone test was started. All run evidence and
  first-start blockers are preserved; repository working tree is clean after
  the documentation commit.

## Handoff — 0098 local implementation, 2026-10-19

- User confirmed the 0097 home screen and requested all work documented before
  stopping for the usage limit. No further phone boot is authorized in this session.
- `0098-sweet-gpu-exact-ao-mask-readback.patch`, same mode 15, baseline c242eb7
  (measured 0097), accepts only offset +0x24c18 / write 0xffffffff / read 0x3f.
  Mainline write value stays unchanged. All other set/restore comparisons exact.
- Normal and ASan/UBSan suites pass: exact AO tuple; all six missing AO bits,
  unexpected AO high bits/full all-ones, every missing HFI bit and HFI=0x3f
  refused (42 alternatives); all 20 zero-write preconditions and previous
  set/restore/quarantine/full-chain/mode/replay cases retained.
  Arm64 compile 0 of 1 failed; patch equals isolated diff. Full CI and phone
  validation pending at implementation. No 0098 image exists yet.
- Next: verify push-triggered CI and its exact source, package mode 15, always
  check fastboot first, then measure the second mask. HANDOFF has commands and
  full first-start draft review, including SMMU global-fault IRQ containment.

## Phone result — 0097 IRQ mask/restore, 2026-10-19 18:53 UTC

- Always checked fastboot first: exactly one already present, serial redacted.
  Announced first mask writes and temporarily booted once at 18:53:52 UTC;
  send 0.423s, boot 0.134s, total 0.563s. Ping succeeds. **User confirmed the home screen.**
- Image `shim/out/shim-boot-0097-irqmask.img`, SHA256
  `9ae01e4289113accd0ad18fcf15e436afd4cfaecc5330e8b69b5b63760f0ca7e`, mode 15;
  source 01dbc6e5571eacdca32f7c0d60bc34ce0d77ab00, green CI 39305068882.
- Capture: 462 UDP packets, 206191 decoded bytes; local/ignored
  `ios-extra-work/logs/phone-0097-irqmask.{pcap,txt}` plus sanitized fastboot log.
  Initial report 0 partial; raw values below from complete cached report 1.
- **Stopped at the intended readback guard:** AO mask +0x24c18, wrote all ones,
  read 0x3f. Restored it to 0. attempted=1, masked=0 (strict full-word match
  failed), restored=1, quarantined=0. GMU2HOST mask was never written.
  All six final preflight values match 0096, reset/busy/init=1/0/0 and
  GX unchanged 0x00222001. No CM3 execution or GX power.
- Lower checks pass: RSC wake ACK=3/BUSY=0, stop=0x01010006 and state restored;
  buffer ATOS 29/29, inactive=1 and known inert S2CR/CBAR residue, FSR/sGFSR=0;
  firmware bad=0, same nine init differences, clock/CX/votes rolled back.
- Mainline XML declares AO status bits 0..5, consistent with the six retained mask
  bits. It does not define a mask writable-width field. Next patch accepts only
  the specific measured tuple (+0x24c18, wrote=0xffffffff, got=0x3f), still writes
  the mainline all-ones value, and proceeds to test GMU2HOST masking. No broad
  ignored-bit policy or hardware-vs-filtering ownership claim is justified.

```text
SWEET GPU: IRQ mask attempted=1 masked=0 restored=1 quarantined=0 masks=0x0000003f/0x00000000 reset/busy/init=0x1/0x0/0x0 GX=0x00222001/0x00222001 result: interrupt mask write did not read back
SWEET GPU: IRQ mask wr +0x24c18 wrote=0xffffffff got=0x0000003f
SWEET GPU: IRQ mask wr +0x24c18 wrote=0x00000000 got=0x00000000
SWEET GPU: IRQ mask final AO_HOST_INTERRUPT_MASK +0x24c18 = 0x00000000
SWEET GPU: IRQ mask final GMU2HOST_INTR_MASK +0x1464c = 0x00000000
SWEET GPU: IRQ mask final GMU2HOST_INTR_INFO +0x14648 = 0x00000000
SWEET GPU: IRQ mask final AO_HOST_INTERRUPT_STATUS +0x24c14 = 0x00000000
SWEET GPU: IRQ mask final AO_AHB_FENCE_CTRL +0x24c40 = 0x00000000
SWEET GPU: IRQ mask final RPMH_POWER_STATE +0x143b0 = 0x0000000f
```

## 0097 full build and verified image — 2026-10-19

- Full [CI 39305068882](https://github.com/dipa-studio/ios-extra/actions/runs/39305068882)
  **passed** on `01dbc6e5571eacdca32f7c0d60bc34ce0d77ab00`.
- Kernel SHA256 `61d48b8d440b3f03ceb0c7370019aa5a7210971bbea75281fed40ea2353d19bc`;
  SHA256SUMS passed. `_sweet_gpu_probe` at 0xfffffe00074fa838 and
  `_sweet_rpmh_arc_set` at 0xfffffe00074f8548.
- CI GPU source SHA256 `b6040548e42217a8071ae8dff01b8b5ccbdce797c269c08d90cede698ba14b2b`;
  firmware header `2c76898351726399ac212d29c3ca7670786ad00c77e5be28da3b847af0baedf2`;
  RPMh source `fc3669172ee14592cbee2f4312450e68ca9eac7870612d7d669fa2872bf404ca`.
  All byte-identical to locally tested files. Artifacts local/ignored in
  `ios-extra-work/out-0097` and `ci-0097`.
- Image `shim/out/shim-boot-0097-irqmask.img`, 17268736 bytes, SHA256
  `9ae01e4289113accd0ad18fcf15e436afd4cfaecc5330e8b69b5b63760f0ca7e`,
  `sweetgpu=15`; manifest `shim/out/manifest-0097.json`. Payload/boot arguments
  round-trip exactly. No first-start draft is included.
- Always checked fastboot first: exactly one already present, serial redacted.
  Announced first interrupt-mask writes/restore with CM3 reset and performed the
  authorized single temporary boot. Capture/result recorded separately above.
- Pruned reproducible 0093/0094 kernel/buildtree/image/payload/unpack artifacts;
  all phone logs/manifests retained, along with 0095/0096/0097 working artifacts.

## Implementation — 0097 interrupt mask/restore (local checks pass)

- `0097-sweet-gpu-irq-mask-restore.patch`, mode 15, baseline 328cafb (0096).
  Separately tests all-ones AO and GMU2HOST masks and restores both zero defaults,
  with CM3 still held reset. Exact six-word 0096 cached/live state and fresh
  reset/busy/init/GX gates precede all new writes. No clears or CM3/GX controls.
- Normal/ASan/UBSan host suites pass: all 20 zero-write refusals, exact success
  order, either set/restore failing, status/reset/idle quarantine, other state
  changes, full chain, mode isolation and cached replay. Arm64 0 of 1 failed.
  Patch equals isolated diff; full CI/phone pending.
- Unexpected pending status or reset/idle change triggers best-effort all-ones
  masks and explicit incomplete rollback, without clearing the evidence. Raw final
  reads establish actual mask state. No firmware release is present.

## Phone result — 0096 read-only IRQ/fence preflight, 2026-10-19 18:39 UTC

- Checked fastboot first: exactly one already present, serial redacted. Announced
  and performed one temporary boot at 18:39:28 UTC; send 0.424s, boot 0.134s,
  total 0.565s. Ping succeeds; **user confirmed the home screen**.
- Image `shim/out/shim-boot-0096-irqpreflight.img`, SHA256
  `3b9f7aa6e1cfdb337e5e4639ee57cea4b558c9396f4c18902e4f43bc14b4dbef`, mode 14;
  source edd2b796ed7ff02434c42942c490543c17f95456, green CI 39303111412.
- Capture: 461 UDP packets, 198599 decoded bytes, local/ignored
  `ios-extra-work/logs/phone-0096-irqpreflight.{pcap,txt}` and sanitized
  `phone-0096-irqpreflight-fastboot.txt`. Report 0 partial; all six raw values
  below are from complete cached report 1. No panic marker observed.
- Both mask words and both pending-status words are 0; fence control is 0;
  RPMH power state is 0x0f. Source `a6xx_gmu_irq_disable()` masks both sources
  with all ones; our zero defaults must not be assumed safe during execution.
  This dump proves readability, not mask writability or interrupt delivery.
- Lower probes still pass: RSC wake ACK=3/BUSY=0 and stop=0x01010006,
  controls/state restored; pre-boot 29/29; buffer ATOS 29/29, inactive=1 and known
  inert S2CR/CBAR residue only; FSR/sGFSR=0. Firmware bad=0, nine constrained
  init readbacks unchanged, CX/clock/vote cleanup complete. CM3 stayed reset,
  GX remained off. No firmware execution or GPU command.
- Next measured prerequisite: a separate mask/verify/restore test with CM3 held
  reset. Do not combine an unproved mask write with the first CM3 release.

```text
SWEET GPU: IRQ preflight AO_HOST_INTERRUPT_MASK +0x24c18 = 0x00000000
SWEET GPU: IRQ preflight GMU2HOST_INTR_MASK +0x1464c = 0x00000000
SWEET GPU: IRQ preflight GMU2HOST_INTR_INFO +0x14648 = 0x00000000
SWEET GPU: IRQ preflight AO_HOST_INTERRUPT_STATUS +0x24c14 = 0x00000000
SWEET GPU: IRQ preflight AO_AHB_FENCE_CTRL +0x24c40 = 0x00000000
SWEET GPU: IRQ preflight RPMH_POWER_STATE +0x143b0 = 0x0000000f
SWEET GPU: IRQ preflight read=6/6 result: read-only dump complete; masks/fence unchanged; CM3 held reset
```

## 0096 full build and verified image — 2026-10-19

- Full [CI 39303111412](https://github.com/dipa-studio/ios-extra/actions/runs/39303111412)
  **passed** on `edd2b796ed7ff02434c42942c490543c17f95456`.
- Kernel SHA256 `36b92c5cd4cadbf0bc8c67871afcded91e09a60ec737c98d762d1b3899d555cb`;
  SHA256SUMS passed. `_sweet_gpu_probe` at 0xfffffe00074fa838 and
  `_sweet_rpmh_arc_set` at 0xfffffe00074f8548.
- CI GPU source SHA256 `083d74dfec1ed99e5d1447b9e898622e46ff213bcc873d5531160d21895a5abf`;
  firmware header `2c76898351726399ac212d29c3ca7670786ad00c77e5be28da3b847af0baedf2`;
  RPMh source `fc3669172ee14592cbee2f4312450e68ca9eac7870612d7d669fa2872bf404ca`.
  All byte-identical to the locally tested isolated files. Artifacts local/ignored
  in `ios-extra-work/out-0096` and `ci-0096`.
- Image `shim/out/shim-boot-0096-irqpreflight.img`, 17268736 bytes, SHA256
  `3b9f7aa6e1cfdb337e5e4639ee57cea4b558c9396f4c18902e4f43bc14b4dbef`,
  `sweetgpu=14`; manifest `shim/out/manifest-0096.json`. Unpacked payload and
  boot arguments round-trip exactly. The first-start draft is excluded.
- Checked fastboot first: exactly one device already present, serial redacted.
  Announced and started the authorized single temporary read-only test. Phone
  observations recorded separately after capture; no flash or reboot command.

## Implementation — 0096 read-only IRQ/fence preflight (local checks pass)

- Patch `0096-sweet-gpu-irq-fence-preflight.patch`, mode 14, baseline 4be318c
  (validated 0095). Source audit of `a6xx_gmu_resume()` found interrupt setup
  outside the narrower fw_start sequence used for the 0094 dump; mask defaults
  have not been measured. Read six IRQ/fence/power-state words before first release.
- Normal and ASan/UBSan suites pass, including all 13 zero-write refusals,
  byte-for-byte unchanged MMIO, exact offsets/values (including a legitimate
  all-ones mask), lower-mode exclusion, reset preservation and cached replay.
  Arm64 compile 0 of 1 failed. Isolated diff equals the patch. CI/phone pending.
- No new writes or CM3 release. The larger first-start draft was saved outside Git
  as `ios-extra-work/gmu-first-start-draft.patch`, based on 0095. Local arm64 object
  compilation alone passed for that draft; it has no host/full-CI/phone validation
  and omits interrupt protection. It is not in the repository patch chain or a
  boot image. Rework only after the IRQ/fence measurement.

## Phone result — 0095 RSC wake/stop, 2026-10-19 18:18 UTC

- Checked fastboot first: exactly one device already present, serial redacted.
  Announced the first retention/wake request and performed one temporary boot.
  Boot issued 18:18:46 UTC; send 0.417s, boot 0.134s, total 0.564s; ping succeeds.
  **User confirmed the home screen.** No flash or reboot command.
- Image `shim/out/shim-boot-0095-rscwake.img`, SHA256
  `0e33a1a21c65f093b463c6279e60b2968c48deb47efc0e80b2ef6c1c289bb860`, mode 13;
  source 515acba25c91c7d4bb16c82576d50efba9e869d7, green CI 39300239967.
- Capture: 453 UDP packets, 200503 decoded bytes; local/ignored files
  `ios-extra-work/logs/phone-0095-rscwake.{pcap,txt}` and
  `phone-0095-rscwake-fastboot.txt`. Initial report 0 partial; raw transition below
  is from cached report 1. No panic marker observed.
- **Measured:** retention set/restored 1/0; wake ACK becomes **3** (bit 1 set,
  bit 0 remains set), on poll 2; SEQ_BUSY=0 on poll 1. Stop completes on poll 2,
  STATUS=0x01010006. Before/awake/final STATUS=0x01010006/0x0100000c/0x01010006.
  All six sampled RSC/control words return exactly to their incoming values,
  controls-restored=1 and state-restored=1. CM3 reset stays 1 throughout and
  GX GDSCR stays 0x00222001 (collapsed). No firmware execution or GPU command.
- Lower probes still pass: pre-boot 29/29, buffer ATOS 29/29, mapping inactive=1,
  inert S2CR/CBAR residue only, FSR/sGFSR=0; firmware 8192 words bad=0;
  same nine init differences; CX/clock/vote cleanup complete.
- **Gate passed:** this proves RSC wake, idle completion and return to stop under
  the observed init readbacks. It does not identify which layer owns those
  readbacks, prove every rail vote, or prove a GMU DMA stream. Next separate patch:
  first bounded CM3 firmware start, always reset again before existing rollback.

```text
SWEET GPU: RSC wake started=1 ack=1 polls=2 raw=0x3 busy-idle=1 polls=1 raw=0x0 stop-attempted=1 done=1 polls=2 status=0x1010006
SWEET GPU: RSC wake GX GDSCR before/awake/final=0x00222001/0x00222001/0x00222001
SWEET GPU: RSC wake +0x14730 before=0x00000000 awake=0x00000001 final=0x00000000
SWEET GPU: RSC wake +0x24c1c before=0x00000000 awake=0x00000002 final=0x00000000
SWEET GPU: RSC wake +0x24c20 before=0x00000001 awake=0x00000003 final=0x00000001
SWEET GPU: RSC wake +0x23404 before=0x00000001 awake=0x00000000 final=0x00000001
SWEET GPU: RSC wake +0x23010 before=0x01010006 awake=0x0100000c final=0x01010006
SWEET GPU: RSC wake +0x14000 before=0x00000001 awake=0x00000001 final=0x00000001
SWEET GPU: RSC wake retention on/off=0x1/0x0 controls-restored=1 state-restored=1 snapshots=7 (before=1 awake=2 final=4) result: wake/stop complete; CM3 stayed in reset
```

## 0095 full build and verified image — 2026-10-19

- Full [CI 39300239967](https://github.com/dipa-studio/ios-extra/actions/runs/39300239967)
  **passed** on `515acba25c91c7d4bb16c82576d50efba9e869d7`.
- Kernel SHA256 `fac7e775c991dddd83fd84fdf37d44da176627039bfa874adb531451a31d7fa7`;
  SHA256SUMS passed. `_sweet_gpu_probe` at 0xfffffe00074fa838 and
  `_sweet_rpmh_arc_set` at 0xfffffe00074f8548.
- CI GPU source SHA256 `6bb7118554d9baf2d62ffaff31fc10bf67fa5005c2d4ed7a1809577ae4aaa176`;
  firmware header `2c76898351726399ac212d29c3ca7670786ad00c77e5be28da3b847af0baedf2`;
  RPMh source `fc3669172ee14592cbee2f4312450e68ca9eac7870612d7d669fa2872bf404ca`.
  All byte-identical to locally tested isolated files. Artifacts ignored/local
  in `ios-extra-work/out-0095` and `ci-0095`.
- Image `shim/out/shim-boot-0095-rscwake.img`, 17268736 bytes, SHA256
  `0e33a1a21c65f093b463c6279e60b2968c48deb47efc0e80b2ef6c1c289bb860`,
  `sweetgpu=13`; manifest `shim/out/manifest-0095.json`. Unpacked payload and
  boot arguments round-trip exactly.
- Checked fastboot first: exactly one device already present (serial redacted).
  Announced TCM retention + RSC wake/stop, with CM3 held reset, then started the
  authorized single temporary test. No flash or reboot command. Phone result
  recorded separately after capture.

## Implementation — 0095 bounded RSC wake/stop (local checks pass)

- Patch `0095-sweet-gpu-rsc-wake-stop.patch`, mode 13; isolated source baseline
  85017d8 (validated 0094). Smaller step 4a before any CM3 release: TCM retention,
  wake ACK bit 1, BUSY=0, return to stop, restore retention. GX snapshots included.
- Every new precondition comes from the fresh lower-mode proof and measured
  stopped state, except GX is gated by powered-off/collapsed field predicates
  rather than an unmeasured whole register value with CX held on. Exactly the nine
  known init signatures are allowed; every tuple field is checked. All polls have
  10 ms bounds. No CM3/GX control or HFI command added.
- Normal/sanitized host suites pass: 57 zero-write refusals, exact write ordering,
  all three handshake timeouts, retention set/restore failures, unexpected GX
  change, reset preservation, replay and lower-mode exclusion. Arm64 compile
  0 of 1 failed; isolated diff equals the patch. CI and phone pending.

## Phone result — 0094 pre-boot GMU dump, 2026-10-19 18:01 UTC

- User confirmed fastboot. First check saw zero devices during USB reconnection;
  the immediate brief retry saw exactly one (serial redacted), then the helper
  rechecked before one temporary boot. No flash or reboot issued.
- Boot issued 18:01:14 UTC; send 0.419s, boot 0.134s, total 0.598s. Ping succeeds;
  **the user confirmed the home screen**. Image
  `shim/out/shim-boot-0094-gmupreboot.img`, SHA256
  `f1d9e4f9db5f8c468803135b591cf1b1dc9c1dc4d58512f91378746cbb2bf9c0`,
  mode 12; source 8104c7466c39d66b3169f1c420ac630312c8eb02, CI 39297388718.
- Capture: 462 UDP packets, 191276 decoded bytes; local/ignored files
  `ios-extra-work/logs/phone-0094-gmupreboot.{pcap,txt}` and
  `phone-0094-gmupreboot-fastboot.txt`. Report 0 partial; all 29 pre-boot values,
  29 ATOS results and 20 write/readbacks below are from cached report 1.
  No panic marker observed.
- **Measured:** all 29 registers read successfully. After the lower-mode RSC stop,
  ACK=1 and SEQ_BUSY=1 while REQ=0. This is a stopped-state observation, not a
  failed wake (no wake request has been sent). Power CTRL=0x09c40406 and both
  hysteresis words=0x000a2710; do not assume they start at zero. DTCM version=0,
  CM3 reset=1, busy/init=0, CFG=0x52. Other HFI/log/cache/RPMH configuration=0.
- Buffer checks remain 29/29; final SMR/S2CR/SCTLR/CBAR=0/3/0/0x10000,
  inactive=1/restored=0, FSR/sGFSR=0. Narrow CBAR expected diagnostic is now 0
  (normalization fixed), still reads back 0x10000. Firmware 8192/8192 bad=0;
  RSC init remains 48 writes, 9 known differences, stop status=0x01010006;
  CX and clock cleanup complete. No GMU processor release or GX power.
- **Next measured question:** split step 4 further: mainline's bounded RSC wake
  (ACK bit 1, then SEQ_BUSY=0), return to stop, retain CM3 reset. This tests wake
  with the nine constrained RSC/PDC readbacks before attempting firmware execution.

```text
SWEET GPU: pre-boot GMU GENERAL_7 +0x14730 = 0x00000000
SWEET GPU: pre-boot GMU RSCC_CONTROL_REQ +0x24c1c = 0x00000000
SWEET GPU: pre-boot GMU RSCC_CONTROL_ACK +0x24c20 = 0x00000001
SWEET GPU: pre-boot GMU RSCC_SEQ_BUSY_DRV0 +0x23404 = 0x00000001
SWEET GPU: pre-boot GMU CM3_SYSRESET +0x14000 = 0x00000001
SWEET GPU: pre-boot GMU CM3_BOOT_CONFIG +0x14004 = 0x00000000
SWEET GPU: pre-boot GMU CM3_FW_INIT_RESULT +0x14070 = 0x00000000
SWEET GPU: pre-boot GMU CM3_FW_BUSY +0x14068 = 0x00000000
SWEET GPU: pre-boot GMU DTCM_FW_VERSION +0xafe0 = 0x00000000
SWEET GPU: pre-boot GMU HFI_QTBL_ADDR +0x14614 = 0x00000000
SWEET GPU: pre-boot GMU HFI_QTBL_INFO +0x14610 = 0x00000000
SWEET GPU: pre-boot GMU AHB_FENCE_RANGE_0 +0x24c44 = 0x00000000
SWEET GPU: pre-boot GMU CM3_CFG +0x140b4 = 0x00000052
SWEET GPU: pre-boot GMU HFI_SFR_ADDR +0x14608 = 0x00000000
SWEET GPU: pre-boot GMU PWR_COL_CP_MSG +0x14400 = 0x00000000
SWEET GPU: pre-boot GMU PWR_COL_CP_RESP +0x14404 = 0x00000000
SWEET GPU: pre-boot GMU SYS_BUS_CONFIG +0x1303c = 0x00000000
SWEET GPU: pre-boot GMU ICACHE_CONFIG +0x13000 = 0x00000000
SWEET GPU: pre-boot GMU DCACHE_CONFIG +0x13004 = 0x00000000
SWEET GPU: pre-boot GMU PWR_COL_INTER_FRAME_CTRL +0x14300 = 0x09c40406
SWEET GPU: pre-boot GMU PWR_COL_INTER_FRAME_HYST +0x14304 = 0x000a2710
SWEET GPU: pre-boot GMU PWR_COL_SPTPRAC_HYST +0x14308 = 0x000a2710
SWEET GPU: pre-boot GMU RPMH_CTRL +0x143a0 = 0x00000000
SWEET GPU: pre-boot GMU GENERAL_0 +0x14714 = 0x00000000
SWEET GPU: pre-boot GMU GENERAL_1 +0x14718 = 0x00000000
SWEET GPU: pre-boot GMU GENERAL_6 +0x1472c = 0x00000000
SWEET GPU: pre-boot GMU AO_HOST_INTERRUPT_STATUS +0x24c14 = 0x00000000
SWEET GPU: pre-boot GMU HFI_CTRL_INIT +0x14618 = 0x00000000
SWEET GPU: pre-boot GMU HFI_CTRL_STATUS +0x14600 = 0x00000000
SWEET GPU: pre-boot GMU read=29/29 result: read-only dump complete; no start writes or CM3 release
SWEET GPU: buffers pa=0x104664000 bytes=0x10000 stage=3 checks=29/29 passed=29 inactive=1 restored=0
SWEET GPU: buffers IOVA dummy/debug/log/HFI=0x60000000/0x60001000/0x60005000/0x60009000 sizes=4096/16384/16384/16384 HFI-size=120
SWEET GPU: buffers ATOS va=0x60000000 PAR=0x4000000104667b80 expect=mapped
SWEET GPU: buffers ATOS va=0x60000fff PAR=0x104667b80 expect=mapped
SWEET GPU: buffers ATOS va=0x60001000 PAR=0x104668b80 expect=mapped
SWEET GPU: buffers ATOS va=0x60001fff PAR=0x104668b80 expect=mapped
SWEET GPU: buffers ATOS va=0x60002000 PAR=0x104669b80 expect=mapped
SWEET GPU: buffers ATOS va=0x60002fff PAR=0x104669b80 expect=mapped
SWEET GPU: buffers ATOS va=0x60003000 PAR=0x10466ab80 expect=mapped
SWEET GPU: buffers ATOS va=0x60003fff PAR=0x10466ab80 expect=mapped
SWEET GPU: buffers ATOS va=0x60004000 PAR=0x10466bb80 expect=mapped
SWEET GPU: buffers ATOS va=0x60004fff PAR=0x10466bb80 expect=mapped
SWEET GPU: buffers ATOS va=0x60005000 PAR=0x10466cb80 expect=mapped
SWEET GPU: buffers ATOS va=0x60005fff PAR=0x10466cb80 expect=mapped
SWEET GPU: buffers ATOS va=0x60006000 PAR=0x400000010466db80 expect=mapped
SWEET GPU: buffers ATOS va=0x60006fff PAR=0x10466db80 expect=mapped
SWEET GPU: buffers ATOS va=0x60007000 PAR=0x10466eb80 expect=mapped
SWEET GPU: buffers ATOS va=0x60007fff PAR=0x10466eb80 expect=mapped
SWEET GPU: buffers ATOS va=0x60008000 PAR=0x10466fb80 expect=mapped
SWEET GPU: buffers ATOS va=0x60008fff PAR=0x10466fb80 expect=mapped
SWEET GPU: buffers ATOS va=0x60009000 PAR=0x104670b80 expect=mapped
SWEET GPU: buffers ATOS va=0x60009fff PAR=0x104670b80 expect=mapped
SWEET GPU: buffers ATOS va=0x6000a000 PAR=0x104671b80 expect=mapped
SWEET GPU: buffers ATOS va=0x6000afff PAR=0x104671b80 expect=mapped
SWEET GPU: buffers ATOS va=0x6000b000 PAR=0x104672b80 expect=mapped
SWEET GPU: buffers ATOS va=0x6000bfff PAR=0x104672b80 expect=mapped
SWEET GPU: buffers ATOS va=0x6000c000 PAR=0x4000000104673b80 expect=mapped
SWEET GPU: buffers ATOS va=0x6000cfff PAR=0x104673b80 expect=mapped
SWEET GPU: buffers ATOS va=0x5ffff000 PAR=0x204673a03 expect=fault
SWEET GPU: buffers ATOS va=0x6000d000 PAR=0x304673a03 expect=fault
SWEET GPU: buffers ATOS va=0x20000000 PAR=0x104673a03 expect=fault
SWEET GPU: buffers wr +0x180c wrote=0x1 got=0x1
SWEET GPU: buffers wr +0x100c wrote=0x10000 got=0x10000
SWEET GPU: buffers wr +0xb010 wrote=0x1 got=0x1
SWEET GPU: buffers wr +0xb030 wrote=0x802020 got=0x802020
SWEET GPU: buffers wr +0xb020 wrote=0x104664000 got=0x104664000
SWEET GPU: buffers wr +0xb038 wrote=0x44 got=0x44
SWEET GPU: buffers wr +0xb03c wrote=0x0 got=0x0
SWEET GPU: buffers wr +0xb000 wrote=0x27 got=0x27
SWEET GPU: buffers wr +0xc0c wrote=0x3 got=0x3
SWEET GPU: buffers wr +0x80c wrote=0x80000005 got=0x80000005
SWEET GPU: buffers wr +0x80c wrote=0x0 got=0x0
SWEET GPU: buffers wr +0xb000 wrote=0x0 got=0x0
SWEET GPU: buffers wr +0xb020 wrote=0x0 got=0x0
SWEET GPU: buffers wr +0xb010 wrote=0x0 got=0x0
SWEET GPU: buffers wr +0xb030 wrote=0x0 got=0x0
SWEET GPU: buffers wr +0xb038 wrote=0x0 got=0x0
SWEET GPU: buffers wr +0xb03c wrote=0x0 got=0x0
SWEET GPU: buffers wr +0x180c wrote=0x0 got=0x0
SWEET GPU: buffers wr +0xc0c wrote=0x200ff got=0x3 MISMATCH
SWEET GPU: buffers wr +0x100c wrote=0x0 got=0x10000 MISMATCH
SWEET GPU: buffers final SMR/S2CR/SCTLR/CBAR=0x0/0x3/0x0/0x10000 FSR=0x0 sGFSR=0x0 result: ATOS verified; CM3 reset; mapping disabled
```

## 0094 full build and verified image — 2026-10-19

- Full [CI 39297388718](https://github.com/dipa-studio/ios-extra/actions/runs/39297388718)
  **passed** on `8104c7466c39d66b3169f1c420ac630312c8eb02`.
- Kernel SHA256 `3622b9ac5798f146a514d54f61c7ae191e8275f238d51f0c95233c724a1d0711`;
  SHA256SUMS check passed. `_sweet_gpu_probe` at 0xfffffe00074fa838 and
  `_sweet_rpmh_arc_set` at 0xfffffe00074f8548. Artifacts local/ignored in
  `ios-extra-work/out-0094` and `ci-0094`.
- CI GPU source SHA256 `3caa2f49b2c160a4d8b5b08621fe6caedc189a5fde334aaed40a1535101d3ad4`;
  staged firmware header `2c76898351726399ac212d29c3ca7670786ad00c77e5be28da3b847af0baedf2`;
  RPMh source `fc3669172ee14592cbee2f4312450e68ca9eac7870612d7d669fa2872bf404ca`.
  All three byte-identical to locally tested isolated files.
- Image `shim/out/shim-boot-0094-gmupreboot.img`, 17268736 bytes, SHA256
  `f1d9e4f9db5f8c468803135b591cf1b1dc9c1dc4d58512f91378746cbb2bf9c0`,
  mode 12, source/CI identity in `shim/out/manifest-0094.json`. Unpacked payload
  and command-line round-trip passed. **Not booted yet.**
- Checked fastboot first (serials not displayed/stored): zero devices; asked the
  user to enter fastboot. No reboot issued. Phone last tested on 0093, whose
  home screen is now confirmed; separate UI limitations are recorded in NOTES.
- Pruned reproducible 0092 kernel/buildtree/image/payload/unpack-check artifacts;
  preserved manifests and all phone logs, working 0093 and pending 0094 artifacts.

## Implementation — 0094 read-only GMU pre-boot inventory (local checks pass)

- `0094-sweet-gpu-gmu-preboot-inventory.patch`, `sweetgpu=12`, isolated baseline
  d3a6423 (validated 0093). 29 source-verified offsets, including DTCM version
  word +0xafe0, cached only after the buffer map is inactive and CM3 reset/idle
  is rechecked. No start writes or processor release.
- Normal and ASan/UBSan host suites pass: 29 offset/value checks, all 8 refusal
  terms with zero writes, missing-map/failed-buffer exclusions, lower-mode
  isolation and replay. Also tests the saved narrow CBAR diagnostic normalization
  against the exact dirty input observed in 0093. Arm64 compile: 0 of 1 failed.
- Full CI and phone result pending; source/build checks do not prove these new
  registers are readable on the phone. Design: GPU_CX_EXPERIMENT.

## Phone result — 0093 GMU buffers and ATOS, 2026-10-19 17:43 UTC

- Checked `fastboot devices` first (serial redacted): exactly one device already
  in fastboot. Announced and ran the authorized pending test. The helper rechecked
  before the single temporary boot; no flash or reboot command was issued.
- Boot issued 17:43:38 UTC; send 0.418s, boot 0.138s, total 0.564s; ping succeeds.
  `shim/out/shim-boot-0093-gmubuffers.img`, SHA256
  `dd4f6de48318e94e0dee5933467a998ec9ec6c90f352f9e050168b3202304f7a`,
  mode 11; CI 39293204273, built source ab7a61d (implementation c053da3).
- Capture: 452 UDP packets, 187544 decoded bytes. Local/ignored files:
  `ios-extra-work/logs/phone-0093-gmubuffers.{pcap,txt}` and
  `phone-0093-gmubuffers-fastboot.txt`. Initial report 0 is partial; all 29 ATOS
  results and all 20 write/readbacks below are from cached report 1. No panic
  marker observed. **The user confirmed the home screen.**
  Separately reports missing wallpaper and some white Settings/widgets, compared
  with another image made from ios-sweet patches; comparator identity and cause
  are unverified. User requested continuing GPU bring-up.
- **Measured:** allocation PA 0x104664000, 64 KiB; dummy/debug/log/HFI IOVAs
  0x60000000/0x60001000/0x60005000/0x60009000. All 26 mapped-page endpoints
  translate to the expected 13 physical pages; adjacent/unrelated addresses fault.
  `stage=3 checks=29/29 passed=29 inactive=1 restored=0`. FSR=0, sGFSR=0.
  Final SMR/S2CR/SCTLR/CBAR=0/3/0/0x10000: no active mapping, the known two inert
  restore differences remain. Firmware 8192/8192 words, bad=0; CM3 reset=1.
  CX complete/rolled back; clock stage=8 restored=1. RSC init still has the same
  nine constrained readbacks and successful stop status 0x01010006.
- **Diagnostic limitation measured:** the saved incoming CBAR value promotes to
  `0xfffffe8f00000000` in one `buffers wr` line, although its low 32 bits are 0.
  This is the earlier dirty-upper-bit anomaly now on a *saved expected value*;
  the 0093 explicit AND only normalizes the readback. This is a 32-bit MMIO store
  (low word 0), not a 64-bit write of that displayed value. Preserve the raw line;
  normalize the diagnostic's narrow expected value before comparing/logging in the
  next patch. No change to the known final CBAR=0x10000 observation.
- **Gate passed:** SMMU ATOS verifies the full buffer map. This still does not prove
  GMU-master traffic through stream 5; CM3/GX have never run. Next is the separate
  read-only pre-boot register inventory, before any GMU release.

```text
SWEET GPU: buffers pa=0x104664000 bytes=0x10000 stage=3 checks=29/29 passed=29 inactive=1 restored=0
SWEET GPU: buffers IOVA dummy/debug/log/HFI=0x60000000/0x60001000/0x60005000/0x60009000 sizes=4096/16384/16384/16384 HFI-size=120
SWEET GPU: buffers ATOS va=0x60000000 PAR=0x4000000104667b80 expect=mapped
SWEET GPU: buffers ATOS va=0x60000fff PAR=0x104667b80 expect=mapped
SWEET GPU: buffers ATOS va=0x60001000 PAR=0x104668b80 expect=mapped
SWEET GPU: buffers ATOS va=0x60001fff PAR=0x104668b80 expect=mapped
SWEET GPU: buffers ATOS va=0x60002000 PAR=0x104669b80 expect=mapped
SWEET GPU: buffers ATOS va=0x60002fff PAR=0x104669b80 expect=mapped
SWEET GPU: buffers ATOS va=0x60003000 PAR=0x10466ab80 expect=mapped
SWEET GPU: buffers ATOS va=0x60003fff PAR=0x10466ab80 expect=mapped
SWEET GPU: buffers ATOS va=0x60004000 PAR=0x10466bb80 expect=mapped
SWEET GPU: buffers ATOS va=0x60004fff PAR=0x10466bb80 expect=mapped
SWEET GPU: buffers ATOS va=0x60005000 PAR=0x10466cb80 expect=mapped
SWEET GPU: buffers ATOS va=0x60005fff PAR=0x10466cb80 expect=mapped
SWEET GPU: buffers ATOS va=0x60006000 PAR=0x400000010466db80 expect=mapped
SWEET GPU: buffers ATOS va=0x60006fff PAR=0x10466db80 expect=mapped
SWEET GPU: buffers ATOS va=0x60007000 PAR=0x10466eb80 expect=mapped
SWEET GPU: buffers ATOS va=0x60007fff PAR=0x10466eb80 expect=mapped
SWEET GPU: buffers ATOS va=0x60008000 PAR=0x10466fb80 expect=mapped
SWEET GPU: buffers ATOS va=0x60008fff PAR=0x10466fb80 expect=mapped
SWEET GPU: buffers ATOS va=0x60009000 PAR=0x104670b80 expect=mapped
SWEET GPU: buffers ATOS va=0x60009fff PAR=0x104670b80 expect=mapped
SWEET GPU: buffers ATOS va=0x6000a000 PAR=0x104671b80 expect=mapped
SWEET GPU: buffers ATOS va=0x6000afff PAR=0x104671b80 expect=mapped
SWEET GPU: buffers ATOS va=0x6000b000 PAR=0x104672b80 expect=mapped
SWEET GPU: buffers ATOS va=0x6000bfff PAR=0x104672b80 expect=mapped
SWEET GPU: buffers ATOS va=0x6000c000 PAR=0x4000000104673b80 expect=mapped
SWEET GPU: buffers ATOS va=0x6000cfff PAR=0x104673b80 expect=mapped
SWEET GPU: buffers ATOS va=0x5ffff000 PAR=0x204673a03 expect=fault
SWEET GPU: buffers ATOS va=0x6000d000 PAR=0x304673a03 expect=fault
SWEET GPU: buffers ATOS va=0x20000000 PAR=0x104673a03 expect=fault
SWEET GPU: buffers wr +0x180c wrote=0x1 got=0x1
SWEET GPU: buffers wr +0x100c wrote=0x10000 got=0x10000
SWEET GPU: buffers wr +0xb010 wrote=0x1 got=0x1
SWEET GPU: buffers wr +0xb030 wrote=0x802020 got=0x802020
SWEET GPU: buffers wr +0xb020 wrote=0x104664000 got=0x104664000
SWEET GPU: buffers wr +0xb038 wrote=0x44 got=0x44
SWEET GPU: buffers wr +0xb03c wrote=0x0 got=0x0
SWEET GPU: buffers wr +0xb000 wrote=0x27 got=0x27
SWEET GPU: buffers wr +0xc0c wrote=0x3 got=0x3
SWEET GPU: buffers wr +0x80c wrote=0x80000005 got=0x80000005
SWEET GPU: buffers wr +0x80c wrote=0x0 got=0x0
SWEET GPU: buffers wr +0xb000 wrote=0x0 got=0x0
SWEET GPU: buffers wr +0xb020 wrote=0x0 got=0x0
SWEET GPU: buffers wr +0xb010 wrote=0x0 got=0x0
SWEET GPU: buffers wr +0xb030 wrote=0x0 got=0x0
SWEET GPU: buffers wr +0xb038 wrote=0x0 got=0x0
SWEET GPU: buffers wr +0xb03c wrote=0x0 got=0x0
SWEET GPU: buffers wr +0x180c wrote=0x0 got=0x0
SWEET GPU: buffers wr +0xc0c wrote=0x200ff got=0x3 MISMATCH
SWEET GPU: buffers wr +0x100c wrote=0xfffffe8f00000000 got=0x10000 MISMATCH
SWEET GPU: buffers final SMR/S2CR/SCTLR/CBAR=0x0/0x3/0x0/0x10000 FSR=0x0 sGFSR=0x0 result: ATOS verified; CM3 reset; mapping disabled
```

## 0093 full build and packaged image — 2026-10-19

- User confirmed the repo had been made private overnight and requested public
  visibility again. Restored it and verified `isPrivate=false` / `PUBLIC`.
- Full [CI 39293204273](https://github.com/dipa-studio/ios-extra/actions/runs/39293204273)
  **passed** on `ab7a61da02cb91b0f87cf1a372939fabf73e3a59` (implementation c053da3,
  unchanged patch). This is full build/link evidence, not a phone result.
- Kernel `ios-extra-work/out-0093/kernel.development.sweet`, SHA256
  `1baf48029953c7d45b4ff50f3ecec5e0ff21e6bea8bc0525ef2cb6bc435243f5`;
  `sha256sum -c SHA256SUMS` passed. Symbols `_sweet_gpu_probe` at
  `0xfffffe00074fa838`, `_sweet_rpmh_arc_set` at `0xfffffe00074f8548`.
- CI artifact `ios-extra-work/ci-0093/buildtree.tgz`: GPU source SHA256
  `d824360e16362eff9a174e603acf1399e45512186b6d45ba42d425d0e5e7a0a1`,
  firmware header SHA256 `2c76898351726399ac212d29c3ca7670786ad00c77e5be28da3b847af0baedf2`,
  RPMh source SHA256 `fc3669172ee14592cbee2f4312450e68ca9eac7870612d7d669fa2872bf404ca`;
  all three byte-identical to locally tested isolated files.
- Packaged `shim/out/shim-boot-0093-gmubuffers.img` (17268736 bytes), SHA256
  `dd4f6de48318e94e0dee5933467a998ec9ec6c90f352f9e050168b3202304f7a`,
  `sweetgpu=11`, existing UFS-root boot arguments. Manifest
  `shim/out/manifest-0093.json`; unpacked ramdisk equals the generated payload,
  boot arguments round-trip exactly. Artifacts are local/ignored.
- **Not booted yet.** Asked for a new user-controlled fastboot before the single
  temporary test. The phone remains on 0092; no flash or reboot was issued.

## Implementation — 0093 GMU buffers (local checks pass; CI skipped)

- Source commit `c053da3cfae8a4fe053499fee7ad01bb68b61cfd`, patch
  `0093-sweet-gpu-gmu-buffers.patch`, mode 11. Design and preconditions in
  `GPU_CX_EXPERIMENT.md`. Isolated source baseline `60d4b0e` is validated 0092;
  its working diff matches the patch byte-for-byte.
- Local arm64 object compile: 0 of 1 files failed. All four Python test suites
  pass normally and with ASan/UBSan. GPU harness checks complete HFI contents at
  cache clean, 29 translations/faults, 38 precondition refusals issuing zero SMMU
  writes, readback failures, TLB/ATOS timeout bounds, incorrect translation/fault,
  rollback and replay. These are host results, not phone observations.
- [CI 39290944708](https://github.com/dipa-studio/ios-extra/actions/runs/39290944708)
  **skipped without building**: GitHub reports `isPrivate=true`; `.github/workflows/xnu.yml`
  builds only public repositories. Prior public status in the docs does not match
  the live setting. User clarification requested; visibility and the guard have
  not been changed. No 0093 kernel/image or phone result exists.

## Phone result — 0092 RSC/PDC diagnostics, 2026-10-19 16:55 UTC

- Temporary boot only, issued 16:55:16 UTC after the user confirmed fastboot;
  exactly one device, send 0.421s, boot 0.136s, total 0.563s. Image
  `shim/out/shim-boot-0092-rpmhinit.img`, SHA256
  `6fe97291353d16ac2edae5ee679599cf52c7e4e62fd1cb4ddf75408658a1f24c`,
  `sweetgpu=10`; source `a5bd9a2d61d445b1793f9c44d6e152230df26bd2`,
  green CI [39171199100](https://github.com/dipa-studio/ios-extra/actions/runs/39171199100).
- Ping succeeded. Capture: 450 UDP packets, 178296 decoded bytes; files outside
  Git at `ios-extra-work/logs/phone-0092-rpmhinit.{pcap,txt}` and
  `phone-0092-rpmhinit-fastboot.txt`. Initial live report 0 was partial; the first
  complete cached report is **report 1**, copied below. Later cached reports are
  not independent measurements. No panic marker in the decoded capture.
- **The user confirmed the home screen.**
- **Measured:** pre-write table differs in 34/48 entries; RSC/PDC sequencer
  memory and PDC enable/TCS entries are back to zero, including registers that
  accepted 0091 writes. Thus the 0091 configuration did not persist through this
  user-controlled return to fastboot and temporary boot. This does not identify
  which reset/power transition cleared it. SMMU S2CR3/CBAR3 and GMU RCG also start
  at their ABL defaults on this boot.
- **Measured:** 48 writes, 9 readback mismatches, successful stop handshake
  `RSC_STATUS0=0x01010006`. Three hidden RSCC addresses retain `0x82204514`,
  `0x82204510`, `0x82204520`; all six PDC MSGID differences are exactly bit 3
  (`0x10108 -> 0x10100`). Interpretation and limits: `GPU_GMU_BOOT.md`.
- Other raw checks: firmware 8192/8192 words verified, bad=0; CM3 reset=1,
  busy/init=0, CFG=0x52; CX complete and rolled back, clocks stage=8 restored=1.
  ATOS TTBR=0x104664000, data PA=0x104667000, PTE=0x40000104667f43;
  PARs for 0x60000000/0x60000fff/0x60001000/0x20000000 are respectively
  `0x4000000104667b80`, `0x104667b80`, `0x304667a03`, `0x104667a03`;
  passed=4, FSR=0x400, sGFSR=0. Final SMR/S2CR/SCTLR/CBAR = 0/3/0/0x10000
  (the known inert restore limitation). No GMU or GX execution.

Raw RSC/PDC portion of the first complete cached report (all 48 pre-write
values can be reconstructed: the 34 differing entries below plus the other 14
entries equal to the init table in patch 0091):

```text
SWEET GPU: RPMH init writes=48/48 bad=9 stop-handshake=1 RSC_STATUS0=0x01010006
SWEET GPU: RPMH init first bad region=0 off=+0x23034 wrote=0x00000000 got=0x82204514
SWEET GPU: RPMH init bad region=0 off=+0x23034 wrote=0x00000000 got=0x82204514
SWEET GPU: RPMH init bad region=0 off=+0x2303c wrote=0x00000000 got=0x82204510
SWEET GPU: RPMH init bad region=0 off=+0x23044 wrote=0x00000000 got=0x82204520
SWEET GPU: RPMH init bad region=1 off=+0x55d4 wrote=0x00010108 got=0x00010100
SWEET GPU: RPMH init bad region=1 off=+0x55e4 wrote=0x00010108 got=0x00010100
SWEET GPU: RPMH init bad region=1 off=+0x55f4 wrote=0x00010108 got=0x00010100
SWEET GPU: RPMH init bad region=1 off=+0x5764 wrote=0x00010108 got=0x00010100
SWEET GPU: RPMH init bad region=1 off=+0x5774 wrote=0x00010108 got=0x00010100
SWEET GPU: RPMH init bad region=1 off=+0x5784 wrote=0x00010108 got=0x00010100
SWEET GPU: RPMH init result: some writes did not read back
SWEET GPU: RPMH table pre-write region=0 off=+0x23010 found=0x00000000 mainline=0x01000000
SWEET GPU: RPMH table pre-write region=0 off=+0x23034 found=0x82204514 mainline=0x00000000
SWEET GPU: RPMH table pre-write region=0 off=+0x2303c found=0x82204510 mainline=0x00000000
SWEET GPU: RPMH table pre-write region=0 off=+0x23048 found=0x00000000 mainline=0x80000000
SWEET GPU: RPMH table pre-write region=0 off=+0x23044 found=0x82204520 mainline=0x00000000
SWEET GPU: RPMH table pre-write region=0 off=+0x23600 found=0x00000000 mainline=0xa7a506a0
SWEET GPU: RPMH table pre-write region=0 off=+0x23604 found=0x00000000 mainline=0xa1e6a6e7
SWEET GPU: RPMH table pre-write region=0 off=+0x23608 found=0x00000000 mainline=0xa2e081e1
SWEET GPU: RPMH table pre-write region=0 off=+0x2360c found=0x00000000 mainline=0xe9a982e2
SWEET GPU: RPMH table pre-write region=0 off=+0x23610 found=0x00000000 mainline=0x0020e8a8
SWEET GPU: RPMH table pre-write region=2 off=+0x0 found=0x00000000 mainline=0xfebea1e1
SWEET GPU: RPMH table pre-write region=2 off=+0x4 found=0x00000000 mainline=0xa5a4a3a2
SWEET GPU: RPMH table pre-write region=2 off=+0x8 found=0x00000000 mainline=0x8382a6e0
SWEET GPU: RPMH table pre-write region=2 off=+0xc found=0x00000000 mainline=0xbce3e284
SWEET GPU: RPMH table pre-write region=2 off=+0x10 found=0x00000000 mainline=0x002081fc
SWEET GPU: RPMH table pre-write region=1 off=+0x55cc found=0x00000000 mainline=0x00000007
SWEET GPU: RPMH table pre-write region=1 off=+0x55d4 found=0x00000000 mainline=0x00010108
SWEET GPU: RPMH table pre-write region=1 off=+0x55d8 found=0x00000000 mainline=0x00030010
SWEET GPU: RPMH table pre-write region=1 off=+0x55dc found=0x00000000 mainline=0x00000001
SWEET GPU: RPMH table pre-write region=1 off=+0x55e4 found=0x00000000 mainline=0x00010108
SWEET GPU: RPMH table pre-write region=1 off=+0x55e8 found=0x00000000 mainline=0x00030000
SWEET GPU: RPMH table pre-write region=1 off=+0x55f4 found=0x00000000 mainline=0x00010108
SWEET GPU: RPMH table pre-write region=1 off=+0x55f8 found=0x00000000 mainline=0x00030090
SWEET GPU: RPMH table pre-write region=1 off=+0x575c found=0x00000000 mainline=0x00000007
SWEET GPU: RPMH table pre-write region=1 off=+0x5764 found=0x00000000 mainline=0x00010108
SWEET GPU: RPMH table pre-write region=1 off=+0x5768 found=0x00000000 mainline=0x00030010
SWEET GPU: RPMH table pre-write region=1 off=+0x576c found=0x00000000 mainline=0x00000002
SWEET GPU: RPMH table pre-write region=1 off=+0x5774 found=0x00000000 mainline=0x00010108
SWEET GPU: RPMH table pre-write region=1 off=+0x5778 found=0x00000000 mainline=0x00030000
SWEET GPU: RPMH table pre-write region=1 off=+0x577c found=0x00000000 mainline=0x00000002
SWEET GPU: RPMH table pre-write region=1 off=+0x5784 found=0x00000000 mainline=0x00010108
SWEET GPU: RPMH table pre-write region=1 off=+0x5788 found=0x00000000 mainline=0x00030090
SWEET GPU: RPMH table pre-write region=1 off=+0x578c found=0x00000000 mainline=0x00000003
SWEET GPU: RPMH table pre-write region=1 off=+0x4500 found=0x00000000 mainline=0x80000001
SWEET GPU: RPMH table pre-write: 34 of 48 entries differ from the mainline values
SWEET GPU: RSC RSC_STATUS0_DRV0 +0x23010 = 0x00000000
SWEET GPU: RSC PDC_SEQ_START_ADDR +0x23020 = 0x00004520
SWEET GPU: RSC PDC_MATCH_VALUE_LO +0x23024 = 0x00004510
SWEET GPU: RSC PDC_MATCH_VALUE_HI +0x23028 = 0x00004514
SWEET GPU: RSC PDC_SLAVE_ID_DRV0 +0x2302c = 0x00000001
SWEET GPU: RSC HIDDEN_TCS_CMD0_ADDR +0x23034 = 0x82204514
SWEET GPU: RSC HIDDEN_TCS_CMD0_DATA +0x23038 = 0x00000000
SWEET GPU: RSC OVERRIDE_START_ADDR +0x23400 = 0x00000000
SWEET GPU: RSC SEQ_BUSY_DRV0 +0x23404 = 0x00000000
SWEET GPU: RSC SEQ_MEM_0_DRV0 +0x23600 = 0x00000000
SWEET GPU: RSC TCS0_DRV0_STATUS +0x23d18 = 0x00000001
SWEET GPU: RSC TCS3_DRV0_STATUS +0x244f8 = 0x00000001
SWEET GPU: RSC GMU_RSCC_CONTROL_REQ +0x24c1c = 0x00000000
SWEET GPU: RSC GMU_RSCC_CONTROL_ACK +0x24c20 = 0x00000000
SWEET GPU: PDC GPU_ENABLE_PDC +0x4500 = 0x00000000
SWEET GPU: PDC GPU_SEQ_START_ADDR +0x4520 = 0x00000000
SWEET GPU: PDC GPU_TCS0_CONTROL +0x5500 = 0x00000000
SWEET GPU: PDC GPU_TCS1_CMD_ENABLE_BANK +0x55cc = 0x00000000
SWEET GPU: PDC GPU_TCS3_CMD_ENABLE_BANK +0x575c = 0x00000000
SWEET GPU: PDC GPU_TCS3_CMD0_ADDR +0x5768 = 0x00000000
SWEET GPU: PDC SEQ_MEM_0 = 0x00000000
SWEET GPU: PDC SEQ_MEM_1 = 0x00000000
SWEET GPU: PDC SEQ_MEM_2 = 0x00000000
SWEET GPU: PDC SEQ_MEM_3 = 0x00000000
SWEET GPU: PDC SEQ_MEM_4 = 0x00000000
```

## Latest phone result — 0090 RSC/PDC read-only inventory, 2026-10-18 21:58 UTC

- `shim/out/shim-boot-0090-rscpdc.img` (SHA256 `a30aef87…695787`, CI 39169517724,
  sweetgpu=9), fastboot success 0.566s. Logs outside Git: logs/phone-0090-*.
- **No faults: GMU-block RSCC registers and both PDC regions (0x0b290000, 0x0b490000)
  are readable.** RSCC already holds the mainline values PDC_SEQ_START_ADDR=0x4520,
  PDC_MATCH_LO/HI=0x4510/0x4514, PDC_SLAVE_ID_DRV0=1 (HIDDEN_TCS_CMD0_ADDR=
  0x82204514); everything else is zero: RSC_STATUS0 0, OVERRIDE 0, SEQ_BUSY 0,
  SEQ_MEM_0 0, TCS0/TCS3 status 1, RSCC REQ/ACK 0; PDC ENABLE_PDC, SEQ_START,
  TCS0/1/3 banks and SEQ_MEM_0..4 all 0. So ABL/firmware did part of the RSCC setup
  but the PDC/RSC sequencer programming is still missing.
- User did not report the home screen for this boot yet.

## Latest phone result — 0091 mainline RSC/PDC init, 2026-10-18 22:10 UTC

- `shim/out/shim-boot-0091-rpmhinit.img` (SHA256 `fde80dfb…b6a4`, CI 39170396365,
  sweetgpu=10), fastboot success 0.560s. Logs outside Git: logs/phone-0091-*.
  Home screen for 0090/0091 not yet reported by the user.
- **All 48 writes issued; 39 read back as written, 9 did not (bad=9). The RSC stop
  handshake completed** (`RSC_STATUS0_DRV0` = 0x01010006, bit 16 set within the
  10 ms bound), i.e. the RSC sequencer ran with the microcode written. First bad
  write: RSCC `HIDDEN_TCS_CMD0_ADDR` (+0x23034) wrote 0, reads back the pre-existing
  0x82204514, so that register appears hardware-owned/ignores writes. The other 8
  were not logged (only the first mismatch was kept) -> 0092 logs all of them.
- No fault; the PDC regions accepted at least some writes. Whether the RSC/PDC state
  persists across a reboot is unknown; 0092 reads the whole table first.

## Active implementation — 0092 RSC/PDC init diagnostics (not yet built/booted)

- `xnu/patches/0092-sweet-gpu-rpmh-init-diagnostics.patch`: same mode 10; logs every
  bad write (first 16) and reads the whole 48-entry init table before writing (prints
  entries that differ from the mainline values: shows persistence). Host tests (62
  cases) pass incl. ASan/UBSan; arm64 compile ok. Isolated baseline 00095cd (0091).

## Active implementation — 0091 mainline RSC/PDC init (built, phone-tested)

- `xnu/patches/0091-sweet-gpu-rpmh-init.patch`: `sweetgpu=10` performs mainline
  `a6xx_gmu_rpmh_init` for A618 with readback of every write, then the RSC stop
  handshake; leaves the configuration in place. Docs: `docs/GPU_CX_EXPERIMENT.md`.
  Host tests (61 cases) pass incl. ASan/UBSan; arm64 compile ok. Isolated baseline
  8bd13d2 (0090).

## Active implementation — 0090 RSC/PDC read-only inventory (built, phone-tested)

- `xnu/patches/0090-sweet-gpu-rsc-pdc-inventory.patch`: `sweetgpu=9` reads the GPU RSCC
  (gmu+0x23000), RSCC handshake and the two PDC regions before the real mainline
  `a6xx_gmu_rpmh_init` programming is attempted. Host tests (55 cases) pass incl.
  ASan/UBSan; arm64 compile ok. Isolated baseline f6b7900 (0089). Reference sources
  (mainline v6.12 a6xx_gmu.c/.xml, linux-firmware blobs) are external in `gpu-fw/`.
- Also known: mainline a6xx_gmu_start expects FW_INIT_RESULT 0xbabeface if the DTCM
  word at GMU+0xAFE0 (image offset 0x7fe0) is <= 0x20010004, else (&0x1ff)==0x100.

## Latest phone result — 0089 SMMU write transcript, 2026-10-18 21:44 UTC

- `shim/out/shim-boot-0089-smmuctx.img` (SHA256 `f45e1d25…a0ddd3`, CI 39168706195,
  sweetgpu=8); fastboot success 0.567s. Logs outside Git: logs/phone-0089-*.
  (Home screen for this boot not yet confirmed.) ATOS results identical to 0088.
- Transcript (write -> readback): CBA2R3<-1 ok; CBAR3<-0x10000 low bits ok; CB3
  TCR2/TCR/TTBR0/MAIR/SCTLR(0x27) all read back exactly; S2CR3<-3 ok; SMR3<-
  0x80000005 ok (valid bit stuck); restore: SMR3<-0 ok; **S2CR3<-0x200ff and <-0x20000
  both refused (stays 3); CBAR3<-0 and <-0x20000 both refused (stays 0x10000)**;
  CB3 registers (SCTLR/TTBR0/TCR/TCR2/MAIR) all clear again; CBA2R3<-0 accepted.
- Pattern: every refused write has TYPE field value 0 (CBAR) or 2 (S2CR): only
  translate/bypass-type S2CR and stage-1/nested-type CBAR are accepted. Inference,
  not proven.
- **Anomaly:** several 32-bit readbacks of GR0/GR1 registers (SMR/S2CR/CBAR/CBA2R,
  not the CB registers) came back with 0xfffffe3f in bits 63:32 of the 64-bit
  variable although the instruction was `ldr w` (verified in the arm64 object): a
  hardware load cannot do that, so these register pages are probably trapped and
  emulated by the hypervisor with sloppy upper bits. Treat GR0/GR1 reads as 32-bit.
- Net: the SMMU is partly hypervisor-mediated; stream 5 -> CB3 programming works and
  an SMR write of 0 safely deactivates it. Left behind: S2CR3=3, CBAR3=0x10000 with
  SMR3 invalid and SCTLR=0 (inert).

## Active implementation — 0089 SMMU write transcript (built, phone-tested above)

- `xnu/patches/0089-sweet-gpu-smmu-write-transcript.patch`: same `sweetgpu=8`, now
  records each SMMU write with immediate readback and tries inert alternatives for
  S2CR3/CBAR3 if the ABL default is refused. Docs: `docs/GPU_CX_EXPERIMENT.md`.
  Host tests (49 cases) pass incl. ASan/UBSan; arm64 compile ok; isolated baseline
  8be623b (0088).

## Latest phone result — 0088 GMU SMMU context + ATOS, 2026-10-18 21:34 UTC

- `shim/out/shim-boot-0088-smmuctx.img` (SHA256 `943ed6d7…e7acd6`, CI 39167833774,
  sweetgpu=8); fastboot success 0.563s; **user confirmed home screen**. Logs outside
  Git: logs/phone-0088-{fastboot.txt,smmuctx.pcap,smmuctx.txt}.
- **The hardware SMMU accepted the page tables.** Table block PA 0x104660000
  (TTBR0 = that), L3[0] = 0x40000104663f43. ATOS (CB3 ATS1PR): 0x60000000 -> PAR
  0x4000000104663b80 and 0x60000fff -> 0x104663b80 (PA 0x104663000 = block+0x3000,
  F=0); 0x60001000 -> PAR 0x304663a03 and 0x20000000 -> 0x104663a03 (F=1, fault).
  4/4 as expected. Caveat: the first PAR has a non-zero high word the second lacks
  for the same page (attr bits stale/unreliable?); FSR after the test = 0x400
  (bit 10, meaning not decoded); sGFSR 0.
- **Restore did NOT fully take:** final SMR3=0x0, SCTLR=0x0 as intended, but
  **S2CR3=0x00000003 (my programmed value, ABL default was 0x000200ff) and
  CBAR3=0x00010000 (programmed; default 0)**; restored=0 was reported, although the
  result line text said "restored" (message bug). State is harmless: SMR3 invalid
  (group inactive) and SCTLR=0. Unknown whether those two writes were rejected by the
  hardware (e.g. CBAR TYPE 0 = stage-2 context while IDR0.S2TS=0; S2CR CBNDX 0xff
  invalid for 5 CBs) or something else; and whether SMR3's valid write ever stuck.
- Home-screen-confirmed, so nothing is broken. **Next (0089):** transcript every SMMU
  write with immediate readback and try alternative "disabled" encodings, to learn
  which values the hardware accepts, before building GMU mappings on top.

## Active implementation — 0088 GMU SMMU context + ATOS check (built, phone-tested above)

- `xnu/patches/0088-sweet-gpu-smmu-gmu-context.patch`: `sweetgpu=8` programs stream 5
  into CB3 with a 4 KiB-granule table (IOVA 0x60000000 -> one page), verifies via
  ATOS, restores. Details: `docs/GPU_CX_EXPERIMENT.md`. 0087 home screen was
  confirmed by the user. Host tests (47 cases) pass incl. ASan/UBSan; arm64 compile ok.
  Isolated baseline bae8544 (0087).

## Latest phone result — 0087 GPU SMMU inventory, 2026-10-18 21:15 UTC

- `shim/out/shim-boot-0087-smmu.img` (SHA256 `142dca90…1f50df8`, CI 39165446245,
  sweetgpu=7), fastboot success 0.598s, user put the phone in fastboot. Logs
  outside Git: logs/phone-0087-{fastboot.txt,smmu.pcap,smmu.txt}.
- **No bus fault; the kgsl SMMU (0x05040000) is Linux-visible and readable.** Raw
  values (decode below follows the ARM SMMUv2 manual from memory, not verified):
  sCR0 0x00200626, sCR1/sCR2/sACR 0, IDR0 0x48016605, IDR1 0x20008005, IDR2
  0x00007511, IDR7 0, sGFSR/sGFSYNR0 0; SMR0-4 all 0x00000000 and S2CR0-4 all
  0x000200ff; CBAR0-3 0; CB0 SCTLR/TTBR0/TCR/FSR all 0; +0x6000 = 0x00000178.
- Reading: NUMSMRG=5, NUMCB=5, S2CR TYPE=2 (fault) on every group with no valid SMR,
  all context banks unconfigured: the SMMU is enabled (CLIENTPD=0) and faults every
  stream until we program it. IDR0 suggests stream matching, coherent table walk
  (CTTW) and ATOS support; IDR2 suggests 4/16/64 KiB granules, 48-bit UBS.
  sGFSR clean: nothing has faulted since boot.
- GMU, GMU firmware step and clock rollback identical to 0086. Home screen for this
  boot not yet confirmed.
- **Next:** program stream 5 (GMU) to a context bank with a tiny 4 KiB-granule page
  table and verify with the SMMU's own ATOS translate (no GMU run needed); mainline
  uses one GMU address space, IOVA 0x60000000 dummy page, HFI/log buffers at
  0x60001000+.

## Active implementation — 0087 SMMU read-only inventory (built, phone-tested above)

- `xnu/patches/0087-sweet-gpu-smmu-inventory.patch`: `sweetgpu=7` (= mode 6 + SMMU
  reads at 0x05040000). Docs in `docs/GPU_CX_EXPERIMENT.md`. 0086 was confirmed to
  reach the home screen by the user.
- Host tests (38 CX/GMU/SMMU cases) pass incl. ASan/UBSan; arm64 compile ok;
  isolated tree baseline 3afeabe (0086).

## Latest phone result — 0086 GMU firmware in TCM, 2026-10-18 20:45 UTC

- `shim/out/shim-boot-0086-gmufw.img` (SHA256 `a5804983…0db467`, CI 39164168730,
  commit = HEAD at build, sweetgpu=6), fastboot success 0.564s. CI-generated
  firmware header is byte-identical to the local one. Logs outside Git:
  logs/phone-0086-{fastboot.txt,gmufw.pcap,gmufw.txt}.
- **The 32 KiB GMU firmware (a630_gmu.bin) was written to GMU ITCM+DTCM and read back
  with 0 mismatches of 8192 words**; CM3_SYSRESET was 1 before, CM3 never released,
  clocks/CX/votes rolled back (stage 8). Kernel FNV-1a 0x51c28be8 matches the host
  file. First time GMU memory was written; it also shows the GMU TCM is real
  memory at GMU+0x3000..0xB000.
- Home screen for this boot not yet confirmed by the user.
- **Next (mainline order):** GENERAL_7 TCM retention, RSCC/PDC programming
  (a6xx_rpmh_start), then GMU-visible HFI/log memory (SMMU stream 4/5) before
  releasing CM3 reset.

## Active implementation — 0086 GMU firmware to TCM (built, phone-tested)

- Firmware: linux-firmware `a630_gmu.bin` (32 KiB legacy image; mainline uses it
  for A618). Staged by `xnu/patches/0086-stage-gpu-firmware.sh` (pinned commit +
  sha256), generated header not in git. Local copies in external `gpu-fw/`
  (also mainline a6xx_gmu.c/a6xx_hfi.c v6.12 for the next stages).
- `xnu/patches/0086-sweet-gpu-gmu-firmware-tcm.patch`: `sweetgpu=6` copies it to
  GMU ITCM/DTCM (byte +0x3000) and verifies by readback, only if CM3_SYSRESET==1.
  Host tests pass (32 CX/GMU cases, ASan/UBSan); arm64 compile ok.
- **Remaining GMU boot work (mainline order):** GENERAL_7 TCM retention,
  a6xx_rpmh_start (RSCC + PDC sequences at 0xb290000/0xb490000), HFI table +
  log memory visible to the GMU SMMU stream, CM3_BOOT_CONFIG/CFG(0x4052), release
  reset, wait FW_INIT_RESULT, GFX rail OOB, HFI start.

## Latest phone result — 0085 first GMU register reads, 2026-10-18 20:31 UTC

- `shim/out/shim-boot-0085-gmureg.img` (SHA256 `f2e43620…a1b14b`, CI 39162789741,
  sweetgpu=5), fastboot success 0.561s, phone was in fastboot at user's request.
  Logs outside Git: logs/phone-0085-{fastboot.txt,gmureg.pcap,gmureg.txt}.
- **No bus fault; the GMU register block answers.** All 6 reads completed, stage 8,
  clocks/gate/CX/votes rolled back, identical in every replayed report:
  CM3_SYSRESET +0x14000 = **0x00000001** (CM3 held in reset, as expected before
  firmware), CM3_FW_BUSY 0x0, CM3_FW_INIT_RESULT 0x0, CM3_CFG **0x00000052**,
  GENERAL_0 0x0, AO_HOST_IRQ_STATUS 0x0.
- GCC bus branches: memnoc 0x80000220 -> 0x00000221 (running) -> 0x80000220;
  ddrss-axi 0x80000000 -> 0x00000001 (running) -> 0x80000000.
  GMU clocks as in 0084 (cx-gmu 0x00004ff1 on).
- Meaning: CX domain + 200 MHz-config GMU clock + bus branches are sufficient for
  host MMIO to the GMU CSR block. Nothing written to the GMU. Meaning of CM3_CFG
  0x52 not decoded. Home screen not yet confirmed by the user for this boot.
- **Next:** GMU needs SMMU-mapped memory and firmware: map GPU SMMU (0x05040000),
  GMU stream 4/5 contexts, firmware blob location (a618_gmu.bin availability on the
  phone is unverified), then load ITCM/DTCM and release CM3 reset.

## Active implementation — 0085 first GMU register reads (built, phone-tested above)

- `xnu/patches/0085-sweet-gpu-gmu-regs.patch` (on top of 0084): `sweetgpu=5` adds
  GCC memnoc/ddrss-axi branches and reads 6 GMU CX registers; docs in
  `docs/GPU_CX_EXPERIMENT.md`. Host tests pass (incl. ASan/UBSan); arm64 compile ok.
  Isolated tree baseline 0a8eef9 (0084).
- 0084 revised was home-screen confirmed by the user. Phone currently in fastboot
  (user put it there) and idle.

## Latest phone result — 0084 revised GMU clock stage, 2026-10-18 20:11 UTC

- `shim/out/shim-boot-0084-gmuclk.img` (SHA256 `b7bd5903…d652e6`, CI 39161422925,
  sweetgpu=4), fastboot success 0.559s; user had the phone in fastboot.
  Logs outside Git: logs/phone-0084b-{fastboot.txt,gmuclk.pcap,gmuclk.txt}.
- **GMU clock came up at 200 MHz config and rolled back cleanly** (all 4 reports
  identical): gate 0x52004 0x01241d7b -> 0x01251d7b (bit16 set); RCG cmd
  0x80000000 / cfg 0x00000000 -> **0x00000602** (source 6, HID 2) with UPDATE
  cleared; cx-gmu CBCR 0x80004220 -> **0x00004ff1** (running, wake/sleep 0xF)
  then 0x80004ff0 after disable; ahb/cxo stayed 0x00000001 (untouched); CX
  collapse and votes released as in 0083. Stage 6, restored=1.
  Caveat: CLK_OFF clear shows the branch sees a running clock; the actual 200 MHz
  rate is not measured. The RCG is left at 0x602 (unused); gate restored.
- USB up, ping ok; only "panic" string is the DumpPanic exec. Home screen not yet
  confirmed by the user for this boot.
- **Next:** 0085 read-only GMU register access under CX+clock (map GMU base
  0x0506a000), starting with a known-safe register, then GMU memory/SMMU.

## 0084 first phone boot — precondition refused, nothing written (2026-10-18 19:59 UTC)

- `shim-boot-0084-gmuclk.img` (SHA e8dca213…c57d8, CI 39160714701, commit
  473ab51) booted via fastboot; **user confirmed home screen**. CX experiment
  repeated cleanly (0xf8222000 then 0x00222001). The GMU clock stage refused:
  my precondition wrongly required ahb/cxo off. Measured instead: GPLL0 mode
  0xd0100005, vote 0x1, gate 0x52004 0x01241d7b, RCG 0x80000000/0x0, CBCR
  ahb/cx-gmu/cxo = 0x00000001/0x80004220/0x00000001. No clock register written.
- Fix (0084 revised, not yet built): leave pre-enabled branches alone; own only
  cx-gmu. Tests updated.

## Active implementation — 0084 GMU clocks (revised after first boot; rebuild pending)

- `xnu/patches/0084-sweet-gpu-gmu-clocks.patch`: `sweetgpu=4` runs a GMU clock
  stage inside the 0083 CX window (GPLL0/2 gate, RCG 200 MHz, ahb/cx-gmu/cxo
  branches), then undoes it. Details: `docs/GPU_CX_EXPERIMENT.md`.
- 4 host tests pass (also ASan/UBSan); arm64 object compile 0/1 failed.
  Isolated tree baseline f10f32d (0083).
- **Next:** push, CI, package `shim-boot-0084-gmuclk.img`, boot once with user.

## Latest phone result — 0083 CX power experiment, 2026-10-18 19:47 UTC

- Temporary boot of `shim/out/shim-boot-0083-cx.img` (SHA256 `836062ec…abc451`,
  sweetgpu=3) after the user put the phone in fastboot; success in 0.560s.
  Logs outside Git: logs/phone-0083-{fastboot.txt,cx.pcap,cx.txt}.
- **CX GDSC powered on and rolled back cleanly.** Reports 0-3 (original + 3
  cached replays) all show: GDSCR before `0x00222001`; MX and CX LOW_SVS votes
  both returned 0 (hlvl index 2 each); after clearing SW_COLLAPSE GDSCR became
  **`0xf8222000`** on the first poll (PWR_ON plus the other status bits set)
  and still `0xf8222000` after a 1 ms hold; after SW_COLLAPSE it returned to
  `0x00222001` on the first poll; both releases returned 0.
  First measured successful ARC-vote + CX GDSC power-up on this phone.
- USB ECM up, ping ok, no kernel panic string (only the DumpPanic exec).
  The capture was short (~40 s): only one SpringBoard line; UI not confirmed
  from the log. Phone left running 0083 (temporary boot).
- **Next:** GMU clock bring-up (CX is now known good): GCC GPLL0 divided parent,
  RCG 0x1120, gate 0x52004 bit16, CX GMU branch 0x1098 bit0, with a held CX vote.

## Active implementation — 0083 CX power experiment (built; phone-tested above)

- `xnu/patches/0083-sweet-gpu-cx-experiment.patch`: new ARC vote path in
  sweet_rpmh.c and `sweetgpu=3` in sweet_gpu.c (MX/CX LOW_SVS votes, CX GDSC
  enable, PWR_ON check, full rollback). Details: `docs/GPU_CX_EXPERIMENT.md`.
- Host tests pass (4 tests, also ASan/UBSan); arm64 objects compile (0/2 failed).
  Isolated tree baseline for 0083 is local commit 843344a (0082).
- Implementation **1408d1c** pushed; CI **39159151996 PASSED**. Kernel SHA256
  `de3a8499286902ba07ddc697f9a8337b6746a6882b896fa8bcf97a2af50a8a14` (checksum
  file verified); `_sweet_rpmh_arc_set` and `_sweet_gpu_probe` linked; CI copies
  of sweet_gpu.c/sweet_rpmh.c match the isolated tree. Artifacts `out-0083/`,
  `ci-0083/` (external).
- Images (17,203,200 bytes, ADT identical to 0082): `shim/out/shim-boot-0083-cx.img`
  (sweetgpu=3) SHA256 `836062ec0a3882850ee5e95a42f4f2833395bde632a2a5761ed778932dabc451`,
  and `shim-boot-0083-arc.img` (sweetgpu=2 fallback). Manifest manifest-0083.json.
- **Next:** boot `shim-boot-0083-cx.img` once (first GPU hardware write), using the
  HANDOFF.md capture procedure with phone-0083 file names. Report the lines
  `SWEET GPU: CX experiment ...`. Another agent also uses the phone: coordinate.

## Latest phone result — 0082 ARC inventory, 2026-10-18 19:23 UTC

- Temporary boot of `shim/out/shim-boot-0082-arc.img` (SHA256
  `7fca248b6c8af736aee7982388cb55fedf9d4d825f279ea602007be9fe9cccba`),
  sweetgpu=2. Exactly one fastboot device; success in 0.562s. No flashing.
- USB ECM came up automatically (tools/phone-ecm-host.py); ping 3/3, avg 1.3ms.
  Reports 1, 2, 3 complete; ARC cached tables identical (analyzer passed).
- Raw command-DB levels (uint16, padding included; no checksum/voltage meaning
  claimed). All three resources: aux version 0x1000.
  - gfx.lvl addr 0x00030050, priority 0x40000/0: 0,16,64,128,192,256,0...
  - cx.lvl  addr 0x00030000, priority 0x1440010/0: 0,16,64,128,192,256,0...
  - mx.lvl  addr 0x00030010, priority 0x1440010/0: 0,16,192,320,384,0...
- Only "panic" string in the stream is the DumpPanic process exec; 19
  SpringBoard lines. UI state not separately confirmed by the user.
- Own tcpdump stopped. Logs outside Git: logs/phone-0082-{fastboot.txt,arc.pcap,
  arc.txt,inventory.json}. Phone is running 0082 (temporary boot).
- **Next:** design a bounded opt-in CX/GMU power experiment (ARC vote by table
  index through the shared apps-DRV path, MX parent first). See HANDOFF.md
  hardware notes. Confirm with the user before any hardware write.

**User is switching AI to conserve usage. Read [HANDOFF.md](HANDOFF.md) for
the complete continuation context, exact next phone-test commands and all
workspace/source references. 0082 is ready; awaiting fastboot confirmation.
No additional phone action was taken during handoff.**

## Active implementation — read-only ARC inventory 0082

- User said "mehet" after the complete inventory and external-driver audit.
  Added **0082-sweet-gpu-arc-inventory.patch**, modifying only sweet_gpu.c.
  New opt-in **sweetgpu=2** reads clocks plus gfx.lvl/cx.lvl/mx.lvl metadata
  and up to 16 raw uint16 levels per resource from the known firmware locator.
  Modes 0/1 keep their existing mapping behavior. No RPMh RSC/TCS maps,
  voltage helper calls, hardware writes or GPU/GMU/SMMU core mappings.
- Separate bounded parser validates locator/header, entry/auxiliary ranges,
  ARC slave/address type and payload size. Duplicate or malformed resources
  fail explicitly. Raw padding/version/priority/checksum values preserved;
  no checksum verification, corner selection or voltage interpretation.
  Snapshot uses the existing release/acquire publication and cached USB
  reports, including failures. Existing display RPMh helper is unchanged.
- All 3 unit tests pass: 14 clock/cache cases, **30 ARC cases + 512 seeded
  mutations**. Same harness passes ASan/UBSan. Real arm64 object compilation
  passes (0/1 failed), using logs/ci-0081.log and the isolated tree.
  Isolated XNU git baseline through 0081 is **d818e18**; current changes 0082.
- Implementation **6f76e4f15e0f52c65b37d8cf98e647900d5825b0** pushed. Full CI
  **39157726409 PASSED** in 5m02s. Kernel checksum verifies:
  `510f85c8df5a3bff369ab14db41ecc4d91547b28b897ca4c041b58e60aa1afa2`.
  CI GPU/RPMh/USB source and source-list files match local byte for byte;
  both probe/replay symbols linked. Artifacts external out-0082/, ci-0082/.
- Modes 0/1/2 packaged and unpack-verified, each 17,203,200 bytes, with ADT
  identical to validated 0081 and established UFS-root/6-CPU/USB arguments.
  **shim/out/shim-boot-0082-arc.img**, SHA256
  `7fca248b6c8af736aee7982388cb55fedf9d4d825f279ea602007be9fe9cccba`.
  Mode 0 SHA `0f2a1358d27816eebcf12c9257d12f48b8cd7396fe6c1ee9297e7e080d731087`;
  mode 1 SHA `6c8ce3df3842856bc37b1ea538645eeb5676094d05b7b7bb1d18b1658a1c1cab`.
  Manifest shim/out/manifest-0082.json, packaging log logs/boot-package-0082.txt.
- Further pinned-source audit: CX regulator declares MX parent; CX GDSC
  parent is VDD_CX_LEVEL. GMU 200 MHz selects GCC GPLL0 divided parent,
  selector 6/HID 2 at RCG 0x1120; shared gate GCC 0x52004 bit16. Linux
  consumer corner constants add offset1, but DB values are raw and requests
  carry table indices. Recorded in docs/GPU_POWER_SEQUENCE.md. No new writes.
- Details: `docs/GPU_ARC_INVENTORY.md`. Asked user for fastboot availability
  after preparing the verified image; phone remains on validated 0081.
  No 0082 phone experiment yet. Ignored decoder/analyzer prepared under
  research/ for phone-0082-arc capture and per-report ARC table validation.

## Active work — complete inventory and Metal compiler reference

- Patch **0081-sweet-gpu-inventory-replay.patch** is built and phone-tested.
  The user confirmed its first boot reached the home screen. A second boot
  captured all three complete cached GPU inventory reports. The phone is
  left running 0081; no images flashed and no GPU power writes performed.
- Caches the one initial, guarded read-only snapshot and prints it again
  from the existing USB log thread after ~5/15/30 seconds configured-loop
  time. Each report has numbered BEGIN/END markers; replays are explicitly
  marked cached. No new hardware reads, mappings, writes or power votes.
- Immutable snapshot is published release/acquire. No new thread or heap
  allocation. Failure outcomes are cached too. Disabled probing stays quiet.
- Local validation: all 3 unit tests pass (14 MMIO/cache cases in the probe
  harness); real arm64 object generation of GPU and USB C files passes
  (0/2 failed). New tests apply the full GPU patch chain before execution.
- Implementation commit **3fc1124684f2bcf1ac9eebb03f9d18fc5ba9d2e4** is
  pushed. Full CI **39154941656 PASSED** in 7m25s. Kernel checksum verifies;
  GPU/USB/UFS sources and source list match the local tree byte for byte.
  Both GPU probe/replay symbols are linked. Kernel SHA256
  `2f29b0bea5b143f61562417ca346a59896b2370f238a271bf9546de75aacf9c3`.
- Both 0081 images packaged and unpack-verified, each 17,203,200 bytes:
  `shim/out/shim-boot-0081-probe.img` SHA256
  `ad262ff3670fd79b537108b7a2e539d36d49730abb067cd90e514d223cbcc297`;
  `shim/out/shim-boot-0081-default.img` SHA256
  `209b236842959fe3cfd0f71cb3715c9f2ef1c5920dfe69de0e8643c8c075053a`.
  ADT identical to validated 0080; established UFS-root args, cpus=6,
  sweetusb=2, probe mode 1/0. Manifest `shim/out/manifest-0081.json`.
  External artifacts `out-0081/`, `ci-0081/`; logs `logs/ci-0081.log`,
  `logs/boot-package-0081.txt`. Details: `docs/GPU_REPORT_REPLAY.md`.
- 30-second QEMU early-boot check passed: `no_panic_observed`, 0 unknown
  glyphs. Same QEMU ADT, HFS ramdisk and single-CPU arguments as 0080;
  evidence `qemu-0081/boot-local/`. Does not exercise phone USB/GPU/replay.
- Phone results and exact boot/log evidence are recorded below.
- Power/firmware audit added in `docs/GPU_POWER_SEQUENCE.md`, pinned to
  Xiaomi `758bb7ef`: the A618 entry requests **a618_gmu.bin**, unlike the
  mainline SM7150 catalog's a630_gmu.bin. Exact phone firmware unverified.
  GMU startup needs mapped HFI/log buffers before reset release. Source DT
  enables the register-based HFI quirk and GMU streams 4/5. Existing RPMh
  client validates VRM only and its public helper accepts only ldoc11;
  ARC gfx.lvl/cx.lvl/mx.lvl need distinct metadata/table lookup and voting.
  Next independent implementation can expose read-only ARC metadata and
  bounded level tables before designing CX/GMU power writes.
- User suggested Asahi and the open-source NVIDIA Metal driver. Inspected
  NullMoth commit **637282334617d27bccf8aa2448497c0f19465dc8** and upstream
  metal2vulkan **720ef1ce9ae2a2068999a8675717418b9416283e** in separate external
  reference clones. Audit: `docs/GPU_EXTERNAL_DRIVERS.md`. NVIDIA's plugin
  uses the same MetalPluginName/ClassName and initWithAcceleratorPort path
  as our iOS RE. Its macOS MTLIOAccel contracts still need an iOS adaptation.
  Root license is PolyForm Noncommercial; translator licensing is distinct.
- Built upstream metal2vulkan 0.2 CLI (Rust 1.98.0, release, warnings-as-errors)
  in 3m36s. Ran AIR-bitcode compute copy and vertex/fragment translation:
  all **3 SPIR-V modules PASS** CLI verification and spirv-val Vulkan 1.2.
  Synthetic upstream-owned fixtures, vk12-floor reference profile, no phone
  shader execution. Workers bounded to 20s and 500 MiB address space; observed
  0.017s/0.010s, cumulative child RSS high-water 40,724 KiB.
  Rust toolchain isolated at `/home/dipa/.cache/ios-extra-rust/` (external
  drive lacks required symlinks); no shell PATH files changed. Targets,
  smoke artifacts and logs external under `metal2vulkan-target/`,
  `metal2vulkan-smoke/`, `logs/metal2vulkan-build.txt` and saved Cargo.lock.
  This identifies an existing AIR/metallib frontend; real iOS library
  coverage, an Objective-C plugin ABI and Adreno execution remain untested.

## Latest phone result — complete 0081 inventory, 2026-10-18

- Both boots use `shim/out/shim-boot-0081-probe.img`, SHA256
  `ad262ff3670fd79b537108b7a2e539d36d49730abb067cd90e514d223cbcc297`.
  Exactly one fastboot device checked each time; temporary boot only.
- First boot **18:56:07 UTC**, fastboot success in 0.569s; user confirmed
  home screen. Host interface watcher hit usb0 -> enp... rename during
  nmcli and stopped; manual network setup restored ping but missed all
  report windows. 164 packets, 43,128 decoded bytes, 0 capture drops.
  Captured framebuffer swaps, no kernel panic; fitcored/PosterBoard crashes
  present, cause unestablished.
- Added **tools/phone-ecm-host.py** to retry discovery/configuration by ECM
  MAC across rename failures. Manually checked on the live interface and
  successfully exercised automatically during the second boot.
- Second user-authorized boot **19:03:45 UTC**, fastboot success in 0.563s.
  USB ECM host setup succeeded automatically; ping 3/3, no loss, avg 0.780ms.
  Reports **1, 2, 3** have complete matching BEGIN/END markers, 4 GCC values,
  2 GDSCR values and 9 GPUCC clock values each; all cached tables identical.
  This is one original boot measurement replayed, not three samples.
- **CX/GX GDSCR both 0x00222001**: PWR_ON clear, SW_COLLAPSE set. GCC cfg-ahb
  0x00000001; memnoc 0x80000220; snoc-dvm 0x80000001; ddrss-axi 0x00000000.
  All 9 GPUCC branches have halt/off bit31 set. DDRSS software enable is
  clear too; no claim of an owned clock vote from its clear halt bit alone.
  Full raw table: `docs/GPU_REPORT_REPLAY.md`.
- Retry capture: **537 packets, 180,786 decoded bytes, 0 kernel capture
  drops**. SpringBoard/backboardd exec and 16 framebuffer swaps observed;
  no kernel panic marker or crash of those two processes in the capture.
  driverkitd/PosterBoard process crashes observed, cause unestablished.
  The separate explicit user GUI confirmation applies to the first 0081
  boot; second-boot UI evidence here is from the captured stream.
- Existing UDP logger preserved. Stopped only our own tcpdump after reports
  and UI activity; no capture processes left from these two tests.
  Logs outside Git in `ios-extra-work/logs/`: `phone-0081-fastboot.txt`,
  `phone-0081-probe.pcap/.txt`, `phone-0081-retry-fastboot.txt`,
  `phone-0081-retry-probe.pcap/.txt`, `phone-0081-retry-inventory.json`,
  `phone-0081-retry-decode.txt`.
- **Next hardware work:** expose validated read-only ARC command DB metadata
  and level tables for gfx.lvl/cx.lvl/mx.lvl, then design a bounded CX/GMU
  power hold using the source audit and these observed initial states.

## Previous phone result — probe 0080, 2026-10-18

- **Probe 0080 temporary boot PASSED; user confirmed the home screen.**
  Boot started at **18:27:49 UTC**, using
  `shim/out/shim-boot-0080-probe.img`, SHA256
  `7deeb1c9badd6cda5f3e5dcf4959f909680b1b1b1ecf4ee40d05e1651265b5d9`.
  Exactly one fastboot device was detected. `fastboot boot` returned success:
  send 0.420s, boot 0.136s, total 0.562s. No images were flashed.
- The probe completed, USB ECM came up on `enp0s20f0u3u1`, and ping to
  192.168.7.2 returned 3/3 packets, 0% loss, average 0.554ms.
- Logs show HFS root mount, launchd/SpringBoard/backboardd startup and
  framebuffer swaps. No kernel panic or SpringBoard/backboardd crash marker
  was observed in the captured stream. The user separately confirmed GUI
  arrival; this is not inferred merely from process startup.
- Captured GPUCC branches are OFF: CX GMU `0x80004220`, CXO `0x80000001`,
  CX GFX3D `0x80000000`, CX slave `0x80000000`, GX GFX3D `0x80004220`,
  GX CXO `0x80000001`, GX GMU `0x80000000`. The final probe line confirms
  GPU/GMU/SMMU were skipped and no hardware writes were performed.
- **Capture limitation:** live UDP starts partway through the inventory.
  GCC and CX/GX GDSCR raw values are missing; do not infer domain state from
  those absent lines. The precise early-stream loss mechanism is unverified.
- Existing UDP receiver was left running. Used a separate tcpdump capture,
  then stopped only our tcpdump process after the home-screen confirmation:
  621 packets captured, 0 dropped by tcpdump's kernel capture path. This does
  not establish that every UDP datagram was emitted/delivered by the phone.
- Local evidence, kept out of Git, under `ios-extra-work/logs/`:
  `phone-0080-fastboot.txt`, `phone-0080-probe.pcap`,
  `phone-0080-probe.txt` (200,037 bytes). Decoder in this checkout's ignored
  `research/decode-probe-pcap.py`. Other agents' checkout was not edited.
- **Follow-up at this point:** obtain the missing complete power/clock inventory
  (persistent console extraction or a delayed/repeated read-only report)
  before implementing controlled CX/GMU/GX initialization, firmware loading,
  SMMU mappings and the first command-processor memory write. The phone is
  left running this probe kernel at the home screen then. The missing
  inventory was subsequently recovered by 0081 as recorded above.

## Purpose and workspace

- Created 2026-10-18 at the user's request as a separate, initially private
  driver playground. Working experiments can later be ported to `ios-sweet`.
- Local checkout: `/home/dipa/ios-extra`.
- GitHub: https://github.com/dipa-studio/ios-extra.
- **Public with user approval:** the user explicitly said "yes public" on
  2026-10-18. Visibility was changed and verified (`isPrivate=false`).
- Full XNU CI run **39152959124**, source commit
  **ee248d8a46463567d415b0ce4fd83b127c062da3**, **PASSED** (build job 6m15s).
  URL: https://github.com/dipa-studio/ios-extra/actions/runs/39152959124.
- Original reference checkout: `/home/dipa/ios-sweet`; do not modify it as
  part of playground work.
- Imported tracked baseline: upstream `347e19018e3e4c0117635e9e444f73659b2ece53`
  (patch 0079, display power), local snapshot commit `919ebb5`.
- Original README and NOTES are preserved in `docs/UPSTREAM_README.md` and
  `docs/UPSTREAM_NOTES.md`. Historical instructions and status in those files
  are reference material; this file and `AGENTS.md` govern current work.

## Initial state

- Kernel patches 0001–0079, shim and tools imported; first experimental GPU
  probe is now patch **0080**. Full GPU driver work is the selected target.
- No ignored build trees, Apple files, device backups, root images or recovery
  images copied. Existing artifacts remain in the reference workspace and
  `/run/media/dipa/android/ios-sweet-work/`.
- The original project has real iOS 16.7.16 userland on XNU, HFS+ on UFS,
  CPU framebuffer rendering, Goodix touch, hardware buttons and USB ECM.
- README/handoff snapshots lag the patch series: 0070/0071 implement app
  navigation fixes; 0078 allows eight CPU cores; 0079 adds framebuffer
  fade-to-black for display-off. Neither the presence of a patch nor a local
  kernel artifact proves its latest phone test passed.
- The initial source/build work did not access the phone; the subsequent
  user-authorized temporary boot and result are recorded above.

## Builds and integration

- `.github/workflows/xnu.yml` retains the inherited build and staging process.
  Its build job runs only when repository visibility is public. The user
  approved publication; public builds are now enabled.
- GPU probe 0080 is implemented, locally cross-compiled, fully CI-linked and
  phone-tested through the home screen. GPU execution remains unimplemented.
- Verified initial push workflow run **39150033548**, head `8b1e4f2`:
  completed with conclusion **skipped**. No macOS build ran while private.
- Verified the imported baseline Git tree exactly matches upstream `347e190`
  (both tree IDs: `032c01bf3fe13ad075a2692611f73b3a200b402d`).
- Keep driver changes focused. Use patch numbers from 0080 here; reconcile
  upstream numbering when porting. Do not automatically merge back upstream.
- Source-level architecture review recorded in `docs/ARCHITECTURE.md`: boot,
  platform/CPU, framebuffer/IOSurface, touch/HID, RPMh/battery, UFS, USB,
  compatibility services and build tooling. The original checkout remains
  at `347e190` with a clean working tree as of setup verification.
- `tools/xnu-cc.py` now infers the runner path from compile logs; explicit
  `XNU_CI_DXB` override is supported. Regression tests cover both repositories.
- GPU research/plan recorded in `docs/GPU_PLAN.md`. Saved live DT identifies
  Adreno 618 `0x06010800`, GPU base `0x05000000`, GPU SMMU `0x05040000`,
  GMU `0x0506a000`, GPUCC `0x05090000`. These are declarations, not tested
  post-ABL register accessibility. Linux/Mesa references are linked in the plan.
- Shared-cache load commands show AppleMetalGLRenderer depends on Metal;
  AGXMetalA11 depends on Metal/IOGPU/IOSurface. The actual usable iOS driver
  integration boundary remains unproven; do not assume GLES bypasses Metal.
- User reminder: other agents work on ios-sweet. Keep edits, generated trees
  and builds isolated here; coordinate future shared-phone tests. No agents
  were spawned and no phone commands were run in this research session.
- **Probe implementation:** `0080-sweet-gpu-probe.patch` adds a read-only
  `sweetgpu=1` GCC/GPUCC inventory, default off. GPUCC mapping is conditional
  on config-AHB enable/halt/invalid checks. GPU/GMU/SMMU remain unmapped because
  no GMU power hold exists. No hardware writes or root-image changes.
- **Isolated tree:** `/run/media/dipa/android/ios-extra-work/buildtree`.
  XNU base `1b191cb58250d0705d8a51287127505aa4bc0789`, fresh pinned provider
  staging, all 79 imported project patches applied plus applicable blacktop
  patches; local baseline commit `788ab36d761b5564db9eaaee63003a7a7e6a5bae`.
  Headers copied from the reference build artifact; source reconstructed
  separately. Downloaded Xiaomi GPU sources pinned to `758bb7ef`.
- **Local results:** syntax and real arm64 Mach-O object compilation of
  `sweet_gpu.c` and its changed `sweet_ufs.c` caller both pass (0/2 failed).
  Objects in `ios-extra-work/objects/`. Imports checked; ARM barrier present.
  Host MMIO tests cover 11 cases; patch reverse-check passes.
- Full register provenance, commands and limitations: `docs/GPU_BRINGUP.md`.
- Probe implementation commit **cdb9295** pushed. Its private-repository CI
  run **39151552639** completed **skipped** as intended. Full kernel linkage
  was not verified at that point. The user subsequently approved publication
  and full kernel build 39152959124 subsequently passed.
- Copied the reference compile log into
  `ios-extra-work/logs/upstream-run28.log`; future local checks can use that
  isolated copy. Final syntax-check log: `ios-extra-work/logs/probe-0080-syntax.txt`.
- **Metal RE:** traced `MTLRegisterDevices` at `0x181b144c8` and
  `getMetalPluginClassForService` at `0x181a3c7c8`. Metal enumerates
  `IOAcceleratorES`, reads `MetalPluginName`/`MetalPluginClassName`, loads an
  Extensions bundle, checks `_MTLDevice` subclassing and invokes
  `initWithAcceleratorPort:`. This is a candidate custom device-plugin
  boundary, not a tested replacement driver. Details in `docs/GPU_API_RE.md`.
- Unit tests pass with ResourceWarning treated as an error after fixing the
  inherited compile-log reader's file lifetime. No phone/device commands run.
- **Full CI artifact verified:** kernel SHA256
  `bd5d3df40badc1bb83571b4a9155fb88fecbc169002133d15ff90a7184c1aad6`.
  `_sweet_gpu_probe` at `0xfffffe00074ee358`. CI copies of all three changed
  files match the isolated local source. Kernel/buildtree artifacts under
  `/run/media/dipa/android/ios-extra-work/{out-0080,ci-0080}/`; full CI log
  in `ios-extra-work/logs/ci-0080.log`.
- **Boot images built and payload-verified:**
  `shim/out/shim-boot-0080-default.img` (`sweetgpu=0`) and
  `shim/out/shim-boot-0080-probe.img` (`sweetgpu=1`), each 17,203,200 bytes.
  High RAM ADT, cpus=6, USB ECM enabled, 30 Hz CPU display. Exact arguments
  and hashes in `shim/out/manifest-0080.json` and `docs/GPU_BRINGUP.md`.
- `shim/out` is an ignored symlink to `ios-extra-work/shim-out`.
  Copied stock DTB and D22 product tree into this checkout's ignored asset
  directories; the other repo was not edited.
- **QEMU 30-second smoke check:** same CI kernel, single-core QEMU ADT and
  copied HFS test ramdisk. Result `no_panic_observed`, unknown_glyphs=0,
  snapshot_only=true; captured kernel/IOKit initialization and CPU/display/HID
  services. Does not establish userspace boot or GPU hardware functionality.
  Results: `ios-extra-work/qemu-0080/boot-local/`; launch log:
  `ios-extra-work/logs/qemu-0080-local.txt`.
- External filesystem cannot bind QMP Unix sockets: first QEMU launch failed
  before executing the guest. Use `/tmp/ios-extra-q0080-*` as QEMU's output
  directory and copy evidence back. Local output path is recorded in
  `ios-extra-work/qemu-0080/local-output-path.txt`.
- Additional Metal RE: `_MTLDevice initWithAcceleratorPort:` is abstract
  (`doesNotRecognizeSelector:`). Ordinary `_MTLDevice init` provides common
  setup; `MTLIOAccelDevice` adds IOAccel device/configuration/shared-memory
  contracts. Evidence and candidate custom-transport implications recorded
  in `docs/GPU_API_RE.md`.
- The phone test above supersedes the earlier pending-test state.
  iOS renderer selection,
  power-up, firmware, SMMU and submission remain future milestones.
  No GPU command execution or upstream integration yet.
# FP6 powered SMMU baseline 0168 (2026-10-23)

- Source commit `9eeb38e3657ba8bfd259c240155a97868b4db118`, CI run
  `39831380821` (success); kernel SHA-256
  `34436f1dd7469a83658ba5d4b1ab4f63cea44510374f4b3e5e26c1bac5b3ae24`.
  The workflow skipped hosted packaging because `FP6_STOCK_DTB_URL` is unset.
- Local header-v2 image:
  `/tmp/ios-extra-run-39831380821/package/fp6-smmu-powered-baseline-0168.img`,
  SHA-256 `b0ce427af518fd6e76a1cf69c5ea45b834ebde227221eb251993e3b331548b97`.
  It uses the CI ADT (no `/product` artwork; diagnostic image only), the
  previously verified Volcano DTB and minimal RAM disk. Round-trip checks
  passed. Args: `rd=md0 fp6usb=2 fp6smmu=2 fp6smmupower=1`; GMU firmware boot
  was omitted.
- One temporary fastboot boot succeeded; USB ECM answered ping. Decoded log:
  `/tmp/ios-extra-run-39831380821/logs/phone-0168-powered-smmu-baseline.txt`,
  SHA-256 `85a5ae74b441b77bb051d301ef0ba9e474a1b0f724be6afc6471a6c61e6d0ef7`.
- Powered pre-test state: IDR0 `0x4c017e18`, IDR1 `0x40000016`, stream match,
  24 groups, 22 context banks, 4 KiB granule, CB window `+0x20000`. All stream
  groups were invalid with `S2CR=0x00020000` (fault). CB0 was disabled
  (`SCTLR.M=0`) but not zero: CBAR `0`, CBA2R `0`, SCTLR `0x2ff5c314`, TCR
  `0x7d0e6f8c`, TCR2 `0x00038065`, TTBR0 `0x19b143770fcb6d7b`, TTBR1
  `0xdc20c8e1af8db9f4`, MAIR0 `0x079fae8a`, MAIR1 `0x8899bf1f`, FSR `0`.
  Therefore the earlier `0/22` scan before CX/SMMU power does not show the
  powered CB0 contents. Preserve these values; no CB0 write was made.
- CB2 software walk passed IOVA `0x60000000` -> PA `0x904623000`; `ATOSNS`
  means this was not a hardware ATOS transaction. This run did not boot GMU
  firmware. The differences between this pre-test snapshot and 0167's
  post-HFI CB0 values are cross-boot only; they do not identify when state
  changes. Next diagnostic should log CB0 after CB2 cleanup, before CM3
  release, and at the first GFX_ACC refusal in one GMU/HFI boot. The device is
  now running the temporary XNU image; no safe autonomous fastboot-return path
  is established. No DMA/GPU command/draw/Metal result.
  Source inspection finds no autonomous reset path: `SweetPlatformExpert`
  does not override `haltRestart()`, and generic XNU handling here does not
  request Qualcomm PSCI reset or select a bootloader/fastboot reason.
# FP6 guarded CB0 reinitialization and secure HFI allocation boundary 0170 (2026-10-23)

- Commit `54a96ca789ef424bfe2f265e480d76c7a4f206a8` passed CI `39842360411`;
  XNU build succeeded. CI image packaging was skipped because
  `FP6_STOCK_DTB_URL` is unset. Kernel SHA-256
  `036a0a3e5c7c98d74724266c7d16de4b2b67ed36f54f0b9979b187f4a0594d4e`.
- Packaged the CI kernel/ADT with the verified stock Volcano DTB and the actual
  workflow init (not a prior payload). Header-v2 unpack/round-trip passed.
  Image `/tmp/ios-extra-run-39842360411/package-correct/fp6-cb0-reinit-0170.img`,
  SHA-256 `678ae82e3565a403f33abfa0b1ba6ae4629325637e918da158e9d087a15f90a8`.
  The CI ADT lacks `/product` artwork, so this is a diagnostic image only.
- One temporary `fastboot boot` succeeded. User-mode ECM capture recorded 113
  UDP packets in
  `/tmp/ios-extra-run-39842360411/logs/phone-0170-cb0-reinit.txt` and `.udp`;
  both SHA-256 `8f4552a25b5c20f67db78e2620c3e9eaf851c07004b5e89d3197cccdeec50216`.
  Fastboot transcript is the sibling `-fastboot.txt`. No partition was written
  and no EDL command was used. The bounded path verified CM3 reset and retained
  context/clock votes. Phone remains in temporary XNU boot.
- Powered CB0 began disabled and unrouted with `CBAR=CBA2R=0`,
  `SCTLR=0x2ff54304` (`M=0`), `FSR=0`; this residual state differed from 0169.
  Patch 0170 reinitialized CB0 and verified TTBR1 context readback before
  enabling SID0 on group 1. Existing group 0 SID5->CB2 remained. This is the
  first successful SID0 context configuration on the phone, not proof of a
  GPU-master translation.
- Firmware reported `FW_INIT_RESULT=0x100`; `HFI_CTRL_STATUS=1`. Six HFI startup
  requests and bootstrap DDR vote were acknowledged. During HFI startup, XNU
  serviced GPU-access allocation events for kinds 2, 14, 15, four kind-1
  buffers, 3 and 4, plus GMU-only kind 16. The next request was kind 5, flags
  `0x1007`, size 3,670,016; the bounded handler refused it and reset CM3. No
  `START` ACK, GPU core boot, DMA, command write/readback, draw or Metal output.
- Source review against Fairphone module commit
  `54c948d9b30c2ba01835e64c36b68b80692554ac`: kind 5 is
  `HFI_MEMKIND_CSW_PRIV_SECURE`; `GFX_SECURE` routes allocation to
  `kgsl_allocate_secure()`, which uses secure allocation and `hyp_assign_table`
  to transfer pages from HLOS to `VMID_CP_PIXEL`. Normal pages are not a valid
  substitute. Gen8 source supports a one-ring setup when preemption is disabled;
  review whether a bounded no-preemption startup can avoid requesting kind 5.
  Do not clear the secure flag or ACK with ordinary memory.

# FP6 CB0 transition diagnostics 0169 (2026-10-23)

- Added read-only CB0/SID-group snapshots after CB2-test cleanup, just before
  CM3 release, and after GMU firmware init. `git apply --check` passes against
  the CI `39831380821` buildtree; `tools/xnu-cc.py` compiles
  `bsd/dev/sweet_gpu.c` with 0/1 failures. Commit
  `8ec6a73e7b2bdf920b52977909a625e81d3d954d` passed CI run `39835047101`;
  kernel SHA-256 `6c9a6cedc6998253c9425706e789d02ad88c50664f6f741675467c0d0e62c126`.
- Packaged header-v2 image:
  `/tmp/ios-extra-run-39835047101/package/fp6-cb0-stages-0169.img`, SHA-256
  `4c9ac2171e8603bb7d8b2bb8aa9cd7c1c622467c9e4b6bcfffb94edced84cf89`.
  The CI ADT lacks `/product` artwork; this diagnostic image is not for
  SpringBoard validation.
- One bounded `fastboot boot` reached USB ECM and the phone pinged. Capture:
  `/tmp/ios-extra-run-39835047101/logs/phone-0169-cb0-stages.txt` and raw
  `/tmp/ios-extra-run-39835047101/logs/phone-0169-cb0-stages.udp`, both SHA-256
  `a466761c1ca5c5f662e77c99473530482419386951163adad7392d821f51f097`; 99 UDP
  packets. The fastboot transcript is in the matching `-fastboot.txt` file.
  No EDL command, flash or partition write was issued. User returned the phone
  to fastboot after the bounded XNU run.
- In this same boot, powered baseline, post-CB2, pre-CM3, post-firmware and
  first-GFX_ACC refusal snapshots all show the same disabled CB0 values:
  CBAR/CBA2R=0, SCTLR `0x2ff54314` (`M=0`), TCR `0x710e6fcc`, TCR2
  `0x00030065`, TTBR0 `0x19b3d3770fc36d7b`, TTBR1 `0xdc20c4a9af8db9f4`, MAIR0
  `0x069faeaa`, MAIR1 `0x8c99bf1f`, FSR=0. The GMU did not change CB0. The
  contained SID5 software walk assigned group 0 to CB2; group 1 remained
  invalid/fault-routed (`SMR=0`, `S2CR=0x00020000`) for SID0. GMU firmware
  reached `FW_INIT_RESULT=0x100`; HFI reached `HFI_CTRL_STATUS=1`, ACKed six
  startup requests and acknowledged DDR bootstrap voting. The first GPU-global
  allocation then stopped at the all-registers-zero CB0 refusal before any
  CB0 write; CM3 reset was verified and votes/pages retained.
- Patch 0170 narrows takeover to this measured disabled/unrouted case: it
  requires zero CBAR/CBA2R, SCTLR.M clear, FSR clear, idle TLB, no valid live
  stream route to CB0, and an exactly empty/fault-routed candidate group. It
  configures CB0 while SID0 remains fault-routed, verifies context/TLBI state,
  and installs SID0 last. This is the first planned CB0 write and still needs
  CI and phone validation; the HFI/software models are not DMA evidence.
