# GPU bring-up: first build

Patch `0080-sweet-gpu-probe.patch` adds `bsd/dev/sweet_gpu.c`, includes it in
the BSD source list and calls its probe after USB initialization in the
existing UFS-root startup path. It is dormant unless booted with `sweetgpu=1`.

This stage inventories clocks and domain control registers. It does not yet
initialize Adreno, load firmware, submit commands or accelerate rendering.

## Register audit

Xiaomi downstream source is pinned to
[`758bb7ef`](https://github.com/MiCode/Xiaomi_Kernel_OpenSource/tree/758bb7ef50af360e728662a1ed3b3a1b977a2f13).
Downloaded references are ignored under `research/gpu-sources/`.

| Registers | Reference | Probe use |
| --- | --- | --- |
| GCC GPU config AHB `0x71004` | `drivers/clk/qcom/gcc-sdmmagpie.c`, `gcc_gpu_cfg_ahb_clk` | Gate GPUCC access: branch enable bit 0 set, halt bit 31 clear, value not all ones |
| GCC GPU MEMNOC `0x7100c`, SNOC DVM `0x71018`, DDRSS AXI `0x4452c` | Same file, corresponding clock definitions | Raw clock inventory |
| GPUCC CX GDSCR `0x106c`, GX GDSCR `0x100c` | Saved phone DT domain nodes; corroborated by `drivers/clk/qcom/gpucc-sc7180.c` in Linux `32c52ec` | Report raw values and bit 31; never use them to authorize core-register access |
| GPUCC AHB `0x1078`, CX APB `0x1088`, CX GMU `0x1098`, CXO `0x109c` | `drivers/clk/qcom/gpucc-sdmmagpie.c` | Raw clock inventory |
| GPUCC CX GFX3D `0x10a4`, CX slave `0x10a8`, GX GFX3D `0x1054`, GX CXO `0x1060`, GX GMU `0x1064` | Same file | Raw clock inventory |

The saved DT places GCC at `0x00100000`, GPUCC at `0x05090000`, CX GDSCR
at `0x0509106c` and GX GDSCR at `0x0509100c`. The GPUCC control-register
space is used for domain control and status outside the GPU's GX core.
The probe requires the config-AHB branch to be enabled and running before
mapping it. The source's `CLK_IS_CRITICAL` flag is Linux policy, not proof of
the state left by ABL; the hardware branch value is still checked.

The downstream GX regulator requests `qcom,poll-cfg-gdscr` and has a separate
domain-status address. Consequently the log labels bit 31 as `PWR_ON` rather
than claiming that every GX subdomain is safely accessible.

`adreno_a6xx_gmu.c:a6xx_gmu_gx_is_on` explicitly requires a keepalive bit or
a guaranteed stable power state before interpreting GX state. We do not have
that guarantee yet. The probe therefore never maps the GPU, GMU, GPU SMMU,
firmware memory or protected carve-outs, even if the clock inventory looks on.
It performs no MMIO writes, votes, resets or firmware operations.

This is a source-derived access policy. Its behavior on the phone after ABL
is still untested; a successful compile does not validate MMIO accessibility.

## Isolated local build

Workspace: `/run/media/dipa/android/ios-extra-work/buildtree`.
The XNU source was reconstructed from Apple commit
`1b191cb58250d0705d8a51287127505aa4bc0789`; providers were fetched with the
repository's pinned staging scripts. All 79 imported project patches applied,
followed by applicable patches from the pinned darwin-xnu-build tooling.
The resulting local baseline commit is `788ab36d761b5564db9eaaee63003a7a7e6a5bae`.
Application log: `research/baseline-patches.log`.

Generated headers/fakeroot platform headers were copied from the reference
build-tree artifact into this workspace; its live source tree was not used
as the experimental source. No edits were made in the other checkout.

```sh
python3 tools/xnu-cc.py /home/dipa/ios-sweet/research/run28.log \
    /run/media/dipa/android/ios-extra-work/buildtree \
    bsd/dev/sweet_gpu.c bsd/dev/sweet_ufs.c
```

The helper now infers runner checkout paths from compile logs, supporting
both `ios-sweet` and `ios-extra`; `XNU_CI_DXB` provides an explicit override.

Local verification completed:

- XNU syntax checks: **0 of 2 files failed**.
- Real arm64 Mach-O object generation for both changed C files:
  **0 of 2 files failed**. Objects are in `ios-extra-work/objects/`.
- Probe object imports only `PE_parse_boot_argn`, `ml_io_map` and `printf`;
  disassembly contains the intended `dmb oshld` barrier.
- Host tests run the new file extracted directly from patch 0080 against
  mocked mappings, replacing only the ARM barrier for host execution.
  Eleven cases cover missing/disabled/invalid modes, mapping failures,
  disabled/halted/invalid config clocks, normal inventory, invalid power
  values and the prohibition on mapping GPU/GMU/SMMU regions.
- Patch 0080 reverse-application check passes against the isolated tree.

Run tests with `python3 -m unittest discover -s tests -v`.
Host tests check control flow and simulated mappings, not hardware state or
ARM bus ordering. Full kernel linkage and a phone boot are separate checks.

## Hardware test, when device access is available

Build a new kernel and use the normal shim packaging with `sweetusb=2
sweetgpu=1` added to the established boot arguments. Preserve the working
kernel image and root filesystem. This patch requires no root-image changes.

Expected console prefix: `SWEET GPU:`. A disabled config clock should produce
`config-AHB not enabled/running; GPUCC skipped`. An enabled config clock may
produce the GPUCC inventory, ending with
`GPU/GMU/SMMU skipped (no power hold); no hardware writes`.

Test both the default mode and the opt-in mode, keeping the existing UI and
USB logging functioning. Record the actual clock/domain values before
designing power-up, firmware loading and GPU address-space support.
No hardware test has been run in this session.
