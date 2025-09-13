from __future__ import annotations

import json
import os
from pathlib import Path
from typing import Any, Dict

try:
    import tomllib  # Python 3.11+
except ModuleNotFoundError:  # pragma: no cover - fallback for older versions
    import tomli as tomllib  # type: ignore

BASE_DIR = Path(__file__).parent.resolve()


def _load_file(path: Path) -> Dict[str, Any]:
    """Load a JSON or TOML configuration file."""
    if path.suffix.lower() == ".json":
        with open(path, "r", encoding="utf-8") as fh:
            return json.load(fh)
    if path.suffix.lower() in {".toml", ".tml"}:
        with open(path, "rb") as fh:
            return tomllib.load(fh)
    return {}


def _load_config() -> Dict[str, Any]:
    """Search for a configuration file and return its contents.

    Lookup order:
      1. Path from the ``APP_CONFIG`` environment variable.
      2. ``config.json`` in the project root.
      3. ``config.toml`` in the project root.
    """
    candidates = []
    env_path = os.environ.get("APP_CONFIG")
    if env_path:
        candidates.append(Path(env_path))
    candidates.append(BASE_DIR / "config.json")
    candidates.append(BASE_DIR / "config.toml")

    for path in candidates:
        if path.is_file():
            try:
                return _load_file(path)
            except Exception:
                return {}
    return {}


_CONFIG = _load_config()


def _get(name: str, default: Any) -> Any:
    """Return a configuration value.

    Environment variables override values from configuration files."""
    return os.environ.get(name, _CONFIG.get(name, default))


TEMPLATE_PATH = _get("TEMPLATE_PATH", "Site_Daily_report_Template_Date.docx")
SHEET_ID = _get("SHEET_ID", "1t6Bmm3YN7mAovNM3iT7oMGeXG3giDONSejJ9gUbUeCI")
SHEET_NAME = _get("SHEET_NAME", "Reports")
CACHE_FILE = Path(_get("CACHE_FILE", BASE_DIR / "offline_cache.json"))
DISCIPLINE_COL = int(_get("DISCIPLINE_COL", 11))

__all__ = [
    "BASE_DIR",
    "TEMPLATE_PATH",
    "SHEET_ID",
    "SHEET_NAME",
    "CACHE_FILE",
    "DISCIPLINE_COL",
]
