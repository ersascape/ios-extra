# GPU ARC metadata inventory: patch 0082

The complete 0081 measurement found CX/GX collapsed at boot. Before adding
rail votes, patch `0082-sweet-gpu-arc-inventory.patch` reads the firmware's
resource addresses and level tables for `gfx.lvl`, `cx.lvl` and `mx.lvl`.
These are ARC voltage-corner resources, distinct from the display client's
PMIC LDO millivolt commands.

## Opt-in and access boundary

- `sweetgpu=0` or absent: GPU probe remains disabled.
- `sweetgpu=1`: existing guarded clock inventory, without command DB maps.
- **`sweetgpu=2`**: the clock inventory plus the ARC metadata snapshot.
- Other modes are rejected without mapping hardware.

ARC collection maps only the known board command DB locator at
`0x0c3f000c` (8 bytes) and the reserved-RAM database described by it. It does
not call the RPMh voltage helper, map RSC/TCS registers, submit a command,
change a clock/domain, load firmware or map GPU/GMU/SMMU core registers.
The existing GPUCC access guard is unchanged.

The locator policy matches the existing board client: 32-bit physical RAM
at or above `0x80000000`, 4-byte aligned address/size, database size from
144 bytes through 1 MiB, and no wrap past the 4 GiB boundary. The snapshot
requires command DB version 1, the expected magic and standalone bit clear.
Version 1 is a conservative policy, not a general version-support claim.
The firmware checksum is printed raw; checksum integrity is not verified.

## Parser contract

The layout is derived from the pinned downstream
[`cmd-db.c`](https://github.com/MiCode/Xiaomi_Kernel_OpenSource/blob/758bb7ef50af360e728662a1ed3b3a1b977a2f13/drivers/soc/qcom/cmd-db.c),
[`kgsl_gmu.c`](https://github.com/MiCode/Xiaomi_Kernel_OpenSource/blob/758bb7ef50af360e728662a1ed3b3a1b977a2f13/drivers/gpu/msm/kgsl_gmu.c#L594)
and
[`rpmh-regulator.c`](https://github.com/MiCode/Xiaomi_Kernel_OpenSource/blob/758bb7ef50af360e728662a1ed3b3a1b977a2f13/drivers/regulator/rpmh-regulator.c#L1244).

The collector visits at most eight slave headers, ending at the first zero
slave ID. Entry and auxiliary offsets are relative to the data area at byte
144. It checks each complete entry-table range before scanning 24-byte
entries, and checks each requested resource's auxiliary range before reading
it. Arithmetic uses bounded unsigned offsets and subtraction-based range
checks. Invalid slave-table geometry invalidates the database result.

A requested resource must occur exactly once, belong to ARC slave 3 and
have a 4-byte aligned command address with the ARC slave ID in address bits
18:16. The auxiliary payload must be an even, nonzero length of at most
32 bytes: up to sixteen little-endian uint16 values. Duplicate identities,
missing resources, wrong slave/address type and invalid payload ranges are
reported explicitly. One failed resource does not hide the other resources.

All physical loads are aligned 32-bit loads with the existing read barrier.
The uint16 decoder also handles auxiliary offsets that cross aligned word
boundaries. It never issues an unaligned Device halfword load.

For each usable resource the report includes its address, raw auxiliary
version, both priority words and **every raw table entry**, including zero
padding, as `hlvl=<index> vlvl=<value>`. The collector deliberately does not
convert these values to millivolts, trim entries, infer supported corners or
interpret the priority words as an owned vote. Ordering, corner selection,
dependencies and actual voting need their own validated contract.

## Cached reporting

ARC fields are part of the immutable boot inventory published by 0081.
The existing initial and ~5/15/30-second reports carry the same cached ARC
data and numbered BEGIN/END markers. No replay maps or re-reads the locator,
database or hardware. Failure outcomes are cached too. ARC reporting is
independent of whether the clock inventory had to skip GPUCC.

The display's existing `sweet_rpmh.c` remains unchanged. New implementation
is confined to `sweet_gpu.c`; no new source-list entry, thread or heap
allocation is needed.

## Validation and next hardware test

The host harness applies the full GPU patch chain, replacing only the ARM
barrier for host execution. It passes 14 clock/cache cases and 30 ARC cases,
plus 512 deterministic mutations of database headers/entries. Cases include
locator bounds, mapping failures, malformed/oversized tables, missing and
duplicate resources, wrong slave IDs, maximum payload, exact end-of-database
reads, odd auxiliary offsets, immutable replay and byte-for-byte absence of
locator/database writes. ASan/UBSan also passes this same harness.

All three repository unit tests pass. Real arm64 Mach-O compilation against
the isolated XNU headers passes (0 of 1 files failed), using the 0081 CI log.
Full linkage and the next phone boot are separate checks, pending at this
implementation milestone.

The intended phone test uses the normal UFS-root image with `sweetgpu=2`,
the host `tools/phone-ecm-host.py` watcher and an independent UDP capture.
Require a complete report containing all three resources or explicit failure
reasons, retain raw metadata/levels, and verify normal UI/USB operation.
Do not infer a successful rail vote from metadata inspection.
