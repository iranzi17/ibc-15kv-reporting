import streamlit as st


def _resolve_signature_path(candidate):
    # Resolve signature image path with flexible extensions (.png, .jpg, .jpeg, .webp).
    # Returns a valid existing file path or None.
    if not candidate:
        return None
    import os
    exts = [".png", ".jpg", ".jpeg", ".webp"]
    # If path exists as-is, use it
    if os.path.exists(candidate):
        return candidate
    base_dir, name = os.path.split(candidate)
    stem, ext = os.path.splitext(name)
    candidates = []
    if ext:
        # Try sibling extensions if provided ext doesn't exist
        candidates.extend([os.path.join(base_dir or "signatures", stem + e) for e in exts])
    else:
        # No extension provided: assume signatures/<stem>.<ext> if no base_dir
        if not base_dir:
            base_dir = "signatures"
        candidates.extend([os.path.join(base_dir, stem + e) for e in exts])
    for c in candidates:
        if os.path.exists(c):
            return c
    return None
import json

from google.oauth2 import service_account

from googleapiclient.discovery import build

from docxtpl import DocxTemplate, InlineImage

from docx.shared import Mm

import os

import tempfile

import shutil

import zipfile

import pandas as pd

import streamlit as st

import json

from google.oauth2 import service_account

from googleapiclient.discovery import build

from docxtpl import DocxTemplate, InlineImage

from docx.shared import Mm

import os

import tempfile

import shutil

import zipfile

import pandas as pd


# --- Google Sheets API setup ---
SCOPES = ['https://www.googleapis.com/auth/spreadsheets.readonly']

# Load Google credentials from Streamlit secrets
service_account_info = json.loads(st.secrets["GOOGLE_CREDENTIALS"])
creds = service_account.Credentials.from_service_account_info(service_account_info, scopes=SCOPES)
service = build('sheets', 'v4', credentials=creds)
sheet = service.spreadsheets()

SHEET_ID = '1t6Bmm3YN7mAovNM3iT7oMGeXG3giDONSejJ9gUbUeCI'
SHEET_NAME = 'Reports'
TEMPLATE_PATH = "Site_Daily_report_Template_Date.docx"

SIGNATORIES = {
    "Civil": {
        "Consultant_Name": "IRANZI Prince Jean Claude",
        "Consultant_Title": "Civil Engineer",   # or "Junior Civil Engineer" if you prefer
        "Consultant_Signature": os.path.join("signatures", "iranzi_prince_jean_claude"),  # no ext needed
        "Contractor_Name": "RUTALINDWA Olivier",
        "Contractor_Title": "Civil Engineer",
        "Contractor_Signature": os.path.join("signatures", "rutalindwa_olivier"),         # no ext needed
    },
    "Electrical": {
        "Consultant_Name": "Alexis IVUGIZA",
        "Consultant_Title": "Electrical Engineer",
        "Consultant_Signature": os.path.join("signatures", "alexis_ivugiza"),
        "Contractor_Name": "Issac HABIMANA",   # tell me if you want 'Isaac'
        "Contractor_Title": "Electrical Engineer",
        "Contractor_Signature": os.path.join("signatures", "issac_habimana"),
    },
}

@st.cache_data(ttl=300)
def get_sheet_data():
    result = sheet.values().get(
        spreadsheetId=SHEET_ID,
        range=f"{SHEET_NAME}!A:K"
    ).execute()
    rows = result.get('values', [])
    padded_rows = [row + [""] * (11 - len(row)) for row in rows]
    return padded_rows

def get_unique_sites_and_dates(rows):
    sites = sorted(list(set(row[1].strip() for row in rows if len(row) > 1)))
    dates = sorted(list(set(row[0].strip() for row in rows if len(row) > 0)))
    return sites, dates

st.set_page_config(layout="wide")
st.title("📑 Site Daily Report Generator (Pro)")

# --- Load data ---
rows = get_sheet_data()
sites, all_dates = get_unique_sites_and_dates(rows)

# --- UI: Site/Date filters (Sidebar only) ---
with st.sidebar:
    st.header("Step 0: Select Discipline")
    discipline = st.radio(
        "Choose discipline:", ["Civil", "Electrical"], index=0, key="discipline_radio"
    )

    st.header("Step 1: Select Sites")
    site_choices = ["All Sites"] + sites
    selected_sites = st.multiselect(
        "Choose sites:", site_choices, default=["All Sites"], key="sites_ms"
    )
    # If All Sites (or nothing) selected, use all sites
    if "All Sites" in selected_sites or not selected_sites:
        selected_sites = sites

    # --- UI: Date selection ---
    st.header("Step 2: Select Dates")
    site_dates = sorted({row[0].strip() for row in rows if row[1].strip() in selected_sites})
    date_choices = ["All Dates"] + site_dates
    selected_dates = st.multiselect(
        "Choose dates:", date_choices, default=["All Dates"], key="dates_ms"
    )
    if "All Dates" in selected_dates or not selected_dates:
        selected_dates = site_dates

