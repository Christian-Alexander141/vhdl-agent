#!/usr/bin/env python3
import os
import sys

ROOT_DIR = os.path.dirname(os.path.abspath(__file__))
SRC_ROOT = os.path.join(ROOT_DIR, "Schaltungsagent")
if SRC_ROOT not in sys.path:
    sys.path.insert(0, SRC_ROOT)

from src.main import main

if __name__ == "__main__":
    main()
