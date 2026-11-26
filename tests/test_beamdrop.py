"""
Unit and integration tests for BeamDrop.
Runs completely offline with zero external dependencies.
"""

import os
import sys
import json
import time
import shutil
import urllib.request
import urllib.error
import threading
import unittest
from pathlib import Path

# Ensure root folder is in sys.path
sys.path.insert(0, str(Path(__file__).parent.parent))

from beamdrop.core import create_server, sanitize_filename, ClipboardStore
from beamdrop.qr import QRCode


class TestQRCode(unittest.TestCase):
    def test_qr_generation(self):
        url = "http://192.168.1.50:8080"
        qr = QRCode(url)
        self.assertGreaterEqual(qr.version, 1)
        self.assertGreater(qr.size, 20)
        
        # Test ASCII
        ascii_out = qr.to_ascii()
        self.assertIn("█", ascii_out)
        self.assertGreater(len(ascii_out.splitlines()), 10)
        
        # Test SVG
        svg_out = qr.to_svg()
        self.assertTrue(svg_out.startswith("<svg"))
        self.assertTrue(svg_out.endswith("</svg>"))
        self.assertIn("<rect", svg_out)

    def test_qr_version_overflow_handling(self):
        # QR supports up to ~213 bytes in Level M
        qr = QRCode("A" * 150)
        self.assertGreater(qr.version, 4)


class TestClipboardStore(unittest.TestCase):
    def setUp(self):
        self.store = ClipboardStore(max_history=5)

    def test_clipboard_operations(self):
        entry = self.store.set_text("Hello BeamDrop", sender="TestDevice")
        self.assertEqual(entry["text"], "Hello BeamDrop")
        self.assertEqual(entry["sender"], "TestDevice")

        data = self.store.get_data()
        self.assertEqual(data["current"], "Hello BeamDrop")
        self.assertEqual(len(data["history"]), 1)

        # Clear
        self.store.clear()
        data = self.store.get_data()
        self.assertEqual(data["current"], "")
        self.assertEqual(len(data["history"]), 0)


class TestBeamDropServer(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.test_dir = Path("./test_storage_dir").resolve()
        cls.test_dir.mkdir(parents=True, exist_ok=True)
        cls.port = 8990
        cls.pin = "7829"
        
        cls.server = create_server(
            storage_dir=cls.test_dir,
            port=cls.port,
            host="127.0.0.1",
            pin=cls.pin
        )
        cls.server_thread = threading.Thread(target=cls.server.serve_forever, daemon=True)
        cls.server_thread.start()
        time.sleep(0.3)  # Give server a moment to bind

    @classmethod
    def tearDownClass(cls):
        cls.server.shutdown()
        cls.server.server_close()
        shutil.rmtree(cls.test_dir, ignore_errors=True)

    def test_sanitize_filename(self):
        self.assertEqual(sanitize_filename("../../etc/passwd"), "passwd")
        self.assertEqual(sanitize_filename("test/nested/file.txt"), "file.txt")
        self.assertEqual(sanitize_filename("bad:name?.jpg"), "bad_name_.jpg")
        self.assertEqual(sanitize_filename(".hidden"), "hidden")

    def test_pin_protection_rejection(self):
        url = f"http://127.0.0.1:{self.port}/api/status"
        req = urllib.request.Request(url)
        try:
            urllib.request.urlopen(req)
            self.fail("Should have raised HTTP 401 Unauthorized without PIN")
        except urllib.error.HTTPError as e:
            self.assertEqual(e.code, 401)

    def test_pin_verification_and_authenticated_status(self):
        url = f"http://127.0.0.1:{self.port}/api/status"
        req = urllib.request.Request(url, headers={"X-Beam-PIN": self.pin})
        with urllib.request.urlopen(req) as resp:
            self.assertEqual(resp.status, 200)
            data = json.loads(resp.read().decode())
            self.assertEqual(data["version"], "1.0.0")
            self.assertTrue(data["pin_protected"])

    def test_clipboard_api_roundtrip(self):
        # Update clipboard
        url = f"http://127.0.0.1:{self.port}/api/clipboard"
        payload = json.dumps({"text": "BeamDrop Test Clip"}).encode("utf-8")
        req = urllib.request.Request(
            url,
            data=payload,
            headers={"Content-Type": "application/json", "X-Beam-PIN": self.pin},
            method="POST"
        )
        with urllib.request.urlopen(req) as resp:
            self.assertEqual(resp.status, 200)

        # Read clipboard
        req_get = urllib.request.Request(url, headers={"X-Beam-PIN": self.pin})
        with urllib.request.urlopen(req_get) as resp:
            self.assertEqual(resp.status, 200)
            data = json.loads(resp.read().decode())
            self.assertEqual(data["data"]["current"], "BeamDrop Test Clip")

    def test_file_upload_download_range_delete(self):
        upload_url = f"http://127.0.0.1:{self.port}/api/upload"
        boundary = "---------------------------BeamDropBoundary123"
        filename = "sample_test_doc.txt"
        file_content = b"BeamDrop is super fast and lightweight! 1234567890"

        # Build multipart payload
        body = (
            f"--{boundary}\r\n"
            f'Content-Disposition: form-data; name="file"; filename="{filename}"\r\n'
            f"Content-Type: text/plain\r\n\r\n"
        ).encode("utf-8") + file_content + f"\r\n--{boundary}--\r\n".encode("utf-8")

        req = urllib.request.Request(
            upload_url,
            data=body,
            headers={
                "Content-Type": f"multipart/form-data; boundary={boundary}",
                "X-Beam-PIN": self.pin
            },
            method="POST"
        )
        with urllib.request.urlopen(req) as resp:
            self.assertEqual(resp.status, 200)
            res_data = json.loads(resp.read().decode())
            self.assertTrue(res_data["success"])

        # Check in files list
        list_url = f"http://127.0.0.1:{self.port}/api/files"
        req_list = urllib.request.Request(list_url, headers={"X-Beam-PIN": self.pin})
        with urllib.request.urlopen(req_list) as resp:
            files_res = json.loads(resp.read().decode())
            file_names = [f["name"] for f in files_res["files"]]
            self.assertIn(filename, file_names)

        # Download full file
        dl_url = f"http://127.0.0.1:{self.port}/api/download/{filename}"
        req_dl = urllib.request.Request(dl_url, headers={"X-Beam-PIN": self.pin})
        with urllib.request.urlopen(req_dl) as resp:
            self.assertEqual(resp.status, 200)
            self.assertEqual(resp.read(), file_content)

        # Download range (bytes=0-9)
        req_range = urllib.request.Request(dl_url, headers={"X-Beam-PIN": self.pin, "Range": "bytes=0-9"})
        with urllib.request.urlopen(req_range) as resp:
            self.assertEqual(resp.status, 206)
            self.assertEqual(resp.read(), file_content[0:10])

        # Delete file
        del_url = f"http://127.0.0.1:{self.port}/api/files/{filename}"
        req_del = urllib.request.Request(del_url, headers={"X-Beam-PIN": self.pin}, method="DELETE")
        with urllib.request.urlopen(req_del) as resp:
            self.assertEqual(resp.status, 200)
            del_res = json.loads(resp.read().decode())
            self.assertTrue(del_res["success"])


if __name__ == "__main__":
    unittest.main()
