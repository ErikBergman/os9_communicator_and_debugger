# OS 9 communicator and debugger handover

Updated: 13 October 2026, Europe/Stockholm.

## Browser file-transfer addition

A standalone file-transfer server now lives in this repository:
`tools/file_transfer/os9_file_transfer.py`. Run it with Python 3 on the MacBook and open
`http://192.168.77.1:8000/` in Internet Explorer 5 on the iMac. It offers files
from `transfer/to-imac` and saves uploads in `transfer/from-imac`, both at
the repository root. Port 8000 lets it coexist with the communicator on port 5000.
It streams files, defaults to a 2048 MiB upload limit, and requires no packages.
See [the file-transfer instructions](tools/file_transfer/README.md) for commands, options, and resource-fork preservation.
The addition does not relocate or modify the existing communicator below.
Actual transfers with IE 5 on the physical iMac still need verification.

## Current outcome and status

The uploaded Freddi Fisk image was inspected read-only on 13 October 2026.
Its SHA-256 is `29f8319c86cfbfe22c3cd8658b1ac7a1c0aa61bea9b3a26b9c794c744027d77c`.
It is a raw Mode 1 hybrid CD image with HFS and ISO 9660 filesystems.
The HFS catalog contains 12 files; the Windows side contains 259 files.
Both forks and Finder metadata were preserved separately for every HFS file.
The game application has PowerPC PEF code in its data fork and 68k CODE
resources in its resource fork. See [the inspection report](analysis/freddi-fisk/INVENTORY.md)
and `analysis/freddi-fisk/inventory.json`. The source checksum and modification
time were unchanged afterward. No Freddi crash diagnosis or repair has been
performed. `tools/freddi_fisk/inspect_freddi_image.py` reproduces the inspection
using the pinned dependencies in `tools/freddi_fisk/requirements.txt`.

The PowerPC data fork was subsequently imported using Ghidra 12.1.4 with the
explicit `PowerPC:BE:32:default` profile. The accepted run produced pseudocode
for 1,022 recovered functions, 313 import symbols, and 509 defined strings,
with input hash/size/modification-time checks passing. Many pseudocode outputs
contain warnings; these are static-analysis artifacts, not recovered original
source or a confirmed crash diagnosis. Stock REA 6.4.0 rejects PEF and excludes
PowerPC profiles, so this stage uses Ghidra directly. See
[the decompilation checkpoint](analysis/freddi-fisk/decompilation/CHECKPOINT.md)
and `tools/freddi_fisk/decompile_pef.py`. The local toolchain is in ignored
`.local-tools/`; generated C files and import logs are also ignored.

A real Freddi Fisk startup report was received as
`transfer/from-imac/20261013-132121-85591d82ee76-StdLog`. The user reports a crash
after the startup CD-ROM speed test runs for a few seconds. It records system
error 119 (`dsMustUseFCBAccessors`) on Mac OS 9.2.1 and a stack-scan entry for
`LMGetFCBSPtr+00010`. Apple's TN1184/OPS26 identify this as incompatible FCB
access in Mac OS 9. The inspected executable imports that accessor, but the exact
static caller and runtime relocation have not yet been established. The game
files in this report are open from the physical CD volume `$FFFE`; a separate
image volume `$FFFD` is mounted at the same time. See
[the startup crash analysis](analysis/freddi-fisk/crashes/20261013-132121/ANALYSIS.md).
Raw report bytes and a normalized UTF-8 copy are preserved there. No game/system
patch has been made. A focused Ghidra rerun stalled during Java JAR loading
and was stopped before the new probe executed.

The MacBook and the physical iMac running Mac OS 9 communicate over a direct Ethernet connection. Browser-to-MacBook text logging, Terminal-to-iMac browser snippet delivery, and crash-report upload are implemented. AppleScript runs successfully on the iMac, and MacsBug 6.6.3 is installed and has captured a game failure.

The King's Quest VII investigation is **paused at the user's request**. The original reproducible early-game failure could no longer be reproduced. A separate failure when loading the save named `Freja3` was traced to an empty save: the user confirmed that it had never actually saved the game. Creating a new profile, saving through the proper exit workflow, and loading that save worked.

