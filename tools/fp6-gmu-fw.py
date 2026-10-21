#!/usr/bin/env python3
"""Validate and convert FP6 Gen8.3 GMU firmware to a C data-block header.

The input format follows Qualcomm's ``gmu_block_header`` in KGSL:
four little-endian u32 values (address, payload size, type, value), followed
by ``size`` bytes.  Zero-size preallocation records precede loadable blocks.
The output retains all preallocation descriptors and the payload blocks.
"""

from __future__ import annotations

import argparse
import hashlib
import struct
import sys
import urllib.request
from dataclasses import dataclass
from pathlib import Path


SOURCE_COMMIT = "e58a5be8fa0fb6bc5a5f2e29cc01c036ccf75710"
SOURCE_URL = (
    "https://raw.githubusercontent.com/FairBlobs/FP6-firmware/"
    f"{SOURCE_COMMIT}/gen80300_gmu.bin"
)
SOURCE_SHA256 = "6adcbf43b162fb4bdc00154824f44c5f96d82a223cfbe7012d5904098f5bf2fc"
SOURCE_SIZE = 88708

HEADER = struct.Struct("<4I")
BLK_TYPE_PREALLOC_REQ = 1
BLK_TYPE_PREALLOC_PERSIST_REQ = 7
BLK_TYPE_DATA_SENTINEL = 0xEFBEADDE

# Gen8 GMU virtual address map from adreno_gen8_gmu.c.  A firmware data block
# must fit wholly inside one mapping; a block cannot straddle a VMA boundary.
GMU_VMAS = (
    (0x00000000, 0x00004000, "ITCM"),
    (0x00004000, 0x01000000, "cache"),
    (0x10004000, 0x10008000, "DTCM"),
    (0x60000000, 0x80000000, "noncached-kernel"),
    (0xC0000000, 0xE0000000, "noncached-kernel-extended"),
)


@dataclass(frozen=True)
class Block:
    address: int
    size: int
    kind: int
    value: int
    payload: bytes
    header_offset: int


@dataclass(frozen=True)
class Preallocation:
    address: int
    size: int
    kind: int
    header_offset: int


@dataclass(frozen=True)
class Firmware:
    preallocations: tuple[Preallocation, ...]
    blocks: tuple[Block, ...]


class FirmwareError(ValueError):
    """The blob is malformed or does not match the pinned FP6 firmware."""


def _contained_vma(address: int, size: int) -> str | None:
    end = address + size
    if end > 0x1_0000_0000:
        return None
    for start, limit, name in GMU_VMAS:
        if start <= address and end <= limit:
            return name
    return None


def parse_firmware(blob: bytes) -> Firmware:
    """Parse the Linux/KGSL block stream and reject malformed layouts."""
    if not blob:
        raise FirmwareError("empty firmware")

    offset = 0
    seen_payload = False
    payload_blocks: list[Block] = []
    preallocations: list[Preallocation] = []
    while offset < len(blob):
        if len(blob) - offset < HEADER.size:
            raise FirmwareError(f"truncated block header at 0x{offset:x}")
        header_offset = offset
        address, size, kind, value = HEADER.unpack_from(blob, offset)
        offset += HEADER.size

        if size == 0:
            if seen_payload:
                raise FirmwareError(
                    f"zero-size metadata block after payload at 0x{header_offset:x}"
                )
            if kind not in (BLK_TYPE_PREALLOC_REQ, BLK_TYPE_PREALLOC_PERSIST_REQ):
                raise FirmwareError(
                    f"unsupported metadata block type {kind} at 0x{header_offset:x}"
                )
            if value == 0:
                raise FirmwareError(
                    f"invalid preallocation range at 0x{header_offset:x}"
                )
            if _contained_vma(address, value) is None:
                raise FirmwareError(
                    f"preallocation range 0x{address:x}+0x{value:x} is outside GMU VMAs"
                )
            preallocations.append(
                Preallocation(address, value, kind, header_offset)
            )
            continue

        seen_payload = True
        if kind != BLK_TYPE_DATA_SENTINEL:
            raise FirmwareError(
                f"unexpected data block marker 0x{kind:08x} at 0x{header_offset:x}"
            )
        if value != 0xEFBEADDE:
            raise FirmwareError(
                f"unexpected data block value 0x{value:08x} at 0x{header_offset:x}"
            )
        if address & 3 or size & 3:
            raise FirmwareError(
                f"unaligned data block address/size at 0x{header_offset:x}"
            )
        vma = _contained_vma(address, size)
        if vma is None:
            raise FirmwareError(
                f"data block 0x{address:x}+0x{size:x} is outside a single GMU VMA"
            )
        end = offset + size
        if end < offset or end > len(blob):
            raise FirmwareError(
                f"truncated payload at 0x{offset:x}: need 0x{size:x} bytes"
            )
        for previous in payload_blocks:
            previous_end = previous.address + previous.size
            if address < previous_end and previous.address < address + size:
                raise FirmwareError(
                    f"overlapping data blocks at 0x{address:x} and 0x{previous.address:x}"
                )
        payload_blocks.append(
            Block(address, size, kind, value, blob[offset:end], header_offset)
        )
        offset = end

    if not payload_blocks:
        raise FirmwareError("firmware has no nonempty data blocks")
    if not preallocations:
        raise FirmwareError("firmware is missing its preallocation metadata")
    return Firmware(tuple(preallocations), tuple(payload_blocks))


