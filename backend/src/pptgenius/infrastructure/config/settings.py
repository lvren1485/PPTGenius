import os
from pathlib import Path

import yaml

from .models import Settings

# 优先用环境变量，否则从 cwd 查找（uv run 启动时 cwd = backend/）
_project_root = Path(os.environ.get("PPTGENIUS_HOME", Path.cwd()))
DEFAULT_CONFIG = _project_root / "config.yaml"
LOCAL_CONFIG = _project_root / "config.local.yaml"
RESOURCES_DIR = _project_root / "src" / "resources"


def _load_yaml(path: Path) -> dict:
    with open(path, encoding="utf-8") as f:
        return yaml.safe_load(f) or {}


def _deep_merge(base: dict, override: dict) -> dict:
    for key, value in override.items():
        if isinstance(value, dict) and isinstance(base.get(key), dict):
            base[key] = _deep_merge(base[key], value)
        else:
            base[key] = value
    return base


_settings: Settings | None = None


def get_settings() -> Settings:
    global _settings
    if _settings is not None:
        return _settings

    data = _load_yaml(DEFAULT_CONFIG)
    if LOCAL_CONFIG.exists():
        data = _deep_merge(data, _load_yaml(LOCAL_CONFIG))

    _settings = Settings(**data)
    return _settings
