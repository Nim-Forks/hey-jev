"""Entry point for the macOS app bundle: same as `python siri.py --ui`."""
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from assistant_ui import run_app

run_app()
