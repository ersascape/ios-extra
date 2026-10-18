# ios-extra — active handoff

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
- This session has not booted, flashed or otherwise changed the phone.

## Builds and integration

- `.github/workflows/xnu.yml` retains the inherited build and staging process.
  Its build job runs only when repository visibility is public. The user
  approved publication; public builds are now enabled.
- GPU probe 0080 is implemented, locally cross-compiled and fully CI-linked.
  No GPU phone test has been performed.
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
- Next: coordinate a separate phone test.
  iOS renderer selection,
  power-up, firmware, SMMU and submission remain future milestones.
  No GPU hardware test or upstream integration yet.
