# ios-extra — current state

## FP6 first Gen8 HFI command source milestone (2026-10-22)

- Patch 0159 adds the Linux Gen8 HFI `CORE_FW_START` queue request after HFI
  controller init. It uses the existing 17-queue hwsched table, writes a
  2-dword request with sequence 1, rings `HOST2GMU_INTR_SET`, waits up to one
  second for the message IRQ, invalidates the cached HFI buffer, and validates
  the returned ACK header, request header, and zero status. Cache ownership is
  returned to the GMU before the doorbell; the CPU does not touch the buffer
  while firmware owns it. An unexpected response fails closed and the existing
  bounded path resets CM3.
- `python3 tests/test_fp6_gmu_boot.py` and the same harness under
  `-fsanitize=address,undefined` pass, including a simulated ACK and reset
  failure handling. These are host-model results only. CI and phone validation
  for patch 0159 remain pending.
- Linux `adreno_gen8_hwsched_hfi.c` allocates/maps F2H `MEM_ALLOC` requests
  dynamically. The next response must first identify any request the GMU makes;
  XNU must not invent handles or addresses that are absent from the persistent
  domain/SMMU tables. No HFI message has yet been exchanged on the phone.

## FP6 ACV vote and GMU/HFI phone result (2026-10-22)

- Commit `548673a33b397ef80cdbc701cd503903ab63118a` (patch 0158) passed CI
  `39762347940`. The CI kernel SHA256 was verified before local packaging. Image
  `/tmp/ios-extra-run-39762347940/package/fp6-gmu-bootstrap-acv-width.img`,
  SHA256 `0c2e73788e98d3a0bbe768ee54e9f4989e3e88973cb2e82d7438ad76ae3f6c10`.
- One `fastboot boot` succeeded; USB capture yielded 92 packets. Decoded log
  `/tmp/ios-extra-run-39762347940/logs/phone-0158-gmu-bootstrap-acv-width.txt`,
  SHA256 `199a1032353ab16000e60d3424fc72edcc8d99e9941872be251fa66e56791526`;
  pcap SHA256 `50e7f70104ca136dfc74a27e3642c725c7b953cca30328a1dedc9108a42c025a`.
- Hardware accepted the SH0 and MC0 variable votes and fixed ACV vote
  (`addr=0x50068`, width 0). The bounded TCS acknowledged the DDR vote. CM3 was
  released; firmware reported `FW_INIT_RESULT=0x100`, then
  `HFI_CTRL_STATUS=1`. The probe stopped and verified CM3 reset while retaining
  SMMU/context and clock votes. This confirms GMU firmware startup and HFI
  controller initialization. It does not demonstrate HFI message exchange,
  GMU DMA, GPU execution, rendering, or Metal. Optional `GPU_INIT_CX_REGS`
  remains unavailable but nonfatal in this path.
- Next measured milestone: bounded HFI startup message and pre-mapped MEM_ALLOC
  handling with explicit cache ownership, followed by a small GPU memory
  write/readback before rendering or Metal integration.

## FP6 cmd-db ACV metadata diagnosis (2026-10-22)

- Patch 0157 commit `32e325fb8197eac394b91eb9e7f6b140d6a6b9fe` passed CI
  `39760355071`; kernel was locally packaged with verified ADT/Volcano DTB as
  `/tmp/ios-extra-run-39760355071/package/fp6-gmu-cmdb-diagnostic.img`, SHA256
  `bd3a24bce181fcc7c4510ba73a6157d126d15274bfaead9f82bfe8049d822476`.
- One temporary boot captured 95 UDP packets. Decoded log
  `/tmp/ios-extra-run-39760355071/logs/phone-0157-cmdb-diagnostic.txt`, SHA256
  `2eff12f71f275bc4d48dab5fe2d7491312535e0f940dede1fb72436ed76253f1`;
  pcap SHA256 `d6f144827081c75eaf3ce03d4f11e2b7c277c743e857a4847e4476de96c447b2`.
- The dump identifies ACV in BCM slave 5 at address `0x00050068`; aux record is
  valid (`unit=1`, `width=0`, `vcd=12`, length 8). The parser had rejected it
  because it required nonzero width for every BCM. Linux marks ACV `fixed=true`
  and does not use its width. Patch 0158 permits zero width only for fixed
  entries, retains the nonzero-width requirement for SH0/MC0, and updates the
  ASan/UBSan fixture to the observed ACV metadata. CI and phone results are
  recorded above; all three votes were accepted and HFI initialized.

## FP6 Linux cmd-db lookup phone retest (2026-10-22)

- Patch 0156 commit `8c8c00233ce086caf4ef840f02948d8e9520153c` passed CI
  `39758346968`; kernel SHA256
  `72a9a9d0166fd390caf96beeec39d4e08671f3285e18acadbbb58b0229cd5683`.
  The temporary image package used the verified ADT and Volcano DTB, header-v2
  round-trip passed, and SHA256 is
  `1cf437c943cb94edbaaa5e0a0f6e62709f57c2d61bab4f9e3a2e2065c55f97fa`.
- The `fastboot boot` USB capture has 92 packets. Log
  `/tmp/ios-extra-run-39758346968/logs/phone-0156-cmdb-linux-lookup.txt`, SHA256
  `b40b04abf1a055af6b0906434b68b1550f1978b2b6914edbd1f67fc9621a3e84`; pcap
  SHA256 `2d44cac32e7e86131ea4fea5ac735d1b4510278acc1866b6229bc838d237e0e4`.
- Mirroring Linux's ordered name search did not resolve ACV: the log still reports
  missing ACV metadata. CM3 remains held in reset and no TCS vote was issued.
  Candidate patch 0157 adds bounded read-only header summaries and ACV/A-name
  entry/aux diagnostics only when metadata lookup fails; it does not relax the
  guard. Its ASan/UBSan host test checks that missing ACV cannot send a vote.
  Patch 0157 is not built or phone-tested yet.

## FP6 BCM address-ID correction phone result (2026-10-22)

- Patch 0155 commit `8462f999359f501ec523daaf1852693e3f384db6` passed CI run
  `39755620038` (XNU build and FP6 boot job success; CI packaging skipped
  because its stock-DTB URL is unset). Kernel SHA256
  `72a9a9d0166fd390caf96beeec39d4e08671f3285e18acadbbb58b0229cd5683`.
  Locally packaged with the verified product ADT and stock Volcano DTB; header-v2
  round-trip passed. Image:
  `/tmp/ios-extra-run-39755620038/package/fp6-gmu-bcm-address-id.img`, SHA256
  `0d4ff5ab9ee7aef5a1139841bcf6a909ed20d0be7ac73c65b43cf7899bbbf24a`.
- One temporary `fastboot boot` was performed through the USB helper; no partition
  writes or `getvar`. Capture: 93 UDP packets, 19,248 decoded bytes. Log
  `/tmp/ios-extra-run-39755620038/logs/phone-0155-bcm-address-id.txt`, SHA256
  `6a7bb87ec85d75558f95e9b1e81e6ec5d75e13657054ce097c0ed47a56e7ca0e`; pcap
  SHA256 `d437f9b66424434075057c7951f4fa7a40967c6f57f2f1e9e78d3d99b72b2ea7`.
- New result: BCM ID 5 validation accepts SH0/MC0, but lookup stops at
  `bootstrap BCM metadata missing name=ACV`. CM3 remains reset; no vote was issued,
  so this boot did not execute GMU firmware/HFI or GPU work. Linux
  `cmd_db_get_header()` scans populated slave headers in order; the old parser
  searched only ID 5. Candidate patch 0156 now mirrors Linux lookup, tracks the
  selected header ID, requires SH0/MC0 to resolve as BCM ID 5, and validates
  address/header consistency and aux data. The ASan/UBSan fixture places ACV in
  the following ARC header and passes. Patch applies to CI buildtree 39755620038;
  CI and phone validation are pending.


## FP6 HFI cache-path phone retest (2026-10-22)

- Patch 0153 commit `e53c66ab499d75d2101b1736ffbb85a7642e64f8` passed CI run
  `39745254929` (build job 6m44s; FP6 boot job passed). Packaging was skipped
  by CI because `FP6_STOCK_DTB_URL` is unset. The CI kernel was packaged locally
  with the verified product ADT and Volcano DTB; package round-trip and SHA
  manifest checks passed. Temporary image:
  `/tmp/ios-extra-run-39745254929/package/fp6-gmu-hfi-cache-isolation.img`,
  SHA256 `cca41889433f9c1005ddf0aa79513f5be29f49a0bbb1b49808bc150de0d18c5e`.
- One authorized `fastboot boot` was run with `tools/gpu-phone-test.py`; no
  partition writes or `getvar` calls. The USB capture contains 411 packets and
  121,789 bytes. Pcap SHA256
  `440ad1cde70cb785db62a2f78b1d1bdb839a4a31593398d88883c9353dae367a`;
  decoded log SHA256
  `cd93331eea3af227a2808a44c2f6192130b6a106a928f79b6d3800c9d001ab23`.
  Both are under `/tmp/ios-extra-run-39745254929/logs/`.
- Source, build and phone evidence agree: the 0153 image boots through launchd
  without the earlier `phystokv_range` panic. GMU firmware reports
  `FW_INIT_RESULT=0x100`, `HFI_CTRL_STATUS=1`, then the bounded probe verifies
  CM3 reset and retains the context and clock votes. CX timer seeding is
  healthy (16 samples; XNU CNTVCT at 19.2 MHz). The optional
  `GPU_INIT_CX_REGS` SCM call is unavailable and is logged as nonfatal.
  `CB_FSR=0x400` remains the known FORMAT-only status. The SMMU SID stays
  disabled; the persistent firmware upload returned `0` (success). No HFI
  messages, GMU DMA, GPU commands, or rendering were exercised. Removing the
  WIMG rewrite is strongly supported as the panic fix, though the original
  panic had no stack trace, so causality is not formally proven.
- Patch 0154 implements the Linux-equivalent minimum DDR BCM vote before CM3
  release. It reads live cmd-db BCM addresses/aux data at `0x81c60000`, computes
  the peak-only 2,136,718 kB/s request from the stock FP6 DT, and uses one idle
  ACTIVE RPMh TCS. It waits for all command acknowledgments and keeps CM3 in
  reset if metadata, TCS state, or completion is uncertain. Fairphone Linux
  source (`9535e0f08` plus its Gen8.3 module) supports the encoding and startup
  order. The host harness passes with UBSan and the patch applies to the exact
  source from CI run `39745254929`. The first CI image and phone attempt are
  recorded below; the BCM slave ID was wrong, so no vote was written. This is
  an active bus-vote write, not read-only. After validating it once on phone,
  continue with HFI BW/PERF tables and MEM_ALLOC handling with
  explicit cache ownership transitions. GPU MMU/OOB, SQE/AQE submission,
  bounded GPU memory write, rendering/readback, and the A810-compatible
  IOKit/Metal path remain outstanding.

## FP6 patch 0154 first phone attempt (2026-10-22)

- CI `39750406760` passed for `0c5bd243dc26286b1283d5b00ca3daed50c890a2`.
  Kernel SHA256 `d9020fb23a17d7787fef17d0848a51910437da1bb2fb65a3ef07821963a25d78`.
  Local package used the verified FP6 ADT and stock DTB; header-v2 round-trip
  passed. Image `/tmp/ios-extra-run-39750406760/package/fp6-gmu-bootstrap-ddr-vote.img`,
  SHA256 `6093f7f39acac3cb034dc926b94655b100784511f4575b45facc10572d6a3647`.
- One `fastboot boot` was issued after finding exactly one fastboot device. The
  phone log photo shows `bootstrap BCM metadata missing name=SH0`, then
  `first boot stopped before CM3 release; DDR vote unavailable`. Therefore no
  BCM command was written and this boot did not start GMU firmware. The device
  continued booting and the user reports it is waiting for Apple HFS. USB ECM
  did not appear before timeout, so no pcap was produced; the fastboot transcript
  is `/tmp/ios-extra-run-39750406760/logs/phone-0154-bootstrap-ddr-vote-fastboot.txt`.
- Source review found the bug: cmd-db slave IDs are ARC=3, VRM=4, BCM=5. The
  first candidate incorrectly searched BCM names under ARC ID 3 (where CX/MX
  ARC records reside). Patch 0154 is being corrected to search ID 5, and the
  host fixture now identifies its records as BCM entries. The corrected patch
  passes the targeted ASan/UBSan host harness. The build and ID-5 phone retry
  are recorded in the following section. Its USB log lacks the earlier
  `metadata missing` line; source review found a separate stale address-ID=3
  check, so the code likely found metadata and silently rejected BCM addresses.
  Patch 0155 corrects the address check and test fixture; it is not built or
  phone-tested yet. No vote attempt has succeeded on hardware.

## FP6 patch 0154 cmd-db ID-5 retry (2026-10-22)

- Commit `4f68fcb011d5cbec92485f5b076a470140560f59` passed CI run
  `39752494051`; kernel SHA256 `1d67f88580dffa942cbc54e1b8b68c5d6f360de31dac6c16d8c3512b56eff9e8`.
  Packaged header-v2 image with USB ECM enabled:
  `/tmp/ios-extra-run-39752494051/package/fp6-gmu-bootstrap-ddr-vote-cmdb5.img`,
  SHA256 `fe97c9fadae1388605b37124550677f596201c3f51bdc151afd6e80d4f835494`.
- One temporary boot reached ping and produced a 96-packet USB log. Decoded
  text `/tmp/ios-extra-run-39752494051/logs/phone-0154b-bootstrap-ddr-vote.txt`
  (SHA256 `dc1eb8596dfaee7c70f0c8a40f056468c235fbf2b9f513361d10cd68aae2f602`),
  pcap SHA256 `c94751cca1fbba39e8129d11d3e3da7ae9ff5bb782498d522cd0a652f918b4d9`.
  SMMU walk, ARC floors, clocks, timer and firmware upload succeeded; optional
  SCM remained unavailable. Bootstrap then still reported missing SH0 metadata
  and stopped before CM3 release. No BCM write occurred.
- The log does not contain `bootstrap BCM metadata missing name=SH0`; it only
  contains the generic DDR-vote refusal. `fp6_gmu_bootstrap_bcm_vote()` still
  required `(addr >> 16) == 3` after looking up records. Since BCM addresses
  encode slave ID 5, and the host fixture also used `0x300xx`, this explains
  the silent refusal. Patch 0155 changes validation to BCM ID 5, reports any
  other ID, and uses `0x500xx` fixture addresses. It passes ASan/UBSan and
  applies after 0154 to the exact prior CI source. Build and phone retry remain.
  Handoff: `docs/FP6_GPU_CONTINUATION.md`.

## FP6 GMU first-boot attempt (2026-10-22)

- Repackaged CI kernel from run `39667763253` (commit `c79f49f`) with the
  verified product ADT and stock FP6 DTB. Temporary image:
  `/tmp/ios-extra-run-39667763253/package/gmu-first-boot/fp6-gmu-first-boot.img`,
  SHA256 `bfd28263fd42356b507e84d135a5581235e04b1183e52ebeafcafa919194d6b6`.
  Boot arguments enabled the opt-in SMMU, GMU firmware upload and bounded
  first-start paths (`fp6smmu=2 fp6smmupower=1 fp6gmuload=1 fp6gmuboot=1`).
- Phone reached launchd and logged the software walk passing for IOVA
  `0x60000000` -> PA `0x903627000`. It stopped before firmware upload:
  inherited GMU clock register `0x90d4` read `0x2001`, and the clock guard
  refused to proceed without checking whether CM3 was held in reset. No TCM
  upload, CM3 release, GMU DMA or GPU execution occurred. Full decoded log and
  pcap are `/tmp/ios-extra-run-39667763253/logs/phone-0140-gmu-first-boot.txt`
  and `.pcap` (SHA256 of decoded log `5b45571dd8ed645487722c56417e8d98b3b1e5d2ccf97637853834993e612097`).
- Patch `0147-fp6-gmu-inherited-clock-reset-gate.patch` moves the safety check
  ahead of clock reconfiguration: if the GMU core clock is already running, it
  reads `CM3_SYSRESET` first and refuses any clock change unless reset is
  confirmed. If reset is held, the bounded clock/firmware path can continue.
  Patch applies to the CI source; `tests/test_gpu_probe.py` passes. Full CI and
  a retest are still required.

## FP6 GMU clock-fix temporary image packaged (2026-10-22)

- Packaged CI run `39674158109` / source `696a07851fb4e46fd4ab810bdc97e666c14013e2` with product ADT `4da4226e6b9ac393ff22b66a304d9172d6be2bfd6d558348a47379c51aab1d80` and Volcano DTB `8198534128258bfe7b05bbb5b227affc181aa49b376884c08eae8564fce124e3`.
- Image: `research/local-fp6/package-696a078/fp6-gmu-clockfix-boot.img`, SHA256 `9a074945623e65676cf0f1d509a848de63ebe7d54c055b67bf844c9d0da6e989`. Header-v2, embedded payload and DTB round-trip validation passed. Manifest records boot args and all input hashes.
- The phone console photo now shows this image's GMU clock path succeeded: inherited core clock `0x2001`, CM3 reset confirmed, MX ARC floor `0xc0` acknowledged at level 5/TCS0, GPLL0 600 MHz, PLL0 configured, and GMU350/HUB200 clocks enabled. Persistent upload checked 159 pages and returned success (`firmware upload=0`) with CM3 held in reset and SID disabled before the bounded probe.
- GMU firmware then returned `FW_INIT_RESULT=0x100`; `HFI_CTRL_STATUS=1`. The probe reasserted and verified CM3 reset and retained SID/context/clock votes. SMMU global IRQ INTID705 was disabled/pending=0 in the read-only inventory; CB FSR `0x400` is the previously identified FORMAT status, not an asserted translation fault. This proves firmware start and HFI controller initialization, not an HFI command exchange or GMU DMA.
- USB ECM capture `/tmp/fp6-gmu-clockfix-phone.pcap` (SHA256 `b496a1396a21f4be468cb096ad12646526a9281fc2e5d59f99f14c84f4271f86`) and decoded `/tmp/fp6-gmu-clockfix-phone.txt` (SHA256 `185a559ce97068c27f45d3f261d1e62e0c8b28ebb6707c40bbc03c90bb5ba760`) started after the GPU log segment. They contain later boot/userland lines but not the early GMU messages; the console photo is the evidence for those values. Capture ended after 12 seconds because the UDP report stream is continuous.

## FP6 ADT and vendor DTS recovered locally (2026-10-22)

- Copied `/home/ersa/Downloads/vendor_boot.img` to ignored `research/local-fp6/vendor_boot.img` (SHA256 `26dbd78d40a739fd0790518fdaa09bef2cfb4a2098a5daf51098617f0f2ad31c`). `unpack_bootimg` identified Android vendor_boot v4 and extracted its DTB, vendor ramdisk and bootconfig under `research/local-fp6/vendor_boot/`.
- The DTB is a concatenation of 14 FDT blobs. All were split and decompiled with `dtc` under `research/local-fp6/vendor_boot/dtbs/`. `dtb-04` is Volcano (`qcom,volcano`, MSM ID `0x27c`) and its SHA256 `8198534128258bfe7b05bbb5b227affc181aa49b376884c08eae8564fce124e3` matches the previously verified FP6 stock DTB. Selected DTS and DTB are `research/local-fp6/fp6-stock.dts` and `.dtb`.
- Generated `research/local-fp6/fp6.adt` with `tools/mkadt.py --device fp6`; it parsed successfully and contains the iPhone10,3 identity and D22AP `/product` artwork traits. It uses the existing read-only product-tree reference. SHA256 `4da4226e6b9ac393ff22b66a304d9172d6be2bfd6d558348a47379c51aab1d80`.
- Full local artifact inventory, hashes and regeneration commands are in ignored `research/local-fp6/README.md`. None of these device or Apple-derived files are tracked by Git.

## GMU clock fix pushed; bounded boot probe added (2026-10-22)

- Push to `ersascape/ios-extra` on `main`: commit `696a07851fb4e46fd4ab810bdc97e666c14013e2` (`fix(fp6): work on gmu support`). CI run `39674158109` passed; build artifact kernel SHA256 `a10bf7fb4b756f528c95af80d1dc14ed1e66dc8a290c5c0f3dfc6d1fc3670291`. The `fp6-boot` packaging step skipped because `FP6_STOCK_DTB_URL` is unset.
- Patch 0147's phone retry (`/tmp/ios-extra-run-39670975229/logs/phone-0147-gmu-first-boot.txt`, decoded SHA256 `8221b5123fd0ff78b92ebba115458007e007927d75af6a78f97ff2871a939aa2`) confirms GMU `CM3_SYSRESET=1` before setup and MX ARC floor acknowledged. Clock setup then refused without a named failure, so firmware upload/CM3 release did not occur on that boot. The temporary log directory is no longer present in this workspace.
- Patches 0148/0149 add stage-specific clock diagnostics and Linux-aligned setup: MX SVS_L1 floor `0xc0` for GPU PLL calibration, enabling outputs on a compatible inherited Lucid OLE PLL without changing its rate/divider, and waiting for RCG root-on before changing CFG. Unreadable/unsupported live PLL state still refuses; the PLL FSM path remains unsupported because gpucc-volcano exports no software vote register.
- Patch 0149 adds a 16 KiB trace buffer/header, checks firmware fault bits before success bits, and bounds even successful CM3/HFI initialization by asserting reset and verifying it. It retains DMA pages, SID/context and clock votes after the probe, including if reset readback fails, because reset alone does not show bus transactions drained.
- Source review used Fairphone Linux kernel `9535e0f0885d3d4b91c38054541e16019d1e64bd` and modules `54c948d9b30c2ba01835e64c36b68b80692554ac`. `python3 tests/test_gpu_probe.py`, its ASan/UBSan run, and `python3 tests/test_fp6_gmu_boot.py` pass. CI verifies compilation of the patched XNU tree; it does not run these host tests.
- The phone booted 0148/0149 successfully through GMU firmware initialization and HFI_CTRL_INIT. The 0150 CI phone test later stopped safely before upload because CX timer validation returned 0/16 samples; the photo and USB log agree. An unbuilt local follow-up now accepts zero-skew samples and sets CPU WCOMB on the five 16 KiB pages backing the shared HFI queue allocation before publishing the domain. Host normal and ASan/UBSan probes pass; system-Clang AArch64 compile against the exact 39728088129 build tree reports 0/1 failures. No HFI messages or GPU work have run yet. Full HFI still needs the minimum DDR vote, perf/BW tables and MEM_ALLOC request handling. GPU MMU/OOB/SQE startup and a known-value memory-write test remain. UniXNU NativeAdreno/NativeMetal contains A740-specific register and GMEM assumptions and cannot be treated as A810 support.

## Patch 0145 phone log: software table walk passes (2026-10-22)

- A later report appended to `/tmp/claude-1000/-home-ersa-Dev-ios-extra/febca858-d68f-4e09-bdd9-8bdf4a7eb119/scratchpad/gmu-boot4.log` has boot args matching the locally packaged SMMU test (`fp6smmu=2 fp6smmupower=1`). This is a new run in the same log file; the earlier ATOS failure remains above it.
- Phone log: IDR0 `0x4c017e18` advertises ATOSNS; TCR2 readback is `0x00038071`; the CPU table walk reports IOVA `0x60000000` -> PA `0x903617000`, expected `0x903617000`, `passed=1`. This is the first phone confirmation of the software-walk path.
- The final state is `mapped=1 contained=1 route_live=0 bank_reserved=1`; the context bank is disabled and reserved, so no GPU master ran. This validates CPU-visible page tables only, not SMMU table fetch, stream routing, GMU DMA or GPU execution. The log continues through launchd and userland startup; no visible-screen confirmation was recorded.

