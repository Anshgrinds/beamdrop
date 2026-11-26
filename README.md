# BeamDrop ⚡

> Instant, peer-to-peer file transfer and bidirectional clipboard bridge for your local Wi-Fi network. **Zero dependencies. Zero cloud storage. Zero setup.**

---

## 🌟 The Real-Life Problem BeamDrop Solves

Moving files, photos, videos, and clipboard text between devices (Phone ↔ PC ↔ Laptop) on the same Wi-Fi network is full of friction:
- **AirDrop** is restricted to Apple devices and does not work between Windows and Android or iPhone and Windows.
- **Messaging Apps** (WhatsApp, Telegram, Discord) compress your original photos and videos, require internet bandwidth, have file size limits, and route your personal data through third-party servers.
- **Cloud Drives** (Google Drive, Dropbox, OneDrive) waste upload and download quota, take minutes to sync, and clutter your cloud storage with temporary transfers.
- **Bluetooth** is slow (~1-2 Mbps) and requires pairing hassles.

**BeamDrop** solves this completely:
Run a single command on your PC, point your phone's camera at the ASCII QR code printed in the terminal, and your devices are instantly connected over your local Wi-Fi with gigabit LAN speed, direct disk streaming, live clipboard synchronization, and full-resolution media sharing.

---

## ✨ Features

- **Zero External Dependencies**: Engineered with pure Python standard library (`http.server`, `socket`, `threading`, `urllib`). No `pip install` required to run!
- **Terminal QR Code Generator**: Generates clean ANSI half-block QR codes directly in your terminal console and SVG in the browser using an integrated, pure-Python QR engine.
- **Memory-Efficient Streaming Uploads**: Streams multi-gigabyte video files directly to disk in chunks without high RAM usage.
- **HTTP Range Requests (Audio/Video Scrubbing)**: Supports partial content (`HTTP 206`), enabling immediate streaming playback and scrubbing of videos and songs on mobile browsers without waiting for full downloads.
- **Live Bidirectional Clipboard**: Copy text or code on your computer and immediately read it on your phone with a 1-tap "Copy" button; paste links or notes on mobile and push them straight to your PC.
- **Quick Mobile Camera Drop**: Tap "Take Photo & Beam" on mobile to snap high-resolution pictures and transfer them directly into your computer's folder without compression.
- **In-Browser File Previews**: Built-in modal viewer for images, audio tracks, videos, PDFs, and source code.
- **Optional PIN Authentication**: Protect your transfers with `--pin <code >` or `--pin auto` for secure environments.
- **Zip-All Download**: Download all shared files in one compressed archive (`/api/download-all.zip`).

---

## 🚀 Quick Start

### 1. Run Directly (No installation needed)

Clone the repository and run:

```bash
git clone https://github.com/Anshgrinds/beamdrop.git
cd beamdrop
python beamdrop.py
```

### 2. Connect Your Phone / Devices

1. Look at your terminal: an ASCII QR code will appear along with your local network URL (e.g. `http://192.168.1.50:8080`).
2. Scan the QR code using your phone's camera (iPhone Camera app or Android Google Lens).
3. Tap the link to open the web interface in Safari or Chrome.
4. Drag files or snap photos to transfer instantly!

---

## ⚙️ CLI Options & Flags

| Flag | Default | Description |
| :--- | :--- | :--- |
| `-p`, `--port` | `8080` | Port to bind the HTTP server |
| `-d`, `--dir` | `./beamdrop_shared` | Directory where shared files are stored |
| `--host` | `0.0.0.0` | Host IP to bind server |
| `--pin` | `None` | Enable 4-digit PIN access (e.g. `--pin 1234` or `--pin auto`) |
| `--read-only` | `False` | Disallow incoming file uploads and deletions |
| `--no-delete` | `False` | Disallow deleting files from the web UI |
| `--no-qr` | `False` | Suppress the ASCII QR code display in the terminal |
| `--open` | `False` | Automatically launch default browser on startup |

---

## 🏗️ Architecture

```
beamdrop/
├── beamdrop/
│   ├── __init__.py      # Package definitions & version info
│   ├── __main__.py      # CLI runner, argument parser & dashboard
│   ├── core.py          # Multi-threaded HTTP server, streaming upload, range requests, clipboard
│   ├── qr.py            # Pure-Python QR code generator (Version 1-10, Galois Field GF(2^8) Reed-Solomon)
│   └── web/
│       ├── index.html   # Glassmorphic dark UI
│       ├── app.js       # Reactive client (drag-and-drop, chunked upload, live clipboard sync)
│       └── style.css    # Responsive styles with mobile touch support
├── tests/
│   ├── __init__.py
│   └── test_beamdrop.py # Unit tests for API, streaming uploads, range requests, PIN auth & security
├── .github/workflows/
│   └── ci.yml           # Cross-platform GitHub Actions workflow (Ubuntu, Windows, macOS)
├── pyproject.toml       # PEP 621 Python package configuration
├── beamdrop.py          # Root standalone runner
└── README.md            # Documentation
```

---

## 🧪 Testing

Run the built-in test suite with Python's standard `unittest`:

```bash
python -m unittest discover -s tests -v
```

All 8 test suites run completely offline with zero external network access.

---

## 🔒 Security & Privacy

- **100% Offline & Local**: No data, telemetry, or metadata ever leaves your local network.
- **Path Traversal Protection**: All incoming filenames are strictly sanitized to prevent directory traversal attacks (`../`).
- **PIN Isolation**: Optional random 4-digit PIN locks both API endpoints and the web interface from unauthorized LAN peers.

---

## 📄 License

MIT License. Created by [Anshgrinds](https://github.com/Anshgrinds).
