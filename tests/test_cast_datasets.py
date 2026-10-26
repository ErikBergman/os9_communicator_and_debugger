import hashlib
import wave
import json
import sys
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

TOOLS = Path(__file__).resolve().parents[1] / "tools/freddi_fisk"
sys.path.insert(0, str(TOOLS))
import prepare_cast_datasets as cast
sys.path.remove(str(TOOLS))


class CastDatasetTests(unittest.TestCase):
    def fixtures(self, root):
        speech, scripts = root / "speech", root / "scripts"
        speech.mkdir()
        scripts.mkdir()
        scene = scripts / "scene.scu"
        scene.write_text('script 200 {\nactor 2 \\\n talk-color 181 \\\n talkie 1 "@T100,20@Hello"\\\n\n'
                         'actor 2 \\\n talkie 2 "@T200,20@Unknown speaker"\\\n\n}\n')
        cues = {"script_sha256": {"scene.scu": cast.digest(scene)}, "rooms": {
            "scene.scu": {"sha256": cast.digest(scene), "colors": {"181": "sam"}}},
            "notes": {}, "selection": "test cues"}
        cue_file = root / "cues.json"
        cue_file.write_text(json.dumps(cues))
        pcm = bytes([127, 132, 140, 120]) * 1000
        source = speech / "speech100.wav"
        with wave.open(str(source), "wb") as wav:
            wav.setparams((1, 1, 8000, 0, "NONE", "not compressed"))
            wav.writeframes(pcm)
        row = {"offset": 100, "resource_bytes": 20, "file": source.name,
               "sample_rate": 8000, "duration_seconds": .5,
               "pcm_sha256": hashlib.sha256(pcm).hexdigest()}
        (speech / "manifest.json").write_text(json.dumps({"source_sha256": "source", "clips": [row]}))
        return speech, scripts, cue_file, cues

    def test_ambiguous_actor_reuse_does_not_inherit_speaker_and_changed_script_fails(self):
        with tempfile.TemporaryDirectory() as tmp:
            _, scripts, _, cues = self.fixtures(Path(tmp))
            with patch.object(cast, "fish_refs", return_value={}), patch.object(cast, "shark_refs", return_value={}):
                refs = cast.cast_refs(scripts, cues)
                self.assertEqual(set(refs), {100})
                self.assertEqual(refs[100][0]["speaker"], "sam")
                (scripts / "scene.scu").write_text("changed")
                with self.assertRaisesRegex(ValueError, "checksum"):
                    cast.cast_refs(scripts, cues)

    def test_short_source_is_accounted_for_and_resuming_verifies_audio(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            speech, scripts, cues, _ = self.fixtures(root)
            output = root / "dataset"
            with patch.object(cast, "CUE_FILE", cues), patch.object(cast, "PROFILES", {"sam": {"name": "Sam"}}), \
                    patch.object(cast, "shark_refs", return_value={}):
                report = cast.prepare(speech, scripts, output)
                self.assertEqual(report["summary"]["sam"]["train"]["seconds"], .5)
                self.assertEqual(report["summary"]["sam"]["validation"]["clips"], 0)
                self.assertGreater(report["clips"][0]["training_repetitions"], 1)
                self.assertEqual(set(report["references"]["sam"]["offsets"]), {100})
                self.assertTrue(report["references"]["sam"]["repeated"])
                cast.verify(output)
                (output / report["clips"][0]["file"]).write_bytes(b"changed")
                with self.assertRaisesRegex(ValueError, "WAV changed"):
                    cast.verify(output)


if __name__ == "__main__":
    unittest.main()
