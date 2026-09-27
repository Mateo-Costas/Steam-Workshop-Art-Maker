"""
config.py - Centralized configuration management.

Loads config.json from the app folder (see app_paths). Missing keys are
filled from DEFAULT_CONFIG by a deep merge, so new settings are available
after updates without touching the user's file. Supports dot-notation access,
e.g. config.get("paths.models").
"""

import copy
import json
import logging
from pathlib import Path
from typing import Optional

from app_paths import CONFIG_FILE

logger = logging.getLogger("WorkshopArt.config")


class Config:
    """Read/write wrapper around config.json with dot-notation access."""

    # Relative paths are resolved from the app folder (app_paths.resolve).
    DEFAULT_CONFIG = {
        "paths": {
            "models": "SteamWorkshopAppData/models",
        },
        # Workshop Showcase 5-part banner: canvas size and number of columns.
        "steam_profile": {
            "width": 638,
            "height": 354,
            "parts": 5,
        },
        # Artwork Showcase main + side panels (height 0 = keep aspect ratio).
        "artwork_showcase": {
            "main_width": 506,
            "side_width": 100,
            "height": 0,
        },
        "ui": {
            "language": "ES",
            "is_anime": True,
            "scale": 100,
            "recent_files": [],
        },
    }

    def __init__(self, config_path: Optional[str] = None):
        self.config_path = Path(config_path) if config_path else CONFIG_FILE
        self.config = self.load_config()

    def load_config(self) -> dict:
        """Load config from disk merged over the defaults.

        A corrupt file is kept as config.json.bak and replaced by defaults.
        """
        if self.config_path.exists():
            try:
                with open(self.config_path, "r", encoding="utf-8") as f:
                    user_config = json.load(f)
                # deepcopy: merging into the class-level dict would corrupt
                # the defaults for every later instance.
                return self._deep_merge(copy.deepcopy(self.DEFAULT_CONFIG), user_config)
            except (OSError, ValueError) as e:
                logger.warning("config.json ilegible (%s); se guarda copia y se regenera", e)
                try:
                    self.config_path.replace(self.config_path.with_suffix(".json.bak"))
                except OSError:
                    pass
        config = copy.deepcopy(self.DEFAULT_CONFIG)
        self.save_config(config)
        return config

    def save_config(self, config: Optional[dict] = None) -> None:
        """Persist the current (or given) config atomically."""
        config = config if config is not None else self.config
        tmp = self.config_path.with_suffix(".json.tmp")
        try:
            self.config_path.parent.mkdir(parents=True, exist_ok=True)
            with open(tmp, "w", encoding="utf-8") as f:
                json.dump(config, f, indent=4, ensure_ascii=False)
            tmp.replace(self.config_path)
        except OSError as e:
            logger.warning("No se pudo guardar config.json: %s", e)

    def _deep_merge(self, base: dict, update: dict) -> dict:
        """Recursively merge update into base. Nested dicts are merged; scalars overwrite."""
        for key, value in update.items():
            if key in base and isinstance(base[key], dict) and isinstance(value, dict):
                base[key] = self._deep_merge(base[key], value)
            else:
                base[key] = value
        return base

    def get(self, key_path: str, default=None):
        """Return a value by dot-separated path (e.g. 'ui.language'), or default."""
        value = self.config
        for key in key_path.split("."):
            if isinstance(value, dict) and key in value:
                value = value[key]
            else:
                return default
        return value

    def set(self, key_path: str, value) -> None:
        """Set a value by dot-separated path and persist it immediately."""
        keys = key_path.split(".")
        node = self.config
        for key in keys[:-1]:
            if not isinstance(node.get(key), dict):
                node[key] = {}
            node = node[key]
        node[keys[-1]] = value
        self.save_config()
