#!/usr/bin/env python3
"""
BeamDrop: Standalone entrypoint. Run with: `python beamdrop.py`
"""

import sys
from pathlib import Path

# Ensure beamdrop package is in path
sys.path.insert(0, str(Path(__file__).parent))

from beamdrop.__main__ import main

if __name__ == "__main__":
    main()
