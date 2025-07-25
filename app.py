
import streamlit as st
from docxtpl import DocxTemplate, InlineImage
from docx.shared import Mm
import os
from googleapiclient.discovery import build
from google.oauth2.service_account import Credentials
import tempfile
import shutil
import zipfile
import pandas as pd
import json  # NEW: for reading from secrets

st.markdown(
    """
    <style>
    [data-testid="stAppViewContainer"] {
        background-image: url('background.jpg');
        background-size: cover;
        background-position: center;
        background-repeat: no-repeat;
        min-height: 100vh;
    }
    [data-testid="stHeader"] {background: rgba(0,0,0,0);}
    [data-testid="stSidebar"] {background: rgba(255,255,255,0.97); border-right: 1px solid #dee2e6;}
    .stDataFrame { background: white; }
    </style>
    """,
    unsafe_allow_html=True
)

# --- CONFIG ---
SHEET_ID = '1t6Bmm3YN7mAovNM3iT7oMGeXG3giDONSejJ9gUbUeCI'
SHEET_NAME = 'Reports'
TEMPLATE_PATH = "New daily reports template.docx"

# --- Google Sheets API setup ---
SCOPES = ['https://www.googleapis.com/auth/spreadsheets.readonly']

@st.cache_resource
def get_sheet_service():
    # LOAD FROM SECRETS INSTEAD OF FILE!
    creds_dict = json.loads(st.secrets["GOOGLE_CREDENTIALS"])
    creds = Credentials.from_service_account_info(creds_dict, scopes=SCOPES)
    service = build('sheets', 'v4', credentials=creds)
    return service

def get_sheet_data(service):
    sheet = service.spreadsheets()
    result = sheet.values().get(
        spreadsheetId=SHEET_ID,
        range=f"{SHEET_NAME}!A2:F500"   # Fetch 6 columns
    ).execute()
    rows = result.get('values', [])
    # Pad missing fields (now 6 columns)
    padded_rows = [row + [""] * (6 - len(row)) for row in rows]
    return padded_rows

def get_unique_sites_and_dates(rows):
    """Return sorted unique site names and dates from the sheet rows."""
    sites = sorted({row[0].strip() for row in rows if len(row) > 0})
    dates = sorted({row[1].strip() for row in rows if len(row) > 1})
    return sites, dates

st.set_page_config(layout="wide", page_title="Site Daily Report Generator (Iranzi)")

# --- SIDEBAR: Navigation, Branding, Help ---
with st.sidebar:
    # Branding/logo
    try:
        st.image("ibc_logo.png", width=150)
    except Exception:
        pass  # If no logo, ignore
    st.markdown("### 🧭 Steps to Generate Reports")
    st.markdown("""
    <ol>
      <li><span style='color: green; font-weight: bold;'>Select Sites</span></li>
      <li>Select Dates</li>
      <li>Upload Images (Optional)</li>
      <li>Generate & Download</li>
    </ol>
    """, unsafe_allow_html=True)
    # Help
    with st.expander("ℹ️ Need Help?", expanded=False):
        st.markdown("""
        - **Step 1:** Select the sites you want.
        - **Step 2:** Pick the dates.
        - **Step 3:** (Optional) Upload images for each site/date.
        - **Step 4:** Hit 'Generate & Download Reports'!
        """)
    st.markdown("---")

st.title("📑 Site Daily Report Generator (Iranzi)")

# --- LOAD DATA WITH ERROR HANDLING ---
try:
    service = get_sheet_service()
    rows = get_sheet_data(service)
    sites, all_dates = get_unique_sites_and_dates(rows)
except Exception as e:
    st.error(f"❌ Could not load Google Sheets data: {e}")
    st.stop()

# --- UI: Site Selection ---
with st.expander("Step 1: Select Sites", expanded=True):
    site_choices = ["All Sites"] + sites
    selected_sites = st.multiselect("Choose sites:", site_choices, default=["All Sites"])
    if "All Sites" in selected_sites:
        selected_sites = sites

