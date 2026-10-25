#!/usr/bin/env python3
"""Generate a Swedish guide with Chatterbox before character-specific RVC."""

import argparse
import os
from pathlib import Path


def generate_guide(model, text, reference, output, exaggeration, write_audio):
    wav = model.generate(text, language_id="sv", audio_prompt_path=str(reference),
                         exaggeration=exaggeration, cfg_weight=0.3)
    write_audio(str(output), wav.detach().cpu().numpy().reshape(-1), model.sr,
                subtype="PCM_16")


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--text-file", type=Path, required=True)
    parser.add_argument("--reference", type=Path, required=True)
    parser.add_argument("--model-dir", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--exaggeration", type=float, default=0.6)
    parser.add_argument("--device", choices=("auto", "cpu", "mps"), default="auto")
    args = parser.parse_args()
    if not 0 <= args.exaggeration <= 1.5:
        parser.error("Expression must be between 0 and 1.5")
    # Models are installed explicitly; synthesis never starts a model download.
    os.environ.update(HF_HUB_OFFLINE="1", TRANSFORMERS_OFFLINE="1",
                      PYTORCH_ENABLE_MPS_FALLBACK="1")
    import soundfile
    import torch
    from chatterbox.mtl_tts import ChatterboxMultilingualTTS
    torch.set_num_threads(2)
    device = args.device
    if device == "auto":
        device = "mps" if torch.backends.mps.is_available() else "cpu"
    print(f"Chatterbox Multilingual: device={device}, language=sv", flush=True)
    model = ChatterboxMultilingualTTS.from_local(args.model_dir, device=device)
    generate_guide(model, args.text_file.read_text(encoding="utf-8"), args.reference,
                   args.output, args.exaggeration, soundfile.write)


if __name__ == "__main__":
    main()
