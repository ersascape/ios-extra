# FP6 Qualcomm subsystem bring-up audit

Source review of the Fairphone 6 / Qualcomm SM7635 (`volcano`) using the
LineageOS device tree, device configuration and kernel checkout. This records
hardware described by those sources; it does not claim that XNU drivers work
on the phone.

## USB debugging

The board source describes a Qualcomm DWC3 wrapper at `0xa600000` (1 MiB),
with the Synopsys DWC3 core at `0xa600000` (0xd800 bytes). The wrapper uses
Qualcomm GCC clocks and reset, an eUSB2 PHY at `0x088e3000`, EUD-related
registers at `0x088e2000` and `0x0c278000`, and a QMP USB/DisplayPort combo PHY
at `0x088e8000`. It is an OTG, USB role-switch design with EUD extcon and PDC
interrupts. The stock Linux DWC3 MSM driver owns the role, PHY, power, clock,
and DMA setup.

This repository already has a CDC-ECM gadget and live kernel log transport in
patches 0072–0077. Those patches are SWEET/SM7150-specific: their GCC and
QUSB2 PHY register addresses and the USB startup hook assume that board's UFS
path. They are not enabled in the FP6 build and must not be enabled by changing
the board guard alone. FP6 has a different eUSB2 PHY and its current minimal
RAM-disk boot does not enter the SWEET UFS initialization path. The practical
debug target is CDC-ECM so the host can capture XNU logs over IP; USB serial
would also work, but needs its own endpoint and host-side console protocol.

The first FP6 USB experiment should be a read-only register/state inventory
after an FP6 boot, followed by a narrowly scoped endpoint-0/enumeration test.
Only after enumeration is measured should the ECM endpoints and live logger be
ported. The exact FP6 clock offsets can be sourced from `gcc-volcano.c`; do not
reuse the SM7150 offsets. The QMP SuperSpeed PHY is not needed to get a USB 2.0
debug link and should remain out of the first experiment.

## Other Qualcomm blocks visible in the source

| Block | What the board/kernel sources show | Bring-up assessment |
| --- | --- | --- |
| UFS | Qualcomm UFSHCI host with QMP UFS PHY; FP6 is configured for UFS storage. | High priority for iOS userspace. The existing SWEET UFS driver is tied to SM7150 registers. FP6 needs its own controller handoff/initialization and a media path XNU can mount. |
| RPMh / regulators / SPMI | Qualcomm RPMh clock, regulator and power-domain controllers, plus SPMI PMIC drivers. | Useful after kernel startup for safe power sequencing. Start with read-only state and a small, sourced regulator/clock change; this is not needed for the first RAM-disk init. |
| Display | MIPI-DSI panel and Qualcomm display/GPU stack; bootloader supplies the initial framebuffer. | The bootloader framebuffer is a useful console. A live panel driver requires DSI, panel, clock, regulator and backlight sequencing. Keep the splash and an XNU display driver as separate milestones. |
| GPU | Adreno 710 / Qualcomm KGSL path and firmware are present in Android sources. | Later work. The existing Adreno 618 experiments and UniXNU Adreno 740 stack are architectural references, not drop-in drivers for this GPU. |
| Touch / keys | FP6 device tree identifies the board input hardware and its buses/interrupts. | A good peripheral driver after the root and debug paths; requires the board-specific controller and bus support. |
| Wi-Fi / Bluetooth | Device configuration references QCA6750 WLAN, WCN6450 connectivity and firmware/DSP components. | Complex and dependent on firmware, transport, power and vendor interfaces. Not an early XNU bring-up target. |
| Audio / camera / cellular | Qualcomm DSP, codec, camera and modem subsystems with vendor services/firmware. | Much later. They depend on several working power, bus, DMA and userspace services. |

## iOS root image status

The locally assembled iOS 16.7.16 (`20H392`) image is a 16 GiB HFS+ raw image
and a 12 GiB Android sparse image. The post-tweak `fsck.hfsplus -fy` reported
the volume appeared OK, and sparse-image inspection recognized the Android
sparse format. This is a host-side image build only; the image has not been
flashed or mounted by FP6 XNU.

The tested FP6 boot path currently packages the kernel with a tiny `rd=md0`
RAM-disk init. It does not yet provide FP6 UFS block storage or mount the HFS+
image from `userdata`. Flashing the image now would overwrite the phone's
existing `userdata` contents without making the current kernel boot that iOS
root. Do not use `fastboot flash userdata` for this image yet. Keep testing with
temporary `fastboot boot` images until the FP6 UFS and root-media path exist.

## Source locations

- LineageOS device-tree source: `qcom/volcano-usb.dtsi`, `qcom/volcano.dtsi`
- LineageOS GCC source: `drivers/clk/qcom/gcc-volcano.c`
- LineageOS USB glue: `drivers/usb/dwc3/dwc3-msm-core.c`
- FP6 board configuration: `/tmp/lineage-fp6-device`
- FP6 device-tree/kernel source checkouts are local references only and are not
  copied into this repository.
