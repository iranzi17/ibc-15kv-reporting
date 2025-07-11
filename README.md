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
when the app starts.

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
