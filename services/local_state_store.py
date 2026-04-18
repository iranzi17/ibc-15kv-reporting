from __future__ import annotations

import json
from pathlib import Path


def load_json_store(path: Path, default: dict[str, object]) -> dict[str, object]:
    """Load a small JSON store with graceful fallback."""
    try:
        if path.exists():
            with open(path, "r", encoding="utf-8") as handle:
                payload = json.load(handle)
            if isinstance(payload, dict):
                return payload
    except Exception:
        pass
    return default.copy()


def save_json_store(path: Path, payload: dict[str, object]) -> bool:
    """Persist a small JSON store."""
    try:
        path.parent.mkdir(parents=True, exist_ok=True)
        with open(path, "w", encoding="utf-8") as handle:
            json.dump(payload, handle, ensure_ascii=True, indent=2)
    except Exception:
        return False
    return True


def default_ai_memory_state() -> dict[str, object]:
    """Return the default persisted AI-memory structure."""
    return {
        "saved_guidance": [],
        "maintenance_backlog": [],
        "runtime_issues": [],
    }


def load_ai_memory_state(path: Path) -> dict[str, object]:
    """Load AI memory state from local persistent storage."""
    return load_json_store(path, default_ai_memory_state())


def persist_ai_memory_state(path: Path, payload: dict[str, object]) -> bool:
    """Persist AI memory state to local persistent storage."""
    return save_json_store(path, payload)
