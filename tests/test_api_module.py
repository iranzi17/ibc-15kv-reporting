import sys
import types

from fastapi.testclient import TestClient

import api


def test_load_credentials_falls_back_to_streamlit_secret_helper(monkeypatch):
    fake_credentials = object()
    fake_sheets = types.SimpleNamespace(
        get_service_account_credentials=lambda: fake_credentials
    )

    monkeypatch.delenv("GOOGLE_CREDENTIALS", raising=False)
    monkeypatch.delenv("GOOGLE_APPLICATION_CREDENTIALS", raising=False)
    monkeypatch.setitem(sys.modules, "sheets", fake_sheets)

    assert api._load_credentials() is fake_credentials


def test_submit_report_formats_row_before_append(monkeypatch):
    captured = {}

    def fake_append_row(row):
        captured["row"] = row

    monkeypatch.setattr(api, "append_row", fake_append_row)

    client = TestClient(api.app)
    response = client.post(
        "/reports",
        json={
            "date": "2025-08-06",
            "site_name": "Site A",
            "district": "Gasabo",
            "work": "Trench excavation",
            "human_resources": "5 technicians",
            "supply": "Cable drums",
            "work_executed": "Excavated 50 m",
            "comment_on_work": "No blockers",
            "another_work_executed": "Pole setting",
            "comment_on_hse": "PPE compliant",
            "consultant_recommandation": "Proceed",
            "non_compliant_work": "None",
            "reaction_and_wayforword": "Continue tomorrow",
            "challenges": "Rain",
        },
    )

    assert response.status_code == 201
    assert captured["row"] == [
        "06/08/2025",
        "Site A",
        "Gasabo",
        "Trench excavation",
        "5 technicians",
        "Cable drums",
        "Excavated 50 m",
        "No blockers",
        "Pole setting",
        "PPE compliant",
        "Proceed",
        "None",
        "Continue tomorrow",
        "Rain",
    ]


def test_schema_returns_report_headers():
    client = TestClient(api.app)
    response = client.get("/schema")

    assert response.status_code == 200
    assert response.json() == {"headers": api.REPORT_HEADERS}


def test_email_login_flow_and_auth_protected_sites(monkeypatch):
    sent = {}
    rows = [
        api.REPORT_HEADERS,
        [
            "06/08/2025",
            "Site A",
            "Gasabo",
            "Work A",
            "Crew A",
            "Supply A",
            "Executed A",
            "Comment A",
            "Another A",
            "HSE A",
            "Recommendation A",
            "Non compliant A",
            "Reaction A",
            "Challenges A",
        ],
    ]

    monkeypatch.setattr(api, "AUTH_REQUIRED", True)
    monkeypatch.setattr(api, "_email_login_available", lambda: True)
    monkeypatch.setattr(api, "fetch_rows", lambda: rows)
    api._PENDING_LOGIN_CODES.clear()
    api._ACTIVE_SESSIONS.clear()

    def fake_send_login_email(email, code):
        sent["email"] = email
        sent["code"] = code

    monkeypatch.setattr(api, "_send_login_email", fake_send_login_email)

    client = TestClient(api.app)

    config_response = client.get("/auth/config")
    assert config_response.status_code == 200
    assert config_response.json() == {
        "auth_required": True,
        "email_login_available": True,
    }

    unauthenticated_response = client.get("/sites")
    assert unauthenticated_response.status_code == 401

    request_response = client.post("/auth/request-code", json={"email": "user@example.com"})
    assert request_response.status_code == 200
    assert request_response.json() == {"status": "sent"}
    assert sent["email"] == "user@example.com"
    assert len(sent["code"]) == 6

    verify_response = client.post(
        "/auth/verify-code",
        json={"email": "user@example.com", "code": sent["code"]},
    )
    assert verify_response.status_code == 200
    payload = verify_response.json()
    assert payload["email"] == "user@example.com"
    assert payload["token"]

    authenticated_response = client.get(
        "/sites",
        headers={"Authorization": f"Bearer {payload['token']}"},
    )
    assert authenticated_response.status_code == 200
    assert authenticated_response.json() == {"sites": ["Site A"]}


def test_sites_returns_clear_error_when_google_credentials_are_missing(monkeypatch):
    monkeypatch.setattr(api, "AUTH_REQUIRED", False)
    monkeypatch.setattr(
        api,
        "_build_service",
        lambda: (_ for _ in ()).throw(RuntimeError("Google credentials not provided.")),
    )

    client = TestClient(api.app)
    response = client.get("/sites")

    assert response.status_code == 503
    assert response.json() == {"detail": "Google credentials not provided."}


def test_export_reports_filters_sheet_rows_and_returns_zip(monkeypatch):
    rows = [
        api.REPORT_HEADERS,
        [
            "06/08/2025",
            "Site A",
            "Gasabo",
            "Work A",
            "Crew A",
            "Supply A",
            "Executed A",
            "Comment A",
            "Another A",
            "HSE A",
            "Recommendation A",
            "Non compliant A",
            "Reaction A",
            "Challenges A",
        ],
        [
            "07/08/2025",
            "Site B",
            "Kicukiro",
            "Work B",
            "Crew B",
            "Supply B",
            "Executed B",
            "Comment B",
            "Another B",
            "HSE B",
            "Recommendation B",
            "Non compliant B",
            "Reaction B",
            "Challenges B",
        ],
    ]
    generated = {}

    def fake_generate_reports(filtered_rows, uploaded_images, discipline, **kwargs):
        generated["rows"] = filtered_rows
        generated["uploaded_images"] = uploaded_images
        generated["discipline"] = discipline
        generated["kwargs"] = kwargs
        return b"zip-bytes"

    monkeypatch.setattr(api, "fetch_rows", lambda: rows)
    monkeypatch.setattr(api, "generate_reports", fake_generate_reports)
    monkeypatch.setattr(api, "AUTH_REQUIRED", False)

    client = TestClient(api.app)
    response = client.post(
        "/reports/export",
        json={
            "discipline": "Electrical",
            "sites": ["Site A"],
            "dates": ["2025-08-06"],
        },
    )

    assert response.status_code == 200
    assert response.content == b"zip-bytes"
    assert response.headers["content-type"] == "application/zip"
    assert 'filename="Site A_Electrical_2025-08-06.zip"' in response.headers["content-disposition"]
    assert generated["rows"] == [rows[1]]
    assert generated["uploaded_images"] == {}
    assert generated["discipline"] == "Electrical"
    assert generated["kwargs"] == api.DEFAULT_EXPORT_SETTINGS
