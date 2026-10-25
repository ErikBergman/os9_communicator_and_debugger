# Swedish character voices with Chatterbox and RVC

Run from the `os9_communicator_and_debugger` repository. Everything is local.
The game disc, preserved forks and original executable are never modified.

To train the rest of the Swedish first game's cast, use the resumable batch
runner in [TRAIN-CAST.md](TRAIN-CAST.md). It reuses the four completed voices
and adds matching Chatterbox references for each new RVC model.

RVC changes the voice of **recorded speech**. The text interface generates
Swedish speech with **Chatterbox Multilingual**, then converts that guide with
the selected character's separate trained RVC model. Chatterbox supplies the rhythm
and expression; RVC supplies the character voice. The installed macOS **Alva**
voice remains selectable for comparison and is the default until Chatterbox
is installed. Selecting Chatterbox never silently falls back to Alva.

## Type a sentence in the local interface

Double-click `tools/freddi_fisk/Start Voice Studio.command` in Finder, or run:

```sh
/usr/bin/python3 tools/freddi_fisk/voice_studio.py
```

The launcher opens <http://127.0.0.1:8765>. Choose Freddi, Linus, Boss or
Spongehead, type up to
400 characters in Swedish, and press **Skapa röst**. The result can be played
and downloaded as a WAV. Optional controls adjust the guide's tempo and the
conversion's pitch. Keep the terminal open; Ctrl+C stops the studio and any
active conversion. Start it from a normal macOS terminal: restricted execution
can make `say` silently produce an empty recording.

All four character models have been trained to 20 epochs on this Mac. The studio
prefers completed models over the earlier three-clip previews. Voice similarity,
pronunciation, and delivery still need listening evaluation. With Alva selected,
its rhythm and intonation carry through the conversion.

## Chatterbox + trained RVC

The existing RVC models need no retraining. Install Chatterbox into its own
Python environment outside iCloud Documents, alongside the existing studio
runtime. Use Python 3.12:

```sh
VOICE_PYTHON=/Users/erikbergman/.cache/codex-runtimes/codex-primary-runtime/dependencies/python/bin/python3
"$VOICE_PYTHON" tools/freddi_fisk/setup_chatterbox.py install
/usr/bin/python3 tools/freddi_fisk/voice_studio.py
```

Setup installs `chatterbox-tts==0.1.7` and the stable Multilingual v2 checkpoint
at the revision recorded in `chatterbox-versions.json`. Its models require about
3.2 GB plus the Python environment. The separate environment keeps Chatterbox's
PyTorch and NumPy dependencies from replacing the working RVC dependencies.
Large weight downloads are verified against their published SHA-256 hashes.
Exact installed package versions are saved in `chatterbox/installed-requirements.txt`.

Once installed, the studio selects **Chatterbox + RVC** automatically. Expand
**Justera rösten** to compare it with **Alva + RVC**, or select **Lugnt**,
**Naturligt**, or **Livligt** expression. Tempo and pitch remain adjustable.
Requests always finish with the selected character's RVC model and matching
retrieval index. Chatterbox generation runs in a separate process that exits
before RVC starts, releasing its memory. CPU generation with two threads is the
default: Apple MPS was detected on this Mac but failed during audio decoding
with a Metal compiler-service error. To experiment with GPU acceleration on a
Mac where the Metal backend works:

```sh
VOICE_CHATTERBOX_DEVICE=mps /usr/bin/python3 tools/freddi_fisk/voice_studio.py
```

Setup chooses one 3–10 second original Swedish **training** clip per character
from the existing dataset manifest, preferring a duration near eight seconds.
No new character recordings are needed. These references supply Chatterbox's
speaker/style conditioning; they are not additional training. Listen to them
under `~/Library/Application Support/FreddiFishVoiceStudio/runtime/chatterbox/references/`.
The choices and original paths are recorded in `references.json`. Selection is
automatic, not a listening audit; another existing clean clip may work better.
To replace a reference without reinstalling models:

```sh
"$VOICE_PYTHON" tools/freddi_fisk/setup_chatterbox.py references \
  --reference-freddi /absolute/path/to/a/clean-freddi-clip.wav \
  --reference-linus /absolute/path/to/a/clean-linus-clip.wav
```

