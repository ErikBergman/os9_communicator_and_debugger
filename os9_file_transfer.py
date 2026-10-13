#!/usr/bin/env python3
"""File transfers through classic browsers; Python 3 standard library only."""

import argparse
from datetime import datetime
from email.message import Message
from email.parser import Parser
from html import escape
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
import os
from pathlib import Path
import re
import socket
import stat
import tempfile
import unicodedata
from urllib.parse import quote, unquote, urlsplit
from uuid import uuid4

CHUNK = 64 * 1024
HEADER_LIMIT = 16 * 1024
ROOT = Path(__file__).resolve().parent


class UploadError(ValueError):
    pass


class Body:
    """Read exactly the advertised body, with bounded reads and header lines."""

    def __init__(self, stream, length):
        self.stream, self.remaining = stream, length

    def read(self, size):
        if not self.remaining:
            return b""
        data = self.stream.read(min(size, self.remaining))
        if not data:
            raise UploadError("The upload ended before the whole file arrived.")
        self.remaining -= len(data)
        return data

    def line(self):
        data = self.stream.readline(min(HEADER_LIMIT + 1, self.remaining))
        self.remaining -= len(data)
        if len(data) > HEADER_LIMIT or not data.endswith(b"\r\n"):
            raise UploadError("Invalid or incomplete upload headers.")
        return data


def receive_file(stream, length, content_type, directory, max_bytes):
    """Accept one multipart file and publish it only after complete receipt."""
    content = Message()
    content["Content-Type"] = content_type
    boundary = content.get_boundary()
    if content.get_content_type() != "multipart/form-data" or not boundary:
        raise UploadError("Use the file upload form on the home page.")
    if not re.fullmatch(r"[0-9A-Za-z'()+_,./:=? -]{1,70}", boundary) or boundary.endswith(" "):
        raise UploadError("Invalid upload boundary.")
    boundary = boundary.encode("ascii")
    body = Body(stream, length)
    if body.line() != b"--" + boundary + b"\r\n":
        raise UploadError("Invalid start of upload.")
    headers = bytearray()
    while True:
        line = body.line()
        if line == b"\r\n":
            break
        headers.extend(line)
        if len(headers) > HEADER_LIMIT:
            raise UploadError("Upload headers are too large.")
    # IE 5 on Swedish OS 9 commonly sends raw Mac Roman filenames.
    try:
        decoded = headers.decode("utf-8")
    except UnicodeDecodeError:
        decoded = headers.decode("mac_roman")
    part = Parser().parsestr(decoded)
    if part.get_content_disposition() != "form-data" or part.get_param("name", header="content-disposition") != "file":
        raise UploadError("Choose one file using the upload form.")
    filename = part.get_filename()
    if not filename:
        raise UploadError("Choose a file before clicking Upload.")
    # Browsers can supply a Windows or classic Mac full path.
    filename = re.split(r"[/\\:]", filename)[-1]
    filename = "".join(c for c in filename if ord(c) >= 32 and ord(c) != 127).strip()
    if filename in ("", ".", ".."):
        raise UploadError("The file needs a valid filename.")
    # Leave room for the unique receipt prefix within filesystem name limits.
    while len(filename.encode("utf-8")) > 180:
        filename = filename[:-1]
    marker = b"\r\n--" + boundary
    pending = b""
    size = 0
    temporary = None
    try:
        with tempfile.NamedTemporaryFile(dir=directory, prefix=".upload-", delete=False) as output:
            temporary = Path(output.name)

            def write(data):
                nonlocal size
                size += len(data)
                if size > max_bytes:
                    raise UploadError("The file exceeds the configured upload limit.")
                output.write(data)

            finished = False
            while not finished:
                chunk = body.read(CHUNK)
                if not chunk:
                    raise UploadError("The upload is missing its closing boundary.")
                pending += chunk
                search_from = 0
                while True:
                    index = pending.find(marker, search_from)
                    if index < 0 or len(pending) < index + len(marker) + 2:
                        break
                    suffix = pending[index + len(marker):index + len(marker) + 2]
                    if suffix == b"\r\n":
                        raise UploadError("Upload one file at a time.")
                    if suffix == b"--":
                        end = index + len(marker) + 2
                        trailer = pending[end:]
                        if len(trailer) + body.remaining > 2:
                            raise UploadError("Unexpected data after the uploaded file.")
                        trailer += body.read(2)
                        if trailer not in (b"", b"\r\n"):
                            raise UploadError("Invalid end of upload.")
                        write(pending[:index])
                        finished = True
                        break
                    search_from = index + len(marker)
                if not finished:
                    keep = len(marker) + 2
                    if len(pending) > keep:
                        write(pending[:-keep])
                        pending = pending[-keep:]
            output.flush()
            os.fsync(output.fileno())
        name = datetime.now().strftime("%Y%m%d-%H%M%S") + "-" + uuid4().hex[:12] + "-" + filename
        destination = directory / name
        # Atomic publication without overwriting an existing receipt.
        os.link(temporary, destination)
        return destination, size
    finally:
        if temporary is not None:
            temporary.unlink(missing_ok=True)


