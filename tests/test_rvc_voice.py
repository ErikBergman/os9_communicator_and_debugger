import importlib.util
import json
import sys
import tempfile
import types
import unittest
from pathlib import Path
from unittest.mock import Mock, patch

SPEC = importlib.util.spec_from_file_location(
    "rvc_voice", Path(__file__).resolve().parents[1] / "tools/freddi_fisk/rvc_voice.py")
rvc = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(rvc)
WORKER_SPEC = importlib.util.spec_from_file_location(
    "rvc_worker", Path(__file__).resolve().parents[1] / "tools/freddi_fisk/rvc_infer_worker.py")
worker = importlib.util.module_from_spec(WORKER_SPEC)
WORKER_SPEC.loader.exec_module(worker)


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

    def test_progress_wrapper_does_not_hide_a_missing_model_export(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            exp = root / "logs/swedish-linus-v2"
            exp.mkdir(parents=True)
            (exp / "preparation.json").write_text('{}')
            (exp / "config.json").write_text(json.dumps({"train": {"log_interval": 50}}))
            with patch.object(rvc, "RVC", root), patch.object(rvc, "run") as run:
                with self.assertRaisesRegex(RuntimeError, "did not export"):
                    rvc.train("linus", False, 20)
            args = list(map(str, run.call_args.args[0]))
            self.assertTrue(args[0].endswith("rvc_train_progress.py"))
            self.assertIn("train.train", args)
            self.assertEqual(json.loads((exp / "config.json").read_text())["train"]["log_interval"], 10)


class WorkerExitTests(unittest.TestCase):
    def test_mac_worker_flushes_and_preserves_failure_status(self):
        out, err = Mock(), Mock()

        def exit_after_flush(status):
            out.flush.assert_called_once()
            err.flush.assert_called_once()
            raise SystemExit(status)

        cli = types.ModuleType("infer.cli")
        cli.main = lambda: 1
        with patch.dict(sys.modules, {"infer.cli": cli}), patch.object(sys, "platform", "darwin"), patch.object(sys, "stdout", out), patch.object(sys, "stderr", err), patch.object(worker.os, "_exit", side_effect=exit_after_flush):
            with self.assertRaises(SystemExit) as result:
                worker.main()
            self.assertEqual(result.exception.code, 1)

    def test_non_mac_worker_uses_normal_exit(self):
        cli = types.ModuleType("infer.cli")
        cli.main = lambda: 0
        with patch.dict(sys.modules, {"infer.cli": cli}), patch.object(sys, "platform", "linux"), patch.object(worker.os, "_exit") as hard_exit:
            self.assertEqual(worker.main(), 0)
            hard_exit.assert_not_called()


if __name__ == "__main__":
    unittest.main()
