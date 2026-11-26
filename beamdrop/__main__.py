"""
CLI entry point for BeamDrop.
"""

import sys
import os
import random
import socket
import argparse
import webbrowser
from pathlib import Path

from .core import create_server, get_local_ip
from .qr import QRCode


def find_free_port(start_port: int = 8080) -> int:
    """Finds an available TCP port starting from start_port."""
    port = start_port
    while port < 65535:
        with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as s:
            if s.connect_ex(("127.0.0.1", port)) != 0:
                return port
            port += 1
    return start_port


def main():
    parser = argparse.ArgumentParser(
        prog="beamdrop",
        description="⚡ BeamDrop: Zero-config local file & clipboard transfer across your Wi-Fi."
    )
    parser.add_argument("-p", "--port", type=int, default=8080, help="Port to bind server (default: 8080)")
    parser.add_argument("-d", "--dir", type=str, default="./beamdrop_shared", help="Directory for shared files (default: ./beamdrop_shared)")
    parser.add_argument("--host", type=str, default="0.0.0.0", help="Host address to bind (default: 0.0.0.0)")
    parser.add_argument("--pin", type=str, default=None, help="Enable 4-digit PIN protection ('auto' for random PIN)")
    parser.add_argument("--read-only", action="store_true", help="Disallow incoming uploads")
    parser.add_argument("--no-delete", action="store_true", help="Disallow deleting files via web interface")
    parser.add_argument("--no-qr", action="store_true", help="Do not print terminal QR code")
    parser.add_argument("--open", action="store_true", help="Automatically open browser on launch")

    args = parser.parse_args()

    port = args.port
    # Check if port is available; if not specified by user explicitly and 8080 is taken, find next
    if port == 8080:
        port = find_free_port(8080)

    pin = args.pin
    if pin == "auto":
        pin = f"{random.randint(1000, 9999)}"

    storage_dir = Path(args.dir).resolve()
    server = create_server(
        storage_dir=storage_dir,
        port=port,
        host=args.host,
        pin=pin,
        read_only=args.read_only,
        allow_delete=not args.no_delete
    )

    local_ip = server.ctx.local_ip
    connect_url = f"http://{local_ip}:{port}"
    localhost_url = f"http://localhost:{port}"

    # Print Clean CLI Dashboard
    print("\n" + "=" * 60)
    print("   ⚡  B E A M D R O P  ⚡")
    print("   Peerless Local Transfer & Live Clipboard Bridge")
    print("=" * 60)
    print(f"  • Local Network URL : {connect_url}")
    print(f"  • Localhost URL     : {localhost_url}")
    print(f"  • Storage Directory : {storage_dir}")
    if pin:
        print(f"  • Security PIN      : \033[1;33m{pin}\033[0m")
    if args.read_only:
        print("  • Mode              : READ-ONLY")
    print("=" * 60)

    if not args.no_qr:
        print("\n  Point your phone camera at this QR code to connect:\n")
        qr = QRCode(connect_url)
        # Indent ASCII QR slightly for neat display
        for line in qr.to_ascii(border=1).splitlines():
            print("   " + line)
        print("\n" + "-" * 60)

    print("  Server is active. Press Ctrl+C anytime to stop.\n")

    if args.open:
        try:
            webbrowser.open(localhost_url)
        except Exception:
            pass

    try:
        server.serve_forever()
    except KeyboardInterrupt:
        print("\n  [!] BeamDrop shutting down cleanly...")
    finally:
        server.server_close()
        print("  [✓] Stopped.")


if __name__ == "__main__":
    main()
