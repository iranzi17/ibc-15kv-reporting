# IBC 15kV Reporting

This Streamlit app helps generate daily and weekly electrical consultant reports. It can summarize multiple daily reports using a Hugging Face model.

## Hugging Face Token

The app requires a Hugging Face API token for generating weekly summaries. Store this token in your Streamlit secrets file as `HF_TOKEN`:

```
# .streamlit/secrets.toml
HF_TOKEN = "your_huggingface_token"
```

The application retrieves the token using `st.secrets.get("HF_TOKEN")`.