## Patch 0145 build and local FP6 image (2026-10-22)

- CI run `39663527285` passed for `ced5799de0456a1f06a1fb90291eff40e4e17bfd`;
  kernel artifact SHA256SUMS verified. The CI `fp6-boot` job skipped image
  packaging because the repository variable `FP6_STOCK_DTB_URL` is unset.
- Locally packaged the CI kernel with the full product ADT (SHA256
  `6435ed347b1091a80ae59e695f6decc4f2c89ef647f493b83d2ebf2578a3e752`) and
  verified stock FP6 DTB (SHA256
  `8198534128258bfe7b05bbb5b227affc181aa49b376884c08eae8564fce124e3`). The
  UFS-root command line enables `fp6smmu=2 fp6smmupower=1` for the SMMU
  software-walk validation.
- Image: `/tmp/fp6-gpu-ced5799-39663527285/fp6-shim-0145-soft-walk.img`, SHA256
  `b0555fbcbfb28a9ad8dae5fb3123ec130fabc8a83c2f03f6639d91a7314ad1db`.
  Header-v2 payload, shim, and embedded-DTB round-trip checks passed. This is
  a packaged image only; it has not been booted on the phone.

## FP6 SMMU ATOSNS software walk (2026-10-22)

- Reviewed `/tmp/claude-1000/-home-ersa-Dev-ios-extra/febca858-d68f-4e09-bdd9-8bdf4a7eb119/scratchpad/gmu-boot4.log`. The boot reports GPU SMMU `IDR0=0x4c017e18`; after the CB TCR2 readback it logs `context-bank ATOS IOVA=0x60000000 PAR=0x0 expected=0x90361b000 passed=0`, then contains the failure before any master runs. IDR0 bit 26 (`ATOSNS`) is set, so the zero PAR is consistent with unsupported ATOS rather than evidence of a bad PTE. The same log's setup reached TCR2 but does not include a successful TCR readback.
- Patch `0145-fp6-smmu-soft-walk.patch` uses the configured 4 KiB SMMU granule and T0SZ=32, and checks the expected physical page for both temporary and persistent GMU table ranges when ATOSNS is set. CI `39663527285` passed on `ced5799`; the packaged image and phone result are recorded above. It does not prove SMMU table fetch, SID5 routing or GMU DMA.
- Replaced the persistent-table physical-address scan (up to 2,048 candidate L3 entries on every page walk) with direct L1/L2/L3 selection from the IOVA, while retaining physical-address checks. Corrected the patch hunk count; `git apply --numstat` parses it. Host coverage now checks the ATOSNS path issues no ATS write and returns the expected PA, and checks direct persistent table lookup at all three levels.
- `python3 tests/test_gpu_probe.py` passes. Full host suite: 12 tests pass normally and with ASan/UBSan (`ASAN_OPTIONS=detect_leaks=0`). The phone report passes the software walk; no screen confirmation is recorded.

## Timer failure diagnostics follow-up (2026-10-22)

- The latest `ml_get_hwclock()` image reached `upload refused: CX timer
  synchronization failed`; no USB capture was produced, so the exact failing
  branch is unknown. Source review found silent returns if either CX counter
  read fails or if CPU/CX counters do not advance during the bounded 1 ms
  check.
- Added patch 0151 to print which counter read failed, or both before/after
  values when the counters do not advance. Verified it applies to the exact
  source tree from CI run `39732507544`. This is source-level verification
  only; CI and phone results are pending.

## FP6 CX timer: USB diagnosis and Linux-aligned seed fix (2026-10-22)

- CI `39735265609` passed for `089d4ef39822e751ada55eae9bc53f3ccc4472f2`.
  The temporary image was `/tmp/ios-extra-run-39735265609/package/fp6-gmu-timer-diagnostics.img`,
  SHA256 `b5a30a6bce20a730c39529ae08121ddfdbe29c614ad42477b3a21ed9de6c9fef`.
  It was booted once with `fastboot boot`; no partition was flashed or written.
- USB capture `/tmp/ios-extra-run-39735265609/logs/phone-0151-cxtimer-diagnostics.pcap`
  (SHA256 `d297cbf17896b9e36d0afc4709ae6ead0b1eeff7fb7709a9cfdba6a12aca0851`)
  decoded to 405 packets / 122,058 log bytes at
  `/tmp/ios-extra-run-39735265609/logs/phone-0151-cxtimer-diagnostics.txt`
  (SHA256 `729d365b3edab8c39364aca208c58e2673738594498b8dfb438ebba4c643af32`).
  The phone reports CPU counter `0x71e78f2c7->0x71e793e01` while CX stays
  `0x71e78f2ab->0x71e78f2ab`; this confirms the added “must advance” check caused
  the refusal. Firmware upload, SCM/CM3 release and HFI did not run.
- Patch 0152 removes the post-seed CX readback, offset, advance and rate gates.
  Fairphone Linux `gen8_cx_timer_init()` seeds the counter and continues without
  those checks. The host harness models a static post-seed CX counter;
  `python3 tests/test_fp6_gmu_boot.py` and `git diff --check` pass. CI and phone
  validation of this fix are pending.
- Commit `09a398b2d85e1a38e17558003ecdb3e0faa64dc1` passed CI run
  `39739290127`. Kernel SHA256 is
  `9a5d96ef3eb2a2d9b6e854cdaf05852fce850ca18fe57e87e4376364e770a630`.
  Packaged header-v2 image `/tmp/ios-extra-run-39739290127/package/fp6-gmu-cxtimer-linux-seed.img`
  SHA256 `1062709ab0ab0d7a88b8bc5a15a25a3141b5bb4b48557c19741a54b6272ec881`
  with product ADT SHA256 `4da4226e6b9ac393ff22b66a304d9172d6be2bfd6d558348a47379c51aab1d80`
  and stock DTB SHA256 `8198534128258bfe7b05bbb5b227affc181aa49b376884c08eae8564fce124e3`.
  Kernel checksum and package round-trip checks passed.
- Initial checks found `fastbootd`, then no device. A later explicit user
  authorization put the phone in bootloader fastboot and the image was tested
  once, as recorded below. No flash or partition write occurred.
- Linux Gen8 source confirms minimum DDR bandwidth is voted after firmware load,
  SCM CX setup and version info, before GMU start and HFI. The XNU RPMh helper
  currently supports ARC and VRM resources, not the interconnect/BCM vote, so
  if timer removal reaches FW_INIT the following measured work is the minimum
  DDR vote before enabling HFI traffic.
- Phone test on `fp6-gmu-cxtimer-linux-seed.img` was then authorized and run
  once through `tools/gpu-phone-test.py`. `fastboot boot` returned OKAY, but the
  phone panicked before answering the USB ECM ping. The supplied panic is
  `phystokv_range: illegal pa: 0x3df4000 phys base 0x900000000 size 0x100000000`
  at `arm_vm_init.c:406`. No pcap was produced; only the helper's fastboot
  transcript remains at
  `/tmp/ios-extra-run-39739290127/logs/phone-0152-linux-cxtimer-seed-fastboot.txt`.
  No second boot or recovery command was issued.
- Source-order candidate (not yet confirmed by a panic backtrace): after the
  timer check, `fp6_gmu_boot_reserve()` first changes the five HFI backing pages
  to WCOMB. XNU's `pmap_set_cache_attributes()` reaches `phystokv_range()` when
  the page is treated as managed RAM; the reported PA is outside the configured
  high RAM window. The full panic backtrace is needed to confirm this caller
  before changing allocation/cache policy. The device is currently back in
  bootloader fastboot after the panic.

## Current FP6 GPU path

The target is FP6 Adreno 810 Gen8.3. Patches 0148/0149 booted on the phone: the corrected GPU PLL/GMU clocks came up, 159 persistent pages were checked/uploaded, GMU firmware reported `FW_INIT_RESULT=0x100`, HFI controller initialization reported `HFI_CTRL_STATUS=1`, and CM3 reset was verified afterward. The photo records early GPU lines; the later USB capture started after that segment. GMU DMA and HFI command processing are still unproven.

The focused 0153 follow-up removes the new HFI WIMG rewrite that is the only
new path to `pmap_set_cache_attributes()` in this boot; the established
allocator and clean-before-publish sequence already ran in the earlier HFI
controller boot. Patch 0153 passes the GMU host probe normally and under
ASan/UBSan, and `sweet_gpu.c` compiles against CI run `39739290127`'s buildtree
with system Clang. CI and a phone result are pending. Keep HFI controller init
bounded; add explicit cache ownership transitions before HFI message traffic.
After the phone confirms the panic is gone, resume with the minimum
Linux-matching DDR vote, full HFI tables and MEM_ALLOC handling, safe idle, GPU
MMU/OOB and Gen8 SQE/AQE execution, a bounded GPU memory write, draw/readback,
then an IOKit allocation/submission/fence ABI and an A810-compatible Metal
frontend and IOSurface presentation.

See [FP6 GMU first boot](docs/FP6_GMU_FIRST_BOOT.md), [FP6 Adreno Metal audit](docs/FP6_ADRENO_METAL_AUDIT.md) and [FP6 SMMU power](docs/FP6_SMMU_POWER.md).

## Freedreno / Metal reference inspection (2026-10-22)

- Read-only inspection of `/tmp/hackios-xnu-kernel` commit
  `8e61187098f2c26c5daee8f9f72b6416aa64b9ab` and
  `/tmp/hackios-xnu-userland` commit
  `906425b75e02b4f99eb5d7bb1ef7c9583472d772`, especially
  `tools/mesa/mk-mesa.sh`, `tools/mesa/freedreno-darwin.patch`,
  `tools/mesa/redwood-drm/`, and `iokit/Kernel/RedwoodGPU.cpp`.
- Confirmed the working rendering path is Mesa Freedreno (`msm` DRM KMD) over
  an IOKit `RedwoodGPU` user client: buffer create/info/map/close, command
  submission, and fence waits. The userland DRM shim maps the Linux ioctl
  selector and structure ABI onto IOKit calls; buffer handles are mapped as
  client memory. IOSurface import has a separate Redwood selector.
- AIR is a Mesa frontend to NIR/ir3 and is callable from the Metal library
  path, but it does not implement Apple's Metal object model or submission
  ABI. The reference's measured hardware is Adreno 642L; FP6 is Adreno 810
  Gen8.3, so its kernel interface and lifetime model are useful, while its
  chip-specific command programming cannot be copied as A810 support.
- Panic follow-up from CI buildtree `39739290127`: the reported PA
  `0x3df4000` equals `0x903df4000 - gPhysBase(0x900000000)`, an offset within
  the configured RAM window. This raises a specific question about a
  base-relative page number being passed where XNU expects an absolute PA.
  The exact code path is still unconfirmed without panic frames. Do not change
  allocator/cache policy or run another phone test on this inference alone.

## Patch 0150: CX timer and SCM CX preflight (2026-10-22)

- Source inspection: Fairphone Linux `adreno_gen8.c` initializes the CX AO
  timer with 16 samples using `cntpct` and writes to `cx_misc` offsets
  `0x200/0x204`; first GMU start calls optional SCM CX setup with ALWAYS_EN and
  TSENSE. Patch 0150 ports the sample/seed operation, adds bounded readback
  and rate checks, and requests only those two features (`0x9`), leaving BCL
  and CLX disabled.
- The opt-in `fp6gmuboot=1` path synchronizes the timer before firmware upload.
  SCM availability and initialization are checked before SID publication and
  CM3 release. An unavailable SCM service is treated as optional; an available
  service returning an error aborts before the GMU is routed as an SMMU master.
- Host-model timer/SCM fault-injection tests, normal and ASan/UBSan runs, the
  GPU probe host harness and a local AArch64 single-file syntax compile passed.
  The compile used system Clang because the configured Swift Clang path is
  absent. Full unittest discovery cannot import `test_fp6_gmu_runtime.py`
  because `/tmp/fp6-firmware/gen80300_gmu.bin` is unavailable; the directly
  relevant tests pass.
- CI run `39728088129` passed on `c1de4a39ed6dfc2307311fc9d09115f1d3085f5a`.
  Kernel SHA256 `0f57862c073138ddcf74c1380f862c5bc295f3cea2849c8d781a313d15278710`
  verified against `SHA256SUMS`. The workflow image package skipped because
  `FP6_STOCK_DTB_URL` is unset. Local header-v2 image
  `/tmp/ios-extra-run-39728088129/package/fp6-gmu-cxtimer-scm`
  has SHA256 `ff170c41e125c5f1e91431f14a281db4dfe7855d4e55c8d92274f747d489ebd8`;
  it embeds the verified stock DTB and product ADT and enables the opt-in
  upload/first-boot path. No phone boot yet: `fastboot devices` showed zero
  devices when the image was ready.
- Phone test of that image reached launchd and ECM ping. It stopped before
  firmware upload: timer reported `valid=0/16 CNTFRQ=19200000`; therefore SCM
  CX setup, CM3 release, `FW_INIT_RESULT`, and `HFI_CTRL_STATUS` were not
  attempted. The decoded USB capture is
  `/tmp/ios-extra-run-39728088129/logs/phone-0150-cxtimer-scm.txt` (SHA256
  `36c5f8cb4638a0a5436b49e14538160d7907f309f1c6e2a793328bc06ec74a89`); pcap
  is beside it (SHA256
  `e7d6cc8bcaaa7c35b1923a85765e551ee93ebc1eedcf0732bdbc318575949c10`). The
  console photo corroborates the timer failure and shows the subsequent SMMU
  context test contained with `route_live=0`.
- Root cause is now narrowed to the sample filter: the code rejected
  `write_cost == read_cost`, although a 19.2 MHz counter quantizes short
  accesses to equal ticks. The next local patch accepts zero-skew samples and
  reports raw read/write timing ranges plus shorter/outlier counts. Normal and
  ASan/UBSan host tests cover the equal-tick case; the updated file compiles
  against the CI build tree with system Clang. This fix is not yet built by CI
  or phone-tested.
- The combined local follow-up also marks all five 16 KiB CPU pages covering
  the shared 0x12000-byte HFI allocation `VM_WIMG_WCOMB` before writing queue
  headers or publishing the SMMU domain. It confirms physical contiguity and
  that each page was default cached or already WCOMB, then sets and checks the
  attributes. This mirrors Linux's write-combine HFI mapping and prevents
  cached CPU writeback from clobbering GMU-owned queue indices. The pmap API
  definitions are explicitly declared in the FP6 driver because they are not
  exported by the BSD-visible header configuration.
- The combined patch passes `test_fp6_gmu_boot.py`, `test_gpu_probe.py`,
  `test_rpmh_arc.py`, and `test_xnu_cc.py`, normally and the two C harnesses
  under ASan/UBSan. A system-Clang AArch64 compile of `sweet_gpu.c` against
  the exact CI 39728088129 build tree reports 0/1 failures. This source delta
  is local only: no CI build or phone test has been run for it yet.
- Follow-up build `6c248dd` passed CI run `39730474027`; kernel
  `SHA256=1dccb4fb5992417c37b73c28fc74d49e30c2f7dc8b3e2050fd5b8cfd08a02228`.
  The temporary header-v2 image
  `/tmp/ios-extra-run-39730474027/package/fp6-gmu-timer-wcomb.img` has
  `SHA256=f2b92b5fcfeb6af4e86a953dae8202b12abda5c1f700e8a9c59cd51d69137845`.
  Its phone boot still refused the timer: `valid=0/16`, `read=0..0`,
  `write=0..0`. USB capture contains 705 packets / 168,631 log bytes;
  pcap SHA256 `048725f34765776a36d4ce5cbc13733854bbf47875ed30b491ca095e15f59dfe`,
  decoded text SHA256 `e14fbf9b65b5a6dd6ff6f4d6d791f254933d0530ec79ad71d8d7bcbc94aed83a`.
  It confirms SMMU test contained and no firmware upload. All samples were
  discarded as backward before recording timing ranges.
- Source inspection found XNU's `ml_get_hwclock()` is its nonspeculative
  `CNTVCT` hardware timebase; the driver had used raw `CNTPCT`. The latest
  local update uses `ml_get_hwclock()` and logs backward-read counts plus the
  final raw sample triple. This is an XNU-specific counter-source correction
  inferred from the phone result; no CI or phone result exists for it yet.
- The interrupted test exposed a prompt loop in `phone-ecm-host.py`: setup
  errors retried two `pkexec` commands every 100 ms, while the outer test also
  made separate capture/cleanup authorization requests. The updated helper
  performs setup, bounded capture and stale-capture cleanup under one
  authorization, fails immediately on setup/auth errors, and self-stops
  tcpdump. The prior root capture at
  `/tmp/ios-extra-run-39730474027/logs/phone-0150-timer-wcomb.pcap` was not
  stoppable after pkexec authorization was denied; the next authorized helper
  call can stop only that exact capture path. No serial is stored.
- Minimum DDR bandwidth/BCM voting remains unresolved. Do not send HFI messages
  until shared HFI backing is mapped Normal noncached on CPU pages and runtime
  BCM metadata is understood.

## FP6 GPU SMMU: TCR2 passes, FSR FORMAT bits (2026-10-21)

- Boot of CI `39650403002` (`b919d67`, 0143), 18:19:12 UTC, USB log:
  `TCR2 wrote 0x00038011 read 0x00038071` (accepted), then `setup failed:
  fault clear +0x22058 want=0x00000000 got=0x00000400`, `contained=1
  route_live=0 bank_reserved=1`. FSR 0x400 is FORMAT (bits 10:9 = 0b10,
  AArch64 context), read-only, not a fault. Patch 0144 checks only Linux's
  ARM_SMMU_FSR_FAULT bits (0xc00001fe), and compares only programmed fields
  for SCTLR (0x27), S2CR (TYPE + CBNDX) and SMR, logging any extra bits read
  (pre-emptive: this SMMU has forced read-only bits). Compiles locally; host
  suite passes.

## FP6 GPU SMMU context bank live; TCR2 TBI bits (2026-10-21)

- Boot of CI `39649157006` (`ebae218`, 0141/0142), 18:09:17 UTC; full boot
  log received over USB (0142 whole-ring replay works, 104 KB including the
  early SMMU inventory: IDR0=0x4c017e18 IDR1=0x40000016 IDR2=0x00005511
  sCR0=0x002c0406, 24 groups, 22 banks). CX vote + GDSC on as before;
  `clock index=3 running without SW enable (0x00000000)` (0141 works).
- **CB2 TCR2 now retains its value**: wrote 0x00038011, read 0x00038071.
  Previously it read 0 (dead bank while CX was collapsed). The difference is
  TBI0/TBI1 (bits 5-6), forced on by the hardware or hypervisor; the strict
  readback rejected it before any stream route was written (`route_live=0`),
  and the rollback's TCR2==0 check reported `contained=0` for the same bits.
  Patch 0143 compares TCR2 without the TBI bits in setup and rollback and
  logs the value read. Compiles locally; host suite passes.

## FP6 GMU boot attempt: stopped at the SMMU AHB clock (2026-10-21)

- Boot of CI `39647440570` (`8e055a8`, all GPU stages on, console muted),
  18:00:16 UTC. Phone stayed up (launchd running). Console photo: RPMh CX
  vote and CX GDSC succeed again; `before/after AON gates ahb=0x00000000
  hub_cmd=0x00000000 hub_cfg=0x00100000 hub_div=0x00000001`; gates
  cb 0x1, cxo_aon 0x0, demet 0x0, gx_ahb_ff 0x80000001, rscc_hub_aon 0x1,
  rscc_xo_aon 0x1, sleep 0x1; then `clock index=3 before=0x00000000` and
  `prerequisite clock failed index=3; no context writes`, so the context
  test, upload and CM3 release did not run.
- gpu_cc_ahb reads 0 with CLK_OFF clear: running under hardware/other-voter
  control while its SW enable ignores writes (cxo_aon and demet likewise).
  Linux does not read back HALT_DELAY branch enables. Patch 0141 accepts a
  branch that is SW-enabled or not CLK_OFF, and logs it.
- USB log: the host received 37 KB starting mid-boot; the early lines were
  lost because the logger replays only 64 KB and starts sending at link-up,
  before NetworkManager has assigned 192.168.7.1. Patch 0142 replays the
  whole 4 MB ring and waits 3 s after link-up. Host side: NM profile
  `fp6-usb-log` and a ufw rule for UDP 5140 (added by the user).

## FP6 SpringBoard/PosterBoard crash after Bold Text: CoreImage GL (2026-10-21)

- User enabled Settings > Accessibility > Bold Text; SpringBoard and
  PosterBoard then crash: `CRASH SpringBoard sig 11 code 0x100000001 sub 0x0
  slide 0x35730000`, `pc 0x0 lr 0x1ca26858c` (unslid 0x194b3858c).
- Symbolicated with ipsw 3.1.739 against the 20H392 shared cache extracted
  from the Tegu root (local, git-ignored: `research/dsc-20H392/`,
  `research/tools-ipsw/ipsw`): CoreImage `CI::GLContext::init()` +204. Its
  `GetMacroContext` -> `[EAGLContext getMacroContextPrivate]` returns NULL
  (no GLES renderer: no GPU driver), the 0x2c8-byte GL dispatch struct stays
  zero, CoreImage logs "Unable to get macro state for the GLContext" and
  then calls slot +0xe8 with 0xb71 (GL_DEPTH_TEST) -> blr to NULL. No Bold
  Text code in that function; the respring path presumably creates a GL
  CIContext (inference). Fix depends on a GPU renderer, or forcing CoreImage
  to its CPU renderer / making GL context creation fail cleanly (not tried).

## FP6 GMU first boot patch (2026-10-21)

- Patch 0140 (opt-in `fp6gmuboot=1`, after a successful `fp6gmuload=1`
  upload; also needs `fp6smmu=2 fp6smmupower=1`) follows
  `docs/FP6_GMU_FIRST_BOOT.md`: reserves noncached HFI (0x12000, 17 queues),
  log (64 KiB) and VRB (4 KiB) first-fit from 0x60000000 before the domain is
  frozen, fills the queue table/VRB header, re-arms the SID5 stream match,
  masks all GMU interrupts, writes KGSL's register config (RPMH_POWER_STATE,
  FAL, BOOT_CONFIG 2, HFI_QTBL, fence range 0x80c808a0, CM3_CFG 0x4052,
  GBIF, GENERAL_8..11, caches), prints the DTCM firmware versions, releases
  CM3 and polls FW_INIT_RESULT for 0x100 (100 ms, aborts on 0xe00), then
  HFI_CTRL_INIT/STATUS. No HFI messages yet. Failure puts CM3 back into
  reset, masks/clears interrupts and sets the fence to allow. Compiles
  locally; host suite passes; no phone result. This would be the first GMU
  firmware execution on FP6.

## FP6 first RPMh vote and CX power on the phone (2026-10-21)

- No-spam GPU power test (`fp6smmu=2 fp6smmupower=1`, kernel `121a02d`,
  booted 17:42:00 UTC), console photo: `CX GDSCR=0x0022f001
  status=0x2800010a HUB_CMD=0x00000000`; **`FP6 CX ARC floor 0x40
  acknowledged level=2 TCS=0`** (first RPMh vote from XNU on FP6); **`CX GDSC
  on GDSCR=0xf8228800 status=0x80000202`** (PWR_ON). SMMU clocks: 0x7000
  before 0x80000000, GCC memnoc 0x3, snoc 0x1, gpu_cc_ahb 0x90bc before
  0x00000000 and its enable did not stick -> `prerequisite clock failed
  index=3; no context writes`.
