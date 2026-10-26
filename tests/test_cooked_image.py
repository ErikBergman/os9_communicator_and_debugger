import hashlib
from pathlib import Path
import struct
import sys
import tempfile
import unittest

TOOLS = Path(__file__).resolve().parents[1] / "tools/freddi_fisk"
sys.path.insert(0, str(TOOLS))
from inspect_cooked_image import inspect, partitions
sys.path.remove(str(TOOLS))


def directory_record(name, extent, size, directory=False):
    record = bytearray(33 + len(name) + (len(name) % 2 == 0))
    record[0] = len(record)
    struct.pack_into("<I", record, 2, extent)
    struct.pack_into(">I", record, 6, extent)
    struct.pack_into("<I", record, 10, size)
    struct.pack_into(">I", record, 14, size)
    record[25], record[32] = 2 if directory else 0, len(name)
    record[33:33 + len(name)] = name
    return record


def sample_iso():
    image = bytearray(24 * 2048)
    descriptor = bytearray(2048)
    descriptor[:7] = b"\x01CD001\x01"
    descriptor[40:72] = b"TEST_DISC".ljust(32)
    struct.pack_into("<I", descriptor, 80, 24)
    struct.pack_into("<H", descriptor, 128, 2048)
    root = directory_record(b"\0", 20, 2048, True)
    descriptor[156:156 + len(root)] = root
    image[16 * 2048:17 * 2048] = descriptor
    listing = root + directory_record(b"\1", 20, 2048, True)
    listing += directory_record(b"FREDDI2.HE0;1", 21, 7)
    image[20 * 2048:20 * 2048 + len(listing)] = listing
    image[21 * 2048:21 * 2048 + 7] = b"example"
    return image


class CookedImageTests(unittest.TestCase):
    def test_iso_inventory_keeps_source_identity_and_hashes_file_extent(self):
        with tempfile.TemporaryDirectory() as tmp:
            source, output = Path(tmp) / "disc.iso", Path(tmp) / "inspection"
            original = bytes(sample_iso())
            source.write_bytes(original)
            before = source.stat()
            report = inspect(source, output)
            self.assertEqual(source.read_bytes(), original)
            self.assertEqual(source.stat().st_mtime_ns, before.st_mtime_ns)
            self.assertEqual(report["source"]["sha256"], hashlib.sha256(original).hexdigest())
            entry, = report["iso9660"]["entries"]
            self.assertEqual(entry["path"], "FREDDI2.HE0")
            self.assertEqual(entry["sha256"], hashlib.sha256(b"example").hexdigest())
            self.assertIsNone(report["hfs"])
            with self.assertRaises(FileExistsError):
                inspect(source, output)

    def test_partition_extents_outside_image_are_rejected(self):
        image = sample_iso()
        image[512:514] = b"PM"
        struct.pack_into(">III", image, 516, 1, 0, len(image) // 512 + 1)
        with self.assertRaisesRegex(ValueError, "beyond the image"):
            partitions(image)

    def test_raw_sector_input_is_rejected_without_creating_output(self):
        with tempfile.TemporaryDirectory() as tmp:
            source, output = Path(tmp) / "raw.img", Path(tmp) / "inspection"
            source.write_bytes(b"\0" * 2352)
            with self.assertRaisesRegex(ValueError, "2048-byte"):
                inspect(source, output)
            self.assertFalse(output.exists())
