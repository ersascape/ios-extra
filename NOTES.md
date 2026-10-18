# ios-extra — active handoff

## Purpose and workspace

- Created 2026-10-18 at the user's request as a separate, initially private
  driver playground. Working experiments can later be ported to `ios-sweet`.
- Local checkout: `/home/dipa/ios-extra`.
- GitHub: https://github.com/dipa-studio/ios-extra.
- Original reference checkout: `/home/dipa/ios-sweet`; do not modify it as
  part of playground work.
- Imported tracked baseline: upstream `347e19018e3e4c0117635e9e444f73659b2ece53`
  (patch 0079, display power), local snapshot commit `919ebb5`.
- Original README and NOTES are preserved in `docs/UPSTREAM_README.md` and
  `docs/UPSTREAM_NOTES.md`. Historical instructions and status in those files
  are reference material; this file and `AGENTS.md` govern current work.

## Initial state

- Kernel patches 0001–0079, shim and tools imported. No experimental driver
  implementation yet. The user selected full GPU driver work as the target.
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
  Its build job runs only when repository visibility is public. Private
  pushes may produce a skipped workflow; no macOS build should run.
- No kernel CI build has been requested in this session.
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
- Tooling follow-up: `tools/xnu-cc.py` hardcodes the upstream runner path;
  adapt it before replaying logs from this repository. Stage separate local
  build artifacts before kernel edits. CI itself does not use that helper.
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
- Next: audit GPU initialization dependencies and iOS renderer selection,
  then prepare opt-in GPU probe patch 0080 in an isolated build tree. No
  publication, kernel build, GPU hardware test or upstream integration yet.
