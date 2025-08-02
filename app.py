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

import json
from google.oauth2 import service_account

SCOPES = ['https://www.googleapis.com/auth/spreadsheets.readonly']

# Use Streamlit secrets for Google service account
service_account_info = json.loads(st.secrets["GOOGLE_CREDENTIALS"])
creds = service_account.Credentials.from_service_account_info(service_account_info, scopes=SCOPES)

service = build('sheets', 'v4', credentials=creds)
sheet = service.spreadsheets()

TEMPLATE_PATH = "Site_Report_Template.docx"

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
    # Pad missing fields
    padded_rows = [row + [""] * (5 - len(row)) for row in rows]
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

# --- UI: Site selection ---
with st.sidebar:
    st.header("Step 1: Select Sites")
    site_choices = ["All Sites"] + sites
    selected_sites = st.multiselect("Choose sites:", site_choices, default=["All Sites"])
    if "All Sites" in selected_sites:
        selected_sites = sites

# --- UI: Date selection ---
    st.header("Step 2: Select Dates")
    # Filter available dates for the selected sites only
    site_dates = sorted(list(set(row[0].strip() for row in rows if row[1].strip() in selected_sites)))
    date_choices = ["All Dates"] + site_dates
    selected_dates = st.multiselect("Choose dates:", date_choices, default=["All Dates"])
    if "All Dates" in selected_dates:
        selected_dates = site_dates

# --- Filter rows for preview ---
filtered_rows = [row for row in rows if row[1].strip() in selected_sites and row[0].strip() in selected_dates]

# --- Preview Table ---
st.subheader("Preview Reports to be Generated")
df_preview = pd.DataFrame(filtered_rows, columns=["Date", "Site", "Civil Works", "Planning", "Challenges"])
st.dataframe(df_preview, use_container_width=True, hide_index=True)

# --- Image Uploads ---
st.subheader("Step 3: Upload Images (Optional)")

st.markdown("You may upload multiple images and assign them to a specific site/date. Images will be included in the corresponding report.")

# Helper: Build site-date pairs for assignment
site_date_pairs = sorted(set((row[1].strip(), row[0].strip()) for row in filtered_rows))

uploaded_image_mapping = {}
if len(site_date_pairs) > 0:
    for idx, (site, date) in enumerate(site_date_pairs):
        with st.expander(f"Upload Images for {site} ({date})"):
            imgs = st.file_uploader(f"Images for {site} ({date})", accept_multiple_files=True, key=f"{site}_{date}")
            uploaded_image_mapping[(site, date)] = imgs

# --- Generate Reports ---
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

st.info("**Tip:** If you don't upload images, reports will still be generated with all your data.")
st.caption("Made for efficient, multi-site daily reporting. Feedback & customizations welcome!")