def verify_pinned_blob(blob: bytes) -> Firmware:
    if len(blob) != SOURCE_SIZE:
        raise FirmwareError(f"wrong firmware size: {len(blob)} (expected {SOURCE_SIZE})")
    actual = hashlib.sha256(blob).hexdigest()
    if actual != SOURCE_SHA256:
        raise FirmwareError(f"firmware SHA-256 mismatch: {actual}")
    return parse_firmware(blob)


def emit_header(firmware: Firmware, output: Path) -> None:
    """Write C data and descriptors for a later XNU firmware loader."""
    lines = [
        "/* Generated by tools/fp6-gmu-fw.py; do not edit or commit firmware. */",
        "#ifndef FP6_GMU_FW_GENERATED_H",
        "#define FP6_GMU_FW_GENERATED_H",
        "#include <stdint.h>",
        "struct fp6_gmu_fw_preallocation {",
        "\tuint32_t address, size, type;",
        "};",
        "struct fp6_gmu_fw_block {",
        "\tuint32_t address, size, type, value;",
        "\tconst uint8_t *data;",
        "};",
    ]
    lines.append("static const struct fp6_gmu_fw_preallocation fp6_gmu_fw_preallocations[] = {")
    for item in firmware.preallocations:
        lines.append(
            f"\t{{ 0x{item.address:08x}, 0x{item.size:08x}, 0x{item.kind:08x} }},"
        )
    lines.append("};")
    lines.append(f"#define FP6_GMU_FW_PREALLOCATION_COUNT {len(firmware.preallocations)}u")
    for index, block in enumerate(firmware.blocks):
        lines.append(f"static const uint8_t fp6_gmu_fw_data_{index}[0x{block.size:x}] = {{")
        for start in range(0, block.size, 12):
            chunk = block.payload[start : start + 12]
            lines.append("\t" + ", ".join(f"0x{byte:02x}" for byte in chunk) + ",")
        lines.append("};")
    lines.extend(
        [
            "static const struct fp6_gmu_fw_block fp6_gmu_fw_blocks[] = {",
        ]
    )
    for index, block in enumerate(firmware.blocks):
        lines.append(
            f"\t{{ 0x{block.address:08x}, 0x{block.size:08x}, "
            f"0x{block.kind:08x}, 0x{block.value:08x}, fp6_gmu_fw_data_{index} }},"
        )
    lines.extend(
        [
            "};",
            f"#define FP6_GMU_FW_BLOCK_COUNT {len(firmware.blocks)}u",
            f"#define FP6_GMU_FW_SOURCE_SHA256 \"{SOURCE_SHA256}\"",
            "#endif",
            "",
        ]
    )
    output.write_text("\n".join(lines), encoding="ascii")


def read_source(path: Path | None) -> bytes:
    if path is not None:
        return path.read_bytes()
    with urllib.request.urlopen(SOURCE_URL, timeout=30) as response:
        return response.read(SOURCE_SIZE + 1)


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--source", type=Path, help="local firmware file (still SHA-pinned)")
    parser.add_argument("--output", type=Path, required=True, help="generated C header path")
    args = parser.parse_args(argv)
    try:
        blob = read_source(args.source)
        firmware = verify_pinned_blob(blob)
        emit_header(firmware, args.output)
    except (OSError, FirmwareError, TimeoutError) as exc:
        print(f"fp6-gmu-fw: {exc}", file=sys.stderr)
        return 1
    print(
        f"validated {len(blob)} bytes ({hashlib.sha256(blob).hexdigest()}); "
        f"generated {len(firmware.preallocations)} preallocations and "
        f"{len(firmware.blocks)} GMU data blocks in {args.output}"
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
