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

# ----------------------------- CONFIG -----------------------------
BASE_DIR = Path(__file__).parent.resolve()
TEMPLATE_PATH = BASE_DIR / "Site_Daily_report_Template_Date.docx"

SIGNATORIES = {
    "Civil": {
        "Consultant_Name": "IRANZI Prince Jean Claude",
        "Consultant_Title": "Civil Engineer",
        "Consultant_Signature": "iranzi_prince_jean_claude",
        "Contractor_Name": "Issac HABIMANA",
        "Contractor_Title": "Electrical Engineer",
        "Contractor_Signature": "issac_habimana",
    },
    "Electrical": {
        "Consultant_Name": "Alexis IVUGIZA",
        "Consultant_Title": "Electrical Engineer",
        "Consultant_Signature": "alexis_ivugiza",
        "Contractor_Name": "Issac HABIMANA",
        "Contractor_Title": "Electrical Engineer",
        "Contractor_Signature": "issac_habimana",
    },
}

SCOPES = ["https://www.googleapis.com/auth/spreadsheets"]
SHEET_ID = "1t6Bmm3YN7mAovNM3iT7oMGeXG3giDONSejJ9gUbUeCI"
SHEET_NAME = "Reports"
CACHE_FILE = BASE_DIR / "offline_cache.json"

# ----------------------------- HELPERS -----------------------------
def resolve_asset(name: Optional[str]) -> Optional[str]:
    if not name:
        return None
    p = (BASE_DIR / name).resolve()
    stem = p.with_suffix("").name
    search_dirs = [BASE_DIR / "signatures", BASE_DIR]
    exts = ["", ".png", ".jpg", ".jpeg", ".webp"]
    for d in search_dirs:
        for ext in exts:
            candidate = (d / f"{stem}{ext}").resolve()
            if candidate.exists():
                return str(candidate)
    return None

def safe_filename(s: str, max_len: int = 150) -> str:
    s = str(s)
    s = re.sub(r'[\\/:*?"<>|]+', "-", s)
    s = re.sub(r"\s+", " ", s).strip(" .-")
    return s[:max_len]

def format_date_title(d: str) -> str:
    try:
        return pd.to_datetime(d, dayfirst=True).strftime("%d.%m.%Y")
    except Exception:
        return str(d).replace("/", ".").replace("-", ".")

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
    result = sheet.values().get(spreadsheetId=SHEET_ID, range=f"{SHEET_NAME}!A:K").execute()
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
                {"name": f.name, "data": base64.b64encode(f.getbuffer()).decode("utf-8")}
                for f in (files or [])
            ]
            for (site, date), files in uploads.items()
        },
    }
    with open(CACHE_FILE, "w") as fh:
        json.dump(data, fh)