# --- UI: Date Selection ---
with st.expander("Step 2: Select Dates", expanded=False):
    site_dates = sorted({row[1].strip() for row in rows if row[0].strip() in selected_sites})
    date_choices = ["All Dates"] + site_dates
    selected_dates = st.multiselect("Choose dates:", date_choices, default=["All Dates"])
    if "All Dates" in selected_dates:
        selected_dates = site_dates

# --- Filter rows for preview ---
filtered_rows = [row for row in rows if row[0].strip() in selected_sites and row[1].strip() in selected_dates]

# --- Dynamic report count ---
with st.sidebar:
    st.markdown(f"**Reports to generate:** <span style='color:blue; font-size:1.2em;'>{len(filtered_rows)}</span>", unsafe_allow_html=True)

# --- Preview Table ---


# --- Image Uploads ---
with st.expander("Step 4: Upload Images (Optional)", expanded=False):
    st.markdown("You may upload up to **2 images per site/date**. Images will be included side-by-side in the report.")
    site_date_pairs = sorted({(row[0].strip(), row[1].strip()) for row in filtered_rows})
    uploaded_image_mapping = {}
    if len(site_date_pairs) > 0:
        for idx, (site, date) in enumerate(site_date_pairs):
            with st.expander(f"Images for {site} ({date})"):
                imgs = st.file_uploader(
                    f"Upload up to 2 images for {site} ({date})",
                    accept_multiple_files=True, type=['jpg', 'jpeg', 'png'], key=f"{site}_{date}"
                )
                # Only take first 2 images
                if imgs and len(imgs) > 2:
                    st.warning("Only the first 2 images will be used.")
                uploaded_image_mapping[(site, date)] = imgs[:2] if imgs else []

# --- GENERATE REPORTS BUTTON ---
if st.button("🚀 Generate & Download All Reports"):
    if not filtered_rows:
        st.error("Please select at least one site and one date to generate reports.")
    else:
        with st.spinner("Generating reports, please wait..."):
            temp_dir = tempfile.mkdtemp()
            zip_buffer = tempfile.NamedTemporaryFile(delete=False, suffix=".zip")
            progress = st.progress(0)
            with zipfile.ZipFile(zip_buffer, "w") as zipf:
                for idx, row in enumerate(filtered_rows):
                    # Extract the columns in the order defined in the sheet
                    site, date, civil_works, general_rec, comments, challenges = (row + [""] * 6)[:6]
                    tpl = DocxTemplate(TEMPLATE_PATH)
                    # Attach up to two images for this site/date (side-by-side support)
                    image_files = uploaded_image_mapping.get((site, date), [])
                    image1, image2 = None, None
                    if len(image_files) > 0:
                        img1_path = os.path.join(temp_dir, image_files[0].name)
                        with open(img1_path, "wb") as f:
                            f.write(image_files[0].getbuffer())
                        image1 = InlineImage(tpl, img1_path, width=Mm(70))  # Adjust width as needed
                    if len(image_files) > 1:
                        img2_path = os.path.join(temp_dir, image_files[1].name)
                        with open(img2_path, "wb") as f:
                            f.write(image_files[1].getbuffer())
                        image2 = InlineImage(tpl, img2_path, width=Mm(70))

                    filename = f"SITE DAILY REPORT_{site}_{date.replace('/', '.')}.docx"
                    tpl.render(context)
                    out_path = os.path.join(temp_dir, filename)
                    tpl.save(out_path)
                    zipf.write(out_path, arcname=filename)
                    progress.progress((idx + 1) / len(filtered_rows))
            st.success("All reports generated successfully!")
            with open(zip_buffer.name, "rb") as f:
                st.download_button("⬇️ Download All Reports (ZIP)", data=f, file_name="reports.zip")
            shutil.rmtree(temp_dir)
            os.remove(zip_buffer.name)

# --- Footer Info ---
st.info("**Tip:** If you don't upload images, reports will still be generated with all your data.")
st.caption("Made for efficient, multi-site daily reporting. Feedback & customizations welcome!")
