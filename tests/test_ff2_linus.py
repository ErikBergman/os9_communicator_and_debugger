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
import compare_linus
from check_linus_words import word_errors
import train_linus
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


class LinusComparisonTests(unittest.TestCase):
    def test_six_outputs_share_guides_and_cached_rerun_does_not_synthesize_again(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            runtime, output = root / "runtime", root / "comparison"
            for experiment in ("swedish-linus-v2", compare_linus.ENGLISH_EXPERIMENT):
                model = runtime / "rvc/assets/weights" / f"{experiment}.pth"
                model.parent.mkdir(parents=True, exist_ok=True)
                model.write_bytes(experiment.encode())
                folder = runtime / "rvc/logs" / experiment
                folder.mkdir(parents=True)
                (folder / "added_test.index").write_bytes(b"index")
                (folder / "completed-training.json").write_text(json.dumps({"epochs": 20, "model_sha256": compare_linus.digest(model)}))
            reference = runtime / "chatterbox/references/linus.wav"
            reference.parent.mkdir(parents=True)
            reference.write_bytes(b"reference")
            commands = []

            class FakeStudio:
                ffmpeg = "ffmpeg"

                def close(self):
                    pass

                def command(self, arguments, log, env=None, timeout=180):
                    args = list(map(str, arguments))
                    commands.append(args)
                    if args[-1] == "-":
                        log.write(json.dumps({"input_i": "-20", "input_tp": "-4", "input_lra": "1",
                                              "input_thresh": "-30", "target_offset": "0"}))
                        return
                    target = Path(args[args.index("--output") + 1]) if "--output" in args else Path(args[-1])
                    with wave.open(str(target), "wb") as wav:
                        wav.setparams((1, 2, 32000, 0, "NONE", "not compressed"))
                        wav.writeframes(b"\x00\x01" * 16000)

            with patch.object(compare_linus, "VoiceStudio", FakeStudio):
                results = compare_linus.render(runtime, output)
                rvc_calls = [args for args in commands if any("rvc_infer_worker.py" in value for value in args)]
                self.assertEqual(len(rvc_calls), 6)
                for number in range(3):
                    pair = rvc_calls[number * 2:number * 2 + 2]
                    self.assertEqual(pair[0][pair[0].index("--input") + 1], pair[1][pair[1].index("--input") + 1])
                    self.assertIn("swedish-linus-v2.pth", pair[0][pair[0].index("--model") + 1])
                    self.assertIn("english-linus-freddi2-v2.pth", pair[1][pair[1].index("--model") + 1])
                self.assertEqual(len(list(output.glob("*.wav"))), 9)
                before = len(commands)
                self.assertEqual(compare_linus.render(runtime, output), results)
                self.assertEqual(len(commands), before)

    def test_word_check_keeps_swedish_letters_and_counts_missing_words(self):
        expected = "På vår ö finns sju gröna sjöstjärnor."
        self.assertEqual(word_errors(expected, expected.upper())["edits"], 0)
        self.assertEqual(word_errors(expected, "På vår ö finns gröna sjöstjärnor.")["edits"], 1)
        self.assertEqual(word_errors("ål", "al")["edits"], 1)

    def test_ab_wav_plays_swedish_model_first_then_silence_then_english_model(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            for name, value in (("a.wav", b"\x01\x00"), ("b.wav", b"\x02\x00")):
                with wave.open(str(root / name), "wb") as wav:
                    wav.setparams((1, 2, 32000, 0, "NONE", "not compressed"))
                    wav.writeframes(value * 320)
            compare_linus.paired_wav(root / "a.wav", root / "b.wav", root / "ab.wav", gap_seconds=.01)
            with wave.open(str(root / "ab.wav"), "rb") as wav:
                self.assertEqual(wav.getnframes(), 960)
                self.assertEqual(wav.readframes(960), b"\x01\x00" * 320 + b"\0\0" * 320 + b"\x02\x00" * 320)

    def test_silent_recording_is_rejected(self):
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / "silent.wav"
            with wave.open(str(path), "wb") as wav:
                wav.setparams((1, 2, 32000, 0, "NONE", "not compressed"))
                wav.writeframes(b"\0\0" * 320)
            with self.assertRaisesRegex(ValueError, "Silent"):
                compare_linus.wave_info(path)


class EnglishLinusTrainingTests(unittest.TestCase):
    def test_training_uses_separate_model_and_resumes_without_touching_swedish_baseline(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            runtime, work = root / "runtime", root / "work"
            dataset_root = work / "linus-english-dataset"
            dataset_root.mkdir(parents=True)
            (dataset_root / "manifest.json").write_text('{}')
            baseline = runtime / "rvc/assets/weights/swedish-linus-v2.pth"
            baseline.parent.mkdir(parents=True)
            baseline.write_bytes(b"native Swedish model")
            exp = runtime / "rvc/logs" / train_linus.EXPERIMENT
            exp.mkdir(parents=True)
            (exp / "preparation.json").write_text('{}')

            def complete(command, **kwargs):
                self.assertEqual(command[2:4], ["train", "linus"])
                self.assertEqual(command[-2:], ["--epochs", "20"])
                self.assertEqual(command[command.index("--experiment") + 1], "english-linus-freddi2-v2")
                model = baseline.parent / "english-linus-freddi2-v2.pth"
                model.write_bytes(b"English model")
                (exp / "added_test.index").write_bytes(b"English index")
                (exp / "completed-training.json").write_text(json.dumps({"epochs": 20, "model_sha256": train_linus.digest(model)}))

            with patch.object(train_linus.subprocess, "run", side_effect=complete) as run:
                train_linus.train(runtime, work)
                train_linus.train(runtime, work)
                self.assertEqual(run.call_count, 1)
            self.assertEqual(baseline.read_bytes(), b"native Swedish model")