There is **no confirmed CD damage**, no game patch, and no inspected or repaired King's Quest VII disk image. The tools remain available if the original failure returns.

## Where the implementation lives

This handover is in the newly created `os9_communicator_and_debugger` directory, which already contained its own `.git` directory. The implementation and evidence currently remain in the parent workspace; they were not moved into this repository as part of writing this document.

Parent workspace: `/Users/erikbergman/Documents/Programmering/MacOS9`

| Item | Location |
| --- | --- |
| Python HTTP receiver | [tools/os9_text_receiver.py](/Users/erikbergman/Documents/Programmering/MacOS9/tools/os9_text_receiver.py) |
| zsh/bash sender function | [tools/imac-send.sh](/Users/erikbergman/Documents/Programmering/MacOS9/tools/imac-send.sh) |
| Text and upload event log | [output/os9-text.log](/Users/erikbergman/Documents/Programmering/MacOS9/output/os9-text.log) |
| Latest displayed snippet | [output/os9-command.txt](/Users/erikbergman/Documents/Programmering/MacOS9/output/os9-command.txt) |
| MacsBug archive | [output/os9-downloads/macsbug663.hqx](/Users/erikbergman/Documents/Programmering/MacOS9/output/os9-downloads/macsbug663.hqx) |
| Captured save-load report | [StdLog-20261013-114216-f80e48a7.txt](/Users/erikbergman/Documents/Programmering/MacOS9/output/os9-crash-reports/StdLog-20261013-114216-f80e48a7.txt) |

These absolute links refer to this MacBook. A future migration should include both Python and shell files, the MacsBug archive, and any evidence needed for further analysis. The Python program derives its `output` directory from its own location: moving it changes where it reads and writes these artifacts.

## Ethernet configuration

| Setting | MacBook | iMac |
| --- | --- | --- |
| IPv4 address | `192.168.77.1` | `192.168.77.2` |
| Subnet mask | `255.255.255.0` | `255.255.255.0` |
| Router and DNS for this direct link | Blank | Blank |
| Configuration | Manual, Ethernet service | TCP/IP control panel: Ethernet, Manually |

The MacBook interface is currently `en5`; it reports an active 100baseTX full-duplex link. Interface names may change if adapters change. Wi-Fi remains a separate interface.

The user's connection test returned all four replies with no packet loss:

```sh
ping -c 4 192.168.77.2
```

The iMac sent `Hej Erik` through the browser form, and the text was received and saved on the MacBook.

## Start and stop the receiver

The program uses Python 3's standard library and requires no Python packages. During setup, `python3` resolved to `/opt/homebrew/bin/python3` (Python 3.14).

Run in a MacBook Terminal:

```sh
python3 "/Users/erikbergman/Documents/Programmering/MacOS9/tools/os9_text_receiver.py"
```

It binds specifically to `192.168.77.1:5000`. That address must be configured on the Ethernet interface before starting it. Stop it with Control-C in its owning terminal.

At handover time, a Python receiver was still listening on this address. It is a foreground process started during the chat, not an installed service or a guaranteed persistent daemon. Check before launching a second instance:

```sh
lsof -nP -iTCP:5000 -sTCP:LISTEN
```

macOS Control Center also listens on port 5000 in this environment. It coexisted with the Python server bound to the specific Ethernet address. Identify the Python listener carefully rather than terminating every process on this port.

The Codex shell sandbox blocked binding and HTTP access initially; the receiver and local network checks were run through approved sandbox escalations. User Terminal commands do not run in that Codex sandbox.

Watch text messages and report-upload events:

```sh
tail -f "/Users/erikbergman/Documents/Programmering/MacOS9/output/os9-text.log"
```

## Browser pages and endpoint behavior

The iMac opens these addresses over plain HTTP:

| Address | Behavior |
| --- | --- |
| `http://192.168.77.1:5000/` | Text-message form and links to the other tools |
| `http://192.168.77.1:5000/commands` | Latest AppleScript snippet in a read-only text box; refreshes every three seconds |
| `http://192.168.77.1:5000/commands?paused=1` | Same snippet with refresh paused, for selecting and copying |
| `http://192.168.77.1:5000/reports` | File-upload form for a MacsBug report |
| `http://192.168.77.1:5000/macsbug663.hqx` | MacsBug archive download for extraction on the iMac |

