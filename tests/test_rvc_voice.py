import importlib.util
import json
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

SPEC = importlib.util.spec_from_file_location(
    "rvc_voice", Path(__file__).resolve().parents[1] / "tools/freddi_fisk/rvc_voice.py")
rvc = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(rvc)


class TrainingInputTests(unittest.TestCase):
    def make_inputs(self, root):
        train = root / "datasets/freddi/train"
        validation = root / "datasets/freddi/validation"
        train.mkdir(parents=True)
        validation.mkdir(parents=True)
        for i in range(3):
            (train / f"speech{i}.wav").write_bytes(b"training input")
        (validation / "held-out.wav").write_bytes(b"must never train on this")

    def test_validation_is_excluded_from_normal_and_smoke_inputs(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            self.make_inputs(root)
            with patch.object(rvc, "WORK", root):
                for smoke in (False, True):
                    selected = rvc.input_files("freddi", smoke)
                    self.assertEqual({p.name for p in selected}, {f"speech{i}.wav" for i in range(3)})
                    self.assertFalse(any("validation" in p.parts for p in selected))

    def test_changed_inputs_cannot_reuse_previous_features(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            self.make_inputs(root)
            exp = root / "rvc/logs/swedish-freddi-v2"
            exp.mkdir(parents=True)
            (exp / "input-files.json").write_text(json.dumps({"previous.wav": "old digest"}))
            with patch.object(rvc, "WORK", root), patch.object(rvc, "RVC", root / "rvc"), patch.object(rvc, "run") as run:
                with self.assertRaisesRegex(RuntimeError, "Training input changed"):
                    rvc.prepare("freddi", False)
                run.assert_not_called()


if __name__ == "__main__":
    unittest.main()
