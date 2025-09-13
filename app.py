# cleaned_app.py
import os
import re
import json
import tempfile
import zipfile
import base64
from pathlib import Path
from typing import Optional
from io import BytesIO

import pandas as pd
import streamlit as st
from google.oauth2 import service_account
from googleapiclient.discovery import build
from docxtpl import DocxTemplate, InlineImage
from docx.shared import Mm
from docx import Document
from openpyxl import load_workbook

# -----------------------------
# Globals
# -----------------------------
BASE_DIR = Path(__file__).parent.resolve()
TEMPLATE_PATH = "Site_Daily_report_Template_Date.docx"
SHEET_ID = "1t6Bmm3YN7mAovNM3iT7oMGeXG3giDONSejJ9gUbUeCI"
SHEET_NAME = "Reports"
CACHE_FILE = BASE_DIR / "offline_cache.json"

DISCIPLINE_COL = 11  # (kept from original)

# -----------------------------
# Utility functions
# -----------------------------
def set_background(image_path: str, overlay_opacity: float = 0.55):
    """
    Set a full-page background image with a subtle overlay for readability.
    overlay_opacity: 0.0 (no overlay) → 1.0 (solid)
    """
    overlay_opacity = max(0.0, min(1.0, overlay_opacity))
    path = Path(__file__).parent / image_path
    if not path.exists():
        return
    with open(path, "rb") as f:
        encoded = base64.b64encode(f.read()).decode()

    st.markdown(
        f"""
        <style>
        [data-testid="stAppViewContainer"] {{
            background-image:
                linear-gradient(rgba(255,255,255,{overlay_opacity}),
                                rgba(255,255,255,{overlay_opacity})),
                url("data:image/jpg;base64,{encoded}");
            background-size: cover;
            background-position: center center;
            background-attachment: fixed;
        }}
        [data-testid="stHeader"] {{
            background: rgba(0,0,0,0);
        }}
        .block-container {{
            background: rgba(255,255,255,0.85);
            border-radius: 14px;
            padding: 1.2rem 2rem;
            box-shadow: 0 4px 20px rgba(0,0,0,0.08);
            backdrop-filter: blur(2px);
        }}
        [data-testid="stSidebar"] > div:first-child {{
            background: rgba(255,255,255,0.75);
            border-radius: 12px;
            margin: 0.5rem;
            padding: 0.5rem;
            backdrop-filter: blur(2px);
        }}
        .stButton>button {{
            box-shadow: 0 2px 8px rgba(0,0,0,0.12);
        }}
        @media (max-width: 768px) {{
          .block-container {{ background: rgba(255,255,255,0.92); }}
        }}
        </style>
        """,
        unsafe_allow_html=True,
    )

def safe_filename(s: str, max_len: int = 150) -> str:
    """Remove illegal filename characters and tidy whitespace."""
    s = str(s)
    s = re.sub(r'[\\/:*?"<>|]+', "-", s)
    s = re.sub(r"\s+", " ", s).strip(" .-")
    return s[:max_len]

def normalize_date(d) -> str:
    """Normalize date like '06/08/2025' -> '2025-08-06' (safe for logs etc.)."""
    try:
        return pd.to_datetime(d, dayfirst=True, errors="raise").strftime("%Y-%m-%d")
    except Exception:
        return str(d).replace("/", "-").replace("\\", "-")

def format_date_title(d: str) -> str:
    """Return dd.MM.YYYY for filenames like 04.08.2025."""
    try:
        return pd.to_datetime(d, dayfirst=True, errors="raise").strftime("%d.%m.%Y")
    except Exception:
        return str(d).replace("/", ".").replace("-", ".")

