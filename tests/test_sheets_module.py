from pathlib import Path

import pytest
from googleapiclient.errors import HttpError

import sheets


class _FakeHttpResponse(dict):
    def __init__(self, status: int):
        super().__init__()
        self.status = status
        self.reason = "Forbidden"


def _http_error(status: int) -> HttpError:
    return HttpError(
        _FakeHttpResponse(status),
        b'{"error": {"message": "The caller does not have permission"}}',
    )


def test_get_unique_sites_and_dates():
    rows = [
        ["2024-01-01", "Site A"],
        ["2024-01-02", "Site B"],
        ["2024-01-01", "Site A"],
    ]
    sites, dates = sheets.get_unique_sites_and_dates(rows)
    assert sites == ["Site A", "Site B"]
    assert dates == ["2024-01-01", "2024-01-02"]


def test_save_and_load_offline_cache(tmp_path, monkeypatch):
    monkeypatch.setattr(sheets, "CACHE_FILE", tmp_path / "cache.json")
    rows = [["2024-01-01", "Site A"]]
    uploads = {("Site A", "2024-01-01"): []}
    sheets.save_offline_cache(rows, uploads)
    data = sheets.load_offline_cache()
    assert data["rows"] == rows
    assert data["uploads"] == {"Site A|2024-01-01": []}


def test_permission_error_includes_service_account_and_sheet_context(monkeypatch):
    monkeypatch.setattr(
        sheets,
        "_load_service_account_info",
        lambda: {"client_email": "reports-writer@example.iam.gserviceaccount.com"},
    )
    monkeypatch.setattr(sheets, "SHEET_ID", "sheet-123")
    monkeypatch.setattr(sheets, "SHEET_NAME", "Reports")

    with pytest.raises(sheets.GoogleSheetAccessError) as exc_info:
        sheets._raise_actionable_sheet_error("appending rows", _http_error(403))

    message = str(exc_info.value)
    assert "reports-writer@example.iam.gserviceaccount.com" in message
    assert "as Editor" in message
    assert "sheet-123" in message
    assert "`Reports`" in message
    assert "Original Google API status: 403" in message


def test_non_permission_google_api_error_is_not_rewritten():
    original = _http_error(500)

    with pytest.raises(HttpError) as exc_info:
        sheets._raise_actionable_sheet_error("reading rows", original)

    assert exc_info.value is original
