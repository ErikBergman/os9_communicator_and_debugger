import importlib.util
import struct
import tempfile
import unittest
import wave
from pathlib import Path

SPEC = importlib.util.spec_from_file_location(
    "extract_speech", Path(__file__).resolve().parents[1]
    / "tools/freddi_fisk/extract_speech.py")
speech = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(speech)


def chunk(tag, payload):
    return tag + struct.pack(">I", len(payload) + 8) + payload


def archive(pcm=b"\x80\x81\x7f\xff\x00"):
    header = b"\0\0\x80\x80\xff\xff" + struct.pack("<H", 11025) + bytes(8)
    return chunk(b"TLKB", chunk(b"TALK", chunk(b"HSHD", header) + chunk(b"SDAT", pcm)))


class SpeechTests(unittest.TestCase):
    def test_encrypted_and_plain_pcm_match(self):
        plain = archive()
        decoded = list(speech.speech_records(plain))
        self.assertEqual(decoded, list(speech.speech_records(plain.translate(speech.XOR_TABLE))))
        self.assertEqual(decoded[0][0]["offset"], 8)
        self.assertEqual(decoded[0][1], b"\x80\x81\x7f\xff\x00")

    def test_invalid_chunk_sizes_fail(self):
        plain = archive()
        for size in (0, 7, 100000):
            damaged = plain[:12] + struct.pack(">I", size) + plain[16:]
            with self.assertRaises(ValueError):
                list(speech.speech_records(damaged))
        with self.assertRaises(ValueError):
            list(speech.speech_records(plain[:-1]))

    def test_source_and_output_are_preserved(self):
        with tempfile.TemporaryDirectory() as tmp:
            source, output = Path(tmp) / "source", Path(tmp) / "export"
            source.write_bytes(archive().translate(speech.XOR_TABLE))
            before = source.read_bytes(), source.stat().st_mtime_ns
            report = speech.extract(source, output)
            self.assertEqual(before, (source.read_bytes(), source.stat().st_mtime_ns))
            self.assertTrue(report["source_unchanged"])
            with wave.open(str(output / "speech8.wav"), "rb") as wav:
                self.assertEqual((wav.getnchannels(), wav.getsampwidth(), wav.getframerate()), (1, 1, 11025))
                self.assertEqual(wav.readframes(100), b"\x80\x81\x7f\xff\x00")
            with self.assertRaises(FileExistsError):
                speech.extract(source, output)


if __name__ == "__main__":
    unittest.main()