# Proper resolve_asset with docstring correctly indented
def resolve_asset(name: Optional[str]) -> Optional[str]:
    """Find an asset (e.g., signature image) whether it's in ./ or ./signatures/,
    with or without extension. Tries .png/.jpg/.jpeg/.webp. Returns an absolute path or None."""
    if not name:
        return None

    p = (BASE_DIR / name).resolve()
    stem = p.with_suffix("").name

    # Where to look
    if p.parent != BASE_DIR:
        search_dirs = [p.parent]
    else:
        search_dirs = [BASE_DIR / "signatures", BASE_DIR]

    exts = ["", ".png", ".jpg", ".jpeg", ".webp"]
    for d in search_dirs:
        for ext in exts:
            candidate = (d / f"{stem}{ext}").resolve()
            if candidate.exists():
                return str(candidate)
    return None

# -----------------------------
# UI helpers
# -----------------------------
def render_workwatch_header(
    author: str = "IRANZI",
    brand: str = "WorkWatch",
    subtitle: str = "Site Intelligence",
    logo_path: Optional[str] = "ibc_logo.png",
    tagline: Optional[str] = "Field reports & weekly summaries",
):
    # embed logo if available
    logo_html = ""
    if logo_path:
        p = Path(__file__).parent / logo_path
        if p.exists():
            encoded = base64.b64encode(p.read_bytes()).decode()
            logo_html = f'<img class="ww-logo" src="data:image/png;base64,{encoded}" alt="logo"/>'

    # optional discipline suffix (from your sidebar radio)
    discipline = st.session_state.get("discipline_radio")
    suffix = f' <span class="ww-suffix">— {discipline}</span>' if discipline else ""

    st.markdown(
        f"""
        <style>
        .ww-wrap {{
          display:flex; align-items:center; gap:14px; margin: .25rem 0 1rem 0;
        }}
        .ww-logo {{
          height: 46px; width:auto; border-radius:8px; box-shadow:0 2px 8px rgba(0,0,0,.12);
        }}
        .ww-title {{
          font-size: clamp(28px, 4vw, 44px);
          line-height: 1.05;
          font-weight: 800;
          margin: 0;
        }}
        .ww-brand {{
          background: linear-gradient(90deg,#111,#5a5a5a 60%,#111);
          -webkit-background-clip: text;
          background-clip: text;
          color: transparent;
        }}
        .ww-sub {{ opacity:.85; font-weight:700; }}
        .ww-dot {{ opacity:.6; font-weight:600; padding:0 .2rem; }}
        .ww-author {{ font-weight:500; opacity:.8; }}
        .ww-suffix {{ font-weight:500; opacity:.65; }}
        .ww-tagline {{ margin-top:.25rem; opacity:.75; font-size:0.95rem; }}
        </style>

        <div class="ww-wrap">
          {logo_html}
          <div>
            <div class="ww-title">
              ⚡ <span class="ww-brand">{brand}</span> — <span class="ww-sub">{subtitle}</span>
              <span class="ww-dot">·</span><span class="ww-author">{author}</span>{suffix}
            </div>
            {f'<div class="ww-tagline">{tagline}</div>' if tagline else ''}
          </div>
        </div>
        """,
        unsafe_allow_html=True,
    )

# -----------------------------
# Signatories & config
# -----------------------------
SIGNATORIES = {
    "Civil": {
        "Consultant_Name": "IRANZI Prince Jean Claude",
        "Consultant_Title": "Civil Engineer",
        "Consultant_Signature": "iranzi_prince_jean_claude.jpg",  # full name with extension
        "Contractor_Name": "Issac HABIMANA",
        "Contractor_Title": "Electrical Engineer",
        "Contractor_Signature": "issac_habimana.jpg",  # full name
    },
    "Electrical": {
        "Consultant_Name": "Alexis IVUGIZA",
        "Consultant_Title": "Electrical Engineer",
        "Consultant_Signature": "alexis_ivugiza.jpg",
        "Contractor_Name": "Issac HABIMANA",
        "Contractor_Title": "Electrical Engineer",
        "Contractor_Signature": "issac_habimana.jpg",
    },
}


# -----------------------------
# Google sheets helpers
# -----------------------------
SCOPES = ["https://www.googleapis.com/auth/spreadsheets"]

def _build_service():
    service_account_info = json.loads(st.secrets["GOOGLE_CREDENTIALS"])
    creds = service_account.Credentials.from_service_account_info(
        service_account_info, scopes=SCOPES
    )
    return build("sheets", "v4", credentials=creds)

