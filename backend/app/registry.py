from __future__ import annotations

from pathlib import Path

import yaml


def _load(path: Path, key: str) -> list[dict]:
    if not path.exists():
        return []
    data = yaml.safe_load(path.read_text(encoding="utf-8")) or {}
    return list(data.get(key, []))


def load_models(registry_dir: Path) -> list[dict]:
    return _load(Path(registry_dir) / "models.yaml", "models")


def load_datasets(registry_dir: Path) -> list[dict]:
    return _load(Path(registry_dir) / "datasets.yaml", "datasets")