class TransferServer(ThreadingHTTPServer):
    daemon_threads = True

    def __init__(self, address, send_dir, receive_dir, max_bytes):
        self.send_dir, self.receive_dir, self.max_bytes = send_dir, receive_dir, max_bytes
        super().__init__(address, TransferHandler)


class TransferHandler(BaseHTTPRequestHandler):
    protocol_version = "HTTP/1.0"

    def setup(self):
        super().setup()
        self.connection.settimeout(120)

    def log_message(self, fmt, *args):
        # Do not print filename or URL control characters to the terminal.
        print(f"{self.client_address[0]}: {ascii(fmt % args)}", flush=True)

    def page(self, status, message):
        html = ('<html><head><title>iMac file transfer</title></head>'
                '<body><h1>MacBook / iMac file transfer</h1>' + message + '</body></html>')
        data = html.encode("ascii", errors="xmlcharrefreplace")
        self.send_response(status)
        self.send_header("Content-Type", "text/html; charset=us-ascii")
        self.send_header("Cache-Control", "no-store")
        self.send_header("Content-Length", str(len(data)))
        self.end_headers()
        self.wfile.write(data)

    def do_GET(self):
        try:
            self.get()
        except (BrokenPipeError, ConnectionResetError, socket.timeout):
            self.log_message("Transfer connection closed or timed out")

    def get(self):
        path = urlsplit(self.path).path
        if path == "/":
            files = sorted(p for p in self.server.send_dir.iterdir() if p.is_file() and not p.is_symlink() and not p.name.startswith("."))
            listing = "".join(f'<li><a href="/download/{quote(p.name, safe="")}">{escape(p.name)}</a> ({p.stat().st_size:,} bytes)</li>' for p in files)
            self.page(200, '<h2>MacBook to iMac</h2><p>Click a file to download it. '
                      '<a href="/">Refresh file list</a>.</p>'
                      + ('<ul>' + listing + '</ul>' if files else '<p>No files ready for download.</p>')
                      + '<h2>iMac to MacBook</h2><p>Choose one file, then click Upload. '
                      'Wait for the saved-file confirmation.</p>'
                      '<form action="/upload" method="POST" enctype="multipart/form-data">'
                      '<p><input type="file" name="file"></p><input type="submit" value="Upload"></form>'
                      f'<p>Upload limit: {self.server.max_bytes // (1024 * 1024):,} MiB.</p>'
                      '<p>For Classic Mac applications and files with resource forks, use a '
                      'MacBinary (.bin), BinHex (.hqx), or StuffIt (.sit) archive.</p>')
            return
        if not path.startswith("/download/"):
            self.page(404, '<p>Page not found. <a href="/">Home</a></p>')
            return
        name = unquote(path[len("/download/"):])
        if not name or name.startswith(".") or "/" in name or "\\" in name or "\x00" in name:
            self.page(404, '<p>File not found.</p>')
            return
        try:
            descriptor = os.open(self.server.send_dir / name, os.O_RDONLY | os.O_NOFOLLOW | os.O_NONBLOCK)
        except OSError:
            self.page(404, '<p>File not found.</p>')
            return
        info = os.fstat(descriptor)
        if not stat.S_ISREG(info.st_mode):
            os.close(descriptor)
            self.page(404, '<p>File not found.</p>')
            return
        with os.fdopen(descriptor, "rb") as source:
            ascii_name = unicodedata.normalize("NFKD", name).encode("ascii", "ignore").decode("ascii")
            ascii_name = re.sub(r'[^A-Za-z0-9._ -]', "_", ascii_name).strip() or "download.bin"
            mime = "application/mac-binhex40" if name.lower().endswith(".hqx") else "application/octet-stream"
            self.send_response(200)
            self.send_header("Content-Type", mime)
            self.send_header("Content-Disposition", f'attachment; filename="{ascii_name}"; filename*=UTF-8\'\'{quote(name, safe="")}')
            self.send_header("Content-Length", str(info.st_size))
            self.send_header("Cache-Control", "no-store")
            self.end_headers()
            # Fixed-length transfer; growing files cannot exceed Content-Length.
            remaining = info.st_size
            while remaining:
                data = source.read(min(CHUNK, remaining))
                if not data:
                    break
                self.wfile.write(data)
                remaining -= len(data)
            self.log_message("Download %s (%d of %d bytes)", name, info.st_size - remaining, info.st_size)

    def do_POST(self):
        if self.path != "/upload":
            self.page(404, '<p>Unknown upload endpoint.</p>')
            return
        try:
            lengths = self.headers.get_all("Content-Length", [])
            if len(lengths) != 1 or not lengths[0].isdigit() or self.headers.get("Transfer-Encoding"):
                raise UploadError("The browser must supply one Content-Length.")
            length = int(lengths[0])
            if not 0 < length <= self.server.max_bytes + HEADER_LIMIT + 256:
                self.page(413, '<p>The upload exceeds the configured limit. <a href="/">Home</a></p>')
                return
            destination, size = receive_file(self.rfile, length, self.headers.get("Content-Type", ""), self.server.receive_dir, self.server.max_bytes)
            self.log_message("Saved %s (%d bytes)", str(destination), size)
            self.page(200, f'<p>Upload complete: {escape(destination.name)} ({size:,} bytes).</p><p><a href="/">Transfer another file</a></p>')
        except (UploadError, socket.timeout) as error:
            self.page(400, f'<p>Upload failed: {escape(str(error))}</p><p><a href="/">Try again</a></p>')
        except (BrokenPipeError, ConnectionResetError):
            self.log_message("Upload connection closed")
        except OSError as error:
            self.log_message("Upload storage error: %s", str(error))
            self.page(500, '<p>Could not save the file. Check the MacBook terminal and free disk space.</p>')


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--bind", default="192.168.77.1", help="MacBook Ethernet address (default: %(default)s)")
    parser.add_argument("--port", type=int, default=8000, help="HTTP port (default: %(default)s)")
    parser.add_argument("--send-dir", type=Path, default=ROOT / "transfer" / "to-imac", help="Files offered for download")
    parser.add_argument("--receive-dir", type=Path, default=ROOT / "transfer" / "from-imac", help="Save uploaded files here")
    parser.add_argument("--max-upload-mib", type=int, default=2048, help="Maximum file size in MiB (default: %(default)s)")
    args = parser.parse_args()
    if not 1 <= args.port <= 65535 or args.max_upload_mib < 1:
        parser.error("Use a port between 1 and 65535 and a positive upload limit.")
    send_dir, receive_dir = args.send_dir.expanduser().resolve(), args.receive_dir.expanduser().resolve()
    if send_dir == receive_dir:
        parser.error("Send and receive folders must be different.")
    try:
        for directory in (send_dir, receive_dir):
            directory.mkdir(parents=True, exist_ok=True)
        server = TransferServer((args.bind, args.port), send_dir, receive_dir, args.max_upload_mib * 1024 * 1024)
    except OSError as error:
        parser.exit(1, f"Cannot start file transfer: {error}\nCheck the Ethernet address, folders, and whether the port is already in use.\n")
    print(f"Open on the iMac: http://{args.bind}:{args.port}/\n"
          f"MacBook -> iMac: put files in {send_dir}\n"
          f"iMac -> MacBook: uploads saved in {receive_dir}\n"
          "Keep this terminal open. Stop with Control-C.\n"
          "Anyone who can reach this address can download and upload files.", flush=True)
    try:
        server.serve_forever()
    except KeyboardInterrupt:
        print("\nFile transfer stopped.", flush=True)
    finally:
        server.server_close()


if __name__ == "__main__":
    main()
