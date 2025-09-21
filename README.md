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
**F** should have the following headings starting in row&nbsp;1:

1. **Site Name** – Name of the site.
2. **Date** – The report date in `dd.mm.YYYY`, `dd/mm/YYYY`, or `YYYY-mm-dd`
   format.
3. **Civil Works** – Notes on civil activities.
4. **General recommendation** – Electrical or other recommendations for the
   site.
5. **Comments about the activities performed and challenges faced** – Detailed
   comments on daily progress.
6. **Challenges** – Issues encountered on site.

The application reads rows starting from **A2** and expects the above order. If
any columns are missing, empty strings will be substituted.
