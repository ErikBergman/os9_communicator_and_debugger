"""Byte integrity, incomplete uploads, and HTTP download isolation."""

import hashlib
import http.client
import io
import importlib.util
from pathlib import Path
import tempfile
import threading
import tracemalloc
import unittest
from unittest.mock import patch

SCRIPT = Path(__file__).resolve().parents[1] / "os9_file_transfer.py"
SPEC = importlib.util.spec_from_file_location("file_transfer", SCRIPT)
transfer = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(transfer)
BOUNDARY = b"----IE5-upload-boundary"
CONTENT_TYPE = "multipart/form-data; boundary=" + BOUNDARY.decode()


def multipart(data, filename=b"disk.img"):
    return (b"--" + BOUNDARY + b'\r\nContent-Disposition: form-data; name="file"; filename="'
            + filename + b'"\r\nContent-Type: application/octet-stream\r\n\r\n'
            + data + b"\r\n--" + BOUNDARY + b"--\r\n")


class UploadTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.directory = Path(self.temp.name)
        self.addCleanup(self.temp.cleanup)

    def upload(self, data, filename=b"disk.img", limit=1024 * 1024):
        raw = multipart(data, filename)
        return transfer.receive_file(io.BytesIO(raw), len(raw), CONTENT_TYPE, self.directory, limit)

    def test_ie5_macroman_full_path_and_binary_bytes(self):
        data = bytes(range(256)) * 1000 + b"\r\n\x00"
        path, size = self.upload(data, "Hårddisk:Spel:sjögräs.img".encode("mac_roman"))
        self.assertTrue(path.name.endswith("sjögräs.img"))
        self.assertEqual(size, len(data))
        self.assertEqual(path.read_bytes(), data)

    def test_utf8_and_windows_path(self):
        path, _ = self.upload(b"data", "C:\\Games\\sjögräs.img".encode())
        self.assertTrue(path.name.endswith("sjögräs.img"))

    def test_empty_and_repeated_uploads(self):
        first, size = self.upload(b"")
        second, _ = self.upload(b"new")
        self.assertNotEqual(first, second)
        self.assertEqual(size, 0)
        self.assertEqual(first.read_bytes(), b"")
        self.assertEqual(second.read_bytes(), b"new")

    def test_boundary_split_and_non_delimiter_prefix(self):
        data = b"123\r\n--" + BOUNDARY + b"XY\x00trailing\r\n"
        with patch.object(transfer, "CHUNK", 7):
            path, _ = self.upload(data)
        self.assertEqual(path.read_bytes(), data)

    def test_exact_limit_and_oversize_cleanup(self):
        self.upload(b"12345", limit=5)
        existing = set(self.directory.iterdir())
        with self.assertRaises(transfer.UploadError):
            self.upload(b"123456", limit=5)
        self.assertEqual(set(self.directory.iterdir()), existing)

    def test_truncated_and_missing_boundary_cleanup(self):
        raw = multipart(b"x" * 100)
        for length, received in ((len(raw), raw[:-10]), (len(raw) - 10, raw[:-10])):
            with self.subTest(length=length):
                with self.assertRaises(transfer.UploadError):
                    transfer.receive_file(io.BytesIO(received), length, CONTENT_TYPE, self.directory, 1000)
                self.assertEqual(list(self.directory.iterdir()), [])

    def test_multiple_parts_rejected_without_receipt(self):
        raw = multipart(b"first").replace(b"--\r\n", b'\r\nContent-Disposition: form-data; name="extra"\r\n\r\nsecond\r\n--' + BOUNDARY + b"--\r\n")
        with self.assertRaises(transfer.UploadError):
            transfer.receive_file(io.BytesIO(raw), len(raw), CONTENT_TYPE, self.directory, 1000)
        self.assertEqual(list(self.directory.iterdir()), [])

    def test_browser_did_not_choose_file(self):
        with self.assertRaises(transfer.UploadError):
            self.upload(b"", filename=b"")
        self.assertEqual(list(self.directory.iterdir()), [])

    def test_large_transfer_has_bounded_memory_and_identical_digest(self):
        # Build the request on disk before tracking parser memory use.
        block = bytes(range(256)) * 256
        digest = hashlib.sha256()
        with tempfile.TemporaryFile() as source:
            prefix, suffix = multipart(b"UNIQUE_SPLIT").split(b"UNIQUE_SPLIT")
            source.write(prefix)
            for _ in range(128):
                source.write(block)
                digest.update(block)
            source.write(suffix)
            length = source.tell()
            source.seek(0)
            tracemalloc.start()
            try:
                path, size = transfer.receive_file(source, length, CONTENT_TYPE, self.directory, 8 * 1024 * 1024)
                _, peak = tracemalloc.get_traced_memory()
            finally:
                tracemalloc.stop()
        self.assertEqual(size, 8 * 1024 * 1024)
        with path.open("rb") as result:
            self.assertEqual(hashlib.file_digest(result, "sha256").digest(), digest.digest())
        self.assertLess(peak, 1024 * 1024)


class HTTPTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.temp = tempfile.TemporaryDirectory()
        cls.send = Path(cls.temp.name) / "send"
        cls.receive = Path(cls.temp.name) / "receive"
        cls.send.mkdir()
        cls.receive.mkdir()
        cls.server = transfer.TransferServer(("127.0.0.1", 0), cls.send, cls.receive, 1024 * 1024)
        cls.thread = threading.Thread(target=cls.server.serve_forever, daemon=True)
        cls.thread.start()

    @classmethod
    def tearDownClass(cls):
        cls.server.shutdown()
        cls.server.server_close()
        cls.thread.join()
        cls.temp.cleanup()

    def request(self, method, path, body=None, headers=None):
        connection = http.client.HTTPConnection("127.0.0.1", self.server.server_port, timeout=5)
        try:
            connection.request(method, path, body, headers or {})
            response = connection.getresponse()
            return response.status, dict(response.getheaders()), response.read()
        finally:
            connection.close()

    def test_ie5_style_post_and_download_byte_integrity(self):
        payload = bytes(range(256)) * 100
        raw = multipart(payload, b"imac.img")
        status, _, page = self.request("POST", "/upload", raw, {"Content-Type": CONTENT_TYPE})
        self.assertEqual(status, 200)
        self.assertIn(b"Upload complete", page)
        receipt = next(self.receive.glob("*-imac.img"))
        self.assertEqual(receipt.read_bytes(), payload)
        (self.send / "macbook.img").write_bytes(payload)
        status, headers, actual = self.request("GET", "/download/macbook.img")
        self.assertEqual(status, 200)
        self.assertEqual(headers["Content-Length"], str(len(payload)))
        self.assertEqual(actual, payload)

    def test_html_escaping_and_swedish_download_name(self):
        (self.send / "sjögräs.img").write_bytes(b"Swedish")
        (self.send / "<example>.img").write_bytes(b"html")
        status, _, page = self.request("GET", "/")
        self.assertEqual(status, 200)
        self.assertIn(b"&lt;example&gt;.img", page)
        self.assertIn(b"sj&#246;gr&#228;s.img", page)
        self.assertIn(b"/download/sj%C3%B6gr%C3%A4s.img", page)
        status, headers, actual = self.request("GET", "/download/sj%C3%B6gr%C3%A4s.img")
        self.assertEqual(status, 200)
        self.assertIn('filename="sjogras.img"', headers["Content-Disposition"])
        self.assertEqual(actual, b"Swedish")

    def test_hidden_files_traversal_symlinks_and_folders_not_served(self):
        (self.send / ".private").write_bytes(b"hidden")
        (self.send / "folder").mkdir(exist_ok=True)
        outside = self.send.parent / "outside.txt"
        outside.write_bytes(b"private")
        (self.send / "link").symlink_to(outside)
        for path in ("/download/.private", "/download/%2e%2e%2foutside.txt", "/download/link", "/download/folder", "/unknown"):
            with self.subTest(path=path):
                status, _, _ = self.request("GET", path)
                self.assertEqual(status, 404)
        _, _, page = self.request("GET", "/")
        self.assertNotIn(b"/download/link", page)

    def test_failed_http_upload_does_not_publish_a_file(self):
        existing = set(self.receive.iterdir())
        raw = multipart(b"data")[:-3]
        status, _, _ = self.request("POST", "/upload", raw, {"Content-Type": CONTENT_TYPE})
        self.assertEqual(status, 400)
        self.assertEqual(set(self.receive.iterdir()), existing)
        status, _, _ = self.request("POST", "/upload", b"", {"Content-Type": CONTENT_TYPE})
        self.assertEqual(status, 413)


if __name__ == "__main__":
    unittest.main()
