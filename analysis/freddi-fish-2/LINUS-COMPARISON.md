# Linus: Swedish versus English training

Completed locally on 25 October 2026. The English Freddi Fish 2 Luther/Linus
model was trained for the requested Swedish-speaking comparison. The existing
Swedish Freddi Fish 1 Linus model is unchanged.

## Training and model identity

| Property | A: existing Swedish model | B: new English model |
| --- | --- | --- |
| Source | Swedish Freddi Fish 1 | English Freddi Fish 2, user's CD |
| Training clips | 105 | 85 |
| Training duration | 190.78s | 190.09s |
| Epochs | 20, existing completed run | 20, completed new run |
| Model | `swedish-linus-v2.pth` | `english-linus-freddi2-v2.pth` |

The new run used all 97 prepared segments from its duration-matched training
split; no incomplete segments were excluded. Its 16 validation clips (37.95s)
and 84 reserve clips (192.26s) were excluded from training and retrieval-index
construction. Full training took about 46 minutes on two CPU threads. The
console records every epoch from 1 through 20 and a successful final export.
The inference model is 56,265,661 bytes, with its own matching FAISS index.

Swedish model SHA-256, verified unchanged before training, afterward and during
comparison generation:

```text
9cdaccaec039ec04334820f0753b5b7a9d46a2f8df19b510fdc9aec4a33b8364
```

English model SHA-256, matching its completed-training record:

```text
cdc68738f151788fcba946047362c8f8c24dce798ccb241de68212e1714dd4aa
```

## Listening files

The final listening folder is outside iCloud Documents:

```text
~/Library/Application Support/FreddiFishVoiceStudio/comparisons/linus-sv-ff1-vs-en-ff2-calm/
```

It contains six individual WAVs and three paired WAVs, plus `index.html` with
labelled audio players. `Linus-comparison.zip` contains those nine WAVs, the
player, README, settings, results and verification notes. In each paired WAV,
**A plays first, followed by 1.25 seconds of silence, then B**. Both versions
perform Swedish.

| Example text | A duration | B duration |
| --- | ---: | ---: |
| Hej Freddi! Ska vi simma till skolan och leta efter en ny ledtråd? | 4.32s | 4.32s |
| Jag hörde ett märkligt ljud bakom dörren. Tror du att det är ett spöke? | 4.20s | 4.20s |
| På vår ö finns sju gröna sjöstjärnor och en väldigt blyg ål. | 4.04s | 4.04s |

All six listening files are mono, 16-bit PCM at 32 kHz. Two-pass loudness
matching targets -20 LUFS with a -2 dBTP ceiling. Independent measurements found
-20.00 to -19.99 LUFS and true peaks below the ceiling. Raw, unnormalized RVC
outputs and original Chatterbox guides are retained in subfolders.

Each pair uses the **identical guide file**, the same pitch setting (zero) and
the same conversion settings. The guide hashes and recorded commands were
checked against all six real inference calls. A and B have identical frame
counts within every pair. Checksums verified all 21 generated audio files,
including guides, raw outputs and paired versions. ZIP integrity passed.

## What this experiment establishes

The English-trained model successfully converts Swedish guide audio, but
intelligibility is a material concern in this small experiment. A local,
unprompted Whisper Small Swedish transcription found more word errors in B
than A on all three final examples. The recognizer also mishears parts of the
guides and the Swedish-trained voice, so its transcripts are diagnostics rather
than verified quotations of what a human hears. The user should judge voice
similarity, accent and clarity directly from the WAVs.

The initial guide pass used Chatterbox exaggeration 0.6. Automated checks raised
concerns about the third guide, so all pairs were regenerated with the calmer
0.3 setting. The final third guide's transcript was closer to the intended
words. Both models always received the same guide within a pass; no output was
selected independently to favour either model. The original pass remains in
the sibling `linus-sv-ff1-vs-en-ff2/` folder for traceability.

Training duration and epoch count are matched, while source actors, clip
counts, recording characteristics and training random states differ. This is
a practical voice-generation comparison, not an isolated causal test of
training language or proof that additional English training cannot improve it.
The shared guide uses the existing Swedish Linus Chatterbox reference; this
experiment does not test English-reference Chatterbox generation.

See [the experiment tools and commands](../../tools/freddi_fish2/README.md).
To reproduce the final guide setting, pass `--exaggeration 0.3` and the final
output folder to `compare_linus.py`. Existing checksum-verified WAVs are reused.
