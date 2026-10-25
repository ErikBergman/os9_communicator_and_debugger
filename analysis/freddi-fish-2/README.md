# Freddi Fish 2: Swedish localization investigation

Branch: `codex/freddi-fish-2-swedish`, based on the completed voice studio merge
`eaeeb5a`. The objective is to try a Swedish localization of the user's own CD,
reusing the Swedish character voices already trained from Freddi Fish 1 and
learning additional voices from this disc's English recordings.

## Preserved disc and identified edition

The user supplied `Freddi Fish 2.iso` in the repository and authorized moving
it. It is now stored outside iCloud Documents at:

```text
~/Library/Application Support/FreddiFishVoiceStudio/sources/freddi-fish-2/Freddi Fish 2.iso
```

Size: 328,671,232 bytes (313.45 MiB). SHA-256 before and after moving and again
after read-only inspection:

```text
733209ce2daea1f1a2f75f2d3f3187668fdc54bb90e1578b93c79567fd7dd777
```

This is a cooked, 2048-byte-sector ISO 9660/Apple HFS hybrid, with 80 ISO files
and 66 HFS files. The source was not mounted or modified. HFS data and resource
forks were preserved separately, including the PowerPC application.

The resource index MD5 is `51305e929e330e24a75a0351c8f9975e`. It matches the
English **HE 99 Updated** edition in
[ScummVM's detection table](https://github.com/scummvm/scummvm/blob/master/engines/scumm/scumm-md5.h).
This edition must not be treated as the original HE 80 release, or as the HE 73
Swedish first game. The Mac and Windows copies of the four core data files are
byte-identical:

| Macintosh data fork | ISO path | Bytes | Preserved HFS catalog ID |
| --- | --- | ---: | ---: |
| `Freddi Fish 2 (0)` | `GAME/FREDDI2.HE0` | 65,413 | 96 |
| `Freddi Fish 2 (a)` | `GAME/FREDDI2.(A)` | 115,340,334 | 95 |
| `Freddi Fish 2 (2)` | `GAME/FREDDI2.HE2` | 34,564,440 | 97 |
| `Freddi Fish 2 (4)` | `GAME/FREDDI2.HE4` | 42,596,874 | 98 |

## Completed extraction

All work products are local under
`~/Library/Application Support/FreddiFishVoiceStudio/work/freddi-fish-2/`:

- `inspection/`: complete inventories, checksums, preserved HFS forks and metadata.
- `game/`: verified working copies named `Freddi2.HE0`, `Freddi2.(a)`,
  `Freddi2.HE2` and `Freddi2.HE4`, with `provenance.json`.
- `speech/`: **1,420 original recordings, 52.283 minutes**, with per-clip
  archive offsets, resource sizes and PCM hashes in `manifest.json`.
- `scripts/Freddi2/`: **48 decompiled room files**, using the existing pinned
  NUTCracker with `Version.he99`, XOR key `69`, and normal structure transforms.
- `decompile.log`: complete decompiler console output; the process exited zero.

The speech archive is plain TLKB/TALK/HSHD/SDAT. The existing extractor validates
and decodes it without changes. Recordings are unsigned 8-bit mono PCM at
11,000 or 11,025 Hz, lasting approximately 0.28–7.46 seconds. Original sample
values and rates are retained.

The XOR-decoded `Freddi2.(a)` archive contains 1,516 speech markers covering all
1,420 unique audio offsets. Every marker's resource byte count matches the
corresponding extracted clip. Markers use byte `0x7f` around `T<offset>,<size>`.
The decompiled room files display 462 such references covering 447 clips; the
remaining references also require examining data tables. A regex over displayed
dialogue alone would miss most of the audio. Speaker assignments are still to
be audited; actor IDs and palette colours from the first game do not carry over.

Audio, original scripts, disc images and copied game files remain outside Git.

## Reproduction

Use the existing Python 3.12 runtime. For a fresh inspection directory:

```sh
VOICE_PYTHON=/Users/erikbergman/.cache/codex-runtimes/codex-primary-runtime/dependencies/python/bin/python3
VOICE_RUNTIME="$HOME/Library/Application Support/FreddiFishVoiceStudio/runtime"
FF2_SOURCE="$HOME/Library/Application Support/FreddiFishVoiceStudio/sources/freddi-fish-2/Freddi Fish 2.iso"
FF2_WORK="$HOME/Library/Application Support/FreddiFishVoiceStudio/work/freddi-fish-2"
"$VOICE_PYTHON" -m pip install --target "$VOICE_RUNTIME/inspection-python" \
  -r tools/freddi_fisk/requirements.txt
PYTHONPATH="$VOICE_RUNTIME/inspection-python" "$VOICE_PYTHON" \
  tools/freddi_fisk/inspect_cooked_image.py "$FF2_SOURCE" "$FF2_WORK/inspection"
"$VOICE_PYTHON" tools/freddi_fisk/extract_speech.py \
  --source "$FF2_WORK/inspection/mac-forks/97/data.fork" --output "$FF2_WORK/speech"
```

Inspection and speech extraction refuse existing output directories. Those
outputs already exist on this Mac. The older raw-sector image reader remains
available for the first game's 2352-byte-sector image. Three synthetic ISO
checks verify inventory hashes, source identity, refusal to overwrite output,
partition bounds and rejection of a raw-sector input; the supplied hybrid disc
also completed the real inspection with its source hash unchanged.

## Voice feasibility and next experiment

English recordings can supply a new character's voice identity while a
multilingual model supplies Swedish speech. The intended experiment is:

1. Match one new character's clean English clips to script/table evidence.
2. Train a separate RVC model and index on that character's original recordings.
3. Translate a few representative lines into Swedish. Generate guides with
   Chatterbox Multilingual using an original character reference, and convert
   them with the trained RVC model.
4. Compare Chatterbox alone and Chatterbox + RVC for Swedish pronunciation,
   speaker similarity, delivery and missing/repeated words before scaling up.

This is a cross-language experiment, not yet validated for these characters.
Chatterbox supports Swedish and documents that a reference in another language
can transfer its accent; its guidance suggests testing `cfg_weight=0` for that
case. Our working first-game pipeline currently uses `0.3`. See
[the official Chatterbox documentation](https://github.com/resemble-ai/chatterbox#original-chatterbox-tips).
English-trained RVC may also handle Swedish-specific sounds unevenly. The
current Swedish Freddi/Linus models can be reused for those returning voices;
other recurring characters should be confirmed from this game's dialogue.

Training does not translate the script. Completing the localization also needs
a reviewed Swedish dialogue catalogue, font/encoding checks for å/ä/ö, safe
resource rebuilding with updated sizes and speech references, timing checks and
play testing. No translated game build or newly trained sequel character is
claimed at this checkpoint.
