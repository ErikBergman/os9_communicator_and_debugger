# Train the Swedish Freddi Fisk 1 cast

Run this in Terminal, from any working directory:

```sh
cd "/Users/erikbergman/Documents/Programmering/MacOS9/os9_communicator_and_debugger"
caffeinate -i /usr/bin/python3 tools/freddi_fisk/train_cast.py --compact
```

This runs **20 total epochs per voice**, sequentially, using two CPU threads.
Freddi, Linus, Boss and Spongehead already have verified 20-epoch models and
are skipped. Each new role gets its own RVC model, retrieval index and original
Swedish reference for the existing **Chatterbox → RVC** pipeline. Chatterbox's
shared multilingual model is reused; its weights are not fine-tuned.
The Rich display shows the current voice, epoch, elapsed time and estimated
remaining time **for that voice** once training starts. Feature extraction
prints its own progress first. Do not run another training command alongside it.

## Pause and continue

Press **Ctrl+C once**. Training finishes the next epoch and saves **both**
resume checkpoints before stopping. Keep the terminal open until it says:

```text
Paused. You can close the terminal now. Run the same command to continue.
```

You can then close Terminal, shut down, or disconnect from the internet.
Run the **same command** later. Finished voices are skipped; the interrupted
voice resumes from its saved checkpoint. The upstream RVC trainer repeats
the saved epoch when resuming, so repeating at most one epoch is expected.

During feature extraction, Ctrl+C stops that stage; the next invocation reruns
any incomplete preparation. A second Ctrl+C during training stops immediately
and loses work since the previous checkpoint. Avoid forcing it off while files
are saving. **Ctrl+Z is not the pause command**: it suspends the launcher and can
leave the trainer working in its separate process group.

To request the same checkpoint pause from another terminal:

```sh
/usr/bin/python3 "/Users/erikbergman/Documents/Programmering/MacOS9/os9_communicator_and_debugger/tools/freddi_fisk/train_cast.py" pause
```

To see which voices are finished or have a checkpoint:

```sh
/usr/bin/python3 "/Users/erikbergman/Documents/Programmering/MacOS9/os9_communicator_and_debugger/tools/freddi_fisk/train_cast.py" status
```

## Storage and options

All datasets, references, logs and models live outside iCloud Documents:

```text
~/Library/Application Support/FreddiFishVoiceStudio/runtime/
  cast-datasets/                  # manifest.json and listen.html for review
  chatterbox/references/          # one Swedish prompt per role
  rvc/logs/swedish-<role>-v2/      # features, Rich log, resume checkpoints
  rvc/assets/weights/             # completed inference models
```

`--compact` keeps unfinished voices fully resumable. Once a **new secondary
voice** has a completed, checksum-verified model and retrieval index, it removes
that voice's large G/D optimizer checkpoints. Completed synthesis models, indices,
references, datasets and logs remain. The four previously trained voices are
left intact. Allow roughly **1.5–2 GB additional permanent space**, plus about
**1.3 GB temporary space** for the active voice. The runner checks free space
before starting each voice and stops safely if space is low.

Omit `--compact` to retain checkpoints for further training beyond 20 epochs.
That needs roughly **27 GB more** for the 22 new roles. Compact models remain
usable for synthesis but cannot continue to a higher epoch target without
restoring their training checkpoints. `--epochs` is a total target, not a number
to add to the previous run.

Train only particular roles, or reduce CPU use:

```sh
/usr/bin/python3 tools/freddi_fisk/train_cast.py --compact --speakers grandma ray king_crab
/usr/bin/python3 tools/freddi_fisk/train_cast.py --compact --threads 1
```

`prepare` copies and verifies the Swedish datasets and installs references
without training. It has already been run for this checkout. Subsequent runs
verify the local copies and do not need to read the original cloud-backed WAVs.
`--runtime-root` selects a different **already installed** Voice Studio runtime.

## Source coverage and expected quality

The inventory contains **26 speaking roles**, including the existing four and
unnamed cameos. Labels come from explicit dialogue positions or colours in
checksum-pinned game scripts. They have not all been listening-audited. The
manifest retains the script, line, speech offset, original PCM hash and output
WAV hash for each selection. The script descriptions are retained English text;
the recordings themselves are from the Swedish game. Conflicting/shared audio
is excluded. Validation clips are never used for training or references.

| Roles | Original training speech |
|---|---|
| Freddi / Linus | 10m44s / 3m11s; existing models |
| Boss / Spongehead | 54s / 76s; existing models |
| Mr. Starfish / pearl-game oyster | 3m21s / 2m22s |
| King Crab / old seahorse | 2m05s / 1m57s |
| Grandma / Eddie / Ray / Augie | 55s / 48s / 46s / 39s |
| Fiddler Crab / Fineas / Herman / Mrs. Halibut | 33s / 34s / 30s / 28s |
| Gabby / Squidfather / gatekeeper | 16s / 13s / 8s |
| Jason / kelp celebrant / Snappy / Sam | 6s / 5s / 5s / 3s |
| Ending guppy / zoo visitor / dogfish | 2.5s / 1.8s / 0.5s |

Roles with only seconds of speech are **experimental and may sound poor**.
The Squidfather has grumbles rather than normal dialogue. Tiny clips are repeated
only when needed to meet RVC's minimum segment length or Chatterbox's prompt
length. The report shows original durations and repetition explicitly; this
does not create more training information. Cameos with uncertain identities
remain separate roles rather than being mixed into a named character. English
Freddi Fish 2 recordings are not included.

After training, restart Voice Studio if it was already running, then refresh
the page. Completed new voices appear under **Fler röster från första spelet**.

```sh
/usr/bin/python3 tools/freddi_fisk/voice_studio.py
```

Validation on 2026-10-25: all 26 datasets and reference hashes were checked.
A separate one-source Dogfish experiment completed real feature extraction,
an epoch-1 export, a checkpoint pause, and a resume to epoch 3. Its temporary
model and optimizer checkpoints were removed. This verifies training plumbing;
it is not a listening evaluation or a full cast training run.