# --- Filter rows for preview ---
filtered_rows = [row for row in rows if row[1].strip() in selected_sites and row[0].strip() in selected_dates]

# Build unique (site, date) pairs for upload sections
site_date_pairs = sorted({(row[1].strip(), row[0].strip()) for row in filtered_rows})

# Hold uploaded images per (site, date)
uploaded_image_mapping = {}

# --- Preview Table ---
st.subheader("Preview Reports to be Generated")
df_preview = pd.DataFrame(
    filtered_rows,
    columns=[
        "Date", "Site_Name", "District", "Work", "Human_Resources", "Supply",
        "Work_Executed", "Comment_on_work", "Another_Work_Executed",
        "Comment_on_HSE", "Consultant_Recommandation"
    ]
)
st.dataframe(df_preview, use_container_width=True, hide_index=True)

# --- Image Uploads ---
if len(site_date_pairs) > 0:
    for idx, (site_name, date) in enumerate(site_date_pairs):
        with st.expander(f"Upload Images for {site_name} ({date})"):
            imgs = st.file_uploader(
                f"Images for {site_name} ({date})", accept_multiple_files=True,
                key=f"{site_name}_{date}"
            )
            uploaded_image_mapping[(site_name, date)] = imgs
else:
    st.info("No site/date pairs in current filter. Adjust filters to upload images.")

# --- Generate Reports ---
if st.button("🚀 Generate & Download All Reports"):
    with st.spinner("Generating reports, please wait..."):
        temp_dir = tempfile.mkdtemp()
        zip_buffer = tempfile.NamedTemporaryFile(delete=False, suffix=".zip")
        with zipfile.ZipFile(zip_buffer, "w") as zipf:
            for row in filtered_rows:
                (
                    date, site_name, district, work, human_resources, supply,
                    work_executed, comment_on_work, another_work_executed,
                    comment_on_hse, consultant_recommandation
                ) = (row + [""] * 11)[:11]
                tpl = DocxTemplate(TEMPLATE_PATH)
                image_files = uploaded_image_mapping.get((site_name, date), [])
                from docxtpl import RichText
                images_rt = RichText()
                for img_file in image_files:
                    img_path = os.path.join(temp_dir, img_file.name)
                    with open(img_path, "wb") as f:
                        f.write(img_file.getbuffer())
                    images_rt.add(InlineImage(tpl, img_path, width=Mm(70)))
                
                # Build signatory info (safe defaults)
                sign_info = SIGNATORIES.get(discipline, {})

                # Final context for the DOCX template (keys match placeholders)
                context = {
                    'Site_Name': site_name or '',
                    'Date': date or '',
                    'District': district or '',
                    'Work': work or '',
                    'Human_Resources': human_resources or '',
                    'Supply': supply or '',
                    'Work_Executed': work_executed or '',
                    'Comment_on_work': comment_on_work or '',
                    'Another_Work_Executed': another_work_executed or '',
                    'Comment_on_HSE': comment_on_hse or '',
                    'Consultant_Recommandation': consultant_recommandation or '',
                    'Images': images_rt,
                    # Optional placeholders (add to template if you want signatures and names printed)
                    'Consultant_Name': sign_info.get('Consultant_Name', ''),
                    'Contractor_Name': sign_info.get('Contractor_Name', ''),
                    'Consultant_Title': sign_info.get('Consultant_Title', ''),
                    'Contractor_Title': sign_info.get('Contractor_Title', ''),
                    'Consultant_Signature': InlineImage(tpl, _resolve_signature_path(sign_info.get('Consultant_Signature')), width=Mm(30)) if _resolve_signature_path(sign_info.get('Consultant_Signature')) else None,
                    'Contractor_Signature': InlineImage(tpl, _resolve_signature_path(sign_info.get('Contractor_Signature')), width=Mm(30)) if _resolve_signature_path(sign_info.get('Contractor_Signature')) else None,
                }
                filename = f"SITE DAILY REPORT_{site_name}_{date.replace('/', '.')}.docx"
                tpl.render(context)
                out_path = os.path.join(temp_dir, filename)
                tpl.save(out_path)
                zipf.write(out_path, arcname=filename)
        st.success("All reports generated successfully!")
        with open(zip_buffer.name, "rb") as f:
            st.download_button("⬇️ Download All Reports (ZIP)", data=f, file_name="reports.zip")
        shutil.rmtree(temp_dir)
        os.remove(zip_buffer.name)

st.info("**Tip:** If you don't upload images, reports will still be generated with all your data.")
st.caption("Made for efficient, multi-site daily reporting. Feedback & customizations welcome!")
