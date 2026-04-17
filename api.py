"""
Small FastAPI service that exposes the same Google Sheet used by the Streamlit app.
This lets a mobile client submit daily reports without embedding the service account.

Run locally:
    uvicorn api:app --reload --port 8000

Env vars:
    GOOGLE_CREDENTIALS   - JSON string for the service account (preferred)
    GOOGLE_APPLICATION_CREDENTIALS - path to a service account JSON file
    GOOGLE_SHEET_ID      - override the default sheet ID
    GOOGLE_SHEET_NAME    - override the default sheet name (default: Reports)
"""
import json
import os
import re
import secrets
import smtplib
from datetime import date as date_type, datetime, timedelta, timezone
from email.message import EmailMessage
from functools import lru_cache
from pathlib import Path
from typing import Optional

from fastapi import FastAPI, HTTPException, Request
from fastapi.responses import Response
from google.oauth2 import service_account
from googleapiclient.discovery import build
from pydantic import BaseModel, Field
from report import generate_reports, safe_filename
from report_structuring import REPORT_HEADERS


# Keep defaults aligned with the Streamlit app
SHEET_ID = os.environ.get(
    "GOOGLE_SHEET_ID", "1t6Bmm3YN7mAovNM3iT7oMGeXG3giDONSejJ9gUbUeCI"
)
SHEET_NAME = os.environ.get("GOOGLE_SHEET_NAME", "Reports")
SCOPES = ["https://www.googleapis.com/auth/spreadsheets"]
NUM_COLS = len(REPORT_HEADERS)
SHEET_RANGE = f"{SHEET_NAME}!A:N"
DEFAULT_EXPORT_SETTINGS = {
    "img_width_mm": 185,
    "img_height_mm": 148,
    "spacing_mm": 5,
    "img_per_row": 2,
    "add_border": False,
}
EMAIL_RE = re.compile(r"^[^@\s]+@[^@\s]+\.[^@\s]+$")
AUTH_REQUIRED = os.environ.get("MOBILE_AUTH_REQUIRED", "").strip().lower() in {
    "1",
    "true",
    "yes",
    "on",
}
LOGIN_CODE_TTL_MINUTES = int(os.environ.get("MOBILE_LOGIN_CODE_TTL_MINUTES", "10"))
SESSION_TTL_HOURS = int(os.environ.get("MOBILE_SESSION_TTL_HOURS", "12"))
SMTP_HOST = os.environ.get("SMTP_HOST", "").strip()
SMTP_PORT = int(os.environ.get("SMTP_PORT", "587"))
SMTP_USERNAME = os.environ.get("SMTP_USERNAME", "").strip()
SMTP_PASSWORD = os.environ.get("SMTP_PASSWORD", "")
SMTP_FROM_EMAIL = os.environ.get("SMTP_FROM_EMAIL", SMTP_USERNAME).strip()
SMTP_USE_TLS = os.environ.get("SMTP_USE_TLS", "true").strip().lower() not in {
    "0",
    "false",
    "no",
    "off",
}
ALLOWED_USER_EMAILS = {
    email.strip().lower()
    for email in os.environ.get("MOBILE_ALLOWED_EMAILS", "").split(",")
    if email.strip()
}
ALLOWED_EMAIL_DOMAINS = {
    domain.strip().lower().lstrip("@")
    for domain in os.environ.get("MOBILE_ALLOWED_EMAIL_DOMAINS", "").split(",")
    if domain.strip()
}
_PENDING_LOGIN_CODES: dict[str, dict[str, object]] = {}
_ACTIVE_SESSIONS: dict[str, dict[str, object]] = {}


def _load_credentials():
    """
    Load service-account credentials either from a JSON string env var or a file path.
    """
    creds_str = os.environ.get("GOOGLE_CREDENTIALS")
    if creds_str:
        try:
            data = json.loads(creds_str)
            return service_account.Credentials.from_service_account_info(data, scopes=SCOPES)
        except Exception as exc:
            raise RuntimeError(f"Failed to parse GOOGLE_CREDENTIALS: {exc}") from exc

    cred_path = os.environ.get("GOOGLE_APPLICATION_CREDENTIALS")
    if cred_path and Path(cred_path).expanduser().exists():
        try:
            with open(Path(cred_path).expanduser(), "r") as fh:
                data = json.load(fh)
            return service_account.Credentials.from_service_account_info(data, scopes=SCOPES)
        except Exception as exc:
            raise RuntimeError(f"Failed to read GOOGLE_APPLICATION_CREDENTIALS: {exc}") from exc

    try:
        from sheets import get_service_account_credentials

        return get_service_account_credentials()
    except Exception:
        pass

    raise RuntimeError(
        "Google credentials not provided. Set GOOGLE_CREDENTIALS, "
        "GOOGLE_APPLICATION_CREDENTIALS, or the same Streamlit secrets used by the app."
    )


