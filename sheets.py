import base64
import json
from pathlib import Path
from typing import Dict, List

import streamlit as st
from google.oauth2 import service_account
from googleapiclient.discovery import build

BASE_DIR = Path(__file__).parent.resolve()
SHEET_ID = "1t6Bmm3YN7mAovNM3iT7oMGeXG3giDONSejJ9gUbUeCI"
SHEET_NAME = "Reports"
CACHE_FILE = BASE_DIR / "offline_cache.json"
SCOPES = ["https://www.googleapis.com/auth/spreadsheets"]


def _build_service():
    service_account_info = json.loads(st.secrets["GOOGLE_CREDENTIALS"])
    creds = service_account.Credentials.from_service_account_info(
        service_account_info, scopes=SCOPES
    )
    return build("sheets", "v4", credentials=creds)


@st.cache_data(ttl=300)
def get_sheet_data() -> List[List[str]]:
    """Fetch rows from the configured Google Sheet."""
    service = _build_service()
    sheet = service.spreadsheets()
    result = sheet.values().get(
        spreadsheetId=SHEET_ID,
        range=f"{SHEET_NAME}!A:K",
    ).execute()
    rows = result.get("values", [])
    padded_rows = [row + [""] * (11 - len(row)) for row in rows]
    return padded_rows


def append_rows_to_sheet(rows: List[List[str]]):
    if not rows:
        return
    service = _build_service()
    body = {"values": rows}
    service.spreadsheets().values().append(
        spreadsheetId=SHEET_ID,
        range=SHEET_NAME,
        valueInputOption="USER_ENTERED",
        body=body,
    ).execute()


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
