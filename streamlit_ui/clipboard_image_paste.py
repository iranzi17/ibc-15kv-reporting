from __future__ import annotations

import base64
import binascii
from pathlib import Path

import streamlit as st
import streamlit.components.v1 as components

MAX_CLIPBOARD_IMAGE_BYTES = 20 * 1024 * 1024
_COMPONENT_DIR = Path(__file__).parent / "components" / "clipboard_image_paste"
_clipboard_image_paste = components.declare_component(
    "clipboard_image_paste",
    path=str(_COMPONENT_DIR),
)


def _has_streamlit_runtime() -> bool:
    """Return whether custom components can run in the active Streamlit runtime."""
    try:
        from streamlit.runtime.scriptrunner_utils.script_run_context import get_script_run_ctx

        return get_script_run_ctx() is not None
    except Exception:
        return False


def clipboard_seen_paste_ids() -> dict[str, list[str]]:
    return st.session_state.setdefault("_clipboard_image_paste_seen_ids", {})


def image_bytes_from_data_url(data_url: str, *, max_bytes: int = MAX_CLIPBOARD_IMAGE_BYTES) -> bytes:
    """Decode one clipboard image data URL into bytes."""
    value = str(data_url or "").strip()
    if not value.startswith("data:image/") or ";base64," not in value:
        raise ValueError("Clipboard image must be a base64 image data URL.")

    _, encoded = value.split(";base64,", 1)
    try:
        image_bytes = base64.b64decode(encoded, validate=True)
    except (binascii.Error, ValueError) as exc:
        raise ValueError("Clipboard image data is not valid base64.") from exc

    if not image_bytes:
        raise ValueError("Clipboard image is empty.")
    if len(image_bytes) > max_bytes:
        raise ValueError("Clipboard image is too large.")
    return image_bytes


def pasted_image_bytes_from_component_value(
    value: object,
    *,
    key: str,
) -> list[bytes]:
    """Return newly pasted image bytes from a clipboard component value."""
    if not isinstance(value, dict):
        return []

    paste_id = str(value.get("paste_id", "") or "").strip()
    if not paste_id:
        return []

    seen_by_key = clipboard_seen_paste_ids()
    seen = list(seen_by_key.setdefault(key, []))
    if paste_id in seen:
        return []

    images = value.get("images", [])
    if not isinstance(images, list):
        return []

    decoded_images: list[bytes] = []
    for item in images:
        if not isinstance(item, dict):
            continue
        mime_type = str(item.get("mime_type", "") or "").strip()
        if mime_type and not mime_type.startswith("image/"):
            continue
        try:
            decoded_images.append(image_bytes_from_data_url(str(item.get("data_url", "") or "")))
        except ValueError:
            continue

    seen.append(paste_id)
    seen_by_key[key] = seen[-100:]
    st.session_state["_clipboard_image_paste_seen_ids"] = seen_by_key
    return decoded_images


def render_clipboard_image_paste(
    *,
    label: str,
    key: str,
    max_images: int = 8,
) -> list[bytes]:
    """Render a paste target and return newly pasted image bytes."""
    if not _has_streamlit_runtime():
        return []

    try:
        value = _clipboard_image_paste(
            label=label,
            max_images=max(1, int(max_images)),
            default={},
            key=key,
        )
    except Exception:
        # The normal uploader remains the reliable fallback if components are unavailable.
        return []
    return pasted_image_bytes_from_component_value(value, key=key)
