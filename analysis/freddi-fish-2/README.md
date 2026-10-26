# Freddi Fish 2: Swedish localization investigation

Branch: `codex/freddi-fish-2-swedish`, based on the completed voice studio merge
`eaeeb5a`. The objective is to try a Swedish localization of the user's own CD,
reusing character voices trained from the Swedish Freddi Fish 1 recordings.
The English-trained Linus comparison produced an accent the user described as
Swenglish. The chosen approach is therefore to cast sequel characters using
the Swedish first game's voices, with Chatterbox providing Swedish delivery.

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
Normalizing both literal byte `0x7f` and escaped `\x7F`/`\x7f` markers in the
decompiled files recovers all **1,516 references and 1,420 clips** too. The earlier
462-reference/447-clip count recognized only the literal form and was an
undercount. The dubbing catalogue independently cross-checks scripts against
the binary archive, speech resource sizes and original PCM hashes. Speaker
assignments still need review; actor IDs and palette colours from the first
game do not carry over.

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

## Dubbing preparation

The [Linus comparison](LINUS-COMPARISON.md) remains available as evidence for the
voice decision. Full-cast Swedish FF1 training is handled by the resumable
[cast runner](../../tools/freddi_fisk/TRAIN-CAST.md); it runs separately from
the dialogue preparation tools.

`tools/freddi_fish2/prepare_dubbing.py` creates a complete catalogue and editable
Swedish worksheet in `work/freddi-fish-2/dubbing/` under the app data directory.
Each clip has a stable ID, English text variants, original duration and audio,
archive marker/string positions, containing resource paths, script evidence and
a Swedish voice field. Room names are **storage locations**, not a reconstruction
of playback chronology. Five clips have differing English texts sharing one
recording and are flagged for review. Production prefixes such as `(PU1)` remain
in raw provenance and are omitted from the translation text.

Strict direct-dialogue cues suggest 502 Freddi clips and 214 Linus clips. The
other 704 clips remain unassigned, including animation talkie tables where
one actor can play several characters. These are hints, not approved casting.
Four school-arrival lines have Swedish **drafts**; 1,416 lines await translation.
The worksheet validator protects source fields, rejects unknown voice profiles
and requires Swedish text, character and voice before a line can be approved.
The room review pages play the original English WAVs without starting synthesis.

Next work is to review the Swedish dialogue and terminology, identify remaining
speakers and audition the newly trained Swedish voices. After that, build a
small in-game dubbing pilot to verify audio format, resource offsets, script
sizes/jumps, timing, and font/encoding support for å/ä/ö before scaling up.
No localized game build is claimed by the catalogue.
