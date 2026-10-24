import importlib.util
import tempfile
import unittest
from pathlib import Path

SPEC = importlib.util.spec_from_file_location(
    "voice_datasets", Path(__file__).resolve().parents[1]
    / "tools/freddi_fisk/prepare_voice_datasets.py")
datasets = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(datasets)


class SpeakerCueTests(unittest.TestCase):
    def test_only_explicit_dialogue_positions_label_speakers(self):
        with tempfile.TemporaryDirectory() as tmp:
            Path(tmp, "room.scu").write_text(
                'say-line \\\n\tat V.270,V.271 \\\n\t"@T8,100@Hello Linus"\n'
                'say-line L.1 \\\n\tat V.272,V.273 \\\n\t"@T108,200@Hello Freddi"\n'
                'say-line 1 \\\n\t"@T308,20@Another voice sharing actor 1"\n'
                'actor 1 \\\n\ttalkie 1 "@T328,20@Cutscene voice"\n')
            refs = datasets.dialogue_refs(tmp)
            self.assertEqual(set(refs), {8, 108})
            self.assertEqual(refs[8][0]["speaker"], "freddi")
            self.assertEqual(refs[108][0]["speaker"], "linus")

    def test_conflicts_remain_visible_in_evidence(self):
        with tempfile.TemporaryDirectory() as tmp:
            Path(tmp, "room.scu").write_text(
                'say-line \\\n\tat V.270,V.271 \\\n\t"@T8,100@First"\n'
                'say-line \\\n\tat V.272,V.273 \\\n\t"@T8,100@Conflicting"\n')
            refs = datasets.dialogue_refs(tmp)
            self.assertEqual({r["speaker"] for r in refs[8]}, {"freddi", "linus"})

    def test_unsigned_to_signed_conversion_is_lossless(self):
        self.assertEqual(datasets.signed16(bytes((0, 127, 128, 129, 255))),
                         b"\x00\x80\x00\xff\x00\x00\x00\x01\x00\x7f")


if __name__ == "__main__":
    unittest.main()
