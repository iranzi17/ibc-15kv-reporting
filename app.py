import streamlit as st
import pandas as pd
import gspread
from google.oauth2.service_account import Credentials
from docx import Document
from docx.shared import Inches
import tempfile
import shutil
import os
import zipfile
from PIL import Image

st.set_page_config(
    page_title="15kV Kigali Project – Daily Report Generator",
    layout="wide"
)

st.title("15kV Kigali Project – Daily Report Generator")
st.info(
    "Welcome! Easily generate professional daily site reports for the 15kV Kigali project. "
    "Select sites/dates, upload images, and download your reports instantly."
)

# SHEET SETTINGS – Replace these with your actual IDs/names if changed
SHEET_ID = '1t6Bmm3YN7mAovNM3iT7oMGeX3giDONSejJ9gUbUeCI'
SHEET_NAME = 'Reports'

TEMPLATE_PATH = 'Site_Report_Template.docx'

# Function to get data from Google Sheets
@st.cache_data(ttl=3600)
def get_sheet_data():
    creds_dict = st.secrets["google_service_account"]
    scopes = ["https://www.googleapis.com/auth/spreadsheets.readonly"]
    creds = Credentials.from_service_account_info(dict(creds_dict), scopes=scopes)
    gc = gspread.authorize(creds)
    ws = gc.open_by_key(SHEET_ID).worksheet(SHEET_NAME)
    df = pd.DataFrame(ws.get_all_records())
    return df

def insert_images_to_docx(doc: Document, image_paths, caption=None):
    for img_path in image_paths:
        # Insert image (resize to width=5 inches for uniformity)
        doc.add_picture(img_path, width=Inches(5))
        if caption:
            doc.add_paragraph(caption)
        doc.add_paragraph("")  # Add space after image

def generate_report(row, images, output_dir):
    doc = Document(TEMPLATE_PATH)
    # Replace placeholders
    for p in doc.paragraphs:
        if "{SITE_NAME}" in p.text:
            p.text = p.text.replace("{SITE_NAME}", str(row["SITE_NAME"]))
        if "{DATE}" in p.text:
            p.text = p.text.replace("{DATE}", str(row["Date"]))
        if "{CIVIL_WORKS}" in p.text:
            p.text = p.text.replace("{CIVIL_WORKS}", str(row["CIVIL_WORKS"]))
        if "{PLANNING}" in p.text:
            p.text = p.text.replace("{PLANNING}", str(row["PLANNING"]))
        if "{CHALLENGES}" in p.text:
            p.text = p.text.replace("{CHALLENGES}", str(row["CHALLENGES"]))
    # Optionally add images to end
    if images:
        doc.add_page_break()
        doc.add_paragraph("Site Images:")
        insert_images_to_docx(doc, images)
    # Output path
    fname = f"SITE DAILY REPORT_{row['SITE_NAME'].replace(' ', '_')}_{row['Date']}.docx"
    fpath = os.path.join(output_dir, fname)
    doc.save(fpath)
    return fpath

# MAIN APP LOGIC
df = get_sheet_data()
all_sites = df['SITE_NAME'].drop_duplicates().tolist()
dates = df['Date'].drop_duplicates().tolist()

with st.form("report_form"):
    selected_sites = st.multiselect("Select site(s) to generate reports for:", all_sites)
    selected_date = st.selectbox("Select date:", dates)
    images = st.file_uploader(
        "Upload image(s) for the report (optional):",
        accept_multiple_files=True, type=['jpg', 'jpeg', 'png']
    )
    submit_btn = st.form_submit_button("Generate Reports")

if submit_btn and selected_sites:
    with st.spinner("Generating reports..."):
        temp_dir = tempfile.mkdtemp()
        reports = []
        for site in selected_sites:
            row = df[(df["SITE_NAME"] == site) & (df["Date"] == selected_date)]
            if row.empty:
                st.warning(f"No data found for {site} on {selected_date}")
                continue
            row = row.iloc[0]
            img_paths = []
            if images:
                site_img_dir = os.path.join(temp_dir, site.replace(' ', '_'))
                os.makedirs(site_img_dir, exist_ok=True)
                for img in images:
                    img_path = os.path.join(site_img_dir, img.name)
                    image = Image.open(img)
                    image.save(img_path)
                    img_paths.append(img_path)
            report_path = generate_report(row, img_paths, temp_dir)
            reports.append(report_path)
        # Zip all reports
        if reports:
            zip_path = os.path.join(temp_dir, f"Reports_{selected_date}.zip")
            with zipfile.ZipFile(zip_path, 'w') as zf:
                for rep in reports:
                    zf.write(rep, os.path.basename(rep))
            st.success(f"Generated {len(reports)} reports.")
            with open(zip_path, "rb") as f:
                st.download_button("Download all reports (ZIP)", data=f, file_name=os.path.basename(zip_path))
        else:
            st.error("No reports generated. Please check your selections.")
