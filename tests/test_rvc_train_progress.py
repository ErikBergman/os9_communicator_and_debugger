import importlib.util
import io
import sys
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from rich.console import Console

SPEC = importlib.util.spec_from_file_location(
    "rvc_train_progress", Path(__file__).resolve().parents[1] /
    "tools/freddi_fisk/rvc_train_progress.py")
display = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(display)


class ProgressTests(unittest.TestCase):
    def test_translated_records_and_invalid_progress(self):
        for line in ("Training epoch: 7 [25%]", "训练轮次：7 [25%]",
                     "Époque d'entraînement : 7 [25%]"):
            self.assertEqual(display.parse_progress(line, 20), (7, 25, False))
        for line in ("====> Epoch: 7 time=1:23", "====> 轮次：7 time=1:23"):
            self.assertEqual(display.parse_progress(line, 20), (7, 100, True))
        for line in ("Training epoch: 0 [25%]", "Training epoch: 21 [0%]",
                     "Training epoch: 7 [101%]", "loss_gen=2.5", "====> Epoch: 21"):
            self.assertIsNone(display.parse_progress(line, 20))

    def test_stale_logs_partial_utf8_and_truncation(self):
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / "train.log"
            path.write_text("====> Epoch: 20 old run\n")
            tail = display.LogTail(path)
            self.assertEqual(tail.read(), [])
            record = "训练轮次：5 [50%]\n".encode()
            with path.open("ab") as log:
                log.write(record[:2])
            self.assertEqual(tail.read(), [])
            with path.open("ab") as log:
                log.write(record[2:])
            self.assertEqual(tail.read(), ["训练轮次：5 [50%]"])
            path.write_text("new\n")
            self.assertEqual(tail.read(), ["new"])

    def test_resumed_subprocess_updates_bars_and_retains_raw_output(self):
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / "train.log"
            path.write_text("====> Epoch: 20 stale\n")
            output = io.StringIO()
            console = Console(file=output, force_terminal=True, color_system=None, width=120)
            script = (
                "import pathlib,time; p=pathlib.Path('train.log'); "
                "f=p.open('a'); "
                "f.write('Training epoch: 5 [50%]\\n'); f.flush(); time.sleep(.05); "
                "f.write('====> Epoch: 5 time=00:01\\n'); f.close(); print('raw diagnostic')"
            )
            # The real wrapper runs from RVC's directory; use an absolute log
            # path here so the test never changes the runner's working directory.
            script = script.replace("pathlib.Path('train.log')", f"pathlib.Path({str(path)!r})")
            status = display.monitor([sys.executable, "-c", script], tmp, 10,
                                     "Linus", console, poll_interval=.01)
            self.assertEqual(status, 0)
            self.assertIn("epoch 5/10", output.getvalue())
            self.assertIn("50%", output.getvalue())
            self.assertNotIn("epoch 20", output.getvalue())
            self.assertIn("raw diagnostic", (Path(tmp) / "training-console.log").read_text())

    def test_failure_keeps_exit_status_and_prints_diagnostics(self):
        with tempfile.TemporaryDirectory() as tmp:
            output = io.StringIO()
            console = Console(file=output, width=120)
            status = display.monitor(
                [sys.executable, "-c", "import sys; print('specific trainer failure'); sys.exit(7)"],
                tmp, 20, "Freddi", console, poll_interval=.01)
            self.assertEqual(status, 7)
            self.assertIn("specific trainer failure", output.getvalue())
            self.assertNotIn("Epochs complete", output.getvalue())

    def test_interruption_stops_the_trainer(self):
        with tempfile.TemporaryDirectory() as tmp:
            console = Console(file=io.StringIO())
            with patch.object(display.LogTail, "read", side_effect=KeyboardInterrupt), \
                    patch.object(display, "stop_training", wraps=display.stop_training) as stop:
                with self.assertRaises(KeyboardInterrupt):
                    display.monitor([sys.executable, "-c", "import time; time.sleep(30)"],
                                    tmp, 20, "Freddi", console)
                self.assertIsNotNone(stop.call_args.args[0].poll())


if __name__ == "__main__":
    unittest.main()
