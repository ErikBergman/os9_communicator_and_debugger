# Swedish Freddi / Linus with RVC

Run from the `os9_communicator_and_debugger` repository. Everything is local.
The game disc, preserved forks and original executable are never modified.

RVC changes the voice of **recorded speech**. The text interface first reads
your Swedish sentence with the installed macOS **Alva** voice, then converts
that guide recording with Freddi's or Linus' separate RVC model.

## Type a sentence in the local interface

Double-click `tools/freddi_fisk/Start Voice Studio.command` in Finder, or run:

```sh
/usr/bin/python3 tools/freddi_fisk/voice_studio.py
```

The launcher opens <http://127.0.0.1:8765>. Choose Freddi or Linus, type up to
400 characters in Swedish, and press **Skapa röst**. The result can be played
and downloaded as a WAV. Optional controls adjust the guide's tempo and the
conversion's pitch. Keep the terminal open; Ctrl+C stops the studio and any
active conversion. Start it from a normal macOS terminal: restricted execution
can make `say` silently produce an empty recording.

**Current voices are previews:** each was trained for one epoch on three clips
to verify the pipeline. The full character datasets have been prepared but
full training has not completed. More training and listening evaluation are
needed before calling these convincing copies of the original voices. Alva
also supplies the pacing and expression, so generated delivery differs from
the original actors' performances.

The studio binds only to the loopback interface. Text, guide audio, converted
WAVs and diagnostic logs are stored locally in
`~/Library/Application Support/FreddiFishVoiceStudio/recordings/<job-id>/`.
They are retained until you remove them; the server does not upload them.
Requests run one at a time. The first conversion can take longer while Python
imports and audio caches warm up. Each RVC conversion has a three-minute limit.

On this Mac, iCloud offloads files in Documents even during long-running work.
The interface therefore prefers the installed runtime outside Documents:

```sh
VOICE_RUNTIME="$HOME/Library/Application Support/FreddiFishVoiceStudio/runtime"
"$VOICE_PYTHON" tools/freddi_fisk/setup_voice_tools.py install \
  --runtime-root "$VOICE_RUNTIME" --inference-only
/usr/bin/python3 tools/freddi_fisk/setup_voice_tools.py profiles \
  --runtime-root "$VOICE_RUNTIME"
```

Define `VOICE_PYTHON` as shown in Install below. Both steps are already done on
this Mac. The profiles command copies completed models and matching indexes
from the training runtime in `.local-tools`. Run it again after full training;
the studio automatically prefers full models over preview models. It falls
back to `.local-tools` only when the separate runtime is absent. Keep the small
`tools/freddi_fisk` source folder downloaded in Finder too.

## Install

Requires Python 3.12 and FFmpeg/FFprobe on PATH. The checked setup on this MacBook
uses the bundled Codex Python:

```sh
VOICE_PYTHON=/Users/erikbergman/.cache/codex-runtimes/codex-primary-runtime/dependencies/python/bin/python3
"$VOICE_PYTHON" tools/freddi_fisk/setup_voice_tools.py install
```

The installer pins RVC and NUTCracker Git revisions, creates separate virtual
environments under `.local-tools/`, and downloads the ContentVec/HuBERT, RMVPE,
and RVC v2 32 kHz pitch-guided generator/discriminator weights. Model files are
pinned to a Hugging Face revision and checked against committed SHA-256 hashes.
Downloads stay in the selected runtime directory, which defaults to the ignored
`.local-tools/` folder. Exact installed Python dependencies are recorded in
`<runtime-root>/installed-rvc-requirements.txt` (the original installation's
record is also retained in `analysis/freddi-fisk/voice-work/`).

The upstream RVC CPU requirements use Linux-specific `+cpu` wheel names and
unneeded UI dependencies. Our small Mac requirements use native Apple Silicon
PyTorch wheels and the offline CLI. This pinned upstream version uses CPU
training/inference on macOS; it does not select Apple MPS acceleration.

## Extract and select the voices

```sh
python3 tools/freddi_fisk/extract_speech.py
python3 tools/freddi_fisk/setup_voice_tools.py scripts
python3 tools/freddi_fisk/prepare_voice_datasets.py
```

The commands refuse to overwrite completed extraction/dataset outputs. Existing
preserved `mac-forks/23`, `24`, `25`, `26` are the inputs. The script decompiler
uses copies with HE-compatible filenames and forces the HE 73 interpreter.