@st.cache_data(ttl=300)
def get_sheet_data() -> list[list[str]]:
    service = _build_service()
    sheet = service.spreadsheets()
    result = sheet.values().get(
        spreadsheetId=SHEET_ID,
        range=f"{SHEET_NAME}!A:K",
    ).execute()
    rows = result.get("values", [])
    padded_rows = [row + [""] * (11 - len(row)) for row in rows]
    return padded_rows

def append_rows_to_sheet(rows: list[list[str]]):
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

def load_offline_cache():
    if CACHE_FILE.exists():
        try:
            with open(CACHE_FILE, "r") as fh:
                return json.load(fh)
        except Exception:
            return None
    return None

def save_offline_cache(rows, uploads):
    data = {
        "rows": rows,
        "uploads": {
            f"{site}|{date}": [
                {
                    "name": f.name,
                    "data": base64.b64encode(f.getbuffer()).decode("utf-8"),
                }
                for f in (files or [])
            ]
            for (site, date), files in uploads.items()
        },
    }
    with open(CACHE_FILE, "w") as fh:
        json.dump(data, fh)

def get_unique_sites_and_dates(rows: list[list[str]]):
    sites = sorted({row[1].strip() for row in rows if len(row) > 1 and row[1].strip()})
    dates = sorted({row[0].strip() for row in rows if len(row) > 0 and row[0].strip()})
    return sites, dates

# -----------------------------
# Streamlit app UI
# -----------------------------
st.title("📑 Site Daily Report Generator (Pro)")

# role
role = st.session_state.setdefault("user_role", "Viewer")
if role == "Manager":
    st.sidebar.button("Admin Settings", icon="⚙️")

overlay = st.sidebar.slider("🖼️ Background overlay", 0.0, 1.0, 0.55, 0.05)
set_background("bg.jpg", overlay)

render_workwatch_header(
    author="IRANZI",
    brand="WorkWatch",
    subtitle="Site Intelligence",
    logo_path="ibc_logo.png",
    tagline="Field reports & weekly summaries",
)

# Controls that were mistakenly embedded in HTML in original file:
st.sidebar.subheader("Gallery Controls")
img_width_mm = st.sidebar.slider("Image width (mm)", min_value=30, max_value=100, value=70, step=5)
img_per_row = st.sidebar.selectbox("Images per row", options=[1,2,3,4], index=1)
add_border = st.sidebar.checkbox("Add border to images", value=False)
spacing_mm = st.sidebar.slider("Spacing between images (mm)", min_value=0, max_value=20, value=2, step=1)

# Get sheet data
cache = load_offline_cache()
if cache and cache.get("rows"):
    st.info("Cached offline data detected. Use the button below to sync back to the Google Sheet.")
    if st.button("Sync cached data to Google Sheet"):
        try:
            append_rows_to_sheet(cache.get("rows", []))
            CACHE_FILE.unlink()
            st.success("Cached data synced to Google Sheet.")
            cache = None
        except Exception as e:
            st.error(f"Sync failed: {e}")

try:
    rows = get_sheet_data()
except Exception as e:
    rows = []
    st.warning("Unable to fetch data from the Google Sheet.")

if not rows:
    st.warning("No data found in the Google Sheet.")
    st.stop()

sites, all_dates = get_unique_sites_and_dates(rows)

with st.sidebar:
    offline_enabled = st.checkbox("Enable offline cache", value=False)
    st.header("Select Discipline")
    discipline = st.radio(
        "Choose discipline:", ["Civil", "Electrical"], index=0, key="discipline_radio"
    )

    st.header("Select Sites")
    site_choices = ["All Sites"] + sites
    selected_sites = st.multiselect(
        "Choose sites:", site_choices, default=["All Sites"], key="sites_ms"
    )
    if "All Sites" in selected_sites or not selected_sites:
        selected_sites = sites

    st.header("Select Dates")
    site_dates = sorted({row[0].strip() for row in rows if row[1].strip() in selected_sites})
    date_choices = ["All Dates"] + site_dates
    selected_dates = st.multiselect(
        "Choose dates:", date_choices, default=["All Dates"], key="dates_ms"
    )
    if "All Dates" in selected_dates or not selected_dates:
        selected_dates = site_dates