@lru_cache(maxsize=1)
def _build_service():
    creds = _load_credentials()
    return build("sheets", "v4", credentials=creds)


def _get_sheet_service():
    try:
        return _build_service()
    except RuntimeError as exc:
        raise HTTPException(status_code=503, detail=str(exc)) from exc
    except HTTPException:
        raise
    except Exception as exc:
        raise HTTPException(
            status_code=502,
            detail=f"Failed to initialize Google Sheets service: {exc}",
        ) from exc


def _now_utc() -> datetime:
    return datetime.now(timezone.utc)


def _email_login_available() -> bool:
    return bool(SMTP_HOST and SMTP_FROM_EMAIL)


def _normalise_email(value: str) -> str:
    email = str(value or "").strip().lower()
    if not EMAIL_RE.match(email):
        raise HTTPException(status_code=422, detail="Enter a valid email address.")
    return email


def _is_allowed_email(email: str) -> bool:
    if not ALLOWED_USER_EMAILS and not ALLOWED_EMAIL_DOMAINS:
        return True
    if email in ALLOWED_USER_EMAILS:
        return True
    if "@" not in email:
        return False
    domain = email.rsplit("@", 1)[1]
    return domain in ALLOWED_EMAIL_DOMAINS


def _prune_auth_state() -> None:
    now = _now_utc()

    expired_codes = [
        email for email, data in _PENDING_LOGIN_CODES.items() if data.get("expires_at") <= now
    ]
    for email in expired_codes:
        _PENDING_LOGIN_CODES.pop(email, None)

    expired_sessions = [
        token for token, data in _ACTIVE_SESSIONS.items() if data.get("expires_at") <= now
    ]
    for token in expired_sessions:
        _ACTIVE_SESSIONS.pop(token, None)


def _send_login_email(recipient_email: str, code: str) -> None:
    if not _email_login_available():
        raise RuntimeError("SMTP email login is not configured on the server.")

    message = EmailMessage()
    message["Subject"] = "IBC Reporting login code"
    message["From"] = SMTP_FROM_EMAIL
    message["To"] = recipient_email
    message.set_content(
        "\n".join(
            [
                "Your IBC Reporting login code is:",
                code,
                "",
                f"This code expires in {LOGIN_CODE_TTL_MINUTES} minutes.",
            ]
        )
    )

    with smtplib.SMTP(SMTP_HOST, SMTP_PORT, timeout=30) as server:
        if SMTP_USE_TLS:
            server.starttls()
        if SMTP_USERNAME and SMTP_PASSWORD:
            server.login(SMTP_USERNAME, SMTP_PASSWORD)
        server.send_message(message)


def _require_authenticated_email(request: Request) -> str:
    if not AUTH_REQUIRED:
        return ""

    _prune_auth_state()
    auth_header = request.headers.get("Authorization", "")
    prefix = "Bearer "
    if not auth_header.startswith(prefix):
        raise HTTPException(status_code=401, detail="Email login required.")

    token = auth_header[len(prefix) :].strip()
    if not token:
        raise HTTPException(status_code=401, detail="Email login required.")

    session = _ACTIVE_SESSIONS.get(token)
    if not session:
        raise HTTPException(status_code=401, detail="Session expired. Sign in again.")

    email = str(session.get("email", "")).strip().lower()
    if not email:
        raise HTTPException(status_code=401, detail="Session expired. Sign in again.")
    return email


def _pad_row(row: list[str]) -> list[str]:
    """Pad rows to the expected column count to avoid index errors."""
    if len(row) < NUM_COLS:
        return row + [""] * (NUM_COLS - len(row))
    return row[:NUM_COLS]


def _format_date_for_sheet(d: date_type) -> str:
    """Match the dd/mm/YYYY format used by the Streamlit app."""
    return d.strftime("%d/%m/%Y")


