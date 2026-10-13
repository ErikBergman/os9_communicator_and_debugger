# Physical iMac test — 13 October 2026

The user reports that the patched Freddi Fisk application works on the physical
Mac OS 9 iMac:

> It works perfectly. I'm amazed, to be honest. How is this even possible?

This is the first reported successful physical-system test of the FCB repair.
The patch implementation was already committed as `29d44bd`.

## Delivered build

- Archive: `Freddi-Fisk-OS9-test.bin`, 743,808 bytes.
- Archive SHA-256: `481135551234f3a996ba052f527f9a47e029c32cd3ba0c3c9af932c13ea7de79`.
- Patched data-fork SHA-256: `ed76d3c0da7cb8063ac4f9fd529ee5b0ec014c7a1c71852c34375acd40b24409`.
- The MacBook successfully downloaded the served archive through HTTP and
  verified that checksum before giving the iMac download instructions.
- The original image, preserved forks and resource-fork bytes remain unchanged.

## File-placement issue during testing

The first attempt reported `[0,0] Unable to open` with the filename
`Hårddisk:Desktop Folder: Freddi Fisk (2)`. The game itself contains the
`Unable to open "%s" file` diagnostic. MacsBug did not open for this error.

The archive contains only the patched application, not the game data. The user
was instructed to place the application alongside **Freddi Fisk (0)**,
**Freddi Fisk (1)**, **Freddi Fisk (2)** and **Freddi Fisk (4)** in a separate
hard-disk folder, copying the data from the Mac CD/image with Finder. The
success report followed those instructions; the final layout was not separately
inspected from the MacBook.

The direct Ethernet adapter had also disappeared earlier. The user reported
that unplugging its power supply restored it. The MacBook then verified `en5`
active at 100baseTX full-duplex with `192.168.77.1/24`, and the file-transfer
server served the checksum-matched patch.

## Scope of confirmation

The user confirms successful operation of the patched game. They have not
separately described whether the CD-speed test ran again, which scenes were
played, or whether saving, quitting and reopening a save were exercised. No
instrumented runtime trace or executable checksum was collected on the iMac.
An identical CD-backed reproduction and long-term gameplay are not established
by this report alone.

The 26 automated PowerPC emulation cases, independent import mapping,
Capstone/Ghidra review and MacBinary preservation checks remain documented in
the adjacent reports. Their build-time "physical test required" status is
historical; this record captures the subsequent user result.
