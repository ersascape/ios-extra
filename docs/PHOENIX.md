# POCO X2 (`phoenix`) support

Phoenix is added as a second SM7150 board target alongside the Redmi Note 10 Pro
(`sweet`). Both use the same Cortex-A76/A55 topology, Qualcomm platform support,
and Adreno 618 path in this repository. The board target, device-tree compatible,
and XNU-reported product name distinguish Phoenix from Sweet.

## Display source findings

The inspected kernel is `aospa-phoenix/android_kernel_xiaomi_phoenix` at commit
`c01153e9ba446642640749077a19467e7e0094f5`. Its Phoenix panel device tree lists
1080x2400 timing, dynamic modes from 30 through 120 Hz, 70x154 mm panel
dimensions, and WLED backlight control in
`arch/arm64/boot/dts/qcom/xiaomi/phoenix/dsi-panel-g7b-37-02-0a-dsc-video.dtsi`.
The Sweet panel configuration in the same tree is an OLED panel with 1080x2400
timing, 120/60 Hz modes, and 69x154 mm dimensions. Thus the panel technology,
physical width, backlight and supported refresh modes differ while native pixel
resolution and maximum refresh rate match.

The current XNU framebuffer takes its pixel dimensions and address from the
bootloader's framebuffer, reports an iPhone X sized canvas to match the bundled
iOS userland, and generates 60 Hz software vsync notifications. This change
does not add a DSI panel driver, brightness control, or 120 Hz presentation.
Phoenix's synthesized iOS identity therefore remains D22AP / iPhone10,3; only
the kernel board identity and synthetic ECID differ.

## Selecting Phoenix

- Build XNU with `MACHINE_CONFIG=PHOENIX` (the workflow's `machine_config`
  dispatch input).
- Generate its ADT with `python3 tools/mkadt.py OUT.adt --highmem --device phoenix`.
- Existing Sweet builds remain the default: `MACHINE_CONFIG=SWEET` and the
  default `mkadt.py` device profile.

Source inspection only; no Phoenix XNU build, boot, or phone observation has
been performed. The kernel clone is a temporary source reference and is not
part of this repository.
