#!/usr/bin/env python3
"""Render identical Swedish guides through the Swedish- and English-trained Linus models."""

import argparse
import array
import fcntl
import hashlib
import html
import json
import math
import os
from pathlib import Path
import re
import sys
import wave
import zipfile

HERE = Path(__file__).resolve().parent
FISH_TOOLS = HERE.parent / "freddi_fisk"
sys.path.insert(0, str(FISH_TOOLS))
from text_to_voice import APP_DATA, VoiceStudio

ENGLISH_EXPERIMENT = "english-linus-freddi2-v2"
SENTENCES = [
    "Hej Freddi! Ska vi simma till skolan och leta efter en ny ledtråd?",
    "Jag hörde ett märkligt ljud bakom dörren. Tror du att det är ett spöke?",
    "På vår ö finns sju gröna sjöstjärnor och en väldigt blyg ål.",
]


def digest(path):
    with Path(path).open("rb") as stream:
        return hashlib.file_digest(stream, "sha256").hexdigest()


def json_write(path, data):
    temporary = path.with_suffix(".installing")
    temporary.write_text(json.dumps(data, ensure_ascii=False, indent=2) + "\n")
    temporary.replace(path)


def wave_info(path):
    with wave.open(str(path), "rb") as wav:
        if wav.getnchannels() != 1 or wav.getsampwidth() != 2 or not wav.getnframes():
            raise ValueError(f"Expected nonempty 16-bit mono WAV: {path}")
        samples = array.array("h", wav.readframes(wav.getnframes()))
        if sys.byteorder != "little":
            samples.byteswap()
        peak = max(map(abs, samples))
        if not peak:
            raise ValueError(f"Silent WAV: {path}")
        return {"sample_rate": wav.getframerate(), "frames": wav.getnframes(),
                "seconds": wav.getnframes() / wav.getframerate(), "peak": peak}


def paired_wav(first, second, output, gap_seconds=1.25):
    with wave.open(str(first), "rb") as a, wave.open(str(second), "rb") as b:
        if a.getparams()[:3] != b.getparams()[:3]:
            raise ValueError("A/B files must have matching PCM formats")
        with wave.open(str(output), "wb") as target:
            target.setparams(a.getparams())
            target.writeframes(a.readframes(a.getnframes()))
            target.writeframes(b"\0" * round(a.getframerate() * gap_seconds) * a.getsampwidth() * a.getnchannels())
            target.writeframes(b.readframes(b.getnframes()))