Read [the dataset report](../../analysis/freddi-fisk/VOICE-DATASET.md).
Open `analysis/freddi-fisk/voice-work/datasets/listen.html` locally to listen to
the selected recordings. Descriptions are the retained English script text;
the source recordings are Swedish. Speaker labels come from explicit script
dialogue positions, not numeric actor IDs or a completed listening audit.

Freddi has 282 training clips (10m 44s); Linus has 105 (3m 11s). Separate
validation clips are excluded from every training step. Linus is below RVC's
recommended ten minutes of source audio. Original speech is 8-bit, around
11 kHz; upsampling for RVC does not restore missing high frequencies.

## Prepare the full training data

```sh
python3 tools/freddi_fisk/rvc_voice.py prepare freddi
python3 tools/freddi_fisk/rvc_voice.py prepare linus
```

Each command slices/resamples **only that character's training split**, extracts
RMVPE pitch and 768-dimensional ContentVec features, writes an intersected
file list, and builds a separate FAISS retrieval index. Incomplete feature
sets are excluded and reported in the experiment's `preparation.json`.
Inputs are hashed; changing a dataset cannot silently reuse an old experiment.

The 32 kHz pretrained models are the lowest sample rate offered for RVC v2.
The RVC slicer's high-pass filter and normalisation are applied during this
step; extracted originals and validation WAVs remain intact.

## Train

```sh
python3 tools/freddi_fisk/rvc_voice.py train freddi --epochs 20
python3 tools/freddi_fisk/rvc_voice.py train linus --epochs 20
```

Twenty is a starting experiment, not a quality guarantee. Evaluate held-out
clips and new guide recordings, then adjust training as needed. On this M2
MacBook, CPU training is slow: the initial three-segment Linus smoke epoch took
42 seconds, excluding feature preparation. A full run may take hours. Run one
full training job at a time to keep memory use manageable.

`--epochs` is the total target, including earlier epochs. Re-running the same
command resumes the latest saved G/D checkpoint. Checkpoints are saved every
five epochs (or at the target for targets below five), and the completed run
exports an inference `.pth` file. **Current upstream resumes from the checkpoint
epoch itself, so the last saved epoch may be repeated.** A larger target
continues training. Existing exported voices are replaced only by training
that same named experiment.

Training needs local shared memory and loopback process communication; the
Codex restricted sandbox blocks these. Run training from a normal terminal or
with the app's execution approval. A child failure is detected even when the
upstream parent incorrectly returns exit status zero.

Artifacts (ignored):

- `.local-tools/rvc/logs/swedish-{freddi,linus}-v2/`: training features,
  input hashes, preparation report, logs, resumable G/D checkpoints and index.
- `.local-tools/rvc/assets/weights/swedish-{freddi,linus}-v2.pth`: finished
  inference voices, once full training has completed.

## Convert a new performance

```sh
python3 tools/freddi_fisk/rvc_voice.py convert freddi \
  --input /absolute/path/to/swedish-guide.wav \
  --output /absolute/path/to/freddi-swedish.wav
```

Use `linus` for Linus and optionally `--pitch N` to shift the guide's pitch by
N semitones. The source performance supplies words, delivery and timing.
The command chooses the character's separate trained model and retrieval index,
uses RMVPE pitch extraction, and refuses to overwrite an existing output file.

On macOS, conversion runs in a small worker that flushes its output and exits
after the upstream CLI returns its real status. This avoids a confirmed native
shutdown deadlock between the PyTorch and FAISS OpenMP runtimes. Audio files
have already been closed before the worker exits; failures retain nonzero exit
codes. Interactive conversions also use one OpenMP thread. The upstream
checkout is unmodified.

## Small end-to-end verification

```sh
python3 tools/freddi_fisk/rvc_voice.py prepare linus --smoke
python3 tools/freddi_fisk/rvc_voice.py train linus --smoke --epochs 1
python3 tools/freddi_fisk/rvc_voice.py convert linus --smoke \
  --input /absolute/path/to/held-out-recording.wav \
  --output /absolute/path/to/smoke-output.wav
```

Repeat for Freddi. `--smoke` uses only three training clips, with separate
experiment/model/index names. These tiny models verify the pipeline; they
are not quality voice clones and never replace full training artifacts.
The upstream trainer may report leaked semaphore cleanup on exit; verify the
final export and audio result instead of treating that warning as a model.

See [the verified checkpoint](../../analysis/freddi-fisk/RVC-CHECKPOINT.md) for
the completed work and the distinction between prepared full datasets and the
small test models.

Run regression checks with Python 3.12 or later:

```sh
"$VOICE_PYTHON" -m unittest discover -s tests -v
```
