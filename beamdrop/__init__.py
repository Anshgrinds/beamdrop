"""
BeamDrop: Zero-config, blazing-fast local file and clipboard transfer between PC & Mobile across Wi-Fi.
"""

__version__ = "1.0.0"
__author__ = "Anshgrinds"

from .core import create_server, get_local_ip, BeamServerContext
from .qr import QRCode

__all__ = ["create_server", "get_local_ip", "BeamServerContext", "QRCode", "__version__"]
