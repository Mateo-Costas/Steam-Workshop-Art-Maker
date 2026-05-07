"""
config.py - Gestión de configuración centralizada
"""

import json
from pathlib import Path

class Config:
    """Gestión de configuración centralizada"""
    DEFAULT_CONFIG = {
        "paths": {
            "ffmpeg": "ffmpeg",
            "realesrgan": ".",
            "models": "models",
            "temp_dir": "temp"
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
        """Cargar configuración desde archivo o crear una por defecto"""
        if self.config_path.exists():
            try:
                with open(self.config_path, 'r', encoding='utf-8') as f:
                    user_config = json.load(f)
                    return self._deep_merge(self.DEFAULT_CONFIG.copy(), user_config)
            except Exception:
                pass
        
        self.save_config(self.DEFAULT_CONFIG)
        return self.DEFAULT_CONFIG.copy()
    
    def save_config(self, config: dict = None):
        """Guardar configuración actual"""
        config = config or self.config
        with open(self.config_path, 'w', encoding='utf-8') as f:
            json.dump(config, f, indent=4, ensure_ascii=False)
    
    def _deep_merge(self, base: dict, update: dict) -> dict:
        """Merge profundo de diccionarios"""
        for key, value in update.items():
            if key in base and isinstance(base[key], dict) and isinstance(value, dict):
                base[key] = self._deep_merge(base[key], value)
            else:
                base[key] = value
        return base
    
    def get(self, key_path: str, default=None):
        """Obtener valor de configuración con notación de punto"""
        keys = key_path.split('.')
        value = self.config
        for key in keys:
            if isinstance(value, dict) and key in value:
                value = value[key]
            else:
                return default
        return value
    
    def set(self, key_path: str, value):
        """Establecer valor de configuración"""
        keys = key_path.split('.')
        config = self.config
        
        for key in keys[:-1]:
            if key not in config:
                config[key] = {}
            config = config[key]
        
        config[keys[-1]] = value
        self.save_config()