- gpu_cc_ahb and the hub RCG reading all-zero (not CLK_OFF) suggest a dead
  hub/RSCC clock domain. gpucc-volcano probe enables seven always-on gates
  (cb, cxo_aon, demet, gx_ahb_ff, rscc_hub_aon, rscc_xo_aon, sleep) before
  any GPUCC clock; our SMMU path did not. Patch 0139 enables them right
  after the CX GDSC and logs ahb/hub before and after (source-based).

## FP6 canvas placement and USB log host setup (2026-10-21)

- User: a black bar is visible at the top. 0130 centred the 1125x2436 canvas
  on the 1116x2484 panel (24 rows above and below). Patch 0138 adds boot-arg
  `sweetfb_top=N` (rows above the image, clamped to 0..48) in AppleCLCD and
  SweetHID alike, default 0: image at the top edge, the 48 spare rows below.
  Both files compile locally; no phone result yet.
- The GPU CX test boot (17:37:51 UTC) could not be read: `-enable_kprintf_spam`
  in the hand-written boot args flooded the console. Repacked without it:
  scratchpad `img-121a02d/nospam/fp6-shim-gpu-cx-power-console-nospam.img`,
  SHA256 `2b76017a22ebf733599e2556648dc9d15fde27aa2b029f167289bfa6a457c6ec`.
- Host USB log: NetworkManager profile `fp6-usb-log` (static 192.168.7.1/24,
  matched by host-side MAC 02:00:5e:77:ee:01, autoconnect) replaces the DHCP
  attempt on `enp128s20f0u9`; ping 192.168.7.2 answers. A user-level UDP
  listener received nothing because ufw is active; allowing UDP 5140 on that
  interface needs root (`ufw allow in on enp128s20f0u9 to any port 5140 proto
  udp`).

## FP6 GPU power review and fixes (2026-10-21)

- Recovered an interrupted session's unpushed work from `/tmp/fp6-smmu-work`
  onto branch `codex-gpu-rescue`: commits 3896b67/e63291f/ab3faae/22d527c and
  uncommitted 0134 (opt-in `fp6smmupower=1` CX ARC floor + CX GDSC + hub CXO),
  0135 (`fp6gmuload=1` GMU upload with CM3 held in reset), 0136 (GMU clock
  preparation), `docs/FP6_SMMU_POWER.md` and host tests. CI `39641511245`
  built it.
- Phone evidence (console photo, earlier kernel): `CX_GDSCR=0x0022f001`
  (SW_COLLAPSE set), GPU SMMU groups 10-23 invalid with S2CR fault type,
  `context banks with nonzero state=0/22`. The SMMU (`kgsl-smmu@3da0000`,
  `vdd-supply = gpu_cc_cx_gdsc`) sits in the collapsed CX domain, which is
  the leading explanation for CB2 TCR2 reading back 0.
- Source review against Fairphone `gdsc-regulator.c`, `rpmh-rsc.c`,
  `arm-smmu.c` and KGSL gen8 found, and patch 0137 fixes: CX GDSC power
  status is GPUCC+0x9094 (DT `hw-ctrl-addr`), not GDSCR bit 31; GDSC enable
  now sets clk-dis-wait 8 and RETAIN_FF like Linux; RSC votes no longer mask
  the slot IRQ and poll gated IRQ status - they use Linux's two-step
  trigger/mode clear and poll CMD_STATUS ISSUED|COMPL and TCS idle; the ARC
  floor is LOW_SVS (0x40) instead of the TURBO boot-proxy 0x180; GMU clock
  preparation no longer reads GMU registers before all six KGSL GMU clocks
  run (adds hub_cx_int 0x90e8) and refuses if the GMU core clock is already
  on; FP6 GPU MMIO is single LDR/STR inline asm with register sources and
  TLBIALL/TLBSYNC write QCOM_DUMMY_VAL (-1), per arm-smmu.c's hypervisor
  note. The earlier 0131 rollback abort matches Gunyah refusing a stage-2
  CBAR (TYPE=0) restore. Host model updated (status register, GDSC bits,
  LOW_SVS index); 12/12 host tests pass; local arm64 compile passes; FP6 GPU
  functions contain no WZR/XZR MMIO stores or write-back MMIO accesses.
- Not yet fixed (latent): PAS/zap SMCs use FAST call IDs, leave x6
  uninitialized and do not handle INTERRUPTED/WAITQ returns (Linux uses STD,
  x6=0, retries); the zap carve-out stays mapped after load. FP6's GPU is
  Adreno 810, Gen8.3 (`qcom,adreno-gpu-gen8-3-0`, gen80300 firmware, KGSL
  hwsched path); the GMU is at 0x3d37000/0x68000 per the stock DT.
- Merged to main as `f103c2d`. Test image from CI `39643343440` (branch
  head `121a02d`; kernel patches identical to main `f103c2d`), local ADT with
  `/product`, stock DTB, console visible, `fp6touch=2 fp6smmu=2
  fp6smmupower=1`: scratchpad `img-121a02d/fp6-shim-gpu-cx-power-console.img`,
  SHA256 `88b5038ad453a48dd31d2be689afd243c8589aa7cbea7434bfae72ac8e9e1d51`.
  Kernel contains the 0137 log strings. Temporarily booted 17:37:51 UTC;
  first FP6 RPMh (CX ARC LOW_SVS) vote attempt; result pending.

## CX power state observed on phone (2026-10-21)

- User supplied a console photo from the clock-prerequisite build. It shows
  `CX_GDSCR=0x0022f801`, `HUB_CMD=0x00000000`, followed by the refusal
  `CX domain is not enabled; needs RPMh/CX power before context access`. The
  GDSCR SW_COLLAPSE bit is set and PWR_ON is clear, consistent with an off CX
  domain. This run did not reach TCR2 programming, so it does not isolate why
  the earlier TCR2 write read as zero. The photo does not independently name
  the image, though its diagnostic text matches the 0b41ea2 clock build.
- 0134 draft now adds a dedicated FP6 RSCv3 CX ARC floor vote and CX GDSC/hub
  safe-XO setup. It needs source review, full harness and kernel build before
  any phone test. GMU clocks remain a separate stage; avoid changing live GMU
  rates until reset state has been read.

## Stock-clock kernel packaged (2026-10-21)

- CI39636402248 passed on0b41ea23c1d910865a2412c88fcccedb3dfb388e.
  Downloaded kernel matched artifact SHA256SUMS. Packaged visible-console
  UFS-root image `/tmp/fp6-smmu-0b41ea2/image/fp6-shim-smmu-clocks.img`,
  SHA256 `d4c7a60686b9e71c796900d94ca43531ba4d5e0657b937928b3ddd702341d0ff`.
  Header/payload/DTB packaging checks passed. Includes0132 stock clock votes,
  not the subsequent0133 domain helper or draft0134/0135. No phone result yet.
- Loader callback failure cases now check readiness, allocation, external copy,
  TCM write and publication failures stop the upload at the proper boundary.
  Eight firmware unittest cases passed after this extension.

## Persistent Gen8 GMU mapping layer (2026-10-21)

- Patch0133 adds boot-lifetime sparse 4KiB tables and external backing
  reservation/copy/publication operations. It rounds firmware reservation sizes
  to page coverage and refuses page overlap; uses Normal NC, privileged RW,
  outer-shareable PTEs matching KGSL flags without IOMMU_CACHE. GMU cached VMA
  metadata does not silently choose write-back SMMU attributes.
- `python3 tests/test_fp6_gmu_domain.py` passes synthetic boundary/failure
  cases and actual pinned firmware through upload callbacks, with payload byte
  comparisons and PTE physical-address walks. The map freezes after publishing.
  This remains a staged helper without a runtime owner; live allocation/cache
  callbacks, context activation and GMU execution are not established.

## Firmware loader host check (2026-10-21)

- Eight `tests/test_fp6_gmu_fw.py` cases pass, including staging both headers
  and compiling/running the upload layer against the SHA-pinned actual blob.
  Callback harness checks six external reservations, one external data copy,
  all TCM words and final publication. ASan/UBSan execution also passed with
  leak detection disabled (LeakSanitizer is unsupported under this host tracer).
  This proves callback sequencing on host, not real DMA or GMU execution.
- Review caught an integration issue in draft0133: firmware preallocation
  lengths are not all page aligned; the mapping layer must round safely.
  Also verify cache attributes against KGSL flags rather than infer them from
  GMU VMA names. Agent is correcting these before integration.
## FP6 SpringBoard bounding-path crash: missing /product artwork traits (2026-10-21)

- Correction to the entry below: the user reports the stale MobileGestalt
  cache was already cleared, so the cache theory does not explain the
  `69f9878` crash. That image used CI's `fp6.adt` (10,496 bytes), which has
  **no `/product` node**: CI lacks the Apple D22AP tree, so mkadt silently
  omitted it. Local ADTs (13,180 bytes) carry `/product` with
  `artwork-device-subtype` 0x984 (2436), `artwork-scale-factor` 3,
  `artwork-device-idiom` "phone", `artwork-display-gamut` "P3" and
  `artwork-dynamic-displaymode` "0" - the traits the asset manager uses to
  pick renditions. Without them `BoundingPathBitmap-1125x2436-375x812-3.00x`
  cannot be matched even though it exists. Earlier home-screen boots used
  local ADTs with `/product`.
- `tools/mkadt.py` now refuses a non-QEMU ADT without `/product` unless
  `--allow-no-product`; `tools/fp6-package.py` refuses an ADT lacking
  `artwork-device-subtype` unless `--allow-no-product` and records
  `product_node` in the manifest. CI passes the override for its build-only
  ADT and its (currently skipped) packaging. Local checks: missing D22AP
  tree -> both tools refuse; override -> `product_node: false`; full ADT ->
  `product_node: true`.
- The `img-0b41ea2` image below has `/product`. If SpringBoard still aborts
  with it, the no-`/product` boot may have re-cached wrong traits and the
  MobileGestalt cache needs clearing once more.

## FP6 SpringBoard bounding-path crash: earlier stale-cache hypothesis (2026-10-21)

- `/tmp/fp6-blackboot-packets.txt` (kernel `69f9878`, which already includes
  0130's 1125x2436 canvas) shows 423 SpringBoard aborts:
  `Failed to load bounding path bitmap data from the asset manager for asset
  name: BoundingPathBitmap-1125x2436-375x812-3.00x`. The requested name is
  the correct iPhone X one and the asset exists in the root catalog (earlier
  audit), so canvas geometry is no longer the issue.
- Same failure as Tegu, where it followed boots with the wrong identity and
  cleared only with a fresh root booted with the correct D22 ADT from its
  first boot. On FP6 the current root booted several times with the native
  1116x2484 screen before 0130; MobileGestalt's disk cache (keyed by build and
  UUID, per SWEET) keeps traits derived from that screen. Source-based
  diagnosis; not yet confirmed by a clean-root boot.
- Proposed test: reflash the never-booted Tegu-built root
  (`research/fp6-rootfs-tegu-20261021/fp6-ios-root-tegu.simg`, `a1c6f7da...`),
  then first-boot a kernel with 0130. Image from CI `39636402248` (`0b41ea2`;
  0070, 0130, touch, keys; GPU tests off by default), regenerated ADT with
  canvas 1125x2436 and `/product`, stock DTB `16a9e60e...`, console muted,
  `fp6touch=2`: scratchpad `img-0b41ea2/fp6-shim-ufs-root-touch-canvas.img`,
  SHA256 `5e8c0f7b8f47549f41a13af95b9bb1c2ad2db2e30928d6ad216beb535d6d3274`.
  Not booted yet.

## Stock SMMU clock prerequisites and battery protocol (2026-10-21)

- Patch0132 votes the four stock SMMU clocks in DT order, with bounded
  Linux branch halt/HWCG handling. It borrows only an already-powered CX
  domain and running hub parent; full regulator/RPMh/hub ownership is still
  needed if either is off. Context refusal is not successful translation.
  Agent reports host harness passed; no phone result or kernel build yet.
- Fuelgauge audit and transport-independent numeric GET protocol are in
  `docs/FP6_FUELGAUGE_AUDIT.md` and `xnu/protocol/fp6_battery_glink.h`.
  Stock reporting uses ADSP PMIC GLINK, not the old PM6150 polling path.
  No live transport or measured gauge readings exist yet.
- SpringBoard agent compared the local root catalog against original OS.dmg:
  matching SHA256 `0a53453f1e096f70ccb38618b0b8c32fa950f71dc3b559c4ce556825517aa04d`.
  This excludes corruption/omission of that local catalog, not a runtime
  rendition/trait lookup failure or a difference on the running phone.

## Gen8 firmware upload layer (2026-10-21)

- Added `xnu/helpers/fp6_gmu_loader.h`, staged alongside the pinned generated
  firmware by 0129. It follows KGSL Gen8 preallocation/TCM/external-copy
  semantics with explicit backing, reset-readiness and visibility callbacks.
  TCM indices use Gen8 GPU dword register indices, not guessed physical addresses.
  This is an unconnected implementation layer: live XNU allocation/SMMU mapping
  callbacks and startup integration remain required. No firmware execution or
  build/test result is claimed for this change.
- SpringBoard audit found the requested bounding-path name in the root catalog;
  the earlier runtime failure does not prove the catalog file is absent. Exact
  rendition lookup/decoding is under investigation; preserve statusbar geometry.

## FP6 exact SMMU refusal and SpringBoard capture (2026-10-21)

- Phone console photo reports `setup failed: register readback +0x22010
  want=0x00038011 got=0x00000000`: CB2 TCR2 did not retain the requested
  value. CBA2R/CBAR checks precede it and passed. Translation and GMU execution
  remain unproven; do not accept zero as successful setup. Investigating the
  Fairphone driver's SMMU power/clock and access prerequisites.
- CI `39630788262` succeeded for `69f987818adc6ebe628e8f453a1f10f668c7dd5f`.
  Local visible-console package:
  `/tmp/fp6-smmu-69f9878/image/fp6-shim-smmu-failure-visible.img`, SHA-256
  `bd604be97cf92049048ad5751efbad7663077b49a18c129a8f5ec1296cabc3b4`.
  Uses selected stock DTB, UFS root, existing ECM transport; no Tegu draft.
  Packaging checks passed. Photo alone does not independently identify its image.
- Passive USB capture `/tmp/fp6-blackboot-69f9878.pcap` recorded 4575 packets,
  zero capture drops. Capture filename is not proof of running kernel identity.
  Decoded packet text `/tmp/fp6-blackboot-packets.txt` shows repeated SpringBoard
  SIGABRT with `_UIScreenComplexBoundingPathUtilities` assertion: missing
  `BoundingPathBitmap-1125x2436-375x812-3.00x`. This establishes a userspace crash;
  it does not establish the cause of the reported gradual display darkening.
  Rootfs asset/identity investigation is separate from SMMU/GMU startup.
- Auth-to-Metal audit is in `docs/FP6_ADRENO_METAL_AUDIT.md`. UniXNU has a
  Darwin Turnip backend worth adapting. AirNir currently hard-gates generation7
  and its host script selects A740; FP6 needs the A810 target. This is source
  evidence, not an FP6 runtime result.

## FP6 CB2 test phone observation and failure diagnostics (2026-10-21)

- User's new console photo shows `context banks with nonzero state=0/22`,
  followed by `context test group=0 cb=2 mapped=0 contained=1 route_live=0
  bank_reserved=1 result=test failed; no master run`. Boot proceeds through
  platform registration and CPU startup at the shown point. This demonstrates
  that this attempt passed the earlier rollback panic site, but does not prove
  home-screen arrival or successful translation. The photo followed delivery of
  the atomic ATS image; its exact flashed/booted artifact is not independently
  established by the photo.
- No ATOS result or timeout appears between inventory and the failure summary.
  The likely exit is an earlier register-readback, fault-clear, or TLB-sync
  check. Previously these all silently entered rollback. Patch 0131 now caches
  the first failed offset, requested value and readback and reports them after
  cleanup, distinguishing readback mismatch, FSR clear failure and TLB timeout.
  It changes no register programming or acceptance criteria. Host tests verify
  each nonzero refused setup write reports its exact offset and never reaches
  ATOS; normal and ASan/UBSan suites pass. Firmware has not executed.

## FP6 atomic ATS image, existing ECM transport (2026-10-21)

- CI `39627541732` passed for `2a068b7c182bce5b11bf6bffe3b47d702683e3c4`.
  Downloaded kernel SHA-256
  `0b7a4b4c47fb28dc3275250241ab235065ffc672e82d18a5db16babb85d1f3db`
  matched its CI SHA256SUMS before packaging.
- Packaged `/tmp/fp6-smmu-2a068b7/image/fp6-shim-ufsroot-smmu-atomic.img`,
  SHA-256 `bec67541d4c5d0b08d985f03e65201004aa833d9e4741fc9ee04ea94b8e6a9c4`.
  Uses the verified selected FP6 stock DTB (`81985341...`), UFS root,
  `fp6smmu=2`, `fp6usb=2`, `fp6touch=2`, `fp6pas=1`, eight CPUs and quiet
  console defaults. Header-v2 payload/shim/DTB round-trip checks passed.
  No Tegu transport changes are included; no phone test has run.
- Work on an EP0 host-pull log console is an external draft only:
  `/tmp/fp6-usb-ep0-log-console.draft.patch`. It sketches an EP0-only mode3,
  serial-callback polling and deferred SMMU test after USB startup. It is not
  in the patch series or any kernel/image. Host reader, protocol tests, deferred
  test harness stubs and full kernel validation remain unfinished. Do not apply
  it unchanged. The firmware port remains incomplete: no GMU execution yet.

## FP6 atomic ATS correction and reference correction (2026-10-21)

- Source inspection found a protocol error in patch 0131: AArch64 ATS1PR was
  issued as two 32-bit stores. Fairphone `arm-smmu-qcom.c` explicitly requires
  an atomic ATS1 access and uses `arm_smmu_cb_writeq`. The FP6 helper now uses
  one aligned volatile 64-bit store with the existing ordering barriers. The
  harness rejects split ATS writes and verifies one 64-bit request. This does
  not establish the cause of the photographed CBAR external abort.
- Corrected the preceding audit's mistaken Gen7.11 identification. The selected
  FP6 stock tree (`8198534128258bfe7b05bbb5b227affc181aa49b376884c08eae8564fce124e3`)
  explicitly selects `qcom,adreno-gpu-gen8-3-0`. Fairphone's matching
  `adreno_gpu_core_gen8_3_0` uses `gen80300_{gmu.bin,sqe.fw,zap.mbn}` and
  `adreno_gen8_hwsched_gpudev`. Gen7.11 is another supported module profile,
  not the FP6 hardware profile. Use `adreno_gen8_gmu.c` for runtime loading.
- The same stock tree supplies the GPU QTB500 TBU at `0x03de8000/0x1000`,
  covering SIDs `[0,0x400)`. This identifies the SID5 ECATS target; its power,
  halt/resume, ownership and register access remain untested.
- PAS state correction: patch 0127 implements an opted-in ZAP load; the earlier
  phone observation recorded successful INIT_IMAGE, MEM_SETUP and AUTH_AND_RESET.
  `fp6pas=1` alone remains a query; `fp6zap=1` requests the authenticated load.
- CI `39625922013` passed on `2582fe6`. Its locally packaged image
  `/tmp/fp6-smmu-2582fe6/image/fp6-shim-ufsroot-smmu-cbarfix.img` has SHA-256
  `9918c0219c91414234942b761d7c9555cbad76a2df8d477ddab28ec7c20f96f8` and was
  not phone-tested. It predates the atomic ATS fix and is superseded for live
  SMMU testing. It embeds the complete vendor_boot DTB collection (SHA-256
  `16a9e60e...`); subsequent packages should use the verified selected tree
  above, matching prior tested packages. No GMU execution is claimed.

## FP6 SMMU rollback panic containment (2026-10-21)

- Phone observation: the `fp6smmu=2` GMU SID5 ATOS test panicked in rollback.
  The photographed state shows PC `0xfffffe0007ae71c0`, LR
  `0xfffffe0007ae6f64`, FAR `0xfffffe30000e1000`, ESR `0x96000010` (synchronous
  external abort). Symbolication against the matching CI kernel places PC in
  `fp6_smmu_inventory` at the write restoring the selected context bank's CBAR.
  This is strong address-level evidence for the panic site; the earlier reason
  the test entered rollback remains unknown. GMU firmware was never released.
- Patch 0131 now avoids writing CBAR/CBA2R during rollback. It leaves the
  candidate bank configured but disabled (`SCTLR=0`), invalidates the temporary
  stream match, restores the fault route, and intentionally reserves the bank
  and permanent page-table allocation for the rest of that boot. The probe now
  selects CB2 or higher, matching Linux's reservation of CB0/CB1 for GPU
  pagetable switching. The host
  harness verifies that success and each injected setup failure leave no active
  stream match. Normal and ASan/UBSan GPU probe tests pass. This is a source
  change and containment hypothesis only; no rebuilt image or phone result yet.
- Fairphone KGSL/SMMU cross-check (hardware profile corrected above): the current
  `fp6gpu=1`/`fp6pas=1` modes inventory GPUCC and query PAS availability. A
  separate `fp6zap=1` mode implements ZAP authentication, phone-confirmed earlier.
  Linux's QSMMUv500 path allocates CB0/CB1 to GPU SID0/1 and other clients from
  CB2 onward; patch 0131 now respects that rule. Its CBAR/TCR/TTBR/MAIR ordering
  follows `arm_smmu_write_context_bank`, but the probe's fixed SCTLR `0x27` is
  not Linux's complete fault/coherency setup.
- Important limit: patch 0131 triggers CB `ATS1PR`, which checks context-bank
  page translation but does **not** prove the SID5 stream route end to end.
  Fairphone QSMMUv500 resolves SID-specific ATOS through the corresponding TBU
  ECATS path (halt TBU, disable fault/stall handling temporarily, trigger ECATS,
  inspect/clear FSR, restore SCTLR, resume). Thus the test output is now named
  context-bank ATOS, and SID5 routing remains unverified. The next proper route
  test needs exact FP6 TBU mapping/ownership and a bounded ECATS sequence.
- The Tensor progress screenshot describes user-space AIR shader compilation,
  pipeline import and texture setup, with no compositor draw yet. Those are
  meaningful user-space milestones but do not transfer as a percent-complete
  estimate for FP6: this tree has not started GMU firmware execution, SQE/CP,
  GPU submission, or a Metal bridge.
- Tegu USB source review: `shim/tegu/usb.c` is a pre-XNU polled DWC3 EP0 gadget;
  Tegu also carries the transport into XNU via patch 0088 so its console can
  collect later XNU output. Its shim and XNU versions rely on Tegu-specific
  DWC3/eUSB PHY addresses, firmware handoff, DMA RAM and `cpus=1`; they cannot be
  copied to FP6 as-is. The host reader uses USB control requests to retrieve a
  buffered log. An FP6 adaptation may provide a panic-safe path independent of
  the current ECM logger, but must first establish FP6 controller/PHY ownership
  and DMA constraints.

## FP6 SMMU live-test kernel data abort (2026-10-21)

- User reported `kernel data abort` with PC `0xfffffe0007ae71c0`, LR
  `0xfffffe0007ae6f64`. Against the kernel from CI run `39618365269`, PC resolves
  inside `fp6_smmu_inventory`; instruction disassembly places it at the MMIO
  store restoring the candidate context bank's old CBAR during rollback. The
  image manifest for that run records `hardware_tested: false`; matching this
  report to that image is not yet confirmed.
- The rollback had already restored the old SMR, disabled the context bank,
  and restored S2CR before reaching CBAR. FAR and ESR were requested to
  distinguish an access fault from a hardware/external abort and establish the
  exact register address. Do not treat this as a GMU firmware failure: CM3 was
  never released.
