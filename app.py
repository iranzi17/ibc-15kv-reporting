import streamlit as st
from docxtpl import DocxTemplate, InlineImage
from docx.shared import Mm
import os
import glob
from googleapiclient.discovery import build
from google.oauth2.service_account import Credentials
import tempfile
import shutil
import zipfile
import pandas as pd

# --- CONFIG ---
SHEET_ID = '1t6Bmm3YN7mAovNM3iT7oMGeXG3giDONSejJ9gUbUeCI'
SHEET_NAME = 'Reports'
CREDENTIALS_PATH = "credentials.json"
TEMPLATE_PATH = "Site_Report_Template.docx"
LOGO_PATH = "ibc_logo.png"   # Place your IBC Group logo here

PRIMARY_COLOR = "#1B365D"    # IBC blue (adjust as desired)

# --- Streamlit Setup ---
st.set_page_config(
    page_title="IBC Group – 15kV Kigali Reporting",
    page_icon=LOGO_PATH if os.path.exists(LOGO_PATH) else "📊",
    layout="wide",
    initial_sidebar_state="expanded"
)

# --- Header / Branding ---
col1, col2 = st.columns([1,6])
with col1:
    if os.path.exists(LOGO_PATH):
        st.image(LOGO_PATH, width=80)
    else:
        st.markdown(f"<div style='height:80px'></div>", unsafe_allow_html=True)
with col2:
    st.markdown(f"""
        <h1 style="color:{PRIMARY_COLOR};margin-bottom:0;">IBC Group</h1>
        <h3 style="color:#333;margin-top:0;">15kV Kigali Project – Daily Report Generator</h3>
        """, unsafe_allow_html=True)

st.markdown("---")

st.info("Welcome! Easily generate professional daily site reports for the 15kV Kigali project. Select sites/dates, upload images, and download your reports instantly.")

# --- Google Sheets API setup ---
SCOPES = ['https://www.googleapis.com/auth/spreadsheets.readonly']
creds = Credentials.from_service_account_file(CREDENTIALS_PATH, scopes=SCOPES)
service = build('sheets', 'v4', credentials=creds)
sheet = service.spreadsheets()

def get_sheet_data():
    result = sheet.values().get(
        spreadsheetId=SHEET_ID,
        range=f"{SHEET_NAME}!A2:E500"
    ).execute()
    rows = result.get('values', [])
    padded_rows = [row + [""] * (5 - len(row)) for row in rows]
    return padded_rows

def get_unique_sites_and_dates(rows):
    sites = sorted(list(set(row[1].strip() for row in rows if len(row) > 1)))
    dates = sorted(list(set(row[0].strip() for row in rows if len(row) > 0)))
    return sites, dates

rows = get_sheet_data()
sites, all_dates = get_unique_sites_and_dates(rows)

with st.sidebar:
    st.markdown("### 1. Select Sites")
    site_choices = ["All Sites"] + sites
    selected_sites = st.multiselect("Choose sites:", site_choices, default=["All Sites"])
    if "All Sites" in selected_sites:
        selected_sites = sites

    st.markdown("### 2. Select Dates")
    site_dates = sorted(list(set(row[0].strip() for row in rows if row[1].strip() in selected_sites)))
    date_choices = ["All Dates"] + site_dates
    selected_dates = st.multiselect("Choose dates:", date_choices, default=["All Dates"])
    if "All Dates" in selected_dates:
        selected_dates = site_dates

    st.markdown("---")
    st.markdown(f"""
    <div style="font-size:0.9em;color:gray;">
        <b>IBC Group Reporting System</b><br>
        For help, contact your IT department.
    </div>
    """, unsafe_allow_html=True)

# Filter rows for preview
filtered_rows = [row for row in rows if row[1].strip() in selected_sites and row[0].strip() in selected_dates]

# Preview Table
st.markdown("### Preview: Reports to be Generated")
if filtered_rows:
    df_preview = pd.DataFrame(filtered_rows, columns=["Date", "Site", "Civil Works", "Planning", "Challenges"])
    st.dataframe(df_preview, use_container_width=True, hide_index=True)
else:
    st.warning("No reports match your selection.")

# Image Uploads
st.markdown("### 3. Upload Images (Optional)")
st.caption("You can upload images for each site and date (expand each section). Images will appear in the relevant reports.")

site_date_pairs = sorted(set((row[1].strip(), row[0].strip()) for row in filtered_rows))
uploaded_image_mapping = {}
if len(site_date_pairs) > 0:
    for idx, (site, date) in enumerate(site_date_pairs):
        with st.expander(f"Upload Images for {site} ({date})"):
            imgs = st.file_uploader(f"Images for {site} ({date})", accept_multiple_files=True, key=f"{site}_{date}")
            uploaded_image_mapping[(site, date)] = imgs

# Report Generation Button
if st.button("🚀 Generate & Download All Reports"):
    with st.spinner("Generating reports, please wait..."):
        temp_dir = tempfile.mkdtemp()
        zip_buffer = tempfile.NamedTemporaryFile(delete=False, suffix=".zip")
        with zipfile.ZipFile(zip_buffer, "w") as zipf:
            for row in filtered_rows:
                date, site, civil_works, planning, challenges = (row + [""] * 5)[:5]
                tpl = DocxTemplate(TEMPLATE_PATH)
                # Attach images if uploaded for this site/date
                image_files = uploaded_image_mapping.get((site, date), [])
                images = []
                for img_file in image_files:
                    img_path = os.path.join(temp_dir, img_file.name)
                    with open(img_path, "wb") as f:
                        f.write(img_file.getbuffer())
                    images.append(InlineImage(tpl, img_path, width=Mm(70)))
                context = {
                    'SITE_NAME': site,
                    'DATE': date,
                    'CIVIL_WORKS': civil_works,
                    'PLANNING': planning,
                    'CHALLENGES': challenges,
                    'ALL_IMAGES': images
                }
                filename = f"SITE DAILY REPORT_{site}_{date.replace('/', '.')}.docx"
                tpl.render(context)
                out_path = os.path.join(temp_dir, filename)
                tpl.save(out_path)
                zipf.write(out_path, arcname=filename)
        st.success("All reports generated successfully!")
        with open(zip_buffer.name, "rb") as f:
            st.download_button("⬇️ Download All Reports (ZIP)", data=f, file_name="reports.zip")
        shutil.rmtree(temp_dir)
        os.remove(zip_buffer.name)

st.markdown("---")
st.markdown(
    "<div style='text-align:center;color:gray;font-size:0.9em;'>Powered by <b>IBC Group</b> | Kigali 15kV Project Reporting System</div>",
    unsafe_allow_html=True
)
