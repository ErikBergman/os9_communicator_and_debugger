# Swedish shark voices: Boss and Spongehead

25 October 2026. Inputs are the existing Swedish speech extraction and HE 73
script decompilation described in [VOICE-DATASET.md](VOICE-DATASET.md). The
original archive, extracted audio and fish datasets are unchanged.

## Speaker evidence

Actor numbers are shared between characters, so they do not identify a shark.
The shark cutscenes use explicit dialogue colours within specific scripts:

| Decompiled room | Script | Boss colour | Spongehead colour |
| --- | ---: | ---: | ---: |
| `0010_room_10.scu` | 47 | 170 | 164 |
| `0052_room_52.scu` | 63 | 154 | 148 |
| `0059_room_59.scu` | 65 | 154 | 148 |
| `0060_room_60.scu` | 66 | 154 | 148 |
| `0061_room_61.scu` | 200 | 154 | 147 |

These mappings are scoped to the named room and script; colours are never
inherited from another actor command. The ambiguous room 60 script 200 line is
excluded. Room 61 colour 162 belongs to the Squidfather and is excluded.
`shark-speaker-cues.json` pins the SHA-256 of every inspected script. Each
selected clip records its script, line, colour, original resource offset and
resource size; the extractor also checks original PCM hashes.

Names follow the retained English script text. The interface describes Boss as
“Hajchefen” and Spongehead as “Hajkompisen”; these are descriptive labels rather
than verified Swedish character names. Classification is based on script
evidence, not a complete listening audit.

## Selected recordings

The cues identify 22 candidate Boss recordings and 25 Spongehead recordings.
After the existing 1–10 second duration filter and PCM deduplication:

| Character | Training clips | Training duration | Validation clips | Validation duration |
| --- | ---: | ---: | ---: | ---: |
| Boss | 20 | 54.49s | 0 | 0s |
| Spongehead | 23 | 75.99s | 2 | 4.49s |

The deterministic PCM-hash split puts no Boss recording in validation. There
is consequently no held-out Boss evaluation set. Spongehead's two validation
clips are excluded from feature preparation and training. Both datasets are
small; more epochs cannot replace missing examples or restore frequencies
absent from the original 8-bit, approximately 11 kHz recordings.

The local manifest, WAVs and `listen.html` review page are under
`~/Library/Application Support/FreddiFishVoiceStudio/runtime/shark-datasets/`.
They remain outside iCloud Documents and are not committed to Git.

## Two-stage synthesis

Each shark has a separate RVC v2, pitch-guided, 32 kHz model and retrieval index.
The full training target is 20 epochs per shark, using all of its training split
and the existing pretrained generator/discriminator. Training runs sequentially
with two CPU threads. Resumable checkpoints are saved every five epochs.

Chatterbox Multilingual uses a separate original Swedish reference for each
shark: `speech29043977.wav` for Boss (4.6s) and `speech28930217.wav` for
Spongehead (6.8s). These train-split clips condition the existing Chatterbox
model without fine-tuning its weights. Chatterbox generates the Swedish
performance, then the selected shark's trained RVC model converts it.

The orchestrator installs references, prepares RVC features/indexes, trains both
models and records successful exports. A completion record gates each shark's
availability in the app. It refuses a second concurrent orchestration and skips
completed models with matching hashes on later runs. See
[the voice workflow](../../tools/freddi_fisk/VOICE-WORKFLOW.md) for commands.

## Completed local verification

Both full models completed all 20 epochs on 25 October 2026. Boss prepared 25
complete training segments from its 20 source clips; Spongehead prepared 32
from its 23 clips. Neither preparation excluded an incomplete segment. The
exported models are approximately 53.7 MiB each, and their SHA-256 hashes match
their completion records. Each has its own matching FAISS index.

The new sentence “Nu är det hajarnas tur att prata svenska.” completed
Chatterbox → guide resampling → trained RVC for both sharks:

| Character | CPU pipeline time | Final WAV duration |
| --- | ---: | ---: |
| Boss | about 56s | 4.06s |
| Spongehead | about 47s | 2.42s |

Both outputs contain nonzero 16-bit audio. The app reports all four characters
as trained and available with Chatterbox, and both shark selections were
checked in the interface. These are execution checks; pronunciation,
naturalness and character similarity still require listening evaluation.
The original Chatterbox guides, final WAVs, engine logs and job metadata are
retained in the local recordings folder. The ignored
`voice-work/shark-pipeline-validation.json` records job identifiers, timings,
output paths and model hashes.