def _normalize_date_value(value: str) -> str:
    """Normalise date strings so sheet rows and API filters compare reliably."""
    raw = str(value or "").strip()
    if not raw:
        return ""

    for fmt in (
        "%Y-%m-%d",
        "%d/%m/%Y",
        "%d.%m.%Y",
        "%d-%m-%Y",
        "%Y/%m/%d",
        "%Y.%m.%d",
    ):
        try:
            return datetime.strptime(raw, fmt).date().isoformat()
        except ValueError:
            continue

    return raw


def _data_rows(rows: list[list[str]]) -> list[list[str]]:
    """Skip the header row when it is present in the sheet."""
    if rows and rows[0] and rows[0][0].strip().lower() == "date":
        return rows[1:]
    return rows


def _filter_rows(rows: list[list[str]], sites: list[str], dates: list[str]) -> list[list[str]]:
    """Apply site/date filters using the same sheet row layout as Streamlit."""
    site_filter = {site.strip() for site in sites if site and site.strip()}
    date_filter = {_normalize_date_value(value) for value in dates if value and value.strip()}

    filtered: list[list[str]] = []
    for row in _data_rows(rows):
        padded = _pad_row(row)
        row_date = padded[0].strip()
        site_name = padded[1].strip()

        if site_filter and site_name not in site_filter:
            continue
        if date_filter and _normalize_date_value(row_date) not in date_filter:
            continue
        filtered.append(padded)

    return filtered


def _build_export_filename(filtered_rows: list[list[str]], discipline: str) -> str:
    """Create a stable ZIP filename for the exported reports."""
    if len(filtered_rows) == 1:
        site_name = filtered_rows[0][1].strip() or "report"
        row_date = _normalize_date_value(filtered_rows[0][0]) or date_type.today().isoformat()
        base_name = f"{site_name}_{discipline}_{row_date}"
    else:
        base_name = f"{discipline}_reports_{date_type.today().isoformat()}"
    return f"{safe_filename(base_name)}.zip"


def append_row(report_row: list[str]):
    service = _get_sheet_service()
    body = {"values": [report_row]}
    try:
        service.spreadsheets().values().append(
            spreadsheetId=SHEET_ID,
            range=SHEET_NAME,
            valueInputOption="USER_ENTERED",
            body=body,
        ).execute()
    except Exception as exc:
        raise HTTPException(status_code=502, detail=f"Failed to append row: {exc}") from exc


def fetch_rows() -> list[list[str]]:
    service = _get_sheet_service()
    try:
        result = (
            service.spreadsheets()
            .values()
            .get(spreadsheetId=SHEET_ID, range=SHEET_RANGE)
            .execute()
        )
    except Exception as exc:
        raise HTTPException(status_code=502, detail=f"Failed to read sheet: {exc}") from exc

    rows = result.get("values", [])
    return [_pad_row(r) for r in rows]


class DailyReport(BaseModel):
    date: date_type = Field(..., description="Report date (ISO yyyy-mm-dd is fine)")
    site_name: str = Field(..., min_length=1, max_length=200)
    district: Optional[str] = None
    work: Optional[str] = Field(None, description="Planned work")
    human_resources: Optional[str] = Field(None, description="Team/crew notes")
    supply: Optional[str] = None
    work_executed: Optional[str] = Field(None, description="Main executed work")
    comment_on_work: Optional[str] = None
    another_work_executed: Optional[str] = None
    comment_on_hse: Optional[str] = Field(None, description="HSE comments")
    consultant_recommandation: Optional[str] = None
    non_compliant_work: Optional[str] = None
    reaction_and_wayforword: Optional[str] = None
    challenges: Optional[str] = None

    def to_row(self) -> list[str]:
        """Convert to the exact column order expected by the sheet/app."""
        return [
            _format_date_for_sheet(self.date),
            self.site_name.strip(),
            (self.district or "").strip(),
            (self.work or "").strip(),
            (self.human_resources or "").strip(),
            (self.supply or "").strip(),
            (self.work_executed or "").strip(),
            (self.comment_on_work or "").strip(),
            (self.another_work_executed or "").strip(),
            (self.comment_on_hse or "").strip(),
            (self.consultant_recommandation or "").strip(),
            (self.non_compliant_work or "").strip(),
            (self.reaction_and_wayforword or "").strip(),
            (self.challenges or "").strip(),
        ]


