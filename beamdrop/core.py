"""
Core HTTP server and transfer engine for BeamDrop.
Zero-dependency, multi-threaded, memory-efficient streaming server.
"""

import os
import re
import sys
import json
import time
import socket
import secrets
import zipfile
import mimetypes
import threading
from io import BytesIO
from pathlib import Path
from http import HTTPStatus
from http.server import ThreadingHTTPServer, BaseHTTPRequestHandler
from urllib.parse import urlparse, parse_qs, unquote
from typing import Dict, Any, Optional, List, Tuple

from .qr import QRCode


def get_local_ip() -> str:
    """Detects the primary LAN IP address of this machine."""
    s = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
    try:
        # Does not actually connect or send packets, just determines routing table
        s.connect(("10.255.255.255", 1))
        ip = s.getsockname()[0]
    except Exception:
        try:
            ip = socket.gethostbyname(socket.gethostname())
        except Exception:
            ip = "127.0.0.1"
    finally:
        s.close()
    return ip


def format_bytes(size: int) -> str:
    """Formats bytes into human readable format."""
    for unit in ["B", "KB", "MB", "GB", "TB"]:
        if size < 1024.0 or unit == "TB":
            return f"{size:.1f} {unit}" if unit != "B" else f"{size} B"
        size /= 1024.0
    return f"{size:.1f} PB"


def sanitize_filename(filename: str) -> str:
    """Sanitizes filename against path traversal and forbidden characters."""
    name = os.path.basename(filename).strip()
    name = re.sub(r'[\\/*?:"<>|]', "_", name)
    name = re.sub(r"^\.+", "", name)  # Disallow leading dots (hidden files)
    if not name:
        name = f"drop_{int(time.time())}.bin"
    return name


class ClipboardStore:
    """Thread-safe in-memory store for shared clipboard notes and snippets."""
    def __init__(self, max_history: int = 50):
        self.lock = threading.Lock()
        self.max_history = max_history
        self.current_text: str = ""
        self.history: List[Dict[str, Any]] = []
        self.last_updated: float = time.time()

    def set_text(self, text: str, sender: str = "Unknown") -> Dict[str, Any]:
        with self.lock:
            self.current_text = text
            self.last_updated = time.time()
            entry = {
                "id": secrets.token_hex(6),
                "text": text,
                "sender": sender,
                "timestamp": self.last_updated,
                "length": len(text)
            }
            # Avoid consecutive duplicate entries
            if not self.history or self.history[0]["text"] != text:
                self.history.insert(0, entry)
                if len(self.history) > self.max_history:
                    self.history.pop()
            return entry

    def get_data(self) -> Dict[str, Any]:
        with self.lock:
            return {
                "current": self.current_text,
                "last_updated": self.last_updated,
                "history": list(self.history)
            }

    def clear(self):
        with self.lock:
            self.current_text = ""
            self.history.clear()
            self.last_updated = time.time()


class BeamServerContext:
    """Shared state across all request handlers in the server."""
    def __init__(
        self,
        storage_dir: Path,
        pin: Optional[str] = None,
        read_only: bool = False,
        allow_delete: bool = True,
        host: str = "0.0.0.0",
        port: int = 8080,
    ):
        self.storage_dir = storage_dir.resolve()
        self.storage_dir.mkdir(parents=True, exist_ok=True)
        self.pin = pin
        self.read_only = read_only
        self.allow_delete = allow_delete
        self.host = host
        self.port = port
        self.local_ip = get_local_ip()
        self.url = f"http://{self.local_ip}:{port}"
        self.clipboard = ClipboardStore()
        self.qr = QRCode(self.url)
        self.start_time = time.time()
        self.stats = {
            "uploaded_bytes": 0,
            "downloaded_bytes": 0,
            "files_transferred": 0
        }
        self.stats_lock = threading.Lock()

    def record_upload(self, size: int):
        with self.stats_lock:
            self.stats["uploaded_bytes"] += size
            self.stats["files_transferred"] += 1

    def record_download(self, size: int):
        with self.stats_lock:
            self.stats["downloaded_bytes"] += size


