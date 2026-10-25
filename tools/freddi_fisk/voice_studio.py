#!/usr/bin/env python3
"""Small localhost interface for Swedish Freddi/Linus text-to-voice."""

import argparse
import json
import re
import threading
import webbrowser
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from urllib.parse import urlsplit

from text_to_voice import UnavailableError, VoiceStudio

STATIC = Path(__file__).with_name("voice_studio_ui")
IDENTIFIER = re.compile(r"^[0-9a-f]{32}$")


class StudioServer(ThreadingHTTPServer):
    daemon_threads = True

    def __init__(self, address, studio=None):
        super().__init__(address, Handler)
        self.studio = studio or VoiceStudio()


class Handler(BaseHTTPRequestHandler):
    def local_request(self):
        port = self.server.server_port
        allowed = {f"127.0.0.1:{port}", f"localhost:{port}"}
        origin = self.headers.get("Origin")
        return self.headers.get("Host") in allowed and (
            origin is None or origin in {f"http://{host}" for host in allowed})

    def send(self, status, body, content_type="application/json; charset=utf-8", extra=None):
        if isinstance(body, (dict, list)):
            body = json.dumps(body, ensure_ascii=False).encode("utf-8")
        self.send_response(status)
        self.send_header("Content-Type", content_type)
        self.send_header("Content-Length", str(len(body)))
        self.send_header("Cache-Control", "no-store")
        self.send_header("X-Content-Type-Options", "nosniff")
        self.send_header("Content-Security-Policy", "default-src 'self'; style-src 'self'; script-src 'self'; object-src 'none'; frame-ancestors 'none'")
        for key, value in (extra or {}).items():
            self.send_header(key, value)
        self.end_headers()
        self.wfile.write(body)

    def do_GET(self):
        if not self.local_request():
            return self.send(403, {"error": "Endast lokal åtkomst är tillåten."})
        path = urlsplit(self.path).path
        if path == "/api/status":
            return self.send(200, self.server.studio.status())
        if path.startswith("/api/jobs/"):
            identifier = path.removeprefix("/api/jobs/")
            job = self.server.studio.get(identifier) if IDENTIFIER.fullmatch(identifier) else None
            return self.send(200, job) if job else self.send(404, {"error": "Inspelningen hittades inte."})
        if path.startswith("/audio/"):
            identifier = path.removeprefix("/audio/")
            job = self.server.studio.get(identifier) if IDENTIFIER.fullmatch(identifier) else None
            if job and job["state"] == "done":
                audio = self.server.studio.output / identifier / "voice.wav"
                return self.send(200, audio.read_bytes(), "audio/wav", {
                    "Content-Disposition": f'inline; filename="{job["speaker"]}-{identifier[:8]}.wav"'})
            return self.send(404, {"error": "Inspelningen är inte klar."})
        files = {"/": ("index.html", "text/html; charset=utf-8"),
                 "/app.js": ("app.js", "text/javascript; charset=utf-8"),
                 "/style.css": ("style.css", "text/css; charset=utf-8")}
        if path in files:
            filename, content_type = files[path]
            return self.send(200, (STATIC / filename).read_bytes(), content_type)
        self.send(404, {"error": "Sidan hittades inte."})

    def do_POST(self):
        if not self.local_request():
            return self.send(403, {"error": "Endast lokal åtkomst är tillåten."})
        if self.path != "/api/jobs":
            return self.send(404, {"error": "Sidan hittades inte."})
        if self.headers.get_content_type() != "application/json" or self.headers.get("Transfer-Encoding"):
            return self.send(415, {"error": "Använd JSON för text och röstval."})
        try:
            lengths = self.headers.get_all("Content-Length", [])
            if len(lengths) != 1 or not 0 < int(lengths[0]) <= 8192:
                return self.send(413, {"error": "Förfrågan är för stor eller saknar längd."})
            data = json.loads(self.rfile.read(int(lengths[0])))
            if not isinstance(data, dict):
                raise ValueError("Förfrågan måste innehålla text och röstval.")
            job = self.server.studio.create(data.get("text"), data.get("speaker"),
                                            data.get("rate", 160), data.get("pitch", 0))
            self.send(202, job)
        except (ValueError, UnicodeDecodeError) as error:
            self.send(400, {"error": str(error)})
        except UnavailableError as error:
            self.send(503, {"error": str(error)})
        except OverflowError as error:
            self.send(429, {"error": str(error)})


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--port", type=int, default=8765)
    parser.add_argument("--no-browser", action="store_true")
    args = parser.parse_args()
    server = StudioServer(("127.0.0.1", args.port))
    url = f"http://127.0.0.1:{server.server_port}"
    print(f"Freddi & Linus röststudio: {url}\nTryck Ctrl+C för att stänga.", flush=True)
    if not args.no_browser:
        threading.Timer(0.5, lambda: webbrowser.open(url)).start()
    try:
        server.serve_forever()
    except KeyboardInterrupt:
        pass
    finally:
        server.server_close()
        server.studio.close()


if __name__ == "__main__":
    main()