# Filtered rows
filtered_rows = [
    row for row in rows
    if row[1].strip() in selected_sites and row[0].strip() in selected_dates
]

site_date_pairs = sorted({(row[1].strip(), row[0].strip()) for row in filtered_rows})

uploaded_image_mapping: dict[tuple[str, str], list] = {}

# Preview
st.subheader("Preview Reports to be Generated")
df_preview = pd.DataFrame(
    filtered_rows,
    columns=[
        "Date", "Site_Name", "District", "Work", "Human_Resources", "Supply",
        "Work_Executed", "Comment_on_work", "Another_Work_Executed",
        "Comment_on_HSE", "Consultant_Recommandation",
    ],
)
st.dataframe(df_preview, use_container_width=True, hide_index=True)

# Dashboard toggle
show_dashboard = st.checkbox("Show Dashboard")
if show_dashboard:
    dash_df = df_preview.copy()
    dash_df = dash_df[dash_df["Site_Name"].isin(selected_sites)]
    dash_df = dash_df[dash_df["Date"].isin(selected_dates)]
    if "Discipline" in dash_df.columns:
        dash_df = dash_df[dash_df["Discipline"] == discipline]

    st.subheader("Dashboard")
    st.dataframe(dash_df, use_container_width=True, hide_index=True)

    if "Work_Executed" in dash_df.columns:
        dash_df = dash_df.assign(
            Work_Executed=pd.to_numeric(dash_df["Work_Executed"], errors="coerce"),
            Date=pd.to_datetime(dash_df["Date"], errors="coerce"),
        ).dropna(subset=["Work_Executed", "Date"])
        if not dash_df.empty:
            st.line_chart(
                dash_df.sort_values("Date").set_index("Date")["Work_Executed"]
            )

# Image upload UI
st.subheader("Gallery Preview & Customization")
for site_name, date in site_date_pairs:
    site_name = site_name.strip()
    date = date.strip()
    image_files = uploaded_image_mapping.get((site_name, date), []) or []
    if image_files:
        st.markdown(f"**Gallery for {site_name} ({date})**")
        cols = st.columns(img_per_row)
        for idx, img_file in enumerate(image_files):
            with cols[idx % img_per_row]:
                st.image(img_file, width=200)
                if add_border:
                    st.markdown("<div style='border:1px solid #888; margin-bottom:5px;'></div>", unsafe_allow_html=True)

if site_date_pairs:
    for site_name, date in site_date_pairs:
        site_name = site_name.strip()
        date = date.strip()
        with st.expander(f"Upload Images for {site_name} ({date})"):
            imgs = st.file_uploader(
                f"Images for {site_name} ({date})",
                accept_multiple_files=True,
                key=f"uploader_{safe_filename(site_name)}_{safe_filename(date)}",
            )
            uploaded_image_mapping[(site_name, date)] = imgs
else:
    st.info("No site/date pairs in current filter. Adjust filters to upload images.")

