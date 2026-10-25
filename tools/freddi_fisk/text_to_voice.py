#!/usr/bin/env python3
"""Local Swedish text -> Chatterbox or Alva -> character-specific RVC."""

import json
import os
import shutil
import signal
import subprocess
import threading
import uuid
import wave
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
MAX_TEXT = 400
TERMINAL = {"done", "error"}
APP_DATA = Path.home() / "Library/Application Support/FreddiFishVoiceStudio"
CHATTERBOX = json.loads(Path(__file__).with_name("chatterbox-versions.json").read_text())


class UnavailableError(RuntimeError):
    pass


class VoiceStudio:
    def __init__(self, root=ROOT, renderer=None, data_home=APP_DATA):
        self.root = Path(root)
        self.data_home = Path(data_home)
        runtime = self.data_home / "runtime"
        if not (runtime / "rvc-venv/bin/python").is_file():
            runtime = self.root / ".local-tools"
        self.rvc = runtime / "rvc"
        self.output = self.data_home / "recordings"
        self.python = runtime / "rvc-venv/bin/python"
        self.chatterbox_python = runtime / "chatterbox-venv/bin/python"
        self.chatterbox = runtime / "chatterbox"
        self.ffmpeg = shutil.which("ffmpeg") or "/opt/homebrew/bin/ffmpeg"
        self.jobs = {}
        self.lock = threading.Lock()
        self.executor = ThreadPoolExecutor(max_workers=1, thread_name_prefix="voice-studio")
        self.renderer = renderer or self.render
        self.active = None
        self.closed = False

    def profiles(self):
        profiles = {}
        for speaker, name in (("freddi", "Freddi"), ("linus", "Linus")):
            for suffix, kind in (("", "trained"), ("-smoke", "preview")):
                experiment = f"swedish-{speaker}-v2{suffix}"
                model = self.rvc / "assets/weights" / (experiment + ".pth")
                indexes = sorted((self.rvc / "logs" / experiment).glob("added*.index"))
                if model.is_file() and indexes:
                    profiles[speaker] = {"name": name, "kind": kind, "model": model,
                                         "index": indexes[-1]}
                    break
        return profiles

    def status(self):
        profiles = self.profiles()
        ready = {speaker: self.chatterbox_ready(speaker) for speaker in ("freddi", "linus")}
        return {"max_text": MAX_TEXT, "default_engine": "chatterbox" if any(ready.values()) else "alva",
                "engines": {"alva": {"available": True},
                            "chatterbox": {"available": any(ready.values())}}, "voices": {
            speaker: {"name": speaker.title(), "available": speaker in profiles,
                      "kind": profiles.get(speaker, {}).get("kind", "missing"),
                      "chatterbox_available": ready[speaker]}
            for speaker in ("freddi", "linus")}}

    def chatterbox_ready(self, speaker):
        if not self.chatterbox_python.is_file() or not (self.chatterbox / "installed.json").is_file():
            return False
        if not (self.chatterbox / "references" / f"{speaker}.wav").is_file():
            return False
        return all((self.chatterbox / "models" / name).is_file() and
                   (self.chatterbox / "models" / name).stat().st_size == spec["size"]
                   for name, spec in CHATTERBOX["models"].items())

    def create(self, text, speaker, rate=160, pitch=0, engine=None, exaggeration=0.6):
        if not isinstance(text, str) or not text.strip() or len(text.strip()) > MAX_TEXT:
            raise ValueError(f"Skriv mellan 1 och {MAX_TEXT} tecken.")
        if speaker not in ("freddi", "linus"):
            raise ValueError("Välj Freddi eller Linus.")
        if type(rate) is not int or rate not in (130, 160, 190):
            raise ValueError("Ogiltigt taltempo.")
        if type(pitch) is not int or not -12 <= pitch <= 12:
            raise ValueError("Tonhöjden måste vara mellan −12 och 12.")
        if engine is None:
            engine = "chatterbox" if self.chatterbox_ready(speaker) else "alva"
        if engine not in ("alva", "chatterbox"):
            raise ValueError("Välj Alva eller Chatterbox som talmotor.")
        if type(exaggeration) not in (int, float) or not 0 <= exaggeration <= 1.5:
            raise ValueError("Uttrycket måste vara mellan 0 och 1,5.")
        profile = self.profiles().get(speaker)
        if profile is None or not self.python.is_file():
            raise UnavailableError("Röstmodellen är inte installerad ännu.")
        if engine == "chatterbox" and not self.chatterbox_ready(speaker):
            raise UnavailableError("Chatterbox eller röstens referensklipp är inte installerat ännu. Välj Alva tills vidare.")
        with self.lock:
            if self.closed:
                raise UnavailableError("Röststudion håller på att stängas.")
            if sum(j["state"] not in TERMINAL for j in self.jobs.values()) >= 3:
                raise OverflowError("Kön är full. Vänta tills en inspelning är klar.")
            identifier = uuid.uuid4().hex
            self.jobs[identifier] = {"id": identifier, "text": text.strip(), "speaker": speaker,
                                     "model_kind": profile["kind"], "engine": engine,
                                     "exaggeration": exaggeration, "state": "queued"}
            self.executor.submit(self.generate, identifier, profile, rate, pitch)
        return self.get(identifier)

    def get(self, identifier):
        with self.lock:
            job = self.jobs.get(identifier)
            return dict(job) if job else None

    def update(self, identifier, **fields):
        with self.lock:
            self.jobs[identifier].update(fields)

    def generate(self, identifier, profile, rate, pitch):
        folder = self.output / identifier
        try:
            folder.mkdir(parents=True, exist_ok=False)
            job = self.get(identifier)
            self.renderer(job, profile, rate, pitch, folder,
                          lambda state: self.update(identifier, state=state))
            with wave.open(str(folder / "voice.wav"), "rb") as wav:
                if not wav.getnframes():
                    raise RuntimeError("Röstmotorn skapade en tom inspelning.")
                duration = wav.getnframes() / wav.getframerate()
            self.update(identifier, state="done", duration=duration,
                        audio_url=f"/audio/{identifier}")
        except Exception as error:
            self.update(identifier, state="error", error=str(error))
        finally:
            if folder.exists():
                (folder / "job.json").write_text(
                    json.dumps(self.get(identifier), ensure_ascii=False, indent=2) + "\n",
                    encoding="utf-8")

    def command(self, arguments, log, env=None, timeout=180):
        with self.lock:
            if self.closed:
                raise RuntimeError("Inspelningen avbröts när studion stängdes.")
            process = subprocess.Popen(list(map(str, arguments)), stdout=log, stderr=log,
                                       env=env, cwd=self.rvc, start_new_session=True)
            self.active = process
        try:
            result = process.wait(timeout=timeout)
            if result:
                raise RuntimeError("Tal eller röstkonvertering misslyckades. Detaljer finns i inspelningens engine.log.")
        except subprocess.TimeoutExpired:
            self.stop_process(process)
            raise RuntimeError("Röstmotorn tog för lång tid. Prova en kortare mening.")
        finally:
            with self.lock:
                self.active = None

    @staticmethod
    def stop_process(process):
        if process.poll() is None:
            try:
                os.killpg(process.pid, signal.SIGTERM)
            except ProcessLookupError:
                return
            try:
                process.wait(timeout=5)
            except subprocess.TimeoutExpired:
                try:
                    os.killpg(process.pid, signal.SIGKILL)
                except ProcessLookupError:
                    pass
                process.wait()

    def render(self, job, profile, rate, pitch, folder, progress):
        text = folder / "text.txt"
        text.write_text(job["text"], encoding="utf-8")
        env = os.environ.copy()
        env.update(PYTHONPATH=str(self.rvc), RVC_AUDIO_FORCE_CPU="1", OMP_NUM_THREADS="1",
                   MPLCONFIGDIR=str(self.data_home / "cache/matplotlib"),
                   NUMBA_CACHE_DIR=str(self.data_home / "cache/numba"))
        with (folder / "engine.log").open("w") as log:
            progress("synthesizing")
            guide = folder / "guide.aiff"
            tempo = []
            if job["engine"] == "chatterbox":
                guide = folder / "chatterbox.wav"
                chatterbox_env = os.environ.copy()
                chatterbox_env.pop("PYTHONPATH", None)
                chatterbox_env.update(HF_HOME=str(self.chatterbox / "cache"),
                                       HF_HUB_OFFLINE="1", TRANSFORMERS_OFFLINE="1",
                                       HF_HUB_DISABLE_TELEMETRY="1",
                                       PYTORCH_ENABLE_MPS_FALLBACK="1", OMP_NUM_THREADS="2")
                self.command([self.chatterbox_python,
                              Path(__file__).with_name("chatterbox_guide.py"),
                              "--text-file", text, "--reference",
                              self.chatterbox / "references" / f"{job['speaker']}.wav",
                              "--model-dir", self.chatterbox / "models",
                              "--output", guide, "--exaggeration", job["exaggeration"],
                              "--device", os.environ.get("VOICE_CHATTERBOX_DEVICE", "auto")],
                             log, env=chatterbox_env, timeout=900)
                tempo = ["-af", f"atempo={rate / 160:.4f}"]
            else:
                self.command(["/usr/bin/say", "-v", "Alva", "-r", rate, "-f", text,
                              "-o", guide], log, timeout=60)
            self.command([self.ffmpeg, "-hide_banner", "-loglevel", "error", "-i",
                          guide, *tempo, "-ac", 1, "-ar", 32000,
                          "-c:a", "pcm_s16le", folder / "guide.wav"], log, timeout=30)
            with wave.open(str(folder / "guide.wav"), "rb") as wav:
                if wav.getnframes() < wav.getframerate() / 10:
                    raise RuntimeError("Talmotorn skapade inget tal. Se inspelningens engine.log.")
            progress("converting")
            self.command([self.python, Path(__file__).with_name("rvc_infer_worker.py"),
                          "--model", profile["model"], "--index", profile["index"],
                          "--input", folder / "guide.wav", "--output", folder / "voice.wav",
                          "--pitch", pitch], log, env=env)

    def close(self):
        with self.lock:
            self.closed = True
            active = self.active
        if active:
            self.stop_process(active)
        self.executor.shutdown(wait=True, cancel_futures=True)
