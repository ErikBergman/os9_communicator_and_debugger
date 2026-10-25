import hashlib
import json
import sys
import tempfile
import time
import unittest
import wave
from pathlib import Path
from unittest.mock import Mock, patch

TOOLS = Path(__file__).resolve().parents[1] / "tools/freddi_fisk"
sys.path.insert(0, str(TOOLS))
import chatterbox_guide
import setup_chatterbox
from text_to_voice import UnavailableError, VoiceStudio
from test_voice_studio import fake_model
sys.path.remove(str(TOOLS))


def wav_file(path, seconds=4):
    path.parent.mkdir(parents=True, exist_ok=True)
    with wave.open(str(path), "wb") as wav:
        wav.setparams((1, 2, 16000, 0, "NONE", "not compressed"))
        wav.writeframes(b"\x00\x01" * (16000 * seconds))


class ChatterboxTests(unittest.TestCase):
    def test_worker_requests_swedish_and_character_reference(self):
        model, writer = Mock(), Mock()
        model.sr = 24000
        chatterbox_guide.generate_guide(model, "Hej på dig!", Path("freddi.wav"),
                                        Path("guide.wav"), .9, writer)
        model.generate.assert_called_once_with("Hej på dig!", language_id="sv",
                                              audio_prompt_path="freddi.wav",
                                              exaggeration=.9, cfg_weight=.3)
        self.assertEqual(writer.call_args.args[0], "guide.wav")
        self.assertEqual(writer.call_args.args[2], 24000)
        self.assertEqual(writer.call_args.kwargs, {"subtype": "PCM_16"})

    def test_installed_chatterbox_runs_before_trained_rvc(self):
        with tempfile.TemporaryDirectory() as tmp, \
                patch("text_to_voice.CHATTERBOX", {"models": {"model.pt": {"size": 5}}}):
            root = Path(tmp)
            fake_model(root, suffix="")
            studio = VoiceStudio(root, data_home=root / "app-data")
            try:
                studio.chatterbox_python.parent.mkdir(parents=True)
                studio.chatterbox_python.touch()
                models = studio.chatterbox / "models"
                models.mkdir(parents=True)
                (models / "model.pt").write_bytes(b"model")
                (studio.chatterbox / "installed.json").write_text("{}")
                wav_file(studio.chatterbox / "references/freddi.wav")
                self.assertTrue(studio.status()["voices"]["freddi"]["chatterbox_available"])
                calls = []

                def command(arguments, log, env=None, timeout=180):
                    calls.append((list(map(str, arguments)), env, timeout))
                    if "--output" in arguments:
                        output = Path(arguments[arguments.index("--output") + 1])
                    else:
                        output = Path(arguments[-1])
                    wav_file(output)

                studio.command = command
                job = studio.create("Hej Linus!", "freddi", rate=130, exaggeration=.9)
                for _ in range(100):
                    job = studio.get(job["id"])
                    if job["state"] in ("done", "error"):
                        break
                    time.sleep(.01)
                self.assertEqual(job["state"], "done", job)
                self.assertEqual(job["engine"], "chatterbox")
                self.assertEqual(len(calls), 3)
                self.assertIn("chatterbox_guide.py", calls[0][0][1])
                self.assertIn(str(studio.chatterbox / "references/freddi.wav"), calls[0][0])
                self.assertEqual(calls[0][1]["HF_HUB_OFFLINE"], "1")
                self.assertNotIn("PYTHONPATH", calls[0][1])
                self.assertIn("atempo=0.8125", calls[1][0])
                self.assertIn("rvc_infer_worker.py", calls[2][0][1])
                self.assertIn(str(studio.profiles()["freddi"]["model"]), calls[2][0])
                # An explicitly selected Alva remains available for comparisons.
                studio.create("Hej!", "freddi", engine="alva")
            finally:
                studio.close()

    def test_missing_installation_and_bad_settings_do_not_fall_back_silently(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            fake_model(root)
            studio = VoiceStudio(root, data_home=root / "app-data")
            try:
                with self.assertRaises(UnavailableError):
                    studio.create("Hej", "freddi", engine="chatterbox")
                for settings in ({"engine": "unknown"}, {"exaggeration": True},
                                 {"exaggeration": float("nan")}, {"exaggeration": 2}):
                    with self.assertRaises(ValueError):
                        studio.create("Hej", "freddi", **settings)
                self.assertEqual(studio.status()["default_engine"], "alva")
            finally:
                studio.close()

    def test_reference_selection_uses_existing_training_clips_and_keeps_overrides(self):
        with tempfile.TemporaryDirectory() as tmp:
            runtime, dataset = Path(tmp) / "runtime", Path(tmp) / "dataset"
            dataset.mkdir()
            rows = []
            for speaker in ("freddi", "linus"):
                for split, duration in (("train", 4), ("train", 7), ("validation", 8)):
                    relative = f"{speaker}/{split}/{duration}.wav"
                    wav_file(dataset / relative, duration)
                    rows.append({"speaker": speaker, "split": split, "file": relative,
                                 "duration_seconds": duration})
            (dataset / "manifest.json").write_text(json.dumps({"clips": rows}))
            self.assertEqual(setup_chatterbox.choose_reference(dataset, "freddi").name, "7.wav")
            setup_chatterbox.install_references(runtime, dataset=dataset)
            manifest = runtime / "chatterbox/references/references.json"
            first = manifest.read_text()
            setup_chatterbox.install_references(runtime, dataset=dataset)
            self.assertEqual(manifest.read_text(), first)

    def test_verification_rejects_corrupt_same_size_models(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            model = root / "chatterbox/models/model.pt"
            model.parent.mkdir(parents=True)
            model.write_bytes(b"wrong")
            spec = {"models": {"model.pt": {"size": 5,
                    "sha256": hashlib.sha256(b"right").hexdigest()}}}
            with patch.object(setup_chatterbox, "VERSIONS", spec):
                with self.assertRaisesRegex(RuntimeError, "checksum"):
                    setup_chatterbox.verify_models(root)


if __name__ == "__main__":
    unittest.main()
