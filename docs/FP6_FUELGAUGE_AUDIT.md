# FP6 fuel gauge: stock-kernel path

## Evidence

Source inspected: local Fairphone kernel `lineage-23.2`, commit
`9535e0f08` (short revision). The selected stock DTB has SHA-256
`8198534128258bfe7b05bbb5b227affc181aa49b376884c08eae8564fce124e3`.

The selected DT's `qcom,pmic_glink` node names channel
`PMIC_RTR_ADSP_APPS`, subsystem `lpass`, and protection domain
`tms/servreg` / `msm/adsp/charger_pd`. Its battery child is
`qcom,battery-charger`. This establishes the stock battery reporting path;
it does not prove a directly accessible PMIC fuel-gauge register interface.

References in `android_kernel_fairphone_sm7635`:

- `drivers/power/supply/qti_battery_charger.c`: owner/opcode/property enums,
  request/response structures, `read_property_id`, `validate_message`,
  `handle_message`, `battery_psy_get_prop` and link state handling.
- `drivers/soc/qcom/pmic_glink.c`: RPMSG channel matching, owner routing,
  `rpmsg_send`, subsystem restart and protection-domain notifications.
- `include/linux/soc/qcom/pmic_glink.h`: three-u32 message header.

## Implemented groundwork

`xnu/protocol/fp6_battery_glink.h` defines an allocation-free,
transport-independent numeric GET encoder and matching reply decoder.
It uses explicit little-endian byte access, exact 24-byte lengths,
owner/type/opcode/property checks and remote-error rejection. It admits
battery numeric properties before model-name and USB port-zero online only.
No charging control, firmware upload, ship mode or shutdown command is exposed.

This header is not staged into XNU yet and has no live transport consumer.
No phone reading, build or host execution has been performed for it.
It is a protocol boundary for the shared IPC work, not working battery support.

Raw capacity is hundredths of percent (Linux rounds by 100). Raw temperature
is signed hundredths Celsius (Linux converts to tenths by dividing by ten).
Current is signed microamps carried in a u32; do not interpret discharge as a
large unsigned current. Voltage is microvolts. Keep validity separate from
values so a real zero percent remains representable.

## Required implementation order

1. Boot the matching ADSP firmware with its PAS, reserved-memory, power,
   clock and interrupt requirements. GPU ZAP success does not boot ADSP.
2. Implement ADSP SMEM/GLINK edge and interrupt signaling, then RPMSG channel
   negotiation. No GLINK/RPMSG implementation was found in the current XNU
   patches during this inspection.
3. Observe charger protection-domain readiness and restart/down events.
4. Bind owner 32778 on `PMIC_RTR_ADSP_APPS`. Serialize requests, use a bounded
   timeout (stock driver uses 1000 ms), correlate the requested property and
   drain/reset after timeout. The wire format has no transaction ID.
5. Acquire present/status/capacity/voltage/current/temperature/full/design
   capacity and USB-online, keeping per-property validity and timestamps.
   Invalidate stale observations on transport/PDR down.
6. Publish measured values through the existing IOPMPowerSource service,
   with explicit unit conversion and charging-state mapping. Advertise
   unknown data as unknown rather than reporting a fabricated full battery.

Existing patch 0062 is a PM6150-specific bring-up implementation with synthetic
defaults and optional voltage-derived capacity. It is not evidence of an FP6
gauge, and arbitrary SPMI probing must not be substituted for the stock ADSP
path. Its UI defaults should only be replaced once the real transport can
report valid observations; the protocol header does not alter current UI.
