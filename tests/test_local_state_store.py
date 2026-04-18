from services.local_state_store import (
    default_ai_memory_state,
    load_ai_memory_state,
    persist_ai_memory_state,
)


def test_persist_and_load_ai_memory_state_roundtrip(tmp_path):
    path = tmp_path / "ai_memory.json"
    payload = {
        "saved_guidance": [{"id": "1", "instruction": "Keep it concise."}],
        "maintenance_backlog": [{"id": "2", "title": "Item"}],
        "runtime_issues": [{"area": "converter", "message": "failed"}],
    }

    assert persist_ai_memory_state(path, payload)
    loaded = load_ai_memory_state(path)

    assert loaded == payload


def test_load_ai_memory_state_returns_default_for_missing_file(tmp_path):
    path = tmp_path / "missing.json"

    loaded = load_ai_memory_state(path)

    assert loaded == default_ai_memory_state()
