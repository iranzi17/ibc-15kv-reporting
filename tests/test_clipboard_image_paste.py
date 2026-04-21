import base64
import types

import pytest

from streamlit_ui import clipboard_image_paste


def test_image_bytes_from_data_url_decodes_base64_image():
    data_url = "data:image/png;base64," + base64.b64encode(b"png-bytes").decode("ascii")

    assert clipboard_image_paste.image_bytes_from_data_url(data_url) == b"png-bytes"


def test_image_bytes_from_data_url_rejects_non_image_payload():
    data_url = "data:text/plain;base64," + base64.b64encode(b"text").decode("ascii")

    with pytest.raises(ValueError):
        clipboard_image_paste.image_bytes_from_data_url(data_url)


def test_pasted_image_bytes_from_component_value_consumes_each_paste_once(monkeypatch):
    st_stub = types.SimpleNamespace(session_state={})
    monkeypatch.setattr(clipboard_image_paste, "st", st_stub)
    data_url = "data:image/jpeg;base64," + base64.b64encode(b"image-bytes").decode("ascii")
    value = {
        "paste_id": "paste-1",
        "images": [
            {
                "mime_type": "image/jpeg",
                "data_url": data_url,
            }
        ],
    }

    first = clipboard_image_paste.pasted_image_bytes_from_component_value(value, key="site-a")
    second = clipboard_image_paste.pasted_image_bytes_from_component_value(value, key="site-a")

    assert first == [b"image-bytes"]
    assert second == []
