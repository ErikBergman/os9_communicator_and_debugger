# Swedish Freddi / Linus speech dataset

24 October 2026. Local source: the preserved Macintosh `Freddi Fisk (2)` data
fork, `mac-forks/25/data.fork`. Source archive and disc are unchanged.

## Extraction

`tools/freddi_fisk/extract_speech.py` decodes the archive's XOR 0x69 layer,
validates TLKB/TALK/HSHD/SDAT chunk boundaries, and exports the original unsigned
8-bit mono PCM samples to WAV. There are 1,471 recordings, about 45.20 minutes
across all characters. 1,462 recordings are 11,025 Hz; nine are 11,000 Hz.
No denoising, normalisation or resampling is applied during extraction.

The ignored `voice-work/speech/manifest.json` records original archive offsets,
resource sizes, sample rates, PCM hashes and a before/after source identity check.

## Speaker selection

NUTCracker decompiles the game's HE 73 scripts. Their retained English dialogue
contains `@T<offset>,<resource size>@` references to the Swedish recordings.
Only explicit dialogue placement is used for the initial datasets:

- `at V.270,V.271`: Freddi.
- `at V.272,V.273`: Linus (Luther in the English script).

The paired positions occur in the shared dialogue scripts and character
exchanges. They are stronger evidence than actor IDs: cutscenes/minigames
reuse one actor to perform several characters. Bare `say-line`, numeric actor
IDs and animation `talkie` tables are therefore excluded unless an offset also
has an explicit position cue elsewhere. Speaker evidence is retained per clip.
This is script-based classification, not a complete listening audit.

Only clips 1–10 seconds long are selected. Identical PCM is deduplicated before
a deterministic 90/10 split by PCM hash, so byte-identical audio cannot leak
between training and validation. Validation is excluded from RVC training.

| Character | Training clips | Training duration | Validation clips | Validation duration |
| --- | ---: | ---: | ---: | ---: |
| Freddi | 282 | 10m 43.66s | 30 | 1m 13.19s |
| Linus | 105 | 3m 10.78s | 10 | 19.98s |

The local datasets are 16-bit mono WAVs at the original sample rates, preserving
all source sample values. RVC preprocessing resamples them to the model's rate;
this does not restore frequencies absent from the original recordings.
Linus has less than RVC's recommended ten minutes, so his model is experimental.

## Local artifacts

- `voice-work/speech/`: all original speech WAVs and extraction manifest.
- `voice-work/scripts/Freddi/`: decompiled SCU scripts (English text).
- `voice-work/datasets/{freddi,linus}/{train,validation}/`: selected WAVs.
- `voice-work/datasets/manifest.json`: selection and split provenance.
- `voice-work/datasets/listen.html`: local audio review table.

Audio, transcripts, model downloads and generated training files are excluded
from Git. Only tools and summary evidence are committed.

See [the voice workflow](../../tools/freddi_fisk/VOICE-WORKFLOW.md) for setup,
reproduction, training and conversion commands.
