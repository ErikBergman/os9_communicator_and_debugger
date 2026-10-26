import csv
import hashlib
import html
import json
import re
import struct
import sys
import tempfile
import unittest
import wave
from pathlib import Path

TOOLS = Path(__file__).resolve().parents[1] / "tools/freddi_fish2"
sys.path.insert(0, str(TOOLS))
import prepare_dubbing as dubbing
sys.path.remove(str(TOOLS))


def chunk(tag, body):
    return tag + struct.pack(">I", len(body) + 8) + body


class DubbingPreparationTests(unittest.TestCase):
    def fixture(self, root, missing_reference=False):
        work, output = root / "work", root / "work/dubbing"
        for name in ("game", "speech", "scripts/Freddi2"):
            (work / name).mkdir(parents=True, exist_ok=True)
        lines = b'\x7fT8,120\x7f(PU1)Hello, Freddi!\0'
        lines += b'\x7fT8,120\x7fHello again, Freddi!\0'
        if not missing_reference:
            lines += b'\x7fT128,120\x7fHello, Luther!\0'
        archive = chunk(b"LECF", chunk(b"LFLF", chunk(b"RMDA", chunk(b"LSC2", struct.pack("<I", 2050) + lines))))
        index = chunk(b"DLFL", struct.pack("<HII", 2, 0, 16))
        index += chunk(b"RNAM", b'\x01\0test-room\0\0\0')
        (work / "game/Freddi2.(a)").write_bytes(archive.translate(dubbing.XOR))
        (work / "game/Freddi2.HE0").write_bytes(index.translate(dubbing.XOR))
        (work / "game/Freddi2.HE2").write_bytes(b"test speech source")
        expected = {name: dubbing.digest(work / "game" / name) for name in dubbing.EXPECTED}
        clips = []
        for offset in (8, 128):
            pcm = bytes([128, 130, 140, 125]) * 1000
            name = f"speech{offset}.wav"
            with wave.open(str(work / "speech" / name), "wb") as wav:
                wav.setparams((1, 1, 11025, 0, "NONE", "not compressed"))
                wav.writeframes(pcm)
            clips.append({"offset": offset, "resource_bytes": 120, "file": name,
                          "sample_rate": 11025, "frames": len(pcm), "duration_seconds": len(pcm) / 11025,
                          "pcm_sha256": hashlib.sha256(pcm).hexdigest()})
        (work / "speech/manifest.json").write_text(json.dumps({"source_sha256": expected["Freddi2.HE2"], "clips": clips}))
        (work / "scripts/Freddi2/0001_test.scu").write_text(
            'say-line 2 \\\n color 232 \\\n "\\x7FT8,120\\x7FHello, Freddi!"\n'
            'say-line 2 \\\n "\x7fT128,120\x7fNo explicit speaker colour"\n')
        return work, output, expected

    def test_complete_archive_catalogue_retains_variants_and_does_not_infer_shared_actor(self):
        with tempfile.TemporaryDirectory() as tmp:
            work, output, expected = self.fixture(Path(tmp))
            catalogue = dubbing.build(work, output, expected)
            self.assertEqual(catalogue["summary"]["clips"], 2)
            self.assertEqual(catalogue["summary"]["archive_references"], 3)
            linus, unresolved = catalogue["clips"]
            self.assertEqual(linus["suggested_character"], "linus")
            self.assertEqual(unresolved["suggested_character"], "")
            self.assertEqual(linus["english_variants"], ["Hello, Freddi!", "Hello again, Freddi!"])
            self.assertEqual(linus["occurrences"][0]["prefix"], "(PU1)")
            self.assertIn("multiple_english_texts_share_audio", linus["flags"])
            self.assertEqual(linus["occurrences"][0]["resource_path"][-1]["tag"], "LSC2")
            decoded = (work / "game/Freddi2.(a)").read_bytes().translate(dubbing.XOR)
            for row in catalogue["clips"]:
                for occurrence in row["occurrences"]:
                    offset, size = occurrence["text_offset"], occurrence["text_bytes"]
                    self.assertEqual(decoded[offset:offset + size].decode("ascii"), occurrence["raw_text"])
                    self.assertEqual(decoded[offset + size], 0)
            for name, checksum in expected.items():
                self.assertEqual(dubbing.digest(work / "game" / name), checksum)
            page = output / "review/room-01.html"
            for audio in re.findall(r'src="([^"]+)"', page.read_text()):
                self.assertTrue((page.parent / html.unescape(audio)).resolve().is_file())

    def test_rerun_cannot_overwrite_translation_work_and_swedish_edits_survive_review(self):
        with tempfile.TemporaryDirectory() as tmp:
            work, output, expected = self.fixture(Path(tmp))
            catalogue = dubbing.build(work, output, expected)
            path = output / "translations.csv"
            rows = dubbing.read_sheet(catalogue, path)
            rows[0].update(swedish="På vår ö finns ålar.", status="draft")
            # CSV editors may rewrite a numeric cell without changing its value.
            rows[0]["original_seconds"] += "0"
            with path.open("w", encoding="utf-8-sig", newline="") as stream:
                writer = csv.DictWriter(stream, fieldnames=dubbing.FIELDS)
                writer.writeheader()
                writer.writerows(rows)
            before = path.read_bytes()
            dubbing.write_review(catalogue, dubbing.read_sheet(catalogue, path), output / "review")
            self.assertEqual(path.read_bytes(), before)
            self.assertIn("På vår ö finns ålar.", (output / "review/room-01.html").read_text())
            with self.assertRaises(FileExistsError):
                dubbing.build(work, output, expected)
            self.assertEqual(path.read_bytes(), before)

    def test_missing_audio_reference_and_damaged_wav_are_rejected_before_publication(self):
        for missing in (True, False):
            with self.subTest(missing=missing), tempfile.TemporaryDirectory() as tmp:
                work, output, expected = self.fixture(Path(tmp), missing_reference=missing)
                if not missing:
                    with wave.open(str(work / "speech/speech8.wav"), "rb") as wav:
                        params = wav.getparams()
                    with wave.open(str(work / "speech/speech8.wav"), "wb") as wav:
                        wav.setparams(params)
                        wav.writeframes(b"\x80" * 4000)
                with self.assertRaises(ValueError):
                    dubbing.build(work, output, expected)
                self.assertFalse(output.exists())

    def test_sheet_rejects_source_changes_unknown_voices_and_incomplete_approval(self):
        for field, value in (("english", "Changed original"), ("voice_profile", "english-linus-freddi2-v2"),
                             ("status", "approved"), ("id", "unknown-id")):
            with self.subTest(field=field), tempfile.TemporaryDirectory() as tmp:
                work, output, expected = self.fixture(Path(tmp))
                catalogue = dubbing.build(work, output, expected)
                path = output / "translations.csv"
                rows = dubbing.read_sheet(catalogue, path)
                rows[0][field] = value
                with path.open("w", encoding="utf-8-sig", newline="") as stream:
                    writer = csv.DictWriter(stream, fieldnames=dubbing.FIELDS)
                    writer.writeheader()
                    writer.writerows(rows)
                with self.assertRaises(ValueError):
                    dubbing.read_sheet(catalogue, path)

    def test_freddi_requires_explicit_colour_and_ego_or_selected_actor(self):
        with tempfile.TemporaryDirectory() as tmp:
            source = Path(tmp) / "room.scu"
            source.write_text('say-line \\\n color 228 \\\n "\\x7FT8,120\\x7FHi, Linus!"\n'
                              'say-line 3 \\\n color 228 \\\n "\x7fT128,120\x7fShared actor"\n'
                              'say-line \\\n "\x7fT248,120\x7fNo colour"\n')
            refs, _ = dubbing.script_evidence(Path(tmp))
            self.assertEqual(refs[8][0]["speaker"], "freddi")
            self.assertIsNone(refs[128][0]["speaker"])
            self.assertIsNone(refs[248][0]["speaker"])


if __name__ == "__main__":
    unittest.main()