- Cross-checking Fairphone Linux `arm_smmu_write_context_bank()` found that
  the probe programmed TCR/TTBR/MAIR before CBA2R/CBAR, unlike Linux's
  CBA2R -> CBAR -> TCR2/TCR -> TTBR -> MAIR -> SCTLR order. Patch 0131 and the
  stage-failure harness were reordered to match Linux. This source correction
  is not yet built or phone-tested and does not, by itself, explain the abort.

## FP6 SMMU fault-route selection fix (2026-10-21)

- The user's boot photo from `fp6smmu=2` shows all visible stream groups have
  `SMR=0`, fault routing, and `S2CR=0x00020000`; SID 0/2/5 have no valid visible
  match, and all 22 context banks read clean. The probe refused before any
  programming because it required the whole S2CR to equal `0x000200ff`.
- Corrected free-group selection to test only `S2CR.TYPE == FAULT`; CBNDX is
  irrelevant for a fault route. Host coverage now models the observed
  `0x00020000` value through successful ATOS mapping and rollback.
- `tests/test_gpu_probe.py` passes normally and under ASan/UBSan.
- CI run `39615067086`, source `67f9abdf09067f7cffa2fe1ef16494dbb937e068`,
  ultimately completed successfully; XNU build passed. Automated image
  packaging was skipped because `FP6_STOCK_DTB_URL` is unset. The previous
  local test image at `/tmp/fp6-run-39615067086-image/fp6-shim-smmu-atos.img`
  used the still-unfixed probe and was not a valid SMMU programming test.
- The corrected source is not yet built by CI or tested on the phone. Next:
  publish the focused patch, confirm its XNU build, package with the matching
  stock DTB, then rerun the SID 5 ATOS check. The GMU remains held in reset;
  no firmware has been loaded or executed.

## FP6 Gen8.3 GMU firmware staging and SMMU inventory draft (2026-10-21)

- The local Fairphone kernel modules tree is the hardware reference. Its
  `adreno_gen8_gmu.c` confirms Gen8 firmware blocks are loaded into ITCM/DTCM
  or backing memory from zero-size preallocation records; HFI and CM3 startup
  are still separate stages. The XNU port does not yet consume the generated
  firmware header or start CM3.
- Added `tools/fp6-gmu-fw.py`, pinned to FairBlobs commit
  `e58a5be8fa0fb6bc5a5f2e29cc01c036ccf75710` and SHA-256
  `6adcbf43b162fb4bdc00154824f44c5f96d82a223cfbe7012d5904098f5bf2fc`. It
  validates the 88,708-byte Gen8.3 GMU image and emits 11 preallocation
  descriptors plus four data blocks into a generated header. The firmware
  itself remains outside Git. `0129-stage-fp6-gen80300-gmu.sh` stages that
  header in FP6 CI builds; it is not wired into a runtime loader yet.
- Repaired `0128-fp6-qsmmu-readonly-inventory.patch` and extended the host
  harness to check that `fp6smmu=1` reads SID 0/2/5 routing and context-bank
  registers without MMIO writes. This models the diagnostic only; the actual
  FP6 SMMU window has not been read by this build or tested on the phone.
- Host GPU probe suite passes, including the new SMMU inventory case; the six
  GMU firmware parser tests pass and the staging shell script is tested against
  the local pinned blob. CI runs `39588975030` and `39589703230` stopped in
  staging: the parser path was wrong, then macOS Bash 3.2 rejected an empty
  array under `set -u`. Run `39590152515` passed staging but found the inventory
  calling a SWEET-only MMIO helper; an FP6-local ordered read helper is now in
  place and host tests pass. A follow-up CI run is pending. No GMU firmware has
  been loaded and no GPU commands have executed.

## FP6 PAS/ZAP retest image (2026-10-21)

- CI run `39583564215` completed the corrected kernel build for commit
  `2c6ab5ee519f433b899616217eb9d74f9a2b57b3`. The kernel checksum verified;
  the matching ADT SHA-256 is
  `50247d49f727ef9b2b588c2522250bed4d3b742d139ed2d994ffe79634823a65`.
  The workflow skipped boot-image packaging because `FP6_STOCK_DTB_URL` is not
  configured, so the matching CI kernel and ADT were packaged locally with the
  verified stock `tree-04.dtb` and minimal init ramdisk.
- Temporary image:
  `/tmp/fp6-zap-39583564215/image/fp6-shim-fp6zap-fixed.img`, SHA-256
  `94036ddf12326342ed7432cbd570aa7aac0ee3048ef0a51ae25f5190a6c97644`.
  It enables `fp6gpu=1 fp6pas=1 fp6zap=1 fp6touch=2 fp6usb=2` and includes the
  mapped-virtual-address cache-clean fix for the prior `phystokv_range` panic.
- User-provided console photo from this image confirms the phone reached all
  three firmware stages: `PAS_INIT_IMAGE fid=0xc2000201`,
  `PAS_MEM_SETUP fid=0xc2000203`, and `PAS_AUTH_AND_RESET fid=0xc2000205` each
  returned `smc=0x0 result=0x0`; the kernel then reported “GPU ZAP authenticated
  and reset; PAS remains active.” This validates the SMC route, metadata and
  image mapping, cache-clean fix, TrustZone authentication, and peripheral
  reset on FP6. The screenshot also shows the touch/HID and framebuffer
  services registering. The log was captured from the screen, not a host pcap.
  GMU CM3 startup, HFI, GPU SMMU configuration and command execution remain
  untested.
- A fresh `fastboot devices` check after the report returned zero devices, so
  no further boot was attempted in this turn.

## FP6 quiet-console package defaults (2026-10-21)

- Updated `tools/fp6-package.py` so every generated FP6 image omits
  `-enable_kprintf_spam` and enables `sweetfb_noconsole=1`,
  `sweet_noconsole=1`, and opts in to `fp6pas=1`. This keeps the normal
  framebuffer free of routine kprintf output after the first GUI swap. The
  PAS code only queries SMC call availability and GPU PAS support; it does not
  load/authenticate firmware or touch GPU registers. The kernel ring and
  USB logger remain enabled; panic output is still allowed to draw, and output
  before the GUI swap may still appear on screen. This is a package-default
  change only; it does not alter the kernel.
- Locally packaged the latest successful FP6 kernel from CI run `39569106154`
  (kernel SHA-256 `601288b0a5ae4ac1af9d870a269673205be1856b75f72f7da48131c809bdf100`),
  reusing that run's ADT and stock DTB. The first quiet image omitted
  `fp6touch=2`; that would skip the live touch-driver start. The package
  default now includes it. A corrected diagnostic image with the framebuffer
  console visible (so `QCOM SCM:` output is visible) is:
  `/tmp/fp6-debug-pas-touch-39569106154/fp6-shim-ufs-root-pas-touch-visible.img`,
  SHA-256 `667423e85a0139acab9203ce824bbc4fbfc5a2ce2b657cd515691fa324765f59`.
  Its arguments include `fp6pas=1 fp6touch=2 fp6usb=2`, and omit
  `-enable_kprintf_spam` and the framebuffer mute args. It uses the same
  latest successful kernel and matching ADT/DTB. Header-v2 contents validated;
  it was temporarily booted once after the user said the phone was ready.
  USB capture decoded 448 packets. The console showed `PAS_IS_SUPPORTED`
  advertised and GPU PAS ID 13 supported=1, followed by the FP6 touch driver
  polling at 1116x2484. The user confirmed touch responds. This proves only
  the read-only PAS query; no firmware load/auth/reset or GPU register access
  occurred. Captures are retained outside Git under `/tmp/fp6-kernel-logs`.
- Earlier quiet image (retained for reference):
  `/tmp/fp6-quiet-local-39569106154/fp6-shim-ufs-root-quiet-pas.img`, SHA-256
  `5798d5592286aebf569f5a45c0a33107bc2a1058dad317adabdc78387755dc7c`.
  It had `fp6pas=1 fp6usb=2`, kprintf spam off, and framebuffer mute enabled;
  the live touch argument was absent.

## Codex Adreno/PAS work merged into main (2026-10-21)

- Merged the uncommitted `fp6-adreno-gen711` working state (Codex): patch
  0118 (FP6 GPUCC inventory, opt-in), its PAS query patch renumbered from
  0119 to **0122** (main already had 0119-0121), and its NOTES, docs and
  host-test changes. The two patches touch only sweet_gpu.c/sweet_ufs.c and
  apply after 0119-0121.
- Fixed before any phone use: the PAS patch called SMC FID 0xC2000101 as
  "is call available", but that is SIP service 0x01 (BOOT) function 0x01,
  `QCOM_SCM_BOOT_SET_ADDR`; the query is SVC_INFO 0x06 / IS_CALL_AVAIL 0x01
  = **0xC2000601** (Fairphone `drivers/firmware/qcom_scm.h:111-147`). The
  host test's expected FID was corrected likewise. PAS_IS_SUPPORTED
  0xC2000207 (PIL 0x02 / 0x07) was already correct. Disassembly of the local
  arm64 object shows `smc #0` with x0=0xC2000601, x1=1, x2=0x02000207, then
  x0=0xC2000207, x2=13. The phone query result above matches the expected
  SMC path.

## FP6 Adreno 810 profile correction (2026-10-21)

- Correction from reinspection of the actual `~/Downloads/vendor_boot.img` DTB
  and the linked LineageOS devicetree: FP6 is `qcom,adreno-gpu-gen8-3-0` with
  Volcano GPUCC. GPU is `0x03d00000/0x40000`, GPUCC is
  `0x03d90000/0x9800`, GMU windows are at `0x03d68000`, `0x0b280000`, and
  `0x03d40000`, GPU IRQ SPI 300, GMU IRQ SPIs 304/305, and a dedicated
  `qcom,qsmmu-v500` GPU SMMU at `0x03da0000`. Volcano's GPU DT `iommus`
  properties give stream IDs 0 (user GPU), 2 (secure GPU) and 5 (GMU), all with
  zero masks; these are not context-bank indices. The TBU range is still broad
  (`0..0x3ff`), while those client tuples provide exact SIDs. Runtime S2CR/CB
  ownership and Gunyah's access policy remain unverified.
- Source revisions inspected: LineageOS devicetrees `lineage-23.2` at
  `f32428ad60a7bf1ad04f9a8a001f27842e65fd79`; Fairphone kernel modules at the
  current local checkout; FairBlobs FP6 firmware at `e58a5be8fa0fb6bc5a5f2e29cc01c036ccf75710`.
  The matching Fairphone KGSL profile in the local kernel modules tree is Gen8.3
  and names `gen80300_gmu.bin`, `gen80300_sqe.fw`, and `gen80300_zap.mbn`. The
  public FairBlobs FP6 firmware tree contains these blobs (88,708 / 84,564 /
  12,088 bytes; SHA-256 `6adcbf43b162fb4bdc00154824f44c5f96d82a223cfbe7012d5904098f5bf2fc`,
  `38fd00147e8b752dd29c53a0badac8f94b1dbd89dc06f5b1c372d3428cd1b906`, and
  `a91c411027746d4c3389a69b66f25d21eb646e89f2de5eed3f698e370f83f26c`). These
  downloaded blobs remain in `/tmp` and are not in Git. The earlier Murena
  Gen7.11 filenames belong to a different/older software profile and are not
  selected by this DT compatible. The signed Zap image requires Qualcomm
  PAS/TrustZone authentication; it is not ordinary firmware copying.
- UniXNU organization inventory via GitHub API found: UniXNU, UniXNU-sheng,
  uefi-sheng, ArmCpu, ArmDTPlatform, ArmVirtPlatform, DarwinBoot, NativeAES,
  NativeAdreno, NativeGeniSpi, NativeHidInput, NativeKeyStoreEvents,
  NativeMetal, NativeMobileDisplay, NativeRamBlock, NativeUfs,
  NativeVirtioBlock, NativeVirtioConsole, AdrenoFirmware, AdrenoPM4, AirNir,
  ArmSmmu4K, NativePrelink, VerifiedRoot, NativeNovatekTouch,
  ShengPreflight, and `.github`. NativeAdreno, PM4, AirNir and the display
  Adreno/PM4 and AirNir paths target Sheng/A740; their board profiles and
  instruction encoders are not FP6 drop-ins. NativeMobileDisplay demonstrates
  a CPU framebuffer-copy service, rather than GPU acceleration. ArmSmmu4K and firmware/HFI parsing are the
  strongest pieces to study for a later port, subject to FP6 geometry and
  protocol validation.
