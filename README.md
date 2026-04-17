# IBC 15kV Reporting

This Streamlit app helps generate daily electrical consultant reports.

## Providing Google Credentials

The app also needs access to your reporting Google Sheet. Create a Google
service account and download its credential JSON file. Add the full JSON
contents under the key `GOOGLE_CREDENTIALS` in the same
`.streamlit/secrets.toml` file:

```
# .streamlit/secrets.toml
GOOGLE_CREDENTIALS = """
{ "type": "service_account", "project_id": "...", ... }
"""
```

The credentials are parsed with `json.loads(st.secrets["GOOGLE_CREDENTIALS"])`
when the app starts. For backwards compatibility, an older
`gcp_service_account` key is also accepted if present.

To enable the in-app ChatGPT assistant, add your OpenAI key to the same file
or export it as an environment variable:

```
OPENAI_API_KEY = "your-openai-api-key"
OPENAI_MODEL = "gpt-4o-mini"
```

You can also paste the key into the ChatGPT settings panel inside the app for
the current browser session only.

## Configuration

Application settings can be supplied through environment variables or by
placing a `config.json` or `config.toml` file in the project root.  A custom
configuration file path may also be provided via the `APP_CONFIG` environment
variable.  Settings from environment variables take precedence over values from
the configuration file.

Supported options:

| Name | Description | Default |
| ---- | ----------- | ------- |
| `TEMPLATE_PATH` | Path to the Word report template used when generating documents. | `Site_Daily_report_Template_Date.docx` |
| `SHEET_ID` | ID of the Google Sheet that stores report data. | `1t6Bmm3YN7mAovNM3iT7oMGeXG3giDONSejJ9gUbUeCI` |
| `SHEET_NAME` | Worksheet within the Google Sheet from which to read data. | `Reports` |
| `CACHE_FILE` | File used to cache offline data before syncing. | `offline_cache.json` in the project directory |
| `DISCIPLINE_COL` | Column number for the "Discipline" field in the sheet. | `11` |

Example `config.toml`:

```toml
SHEET_ID = "your-google-sheet-id"
SHEET_NAME = "Reports"
```

## Google Sheet Setup

The app expects data in a Google Sheet named **Reports**. Columns **A** through
**N** should have the following headings starting in row&nbsp;1. Use the exact
names shown below so the app can map your data automatically:

1. **Date** - The report date in `dd.mm.YYYY`, `dd/mm/YYYY`, or `YYYY-mm-dd`
   format.
2. **Site_Name** - Name of the site.
3. **District** - District or location of the site.
4. **Work** - Summary of planned or ongoing work.
5. **Human_Resources** - Staffing information for the day.
6. **Supply** - Materials delivered or required.
7. **Work_Executed** - Activities executed during the day.
8. **Comment_on_work** - Additional notes about the work performed.
9. **Another_Work_Executed** - Any supplementary tasks completed.
10. **Comment_on_HSE** - Health, safety, and environment notes.
11. **Consultant_Recommandation** - Recommendations from the consultant.
12. **Non_Compliant_work** - Items that do not meet compliance expectations.
13. **Reaction_and_WayForword** - Follow-up actions or responses (the template
    previously labelled this column as "Reaction & Way Forward").
14. **challenges** - Issues encountered on site.

The application reads rows starting from **A2** and expects the above order. If
any columns are missing, empty strings will be substituted when generating
reports.

## Mobile/API entry point

A lightweight FastAPI service in `api.py` lets a mobile client submit daily reports to the same Google Sheet. Start it with:

```
uvicorn api:app --reload --port 8000
```

Or on Windows:

```
run_mobile_api.bat
```

Use the same service-account JSON as the Streamlit app (set `GOOGLE_CREDENTIALS` or `GOOGLE_APPLICATION_CREDENTIALS`).

Endpoints:
- `GET /health` to verify credentials
- `GET /auth/config` returns whether email login is enabled/required
- `POST /auth/request-code` sends a one-time email login code
- `POST /auth/verify-code` exchanges the code for a session token
- `GET /schema` returns the exact Google Sheet headers used by the app
- `GET /sites` returns the site list from the sheet
- `POST /reports` accepts the daily report payload
- `POST /reports/export` returns a ZIP of generated DOCX reports for the requested site/date filters

```
{
  "date": "2025-08-06",
  "site_name": "Kigali 15kV Switch",
  "district": "Kicukiro",
  "work": "Trench excavation",
  "human_resources": "5 technicians",
  "supply": "Cables, poles",
  "work_executed": "Excavated 120 m",
  "comment_on_work": "No blockers",
  "another_work_executed": "Cable pulling",
  "comment_on_hse": "PPE compliant",
  "consultant_recommandation": "Proceed with backfilling",
  "non_compliant_work": "None",
  "reaction_and_wayforword": "Continue tomorrow",
  "challenges": "Rain"
}
```

This keeps the service account on the server; the Android client only calls the API.

Export example:

```
{
  "discipline": "Electrical",
  "sites": ["Kigali 15kV Switch"],
  "dates": ["2025-08-06"]
}
```

The export endpoint reuses the same report generator as Streamlit, so the mobile app can download report ZIPs without opening the Streamlit UI.

Optional email login for the mobile app can be configured with:
- `MOBILE_AUTH_REQUIRED=true` to require login before `GET /sites`, `POST /reports`, and `POST /reports/export`
- `SMTP_HOST`, `SMTP_PORT`, `SMTP_USERNAME`, `SMTP_PASSWORD`, `SMTP_FROM_EMAIL`, `SMTP_USE_TLS`
- `MOBILE_LOGIN_CODE_TTL_MINUTES` and `MOBILE_SESSION_TTL_HOURS` to control code/session lifetime
- `MOBILE_ALLOWED_EMAILS` or `MOBILE_ALLOWED_EMAIL_DOMAINS` to restrict who can sign in

The Android app in `mobile/android-app/` now lets the user enter the API server URL inside the app, mirrors the 14 Google Sheet headers from `/schema`, and supports email-code login when the backend has it enabled.

## Free public access without a card

For zero-cost public access during early testing, use the Cloudflare Quick Tunnel flow in `DEPLOY_FREE.md`.

Launcher files:
- `run_mobile_public.bat`
- `run_mobile_public.ps1`

This keeps the Google credential on the computer running the API and gives the phone a temporary HTTPS URL. The URL changes each time the tunnel restarts, so this is suitable for testing and early internal use, not a final production deployment.
