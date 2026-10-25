# RVC voice workflow checkpoint

24 October 2026. Branch: `codex/freddi-linus-rvc` in the
`os9_communicator_and_debugger` repository.

## Completed

- Extracted all 1,471 Swedish speech recordings losslessly. The original speech
  archive's SHA-256 still matches the preservation inventory.
- Prepared separate Freddi and Linus training/validation datasets using script
  dialogue positions. There is no PCM-hash overlap between the splits.
- Installed isolated RVC and NUTCracker environments. RVC's `pip check` reports
  no broken requirements. Git and base-model revisions/hashes are pinned in
  `tools/freddi_fisk/voice-tool-versions.json`.
- Prepared the full training inputs, RMVPE pitch and ContentVec/HuBERT features:

| Character | Source training clips | Complete training segments | Excluded segments |
| --- | ---: | ---: | ---: |
| Freddi | 282 | 301 | 0 |
| Linus | 105 | 106 | 0 |

- Built separate FAISS indexes for both full datasets and separate smoke tests.
- Trained separate three-clip, one-epoch smoke models. Freddi's training epoch
  took 27.4 seconds; Linus's took 42.3 seconds on CPU, excluding preparation.
- Converted one held-out recording per character. The initial output WAVs are
  non-silent 32 kHz, 16-bit mono, 1.96 seconds (Freddi) and 2.34 seconds (Linus).
- Added a macOS worker to avoid an observed OpenMP shutdown deadlock after a
  successful conversion. The native process sample showed one OpenMP runtime
  waiting for workers associated with another runtime. The worker flushes logs
  and retains the upstream CLI exit code after audio files have closed.
- Added a Swedish localhost text interface with Freddi/Linus selection, tempo
  and pitch controls, progress, playback and WAV download. macOS Alva generates
  the Swedish guide performance before character-specific RVC conversion.
- Installed a separate inference runtime in
  `~/Library/Application Support/FreddiFishVoiceStudio/runtime/`, with both
  preview models and their matching indexes. Base-model checksums and
  `pip check` pass. This avoids observed iCloud placeholder reads stalling the
  original runtime inside Documents. Source code remains in the repository.
- Verified text-to-audio through the actual browser interface for both voices:
  Freddi produced a non-silent 3.10-second WAV; Linus produced non-silent
  6.18-second and 3.22-second WAVs. Playback endpoints returned HTTP 200 and WAV
  data. These checks establish functionality, not voice similarity.
- All 29 regression tests pass, including Swedish API roundtrips, audio serving,
  input validation, local runtime selection and full/preview model selection.

The local `voice-work/` folder contains manifests, audio review HTML, generated
WAVs, installation evidence and logs. `.local-tools/rvc/logs/` contains the
prepared full experiments and the separate smoke training checkpoints.
All generated audio, transcripts and model files are excluded from Git. The
interface's entered text and generated recordings live outside iCloud Documents
under `~/Library/Application Support/FreddiFishVoiceStudio/recordings/`.

## Remaining for usable voice clones

**Full-dataset training has not been run.** The exported `*-smoke.pth` models
validate the software path; three clips and one epoch do not establish voice
similarity or performance quality. No subjective listening evaluation has been
completed. The speaker labels should also be checked by listening before a
large production run, particularly any unusual or ambiguous lines.

The original recordings are low-bandwidth 8-bit speech at roughly 11 kHz.
Freddi has about 10m 44s of training audio; Linus about 3m 11s. These constrain
the likely output quality, particularly Linus. A longer CPU training run may
take hours. RVC requires a spoken Swedish guide recording for each new line;
the new interface supplies one automatically using macOS Alva. That guide also
determines pacing and expression. Full trained models can be copied into the
interface runtime with the documented `setup_voice_tools.py profiles` command.

Reproduction and training commands are in
[the voice workflow](../../tools/freddi_fisk/VOICE-WORKFLOW.md).
