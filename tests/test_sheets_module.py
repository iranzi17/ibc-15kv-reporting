from pathlib import Path

import sheets


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
