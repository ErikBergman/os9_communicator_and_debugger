import importlib.util
import io
import os
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
            path = Path(tmp) / "training-console.log"
            path.write_text("====> Epoch: 20 stale\n")
            output = io.StringIO()
            console = Console(file=output, force_terminal=True, color_system=None, width=120)
            script = (
                "import time; "
                "print('Training epoch: 5 [50%]', flush=True); time.sleep(.05); "
                "print('====> Epoch: 5 time=00:01', flush=True); print('raw diagnostic')"
            )
            status = display.monitor([sys.executable, "-c", script], tmp, 10,
                                     "Linus", console, poll_interval=.01)
            self.assertEqual(status, 0)
            self.assertIn("epoch 5/10", output.getvalue())
            self.assertIn("50%", output.getvalue())
            self.assertNotIn("epoch 20", output.getvalue())
            self.assertIn("raw diagnostic", (Path(tmp) / "training-console.log").read_text())

    def test_eta_excludes_resumed_epochs_and_uses_current_pace(self):
        estimate = display.completion_estimate(20, 6, 5, 120, 300)
        self.assertEqual(estimate, "~28m remaining (live pace)")
        self.assertEqual(display.completion_estimate(20, 5.25, 5.25, 0, 195),
                         "~48m remaining (previous epoch)")

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

    def test_pause_waits_for_saved_epoch_and_stops_the_worker_group(self):
        with tempfile.TemporaryDirectory() as tmp:
            folder = Path(tmp)
            pause = folder / "pause"
            pause.touch()
            script = (
                "import subprocess,sys,signal; from pathlib import Path; "
                "p=subprocess.Popen([sys.executable,'-c','import time; time.sleep(30)']); "
                "signal.signal(signal.SIGINT,lambda *args:(p.wait(),sys.exit(130))); "
                f"Path({str(folder / 'pid')!r}).write_text(str(p.pid)); "
                f"Path({str(folder / 'G.pth')!r}).write_text('saved generator'); "
                f"Path({str(folder / 'D.pth')!r}).write_text('saved discriminator'); "
                "print('====> Epoch: 1 saved',flush=True); p.wait()"
            )
            output = io.StringIO()
            status = display.monitor([sys.executable, "-c", script], folder, 20, "Cast",
                                     Console(file=output), .01, pause_file=pause, save_every=1)
            self.assertEqual(status, 75)
            self.assertEqual((folder / "G.pth").read_text(), "saved generator")
            self.assertEqual((folder / "D.pth").read_text(), "saved discriminator")
            self.assertIn("Paused after epoch 1", output.getvalue())
            with self.assertRaises(ProcessLookupError):
                os.kill(int((folder / "pid").read_text()), 0)


if __name__ == "__main__":
    unittest.main()
