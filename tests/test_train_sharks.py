import fcntl
import json
import sys
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

TOOLS = Path(__file__).resolve().parents[1] / "tools/freddi_fisk"
sys.path.insert(0, str(TOOLS))
import train_sharks
sys.path.remove(str(TOOLS))


class SharkTrainingTests(unittest.TestCase):
    def runtime(self, folder):
        root = Path(folder)
        python = root / "rvc-venv/bin/python"
        python.parent.mkdir(parents=True)
        python.touch()
        dataset = root / "shark-datasets"
        dataset.mkdir()
        (dataset / "manifest.json").write_text(json.dumps({
            "cues_sha256": train_sharks.digest(TOOLS / "shark-speaker-cues.json"),
            "summary": {speaker: {"train": {"clips": 3}} for speaker in ("boss", "spongehead")}}))
        return root

    def test_each_shark_is_prepared_fully_trained_and_resumed_without_retraining(self):
        with tempfile.TemporaryDirectory() as tmp:
            runtime = self.runtime(tmp)
            actions = []

            def fake_run(command, env, check):
                action, speaker = command[2:4]
                self.assertEqual(env["RVC_TRAIN_THREADS"], "2")
                self.assertEqual(command[command.index("--runtime-root") + 1], str(runtime))
                self.assertTrue(check)
                actions.append((action, speaker))
                experiment = runtime / "rvc/logs" / f"swedish-{speaker}-v2"
                experiment.mkdir(parents=True, exist_ok=True)
                if action == "prepare":
                    (experiment / "preparation.json").write_text("{}")
                else:
                    self.assertEqual(command[command.index("--epochs") + 1], "20")
                    model = runtime / "rvc/assets/weights" / f"swedish-{speaker}-v2.pth"
                    model.parent.mkdir(parents=True, exist_ok=True)
                    model.write_bytes(speaker.encode())
                    (experiment / "added_test.index").write_bytes(b"index")

            with patch.object(train_sharks, "dialogue_refs"), \
                    patch.object(train_sharks, "copy_pretrained"), \
                    patch.object(train_sharks, "install_references") as references, \
                    patch.object(train_sharks.subprocess, "run", side_effect=fake_run):
                train_sharks.train_all(runtime, 20, 2)
                self.assertEqual(actions, [(action, speaker) for speaker in ("boss", "spongehead")
                                           for action in ("prepare", "train")])
                references.assert_called_once_with(runtime, dataset=runtime / "shark-datasets",
                                                   speakers=("boss", "spongehead"))
                for speaker in ("boss", "spongehead"):
                    record = runtime / "rvc/logs" / f"swedish-{speaker}-v2/completed-training.json"
                    self.assertEqual(json.loads(record.read_text())["epochs"], 20)
                actions.clear()
                train_sharks.train_all(runtime, 20, 2)
                self.assertEqual(actions, [])

    def test_second_launcher_cannot_start_duplicate_trainers(self):
        with tempfile.TemporaryDirectory() as tmp:
            runtime = self.runtime(tmp)
            with (runtime / "shark-training.lock").open("a") as lock:
                fcntl.flock(lock, fcntl.LOCK_EX | fcntl.LOCK_NB)
                with self.assertRaisesRegex(RuntimeError, "already running"):
                    train_sharks.train_all(runtime, 20, 2)


if __name__ == "__main__":
    unittest.main()
