# IBC 15kV Reporting

This Streamlit app helps generate daily and weekly electrical consultant reports. It can summarize multiple daily reports using a Hugging Face model.

## Hugging Face Token

The app requires a Hugging Face API token for generating weekly summaries. Store this token in your Streamlit secrets file as `HF_TOKEN`:

```
# .streamlit/secrets.toml
HF_TOKEN = "your_huggingface_token"
```

The application retrieves the token using `st.secrets.get("HF_TOKEN")`.

## Google Sheet Setup

The app expects data in a Google Sheet named **Reports**. Columns **A** through
**F** should have the following headings starting in row 1:

1. **Date** – The report date in `dd.mm.YYYY`, `dd/mm/YYYY`, or `YYYY-mm-dd`
   format.
2. **Site** – Name of the site.
3. **Civil Works** – Notes on civil activities.
4. **Electrical Work** – Notes on electrical tasks.
5. **Planning** – Planned activities or comments.
6. **Challenges** – Issues encountered on site.

The application reads rows starting from **A2** and expects the above order. If
any columns are missing, empty strings will be substituted.