class ReportExportRequest(BaseModel):
    discipline: str = Field("Electrical", description="Either Electrical or Civil")
    sites: list[str] = Field(default_factory=list, description="Exact site names to include")
    dates: list[str] = Field(
        default_factory=list,
        description="Dates to include. ISO yyyy-mm-dd is recommended.",
    )

    def normalized_discipline(self) -> str:
        value = self.discipline.strip().title()
        if value not in {"Civil", "Electrical"}:
            raise HTTPException(
                status_code=422,
                detail="discipline must be either 'Civil' or 'Electrical'.",
            )
        return value


class EmailLoginRequest(BaseModel):
    email: str = Field(..., min_length=3, max_length=320)


class EmailCodeVerificationRequest(BaseModel):
    email: str = Field(..., min_length=3, max_length=320)
    code: str = Field(..., min_length=6, max_length=6)


app = FastAPI(title="IBC 15kV Reporting API", version="0.1.0")


@app.get("/health")
def health():
    try:
        _build_service()
    except Exception as exc:
        return {"status": "error", "detail": str(exc)}
    return {
        "status": "ok",
        "auth_required": AUTH_REQUIRED,
        "email_login_available": _email_login_available(),
    }


@app.get("/auth/config")
def auth_config():
    return {
        "auth_required": AUTH_REQUIRED,
        "email_login_available": _email_login_available(),
    }


@app.post("/auth/request-code")
def request_login_code(payload: EmailLoginRequest):
    if not _email_login_available():
        raise HTTPException(status_code=503, detail="Email login is not configured on the server.")

    email = _normalise_email(payload.email)
    if not _is_allowed_email(email):
        raise HTTPException(status_code=403, detail="This email is not allowed to sign in.")

    code = f"{secrets.randbelow(1_000_000):06d}"
    _PENDING_LOGIN_CODES[email] = {
        "code": code,
        "expires_at": _now_utc() + timedelta(minutes=LOGIN_CODE_TTL_MINUTES),
    }

    try:
        _send_login_email(email, code)
    except Exception as exc:
        _PENDING_LOGIN_CODES.pop(email, None)
        raise HTTPException(status_code=502, detail=f"Failed to send login email: {exc}") from exc

    return {"status": "sent"}


@app.post("/auth/verify-code")
def verify_login_code(payload: EmailCodeVerificationRequest):
    _prune_auth_state()
    email = _normalise_email(payload.email)
    pending = _PENDING_LOGIN_CODES.get(email)
    if not pending:
        raise HTTPException(status_code=401, detail="No active login code found for this email.")

    expected_code = str(pending.get("code", "")).strip()
    if expected_code != payload.code.strip():
        raise HTTPException(status_code=401, detail="Invalid login code.")

    token = secrets.token_urlsafe(32)
    _ACTIVE_SESSIONS[token] = {
        "email": email,
        "expires_at": _now_utc() + timedelta(hours=SESSION_TTL_HOURS),
    }
    _PENDING_LOGIN_CODES.pop(email, None)
    return {"token": token, "email": email}


@app.get("/schema")
def schema():
    return {"headers": REPORT_HEADERS}


@app.get("/sites")
def list_sites(request: Request):
    _require_authenticated_email(request)
    rows = fetch_rows()
    data_rows = _data_rows(rows)
    sites = sorted({r[1].strip() for r in data_rows if len(r) > 1 and r[1].strip()})
    return {"sites": sites}


@app.post("/reports", status_code=201)
def submit_report(report: DailyReport, request: Request):
    _require_authenticated_email(request)
    append_row(report.to_row())
    return {"status": "stored"}


@app.post("/reports/export")
def export_reports(payload: ReportExportRequest, request: Request):
    _require_authenticated_email(request)
    discipline = payload.normalized_discipline()
    filtered_rows = _filter_rows(fetch_rows(), payload.sites, payload.dates)

    if not filtered_rows:
        raise HTTPException(status_code=404, detail="No rows matched the requested site/date filters.")

    try:
        zip_bytes = generate_reports(
            filtered_rows,
            {},
            discipline,
            **DEFAULT_EXPORT_SETTINGS,
        )
    except Exception as exc:
        raise HTTPException(status_code=502, detail=f"Failed to generate reports: {exc}") from exc

    if not zip_bytes:
        raise HTTPException(status_code=502, detail="Report generation returned an empty ZIP file.")

    filename = _build_export_filename(filtered_rows, discipline)
    return Response(
        content=zip_bytes,
        media_type="application/zip",
        headers={"Content-Disposition": f'attachment; filename="{filename}"'},
    )
