"""
config.py - Centralized configuration management.

Loads config.json from the app root on startup. If the file doesn't
exist, writes DEFAULT_CONFIG to disk. Supports dot-notation access
(e.g., config.get("paths.models")) and deep-merges user overrides
on top of defaults so new keys are always available after updates.
"""

import copy
import json
from pathlib import Path

class Config:
    """Read/write wrapper around config.json with dot-notation access."""

    # Baseline values used when no config.json exists yet.
    # Any key missing from the user's file is filled from here via deep-merge.
    DEFAULT_CONFIG = {
        "paths": {
            "ffmpeg": "ffmpeg",
            "realesrgan": ".",
            "models": "SteamWorkshopAppData/models",
            "temp_dir": "SteamWorkshopAppData/temp"
        },
        "steam_profile": {
            "width": 638,
            "height": 354,
            "parts": 5,
            "min_size_mb": 4.4,
            "max_size_mb": 4.8
        },
        "artwork_showcase": {
            "main_width": 506,
            "side_width": 100,
            "height": 0
        },
        "quality": {
            "default_fps": 24,
            "max_fps": 60,
            "contrast": 1.5,
            "saturation": 1.3
        },
        "gpu": {
            "default": "auto",
            "use_gpu": True,
            "gpu_id": 0
        },
        "optimization": {
            "preserve_quality": True,
            "auto_optimize_size": True,
            "auto_detect_content": True
        }
    }

    def __init__(self, config_path: str = "config.json"):
        self.config_path = Path(config_path)
        self.config = self.load_config()

    def load_config(self) -> dict:
        """Load config from disk, merging with defaults. Returns defaults if file is missing or corrupt."""
        if self.config_path.exists():
            try:
                with open(self.config_path, 'r', encoding='utf-8') as f:
                    user_config = json.load(f)
                    # Deep-merge so new default keys are available even with old config files.
                    # deepcopy: a shallow copy would let the merge mutate the class-level
                    # DEFAULT_CONFIG nested dicts, corrupting defaults for later instances.
                    return self._deep_merge(copy.deepcopy(self.DEFAULT_CONFIG), user_config)
            except Exception:
                pass

        # File missing or unreadable — write fresh defaults
        self.save_config(self.DEFAULT_CONFIG)
        return copy.deepcopy(self.DEFAULT_CONFIG)

    def save_config(self, config: dict = None):
        """Persist current (or provided) config dict to config.json."""
        config = config or self.config
        with open(self.config_path, 'w', encoding='utf-8') as f:
            json.dump(config, f, indent=4, ensure_ascii=False)

    def _deep_merge(self, base: dict, update: dict) -> dict:
        """Recursively merge update into base. Nested dicts are merged; scalars overwrite."""
        for key, value in update.items():
            if key in base and isinstance(base[key], dict) and isinstance(value, dict):
                base[key] = self._deep_merge(base[key], value)
            else:
                base[key] = value
        return base

    def get(self, key_path: str, default=None):
        """Return a config value by dot-separated path (e.g., 'gpu.use_gpu').
        Returns default if any segment is missing."""
        keys = key_path.split('.')
        value = self.config
        for key in keys:
            if isinstance(value, dict) and key in value:
                value = value[key]
            else:
                return default
        return value

    def set(self, key_path: str, value):
        """Set a config value by dot-separated path and immediately persist to disk."""
        keys = key_path.split('.')
        config = self.config

        # Walk to the parent dict, creating missing intermediate dicts
        for key in keys[:-1]:
            if key not in config:
                config[key] = {}
            config = config[key]

        config[keys[-1]] = value
        self.save_config()
