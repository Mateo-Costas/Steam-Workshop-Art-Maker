"""processor.py - compatibility shim.

The implementation now lives in the src/processing/ package (one module per
domain: base, frames, gif_encode, splitting, enhance, shrink). This module
re-exports SteamProcessor so `from processor import SteamProcessor` keeps
working for gui.py, gui_methods.py and any external callers.
"""
from processing import SteamProcessor

__all__ = ["SteamProcessor"]