def build_gallery_subdoc(tpl: DocxTemplate, image_files: list, img_width_mm: int = 70,
                         img_per_row: int = 2, add_border: bool = False, spacing_mm: int = 2) -> any:
    """Return a docx subdocument with images arranged in table per row."""
    subdoc = tpl.new_subdoc()
    row_cells = []
    for idx, img_file in enumerate(image_files):
        with tempfile.NamedTemporaryFile(delete=False, suffix=".img") as tmp_img:
            tmp_img.write(img_file.getbuffer())
            tmp_img.flush()
            row_cells.append(tmp_img.name)

        if (idx + 1) % img_per_row == 0 or idx == len(image_files) - 1:
            table = subdoc.add_table(rows=1, cols=len(row_cells))
            for col_idx, img_path in enumerate(row_cells):
                cell = table.rows[0].cells[col_idx]
                run = cell.paragraphs[0].add_run()
                run.add_picture(img_path, width=Mm(img_width_mm))
                if add_border:
                    from docx.oxml import parse_xml
                    tcPr = cell._element.get_or_add_tcPr()
                    borders_xml = """
                    <w:tcBorders xmlns:w='http://schemas.openxmlformats.org/wordprocessingml/2006/main'>
                        <w:top w:val='single' w:sz='4' w:space='0' w:color='888888'/>
                        <w:left w:val='single' w:sz='4' w:space='0' w:color='888888'/>
                        <w:bottom w:val='single' w:sz='4' w:space='0' w:color='888888'/>
                        <w:right w:val='single' w:sz='4' w:space='0' w:color='888888'/>
                    </w:tcBorders>
                    """
                    tcPr.append(parse_xml(borders_xml))
                for _ in range(spacing_mm // 2):
                    cell.paragraphs[0].add_run().add_text("\u2003")
                os.remove(img_path)
            row_cells = []
    return subdoc

# ----------------------------- APP -----------------------------
st.title("📑 Site Daily Report Generator (Pro)")

# Sidebar controls
with st.sidebar:
    st.header("Settings")
    discipline = st.radio("Choose discipline:", ["Civil", "Electrical"], index=0, key="discipline_radio")
    img_width_mm = st.slider("Image width (mm)", 30, 100, 70, 5)
    img_per_row = st.selectbox("Images per row", [1,2,3,4], index=1)
    add_border = st.checkbox("Add border to images", value=True)
    spacing_mm = st.slider("Spacing between images (mm)", 0, 20, 2, 1)

# Load data
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
    st.warning("Unable to fetch data from the Google Sheet.")
    rows = []

if not rows:
    st.warning("No data found in the Google Sheet.")
    st.stop()

sites = sorted({row[1].strip() for row in rows if len(row) > 1 and row[1].strip()})
all_dates = sorted({row[0].strip() for row in rows if len(row) > 0 and row[0].strip()})

with st.sidebar:
    selected_sites = st.multiselect("Choose sites:", ["All Sites"] + sites, default=["All Sites"])
    if "All Sites" in selected_sites or not selected_sites:
        selected_sites = sites
    selected_dates = st.multiselect("Choose dates:", ["All Dates"] + all_dates, default=["All Dates"])
    if "All Dates" in selected_dates or not selected_dates:
        selected_dates = all_dates

filtered_rows = [row for row in rows if row[1].strip() in selected_sites and row[0].strip() in selected_dates]
site_date_pairs = sorted({(row[1].strip(), row[0].strip()) for row in filtered_rows})
uploaded_image_mapping: dict[tuple[str, str], list] = {}

# Image uploads
for site_name, date in site_date_pairs:
    with st.expander(f"Upload Images for {site_name} ({date})"):
        imgs = st.file_uploader(
            f"Images for {site_name} ({date})", accept_multiple_files=True, key=f"uploader_{site_name}_{date}"
        )
        uploaded_image_mapping[(site_name, date)] = imgs or []

# Preview table
st.subheader("Preview")
df_preview = pd.DataFrame(
    filtered_rows,
    columns=["Date","Site_Name","District","Work","Human_Resources","Supply",
             "Work_Executed","Comment_on_work","Another_Work_Executed","Comment_on_HSE",
             "Consultant_Recommandation"]
)
st.dataframe(df_preview, use_container_width=True, hide_index=True)

# Generate reports
if st.button("🚀 Generate & Download All Reports"):
    with st.spinner("Generating reports..."):
        zip_buffer = tempfile.NamedTemporaryFile(delete=False, suffix=".zip")
        with zipfile.ZipFile(zip_buffer, "w") as zipf:
            for row in filtered_rows:
                date, site_name, district, work, human_resources, supply, work_executed, \
                comment_on_work, another_work_executed, comment_on_hse, consultant_recommandation = (row + [""]*11)[:11]

                tpl = DocxTemplate(TEMPLATE_PATH)

                # Build gallery
                image_files = uploaded_image_mapping.get((site_name, date), []) or []
                images_subdoc = build_gallery_subdoc(
                    tpl,
                    image_files,
                    img_width_mm=img_width_mm,
                    img_per_row=img_per_row,
                    add_border=add_border,
                    spacing_mm=spacing_mm
                )

                # Signatories
                sign_info = SIGNATORIES.get(discipline, {})
                cons_sig_path = resolve_asset(sign_info.get("Consultant_Signature"))
                cont_sig_path = resolve_asset(sign_info.get("Contractor_Signature"))
                cons_sig_img = InlineImage(tpl, cons_sig_path, width=Mm(30)) if cons_sig_path else ""
                cont_sig_img = InlineImage(tpl, cont_sig_path, width=Mm(30)) if cont_sig_path else ""

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
                    "Prepared_By": sign_info.get("Consultant_Name", ""),
                    "Prepared_Signature": cons_sig_img,
                    "Consultant_Title": sign_info.get("Consultant_Title", ""),
                    "Contractor_Name": sign_info.get("Contractor_Name", ""),
                    "Contractor_Title": sign_info.get("Contractor_Title", ""),
                    "Contractor_Signature": cont_sig_img,
                    "Images": images_subdoc,
                }

                tpl.render(ctx)
                out_name = f"{safe_filename(site_name)}_{format_date_title(date)}.docx"
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
