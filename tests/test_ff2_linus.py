import hashlib
import json
from pathlib import Path
import sys
import tempfile
import unittest
from unittest.mock import patch
import wave

TOOLS = Path(__file__).resolve().parents[1] / "tools/freddi_fish2"
sys.path.insert(0, str(TOOLS))
import prepare_linus_dataset as dataset
sys.path.remove(str(TOOLS))


class EnglishLinusDatasetTests(unittest.TestCase):
    def test_requires_both_actor_and_explicit_colour_and_handles_both_marker_styles(self):
        with tempfile.TemporaryDirectory() as tmp:
            p = Path(tmp) / "room.scu"
            p.write_text('say-line 2 \\\n color 232 \\\n "\\x7FT8,100\\x7FHello Freddi!"\n'
                         'say-line 3 \\\n color 232 \\\n "\x7fT108,100\x7fOther actor"\n'
                         'say-line 2 \\\n color 228 \\\n "\x7fT208,100\x7fOther colour"\n'
                         'say-line 2 \\\n "\x7fT308,100\x7fNo explicit colour"\n'
                         'say-line 2 \\\n color 232 \\\n "\x7fT408,100\x7fSecond marker style"\n')
            refs, _ = dataset.dialogue_refs(tmp)
            self.assertEqual(set(refs), {8, 408})

    def test_duration_balance_keeps_validation_and_reserve_out_of_training(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            speech, scripts, output = root / "speech", root / "scripts", root / "dataset"
            speech.mkdir(); scripts.mkdir()
            rows, lines = [], []
            for i in range(20):
                pcm = bytes([120 + i]) * 11025
                name = f"speech{i}.wav"
                with wave.open(str(speech / name), "wb") as wav:
                    wav.setparams((1, 1, 11025, 0, "NONE", "not compressed")); wav.writeframes(pcm)
                rows.append({"offset": i, "resource_bytes": 11100, "duration_seconds": 1,
                             "sample_rate": 11025, "pcm_sha256": hashlib.sha256(pcm).hexdigest(), "file": name})
                lines.append(f'say-line 2 \\\n color 232 \\\n "\x7fT{i},11100\x7fLine {i}"\n')
            (scripts / "room.scu").write_text("".join(lines))
            (speech / "manifest.json").write_text(json.dumps({"source_sha256": dataset.SPEECH_SHA256, "clips": rows}))
            report = dataset.prepare(speech, scripts, output, budget=5)
            self.assertEqual(report["summary"]["train"]["seconds"], 5)
            self.assertGreater(report["summary"]["reserve"]["clips"], 0)
            selected = report["clips"]
            train_hashes = {row["pcm_sha256"] for row in selected if row["split"] == "train"}
            other_hashes = {row["pcm_sha256"] for row in selected if row["split"] != "train"}
            self.assertFalse(train_hashes & other_hashes)
            self.assertTrue(all('/train/' in row["file"] for row in selected if row["split"] == "train"))
            with self.assertRaises(FileExistsError):
                dataset.prepare(speech, scripts, output, budget=5)