class BeamHandler(BaseHTTPRequestHandler):
    """Handles BeamDrop HTTP requests with streaming file transfers and API endpoints."""
    server_version = "BeamDrop/1.0.0"
    protocol_version = "HTTP/1.1"

    @property
    def ctx(self) -> BeamServerContext:
        return self.server.ctx  # type: ignore

    def log_message(self, format, *args):
        # Concise access logging
        pass

    def _send_json(self, data: Any, status: int = 200):
        body = json.dumps(data, indent=2).encode("utf-8")
        self.send_response(status)
        self.send_header("Content-Type", "application/json; charset=utf-8")
        self.send_header("Content-Length", str(len(body)))
        self.send_header("Access-Control-Allow-Origin", "*")
        self.send_header("Cache-Control", "no-cache, no-store, must-revalidate")
        self.end_headers()
        self.wfile.write(body)

    def _send_error(self, message: str, status: int = 400):
        self._send_json({"success": False, "error": message}, status=status)

    def _check_auth(self) -> bool:
        """Verifies PIN authentication if enabled."""
        if not self.ctx.pin:
            return True
            
        # Check header
        auth_header = self.headers.get("X-Beam-PIN")
        if auth_header and auth_header.strip() == self.ctx.pin:
            return True
            
        # Check cookie
        cookie_header = self.headers.get("Cookie", "")
        for item in cookie_header.split(";"):
            if item.strip().startswith("beampin="):
                val = item.strip().split("=", 1)[1]
                if val == self.ctx.pin:
                    return True
                    
        # Check query string
        parsed = urlparse(self.path)
        qs = parse_qs(parsed.query)
        if "pin" in qs and qs["pin"][0] == self.ctx.pin:
            return True
            
        return False

    def do_OPTIONS(self):
        self.send_response(200)
        self.send_header("Access-Control-Allow-Origin", "*")
        self.send_header("Access-Control-Allow-Methods", "GET, POST, DELETE, OPTIONS")
        self.send_header("Access-Control-Allow-Headers", "Content-Type, X-Beam-PIN, Range")
        self.send_header("Content-Length", "0")
        self.end_headers()

    def do_GET(self):
        parsed = urlparse(self.path)
        path = parsed.path

        # PIN login check endpoint
        if path == "/api/auth":
            is_valid = self._check_auth()
            self._send_json({"authenticated": is_valid, "pin_required": bool(self.ctx.pin)})
            return

        # QR code endpoint
        if path == "/api/qr.svg":
            svg = self.ctx.qr.to_svg().encode("utf-8")
            self.send_response(200)
            self.send_header("Content-Type", "image/svg+xml; charset=utf-8")
            self.send_header("Content-Length", str(len(svg)))
            self.send_header("Cache-Control", "public, max-age=3600")
            self.end_headers()
            self.wfile.write(svg)
            return

        # Check PIN authorization for all protected assets/APIs
        if not self._check_auth():
            if path.startswith("/api/"):
                self._send_error("Authentication required. Please provide a valid PIN.", status=401)
            else:
                self._serve_static("index.html")  # Frontend handles PIN lock screen
            return

        # API Endpoints
        if path == "/api/status":
            self._handle_api_status()
        elif path == "/api/files":
            self._handle_api_list_files()
        elif path == "/api/clipboard":
            self._send_json({"success": True, "data": self.ctx.clipboard.get_data()})
        elif path == "/api/download-all.zip":
            self._handle_download_zip()
        elif path.startswith("/api/download/"):
            filename = unquote(path[len("/api/download/"):])
            self._handle_file_download(filename)
        elif path.startswith("/api/preview/"):
            filename = unquote(path[len("/api/preview/"):])
            self._handle_file_download(filename, as_attachment=False)
        else:
            # Static file serving
            subpath = path.lstrip("/")
            if not subpath:
                subpath = "index.html"
            self._serve_static(subpath)

    def do_POST(self):
        parsed = urlparse(self.path)
        path = parsed.path

        # PIN verification endpoint
        if path == "/api/verify-pin":
            content_len = int(self.headers.get("Content-Length", 0))
            body = self.rfile.read(content_len)
            try:
                data = json.loads(body.decode("utf-8"))
                pin_input = str(data.get("pin", "")).strip()
                if pin_input == self.ctx.pin:
                    self._send_json({"success": True, "token": self.ctx.pin})
                else:
                    self._send_error("Invalid PIN code", status=403)
            except Exception:
                self._send_error("Invalid JSON payload", status=400)
            return

        if not self._check_auth():
            self._send_error("Authentication required", status=401)
            return

        if path == "/api/clipboard":
            content_len = int(self.headers.get("Content-Length", 0))
            body = self.rfile.read(content_len)
            try:
                data = json.loads(body.decode("utf-8"))
                text = data.get("text", "")
                sender = data.get("sender", self.client_address[0])
                entry = self.ctx.clipboard.set_text(text, sender=sender)
                self._send_json({"success": True, "entry": entry})
            except Exception as e:
                self._send_error(f"Failed to update clipboard: {str(e)}", status=400)
        elif path == "/api/upload":
            if self.ctx.read_only:
                self._send_error("Server is in read-only mode", status=403)
                return
            self._handle_streaming_upload()
        else:
            self._send_error("Not found", status=404)

    def do_DELETE(self):
        if not self._check_auth():
            self._send_error("Authentication required", status=401)
            return

        parsed = urlparse(self.path)
        path = parsed.path

        if path == "/api/clipboard":
            self.ctx.clipboard.clear()
            self._send_json({"success": True, "message": "Clipboard cleared"})
            return

        if path.startswith("/api/files/"):
            if not self.ctx.allow_delete or self.ctx.read_only:
                self._send_error("Deletion is disabled on this server", status=403)
                return
            filename = unquote(path[len("/api/files/"):])
            self._handle_file_delete(filename)
        else:
            self._send_error("Endpoint not supported", status=404)

    def _serve_static(self, rel_path: str):
        """Serves static UI files securely from the embedded web package."""
        base_web_dir = Path(__file__).parent / "web"
        safe_rel_path = os.path.normpath(rel_path).lstrip(os.sep).lstrip("/")
        file_path = (base_web_dir / safe_rel_path).resolve()

        # Prevent traversal outside web dir
        if not str(file_path).startswith(str(base_web_dir.resolve())) or not file_path.is_file():
            # Fallback to index.html for Single Page App routing
            file_path = base_web_dir / "index.html"

        content_type, _ = mimetypes.guess_type(str(file_path))
        if not content_type:
            content_type = "application/octet-stream"

        try:
            with open(file_path, "rb") as f:
                content = f.read()
            self.send_response(200)
            self.send_header("Content-Type", f"{content_type}; charset=utf-8" if "text" in content_type or "javascript" in content_type else content_type)
            self.send_header("Content-Length", str(len(content)))
            self.send_header("Cache-Control", "no-cache")
            self.end_headers()
            self.wfile.write(content)
        except Exception as e:
            self._send_error(f"Failed reading asset: {str(e)}", status=500)

    def _handle_api_status(self):
        """Returns server runtime status, storage capacity, and network info."""
        free_bytes = 0
        total_bytes = 0
        try:
            stat = os.statvfs(self.ctx.storage_dir) if hasattr(os, "statvfs") else None
            if stat:
                free_bytes = stat.f_bavail * stat.f_frsize
                total_bytes = stat.f_blocks * stat.f_frsize
            else:
                import ctypes
                free_bytes_ctypes = ctypes.c_ulonglong(0)
                total_bytes_ctypes = ctypes.c_ulonglong(0)
                ctypes.windll.kernel32.GetDiskFreeSpaceExW(
                    str(self.ctx.storage_dir),
                    ctypes.byref(free_bytes_ctypes),
                    ctypes.byref(total_bytes_ctypes),
                    None
                )
                free_bytes = free_bytes_ctypes.value
                total_bytes = total_bytes_ctypes.value
        except Exception:
            pass

        self._send_json({
            "version": "1.0.0",
            "uptime_seconds": int(time.time() - self.ctx.start_time),
            "local_ip": self.ctx.local_ip,
            "port": self.ctx.port,
            "url": self.ctx.url,
            "pin_protected": bool(self.ctx.pin),
            "read_only": self.ctx.read_only,
            "storage_dir": str(self.ctx.storage_dir),
            "disk_free": free_bytes,
            "disk_free_formatted": format_bytes(free_bytes),
            "stats": self.ctx.stats
        })

    def _handle_api_list_files(self):
        """Lists files in the storage directory with metadata."""
        files = []
        try:
            for entry in self.ctx.storage_dir.iterdir():
                if entry.is_file():
                    stat = entry.stat()
                    mime, _ = mimetypes.guess_type(entry.name)
                    mime = mime or "application/octet-stream"
                    category = "other"
                    if mime.startswith("image/"): category = "image"
                    elif mime.startswith("video/"): category = "video"
                    elif mime.startswith("audio/"): category = "audio"
                    elif mime == "application/pdf": category = "pdf"
                    elif mime.startswith("text/"): category = "text"

                    files.append({
                        "name": entry.name,
                        "size": stat.st_size,
                        "size_formatted": format_bytes(stat.st_size),
                        "modified": stat.st_mtime,
                        "modified_iso": time.strftime("%Y-%m-%d %H:%M:%S", time.localtime(stat.st_mtime)),
                        "mime": mime,
                        "category": category
                    })
            files.sort(key=lambda x: x["modified"], reverse=True)
            self._send_json({"success": True, "files": files, "count": len(files)})
        except Exception as e:
            self._send_error(f"Failed to list directory: {str(e)}", status=500)

    def _handle_streaming_upload(self):
        """
        Streams multipart/form-data upload directly to disk in chunks.
        Prevents Out-Of-Memory even with gigabyte-sized video uploads.
        """
        content_type = self.headers.get("Content-Type", "")
        if not content_type.startswith("multipart/form-data"):
            self._send_error("Expected multipart/form-data payload", status=400)
            return

        # Extract boundary
        boundary_match = re.search(r"boundary=([^\s;]+)", content_type)
        if not boundary_match:
            self._send_error("Missing multipart boundary", status=400)
            return

        boundary = boundary_match.group(1).encode("ascii")
        if boundary.startswith(b'"') and boundary.endswith(b'"'):
            boundary = boundary[1:-1]
            
        boundary_sep = b"--" + boundary
        boundary_end = b"--" + boundary + b"--"

        content_length = int(self.headers.get("Content-Length", 0))
        if content_length <= 0:
            self._send_error("Empty upload request", status=400)
            return

        uploaded_files = []
        remaining_bytes = content_length
        stream = self.rfile

        # Read line helper
        def readline():
            nonlocal remaining_bytes
            line = stream.readline(min(remaining_bytes, 65536))
            remaining_bytes -= len(line)
            return line

        try:
            line = readline().rstrip(b"\r\n")
            while remaining_bytes > 0 or line:
                if line == boundary_end:
                    break
                if line != boundary_sep:
                    line = readline().rstrip(b"\r\n")
                    continue

                # Parse part headers
                part_headers = {}
                while True:
                    hdr_line = readline()
                    if not hdr_line or hdr_line in (b"\r\n", b"\n"):
                        break
                    decoded_hdr = hdr_line.decode("utf-8", errors="replace").strip()
                    if ":" in decoded_hdr:
                        k, v = decoded_hdr.split(":", 1)
                        part_headers[k.strip().lower()] = v.strip()

                disposition = part_headers.get("content-disposition", "")
                filename_match = re.search(r'filename="([^"]+)"', disposition) or re.search(r'filename=([^\s;]+)', disposition)
                
                if filename_match:
                    raw_name = filename_match.group(1)
                    safe_name = sanitize_filename(raw_name)
                    dest_path = self.ctx.storage_dir / safe_name
                    
                    # Avoid clobbering existing files by appending a counter
                    counter = 1
                    stem = dest_path.stem
                    suffix = dest_path.suffix
                    while dest_path.exists():
                        dest_path = self.ctx.storage_dir / f"{stem}_{counter}{suffix}"
                        counter += 1

                    total_written = 0
                    with open(dest_path, "wb") as out_file:
                        # Stream until next boundary
                        chunk_size = 65536
                        buf = bytearray()
                        while remaining_bytes > 0:
                            chunk = stream.read(min(remaining_bytes, chunk_size))
                            if not chunk:
                                break
                            remaining_bytes -= len(chunk)
                            buf.extend(chunk)

                            # Search boundary in buffer
                            idx = buf.find(boundary_sep)
                            if idx != -1:
                                # Data before boundary belongs to file
                                file_chunk = buf[:idx]
                                if file_chunk.endswith(b"\r\n"):
                                    file_chunk = file_chunk[:-2]
                                elif file_chunk.endswith(b"\n"):
                                    file_chunk = file_chunk[:-1]
                                out_file.write(file_chunk)
                                total_written += len(file_chunk)

                                # Remainder line starts at boundary
                                line = buf[idx:].split(b"\r\n", 1)[0]
                                break
                            else:
                                # Safe chunk to write (leave margin in case boundary is split)
                                safe_len = max(0, len(buf) - (len(boundary_sep) + 16))
                                if safe_len > 0:
                                    out_file.write(buf[:safe_len])
                                    total_written += safe_len
                                    del buf[:safe_len]

                    self.ctx.record_upload(total_written)
                    uploaded_files.append({
                        "name": dest_path.name,
                        "size": total_written,
                        "size_formatted": format_bytes(total_written)
                    })
                else:
                    # Skip non-file fields
                    while remaining_bytes > 0:
                        chunk = readline()
                        if chunk.startswith(boundary_sep):
                            line = chunk.rstrip(b"\r\n")
                            break

            self._send_json({
                "success": True,
                "message": f"Successfully uploaded {len(uploaded_files)} file(s)",
                "files": uploaded_files
            })
        except Exception as e:
            self._send_error(f"Upload error: {str(e)}", status=500)

    def _handle_file_download(self, filename: str, as_attachment: bool = True):
        """Streams a requested file with full HTTP Range request support."""
        safe_name = os.path.basename(filename)
        file_path = (self.ctx.storage_dir / safe_name).resolve()

        if not str(file_path).startswith(str(self.ctx.storage_dir)) or not file_path.is_file():
            self._send_error("File not found", status=404)
            return

        file_size = file_path.stat().st_size
        mime, _ = mimetypes.guess_type(str(file_path))
        mime = mime or "application/octet-stream"

        range_header = self.headers.get("Range")
        if range_header:
            range_match = re.match(r"bytes=(\d+)-(\d*)", range_header)
            if range_match:
                start = int(range_match.group(1))
                end = int(range_match.group(2)) if range_match.group(2) else file_size - 1
                end = min(end, file_size - 1)
                length = end - start + 1

                self.send_response(HTTPStatus.PARTIAL_CONTENT)
                self.send_header("Content-Type", mime)
                self.send_header("Content-Range", f"bytes {start}-{end}/{file_size}")
                self.send_header("Content-Length", str(length))
                self.send_header("Accept-Ranges", "bytes")
                self.end_headers()

                with open(file_path, "rb") as f:
                    f.seek(start)
                    self._copy_chunked(f, length)
                self.ctx.record_download(length)
                return

        self.send_response(HTTPStatus.OK)
        self.send_header("Content-Type", mime)
        self.send_header("Content-Length", str(file_size))
        self.send_header("Accept-Ranges", "bytes")
        disposition = "attachment" if as_attachment else "inline"
        self.send_header("Content-Disposition", f'{disposition}; filename="{safe_name}"')
        self.end_headers()

        with open(file_path, "rb") as f:
            self._copy_chunked(f, file_size)
        self.ctx.record_download(file_size)

    def _copy_chunked(self, source, length: int, chunk_size: int = 65536):
        remaining = length
        while remaining > 0:
            to_read = min(remaining, chunk_size)
            chunk = source.read(to_read)
            if not chunk:
                break
            try:
                self.wfile.write(chunk)
            except (ConnectionResetError, BrokenPipeError):
                break
            remaining -= len(chunk)

    def _handle_file_delete(self, filename: str):
        safe_name = os.path.basename(filename)
        file_path = (self.ctx.storage_dir / safe_name).resolve()

        if not str(file_path).startswith(str(self.ctx.storage_dir)) or not file_path.is_file():
            self._send_error("File not found", status=404)
            return

        try:
            file_path.unlink()
            self._send_json({"success": True, "message": f"Deleted {safe_name}"})
        except Exception as e:
            self._send_error(f"Delete failed: {str(e)}", status=500)

    def _handle_download_zip(self):
        """Zips all files in storage directory and streams to user."""
        buf = BytesIO()
        with zipfile.ZipFile(buf, "w", zipfile.ZIP_DEFLATED) as zf:
            for item in self.ctx.storage_dir.iterdir():
                if item.is_file():
                    zf.write(item, arcname=item.name)
        data = buf.getvalue()
        self.send_response(200)
        self.send_header("Content-Type", "application/zip")
        self.send_header("Content-Disposition", 'attachment; filename="beamdrop_archive.zip"')
        self.send_header("Content-Length", str(len(data)))
        self.end_headers()
        self.wfile.write(data)


def create_server(
    storage_dir: Path,
    port: int = 8080,
    host: str = "0.0.0.0",
    pin: Optional[str] = None,
    read_only: bool = False,
    allow_delete: bool = True
) -> ThreadingHTTPServer:
    """Instantiates and configures the BeamDrop HTTP Server."""
    server_address = (host, port)
    server = ThreadingHTTPServer(server_address, BeamHandler)
    server.ctx = BeamServerContext( # type: ignore
        storage_dir=storage_dir,
        pin=pin,
        read_only=read_only,
        allow_delete=allow_delete,
        host=host,
        port=port
    )
    return server
