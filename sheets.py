import base64
import json
from typing import Dict, List

import streamlit as st
from google.oauth2 import service_account
from googleapiclient.discovery import build
from googleapiclient.errors import HttpError

from config import CACHE_FILE, SHEET_ID, SHEET_NAME

SCOPES = ["https://www.googleapis.com/auth/spreadsheets"]


class GoogleSheetAccessError(RuntimeError):
    """Actionable Google Sheets access/configuration failure."""


def _load_service_account_info() -> Dict:
    """Load the service account JSON from Streamlit secrets."""

    if "GOOGLE_CREDENTIALS" in st.secrets:
        raw_credentials = st.secrets["GOOGLE_CREDENTIALS"]
        if isinstance(raw_credentials, str):
            return json.loads(raw_credentials)
        return raw_credentials
    if "gcp_service_account" in st.secrets:
        return st.secrets["gcp_service_account"]
    raise KeyError(
        "Google service account credentials not configured. Set "
        "st.secrets['GOOGLE_CREDENTIALS'] with the JSON payload."
    )


def get_service_account_credentials() -> service_account.Credentials:
    """Return Google service account credentials for the configured scopes."""

    service_account_info = _load_service_account_info()
    return service_account.Credentials.from_service_account_info(
        service_account_info, scopes=SCOPES
    )


def get_configured_service_account_email() -> str:
    """Return the configured service account email when available."""

    try:
        service_account_info = _load_service_account_info()
    except Exception:
        return ""
    return str(service_account_info.get("client_email", "")).strip()


def _spreadsheet_url() -> str:
    return f"https://docs.google.com/spreadsheets/d/{SHEET_ID}/edit"


def _http_error_status(exc: HttpError) -> int | None:
    status = getattr(getattr(exc, "resp", None), "status", None)
    try:
        return int(status)
    except (TypeError, ValueError):
        return None


def _raise_actionable_sheet_error(operation: str, exc: HttpError):
    status = _http_error_status(exc)
    if status not in {401, 403}:
        raise exc

    service_account_email = get_configured_service_account_email()
    share_target = (
        f"Share the spreadsheet with `{service_account_email}` as Editor."
        if service_account_email
        else "The service account email could not be read from Streamlit secrets."
    )
    raise GoogleSheetAccessError(
        "Google Sheets permission denied while "
        f"{operation}. {share_target} Configured spreadsheet: {_spreadsheet_url()} "
        f"Configured tab: `{SHEET_NAME}`. If the tab or range is protected, allow this "
        "service account to edit it. Original Google API status: "
        f"{status}."
    ) from exc


def _build_service():
    creds = get_service_account_credentials()
    return build("sheets", "v4", credentials=creds)


@st.cache_data(ttl=300)
def get_sheet_data() -> List[List[str]]:
    """Fetch rows from the configured Google Sheet."""
    service = _build_service()
    sheet = service.spreadsheets()
    try:
        result = sheet.values().get(
            spreadsheetId=SHEET_ID,
            range=f"{SHEET_NAME}!A:N",
        ).execute()
    except HttpError as exc:
        _raise_actionable_sheet_error("reading rows", exc)
    rows = result.get("values", [])
    expected_cols = 14
    padded_rows = [row + [""] * max(0, expected_cols - len(row)) for row in rows]
    return padded_rows


def append_rows_to_sheet(rows: List[List[str]]):
    if not rows:
        return
    service = _build_service()
    body = {"values": rows}
    try:
        service.spreadsheets().values().append(
            spreadsheetId=SHEET_ID,
            range=SHEET_NAME,
            valueInputOption="USER_ENTERED",
            body=body,
        ).execute()
    except HttpError as exc:
        _raise_actionable_sheet_error("appending rows", exc)


def load_offline_cache() -> Dict:
    if CACHE_FILE.exists():
        try:
            with open(CACHE_FILE, "r") as fh:
                return json.load(fh)
        except Exception:
            return None
    return None


def save_offline_cache(rows: List[List[str]], uploads: Dict):
    data = {
        "rows": rows,
        "uploads": {
            f"{site}|{date}": [
                {"name": f.name, "data": base64.b64encode(f.getbuffer()).decode("utf-8")}
                for f in (files or [])
            ]
            for (site, date), files in uploads.items()
        },
    }
    with open(CACHE_FILE, "w") as fh:
        json.dump(data, fh)


def get_unique_sites_and_dates(rows: List[List[str]]):
    sites = sorted({row[1].strip() for row in rows if len(row) > 1 and row[1].strip()})
    dates = sorted({row[0].strip() for row in rows if len(row) > 0 and row[0].strip()})
    return sites, dates
