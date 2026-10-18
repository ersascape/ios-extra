# ios-extra — active handoff

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