# -----------------------------
# Generate reports
# -----------------------------
if st.button("🚀 Generate & Download All Reports"):
    with st.spinner("Generating reports..."):
        zip_buffer = tempfile.NamedTemporaryFile(delete=False, suffix=".zip")
        with zipfile.ZipFile(zip_buffer, "w") as zipf:
            for row in filtered_rows:
                (
                    date, site_name, district, work, human_resources, supply,
                    work_executed, comment_on_work, another_work_executed,
                    comment_on_hse, consultant_recommandation
                ) = (row + [""] * 11)[:11]

                date = date.strip()
                site_name = site_name.strip()

                tpl = DocxTemplate(TEMPLATE_PATH)

                # Images from uploader → put each photo in a subdocument paragraph with custom styling
                image_files = uploaded_image_mapping.get((site_name, date), []) or []
                images_subdoc = tpl.new_subdoc()
                row_cells = []

                # Build rows of images (simple implementation)
                for idx, img_file in enumerate(image_files):
                    # write temp file
                    with tempfile.NamedTemporaryFile(delete=False, suffix=".img") as tmp_img:
                        tmp_img.write(img_file.getbuffer())
                        tmp_img.flush()
                        row_cells.append(tmp_img.name)

                    if (idx + 1) % img_per_row == 0 or idx == len(image_files) - 1:
                        table = images_subdoc.add_table(rows=1, cols=img_per_row)
                        for col_idx in range(img_per_row):
                            cell = table.rows[0].cells[col_idx]
                            if col_idx < len(row_cells):
                                img_path = row_cells[col_idx]
                                run = cell.paragraphs[0].add_run()
                                run.add_picture(img_path, width=Mm(img_width_mm))
                                # optionally add border (simple approach)
                                if add_border:
                                    from docx.oxml import parse_xml
                                    borders_xml = """
                                    <w:tcBorders xmlns:w='http://schemas.openxmlformats.org/wordprocessingml/2006/main'>
                                        <w:top w:val='single' w:sz='4' w:space='0' w:color='888888'/>
                                        <w:left w:val='single' w:sz='4' w:space='0' w:color='888888'/>
                                        <w:bottom w:val='single' w:sz='4' w:space='0' w:color='888888'/>
                                        <w:right w:val='single' w:sz='4' w:space='0' w:color='888888'/>
                                    </w:tcBorders>
                                    """
                                    tcPr = cell._element.get_or_add_tcPr()
                                    tcPr.append(parse_xml(borders_xml))
                                try:
                                    os.remove(img_path)
                                except Exception:
                                    pass
                        row_cells = []

                # Signatures
                sign_info = SIGNATORIES.get(discipline, {})
                cons_sig_path = resolve_asset(sign_info.get("Consultant_Signature"))
                cont_sig_path = resolve_asset(sign_info.get("Contractor_Signature"))
                cons_sig_img = InlineImage(tpl, cons_sig_path, width=Mm(30)) if cons_sig_path else ""
                cont_sig_img = InlineImage(tpl, cont_sig_path, width=Mm(30)) if cont_sig_path else ""

                # Build context (you will need to adapt to your docx template variables)
                ctx = {
                    "Date": date,
                    "Site_Name": site_name,
                    "District": district,
                    "Work": work,
                    "Human_Resources": human_resources,
                    "Supply": supply,
                    "Work_Executed": work_executed,
                    "Comment_on_work": comment_on_work,
                    "Another_Work_Executed": another_work_executed,
                    "Comment_on_HSE": comment_on_hse,
                    "Consultant_Recommandation": consultant_recommandation,
                    "Consultant_Name": sign_info.get("Consultant_Name", ""),
                    "Consultant_Title": sign_info.get("Consultant_Title", ""),
                    "Contractor_Name": sign_info.get("Contractor_Name", ""),
                    "Contractor_Title": sign_info.get("Contractor_Title", ""),
                    "Consultant_Signature": cons_sig_img,
                    "Contractor_Signature": cont_sig_img,
                    "Gallery": images_subdoc,
                }

                tpl.render(ctx)

                # produce a filename and write into zip
                out_name = safe_filename(f"{site_name}_{format_date_title(date)}.docx")
                with tempfile.NamedTemporaryFile(delete=False, suffix=".docx") as tmp_docx:
                    tpl.save(tmp_docx.name)
                    zipf.write(tmp_docx.name, arcname=out_name)
                    os.remove(tmp_docx.name)

        zip_buffer.flush()
        zip_buffer.seek(0)
        st.download_button(
            "⬇️ Download ZIP",
            data=zip_buffer.read(),
            file_name="daily_reports.zip",
            mime="application/zip",
        )

st.info("**Tip:** If you don't upload images, reports will still be generated with all your data.")
st.caption("Made for efficient, multi-site daily reporting. Feedback & customizations welcome!")
