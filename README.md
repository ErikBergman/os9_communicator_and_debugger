# MacBook / Mac OS 9 file transfer

Run this in Terminal on the MacBook (Python 3, no extra packages):

```sh
python3 "/Users/erikbergman/Documents/Programmering/MacOS9/os9_communicator_and_debugger/os9_file_transfer.py"
```

On the iMac, open **Internet Explorer 5** and visit:

```text
http://192.168.77.1:8000/
```

Use the direct Ethernet settings from [HANDOVER.md](HANDOVER.md): MacBook
`192.168.77.1`, iMac `192.168.77.2`, subnet mask `255.255.255.0`.
The transfer server uses port 8000 so the existing communicator on port 5000
can keep running. If macOS asks, allow Python incoming connections.

## MacBook to iMac

The script creates `transfer/to-imac` beside itself. Put the files you want to
send in that folder. Refresh the browser page on the iMac and click a filename
to download it. The page lists files directly in the folder, excluding hidden
files, folders, and symbolic links. Finish copying a file into the folder before
downloading it.

## iMac to MacBook

Use **Browse...** in the page's upload form, choose a file, and click **Upload**.
Wait for **Upload complete** before closing the page. Uploaded files appear in
`transfer/from-imac` beside the script. Each filename gets a timestamp and unique
prefix; repeated uploads keep separate copies. Failed or interrupted uploads
are removed and are never published as completed files. A forced process kill
may leave a hidden `.upload-*` temporary file, which can be removed when the
server is stopped.

Transfers stream in 64 KiB chunks. The default upload limit is 2048 MiB, suitable
for a CD image; the browser and OS may impose their own limits. There is no
resume support. Zero-byte files are supported. Keep the Terminal running during
transfers; stop the server with **Control-C**.

## Classic Mac file preservation

HTTP transfers the selected file's bytes, not its resource fork or Finder
type/creator metadata. For Classic applications and other files needing that
metadata, first package them on the sending Mac as **MacBinary (`.bin`), BinHex
(`.hqx`), or StuffIt (`.sit`)**, then unpack on the receiving Mac with an
appropriate tool such as StuffIt Expander on OS 9. Ordinary data files can be
sent directly. For a disk image, transfer its data file; if the image file itself
also needs resource-fork metadata, package it too. Resource forks stored *inside*
an intact disk image remain inside the image.

Swedish upload filenames are read as UTF-8 when valid, otherwise Mac Roman for
IE 5. The browser page displays Swedish names. For old browsers, download names
use an ASCII fallback (for example, `sjögräs.img` becomes `sjogras.img`);
the file contents are unchanged.

## Optional settings

```sh
python3 os9_file_transfer.py --bind 192.168.77.1 --port 8000 \
  --send-dir "/path/to/files-for-imac" \
  --receive-dir "/path/to/files-from-imac" \
  --max-upload-mib 4096
```

The server uses plain HTTP and has no password. Run it on the direct Ethernet
link and put only files intended for sharing in the send folder. It neither
executes uploads nor exposes arbitrary MacBook paths.

Local regression checks (standard library only):

```sh
python3 -m unittest discover -s tests -v
```

The pages use ordinary links and a single multipart upload form, without
JavaScript, HTTPS, or modern browser APIs. Actual IE 5 compatibility still needs
a transfer test on the physical iMac.