- Local patch `0118` adds an opt-in `fp6gpu=1` read-only inventory of 11 Volcano
  GPUCC branch registers (base/size and offsets corrected to the exact DT and
  `gpucc-volcano.c`). The inventory patch itself has not yet been rebuilt or
  phone-tested after this correction. It maps no GPU-core, GMU, or SMMU windows and performs
  no writes, power/clock requests, DMA, or firmware startup. It is diagnostic
  groundwork only; no acceleration is enabled yet. Host model tests pass both
  normally and with ASan/UBSan (`ASAN_OPTIONS=detect_leaks=0` is needed because
  LeakSanitizer cannot operate under this test runner's ptrace sandbox); RPMh
  and XNU-compile-log helper tests also pass. An AArch64 Clang syntax check
  with lightweight XNU header stubs passed. The patch applies to the accumulated
  GPU source; no full XNU CI build or phone inventory test has run for 0118.
  This work is on `main`; no phone GPU inventory test has run.

## FP6 Qualcomm PAS query (2026-10-21)

- Patch `0122` adds an opt-in `fp6pas=1` QCOM SCM query during early boot
  setup. It asks SCM whether `PAS_IS_SUPPORTED` is advertised, then queries
  PAS peripheral ID 13 (GPU). It does not load Zap, initialize/authenticate a
  PAS image, reset a peripheral, map GPU memory, or touch GPU/GMU/SMMU MMIO.
- The SMC IDs, SIP owner, argument encoding, and PAS query order were checked
  against the cloned Fairphone Qualcomm kernel's `qcom_scm.c` and
  `qcom_scm-smc.c`; the GPU PAS ID and Zap flow were checked in its KGSL
  Adreno loader. XNU's PSCI `smc #0` helper is the only existing local SMC
  precedent; this does not establish that the direct SIP SCM route is accepted
  on FP6 (the vendor kernel also has a QCPE/HAB transport branch).
- Host model tests cover disabled/invalid modes, service-unavailable and SMC
  error paths, and the exact two successful query descriptors. The local
  harness and ASan/UBSan GPU harness pass. CI build 39569106154 included this
  patch; the phone result is recorded above. It is still query-only.

## FP6 Adreno startup and signed ZAP loader draft (2026-10-21)

- User clarified that GPU bring-up must not be attached to UFS initialization.
  Patch 0127 moves the FP6 GPU inventory and PAS query into a dedicated
  `EARLY_BOOT` startup hook in `sweet_gpu.c`; UFS no longer owns those calls.
- Patch 0126 fetches `gen80300_zap.mbn` from FairBlobs commit
  `e58a5be8fa0fb6bc5a5f2e29cc01c036ccf75710`, verifies its SHA-256, validates
  the ELF32/QDSP6 program-header and relocatable-segment layout, then emits
  only the signed-image metadata and segment into a generated header. The
  firmware binary remains out of Git.
- Patch 0127 adds opt-in `fp6zap=1`: check PAS availability/support, write the
  metadata into the second page of the stock 8 KiB no-map Zap carveout, call
  PAS_INIT_IMAGE, copy/zero the relocatable 4 KiB image page, call
  PAS_MEM_SETUP and PAS_AUTH_AND_RESET, and call PAS_SHUTDOWN on failure.
  Successful PAS state remains active. This does not start the GMU, map or
  program the GPU SMMU, or execute GPU commands.
- The staging script passed against the local blob (SHA-256
  `a91c411027746d4c3389a69b66f25d21eb646e89f2de5eed3f698e370f83f26c`),
  producing a 0xfcc-byte Linux-compatible metadata buffer and 0x378-byte
  segment. Host GPU harness and full four-test suite pass, including
  ASan/UBSan; `git diff --check` passes. These changes have not yet had a full
  XNU CI build or a phone test. PAS authentication is therefore not proven.

## FP6 touch, HID services and ring switch (2026-10-21)

- Patches 0115 (SweetHID button/touch services registered on FP6, touch
  geometry from the boot framebuffer), 0116 (ring/silent switch as Telephony
  RingEnable via `sweet_hid_key(4)`, position returned by copyEvent and sent
  to new clients) and 0117 (`bsd/dev/qcom_geni.c/.h` polled GENI FIFO/SPI
  core; `bsd/dev/fp6_touch.c` ESWIN EPH86xx on SE0 SPI mode 3 ~1.9 MHz CS0,
  vendor TLV protocol, X inverted on 1116x2484, GPIO 107 slider to the ring
  switch; `fp6touch=1` read-only probe, `fp6touch=2` live). Hardware facts
  re-checked against Fairphone kernel sources: Volcano TLMM REG_BASE
  0x100000 (GPIO n at 0x0f100000+0x1000n, 168 GPIOs), SE0 pins 0-3 func 1,
  GCC vote 0x52008 bits 18-22, halts 0x23018/0x23008/0x23000/0x23004/0x18004,
  non-DFS RCG 0x18010 with XO in its table, FIFO full-duplex opcode 3.
  The repo's earlier Cliffs TLMM description (179 GPIOs, reserved 56-60) and
  "SPI pins 94-97" are wrong for FP6 and not used by this driver.
- Local arm64 compile (system clang, CI flags via xnu-cc replay) passed for
  the new files and SweetHID.cpp. CI `39554419254` (head `43fdbd7`) build
  job passed; kernel SHA256SUMS verified, symbols present.
- Image (wifimac ADT, console muted, `fp6touch=2`):
  `/tmp/fp6-touch-39554419254/img/fp6-shim-ufs-root-touch.img`, SHA256
  `39175f461e09eeb9dd2f1af9ecf225841cee49f28646f4a9ff8345820ffbf6b0`.
  Temporarily booted 06:23:21 UTC (`fastboot boot` OKAY). Phone result (screen
  photos): SE0 `fw=0x102 proto=1 if_disable=0x1 status=0 hw=0x202029e4/...
  dma=0x1 mclk=0x11 clksel=0`: SPI firmware is loaded but FIFO mode is
  disabled (GSI/GPI DMA only), so `qgeni_fifo_init` refused (err 19).
  Clock bring-up worked: initial vote 0x52008=0x40000900, RCG 0x18010 root
  off (0x80000000, cfg 0x100000) -> rcg 0, cfg 0x100001 (XO); branch 0x18004
  0x80004000 -> 0x4000; 0x23018/0x23008=0x4000, 0x23000/0x23004=0. TLMM:
  gpio0/1 cfg 0x203 (GPIO out high, pull-up), gpio2/3 cfg 0x1 io 0, gpio19
  (CHG) cfg 0x1 pull-down io 1, gpio20 (reset) cfg 0x1 input pull-down io 0
  = controller held in reset, gpio107 (slider) cfg 0 no pull io 0 =
  floating (DT wants pull-up). SweetHID works: `key 0xb/0x2d down (1
  clients)` after `FP6 SLIDER: gpio107=0 -> ringer`. No controller access happened (the check
  precedes any SPI transfer). Stock Volcano DT wires SE0 SPI to GPI DMA
  (`gpi_dma0` @0xa00000, SID 0x576, gpii-mask 0x3e, static-gpii-mask 0x01;
  QUP wrapper SID 0x563), so FIFO-disabled GSI firmware is the leading
  explanation, now confirmed. Chosen direction: a polled GPI DMA path in
  qcom_geni (research in progress).
- Patch 0119 adds a polled GPI DMA (GSI) path to qcom_geni, used when SE
  firmware disables FIFO (as on FP6 SE0): read-only GPII 0 state check
  (refuses unless both channel and event contexts are zero), SMMU stream
  pass-through for SIDs 0x576/0x563 (accepts existing bypass or
  unmatched-stream bypass, else adds a Linux-style S1_TRANS_S2_BYPASS bank),
  16 KiB contiguous DMA (event ring 2 KiB, TX/RX rings 1 KiB, bounce
  buffers), Linux msm_gpi sequence (IRQ-status config, EV ALLOCATE, CH
  ALLOCATE x2, program, START x2) and per transfer CONFIG0+GO+TX DMA / RX DMA
  TREs with EOT polling. The touch driver now also sets GPIO 107 and 19 to
  pull-up inputs and releases reset on GPIO 20 (low 10 ms, high, 300 ms).
  Local arm64 compile passed. CI `39556553401` (head `9cdc23a`) build
  passed; kernel SHA256SUMS verified. Image (wifimac ADT, console muted,
  `fp6touch=2`): `/tmp/fp6-gpi-39556553401/img/fp6-shim-ufs-root-gpi-touch.img`,
  SHA256 `85424b1ece61a39be62d9c97c91089bbf8bb7e884b168c94b0b416cb43f8b54d`,
  temporarily booted 06:43:30 UTC. Result: kernel data abort at PC
  0xfffffe00074f57f0 (LR 0xfffffe00074f5738) = `qgeni_smmu_passthrough+0xe8`,
  the first SMR load of the stream-match scan (SMMU base + 0x800 + 4i); the
  sCR0/IDR0/IDR1 loads before it completed, so the GPII 0 idle check had
  passed. FAR/ESR not captured. Unlike sweet_ufs.c, which reads the same
  SMRs on this phone, the new scan did not cap the IDR0 group count at 128.
- Patch 0120 caps the SMR scan at 128 groups as sweet_ufs.c does and logs
  sCR0/IDR0/IDR1 before scanning (diagnosis is source-based until the next
  boot). Patch 0121 adds `bsd/dev/fp6_keys.c`: read-only polling (20 ms, two
  equal samples) of PMK8550 PON_RT_STS 0x1310 (bit 7 power, bit 6 volume
  down; GEN3 subtype 0x09 checked at 0x1305) and PM7550 GPIO 6 RT_STS
  0x8d10 bit 0 (volume up, active low; used only if EN_CTL bit 7 and
  digital-input mode) through the v7 arbiter observer channel for EE 0
  (core 0x0c400000 APID map +0x2000+4n, cnfg 0x0c42d000 owner +4n, obs
  0x0c440000 +0x20*apid; offsets checked in spmi-pmic-arb.c). The only MMIO
  write is the observer read command; `fp6keys=0` disables. Both compile
  locally.
  CI `39557553973` (`9d9f1de`, before the Codex merge) passed. Image with
  console visible and `fp6touch=2`:
  `/tmp/fp6-keys-39557553973/img/fp6-shim-ufs-root-touch-keys-console.img`,
  SHA256 `7008124cc16249af752d318806fef60efba97df12360f832aa27eaef8ee2abcc`,
  temporarily booted 06:59:58 UTC. Result: same data abort, PC
  0xfffffe00074f5810 (`qgeni_smmu_passthrough`, SMR scan, already capped).
  Panic registers: FAR = SMMU map base + 0x800 (SMR 0, first entry), ESR
  0x96000010 (EL1 data abort, DFSC 0x10 synchronous external abort), sCR0
  0x00230406 (USFCFG set: unmatched streams fault), IDR0 0x4c017e72 (114
  SMRGs), IDR1 0x60000048 (72 banks, 4 KiB pages). The faulting load was
  post-indexed (`ldr w15, [x14], #4`); the preceding sCR0/IDR loads used
  plain base+offset and succeeded. Diagnosis: the apps SMMU is trapped by the
  hypervisor, which cannot emulate write-back loads (no valid instruction
  syndrome) and injects an external abort; sweet_ufs.c's SMR loop compiled
  to plain loads. The 128 cap (0120) was not the cause.
- Patch 0123 makes the rd/wr MMIO accessors in qcom_geni.c, fp6_touch.c and
  fp6_keys.c single inline-asm LDR/STR with a plain base register. Local
  objects contain no write-back loads/stores to MMIO (remaining write-back
  forms are stack pushes, a const-table load and buffer copies). Because
  sCR0.USFCFG=1, the GPI streams need SMR/S2CR entries; whether the
  hypervisor accepts those writes is unknown (readback is checked).
  CI `39559458529` (`a24dc47`, includes the Codex merge) passed. Images
  (console visible, `fp6touch=2`): touch+keys
  `/tmp/fp6-mmio-39559458529/touch-keys/fp6-shim-ufs-root-touch-keys-console.img`
  SHA256 `0c592511eebde58a5fba6afed8728415b73eeeeaf37930b53b83981da381c20c`,
  temporarily booted 07:12:27 UTC. **User reports touch and buttons work**
  (first FP6 input: SE0 SPI through GPI DMA with SMMU stream entries via the
  hypervisor-trapped MMIO, PMIC keys through the v7 SPMI observer channel);
  SpringBoard then crashed (signal/reason not yet reported). Leading
  suspect from SWEET history: patch 0070 (`pid_hibernate`, syscall 435) was
  SWEET-only, so SpringBoard gets SIGSYS when an app leaves the
  foreground; 0070's two guards now include FP6 (source fix, unconfirmed);
  user also reports Settings -> General -> About crashes (as on SWEET:
  PodcastsUI force-unwrap of `URL.volumeTotalCapacity`, diagnosed there, not
  fixed) and apps show black windows (SWEET: e.g. Phone blocked in a sync
  voicemail XPC that needs the modem). 0099's sweet_sample.c guard and new
  patch 0124 enable SWEET's process sampler on FP6, opt-in via
  `sweetsample=Name,...` (output is console/log only); same plus `fp6pas=1`
  `/tmp/fp6-mmio-39559458529/touch-keys-pas/fp6-shim-ufs-root-touch-keys-pas-console.img`
  SHA256 `9fbaab46e356761bf2519b0d7df4738571bc366b338a442386390fb450770957`
  (not booted). The stock DT confirms the Gunyah hypervisor
  (`gunyah_hyp_region@80000000`, trustedvm/oemvm guests). Rails
  (L22B/L9B) and PMIC are still untouched. Work is committed from a separate
  worktree on main because the shared checkout is on Codex's
  `fp6-adreno-gen711` branch.
  The driver does not touch reset, L22B/L9B or PMIC; slider polarity
  (mainline: GPIO 107 high = muted) is unverified.

## FP6 home screen (2026-10-21)

- **User reports the iOS home screen on FP6** after booting
  `fp6-shim-ufs-root-wifimac-console.img` (`5ebfd2d5...`): kernel from CI
  `39550549760` (`b8ad3fe`: 0031/0039/0042/0043/0048/0052/0059 on FP6), ADT
  with the D22AP identity and `/chosen/mac-address-wifi0` (`96baa92`), stock
  DTB, console left visible. Root: the freshly flashed Tegu-built image
  (`fp6-ios-root-tegu.simg` `a1c6f7da...`, raw `574cbad6...`) on `userdata`, per
  the user; its first boots therefore used the D22AP identity.
  Touch/buttons have no FP6 HID driver (no SweetHIDButtons/SweetHIDTouch on
  FP6), so interaction is not established.
- Same kernel/ADT repacked with the default arguments (console muted after the
  first swap: `sweetfb_noconsole=1 sweet_noconsole=1`):
  `/tmp/fp6-fixes-39550549760/img-home/fp6-shim-ufs-root-home.img`, SHA256
  `1a7f40b4e66d03fcb44ec5442c7d6e74ee2a60eabc33d405887e33433cb6f40b`.
  Header-v2 validation passed; not yet booted.
- The Wi-Fi MAC is a fixed stand-in. The stock DTB has no static MAC; ABL's
  runtime FDT `/chosen` has not been inspected. The DTB names both a PCIe
  Kiwi path (`wlan/qca_cld/kiwi_v2`) and `qca6750/wpss.mdt`; the actual WLAN
  part is unconfirmed.

## FP6 userspace stall after early boot (2026-10-21)

- Phone observation (user report, image from CI run `39545845250`): libignition
  at `ignition_level=1` prints "failed to write persona, ignition level
  insufficient" (a skipped stage, as on SWEET) and continues; level 3 fails on
  the missing Preboot volume, as on SWEET. Boot then reaches early boot
  complete: bindfs firmware mount message, MKB init passes, "Could not get
  options entry from the device tree" (no NVRAM node, also on SWEET), a
  bluetoothd/xpcproxy relaunch loop (no hardware, also on SWEET), `logd
  privilege 1002 denied` (0064 log), MobileGestalt AKS/IOKit call returning 0.
  No backboardd activity and no `SWEET SURF` lines.
- Source audit against SWEET's working path found FP6 lacked: the iPhone X
  identity (ADT root `FP6`, chip-id `0x7635`, no security-status or
  `display-scale`; 0059 kept the macOS `hw.machine`/`hw.model`), 0052
  RENAME_SWAP fallback (the fix before SWEET's backboardd milestone), 0031
  `rootrw=1` (passed by the FP6 package but compiled out), 0039 core dumps off,
  and the 0042/0043/0048 exec/crash/tee diagnostics.
- Commit `5e9a9a0` widens those patch guards to FP6; `90f6c55` gives the FP6
  ADT Sweet's D22AP / iPhone10,3 / D22 identity, chip-id `0x8015`, the
  security-status tuple and `display-scale` 3. The `disp0` canvas stays
  1116x2484 because AppleCLCD reports the native size when the panel is taller
  than 2436. `b043585` commits the pending 0041 HFS diagnostic cap for FP6.
  Local arm64 compile was not possible (no Apple clang here); CI is the build
  check.
- ADT-only test image (old kernel from CI `39545845250`, new local ADT with
  `/product`, stock DTB `16a9e60e...`, default UFS-root args):
  `/tmp/fp6-identity-39545845250/fp6-shim-ufs-root-identity.img`, SHA256
  `33e7f7c2624d45864408a374074a841c7bcd0a42a8b890175750bc362cf57420`.
  Header-v2 validation passed; not yet booted. It tests the ADT identity
  without the 0059 `hw.machine`/`hw.model` change or the other kernel fixes.
  A MobileGestalt cache written under the old FP6 identity may need clearing.
- CI run `39550549760` (ersascape/ios-extra, head `b8ad3fe`) passed: build and
  fp6-boot jobs green. Kernel SHA256SUMS verified; the build tree carries the
  FP6 guards in kpi_vfs.c, kern_mib.c, exception.c, kern_exec.c and
  vfs_subr.c, and the kernel contains the exec/CRASH/dirty-root strings.
  Packaged with the D22AP ADT (`dee5539e...`) and stock DTB:
  `/tmp/fp6-fixes-39550549760/img/fp6-shim-ufs-root-fixes.img`, SHA256
  `0129b2855762bf0b0f12c051fdc17ab7c735566880f85a11ec221578033e493f`,
  kernel `b894d3fc...`. Header-v2 validation passed; not yet booted.
- The never-booted Tegu root (`fp6-ios-root-tegu.simg` `a1c6f7da...`, raw
  `574cbad6...`) re-verified against the hashes above; it has no MobileGestalt
  cache and has the migration marker. Tegu's history shows a cache written
  under a wrong identity breaks SpringBoard until a clean root is used, so
  the clean root should first boot with the D22AP ADT. Not flashed.
- Phone observation (user): the fixes image showed a solid Apple logo (backboardd
  presenting; no progress bar, no flicker) and stayed there. Tegu hit the same
  stall: lsd's database seeding waited in MobileGestalt for a Wi-Fi identity
  (it reads `/chosen/mac-address-wifi0` first), so SpringBoard never drew;
  adding that CFData fixed it there. Added a locally administered
  `mac-address-wifi0` (`02:46:50:36:00:01`) to the FP6 ADT. Repacked with
  console text visible (no `sweetfb_noconsole`):
  `/tmp/fp6-fixes-39550549760/img-wifimac/fp6-shim-ufs-root-wifimac-console.img`,
  SHA256 `5ebfd2d58eeeeaaebca1796004190804e2eb9b7398790644e9419b49500851cd`.
  Not yet booted. No logo-to-UI duration is recorded for SWEET or Tegu; SWEET's
  only logo timing is the ~60 min data-migration bar (progress bar visible),
  and Tegu's logo stall did not clear by waiting (boots ended at ~4-6 min).
- Not changed, from review: 0108 with the macOS Edge scheduler leaves P cores
  4–7 mostly idle (E→P migration/steal disallowed; throughput only); 0100
  probe images ignore `ufsrw=1`; 0105 SMMU geometry decode and power-query
  timeout cleanup are latent; 0114 socket-first send can report success while
  ARP holds the packet, hiding the raw fallback; the persistent log flush
  (0047) stays SWEET-only.

## FP6/SWEET launch diagnostics and USB logger (2026-10-21)

- Patch 0111 replaces the kernel logger's routed UDP socket sends with complete
  Ethernet/IPv4/UDP frames addressed to the fixed USB-ECM host. This bypasses
  XNU route and ARP resolution, which were in the previous send path. It waits
  for the ECM data alternate setting, reports a full transmit queue as
  `ENOBUFS`, and keeps the ring cursor unchanged on failure so the chunk is
  retried. A clean replay of patches 0099–0112 applied successfully; the
  resulting `sweet_usb.c` passed syntax compilation against the CI build tree.
  CI run `39537652816` passed for patches 0111–0112; patch 0035 already
  registers the permissive Sandbox policy for FP6.
- Live test of the 0111 image disproved the assumption that the raw sender was
  fixed: USB Ethernet came up and ping worked, but the host captured no UDP
  packets. The phone then reported raw UDP error 55, which is `ENOBUFS` on
  XNU/Darwin. This is consistent with transmit-queue or mbuf-buffer pressure
  while the logger sends its backlog. Patch 0114 adds
  socket-first delivery with the raw frame path as fallback and retries the
  same ring position after a 10 ms queue-drain delay when raw output returns
  `ENOBUFS`. Commit `1788b20` passed CI run `39545845250` (XNU build green).
  Extracted the matching stock DTB from `/home/ersa/Downloads/vendor_boot.img`
  with `unpack_bootimg`; its SHA256 matches the previously verified FP6 DTB.
  Packaged header-v2 UFS-root image
  `/tmp/fp6-usb-log-39545845250/fp6-shim-usb-log-retry.img`, SHA256
  `2e753c95582967f57dcd23090002ec83c333e76729b5fc0f856c6a3eefac490c`.
  `fastboot devices` showed no attached device. The new image has not been
  booted; confirm delivery with a host UDP capture before calling the logger
  fixed.
- Patch 0112 adds `sweet_noconsole=1` as an alias for
  `sweetfb_noconsole=1`. Both mute framebuffer console drawing after the first
  GUI swap; persistent logging and panic drawing are preserved.
- The attempted patch 0113 was redundant: existing patch 0035 already registers
  `sweet_amfi_policy_register()` for SWEET and FP6. CI applied 0035 and then
  failed when 0113 tried to rewrite the same call site. Removed 0113 from the
  series. This registers the permissive policy but does not provide individual
  sandbox profile files or container metadata.
- `tools/fp6-package.py` now puts the README's kernel diagnostics into the
  default FP6 images (`debug=0xc`, serial console, symbols, and kprintf spam),
  starts the FP6 USB logger with `fp6usb=2`, and uses the UFS-root/write,
  launchd, watchdog, and framebuffer arguments used in the previous test
  packages. SWEET-only `sweetnull`/heap-scan/IOKit-trace selectors are not
  treated as active FP6 diagnostics.
- Commit `fe6a8dc` builds successfully in CI run `39539461187`. The CI boot
  packaging job skipped because the stock FP6 DTB is not stored in CI; using
  the existing local `/tmp/fp6-stock.dtb`, the CI kernel and generated ADT
  were packaged and header-v2 contents verified at
  `/tmp/fp6-debug-build-39539461187/ufs-root-debug/fp6-shim-ufs-root-debug.img`.
  SHA-256: `f420d3d25ddab3e013b2159fc62b05b9be1c8506c52e90322f8a764d39805333`.
  The package uses `cpus=8`, `fp6usb=2`, verbose diagnostics, UFS-root/write,
  watchdog, and framebuffer arguments; it has not yet been phone-tested.
- Updated `tools/sweet-root-tweaks.py` to change any launchd stdout/stderr
  override from `/dev/console` to `/dev/null`; the diagnostic-only
  `tools/patch-launchd-plist.py` uses `/dev/null` as well. The current local
  Tegu HFS image was inspected directly: `backboardd` has neither explicit
  path, and no launchd job points either stream to `/dev/console` (two WebKit
  jobs use `/dev/null`). Therefore the old confirmed spawn failure is not
  present in this root image; no rootfs rebuild is needed for that fix.
- Existing SWEET patches already capture a `backboardd` abort: 0043–0044 log
  crash registers/backtrace, 0051/0053 scan writable heap text for exception
  reasons, 0048 tees selected `/dev/null` output, and 0049/0054 trace IOKit
  lookups and opens. These hooks are SWEET-only; the README SWEET profile uses
  their defaults. For the FP6 image, patch 0111 supplies the USB kernel logger
  but the current SWEET-only crash/IOKit hooks are not enabled.
- ADT audit: the local D22AP IPSW tree supplies the 61 usable `/product`
  properties copied by `tools/mkadt.py`; no Apple-format SWEET ADT was found.
  The generated SWEET ADT currently describes all eight CPUs as homogeneous,
  while the SWEET Linux DT describes six efficiency and two performance cores.
  This is a topology metadata gap, not an identified cause of the present
  `backboardd` exception. Qualcomm peripheral nodes require matching XNU
  drivers and should not be copied wholesale from the iPhone tree.

## FP6 watchdog/framebuffer boot-argument package (2026-10-21)

- The earlier USB-log UFS boot image omitted `wdt=-1`,
  `wdt_test=no_user_checkin`, `sweetfb_noconsole=1`, and `sweetfb_hz=30`.
  Repacked the same CI kernel (run `39472658322`, commit
  `698cc43ed79a9f8e3c53af4b436872bd764dfa60`), D22AP-product ADT, and stock
  FP6 DTB. The new arguments also disable the SWEET touch/button drivers and
  retain USB debug. `cpus=8` is retained for FP6's eight-core topology.
- `wdt=-1` is an XNU boot argument; `wdt_test=no_user_checkin` is read by
  watchdogd from the boot arguments. They were already used by the SWEET
  profile; their effect on this FP6 boot is not yet device-verified. This does
  not establish that a physical SoC watchdog has been disabled.
- Image `shim/out/fp6-wdt-fb-39472658322/fp6-shim-ufs-root-wdt-fb.img`, SHA256
  `f2ca0c938d9dc86a9a4dcc01d28e48700e2fcaf71481cf55186d37902be04b5a`.
  Header-v2 package validation passed, including embedded kernel shim and
  stock DTB checks. It has not been booted; the current phone boot was left
  untouched. USB log delivery remains unverified; the host capture was empty.

## FP6 Tegu-style iOS 16 root image (2026-10-21)

- Rebuilt the iOS 20H392 root from the locally extracted OS, SystemOS, and
  AppOS images using a Tegu-style Linux guest copy (`rsync -aH --numeric-ids`).
  `/dev/kvm` is unavailable here, so QEMU used TCG; the OS copy took about 22
  minutes. The earlier host-built image with invalid HFS index/thread records
  remains rejected and must not be flashed.
- Applied `tools/sweet-root-tweaks.py` through Tegu's isolated guest. Readback
  confirmed the Setup skip, launchd crash-policy rename and CommCenter removal,
  migration marker, audio/recorder disables, SpringBoard settings, containers,
  and ownership/mode requirements. The image has no mobileactivationd system
  container yet, so the tweak script warned that it skipped the data ark; FP6
  activation still depends on the ADT `/chosen` security-status properties.
- Tegu's read-only verifier passed for launchd, dyld, SystemVersion, all 44
  shared-cache aliases (matching inode numbers to the cryptex copies), the two
  trampoline libraries, cryptex symlinks, log directories/owners, and the
  system keybag. Linux `fsck.hfsplus -fy` repaired the volume; subsequent
  `-fn` reports only the documented journaled-volume-header minor-repair
  warning (status 8), with catalog, multi-linked-file, hierarchy, extents,
  attributes, and bitmap checks clean. Tegu's temporary local check accepts
  only this specific header-only warning.
- Linux HFS+ still does not set Apple's hard-link chain bit on these links;
  XNU can log/repair that bit at lookup, and patch 0041 only limits repeated
  diagnostics. The Tegu check proves the cache paths share inodes, not that the
  HFS catalog contains Apple's chain-bit metadata. This is the known Linux HFS+
  limitation and was also present in the earlier successful Tegu path.
- Raw image: `research/fp6-rootfs-tegu-20261021/fp6-ios-root-tegu.hfs`, SHA256
  `574cbad62a794a5e8f69cb118a37c0cf915ffe4e66ab1a5a296175c1a216296d`.
  Fastboot sparse image: `research/fp6-rootfs-tegu-20261021/fp6-ios-root-tegu.simg`,
  SHA256 `a1c6f7da616520841c4d56ac2a147940c5c93a0b4406cb1c9ae6832d64338f7c`;
  sparse header is v1, 4 KiB blocks, 4,194,304 blocks. Neither image has been
  flashed or booted on the phone.

## FP6 `mount[3]` boot-task panic (2026-10-20)

- The latest phone photo shows `mount[3] exited -- no exit reason available --
  (signal 0, exit status 1)`. The backtrace resolves in the exact CI kernel
  (`39468219112`, text base `0xfffffe0007004000`) through
  `proc_prepareexit`/`proc_handle_critical_exit`; this is launchd panicking
  because the required `mount -P 1` task returned failure, not a SweetFB or
  SweetSurface fault. Those services registering confirms matching only.
- The known SWEET `mount -P 1` failure was fixed by supplying a writable HFS
  root; the FP6 launchd-fix package omitted `ufsrw=1 rootrw=1`. The exact
  mount subcommand failure is not in this photo, so read/write root is the
  leading source-based diagnosis, not confirmed phone evidence. The packaged
  IPSW-product ADT does contain `/chosen/boot-manifest-hash`, so the earlier
  missing-hash failure is not explained by that ADT omission.
- Repacked the same CI kernel, D22AP-product ADT, and stock DTB, changing only
  boot arguments to add `ufsrw=1 rootrw=1 fp6usb=2 launchd_unsecure_cache=1`
  while retaining `unentitled_ios_sim_launch=1`. Header-v2 package:
  `/tmp/fp6-mount-fix-39468219112/fp6-shim-d22ap-product-ufs-rw-mount-fix.img`,
  SHA256 `af8e26a51deded4c1d14e5996fa73735be85553fea69a7ff8e0e8c4cf2a1f528`.
  Package construction passed; it has not been booted. `ufsrw=1 rootrw=1`
  permits writes to the existing userdata HFS volume.

## FP6 CPU cluster topology (2026-10-20)

- Source review confirms the Volcano DTS uses MPIDRs `0x000` through `0x700`,
  with efficiency CPUs 0–3 and performance CPUs 4–7 arranged as 4/3/1 clusters.
  The generated ADT preserved those MPIDRs and cluster IDs, but set every
  `cluster-type` to integer 0.
- XNU's parser in patch 0099 recognizes ASCII `E`/`P` values for those types.
  Updated `tools/mkadt.py` to emit `E` for CPUs 0–3 and `P` for CPUs 4–7. This
  corrects the topology metadata. Patch 0108 now defines `__ARM_AMP__` in the
  FP6 header so XNU builds its AMP/Edge scheduler and forms E/P scheduling sets.
  With `HAS_CLUSTER` unset, the 4/3/1 physical layout is represented to the
  scheduler as one E set (CPUs 0–3) and one P set (CPUs 4–7).
- The ADT was generated locally; CI build and phone validation are pending.
  User previously reported eight CPUs up, but did not provide the startup log
  that would verify each per-core PSCI and IPI message. Scheduling on P cores
  and a measured performance improvement remain unverified.

## FP6 boot log repetition (2026-10-20)

- The user's latest FP6 observation is only AKS calls from `backboardd`; there
  is no confirmation yet for other AKS clients, SpringBoard, or UI startup.
  The separate MediaTek-device screenshot is not FP6 evidence. AKS is the
  AppleKeyStore interface; this tree already provides a built-in no-passcode
  compatibility implementation without SEP-backed protection. `backboardd`
  reaching it indicates the request path is present, but does not identify
  whether the returned state is sufficient for display startup.
- Repeated HFS hardlink messages and daemon-spawn output were seen earlier.
  HFS patch 0041's limiter only caps diagnostic output and does not repair
  catalog metadata. The user asked to defer that cap for now, so the FP6 guard
  is removed from patch 0041 for the next build; SWEET's existing cap remains.

## FP6 SWEET userspace-enablement patch audit (2026-10-20)

- Patch 0035 registers `sweet_amfi_policy_register()` for SWEET and FP6. A
  later local replay gave a conflicting result, but the CI failure log confirms
  patch 0035 is applied before the redundant 0113 call-site rewrite. The
  permissive stand-in does not supply individual sandbox profile files or
  container metadata that some services may request.
- The FP6 `MASTER.arm64.fp6` config introduced by patch 0099 already omits
  `config_ext_resolver`, matching the effective SWEET configuration from
  patch 0057. Patch 0108 enables the AMP scheduler. Its CI build passed; phone
  testing is pending. The FP6 HFS diagnostic limiter was deferred for that
  scheduler build, then re-enabled in the follow-up HFS patch comparison below.
- Patch 0108 enables the AMP scheduler. Its CI build passed; phone testing is
  pending. The FP6 HFS diagnostic limiter was deferred for that scheduler
  build, then re-enabled in the follow-up HFS patch comparison below.

## D22AP product metadata recovery and FP6 boot package (2026-10-20)

- Located the iPhone X iOS 16.7.16 IPSW locally and extracted its D22AP device
  tree to the ignored `research/ipsw-x/` directory. The FP6 ADT generator copied
  all 61 non-placeholder `/product` properties; a parsed comparison confirmed
  they match the IPSW tree exactly and syscfg placeholders are excluded.
- Packaged `/tmp/fp6-ipsw-product-boot/fp6-shim-d22ap-product-ufs-root.img`
  with the existing AMP kernel from CI run 39461451126 (source commit
  `590b4bc05bfa574f4bfdb3fa4f101308c5ce5548`), stock FP6 DTB and the prior
  UFS-root command line. Header v2 packaging and embedded kernel/DTB/payload
  checks passed. Image SHA-256:
  `2cb4f1b8cbe2bd46a6771c648897931d0efc0e8b462a4dcb644c94e3878c0579`.
- No fastboot device was connected when checked, so this image has not been
  booted. The GitHub workflow still lacks the local D22AP ADT input; its normal
  generated ADT omits `/product` until that input is provisioned there.
- The current FP6 userdata root image is not available locally. The IPSW is
  present, but this work only extracted its device tree; it did not inspect the
  phone's userdata or validate its current HFS volume.

## FP6 HFS patch comparison and root image status (2026-10-20)

- Shallow-cloned SWEET at `11da58b` for read-only comparison. FP6 already has
  the relevant HFS support: staged Apple OSS HFS (0026), unsealed-root handling
  (0029), read/write root support (0031), rename-swap (0052), and UFS performance
  work (0069). FP6's 0106 enables `SWEET_HFS` in its own master config; SWEET's
  generic `config/MASTER` change is therefore not needed.
- SWEET's 0041 patch already limits repeated hardlink-catalog diagnostics to
  eight messages. Re-enabled that behavior for FP6 as well, per the user's new
  request to bring in SWEET's HFS patches. It suppresses repeated log output;
  it does not repair catalog records or filesystem corruption.
- No FP6 root image or extracted OS/SystemOS/AppOS images are present in the
  available local paths, so the current userdata HFS volume could not be
  inspected here. Earlier notes record a pre-boot `fsck.hfsplus -fy` as OK;
  that is not a check of the volume after the phone mounted it read-write.
- The user's Nord 2 report is separate: Apple userland and eight CPUs were
  already running there before the MediaTek framebuffer handoff was added. It
  does not establish the integrity of FP6's root volume.

## FP6 IOSurface and framebuffer enablement (2026-10-20)

- Patch 0109 enables the existing `SweetSurface` and `SweetFramebuffer`
  implementations for the FP6 build and adds the FP6 IOKit personalities for
  `IOCoreSurfaceRoot` and `AppleCLCD`. The FP6 ADT already publishes
  `/arm-io/disp0` as `sweet,display`; the shim supplies `PE_current_console`
  video fields from the bootloader FDT's `0xe3940000` framebuffer node.
- Replayed syntax compilation for `SweetSurface.cpp`, `SweetFramebuffer.cpp`,
  and `KernelConfigTables.cpp` against the prior CI build tree with clang 23;
  all three passed. The repository helper's pinned Swift clang path is absent
  on this host, so the replay used the installed clang. Full CI build and phone
  presentation test are pending.
- The image packaged before patch 0109 does not contain this driver enablement.
  The new code only copies CPU-rendered IOSurface frames to the framebuffer ABL
  left active; no FP6 DSI/panel initialization is added here.
- CI initially rejected 0109 because its context-free hunks used stale line
  numbers after patches 0101 and 0107. Added surrounding context in commit
  `3a500436979d8c3debbe07ed8d58f5ccfc5f55de`; patch application and the full
  XNU build then passed in Actions run `39468219112` (5m42s).
- Packaged that run's kernel with the verified stock FP6 DTB and an FP6 ADT
  carrying all 61 non-placeholder `/product` properties from the local D22AP
  IPSW ADT. Image:
  `/tmp/fp6-display-build-39468219112/fp6-shim-d22ap-product-ufs-root.img`,
  SHA-256 `84aad4e03bc396e684dcd45219200a744745dd1681219a80c71d2276c7c4865a`.
  Header-v2 unpack/metadata checks passed. CI's automatic phone-image packaging
  skipped because `FP6_STOCK_DTB_URL` is unset; this local package uses the
  verified DTB. It has not been booted on the phone.

## FP6 watchdogd service discovery (2026-10-20)

- The FP6 DT/ADT does not expose a verified APSS/MSM watchdog resource, so do
  not map or write Qualcomm watchdog MMIO. The user's ADSP/WPSS `wdog` IRQs
  belong to those remote processors and are unrelated to the AP watchdog.
- Added patch `0107-fp6-dummy-iowatchdog.patch`: it compiles the existing
  watchdogd-facing `IOWatchdog` user-client for FP6 and registers its IOKit
  personality in the FP6 kernel table. It preserves the known dummy behavior,
  including the `IOPMUPrimary` marker, but explicitly logs that hardware
  watchdog control is disabled. This is an interim service-discovery fix, not
  a hardware watchdog driver.
- First CI attempt `39455499092` exposed context failures in patch 0107 before
  compilation; the new patch had guessed source line positions from earlier
  hunks. Reworked the hunks to include surrounding exact context. The corrected
  commit `9c3c2f7b49c908840fc46108c6db12628e27e779` passed CI run
  `39456160901` (XNU build and FP6 packaging job). CI skipped image upload
  because `FP6_STOCK_DTB_URL` is unset. The matching kernel and ADT were
  downloaded locally and their SHA256 values verified; the known matching
  stock DTB was reused (`16a9e60e441772b5cf491a6b51dbe4829f5895fa284bcfa342623bc5b2287dc5`).
- Locally packaged and header-v2 validated a UFS-root image preserving the
  prior iOS userspace boot arguments:
  `/tmp/fp6-watchdog-39456160901/ufs-root/fp6-shim-ufs-root-watchdog.img`,
  SHA256 `e31d60c0b1323f70829a3aab41ad31ad16a2dc3d8bf230a8833ecfcda61e2680`.
  It embeds kernel SHA256
  `e2c08fa79086456dfc5d24bf4c519895a1246237f7f0e50a92812fe26db40fbc` and ADT
  SHA256 `9f6030208a39700f508f34fd01c6ec5f95376fa1efb25dbdeeeb202e9322496d`.
  The command line retains `rd=ufsroot0 ufsrw=1 fp6usb=2
  unentitled_ios_sim_launch=1 launchd_unsecure_cache=1`. Header-v2 checksum,
  unpacked payload and embedded DTB checks pass. This is package validation;
  the new dummy watchdog personality has not yet been observed on the phone.

## FP6 unsealed HFS root authentication (2026-10-20)

- The user reports that the HFS root mounted, then XNU panicked with
  `rootvp not authenticated after mounting` at `bsd_init.c:947`. This advances
  past the prior journal-write failure; it is the sealed-root authentication
  check, not evidence of an HFS mount failure.
- The existing patch 0029 already permits an unauthenticated HFS root on the
  unsigned SWEET development boot. Extended that original patch's guard to
  include FP6, where the unsigned shim boot also has no Image4 trust chain and
  the development HFS root is unsealed. It now reports the auth error and
  continues through this check. This does not authenticate the volume or prove
  later userspace startup.
- A follow-on patch 0107 failed in CI because it targeted `bsd_init.c` after
  prior patch edits shifted the context. Removed it and folded the same one-line
  board guard into patch 0029, which introduces this block early in the series.
  Commit `11e3311dec6aebdcdf40f167c05316fc29601169` passed CI run
  `39444642284` (both XNU build and FP6 boot job). The workflow's generic boot
  image was skipped because `FP6_STOCK_DTB_URL` is unset.
- The intended next test image should retain `rd=ufsroot0 ufsrw=1` to allow the
  journal/root writes required by this image, and USB diagnostics. No device
  action has been run from this workspace. Locally packaged and header-v2
  validated the matching CI kernel and ADT with the verified local stock DTB:
  `/tmp/fp6-unsealed-394446/ufs-root/fp6-shim-ufs-root-rw.img`, 23,396,352
  bytes, SHA256 `e0143993d89b656cdb7094bc323d57ce32941c59c7e8b5f3bab6f2f8e0596bee`.
  Kernel SHA256 `e9568a5aa790b88c2a773483e4717d7c1ba307d91ba79f7a32c62b08e7c80750`,
  ADT SHA256 `5f273d7248d288e77f0cde2cfd118acd39f5008502e8f8b4d0db52dfee3a4a84`,
  stock DTB SHA256 `16a9e60e441772b5cf491a6b51dbe4829f5895fa284bcfa342623bc5b2287dc5`.
  Command line is `debug=0xc serial=3 cpus=8 keepsyms=1 -noprogress rd=ufsroot0
  ufsrw=1 fp6usb=2`. This opts in to writes to userdata for the HFS journal;
  The user boot-tested it and confirmed root authentication was passed far
  enough to reach launchd; launchd then failed with the wrong-platform reason
  below.

## FP6 launchd platform rejection (2026-10-20)

- On the first `fp6-shim-ufs-root-rw.img` test, the user reports that root mount
  progressed to launchd, then panicked:
  `unexpected SIGKILL of launchd (CS_KILLED) with reason namespace 9 code 0xe`.
  XNU `bsd/sys/reason.h` maps namespace 9 to `OS_REASON_EXEC`; code 14 (`0xe`)
  is `EXEC_EXIT_REASON_WRONG_PLATFORM`. This is the macOS-targeted kernel
  rejecting the iOS platform binary, not a code-signature validation failure.
- Reused the DEVELOPMENT boot argument
  `unentitled_ios_sim_launch=1` from the existing SWEET iOS userspace bring-up
  and locally repackaged the same CI kernel/ADT/stock DTB. New image:
  `/tmp/fp6-unentitled-394446/ufs-root/fp6-shim-ufs-root-rw-unentitled.img`,
  SHA256 `ae4b86c91208e56a28d9230a80b6262f6a824431b41ff25d74e2daafe0628b82`.
  It retains `rd=ufsroot0 ufsrw=1 fp6usb=2`; header-v2 packaging completed.
  This development bypass has not yet been tested on the phone.

## FP6 boot-task platform classification (2026-10-20)

- The user booted the unentitled image and reports a new panic:
  `boot task is not a platform binary /sbin/fsck`. The iOS platform rejection
  was bypassed and launchd advanced to its boot-task sequence.
- Source inspection found patch 0035 registers the built-in AMFI MAC policy
  from `bsd_init.c` only under `ARM64_BOARD_CONFIG_SWEET`. Patch 0099 compiles
  the AMFI implementation for FP6, but does not register its MAC policy there.
  As a result, its `vnode_check_signature` hook never marks root-filesystem
  binaries `CS_PLATFORM_BINARY`; the boot-task check rejects `/sbin/fsck`.
- Extended patch 0035's policy-registration guard to include FP6. This is the
  targeted source fix. Commit `8c423bf0bd8917e0a49787eac2b40bfb5385625f`
  passed CI run `39447341232` (XNU build and FP6 boot job).
- `launchd_unsecure_cache=1` is also included, as in the known-good SWEET
  userspace boot args; it lets launchd use its job cache without AMFI's
  trust-cache service. Packaged and header-v2 validated the matching kernel and
  ADT plus verified stock DTB as
  `/tmp/fp6-platform-394473/ufs-root/fp6-shim-ufs-root-amfi.img`, SHA256
  `34ac69fbdef9e3d32d4d0dbb6dc0b28ba4264590a1b71dca026a4aa347509c0a`.
  Kernel SHA256 `38c525fe8753ee2a456ad684bd38264d70e582846a12e17bc04d30d500bc3cb4`,
  ADT SHA256 `f228d71be97a8f6525819282745dd92d1ef7fecbd26a86aaaa6c4d8f8f46b35b`.
  Command line retains UFS writes and USB diagnostics and adds both
  `unentitled_ios_sim_launch=1 launchd_unsecure_cache=1`. Phone validation is
  pending.

## FP6 MKB/keybag initialization (2026-10-20)

- After the AMFI/platform image, the user reports `hfs: set hardlink bit` lines,
  then a fatal keybag error during `MKB_INIT`, followed by
  `Halt/Restart Timed Out @IOPlatformExpert.cpp`. HFS's link-chain repair is
  informational here; the fatal MKB init is the active blocker. The restart
  timeout is secondary: this FP6 bring-up does not yet provide a working
  platform restart implementation.
- Source audit found the existing built-in `AppleKeyStore`/libaks test service
  is compiled and registered only for SWEET. FP6 therefore has no service to
  satisfy keybagd's `aks_get_system` path. The ADT builder already sets
  `/defaults/no-effaceable-storage`, and `mkiosroot.sh` adds the plain system
  keybag plist; those are the established SWEET keybag prerequisites.
- Extending the built-in no-passcode AppleKeyStore service and IOKit match entry
  to FP6. This is a development stub, not SEP-backed keybag security. CI and
  phone validation are pending.
- First CI run `39449649400` failed before compilation because the modified
  patch 0099 hunk count was short by one line (`corrupt patch at line 696`).
  Corrected its hunk header; retry pending.

Last updated 2026-10-20 after adding the FP6 ADT profile. Read [HANDOFF.md](HANDOFF.md) for how to
continue and [AGENTS.md](AGENTS.md) for the rules. The per-step history (images,
hashes, CI runs, raw numbers) is [docs/GPU_LOG.md](docs/GPU_LOG.md); the hardware and
mainline reference is [docs/GPU_GMU_BOOT.md](docs/GPU_GMU_BOOT.md); the per-patch
design is [docs/GPU_CX_EXPERIMENT.md](docs/GPU_CX_EXPERIMENT.md).

## FP6 panic from probe image (2026-10-20)

- User tested image `fp6-shim-touch-ufs-probe.img` from CI run 39423526775, SHA256
  `f5abf0c8697aebef950f1d1fa6d997d6eae1d3a770caacd3b3377b0d26928198`. The phone
  displayed a kernel data abort. Photo state: PC `0xfffffe0007948c14`, LR
  `0xfffffe000793efc4`, ESR `0x96000005` (translation fault, level 1), FAR zero.
- Symbolication against that run's exact `kernel.development.fp6` resolves PC to
  `IOUserResources::resources()` and LR to `IODTMapInterruptsSharing`. This occurs
  during IOKit device-tree interrupt mapping, before the optional UFS/GPIO/touch
  probes in `IOKitBSDInit` run; those probes are not implicated by this trace.
- Source inspection found FP6's generated GIC node had an `AAPL,phandle` and was
  referenced by SPI0/TLMM interrupt-parent properties, but omitted `#interrupt-cells`.
  XNU only indexes interrupt-controller phandles that provide that property, so
  interrupt-parent resolution can return null and fault at address zero. Added
  `#interrupt-cells = 3` to the FP6 GIC profile. The corrected ADT serializes and
  dumps that property; a rebuilt image and phone retest are still pending. This is
  a source-based diagnosis until the corrected build reaches the same boot stage.

## FP6 root panic and USB debug path (2026-10-20)

- A second phone photo's backtrace was symbolicated against the exact kernel
  from CI run 39423526775. `IOFindBSDRoot` reaches its explicit panic branch:
  `QCOM UFS root %s unavailable: %d`; the visible panic-stack `Assert` frame is
  secondary. This identifies the failure as UFS root selection. The photo is
  cropped before the formatted error number, so the specific UFS init/GPT error
  remains unknown. This differs from the earlier GIC interrupt-cell panic.
- Source inspection found the SWEET DWC3 ECM gadget and UDP log sender already
  exist, but their controller power/clock probe uses SWEET-only GCC offsets.
  Patch 0101 adds an opt-in FP6 entry (`fp6usb=1` for DWC3 handoff diagnostics,
  `fp6usb=2` to start the ECM gadget and UDP console log at
  `192.168.7.1:5140`). The FP6 path does not read or write SWEET GCC offsets or
  change SMMU registers. USB DMA/IOMMU operation is not yet measured.
- Patch 0101 also hooks the existing 4 MiB in-memory console ring for FP6 from
  the first serial-console output, before UFS root setup can panic. This gives
  the USB log sender access to root-selection diagnostics. A separate USB
  debug boot image uses `fp6usb=2`; the ordinary RAM-disk image keeps USB
  disabled. Both use `debug=0xc keepsyms=1` for runtime diagnostics.
- CI run 39427603634 confirmed the patch series applied and the FP6 ADT
  generated, but the compile failed in seven existing `DEBUG`-profile units
  (DTrace `MUTEX_HELD`, ARM `bad_page_cnt`, scheduler `max_unsafe_rt_quanta`,
  and VM `uple_create_btref`). No errors were reported from the USB changes.
  The workflow default is restored to `DEVELOPMENT`, which has built previously;
  the diagnostic boot flags and USB debug image remain enabled.
- CI run 39428369953 passed for commit `207b1d8f3ee632c3cc3c3404007230752473ca0d`.
  It built `kernel.development.fp6` (SHA256
  `ea460a064820ac507e202e82ab26c1ba87d3174d2cd3b948a0662dbc82e1336e`) and the
  corrected FP6 ADT (SHA256
  `cc7891f4b863eaea02343c5624e4f9249010e6010641f03149ad23d9775be3fa`). The
  kernel compiled with `DEVELOPMENT`; runtime debug args are enabled. CI's boot
  packaging step skipped because `FP6_STOCK_DTB_URL` is unset.
- Packaged `/tmp/fp6-usb-394283/usb-debug/fp6-shim-usb-debug.img` locally using
  that run's kernel and ADT plus the existing stock DTB (SHA256
  `16a9e60e441772b5cf491a6b51dbe4829f5895fa284bcfa342623bc5b2287dc5`). The
  header-v2 unpack check verified payload, shim and embedded DTB. Image SHA256
  is `81de2706d9094cc9f539a45fcaae60ffae2e346702d748c408319db18d3d7eb5`; boot
  args are `debug=0xc serial=3 cpus=8 keepsyms=1 -noprogress rd=md0 fp6usb=2`.
  `hardware_tested` is false: USB enumeration, DMA and log delivery have not
  been observed on the phone. The host can listen with
  `tools/sweet-usbnet.sh /tmp/fp6-usb-394283/usb-debug/fp6-usb.log`.

- The user subsequently confirmed that the SWEET USB gadget appeared on the
  host. Packaged a second image from the same CI kernel/ADT and local stock DTB
  with `rd=ufsroot0 fp6usb=2`, so the existing UDP log sender starts before
  UFS root selection. Header-v2 validation confirmed the image payload, shim
  and embedded DTB. Image:
  `/tmp/fp6-ufs-usb-debug/fp6-shim-ufs-usb-debug.img`, 22,900,736 bytes,
  SHA256 `f0a8cadcd3e717fc819605db518dbfcd0e8e77dcbb356ec5719ebf8565366e05`.
  It has not been booted. The UFS initializer defaults to read-only without
  `ufsrw`; it does not flash or modify userdata. No UFS panic log has been
  captured yet, so the numeric initializer error and failing stage remain
  unknown. `fastboot devices` returned no device at packaging time.
- The user ran the host logger with the UFS-root image: the USB Ethernet
  interface appeared, but no UDP log arrived. Likely limitation: the UFS-root
  panic occurs before the background log thread gets a chance to transmit; this
  is not proof of the underlying UFS fault. Packaged a read-only UFS probe
  image that continues into the known RAM-disk init, allowing the UDP logger to
  stay alive after the same UFS initialization path. Image:
  `/tmp/fp6-ufs-probe-usb-debug/fp6-shim-ufs-probe-usb-debug.img`,
  22,917,120 bytes, SHA256
  `1a6831822a695c88e3537b48a71ec7c3a176bdd150d3ffc587153743e2764e8f`.
  Header-v2 payload/shim/DTB validation passed. It has not been booted; this is
  a diagnostic image, not a UFS-root fix.
- The user clarified that the probe logs are not files on `md0`; correct. The
  intended destination is the host-side UDP capture, which remained empty.
  The latest panic photo confirms `EIO` (errno 5), but does not distinguish
  request-list takeover from a failed SCSI completion. Patch 0102 records the
  failing UFS stage and command/status detail and adds them to the panic text,
  so the next UFS-root attempt can identify the underlying failure without a
  working UDP stream. This is diagnostic instrumentation, not yet an UFS fix;
  it still needs a CI build and phone boot.
- Patch 0102 CI run `39431367035` succeeded on commit
  `cd38bdead498c0dd7e687aa169490ad723f781a5`. Kernel SHA256:
  `cc1462c718fa2c8280c8426b0cca4eb87cac2a35a01a74437ac5558b003df334`;
  matching FP6 ADT SHA256: `2a9500cfffd003771621b6ea0afbea573f3e43eabff748f2777c2032b49b76ff`.
  CI boot packaging skipped because `FP6_STOCK_DTB_URL` is unset. Locally
  packaged and header-v2 validated a temporary UFS-root image using those
  artifacts and local stock DTB:
  `/tmp/fp6-ufs-stage-394313/fp6-shim-ufs-stage-debug.img`, 22,900,736 bytes,
  SHA256 `3b9100a82b7576f8f9ebf6d4c7ea66593e9ce0cf3e88f3fcfed383d5e37825c5`.
  Command line includes `rd=ufsroot0 fp6usb=2`. The user booted it and reported
  `SCSI completion detail 0x2102` and panicked task pointer
  `0xfffffe1b4109ec10`.
- The reported `0x2102` detail decodes to response UPIU `0x21` and SCSI status
  `0x02` (CHECK CONDITION); OCS is zero and the command was TEST UNIT READY.
  Because the reported stage is still `SCSI completion` on the 0103 image, its
  earlier guard also saw nonzero response byte `resp[6]`, which the packed
  detail omits. The UFS transport completed, but the response byte and sense
  values remain unknown. The panicked-task pointer is not a fault diagnosis.
  Linux's UFS definitions confirm that sense data is embedded in the response
  UPIU, so a separate REQUEST SENSE command is unnecessary.
- Patch 0103 decodes the embedded sense key/ASC/ASCQ and reports them in the
  panic detail. It retries TEST UNIT READY for up to 3 seconds only for UNIT
  ATTENTION or NOT READY / becoming ready; other SCSI errors remain failures.
  CI run `39433706325` built successfully on commit
  `be6b8d176a83426b12697bc0c0a27d8fc4374744`. Packaged and header-v2 unpack
  validated `/tmp/fp6-sense-394337/ufs-root/fp6-shim-ufs-sense-debug.img`,
  SHA256 `1a55b0261c102fff887dfb9fd33c97d0c4705a9d59b56e054c0bf7d5fab6cf55`.
  It uses `rd=ufsroot0 fp6usb=2`, is read-only with respect to UFS by default,
  and was subsequently booted; it reproduced the SCSI completion panic below.
- The user then booted the 0103 image and still saw
  `ufsroot0 unavailable 5 at SCSI completion detail 0x2102`. The 0103 kernel
  binary contains the new check-condition path, so the reported stage means its
  earlier completion guard rejected a nonzero response byte (`resp[6]`) before
  sense decoding. The packed detail retains UPIU `0x21` and status `0x02` but
  omits that response byte. Linux's completion path consumes SCSI status from a
  response UPIU and copies the embedded sense for CHECK CONDITION; patch 0104
  now follows that flow and reports both response and sense. Exact values still
  await phone retest.
- Research against the local stock FP6 DTB found its UFS host node at
  `0x1d84000`, using two lanes, the Qualcomm UFS PHY, ICE, MCQ, and an SMMU
  stream (`iommus` stream ID `0x60`) with `qcom,iommu-dma = "fastmap"`. It also
  sets `qcom,broken-ahit-wa`. Linux's QCOM driver disables the auto-hibernation
  idle timer while commands are active on that quirk path; the current XNU
  handoff driver does not. This is a platform-confirmed candidate to address,
  though it does not by itself explain the TUR CHECK CONDITION. The existing
  TUR has no PRDT, so its completion has not validated data-buffer DMA through
  the SMMU; actual GPT/data reads remain untested.
- The QCOM Linux host also owns PHY initialization, regulators/clocks, link
  startup, device-init queries, and recovery. XNU currently assumes ABL leaves
  those initialized and takes over only the UTRL. Since TUR returns a UFS
  response with OCS zero, the live link and a response DMA work at least once;
  this does not validate post-handoff power-state handling or data DMA. No
  Apple-specific iPhone UFS host source was found in Apple's public XNU tree.
- Patch 0104 CI run `39435664153` succeeded on commit
  `0ff825a8f143aff1926e8071342ccba708057ad3`. Locally packaged and header-v2
  validated `/tmp/fp6-ufs-audit-394356/ufs-root/fp6-shim-ufs-response-debug.img`,
  SHA256 `6a61741e1c8a1853a6362f5ac7b2258ab65e91be869d4441612b42045e7e154b`.
  It uses `rd=ufsroot0 fp6usb=2`; it has not yet been booted. CI's own boot
  packaging was skipped because `FP6_STOCK_DTB_URL` is unset.
- Patch 0105 implements the FP6 UFS/SoC handoff basics using NativeUfs and the
  cloned SM7635 Linux sources: disable/restore the DT-confirmed broken AHIT
  timer around each completed transfer; read `bCurrentPowerMode`, wake a
  non-active device with START STOP UNIT on WLUN `0xD0`, then retry TUR for a
  bounded 3 seconds; decode fixed and descriptor sense; inspect FP6 SMMU stream
  `0x60` and preserve its live mapping, or configure only that stream through a
  checked Linux Qualcomm pass-through context when no mapping exists. The FP6
  ADT now carries the stock SMMU range `0x15000000..0x150fffff` and stream ID.
  Patch application and ADT generation were checked locally. The local XNU
  compile could not run because this Linux workspace lacks the Xcode kernel SDK
  clang expects; CI build and phone validation are pending. No device was
  touched, and this patch has not yet been committed.

## FP6 hardware bringup and pthread/gPanicBase fixes (2026-10-20)

- On-device observation with packaged header v2 boot image (containing stock DTB):
  ABL booted successfully into shim, simple-framebuffer splash activated at 0xe3940000 (1116x2484).
  XNU initialized console, IOKit matched platform and boot CPU ("1 of 1 CPUs initialized"),
  entered BSD, and halted with:
  `panic pthread kernel extension not loaded pthread_shims.c:318`.
  Also observed:
  `debug_log_init: Error!! gPanicBase is still not initialized` and
  `Serial requested, consistent debug disabled or debug boot arg not present`.
- Root causes:
  1. Built-in libpthread was guarded by `CURRENT_MACHINE_CONFIG == SWEET` and `ARM64_BOARD_CONFIG_SWEET`.
     `sweet_pthread_register` was never compiled or registered during early boot on FP6.
  2. `gPanicBase` was uninitialized because no `pram` node exists in the bootstrap ADT, causing
     `check_for_panic_log` to return early.
  3. `kdp_udp.c` fell back to serial KDP warning because `PE_consistent_debug_enabled()` returned false.
- Fixes staged in patch 0099:
  1. Enabled `sweet_libpthread` and `sweet_hfs` for `FP6` in `bsd/conf/Makefile.template`,
     `bsd/sys/pthread_internal.h`, `bsd/pthread/sweet_pthread_*.c`, `bsd/kern/sweet_amfi.c`,
     and `iokit/Kernel/IOService.cpp`.
  2. In `pexpert/arm/pe_init.c`, provided a 256 KiB static panic buffer fallback when `pram` is absent,
     initializing `gPanicBase` and `panic_info` cleanly.
  3. In `pexpert/arm/pe_consistent_debug.c`, provided a static debug registry fallback for FP6, and in
     `osfmk/kdp/kdp_udp.c`, bypassed serial KDP when serial is not explicitly requested.
  4. Registered `QcomPlatformExpert` and `QcomCPU` classes in `SweetPlatformExpert.cpp` and `SweetCPU.cpp`
     and added corresponding entries in `KernelConfigTables.cpp`.
  5. Verified patch 0099 applies with zero errors against the baseline.

## FP6 shim packaging (2026-10-20)

- Patch audit: Phoenix edits to 0016 broke later patch contexts. Restored 0016
  and placed board integration in 0099. A clean xnu-8796.141.3 replay applied
  all 99 local patches and four selected Ventura harness patches (103/103).
- Added explicit FP6/Phoenix MASTER configs and FP6 header export; FP6 shares
  portable crypto/RNG and architecture CPU/GIC code with a one-CPU limit.
  Sweet hardware driver registration remains disabled for FP6. These source
  changes await full CI compilation and hardware validation.
- Build preparation now selects the four applicable upstream patches, aborts
  on every patch failure, stages portable dependencies for FP6/Phoenix and
  defaults the workflow to FP6. Different targets have separate concurrency.

- Inspected user-selected successful CI run `39371823683` at `4e7fdf0`.
  Artifact `12242266868` contains `kernel.development.sweet`, SHA256
  `18f69070e456841cc4d400f6d6438b7ede02eb2e6b0429d4b231da88e7d9eddc`,
  and no FP6 ADT artifact. A source commit mentioning FP6 did not select FP6
  for this push build. Do not package that kernel for FP6.
- FP6 build run `39373440958` at `24370bb` generated the ADT, then failed during
  XNU compilation; the `fp6-boot` job was skipped, so no matching kernel/boot
  image exists. The failed compile pulled in SWEET HFS and pthread features
  through the shared master config, and the portable BearSSL include paths were
  only enabled for SWEET.
- Corrected the config scope: SWEET HFS is machine-specific; FP6 no longer
  enables Sweet HFS or its bundled pthread provider. FP6 still stages the
  portable crypto implementation, with compiler include paths enabled for
  FP6. Run `39374822879` reached patch 0031, which requires staged HFS source
  even when that filesystem is disabled. Restored HFS source staging for FP6;
  this stages files for later patch contexts but does not enable HFS in its
  machine config. Retry CI after this fix. Full build and phone boot are pending.
- Inspected failed CI run `39375193145` at `552b6b2`. All compilation units
  succeeded; the final link `kernel.development.fp6.unstripped` failed on two
  undefined symbols: `_sweet_sample_task` from `sweet_sample.o` (unconditionally
  compiled by bsd/conf/files while its implementation in osfmk/kern/exception.c
  was guarded by ARM64_BOARD_CONFIG_SWEET) and `_sweet_secondary_entry` from
  `SweetCPU.cpo` (PSCI CPU_ON stub in osfmk/arm64/start.s was guarded by SWEET).
  In patch 0099, guarded `bsd/dev/sweet_sample.c` under ARM64_BOARD_CONFIG_SWEET
  and added FP6 guards to `osfmk/arm64/start.s` for `sweet_secondary_entry`, MPIDR
  Aff1 extraction, TLB/cache invalidation and SCTLR check bypass. Patch 0099
  verified to apply cleanly against baseline `b097596`. Ready to commit and push.

- Local LLVM build now links the shim and packages an unsigned Android v4 image.
  The local packaging check used placeholder payload bytes only: shim and ramdisk
  unpack byte-for-byte. This is not a tested XNU boot image or a phone observation.
- `tools/fp6-package.py` consumes a kernel and ADT from the same CI run, builds
  the FP6 shim, verifies packaged components and writes hashes/provenance.
  The new `fp6-boot` CI job uploads `fp6-fastboot-boot` after an FP6 kernel build.
  Its first CI execution failed before packaging. Pushes now use the FP6 target
  by default; select other targets explicitly for manual runs.
- FP6 shim failures halt instead of entering Sweet diagnostic probes. Missing
  runtime framebuffer leaves the display untouched. The loader searches aligned
  payload headers after possible vendor ramdisks and validates segment extents.
- Header v4 relies on the installed vendor_boot/DTBO and ABL for the runtime FDT.
  Acceptance by FP6 ABL, live framebuffer availability and XNU handoff remain
  unmeasured. No flashing or phone commands were performed.
- User wants the new run's matching kernel/ADT, followed by driver bring-up one
  kext at a time after a working initial boot. Do not use the older kernel run.

## Fairphone 6 platform audit (2026-10-20)

- Began a source-only audit for Fairphone (Gen. 6), device name `FP6`.
  Fairphone identifies it as Snapdragon 7s Gen 3 / SM7635. Mainline Linux has
  `milos-fairphone-fp6.dts` with `fairphone,fp6` and `qcom,milos` compatibles.
- QCM6490 is Fairphone 5, not Fairphone 6. No QCM6490 code or FP5 target was
  added as part of this work.
- An experimental `MACHINE_CONFIG=FP6` compile target exists in patch 0004,
  using an ARMv8.2+crypto baseline and the sourced 8-core / 3 cluster counts.
  `tools/mkadt.py --device fp6` now generates an FP6 ADT profile with sourced
  CPU affinity/topology, GICv3 and UFS ranges, Fairphone identity, and the
  upstream Linux FP6 framebuffer address and dimensions. It requires
  no RAM arguments: the shim will read the bootloader FDT, exclude reserved
  ranges, initrd, framebuffer and its own image, then patch `dram-base` and
  `dram-size` in the ADT and boot args. The LineageOS DTS leaves RAM as
  `<0 0 0 0>`. The XNU workflow accepts `MACHINE_CONFIG=FP6` and emits the
  profile ADT artifact. Host syntax/serialization checks passed, but there has
  been no FP6 XNU build, CI run, FP6 shim image, or phone observation. See
  [docs/FAIRPHONE6.md](docs/FAIRPHONE6.md).
- Persistent LineageOS source checkouts are available under `/home/ersa/Dev`:
  `android_kernel_fairphone_sm7635` and
  `android_kernel_fairphone_sm7635-modules`. The device tree and vendor DTS
  reference remain under `/tmp/lineage-fp6-device` and
  `/tmp/lineage-fp6-devicetrees`.

## POCO X2 / Phoenix support (2026-10-20)

- Inspected `aospa-phoenix/android_kernel_xiaomi_phoenix` at
  `c01153e9ba446642640749077a19467e7e0094f5` in `/tmp` (source only; clone is
  not part of this repository). It confirms the shared SM7150 platform and
  Adreno 618 family. Phoenix and Sweet both have 1080x2400 panels with 120 Hz
  maximum timing; the Phoenix source describes WLED and 30–120 Hz modes, while
  Sweet uses OLED and 60/120 Hz modes.
- Added a `PHOENIX` XNU machine config that reuses the existing SM7150 board
  definition, platform expert and GPU path. Added `--device phoenix` to
  `tools/mkadt.py`; generated Phoenix trees use the `xiaomi,phoenix` compatible
  and a distinct synthetic ECID. The iOS-facing D22AP / iPhone10,3 identity is
  retained for the bundled iPhone X userland.
- This is source inspection and code editing only. No tests, XNU build, CI run,
  phone boot, or display observation was performed. The XNU/platform changes
  and Phoenix ADT have not yet been built or tested on hardware. See
  [docs/PHOENIX.md](docs/PHOENIX.md).

## What this repo is

Driver playground for the XNU/iOS 16 port to the Redmi Note 10 Pro (`sweet`,
SM7150, Adreno 618). The target is a real Adreno driver; the display today is
CPU-rendered. Public repo `dipa-studio/ios-extra`, branch `main`. The user made it
private overnight, then authorized restoring public visibility on 2026-10-19;
GitHub now confirms public. Kernel builds use this repo's GitHub Actions
(`.github/workflows/xnu.yml`, macOS runner, ~6 min).
`/home/dipa/ios-sweet` belongs to other agents: read-only for us.

## Where the GPU bring-up stands (all measured on the phone unless noted)

| Patch | `sweetgpu=` | What it does | CI run | Phone |
| --- | --- | --- | --- | --- |
| 0080 | 1 | read-only GCC/GPUCC clock + GDSC inventory | 39152959124 | ok |
| 0081 | 1 | cache that inventory, replay it over USB | 39154941656 | ok |
| 0082 | 2 | command-DB ARC level tables (`gfx/cx/mx.lvl`) | 39157726409 | ok |
| 0083 | 3 | MX+CX LOW_SVS votes via RPMh ARC, CX GDSC on/off, rollback | 39159151996 | ok |
| 0084 | 4 | GMU clock tree (GPLL0/2 gate, RCG 200 MHz, cx-gmu branch), rollback | 39161422925 | ok (first build refused: wrong precondition) |
| 0085 | 5 | GCC memnoc/ddrss-axi branches + first GMU register reads | 39162789741 | ok |
| 0086 | 6 | GMU firmware (`a630_gmu.bin`, staged at build) into ITCM/DTCM, readback | 39164168730 | ok, 0/8192 mismatches |
| 0087 | 7 | read-only GPU SMMU inventory | 39165446245 | ok |
| 0088-0089 | 8 | stream 5 -> CB3, tiny 4 KiB page table, ATOS check, restore (+ write transcript) | 39167833774 / 39168706195 | translations correct; S2CR3/CBAR3 refuse restore |
| 0090 | 9 | read-only RSC/PDC inventory | 39169517724 | ok |
| 0091 | 10 | mainline A618 RSC/PDC init (48 writes, readback), RSC stop handshake | 39170396365 | handshake ok, 9/48 writes did not read back |
| 0092 | 10 | same, logs every mismatch + reads the table first | 39171199100 | stop handshake ok; all 9 mismatches identified |
| 0093 | 11 | 13 GMU buffer pages, mainline HFI layout, 29 ATOS checks | 39293204273 **passed** | 29/29 ATOS; inactive=1, restored=0 |
| 0094 | 12 | read-only inventory of 29 pre-boot GMU registers | 39297388718 **passed** | 29/29 registers read; home screen confirmed |
| 0095 | 13 | bounded TCM retention + RSC wake/stop, CM3 reset | 39300239967 **passed** | wake/stop and full sampled state restore; home screen |
| 0096 | 14 | read-only GMU IRQ masks/status, fence and RPMH state | 39303111412 **passed** | 6/6 reads; home screen |
| 0097 | 15 | GMU interrupt mask/restore | 39305068882 **passed** | AO reads 0x3f; guard stops, restored; home screen |
| 0098 | 15 | exact measured AO readback; continue mask test | 39307039113 in progress | not tested; no image yet |

The user confirmed the home screen after every boot up to 0097. Each stage runs
inside the previous one's window (`sweetgpu=N` includes all lower modes) and undoes
itself except: SMMU `S2CR3`/`CBAR3` (left inert: `SMR3` invalid, `SCTLR` 0), the
GMU RCG (left at `0x602`), and the RSC/PDC configuration of 0091 (left in place).

**The GPU core (GX) has never been powered and nothing has executed on the GPU.**
Rendering is still CPU. The GMU processor has never been released from reset.

## Immediate next action

0095 phone test passed: RSC wake ACK=3 (bit 1 set), SEQ_BUSY=0, stop
STATUS=0x01010006, all six sampled control/state words restored. Retention 1->0,
CM3 reset remained 1 and GX GDSCR stayed 0x00222001. User confirmed home screen.
Raw values in GPU_LOG. No firmware execution or GPU command yet.

0096 (mode 14) passed at 18:39:28 UTC, user confirmed home screen. Both GMU
interrupt mask words=0, both status words=0, AO fence control=0, RPMH power
state=0x0f; raw values in GPU_LOG. All lower probes/cleanup still pass. Full CI
39303111412 built edd2b796ed7ff02434c42942c490543c17f95456 and artifacts match the
local source. 0097 separately tested the first mask with CM3 still reset (result below).
0097 (mode 15) reached the readback guard at 18:53:52 UTC: wrote AO mask
0xffffffff, got 0x3f, restored 0; second mask untouched. All sampled state/lower
cleanup restored, reset=1 and GX off. User confirmed the home screen. Green CI
39305068882 built 01dbc6e5571eacdca32f7c0d60bc34ce0d77ab00; artifacts matched.
0098 implements only that exact AO tuple exception, retaining mode 15 and the
mainline all-ones write. Normal and ASan/UBSan suites pass, including 42 rejected
alternative AO/HFI readbacks, all 20 zero-write refusals and failure/rollback tests;
arm64 compile 0 of 1 failed. Baseline c242eb7 (measured 0097); isolated diff equals
0098 patch, committed/pushed at edab65c998a917d5e450b730aa4d0ff2e8e6032e. CI 39307039113
is in progress at handoff; verify it succeeds and verify/package its artifacts before
the phone test. No 0098 image or phone result exists at this handoff.

An unvalidated first-start draft is external only (`ios-extra-work/gmu-first-start-draft.patch`),
based on 0095; do not apply it unchanged. It still needs IRQ-mask/clear gates,
complete host failure tests and reconciliation with 0096–0098 measurements before
full CI or phone use. It also needs SMMU global-fault interrupt containment: measured
sCR0=0x00200626 has GFIE/GCFGFIE set. No sCR0 write has been made. See GPU_GMU_BOOT
and the first-start review in HANDOFF. No first-start image exists.

## User-visible iOS observation (2026-10-19)

The user reports missing wallpaper and some white Settings/widgets in this image;
a separate image assembled from ios-sweet patches reportedly has working wallpaper
and widgets (still only three apps). The comparator build/root/assets have not
been identified or reproduced here; cause and relationship to GPU experiments
are unestablished. Home-screen arrival does not mean the UI is fully working.
The user asked to continue GPU bring-up; no userland repair or upstream-tree
changes are being made as part of this work.

## Additional source reference

The user supplied apple-silicon-anyos-project. Pinned source review at
59fd73aac4ae386939bc69dc58dffbce1b2167b2 is in GPU_EXTERNAL_DRIVERS: candidate
AIR/SPIR-V/Vulkan reuse for later integration, but a QEMU/macOS paravirtual
transport and no demonstrated sweet/Adreno path. No code imported or executed.

## Hard constraints (unchanged)

- Always check `fastboot devices` (serials redacted) before asking for fastboot.
  If exactly one device is already there, announce and run the authorized pending
  temporary test; ask only when none is present, stop if multiple are present.
- Temporary `fastboot boot` only. No flashing, no partition/GPT changes, keep
  bootloaders, recovery, modem, persist and the backups. Never `fastboot getvar`.
  The user must put the phone in fastboot; never reboot it unannounced.
- Keep serials, device dumps and Apple artifacts out of Git. The GMU firmware is
  downloaded at build time (`xnu/patches/0086-stage-gpu-firmware.sh`), never committed.
- Report source reading, a green build and a phone result as three different things.

## Workspace map (outside Git)

`/run/media/dipa/android/ios-extra-work/`: `buildtree/xnu` (isolated XNU tree; local
git commits mark each CI-validated baseline, `sweet_gpu_fw.h` is untracked there),
`out-NNNN/` + `ci-NNNN/` (latest CI kernel and build tree), `gpu-fw/` (linux-firmware
clone `lf/`, mainline v6.12 sources, register xml), `logs/` (`phone-*.pcap/.txt`,
`ci-0081.log` which `tools/xnu-cc.py` needs, sanitized fastboot output), `objects/`,
`shim-out/` (symlinked as `shim/out`). Keep only the latest image/kernel; old ones are
reproducible from the manifests. 136 GB free on the external drive; the home disk is
small, so keep large files external.

## Tools (all tracked, `tools/`)

`gpu-package.py` (kernel -> temporary boot image + manifest), `gpu-phone-test.py`
(capture, boot once, replay window, decode), `gpu-decode-pcap.py` (UDP log from a
pcap), `phone-ecm-host.py` (host side of the USB ECM link), `xnu-cc.py` (single-file
arm64 compile against the CI build tree). Host tests: `python3 -W
error::ResourceWarning -m unittest discover -s tests` (also with
`IOS_EXTRA_CFLAGS="-fsanitize=address,undefined -fno-sanitize-recover=all -g"`).

## FP6 Actions failure review (2026-10-20)

- Reviewed failed FP6 run `39412735706` at `83a712822ef0855bf653f00ee2938b8845766352`.
  The compile reached the XNU build and reported an undefined `kDbgIdTopLevelHeader`
  in the FP6 consistent-debug fallback, plus missing staged `sweet_libpthread/kern/*.c`
  includes. Downloaded that run's `xnu-buildtree` artifact and confirmed XNU 8796's
  `consistent_debug.h` documents the top-level record field but does not define that
  symbol. The fallback now supplies a local CDBG-HDR record ID. The libpthread staging
  script now stages the immutable matching provider for FP6, consistent with patch
  0099 compiling its provider sources. Pending a new Actions result.
- Reviewed FP6 Qualcomm constants in patch 0099 and the generated ADT: FP6 uses
  GIC redistributor stride `0x40000`, virtual timer INTID 27, one CPU for initial
  bring-up, and SM7635/Volcano compatible strings. Patch 0099 corrects the initial
  FP6 header's placeholder stride. No device or display driver behavior is inferred
  from these build definitions; the framebuffer splash is bootloader-provided.

- Follow-up run `39413914090` at `6da7325` staged pthread successfully and compiled all
  XNU objects, then failed at final link: `sweet_amfi.o` referenced seven
  `sweet_entitlements_*` functions absent from `SweetEntitlements.cpp` because that
  implementation was SWEET-only. Expanded its build guard to FP6 in patch 0035;
  this preserves XML entitlement support and resolves the specific undefined symbols.
  New CI build pending.
- Run `39414717734` at `48b58a5948a7c23e46022406eb5134e0da7f314d` completed successfully:
  both the FP6 XNU build and `fp6-boot` packaging job passed. The run uploaded
  `fp6-fastboot-boot` (shim boot image, SHA256SUMS and manifest), plus `xnu-kernel`
  and `fp6-adt`. This confirms a kernel build and temporary-boot-image package only;
  no phone boot has been performed for this image.
- The user expanded the FP6 port goal to staged XNU support for CPU/SMP, timer/GIC,
  display console, UFS storage, graphics/software rendering and USB/DWC3 networking
  or serial. Work these subsystems one at a time; distinguish bootloader-provided
  framebuffer splash from an XNU display driver. Fairphone 6 is SM7635 (Snapdragon
  7s Gen 3), so the user's table's SM7450 label should not be used for this target.
- SMP source review: LineageOS `qcom/volcano.dtsi` has eight CPU nodes with MPIDRs
  `0x000` through `0x700` and a 4+3+1 cpu-map. The generated FP6 ADT matches those
  IDs. Existing PSCI CPU_ON, secondary reset entry, redistributor lookup and SGI
  startup path are present in patch 0099; enabled its ceiling for all eight CPUs
  and changed the generated FP6 image command line to `cpus=8`. This is source
  inspection only until the next CI result and a phone boot; each secondary must
  report initialized/SGI-ready before XNU publishes all CPUs initialized.
- Separate boot observations reported by the user: XNU waits for
  `IOProviderClass IOMedia AppleHFS`, and the boot picker failed to write its
  reason to NVRAM. Neither observation verifies secondary CPU startup. Root media
  publication and NVRAM persistence remain separate issues. The wait is emitted
  by `IOFindBSDRoot`'s fallback HFS-media matcher when no `rd=` root was selected.
  For the next FP6 image, package a minimal Mach-O init as the existing virtual
  `RAMDisk`/`rd=md0` root. This deliberately bypasses UFS; it does not implement or
  validate the FP6 UFS host driver. The CI packager now builds and includes that
  init. The known header-v2 packaging path still requires the local stock DTB.
- Correction after reviewing the earlier FP6 boot notes: the known on-device path used
  Android boot header v2 with the stock DTB embedded. CI run `39414717734` uploaded a
  5,626,548-byte compressed artifact, but that artifact expands to a 16,203,776-byte
  header v4 image without a DTB; it is not the previously tested packaging format.
  Repacked that run's successful kernel and matching ADT with `/tmp/fp6-stock.dtb`
  using `tools/fp6-package.py --dtb`, which selects header v2. The resulting image is
  22,896,640 bytes, SHA256 `3dcc03f79b4fb6b775ebbb1612509a772e54b78d45301e20bdd72ce95861e59e`;
  unpack validation confirmed the 192,512-byte shim kernel, 16,003,456-byte XNU
  payload and embedded DTB exactly match their inputs. This rebuilt v2 image has not
  been booted. CI run `39417320648` repeated the same v4/no-DTB mistake. The user
  tested its image and ABL rejected it with `Failed to load/authenticate boot image:
  Invalid Parameter`. Confirmed the header version at offset 40 is 4 and there is no
  embedded DTB. Repacked this run's eight-CPU kernel and matching ADT with the local
  stock DTB and RAM-disk init: `/tmp/fp6-repack/fp6-shim-boot.img`, 22,913,024 bytes,
  SHA256 `4a528a4cec90f772685fd740484636b2fc8c61b23d0d840e825872e4c8a896e0`.
  Package validation confirms header v2 and exact kernel, payload, and DTB bytes.
  `tools/fp6-package.py` now requires a DTB and rejects header v4. CI publishes a
  fastboot image only when repository variable `FP6_STOCK_DTB_URL` is configured;
  without it, the workflow warns and skips the image artifact. The corrected local
  image was then booted on the phone; the user reports that all 8 CPUs came up.
  The exact image SHA and boot log have not yet been provided, so this observation
  is not attributed to a particular package.

## FP6 iOS userspace image and Qualcomm subsystem audit (2026-10-20)

- Built a local iOS 16.7.16 (`20H392`) HFS+ root image from the user-provided
  iPhone X IPSW. The raw image is 16 GiB; `img2simg` produced a 12 GiB Android
  sparse image. The final `fsck.hfsplus -fy` reported the volume appeared OK;
  `file` recognized the output as Android sparse v1. This is host-side image
  construction only. It has not been flashed or mounted by FP6 XNU.
- Do not flash this image to `userdata` yet. That operation overwrites the
  phone's existing userdata, while the current FP6 image boots a tiny `rd=md0`
  RAM-disk init and has no FP6 UFS block driver/root-media path. The iOS HFS+
  image therefore cannot yet be used by the running kernel. Raw and sparse
  images remain under Downloads and are not tracked.
- User clarified that the current debugging goal is USB debugging. Source review
  confirms FP6's Qualcomm DWC3 wrapper at `0xa600000`, generic DWC3 core at
  `0xa600000`, eUSB2 PHY at `0x088e3000`, EUD registers at `0x088e2000` and
  `0x0c278000`, and QMP USB/DP combo PHY at `0x088e8000`. It uses OTG/role
  switching, extcon/EUD and PDC interrupts. Existing CDC-ECM/live-log patches
  0072–0077 are SWEET/SM7150-specific and cannot simply be enabled for FP6.
  See [FP6 Qualcomm subsystem audit](docs/FP6_QUALCOMM_SUBSYSTEMS.md).
- Source review also finds the next practical subsystem priorities: FP6 UFS
  block/root support for iOS userspace, USB CDC-ECM for debug logs, then the
  board-specific power/regulator path and touch input. The bootloader framebuffer
  is separate from a live panel driver; Adreno 618/740 code is not a drop-in for
  FP6's Adreno 810 Gen8.3 GPU. Wi-Fi, Bluetooth, audio, camera and cellular depend on more
  firmware/DSP and transport work.
- No FP6 USB code was changed or tested in this audit, and no new CI run or phone
  boot was started. The next USB code change should first gather a read-only
  FP6 DWC3/clock/PHY state report, then test endpoint-zero enumeration before
  adding CDC-ECM. The new root image must not be presented as a phone-tested
  result.


## FP6 Qualcomm UFS and GPIO ADT (2026-10-20)

- Started `0100-fp6-qcom-ufs-root.patch`: enables the existing UFSHCI driver
  for FP6, labels its output QCOM UFS, keeps Sweet-only log/GPU/USB/touch/key
  startup behind the SWEET board guard, rejects failed controller MMIO maps,
  and adds an idempotent initializer with a read-only probe entry point. The
  probe ignores `ufsrw`; root mode honors it only when explicitly requested.
- `IOKitBSDInit.cpp` gains an opt-in `fp6ufsprobe=1` hook and FP6 `rd=ufsroot0`
  routing. The probe image retains `rd=md0`; the root image omits the RAM disk
  and leaves the existing Android `userdata` untouched. At the initial source
  change, neither image had been built or booted; follow-up CI/package results
  are recorded below.
- Corrected `tools/mkadt.py` to match the FP6 stock DTB's Cliffs TLMM:
  physical base `0x0f000000`, 16 MiB range, SPI 208, 179 GPIOs, reserved 56–60.
  This replaces an incorrect Volcano-compatible/reserved-pin guess.
- The FP6 bugreport identifies the touch controller as ESWIN EPH86xx on SPI0.0
  at QUPv3 SE0 `0xa80000`; the Fairphone SM7635 modules contain its SPI driver.
  The matching FP6 SKU overlay includes the Volcano MTP touch description:
  SPI mode 3 at 2 MHz, IRQ TLMM GPIO 19, reset GPIO 20, SPI pins 94–97, L22B
  and L9B supplies, plus `EPH86XX_fw.bin`. Linux's GPIO number 364 corresponds
  to the source reset pin in that overlay, although XNU must use the TLMM-local
  pin number 20.
- Updated the generated FP6 ADT to mark QUPv3 SPI0 and its ESWIN touch child
  present, with the overlay's GPIO and panel metadata. The controller still
  needs a GENI driver, pinmux/clock/regulator support and a HID event service;
  marking the ADT node present does not turn on the physical bus.
- Added opt-in `fp6gpio=1` and `fp6touch=1` passive probes to the UFS-probe
  image. They sample Cliffs GPIO input states (skipping reserved pins 56–60)
  and report the ESWIN touch ADT node. They do not access SPI MMIO or write pin
  mux, clock, reset, or SPI command registers.
  The successful build contains these paths; no phone observation exists yet.
  They are diagnostics, not a touch event driver.
- The corrected workflow run `39423526775` succeeded on source commit
  `d50bbff0304a365ee2972e3c041b2a9936e53591`. CI kernel SHA256:
  `2736519b29b5b6737aa40ddbf2377affea27d3a0adc5db7279677bc90a061181`; FP6
  ADT SHA256: `da9a1f5881207ac946db3f64cbd4165b8828a899019a049a04bb49081d3529f4`.
- The CI `fp6-boot` job skipped packaging because `FP6_STOCK_DTB_URL` is not
  configured. Using the verified CI kernel/ADT and local matching stock DTB
  (`16a9e60e441772b5cf491a6b51dbe4829f5895fa284bcfa342623bc5b2287dc5`),
  locally packaged Android boot header-v2 images in
  `/tmp/fp6-ci-39423526775/images/`. The recommended read-only probe image is
  `touch-probe/fp6-shim-touch-ufs-probe.img`, 22,917,120 bytes, SHA256
  `f5abf0c8697aebef950f1d1fa6d997d6eae1d3a770caacd3b3377b0d26928198`; its
  command line keeps `rd=md0` and enables `fp6ufsprobe=1 fp6gpio=1 fp6touch=1`.
  Baseline and `rd=ufsroot0` images are alongside it. Package validation
  confirmed embedded kernel/payload/DTB and all SHA256SUMS; no image has been
  booted. Current Android `userdata` is not the iOS HFS+ root image.
- FP6 USB gadget/debug transport and active EPH86xx SPI/HID input remain
  unported; Sweet's SM7150 implementations are still guarded from FP6.

## FP6 Qualcomm UFS SOC bring-up (2026-10-20)

- Added and pushed commit `b1d8734` (`feat(fp6): initialize UFS power and SMMU
  handoff`). Patch `0105-fp6-ufs-soc-basics.patch` adds FP6-only handling for
  the UFS SMMU stream, the Qualcomm `broken-ahit-wa`, UFS power-mode query and
  wake-up, fixed/descriptor sense parsing, and bounded readiness retries. The
  FP6 ADT now includes SMMU base `0x15000000`, size `0x100000`, and UFS stream
  ID `0x60`. The SMMU path preserves a pre-existing stream mapping and only
  creates a bypass context for this stream when it is unmapped; it does not
  alter global SMMU settings or other streams.
- GitHub Actions run `39439447885` built the FP6 kernel successfully (build
  job `118685115137`, 6m57s) and generated/uploaded the matching ADT. The
  `fp6-boot` packaging step skipped because repository variable
  `FP6_STOCK_DTB_URL` is unset.
- Downloaded CI kernel SHA256
  `9f7b6335a4d377779618832b22a49d8f69685ad1f133481218af11c61ecef3c7` and ADT
  SHA256 `9d9957b903bb091d91ab688788facee0432f2ddc8ade82081ad48239d65bc467`.
  Reused the exact stock FP6 DTB from the previous verified v2 boot image;
  its SHA256 `16a9e60e441772b5cf491a6b51dbe4829f5895fa284bcfa342623bc5b2287dc5`
  matches that image's manifest. Locally packaged the header-v2 UFS-root image
  at `/tmp/fp6-soc-39439447885/ufs-root/fp6-shim-ufs-root.img`, 22,917,120
  bytes, SHA256
  `3f557a3bbe16056d8e53a67dba70de89ba7aa693659be74946c77e33f41be2ad`.
  Its command line is `debug=0xc serial=3 cpus=8 keepsyms=1 -noprogress
  rd=ufsroot0`; packaging verified the embedded kernel, payload and DTB.
- Source/build/package results only. The new SMMU/UFS path has not been booted
  on hardware; the image leaves userdata and all partitions untouched. Next
  step is the user's temporary `fastboot boot` test, then use the resulting
  console/panic or root mount observation to tune the stream mapping and UFS
  command path.

## FP6 UFS root HFS mount fix (2026-10-20)

- User tested the UFS-root image from run `39439447885`. Phone output reported
  `userdata` on LUN 0, first block `0x666d88`, 213586 MiB, read-only, and an
  enabled SMMU stream entry for SID `0x60` (`SMR=0x80000060`). The selected
  `ufsroot0` device was then followed by root mount failure `errno 19`
  (`ENODEV`). This confirms discovery and root-device selection; SMMU mapping
  was already present and preserved.
- Traced the mount failure to FP6's generated master config: patch 0026 builds
  and registers the Apple OSS HFS implementation only when `SWEET_HFS` is
  enabled, but the new `MASTER.arm64.fp6` config omitted that option and the
  `sweet_hfs` filesystem selection. Added patch
  `0106-fp6-enable-hfs-root.patch` and pushed commit `4ce0c16`; it enables both
  for FP6 so `vfs_mountroot` registers HFS.
- CI run `39441508260` built successfully (build job `118692265513`, 7m30s).
  As before, automated boot packaging skipped because `FP6_STOCK_DTB_URL` is
  unset. Locally packaged the matching kernel/ADT and verified stock DTB as a
  header-v2 UFS-root image:
  `/tmp/fp6-hfs-39441508260/ufs-root/fp6-shim-ufs-root.img`, 23,396,352 bytes,
  SHA256 `ed7d3aeaa163215c375f1eb11b7068e3399f3c263831c5a9013533f41d2f19fd`.
  The manifest records kernel, ADT and DTB hashes and `rd=ufsroot0`; package
  validation confirmed the embedded components. This HFS-enabled image has
  not yet been booted on the phone.
- Follow-up phone output shows HFS finds an in-filesystem journal at offset
  `0x800000`, but journal-header update fails with `EINVAL` while the UFS
  device was initialized read-only. The root mount path deliberately defaults
  to read-only unless `ufsrw=1` is passed; HFS journal replay/update needs the
  custom userdata partition writable. Packaged a follow-up image with that
  explicit opt-in:
  `/tmp/fp6-hfs-rw-39441508260/ufs-root/fp6-shim-ufs-root-rw.img`, SHA256
  `74dda22095553a68ebd8cb61b2836b896440cb3908c728c02554fc075f839d30`.
  Its write path remains bounded to the GPT partition selected by `ufsroot`
  (`userdata` by default); it cannot address other UFS partitions. This
  read-write image has not yet been tested on the phone.

## UniXNU repository review (2026-10-20)

- Shallow-cloned the UniXNU build repository to `/home/ersa/Dev/UniXNU` with
  its shallow driver/kit submodules, the device repo to
  `/home/ersa/Dev/UniXNU-sheng` with its shallow touch/preflight submodules,
  and firmware repo to `/home/ersa/Dev/uefi-sheng`. Main repo commits at
  review: UniXNU `5725f11`, UniXNU-sheng `b409de2`, uefi-sheng `329b473`.
  All these checkouts were clean after cloning. Source review only: no build,
  tests or phone run was done.
- UniXNU-sheng targets Xiaomi Pad 6S Pro / SM8550 and boots through its own
  Mu-Silicium UEFI plus DarwinBoot flow. FP6 currently boots through the
  existing fastboot shim, so the UniXNU boot chain is a separate architecture
  choice; its driver repos can still be referenced or selectively ported.
- Most transferable source is at the interface/algorithm level: ARM CPU/GIC/
  timer, ADT matching, UFSHCI command handling, SMMUv2 4 KiB table code,
  framebuffer copy/present, GENI SPI transport, HID event publication and
  root-manifest verification. None should be assumed board-ready for FP6.
- Confirmed board-specific limits: NativeUfs matches `qcom,sm8550-ufshc` and
  hardcodes sheng GCC/UFS physical ranges and stream setup; NativeAdreno and
  AdrenoPM4 are A740-specific; NativeNovatekTouch is for the sheng NT36532E;
  NativeMobileDisplay uses firmware GOP/framebuffer scanout and has no hardware
  vblank. NativeMetal's demonstrated GPU path depends on the Adreno/Turnip stack.
- `kits/VerifiedRoot` implements an owner-key RSA-3072/SHA-256 block-manifest
  format; it is not Apple's Image4/APFS sealed-root authentication. NativeAES
  and NativeKeyStoreEvents do not implement QTEE communication or SEP-backed
  AppleKeyStore. Check each module's own license before copying; the collection
  mixes BSD-2-Clause-Patent, BSD-2-Clause, MIT, and Apache-2.0 code.
- The UniXNU organization page showed three top-level repositories at review;
  the build repo additionally pins 21 driver/kit submodules, and the sheng
  device repo adds two submodules. See the checked-out READMEs and source under
  `/home/ersa/Dev/UniXNU*` for exact per-module commits.

## FP6 USB log sender follow-up (2026-10-21)

- User reports the USB log stream is not usable for debugging and the Settings
  About page raises `RemoteMemoryException`. The crash is not diagnosed yet; a
  phone crash report or reliable kernel capture is needed before attributing it
  to the earlier SWEET `volumeTotalCapacity` issue.
- Patch 0125 removes socket-first delivery from the FP6 USB log sender. In 0114,
  `sock_send()` returning success advanced the ring cursor even if the packet was
  still queued behind route/ARP and never reached the host, so the raw Ethernet
  path was skipped. The sender now always emits the already-framed raw packet,
  retains its ring position on `ENOBUFS`, and waits 5 ms between successful
  packets to let the gadget's 32-entry TX queue drain.
- Source was based on CI build tree for run 39565043535 (success, head
  0755f4d2f6343b06cc0f5d31d31460b096330d3d). The modified `sweet_usb.c` passed
  `tools/xnu-cc.py` against that tree (`0 of 1 files failed`) using local Clang
  23. Initial CI run 39568643454 failed before compilation because the patch
  runner rejects zero-context diffs. Patch 0125 was regenerated with standard
  context, passed `git apply`, and built successfully in CI run 39569106154 on
  e21a51767ef7ca68ca796bb840431c8ef7810044. The CI build-tree `sweet_usb.c`
  matches the locally compiled file byte-for-byte (SHA-256
  `5f6d78f1a5f1120ee4e8f1b98de803a98d54e34a7490f2474e51cbf307e220c7`).
- CI's `fp6-boot` skipped packaging because `FP6_STOCK_DTB_URL` is unset. The
  kernel checksum passed (`601288b0a5ae4ac1af9d870a269673205be1856b75f72f7da48131c809bdf100`);
  ADT SHA-256 is `401b10b78b7d4d0480b630c76b78d3e2bbbfd2da1753bc1382e797ba54474f8a`.
  Locally packaged and header-v2 round-trip checked
  `/tmp/fp6-usb-39569106154/image/fp6-shim-ufs-root-pas-touch-usb-raw-paced.img`,
  SHA-256 `d25383cdb095111d6c8c600f2a0943eebc3f96ba31b37e1082a094945cdd6c01`,
  using the verified stock DTB (SHA-256
  `8198534128258bfe7b05bbb5b227affc181aa49b376884c08eae8564fce124e3`). Its
  args keep `fp6pas=1`, `fp6touch=2`, `fp6usb=2`, and the console visible.
- User's current tcpdump capture contained 233 UDP/5140 packets / 40,249 decoded
  bytes at inspection time. Decoded lines include kernel `CRASH assetsd` records
  and `exec ReportMemoryException`; this is not an About-specific stack trace.
  Capture remains active for the new-image test. `fastboot devices` returned
  zero, so this image has not been booted and the USB change is not yet
  phone-verified.

## FP6 battery and fuel-gauge source audit (2026-10-21)

- Inspected the exact stock DTB embedded in CI run 39569106154, decompiled to
  `/tmp/fp6-live.dts`, plus the Fairphone Volcano DTS and kernel sources. The
  DT has a PMK8550 ADC/RTC/PON/SDAM tree and a `qcom,power-telemetry` child
  marked `status = "disabled"`; it has no enabled local `qpnp-qg` fuel-gauge
  node. The battery-charger interface is instead a child of `qcom,pmic-glink`
  on `PMIC_RTR_ADSP_APPS`, with subsystem `lpass` and ADSP
  `msm/adsp/charger_pd` protection-domain dependency.
- The available `drivers/power/supply/qcom/qpnp-qg.c` only matches PM2250,
  PM6150, PMI632 and PM7250B configurations; its probe requires a parent
  regmap and battery-ID/thermistor ADC channels. It is not a PMK8550 driver
  that can be enabled by adding an XNU SPMI read. Historical SWEET
  `SweetBattery` in patch 0062 assumes a PM6150 fuel-gauge register map and
  estimates SOC from voltage; it must not be reused as FP6 telemetry.
- No FP6 code or device operation was made in this audit. Real SOC, current,
  charge state and temperature require the ADSP PMIC-GLink battery service
  (and its remote-processor/IPC prerequisites), or a separately validated
  PMK8550 telemetry implementation if the disabled QPT block's wire protocol
  can be established. An interim IOPMPowerSource would be a labeled static
  fallback, not a functioning fuel gauge.

## FP6 Adreno PAS ZAP loader patch correction (2026-10-21)

- CI run 39579222524 for commit 813e0ab failed while applying patch 0127 at
  `bsd/dev/sweet_ufs.c`: the patch used a zero-context declaration hunk that
  the strict patch runner could not locate. This was a patch-context failure;
  no compilation or phone test occurred in that run.
- A second attempt in commit f72c9d9 still failed at the first UFS hunk
  (line 56); no compile or phone test occurred. Rather than patch that file in
  a later step, remove the original UFS hook hunks from 0118 and 0122 as well
  as the attempted removal from 0127. The GPU inventory, PAS query and opt-in
  ZAP loader are registered together through `fp6_adreno_startup` at
  `EARLY_BOOT`. This eliminates all GPU references from the UFS driver and
  makes the patch series independent of that file's evolving context. Normal
  and ASan/UBSan host tests pass; a corrected CI build is still required before
  image packaging or phone testing.
- Commit e998189 built successfully in CI run 39581455083. The FP6 boot job
  skipped image packaging because the repository has no `FP6_STOCK_DTB_URL`.
  Locally packaged the matching kernel/ADT with the verified stock `tree-04`
  DTB and minimal RAM-disk init. Image
  `/tmp/fp6-zap-39581455083/image/fp6-shim-fp6zap.img` uses `fp6gpu=1`,
  `fp6pas=1`, `fp6zap=1`, `fp6touch=2`, and `fp6usb=2`; SHA256
  `2438d333a1d0a5e10ccf3ed8601916a0db61d010b0b535267beeeca83c27fc94`.
  The user booted it and reported this panic:
  `phystokv_range: illegal PA: 0x9ea9b000 phys base 0x900000000 size 0x100000000 @arm_vm_init.c:406`.
  Source audit confirms both ZAP cache-clean calls passed reserved carveout
  physical addresses with `phys=TRUE`; `clean_dcache` then calls
  `phystokv_range`, which rejects this carveout because it is outside XNU's
  managed RAM range. Fix patch 0127 to clean through the `ml_io_map_wcomb`
  virtual mapping (`phys=FALSE`). Updated the host harness to assert the mapped
  virtual addresses/flag. Normal and ASan/UBSan suites pass. This correction
  needs a new CI build and phone retest; the failed boot's USB NIC disappeared
  before capture started, so no PAS/ZAP SMC result is available.

## NativeUfs and Topaz cross-reference (2026-10-21)

- Read-only review of UniXNU/NativeUfs history: SMMU takeover entered in
  `31155a6`, with lower-context fallback in `04b748e`; later `33d9f64` and
  `af785c1` concern storage/FUA behavior. Its UFS driver quiesces requests,
  rejects stream conflicts, configures a pass-through context, fences writes,
  and validates readback. It does **not** build translation tables or program
  TTBR/TCR, TLBI, ATOS, Gunyah, or GPU DMA. Port its refusal/order/readback
  discipline only; its sheng addresses, SID and bypass mode are not FP6 values.
  Source: https://github.com/UniXNU/NativeUfs/commit/31155a6db21678df3c89d9d25b5711466d229369
- Read-only Topaz patch audit: its Wi-Fi patches 0113–0130 use Topaz's
  SM6225 modem/WLFW and GLINK/QRTR/QMI assumptions; no direct FP6 port is
  justified. Topaz README still reports no wallpaper provider, so there is no
  wallpaper implementation to lift. Surface patches 0131–0139 may inform the
  SweetSurface/CoreAnimation ABI after comparing with local 0109, but do not
  implement GPU execution. Display/DSI sequences target Topaz's 1080x2400
  panel; patch 0114's 1125x2436 logical canvas is a reference for the current
  FP6 status-bar work, not a physical panel configuration. Gold-cluster
  patches 0080–0082 are SM6225-specific; FP6 has its own 4/3/1 topology and
  those patches should not be copied.
  Source: https://github.com/MakrSas/ios-topaz
- FP6 translated-context patch 0131 host harness passes in normal and
  ASan/UBSan modes. RPMh ARC, GMU firmware, and XNU compile-helper tests pass.
  A local XNU object/syntax compile was attempted but could not start because
  `tools/xnu-cc.py` expects `/home/ersa/swift/usr/bin/clang`, which is absent
  on this host; only `/usr/bin/clang` is installed. Thus 0131 is not yet
  validated against the cached XNU compile commands or a CI kernel build, and
  no SMMU write has been tested on the phone. Do not claim GPU/Metal execution.

## FP6 iPhone X logical display canvas (2026-10-21)

- Status-bar experiment 0130 changes FP6's logical display provider to
  1125x2436 while preserving the stock 1116x2484 physical framebuffer. The
  framebuffer offset math centers the logical canvas (4-pixel horizontal crop
  per side and 24-pixel top/bottom bars); `present()` clears the unused rows.
  SweetHID now reports the same logical dimensions. This targets iPhone X
  userland layout and is separate from a native DSI/panel driver.
- `tools/mkadt.py` generated an ADT whose parsed `sweet,display` node reports
  canvas-width=1125 and canvas-height=2436. Patch 0130 applies cleanly to the
  cached XNU source. No XNU CI build or phone observation has tested this yet;
  it is included with the next GPU SMMU CI build at the user's request.

## FP6 GMU SMMU context programming correction (2026-10-21)

- Rechecked the `fp6smmu=2` context image against the local Fairphone
  `drivers/iommu/arm/arm-smmu` implementation. The initial probe omitted the
  AArch64/SEP fields in `TCR2` and Linux's S1 defaults in `CBAR`. It now uses
  `TCR2=0x00038011` (upstream SEP, AArch64 AS, 36-bit output PA) and
  `CBAR=0x0001f300` (S1 plus NSH walk configuration and WB fallback).
  `TCR=0x00802020` remains T0SZ=32, outer-shareable table walk, and EPD1;
  the 4 KiB TG0 encoding is zero. The probe refuses a context with nonzero
  FSR, clears stale W1C faults, invalidates/synchronizes its TLB before
  enabling the context, and installs the SID5 route last.
- Extended the FP6 MMIO harness to model FSR W1C behavior and require the
  expected `TCR2`, `CBAR`, and FSR-clear writes. The complete 11-test host suite
  passes; the GPU harness also passes ASan/UBSan, and `git diff --check` is
  clean. CI run 39611115127 failed on undeclared `delay()` calls. Added the
  missing XNU clock header; the next CI build is required to validate it. No
  SMMU write has been tested on the phone. Do not use the earlier 0131 build
  for a translated-context phone test.
