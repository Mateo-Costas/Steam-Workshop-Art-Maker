"""gui_methods.py - compatibility shim.

The implementation now lives in src/ui/logic/ (one module per domain:
system, files, processing, fragmentation, upload). This module re-exports
GUIMethodsMixin so `from gui_methods import GUIMethodsMixin` keeps working.
"""
from ui.logic import GUIMethodsMixin

__all__ = ["GUIMethodsMixin"]
