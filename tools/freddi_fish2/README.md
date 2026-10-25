# English-trained Linus speaking Swedish

This experiment compares the existing Swedish Freddi Fish 1 Linus model with a
separate model trained on English Luther/Linus from the user's Freddi Fish 2 CD.
The existing studio profiles and Swedish model are retained.

## Dataset and training

The English dataset uses explicit `say-line 2` **and** `color 232` in the
decompiled sequel scripts. This is supported by the view-room conversation in
which actor 2 addresses Freddi and Freddi replies to Luther. Generic actor IDs
and animation talkie tables are excluded. Both literal byte `0x7f` speech
markers and the decompiler's escaped `\x7F` representation are recognized.
Script hashes, line numbers, archive byte counts and original PCM hashes are
recorded per source clip. This is script-based identification, not a complete
listening audit of every recording.

There are 185 unique eligible English clips (1–10 seconds). A deterministic
PCM-hash split holds out 16 clips (37.95 seconds). The training pool is selected
in PCM-hash order until it matches the native Swedish model's training duration:

| Model | Training clips | Training seconds | Epoch target |
| --- | ---: | ---: | ---: |
| A: Swedish FF1 Linus, existing | 105 | 190.78 | 20 |
| B: English FF2 Luther/Linus, new | 85 | 190.09 | 20 |

Another 84 English clips (192.26 seconds) are reserved, excluded from this
matched experiment. The comparison controls training duration and epoch target;
the actors, recording characteristics, clip counts and training random states
still differ. It does not isolate language as the only causal variable.

The full 32 kHz, pitch-guided RVC v2 experiment has a separate name,
`english-linus-freddi2-v2`. Preparation produces 97 complete training segments;
none were excluded. Validation and reserve clips never enter feature extraction,
index construction or training. The model starts from the same pretrained RVC
generator/discriminator family as the existing voices. Two CPU threads are used.

Run from the repository with the installed Python 3.12:

```sh
VOICE_PYTHON=/Users/erikbergman/.cache/codex-runtimes/codex-primary-runtime/dependencies/python/bin/python3
caffeinate -i "$VOICE_PYTHON" tools/freddi_fish2/train_linus.py
```

The helper prepares missing data/features, rejects duplicate concurrent runs,
resumes saved checkpoints, and skips an already completed 20-epoch model. It
hashes the existing Swedish model before and after training. Use Ctrl+C to stop;
do not suspend and relaunch duplicate jobs with Ctrl+Z.

All large files stay outside iCloud Documents, under
`~/Library/Application Support/FreddiFishVoiceStudio/`:

- `work/freddi-fish-2/linus-english-dataset/`: train, validation, reserve and manifest.
- `runtime/rvc/logs/english-linus-freddi2-v2/`: features, input hashes, index,
  five-epoch checkpoints, completion record and trainer logs.
- `runtime/rvc/assets/weights/english-linus-freddi2-v2.pth`: completed inference model.

## The three Swedish sentences

1. Hej Freddi! Ska vi simma till skolan och leta efter en ny ledtråd?
2. Jag hörde ett märkligt ljud bakom dörren. Tror du att det är ett spöke?
3. På vår ö finns sju gröna sjöstjärnor och en väldigt blyg ål.

Each sentence gets **one shared Chatterbox Swedish guide**, conditioned on the
existing Swedish Linus reference. The identical resampled guide is passed to A
and B with unchanged conversion settings and pitch zero. This tests English-
trained RVC on an already Swedish performance without adding an English
Chatterbox-reference accent. It does not test English-reference Chatterbox.
Some source voice characteristics can still leak through voice conversion.

After training:

```sh
"$VOICE_PYTHON" tools/freddi_fish2/compare_linus.py
```

Outputs are in `comparisons/linus-sv-ff1-vs-en-ff2/` under the app data folder:

- Six individual **16-bit PCM, mono, 32 kHz WAVs**, loudness matched with
  FFmpeg's two-pass loudnorm to -20 LUFS and a -2 dBTP ceiling.
- Three paired WAVs: **A first, 1.25 seconds of silence, then B**.
- `index.html`: labelled players for all three comparisons.
- `Linus-comparison.zip`: individual and paired WAVs, the player and result metadata.
- `raw/`: untouched RVC outputs; `guides/`: original and resampled Chatterbox audio.
- `experiment.json`, `results.json`, `commands.json`, `artifacts.json` and `logs/`:
  settings, model/index/reference hashes, identical-guide provenance and diagnostics.

Rerunning synthesis reuses checksum-verified completed audio. Changed models,
settings or modified output files require a fresh output folder. A lock prevents
two exporters from writing the same comparison concurrently. Chatterbox's
installed watermarking remains enabled; no audio is uploaded.

## Optional local word check

An isolated `runtime/whisper-venv` uses `faster-whisper==1.2.1` with multilingual
Whisper Small on the CPU. The verified model is `Systran/faster-whisper-small`,
revision `536b0662742c02347bc0e980a01041f333bce120`, model SHA-256
`3e305921506d8872816023e4c273e75d2419fb89b24da97b4fe7bce14170d671`.
Installed dependency versions are retained in `runtime/whisper-installed-requirements.txt`.

```sh
VOICE_RUNTIME="$HOME/Library/Application Support/FreddiFishVoiceStudio/runtime"
HF_HUB_OFFLINE=1 "$VOICE_RUNTIME/whisper-venv/bin/python" tools/freddi_fish2/check_linus_words.py
```

The recognizer transcribes each guide and both outputs as Swedish without being
prompted with the expected sentence. `transcription-check.json` reports word
edits, including å/ä/ö distinctions. This screens for skipped/repeated words;
it cannot establish accent quality, naturalness or character similarity.