Existing reference choices are preserved unless explicitly replaced. The
installer accepts `--runtime-root` for another runtime location. To verify
model files again, run `setup_chatterbox.py check` with the same Python.
Synthesis uses local weights with Hugging Face offline mode enabled. Downloads
happen only during setup, including the upstream tokenizer's auxiliary cache.
Setup also checks that Chatterbox's bundled watermarking component loads.
A first generation may take several minutes; its
limit is 15 minutes, followed by the existing three-minute RVC conversion limit.
The original Chatterbox guide is retained as `chatterbox.wav` beside the final
`voice.wav`, so you can compare expression before and after conversion.

Upstream APIs and Swedish support: [Chatterbox](https://github.com/resemble-ai/chatterbox)
and [official model files](https://huggingface.co/ResembleAI/chatterbox).

Local validation on 2026-10-25: both trained character profiles completed
Chatterbox → guide resampling → RVC for “Hej Linus! Ska vi leta efter skatten?”.
CPU runs took approximately 67 seconds for Freddi and 44 seconds for Linus,
producing 2.48- and 2.84-second WAVs. These checks establish that the full pipeline
runs; naturalness, pronunciation, and voice similarity still need listening
comparison with Alva and the original recordings.

## Train and add the two sharks

Boss and Spongehead use separate datasets, RVC models, retrieval indexes and
Chatterbox references. Their source cues, clip counts and limitations are in
[the shark dataset report](../../analysis/freddi-fisk/SHARK-VOICE-DATASET.md).
The complete workflow runs outside iCloud Documents and uses two CPU threads:

```sh
VOICE_PYTHON=/Users/erikbergman/.cache/codex-runtimes/codex-primary-runtime/dependencies/python/bin/python3
caffeinate -i "$VOICE_PYTHON" tools/freddi_fisk/train_sharks.py --epochs 20 --threads 2
```

This requires the already installed RVC and Chatterbox runtimes and the existing
speech extraction/decompiled scripts. It extracts the verified shark training
clips, installs original Swedish references into Chatterbox, prepares RVC pitch
and content features, builds the indexes and trains both sharks sequentially.
The Chatterbox weights stay fixed; the two RVC character models are trained.
Do not start another copy while it runs: a lock rejects duplicate orchestration.

Run the same command later to resume checkpoints or skip models already
completed at the requested epoch target. `--epochs` is a total target, not an
additional count. Five-epoch checkpoints and trainer logs are under
`~/Library/Application Support/FreddiFishVoiceStudio/runtime/rvc/logs/swedish-{boss,spongehead}-v2/`.
The exported models are in that runtime's `rvc/assets/weights/` folder.

The app enables a shark after its completed model export is recorded. Restart
the server to load updated source code, then refresh the page. No profile-copy
command is needed for these models: training writes directly to the app's
local runtime. Freddi and Linus retain their existing trained models.

Completed on this Mac on 2026-10-25: both sharks trained to 20 epochs and
generated new Swedish sentences through Chatterbox and their trained RVC
models. Short CPU checks took approximately 56 seconds for Boss and 47 seconds
for Spongehead. Their small source datasets make listening comparison
particularly important; see the report for the actual clip counts.

To choose a different clean original shark reference without retraining RVC:

```sh
"$VOICE_PYTHON" tools/freddi_fisk/setup_chatterbox.py references \
  --speakers boss spongehead \
  --dataset-root "$HOME/Library/Application Support/FreddiFishVoiceStudio/runtime/shark-datasets" \
  --reference-boss /absolute/path/to/boss.wav \
  --reference-spongehead /absolute/path/to/spongehead.wav
```

## Local runtime and recordings

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

The commands display Rich progress bars for the overall epoch target and the
current epoch, plus elapsed time and estimated time remaining. During startup
the display says `Loading models / data`; percentages begin when the trainer
reports its first batch. Batch percentages update at the trainer's log points
(at least every ten batches), so they can stay still while a batch is running.
On resume, progress starts at the restored epoch and the ETA is estimated from
the current invocation. Epoch 100% means the epochs have finished; the command
still waits for model export and verifies that an updated model was written.

Rich runs inside the isolated RVC environment; the outer `python3` command does
not need Rich installed globally. Existing installations need the new pinned
dependency once (already installed on this Mac):

```sh
.local-tools/rvc-venv/bin/python -m pip install rich==14.1.0
```

Raw console output is retained in each experiment's `training-console.log`;
the trainer's original `train.log` and TensorBoard files are retained too.
Failures print recent console diagnostics and return a failure status. Ctrl+C
stops the trainer and its child processes; checkpoint/resume behavior is
unchanged. Redirected output includes an epoch-completion line for each epoch.

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
.local-tools/rvc-venv/bin/python -m unittest discover -s tests -v
```
