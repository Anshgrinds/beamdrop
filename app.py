#!/usr/bin/env python3
"""
BeamDrop Native Desktop Application Launcher.
Wraps BeamDrop in a native Microsoft Edge WebView2 desktop window with zero Electron bloat.
"""

import sys
import time
import socket
import threading
import webbrowser
from pathlib import Path

# Add package directory to path
root_dir = Path(__file__).parent.resolve()
sys.path.insert(0, str(root_dir))

from beamdrop.core import create_server, get_local_ip


def find_free_port(start_port: int = 8080) -> int:
    port = start_port
    while port < 65535:
        with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as s:
            if s.connect_ex(("127.0.0.1", port)) != 0:
                return port
            port += 1
    return start_port


def run_desktop_app(port: int = 8080, storage_dir: Path = None, pin: str = None):
    if storage_dir is None:
        storage_dir = root_dir / "beamdrop_shared"

    port = find_free_port(port)
    server = create_server(
        storage_dir=storage_dir,
        port=port,
        host="0.0.0.0",
        pin=pin
    )

    # Start server in background daemon thread
    server_thread = threading.Thread(target=server.serve_forever, daemon=True)
    server_thread.start()

    local_url = f"http://127.0.0.1:{port}"
    lan_url = server.ctx.url
    print(f"[*] BeamDrop Server running at {lan_url} (Local: {local_url})")

    # Try native WebView2 desktop window via pywebview
    try:
        import webview
        icon_path = str(root_dir / "beamdrop" / "web" / "favicon.png")
        
        window = webview.create_window(
            title="BeamDrop",
            url=local_url,
            width=960,
            height=740,
            min_size=(640, 520),
            background_color="#0b0f19",
            text_select=True,
            zoomable=True
        )
        print("[*] Launching native Edge WebView2 Desktop Window...")
        webview.start(gui="edgechromium", debug=False)
    except Exception as e:
        print(f"[!] Native WebView2 window could not be opened: {e}")
        print("[*] Opening in default web browser instead...")
        webbrowser.open(local_url)
        try:
            while True:
                time.sleep(1)
        except KeyboardInterrupt:
            pass
    finally:
        print("[*] Shutting down BeamDrop...")
        server.shutdown()
        server.server_close()


if __name__ == "__main__":
    import argparse
    parser = argparse.ArgumentParser(description="BeamDrop Desktop App")
    parser.add_argument("-p", "--port", type=int, default=8080)
    parser.add_argument("-d", "--dir", type=str, default=None)
    parser.add_argument("--pin", type=str, default=None)
    args = parser.parse_args()

    s_dir = Path(args.dir).resolve() if args.dir else None
    run_desktop_app(port=args.port, storage_dir=s_dir, pin=args.pin)