def render(runtime, output, exaggeration=.6):
    rvc = runtime / "rvc"
    profiles = {}
    for label, experiment in (("A", "swedish-linus-v2"), ("B", ENGLISH_EXPERIMENT)):
        model = rvc / "assets/weights" / f"{experiment}.pth"
        indexes = sorted((rvc / "logs" / experiment).glob("added*.index"))
        if not model.is_file() or not indexes:
            raise RuntimeError(f"Missing model/index for {experiment}")
        profiles[label] = {"model": str(model), "index": str(indexes[-1]),
                           "model_sha256": digest(model), "index_sha256": digest(indexes[-1])}
    experiment = rvc / "logs" / ENGLISH_EXPERIMENT
    completed = json.loads((experiment / "completed-training.json").read_text())
    if completed["epochs"] != 20 or completed["model_sha256"] != profiles["B"]["model_sha256"]:
        raise RuntimeError("English model is not the completed 20-epoch experiment")
    before = experiment / "swedish-baseline-before.json"
    if before.is_file() and json.loads(before.read_text())["model_sha256"] != profiles["A"]["model_sha256"]:
        raise RuntimeError("Swedish baseline changed since training started")
    reference = runtime / "chatterbox/references/linus.wav"
    configuration = {"sentences": SENTENCES, "profiles": profiles, "epochs": 20,
                     "guide_reference": str(reference), "reference_sha256": digest(reference),
                     "guide_language": "sv", "exaggeration": exaggeration, "cfg_weight": .3,
                     "format": "16-bit PCM WAV, mono, 32000 Hz", "loudness": "-20 LUFS, -2 dBTP",
                     "order": "A: Swedish Freddi 1 training; B: English Freddi 2 training; both speak Swedish"}
    output.mkdir(parents=True, exist_ok=True)
    config_path = output / "experiment.json"
    if config_path.exists() and json.loads(config_path.read_text()) != configuration:
        raise RuntimeError("Comparison settings or models changed; choose a fresh output folder")
    json_write(config_path, configuration)
    artifact_path = output / "artifacts.json"
    artifacts = json.loads(artifact_path.read_text()) if artifact_path.exists() else {}
    studio = VoiceStudio()
    studio.rvc = rvc
    command_path = output / "commands.json"
    commands = json.loads(command_path.read_text()) if command_path.exists() else []

    def run(arguments, log_path, env=None, timeout=180):
        commands.append(list(map(str, arguments)))
        json_write(output / "commands.json", commands)
        log_path.parent.mkdir(parents=True, exist_ok=True)
        with log_path.open("w") as log:
            studio.command(arguments, log, env=env, timeout=timeout)

    def produce(path, writer):
        key = str(path.relative_to(output))
        if path.exists():
            if artifacts.get(key) != digest(path):
                raise RuntimeError(f"Unrecorded or changed output; left untouched: {path}")
            return wave_info(path)
        path.parent.mkdir(parents=True, exist_ok=True)
        temporary = path.with_name(path.stem + ".inprogress.wav")
        temporary.unlink(missing_ok=True)
        writer(temporary)
        info = wave_info(temporary)
        temporary.replace(path)
        artifacts[key] = digest(path)
        json_write(artifact_path, artifacts)
        return info

    def normalize(source, temporary, log_name):
        measurement = output / "logs" / (log_name + "-measurement.log")
        run([studio.ffmpeg, "-nostdin", "-hide_banner", "-i", source,
             "-af", "loudnorm=I=-20:TP=-2:LRA=7:print_format=json", "-f", "null", "-"], measurement, timeout=30)
        data = json.loads(re.findall(r'\{\s*"input_i".*?\}', measurement.read_text(), re.DOTALL)[-1])
        values = {key: float(data[key]) for key in ("input_i", "input_tp", "input_lra", "input_thresh", "target_offset")}
        if not all(math.isfinite(value) for value in values.values()):
            raise RuntimeError("Cannot normalize silent or invalid audio")
        settings = (f'loudnorm=I=-20:TP=-2:LRA=7:measured_I={values["input_i"]}'
                    f':measured_TP={values["input_tp"]}:measured_LRA={values["input_lra"]}'
                    f':measured_thresh={values["input_thresh"]}:offset={values["target_offset"]}:linear=true')
        run([studio.ffmpeg, "-nostdin", "-hide_banner", "-loglevel", "error", "-i", source,
             "-af", settings, "-ac", 1, "-ar", 32000, "-c:a", "pcm_s16le", temporary],
            output / "logs" / (log_name + "-normalized.log"), timeout=30)

    results = []
    try:
        for number, sentence in enumerate(SENTENCES, 1):
            print(f"Sentence {number}/3: generating one shared Swedish Chatterbox guide", flush=True)
            text = output / "guides" / f"{number:02d}-text.txt"
            text.parent.mkdir(exist_ok=True)
            text.write_text(sentence, encoding="utf-8")
            guide = output / "guides" / f"{number:02d}-chatterbox.wav"
            env = os.environ.copy()
            env.pop("PYTHONPATH", None)
            env.update(HF_HOME=str(runtime / "chatterbox/cache"), HF_HUB_OFFLINE="1",
                       TRANSFORMERS_OFFLINE="1", HF_HUB_DISABLE_TELEMETRY="1", OMP_NUM_THREADS="2")
            produce(guide, lambda temporary: run([runtime / "chatterbox-venv/bin/python",
                    FISH_TOOLS / "chatterbox_guide.py", "--text-file", text, "--reference", reference,
                    "--model-dir", runtime / "chatterbox/models", "--output", temporary,
                    "--exaggeration", exaggeration, "--device", "cpu"],
                    output / "logs" / f"{number:02d}-chatterbox.log", env, 900))
            guide32 = output / "guides" / f"{number:02d}-guide-32k.wav"
            produce(guide32, lambda temporary: run([studio.ffmpeg, "-nostdin", "-hide_banner", "-loglevel", "error",
                    "-i", guide, "-ac", 1, "-ar", 32000, "-c:a", "pcm_s16le", temporary],
                    output / "logs" / f"{number:02d}-resample.log", timeout=30))
            entry = {"number": number, "text": sentence, "shared_guide_sha256": digest(guide32), "voices": {}}
            normalized = []
            for label, description in (("A", "Swedish-FF1"), ("B", "English-FF2")):
                print(f"Sentence {number}/3: converting Linus {label} ({description})", flush=True)
                profile = profiles[label]
                raw = output / "raw" / f"{number:02d}_{label}_{description}.wav"
                env = os.environ.copy()
                env.update(PYTHONPATH=str(rvc), RVC_AUDIO_FORCE_CPU="1", OMP_NUM_THREADS="1",
                           MPLCONFIGDIR=str(APP_DATA / "cache/matplotlib"), NUMBA_CACHE_DIR=str(APP_DATA / "cache/numba"))
                produce(raw, lambda temporary: run([runtime / "rvc-venv/bin/python", FISH_TOOLS / "rvc_infer_worker.py",
                        "--model", profile["model"], "--index", profile["index"], "--input", guide32,
                        "--output", temporary, "--pitch", 0], output / "logs" / f"{number:02d}-{label}-rvc.log", env))
                target = output / raw.name
                info = produce(target, lambda temporary: normalize(raw, temporary, f"{number:02d}-{label}"))
                if info["sample_rate"] != 32000:
                    raise RuntimeError("Unexpected comparison sample rate")
                normalized.append(target)
                entry["voices"][label] = {"file": target.name, "raw_file": str(raw.relative_to(output)), **info}
            pair = output / f"{number:02d}_AB_Swedish-then-English-trained.wav"
            produce(pair, lambda temporary: paired_wav(*normalized, temporary))
            entry["pair"] = pair.name
            results.append(entry)
            json_write(output / "results.json", {"experiment": configuration, "sentences": results})
        for profile in profiles.values():
            if digest(profile["model"]) != profile["model_sha256"]:
                raise RuntimeError("A comparison model changed during synthesis")
    finally:
        studio.close()
    descriptions = "A = Linus trained on Swedish Freddi Fish 1. B = Linus trained on English Freddi Fish 2. Both speak Swedish."
    (output / "README.txt").write_text(descriptions + "\n\nEach AB file plays A, 1.25 seconds of silence, then B.\n"
        "All six individual files use identical Swedish guides within each pair.\n"
        "WAV: mono, 16-bit PCM, 32 kHz. Loudness matched to -20 LUFS, peak ceiling -2 dBTP.\n"
        "Original unnormalized RVC outputs are retained in raw/. Chatterbox guides are in guides/.\n\n"
        + "\n".join(f'{row["number"]}. {row["text"]}' for row in results), encoding="utf-8")
    cards = []
    for row in results:
        voices = "".join(f'<div><strong>Linus {label}: {"svensk träning" if label == "A" else "engelsk träning"}</strong>'
            f'<audio controls preload="none" src="{row["voices"][label]["file"]}"></audio></div>' for label in ("A", "B"))
        cards.append(f'<section><h2>{row["number"]}. {html.escape(row["text"])}</h2><div class="pair">{voices}</div>'
                     f'<p>A följt av B:</p><audio controls preload="none" src="{row["pair"]}"></audio></section>')
    (output / "index.html").write_text('<!doctype html><html lang="sv"><meta charset="utf-8">'
        '<meta name="viewport" content="width=device-width"><title>Två svenska Linus</title>'
        '<style>body{font:17px system-ui;background:#f4f4ed;color:#243a3c;max-width:1000px;margin:3rem auto;padding:0 1rem}'
        'section{background:white;border-radius:18px;padding:1.5rem;margin:1.5rem 0}h2{font-size:1.15rem}'
        '.pair{display:grid;grid-template-columns:repeat(auto-fit,minmax(280px,1fr));gap:1.5rem}audio{display:block;width:100%;margin:.7rem 0}</style>'
        '<h1>Två svenska Linus</h1><p>A är tränad på svenska Freddi Fisk 1. B är tränad på engelska Freddi Fish 2. '
        'Båda läser samma svenska Chatterbox-inspelning. Volymen är utjämnad för jämförelsen.</p>' + "".join(cards) + '</html>', encoding="utf-8")
    with zipfile.ZipFile(output / "Linus-comparison.zip", "w", compression=zipfile.ZIP_DEFLATED) as archive:
        for path in sorted(output.glob("*.wav")) + [output / "README.txt", output / "index.html", output / "results.json"]:
            archive.write(path, path.name)
    print(f"Comparison ready: {output}", flush=True)
    return results


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--runtime-root", type=Path, default=APP_DATA / "runtime")
    parser.add_argument("--output", type=Path, default=APP_DATA / "comparisons/linus-sv-ff1-vs-en-ff2")
    parser.add_argument("--exaggeration", type=float, default=.6)
    args = parser.parse_args()
    if not 0 <= args.exaggeration <= 1.5:
        parser.error("--exaggeration must be between zero and 1.5")
    output = args.output.expanduser().resolve()
    output.mkdir(parents=True, exist_ok=True)
    with (output / ".comparison.lock").open("a") as lock:
        try:
            fcntl.flock(lock, fcntl.LOCK_EX | fcntl.LOCK_NB)
        except BlockingIOError:
            parser.error("This comparison is already running")
        render(args.runtime_root.expanduser().resolve(), output, args.exaggeration)


if __name__ == "__main__":
    main()
