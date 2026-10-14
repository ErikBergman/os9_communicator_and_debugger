# Freddi Fisk compatibility repair, explained simply

Updated 14 October 2026, Europe/Stockholm.

## The problem

Imagine a library where you used to find a book by opening the librarian's
drawer and reading its cards yourself. Then the librarian reorganizes the
drawer. Your old instructions no longer work, even though the books are still
there. The reliable way is to ask the librarian where the book is.

Freddi Fisk had a similar shortcut. When closing a file, it looked directly
inside Mac OS's private records to find the file's disk, folder and name.
Mac OS 9 changed those records and deliberately stopped programs using the
old shortcut. That produced **error 119**. The user saw the game crash after
its startup CD-ROM speed test; the crash log gave us the clue to investigate
this file-handling code.

## Where the unpatched game was expected to work

The bundled Swedish **Viktigt** readme specifies **System 7.0 or later** and
an **68040 or PowerPC Macintosh running at 25 MHz or faster**. The game was
built for the classic Mac OS environment before Mac OS 9.

| System | What we know about this file-handling code |
| --- | --- |
| **System 7.x** | The old file-record layout matched the routine's assumptions. This is the operating-system family named in the game's requirements. |
| **Mac OS 8.x, through 8.6** | Apple retained that layout, so this specific Mac OS 9 incompatibility was not present. |
| **Mac OS 9, before the patch** | The layout changed starting with 9.0. The old PowerPC shortcut raises error 119; we captured it on **9.2.1**. |
| **Mac OS 9.2.1, after the patch** | The user reported successful operation on the physical PowerPC iMac. |

The earlier compatibility range follows the game's published requirements and
Apple's description of the old layout; we have not tested this edition on
every System 7 or Mac OS 8 release. Apple's [FCBs, Now and Forever](https://leopard-adc.pepas.com/technotes/tn/tn1184.html)
explains the change at Mac OS 9 and the deliberate error from the PowerPC accessor.

## The solution

We did not have the game's original source code, but its application still
contained the instructions the computer executes. Ghidra helped us read those
PowerPC instructions. By tracing the old file-record lookup, we located one
small file-close routine and worked out what information it needed.

We replaced that routine with instructions that **ask the operating system
for the information**, using supported File Manager functions. The repaired
routine then closes the file, deletes it when it is a temporary file, and
finishes pending disk writes as appropriate. The game can continue using the
information without knowing how Mac OS stores its private records.

This changed **252 bytes inside a 340-byte routine**. We kept the executable's
size and surrounding layout, its resource fork, and the separate game-data
files intact. The repair was built as a separate application copy; the original
disk image was never modified. This patch changes the PowerPC code used by the
iMac; the application's separate 68k code remains unchanged.

Before trying it on the iMac, we ran the original and replacement instructions
through **26 emulated tests** with simulated operating-system calls. We checked
that they passed the right file information, returned the expected errors, and
left the computer's saved registers and stack intact. Independent disassembly
also checked the replacement instructions. The user then tried the patched
application on the physical iMac and reported: **"It works perfectly."** Saving,
reopening saves and extended gameplay have not been separately confirmed.

## Why this helps future projects

The useful lesson is that an old game can sometimes be repaired by changing
one small conversation with the operating system. We can leave its game rules,
pictures, sound and story alone while updating the outdated way it asks for
help. We do not need to understand every instruction in the whole game first.

For another project, we can reuse this approach:

1. **Keep an untouched original.** Record its checksum, a fingerprint of its
   bytes, so the patch can reject an unexpected version of the game.
2. **Use the failure as a clue.** A crash log can point to an obsolete system
   function and narrow the search to a small part of the program.
3. **Understand that part before replacing it.** Identify what it receives,
   what it returns, and which file operations it performs.
4. **Replace the outdated interaction.** Use supported system functions while
   keeping the information and behavior the surrounding game expects.
5. **Check the actual replacement instructions.** Test ordinary operations,
   error paths and the computer state they must preserve, then try the result
   on real hardware.

The tools and testing method can help with other preservation and compatibility
projects. The exact byte patch is specific to the verified Freddi Fisk edition;
another game needs its own investigation. See the [repair details and tools](patches/os9-fcb-v1/README.md)
and the [physical iMac test record](patches/os9-fcb-v1/IMAC-TEST.md).
