import http.client
import json
import sys
import tempfile
import threading
import time
import unittest
import wave
from pathlib import Path
from unittest.mock import patch

TOOLS = Path(__file__).resolve().parents[1] / "tools/freddi_fisk"
sys.path.insert(0, str(TOOLS))
from text_to_voice import VoiceStudio
from voice_studio import StudioServer
import setup_voice_tools
sys.path.remove(str(TOOLS))


def fake_model(root, speaker="freddi", suffix="-smoke"):
    name = f"swedish-{speaker}-v2{suffix}"
    weights = root / ".local-tools/rvc/assets/weights"
    experiment = root / ".local-tools/rvc/logs" / name
    weights.mkdir(parents=True, exist_ok=True)
    experiment.mkdir(parents=True, exist_ok=True)
    (weights / (name + ".pth")).write_bytes(b"test model")
    (experiment / "added_test.index").write_bytes(b"test index")
    if speaker in ("boss", "spongehead"):
        (experiment / "completed-training.json").write_text('{"epochs":20}')
    python = root / ".local-tools/rvc-venv/bin/python"
    python.parent.mkdir(parents=True, exist_ok=True)
    python.touch()


def render_fixture(job, profile, rate, pitch, folder, progress):
    progress("synthesizing")
    progress("converting")
    with wave.open(str(folder / "voice.wav"), "wb") as wav:
        wav.setparams((1, 2, 32000, 0, "NONE", "not compressed"))
        wav.writeframes(b"\x00\x01" * 16000)


class StudioTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.root = Path(self.temp.name)
        fake_model(self.root)
        self.studio = VoiceStudio(self.root, render_fixture, self.root / "app-data")

    def tearDown(self):
        self.studio.close()
        self.temp.cleanup()

    def test_input_validation_and_local_output(self):
        for text in (None, " ", "a" * 401):
            with self.assertRaises(ValueError): self.studio.create(text, "freddi")
        for voice in (None, "../../private", "alva", [], {}):
            with self.assertRaises(ValueError): self.studio.create("Hej", voice)
        for field, value in (("pitch", True), ("pitch", 13), ("rate", "160")):
            with self.assertRaises(ValueError): self.studio.create("Hej", "freddi", **{field: value})
        job = self.studio.create("  Hej på dig, ål!  ", "freddi")
        for _ in range(100):
            job = self.studio.get(job["id"])
            if job["state"] == "done": break
            time.sleep(.01)
        self.assertEqual(job["state"], "done")
        self.assertEqual(job["text"], "Hej på dig, ål!")
        self.assertEqual(job["duration"], .5)
        self.assertTrue((self.root / "app-data/recordings" / job["id"] / "voice.wav").exists())

    def test_full_model_replaces_preview_without_mixing_indexes(self):
        self.assertEqual(self.studio.profiles()["freddi"]["kind"], "preview")
        fake_model(self.root, suffix="")
        profile = self.studio.profiles()["freddi"]
        self.assertEqual(profile["kind"], "trained")
        self.assertEqual(profile["model"].stem, "swedish-freddi-v2")
        self.assertEqual(profile["index"].parent.name, "swedish-freddi-v2")

    def test_local_runtime_takes_precedence_over_cloud_repository(self):
        local = self.root / "app-data"
        fake_model(local)
        (local / ".local-tools").rename(local / "runtime")
        studio = VoiceStudio(self.root, render_fixture, local)
        try:
            self.assertEqual(studio.python, local / "runtime/rvc-venv/bin/python")
            self.assertEqual(studio.profiles()["freddi"]["model"].parents[3], local / "runtime")
        finally:
            studio.close()

    def test_both_sharks_use_separate_trained_model_index_pairs(self):
        self.assertEqual(set(self.studio.status()["voices"]), {"freddi", "linus", "boss", "spongehead"})
        for speaker in ("boss", "spongehead"):
            fake_model(self.root, speaker=speaker, suffix="")
            profile = self.studio.profiles()[speaker]
            self.assertEqual(profile["model"].stem, f"swedish-{speaker}-v2")
            self.assertEqual(profile["index"].parent.name, f"swedish-{speaker}-v2")
            job = self.studio.create("Här kommer hajarna!", speaker)
            for _ in range(100):
                job = self.studio.get(job["id"])
                if job["state"] == "done":
                    break
                time.sleep(.01)
            self.assertEqual(job["state"], "done", job)
            self.assertEqual(job["speaker"], speaker)
            self.assertEqual(job["model_kind"], "trained")

    def test_shark_is_unavailable_until_training_export_is_complete(self):
        fake_model(self.root, speaker="boss", suffix="")
        record = self.root / ".local-tools/rvc/logs/swedish-boss-v2/completed-training.json"
        record.unlink()
        self.assertFalse(self.studio.status()["voices"]["boss"]["available"])

    def test_copying_shark_profile_preserves_completion_record(self):
        fake_model(self.root, speaker="boss", suffix="")
        fake_model(self.root, speaker="spongehead", suffix="")
        record = self.root / ".local-tools/rvc/logs/swedish-spongehead-v2/completed-training.json"
        record.unlink()
        destination = self.root / "installed"
        with patch.object(setup_voice_tools, "ROOT", self.root), \
                patch.object(setup_voice_tools, "LOCAL", destination):
            setup_voice_tools.profiles()
        copied = destination / "rvc/logs/swedish-boss-v2/completed-training.json"
        self.assertEqual(json.loads(copied.read_text())["epochs"], 20)
        self.assertFalse((destination / "rvc/assets/weights/swedish-spongehead-v2.pth").exists())


class HTTPTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        root = Path(self.temp.name)
        fake_model(root)
        self.studio = VoiceStudio(root, render_fixture, root / "app-data")
        self.server = StudioServer(("127.0.0.1", 0), self.studio)
        self.thread = threading.Thread(target=self.server.serve_forever, daemon=True)
        self.thread.start()

    def tearDown(self):
        self.server.shutdown()
        self.server.server_close()
        self.studio.close()
        self.temp.cleanup()

    def request(self, method, path, body=None, headers=None):
        connection = http.client.HTTPConnection("127.0.0.1", self.server.server_port)
        connection.request(method, path, body=body, headers=headers or {})
        response = connection.getresponse()
        result = response.status, response.read(), response.getheader("Content-Type")
        connection.close()
        return result

    def test_swedish_text_roundtrip_and_audio(self):
        status, body, _ = self.request("POST", "/api/jobs", json.dumps({"text": "Hej, skärgården!", "speaker": "freddi"}), {"Content-Type": "application/json"})
        self.assertEqual(status, 202)
        job = json.loads(body)
        for _ in range(100):
            status, body, _ = self.request("GET", "/api/jobs/" + job["id"])
            job = json.loads(body)
            if job["state"] == "done": break
            time.sleep(.01)
        self.assertEqual(job["text"], "Hej, skärgården!")
        status, body, content_type = self.request("GET", job["audio_url"])
        self.assertEqual((status, content_type), (200, "audio/wav"))
        self.assertEqual(body[:4], b"RIFF")

    def test_cross_origin_and_path_traversal_are_rejected(self):
        status, _, _ = self.request("POST", "/api/jobs", '{}', {"Content-Type": "application/json", "Origin": "https://example.com"})
        self.assertEqual(status, 403)
        for path in ("/audio/../../etc/passwd", "/api/jobs/../", "/../text_to_voice.py"):
            self.assertEqual(self.request("GET", path)[0], 404)
        self.assertEqual(self.request("GET", "/api/status", headers={"Host": "example.com"})[0], 403)

    def test_bad_json_and_missing_voice_are_reported(self):
        self.assertEqual(self.request("POST", "/api/jobs", '{', {"Content-Type": "application/json"})[0], 400)
        self.assertEqual(self.request("POST", "/api/jobs", '{}', {"Content-Type": "text/plain"})[0], 415)
        status, _, _ = self.request("POST", "/api/jobs", json.dumps({"text": "Hej", "speaker": "linus"}), {"Content-Type": "application/json"})
        self.assertEqual(status, 503)
        for engine, expected in (("chatterbox", 503), ("unknown", 400)):
            body = json.dumps({"text": "Hej", "speaker": "freddi", "engine": engine})
            self.assertEqual(self.request("POST", "/api/jobs", body,
                             {"Content-Type": "application/json"})[0], expected)


if __name__ == "__main__":
    unittest.main()
