import fcntl
import os
import signal
import json
import sys
import tempfile
import unittest
from types import SimpleNamespace
from pathlib import Path
from unittest.mock import patch

TOOLS = Path(__file__).resolve().parents[1] / "tools/freddi_fisk"
sys.path.insert(0, str(TOOLS))
import train_cast as trainer
sys.path.remove(str(TOOLS))


class CastRunnerTests(unittest.TestCase):
    def fixture(self, root):
        runtime = Path(root)
        python = runtime / "rvc-venv/bin/python"
        python.parent.mkdir(parents=True)
        python.touch()
        dataset = runtime / "cast-datasets"
        dataset.mkdir()
        report = {"summary": {}, "references": {}, "notes": {}}
        for speaker in ("grandma", "ray"):
            source = dataset / speaker / "train/source.wav"
            source.parent.mkdir(parents=True)
            source.write_bytes(speaker.encode())
            report["summary"][speaker] = {"train": {"clips": 1, "seconds": 3}}
            report["references"][speaker] = {"file": "reference.wav"}
        (dataset / "manifest.json").write_text(json.dumps(report))
        return runtime, report

    def test_batch_resumes_interrupted_voice_and_skips_completed_voice(self):
        with tempfile.TemporaryDirectory() as tmp:
            runtime, report = self.fixture(tmp)
            actions, pause_once = [], [True]

            def fake_run(runner, command, env, training=False):
                action, speaker = command[2:4]
                actions.append((action, speaker))
                self.assertEqual(env["RVC_TRAIN_THREADS"], "2")
                folder = trainer.experiment(runtime, speaker)
                folder.mkdir(parents=True, exist_ok=True)
                if action == "prepare":
                    for name in ("preparation.json", "config.json"):
                        (folder / name).write_text("{}")
                    source = runtime / "cast-datasets" / speaker / "train/source.wav"
                    (folder / "filelist.txt").write_text("|".join([str(source)] * 4 + ["0"]) + "\n")
                    trainer.atomic_json(folder / "input-files.json", {source.name: trainer.digest(source)})
                    (folder / "added_test.index").write_bytes(b"index")
                elif speaker == "ray" and pause_once[0]:
                    (folder / "G_2333333.pth").write_bytes(b"checkpoint")
                    pause_once[0] = False
                    return trainer.PAUSED
                else:
                    self.assertIn("--save-every", command)
                    self.assertEqual(command[command.index("--epochs") + 1], "20")
                    model = trainer.model_path(runtime, speaker)
                    model.parent.mkdir(parents=True, exist_ok=True)
                    model.write_bytes(speaker.encode())
                    trainer.atomic_json(folder / "completed-training.json", {
                        "epochs": 20, "model_sha256": trainer.digest(model)})
                return 0

            with patch.object(trainer, "verify", return_value=report), \
                    patch.object(trainer.shutil, "disk_usage", return_value=SimpleNamespace(free=64 * 1024**3)), \
                    patch.object(trainer, "import_legacy_fish"), patch.object(trainer, "copy_pretrained"), \
                    patch.object(trainer, "install_references"), \
                    patch.object(trainer.Runner, "run", fake_run):
                self.assertEqual(trainer.train_all(runtime, 20, 2, ["grandma", "ray"]), trainer.PAUSED)
                self.assertEqual(trainer.completed_epochs(runtime, "grandma"), 20)
                self.assertEqual(trainer.train_all(runtime, 20, 2, ["grandma", "ray"]), 0)
                self.assertEqual(actions, [("prepare", "grandma"), ("train", "grandma"),
                                           ("prepare", "ray"), ("train", "ray"), ("train", "ray")])
                trainer.model_path(runtime, "grandma").write_bytes(b"damaged")
                with self.assertRaisesRegex(RuntimeError, "changed"):
                    trainer.completed_epochs(runtime, "grandma")

    def test_first_interrupt_requests_checkpoint_pause_without_signalling_worker(self):
        with tempfile.TemporaryDirectory() as tmp:
            runner = trainer.Runner(Path(tmp))
            runner.training = True
            runner.active = type("Process", (), {"pid": 12345})()
            with patch.object(os, "killpg") as kill:
                runner.request_pause(signal.SIGINT, None)
                self.assertTrue(runner.pause_file.exists())
                kill.assert_not_called()
                runner.request_pause(signal.SIGINT, None)
                kill.assert_called_once_with(12345, signal.SIGINT)

    def test_duplicate_batch_is_rejected_before_any_training(self):
        with tempfile.TemporaryDirectory() as tmp:
            runtime, _ = self.fixture(tmp)
            with (runtime / "cast-training.lock").open("a") as lock:
                fcntl.flock(lock, fcntl.LOCK_EX | fcntl.LOCK_NB)
                with self.assertRaisesRegex(RuntimeError, "already running"):
                    trainer.train_all(runtime, 20, 2, ["grandma"])

    def test_missing_index_does_not_count_as_prepared(self):
        with tempfile.TemporaryDirectory() as tmp:
            folder = Path(tmp)
            for name in ("preparation.json", "config.json", "filelist.txt", "input-files.json"):
                (folder / name).write_text("{}")
            self.assertFalse(trainer.prepared(folder))

    def test_compact_keeps_interrupted_checkpoints_and_finished_voice_artifacts(self):
        with tempfile.TemporaryDirectory() as tmp:
            runtime = Path(tmp)
            for speaker in ("grandma", "ray", "boss"):
                folder = trainer.experiment(runtime, speaker)
                folder.mkdir(parents=True)
                for name in ("G_2333333.pth", "D_2333333.pth", "added_test.index"):
                    (folder / name).write_bytes(b"checkpoint or index")
                if speaker != "ray":
                    model = trainer.model_path(runtime, speaker)
                    model.parent.mkdir(parents=True, exist_ok=True)
                    model.write_bytes(speaker.encode())
                    trainer.atomic_json(folder / "completed-training.json", {
                        "epochs": 20, "model_sha256": trainer.digest(model)})
                trainer.compact_finished(runtime, speaker)
            self.assertFalse(list(trainer.experiment(runtime, "grandma").glob("G_*.pth")))
            self.assertTrue(list(trainer.experiment(runtime, "ray").glob("G_*.pth")))
            self.assertTrue(list(trainer.experiment(runtime, "boss").glob("G_*.pth")))
            self.assertEqual(trainer.completed_epochs(runtime, "grandma"), 20)


if __name__ == "__main__":
    unittest.main()
