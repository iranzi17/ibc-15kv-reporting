
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
from datetime import datetime, timedelta

from utils import parse_any_date

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
    sites = sorted(list(set(row[1].strip() for row in rows if len(row) > 1)))
    dates = sorted(list(set(row[0].strip() for row in rows if len(row) > 0)))
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
    site_dates = sorted(list(set(row[0].strip() for row in rows if row[1].strip() in selected_sites)))
    date_choices = ["All Dates"] + site_dates
    selected_dates = st.multiselect("Choose dates:", date_choices, default=["All Dates"])
    if "All Dates" in selected_dates:
        selected_dates = site_dates

# --- Filter rows for preview ---
filtered_rows = [row for row in rows if row[1].strip() in selected_sites and row[0].strip() in selected_dates]

# --- Dynamic report count ---
with st.sidebar:
    st.markdown(f"**Reports to generate:** <span style='color:blue; font-size:1.2em;'>{len(filtered_rows)}</span>", unsafe_allow_html=True)

# --- Preview Table ---
with st.expander("Step 3: Preview Reports to be Generated", expanded=True):
    if filtered_rows:
        # Now include Electrical Work in columns
        df_preview = pd.DataFrame(filtered_rows, columns=[
            "Date", "Site", "Civil Works", "Electrical Work", "Planning", "Challenges"
        ])
        st.dataframe(df_preview, use_container_width=True, hide_index=True)
    else:
        st.info("No reports match your selection. Please adjust your sites or dates.")

# --- Image Uploads ---
with st.expander("Step 4: Upload Images (Optional)", expanded=False):
    st.markdown("You may upload up to **2 images per site/date**. Images will be included side-by-side in the report.")
    site_date_pairs = sorted(set((row[1].strip(), row[0].strip()) for row in filtered_rows))
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
                    # Now extract 6 columns!
                    date, site, civil_works, electrical_work, planning, challenges = (row + [""] * 6)[:6]
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
                    context = {
                        'Site Name': site,
                        'Date': date,
                        'Civil Works': civil_works,
                        'General recommendation': electrical_work,
                        'Comments about the activities performed and challenges faced': planning,
                        'Challenges': challenges,
                        'Cabin  or Underground Cables': '',
                        'District': '',
                        'Personnel': '',
                        'Materials and equipment': '',
                        'Comments about observation on rules of HEALTH, SAFETY & ENVIRONMENT': '',
                    }
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


# --------------- SETTINGS ---------------
WEEKLY_TEMPLATE_PATH = "Weekly reports template.docx"
HF_TOKEN = st.secrets.get("HF_TOKEN")

# import the summarization helper from a separate module so it can be tested in isolation
from summary_utils import generate_hf_summary


st.header("🗓️ Generate Weekly Electrical Consultant Report")

with st.expander("Step 1: Select Week and Generate Report", expanded=True):

    # --- Week picker
    week_start = st.date_input("Start of Week", value=datetime.today()-timedelta(days=6))
    week_end = st.date_input("End of Week", value=datetime.today())

    # --- Filter your existing daily rows by week
    week_rows = []
    for row in rows:
        try:
            row_date = parse_any_date(row[0])
            if week_start <= row_date <= week_end:
                week_rows.append(row)
        except Exception:
            continue  # Optionally log errors here

    st.write(f"Found {len(week_rows)} daily reports in this week.")  # <--- For debugging

    if week_rows:
        # --- Concatenate data for the summary
        week_text = "\n\n".join(
            f"Date: {row[0]}\nSite: {row[1]}\nCivil: {row[2]}\nElectrical: {row[3]}\nPlan: {row[4]}\nChallenges: {row[5]}"
            for row in week_rows
        )

        # --- Extract other fields for the context
        issues = "\n".join([row[5] for row in week_rows if row[5]])
        difficulties = "\n".join([row[5] for row in week_rows if "difficult" in row[5].lower()])
        ongoing_activities = "\n".join([row[3] for row in week_rows if row[3]])
        achievements = "\n".join([row[2] for row in week_rows if "complete" in row[2].lower() or "finish" in row[2].lower()])
        planned_activities = "\n".join([row[4] for row in week_rows if row[4]])
        hse = "No incidents reported this week."   # Add your logic or field if available

        st.write("Preview of Aggregated Data:")
        st.code(week_text)

        if st.button("✨ Generate and Download Weekly Report (.docx)"):
            with st.spinner("Generating summary and filling template..."):
                summary = generate_hf_summary(week_text, HF_TOKEN)

                context = {
                    "WEEK_NO": week_start.isocalendar()[1],
                    "PERIOD_FROM": week_start.strftime('%Y-%m-%d'),
                    "PERIOD_TO": week_end.strftime('%Y-%m-%d'),
                    "DOCUMENT_NO": f"WR-{week_start.strftime('%Y%m%d')}-{week_end.strftime('%Y%m%d')}",
                    "DATE": datetime.today().strftime('%Y-%m-%d'),
                    "PROJECT_NAME": "15kV Substation Project",  # Or ask user
                    "SUMMARY": summary,
                    "PROJECT_PROGRESS": summary,
                    "ISSUES": issues or "None.",
                    "DIFFICULTIES": difficulties or "None.",
                    "ONGOING_ACTIVITIES": ongoing_activities or "See attached summary.",
                    "ACHIEVEMENTS": achievements or "See attached summary.",
                    "PLANNED_ACTIVITIES": planned_activities or "See attached summary.",
                    "HSE": hse,
                }

                tpl = DocxTemplate(WEEKLY_TEMPLATE_PATH)
                tpl.render(context)
                out_path = f"Weekly_Report_{week_start.strftime('%Y%m%d')}_to_{week_end.strftime('%Y%m%d')}.docx"
                tpl.save(out_path)

                with open(out_path, "rb") as f:
                    st.download_button(
                        "⬇️ Download Filled Weekly Report (.docx)",
                        data=f,
                        file_name=out_path
                    )
            st.success("Report generated!")
    else:
        st.info("No daily reports found in this week’s range. Try different dates.")



# --- Footer Info ---
st.info("**Tip:** If you don't upload images, reports will still be generated with all your data.")
st.caption("Made for efficient, multi-site daily reporting. Feedback & customizations welcome!")