POST interfaces:

- `/message`: URL-encoded `message` field; decoded as Mac Roman and appended to `os9-text.log`. The complete body limit is 8,192 bytes. Terminal control characters are escaped in the log.
- `/commands`: URL-encoded UTF-8 `snippet` field; replaces `os9-command.txt`. The complete encoded body limit is 131,072 bytes. Empty snippets are rejected.
- `/reports`: multipart form with one file field named `report`. The complete body limit is 2 MiB. Empty files are rejected. The original bytes are saved under a generated `StdLog-<timestamp>-<suffix>.txt` filename in `output/os9-crash-reports`; the original upload filename is not retained.

Snippets are displayed as escaped HTML, with numeric character references for non-ASCII characters. Neither the receiver nor the browser executes AppleScript. The user copies a snippet into Manusredigerare and explicitly runs it there. There is no remote shell, debugger command execution, or automatic game instrumentation.

The `/commands` text-box version is the version the user requested and confirmed working. A misunderstanding briefly led to replacing it with plain text and a `/commands.txt` endpoint; those changes were **reverted at the user's request**. Do not diagnose the original text box as broken based on that earlier exchange. `/commands.txt` is not an implemented text-only endpoint now.

The receiver is a small local diagnostic helper: single-threaded, unauthenticated, and bound to the direct Ethernet address. It is not intended for public hosting. It has no request timeouts, command history, or automatic restart. Unknown GET paths currently return the home page; an unfamiliar URL returning HTTP 200 does not prove that endpoint exists.

## Send AppleScript from the MacBook

Load the function in each Terminal session where it is needed:

```sh
source "/Users/erikbergman/Documents/Programmering/MacOS9/tools/imac-send.sh"
```

Send a multiline snippet:

```sh
imac_send <<'APPLESCRIPT'
display dialog (path to system folder as text)
APPLESCRIPT
```

The quoted heredoc delimiter keeps the shell from expanding the snippet. The function reads stdin when no argument is given, URL-encodes it with `curl`, bypasses proxies for this request, and uses a ten-second timeout.

Other supported forms:

```sh
imac_send 'display dialog "Hello from the MacBook"'
imac_send < "/absolute/path/to/script.applescript"
```

On the iMac, open `/commands`, pause refresh, select the text inside the box, copy it into **Manusredigerare** (the Swedish Script Editor), and run it.

At handover time, the latest saved snippet opens the active System Folder:

```applescript
set activeSystemFolder to path to system folder
tell application "Finder"
    activate
    open activeSystemFolder
end tell
```

## System Folder location and MacsBug installation

The user found a `Systemmapp` at:

```text
Hårddisk/Applications/Spel/Slithereens/Systemmapp
```

Classic Mac OS identifies its bootable System Folder through disk metadata, often called blessing; it does not require a fixed path at the disk root. A nested folder may be active, or it may be an extra copy. The exact active path was not reported back in the chat. Use `path to system folder` on the iMac to identify it rather than assuming the location from a folder name.

MacsBug 6.6.3 was downloaded from Macintosh Repository and checked against its published SHA-1:

```text
0cfe73f284cd8382b01d1c3e3585b7d0f9a51833
```

The archive is 512,626 bytes. The copy served through the local HTTP endpoint had the same hash.

Installation was performed on the iMac: extract the `.hqx` archive with StuffIt Expander, find **MacsBug** inside **into System folder**, and place that file directly in the active **Systemmapp**, alongside System and Finder. Restart. The expected startup message is **Debugger Installed**. The subsequent photo and uploaded log establish that MacsBug is installed and functioning.

## Capture and transfer a failure

If the user resumes debugging and reproduces a failure:

1. When MacsBug appears, enter `stdlog` and press Return. This writes a diagnostic report to the iMac desktop.
2. Enter `es` and press Return to attempt to exit the failing application and return to Finder.
3. Give the report a descriptive name before the next capture, such as `Save-load-StdLog` or `Early-game-StdLog`.
4. Restart the iMac before another test. MacsBug's documentation recommends restarting after recovering from a fault.
5. Open `http://192.168.77.1:5000/reports`, select the report, and click Upload.
6. Note which action caused the failure and which generated report corresponds to it. The upload destination does not preserve the chosen filename.

