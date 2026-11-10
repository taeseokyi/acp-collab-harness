"""`PYTHONPATH=tools python3 -m aimem_monitor` 진입점 (관리자 소유)."""
import sys

from .server import main

if __name__ == "__main__":
    sys.exit(main())
