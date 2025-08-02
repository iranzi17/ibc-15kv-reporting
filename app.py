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

def get_sheet_data():
    result = sheet.values().get(
        spreadsheetId=SHEET_ID,
        range=f"{SHEET_NAME}!A2:K500"
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

# --- UI: Site selection ---
with st.sidebar:
    st.header("Step 1: Select Sites")
    site_choices = ["All Sites"] + sites
    selected_sites = st.multiselect("Choose sites:", site_choices, default=["All Sites"])
    if "All Sites" in selected_sites:
        selected_sites = sites

    # --- UI: Date selection ---
    st.header("Step 2: Select Dates")
    site_dates = sorted(list(set(row[0].strip() for row in rows if row[1].strip() in selected_sites)))
    date_choices = ["All Dates"] + site_dates
    selected_dates = st.multiselect("Choose dates:", date_choices, default=["All Dates"])
    if "All Dates" in selected_dates:
        selected_dates = site_dates

# --- Filter rows for preview ---
filtered_rows = [row for row in rows if row[1].strip() in selected_sites and row[0].strip() in selected_dates]

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
st.subheader("Step 3: Upload Images (Optional)")
st.markdown("You may upload multiple images and assign them to a specific site/date. Images will be included in the corresponding report.")

site_date_pairs = sorted(set((row[1].strip(), row[0].strip()) for row in filtered_rows))
uploaded_image_mapping = {}
if len(site_date_pairs) > 0:
    for idx, (site_name, date) in enumerate(site_date_pairs):
        with st.expander(f"Upload Images for {site_name} ({date})"):
            imgs = st.file_uploader(f"Images for {site_name} ({date})", accept_multiple_files=True, key=f"{site_name}_{date}")
            uploaded_image_mapping[(site_name, date)] = imgs

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
                images = []
                for img_file in image_files:
                    img_path = os.path.join(temp_dir, img_file.name)
                    with open(img_path, "wb") as f:
                        f.write(img_file.getbuffer())
                    images.append(InlineImage(tpl, img_path, width=Mm(70)))
                context = {
                    'Site_Name': site_name,
                    'Date': date,
                    'District': district,
                    'Work': work,
                    'Human_Resources': human_resources,
                    'Supply': supply,
                    'Work_Executed': work_executed,
                    'Comment_on_work': comment_on_work,
                    'Another_Work_Executed': another_work_executed,
                    'Comment_on_HSE': comment_on_hse,
                    'Consultant_Recommandation': consultant_recommandation,
                    'Images': images
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