MacsBug pauses the machine during inspection, including ordinary network activity. Our approach saves the report locally and uploads it after returning to normal operation. The HTTP receiver is not a debugger transport and does not automatically capture crashes.

## Captured evidence and interpretation

Only one real report was uploaded during the investigation:

```text
StdLog-20261013-114216-f80e48a7.txt
```

It is 24,907 bytes, encoded in Mac Roman with classic Mac carriage-return line endings. Preserve the original bytes; decode and normalize a copy for analysis. One synthetic upload test was removed after verifying transfer integrity. Its upload event may remain in `os9-text.log`.

The real report records a failed save-game load:

- Current application: King's Quest VII; system version `$0921` (Mac OS 9.2.1).
- `User break` at `0610A5A2`, in `CODE 0001`, offset `+46CD2`.
- Diagnostic message: `Error reading file`.
- The nearby disassembly calls `_DebugStr`; this was a deliberate error report from the game rather than a captured CPU exception.
- Register `D0 = FFFFFFD9`, signed decimal **-39**, corresponding to **eofErr**, logical end-of-file reached.
- File control block `016A`: **Freja3**, type `KQ7g`, hard-disk volume reference `FFFF`, data fork with logical length `00000000`.
- The nearby stack contains reference number `016A`, strongly linking the failed operation to that save file.
- MacsBug found the game heap structurally healthy and reported about 2.9 MiB free. This is not a comprehensive exclusion of all memory-related bugs.
- Game resource files `Data1` through `Data16` and the game executable were open from the `KQ7 CD` volume.

Initial analysis inferred that loading the zero-length save caused the error. The user then confirmed that **Freja3 had never saved the game**, and that a properly saved new profile loaded successfully. That resolves the captured save-load case without establishing anything about the physical CD's integrity.

The original early-game failure could no longer be reproduced, so there is no second report to compare. A future investigation should distinguish a newly reproduced failure from this already explained empty-save case.

The iMac's report clock and the MacBook's upload timestamp differed. Treat the filename as a receipt timestamp and use the test description to associate evidence; do not infer event ordering from matching clock times alone.

## Verification already completed

- Direct Ethernet ping and real browser message delivery from the iMac.
- MacsBug download checksum and local HTTP download checksum.
- Shell sender syntax and live POST delivery.
- Multiline and Swedish-character preservation, escaped HTML display, and pause-refresh behavior.
- The user confirmed the original snippet page and AppleScript execution in Manusredigerare worked.
- Synthetic multipart upload preserved original bytes and classic Mac line endings; the test artifact was removed.
- A real MacsBug report was uploaded and analyzed.
- Successful save and reload after the user used a new profile and the proper save/exit workflow.

No full remote debugger, OS 9 logging extension, game binary patch, CD repair, or disk-image inspection was built or performed.

## References

- [Apple: HFS Plus Volume Format](https://developer.apple.com/library/archive/technotes/tn/tn1150.html) — the `finderInfo` fields identify the bootable System Folder.
- [Apple TN1154: Debugging Java Code With MacsBug, archived PDF](https://tools.inter-net.de/files/Company/a/Apple/OS9/Java-OS9/ver118/debuggerhelp.pdf) — generic MacsBug installation, user breaks, `stdlog`, and recovery commands. This game is not a Java application; the Java-specific commands are not relevant.
- [Apple Inside Macintosh: FSRead, archived documentation](https://dev.os9.ca/techpubs/mac/Files/Files-127.html) — `eofErr = -39` and file-read behavior.
- [Macintosh Repository: MacsBug archive source](https://www.macintoshrepository.org/736-macsbug-6-6-3-6-5-3) — download and published archive checksum.
- [Apple: Open Transport Reference, archived documentation](https://leopard-adc.pepas.com/documentation/Carbon/Reference/Open_Transport/Reference/reference.html) — potential API for a future native OS 9 sender. The current communicator uses the existing browser and does not call this API directly.
