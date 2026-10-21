import importlib.util
import struct
import sys
import tempfile
import unittest
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
SPEC = importlib.util.spec_from_file_location(
    "fp6_gmu_fw", ROOT / "tools" / "fp6-gmu-fw.py"
)
fw = importlib.util.module_from_spec(SPEC)
sys.modules[SPEC.name] = fw
SPEC.loader.exec_module(fw)


def record(address, size, kind, value, payload=b""):
    return struct.pack("<4I", address, size, kind, value) + payload


class FP6GMUFirmwareTests(unittest.TestCase):
    def test_local_pinned_firmware_and_generated_descriptors(self):
        path = Path("/tmp/fp6-firmware/gen80300_gmu.bin")
        if not path.exists():
            self.skipTest("local FP6 firmware artifact is unavailable")
        blob = path.read_bytes()
        blocks = fw.verify_pinned_blob(blob)
        self.assertEqual(len(blocks.blocks), 4)
        self.assertEqual(
            [(b.address, b.size) for b in blocks.blocks],
            [(0x0, 0x1EC), (0x4000, 0x15768), (0x10007F98, 0x28), (0x10007FDC, 0x18)],
        )
        self.assertEqual(len(blocks.preallocations), 11)
        self.assertEqual(blocks.preallocations[0].size, 0x1EC)
        self.assertEqual(blocks.preallocations[0].kind, fw.BLK_TYPE_PREALLOC_REQ)
        with tempfile.TemporaryDirectory() as temp:
            output = Path(temp) / "fp6_gmu_fw.h"
            fw.emit_header(blocks, output)
            generated = output.read_text()
            self.assertIn("FP6_GMU_FW_BLOCK_COUNT 4u", generated)
            self.assertIn("FP6_GMU_FW_PREALLOCATION_COUNT 11u", generated)
            self.assertIn("0x00000000, 0x000001ec, 0x00000001", generated)
            self.assertIn("0x00000000, 0x000001ec", generated)
            self.assertIn(fw.SOURCE_SHA256, generated)

    def test_metadata_then_data_is_valid(self):
        blob = (
            record(0x60000000, 0, 7, 0x1000)
            + record(0, 4, fw.BLK_TYPE_DATA_SENTINEL, 0xEFBEADDE, b"ABCD")
        )
        firmware = fw.parse_firmware(blob)
        self.assertEqual(len(firmware.blocks), 1)
        self.assertEqual(firmware.blocks[0].payload, b"ABCD")
        self.assertEqual(firmware.preallocations[0].size, 0x1000)

    def test_rejects_truncated_header_or_payload(self):
        with self.assertRaisesRegex(fw.FirmwareError, "truncated block header"):
            fw.parse_firmware(b"\0" * 15)
        with self.assertRaisesRegex(fw.FirmwareError, "truncated payload"):
            fw.parse_firmware(
                record(0, 8, fw.BLK_TYPE_DATA_SENTINEL, 0xEFBEADDE, b"ABCD")
            )

    def test_rejects_bad_metadata_and_data_ranges(self):
        with self.assertRaisesRegex(fw.FirmwareError, "unsupported metadata"):
            fw.parse_firmware(record(0, 0, 2, 4))
        with self.assertRaisesRegex(fw.FirmwareError, "outside a single GMU VMA"):
            fw.parse_firmware(
                record(0, 0, 1, 0x1000)
                + record(0x3FFC, 8, fw.BLK_TYPE_DATA_SENTINEL, 0xEFBEADDE, b"12345678")
            )

    def test_rejects_metadata_after_data_and_overlapping_data(self):
        metadata = record(0x60000000, 0, 1, 0x1000)
        data = record(0, 8, fw.BLK_TYPE_DATA_SENTINEL, 0xEFBEADDE, b"12345678")
        with self.assertRaisesRegex(fw.FirmwareError, "metadata block after payload"):
            fw.parse_firmware(metadata + data + metadata)
        overlapping = record(4, 8, fw.BLK_TYPE_DATA_SENTINEL, 0xEFBEADDE, b"12345678")
        with self.assertRaisesRegex(fw.FirmwareError, "overlapping data blocks"):
            fw.parse_firmware(metadata + data + overlapping)

    def test_hash_pin_rejects_modified_firmware(self):
        path = Path("/tmp/fp6-firmware/gen80300_gmu.bin")
        if not path.exists():
            self.skipTest("local FP6 firmware artifact is unavailable")
        blob = bytearray(path.read_bytes())
        blob[-1] ^= 1
        with self.assertRaisesRegex(fw.FirmwareError, "SHA-256 mismatch"):
            fw.verify_pinned_blob(bytes(blob))


if __name__ == "__main__":
    unittest.main()
