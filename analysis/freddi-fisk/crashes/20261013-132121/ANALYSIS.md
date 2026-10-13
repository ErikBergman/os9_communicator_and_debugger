# Startup CD-speed-test failure

## Finding

The captured failure is a Mac OS 9 FCB-access compatibility error. MacsBug
reports **system error 119, `dsMustUseFCBAccessors`**, and its stack scan includes
`LMGetFCBSPtr+00010`. The user reports that the game was just launched, displayed
the CD-ROM speed test, ran it for a few seconds, and crashed.

Apple explains that Mac OS 9 changed its file-control-block table and makes
the PowerPC `LMGetFCBSPtr` accessor raise error 119. This is deliberate detection
of incompatible file-access code. [Apple Q&A OPS26](https://leopard-adc.pepas.com/qa/ops/ops26.html)

The preserved game executable also imports `InterfaceLib::LMGetFCBSPtr`.
Its recovered strings include `TestDriveSpeed`, `CDROMBufferingSpeed`, and
`DriveBufferingTestResult`. These static observations support investigating
the game's startup disk test, although an imported function alone does not
prove which call site was reached in this run.

## Evidence from the report

- Application: **Freddi Fisk**; system version `$0921` (Mac OS 9.2.1).
- Error: `System error #119 = dsMustUseFCBAccessors at 0639DFB8`.
- Register D0: `$00000077`, decimal 119.
- Stack scan: `002FBBE0 LMGetFCBSPtr+00010`, `FFCFB110 SysError+00018`,
  and `_vGoDriver+008E4`.
- The game heap passes MacsBug's structural check, with 2,140,496 bytes free.
  This does not exclude every possible memory problem.
- Two volumes named **Freddi** are mounted: `$FFFE` on `.AppleCD`, and `$FFFD`
  on the `.HDI` image driver. The game's resource fork and data files `(2)` and
  `(4)` are open on `$FFFE`, the physical CD volume. This capture therefore
  concerns the CD-backed run even though an image is also mounted.
- The runtime resource-fork and data-file lengths match the inspected edition.
  Their runtime bytes were not hashed, so exact identity with the uploaded
  executable is not established solely by this report.
- The fault PC is not a confirmed address in the game's PEF code. It cannot be
  patched or mapped by simply subtracting Ghidra's image base.

MacsBug's “Return addresses on the stack” list is a scan, not a fully verified
call chain. It is corroborating evidence for the named FCB accessor. The
reported error number independently identifies the compatibility class.

## Preservation

The original uploaded file is retained in `transfer/from-imac` and copied
byte-for-byte to `StdLog.macroman`. Its SHA-256 is:

```text
f37b806c670980aa1b0e39e2ac474030265a5d19cd4ab3c3cc979c4908d9fbc8
```

`StdLog.txt` is a Mac Roman decoded UTF-8 copy with CR line endings normalized
to LF. The raw report is 23,418 bytes. The upload filename records MacBook
receipt time; the iMac report clock differs and should not be used to infer
the event ordering from matching times.

## Consequence for a repair

The captured error is not evidence of damaged CD data. A candidate code repair
must replace the direct FCB-table access with a supported query suited to what
the caller needs. Apple recommends File Manager FCB-information APIs for
application code and documents FSM accessors for immediate access.
[Apple TN1184](https://leopard-adc.pepas.com/technotes/tn/tn1184.html)

Blindly suppressing the error or making the accessor return the old low-memory
pointer would leave the incompatible table assumptions in place. No game or
system binary has been patched. The next step is to identify the game's FCB
caller and determine which file/volume information the speed test requests.

## Static caller trace status

A focused Ghidra probe was prepared, but its rerun stalled during Java
framework-JAR loading, before game analysis began. The thread dump showed the
main thread waiting in `RandomAccessFile.readBytes0` while opening a JAR ZIP
directory. The optional probe was stopped. No static caller address or runtime
address mapping is claimed from that attempt. The earlier completed PEF export
and the preserved crash evidence remain available.
