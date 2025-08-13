import os
import re
import json
import tempfile
import zipfile
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

# -----------------------------
# Paths & small helpers
# -----------------------------
BASE_DIR = Path(__file__).parent.resolve()

def resolve_asset(name: Optional[str]) -> Optional[str]:
    """
    Find an asset (e.g., signature image) whether it’s in ./ or ./signatures/,
    with or without extension. Tries .png/.jpg/.jpeg/.webp.
    Returns an absolute path or None.
    """
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
        # Fallback: normalize common separators to dots
        return str(d).replace("/", ".").replace("-", ".")


def safe_filename(s: str, max_len: int = 150) -> str:
    """Remove illegal filename characters and tidy whitespace."""
    s = str(s)
    s = re.sub(r'[\\/:*?"<>|]+', "-", s)  # illegal on Windows + unsafe elsewhere
    s = re.sub(r"\s+", " ", s).strip(" .-")
    return s[:max_len]


def merge_daily_reports(files):
    """Merge multiple daily report DOCX files into a single document with page breaks."""
    if not files:
        return None

    merged_doc = Document(BytesIO(files[0].getvalue()))
    for f in files[1:]:
        doc = Document(BytesIO(f.getvalue()))
        merged_doc.add_page_break()
        for element in doc.element.body:
            merged_doc.element.body.append(element)

    output = BytesIO()
    merged_doc.save(output)
    output.seek(0)
    return output

# -----------------------------
# App config & constants
# -----------------------------
st.set_page_config(layout="wide", page_title="Site Daily Report Generator (Pro)")

SHEET_ID = "1t6Bmm3YN7mAovNM3iT7oMGeXG3giDONSejJ9gUbUeCI"
SHEET_NAME = "Reports"
TEMPLATE_PATH = "Site_Daily_report_Template_Date.docx"

SIGNATORIES = {
    "Civil": {
        "Consultant_Name": "IRANZI Prince Jean Claude",
        "Consultant_Title": "Civil Engineer",
        # Keep stems; resolver will find .jpg/.png in repo root or ./signatures
        "Consultant_Signature": "iranzi_prince_jean_claude",
        "Contractor_Name": "RUTALINDWA Olivier",
        "Contractor_Title": "Civil Engineer",
        "Contractor_Signature": "rutalindwa_olivier",
    },
    "Electrical": {
        "Consultant_Name": "Alexis IVUGIZA",
        "Consultant_Title": "Electrical Engineer",
        "Consultant_Signature": "alexis_ivugiza",
        "Contractor_Name": "Issac HABIMANA",  # say if you want 'Isaac'
        "Contractor_Title": "Electrical Engineer",
        "Contractor_Signature": "issac_habimana",
    },
}

# -----------------------------
# Google Sheets
# -----------------------------
SCOPES = ["https://www.googleapis.com/auth/spreadsheets.readonly"]

@st.cache_data(ttl=300)
def get_sheet_data() -> list[list[str]]:
    # Load credentials from Streamlit secrets
    service_account_info = json.loads(st.secrets["GOOGLE_CREDENTIALS"])
    creds = service_account.Credentials.from_service_account_info(
        service_account_info, scopes=SCOPES
    )
    service = build("sheets", "v4", credentials=creds)
    sheet = service.spreadsheets()

    result = sheet.values().get(
        spreadsheetId=SHEET_ID,
        range=f"{SHEET_NAME}!A:K",  # open-ended range
    ).execute()
    rows = result.get("values", [])
    # pad rows to 11 columns to avoid index errors
    padded_rows = [row + [""] * (11 - len(row)) for row in rows]
    return padded_rows


def get_unique_sites_and_dates(rows: list[list[str]]):
    sites = sorted({row[1].strip() for row in rows if len(row) > 1 and row[1].strip()})
    dates = sorted({row[0].strip() for row in rows if len(row) > 0 and row[0].strip()})
    return sites, dates

# -----------------------------
# UI
# -----------------------------
st.title("📑 Site Daily Report Generator (Pro)")

rows = get_sheet_data()
if not rows:
    st.warning("No data found in the Google Sheet.")
    st.stop()

sites, all_dates = get_unique_sites_and_dates(rows)

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
    if "All Sites" in selected_sites or not selected_sites:
        selected_sites = sites

    st.header("Step 2: Select Dates")
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

# (site, date) pairs for upload mapping
site_date_pairs = sorted({(row[1].strip(), row[0].strip()) for row in filtered_rows})

# Uploads mapping
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

# Image uploads
if site_date_pairs:
    for site_name, date in site_date_pairs:
        with st.expander(f"Upload Images for {site_name} ({date})"):
            imgs = st.file_uploader(
                f"Images for {site_name} ({date})",
                accept_multiple_files=True,
                key=f"uploader_{site_name}_{date}",
            )
            uploaded_image_mapping[(site_name, date)] = imgs
else:
    st.info("No site/date pairs in current filter. Adjust filters to upload images.")

# -----------------------------
# Generate reports
# -----------------------------
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

                # Images from uploader → put each photo in a subdocument paragraph
                image_files = uploaded_image_mapping.get((site_name, date), []) or []
                images_subdoc = tpl.new_subdoc()
                for img_file in image_files:
                    img_path = os.path.join(temp_dir, img_file.name)
                    with open(img_path, "wb") as f:
                        f.write(img_file.getbuffer())
                    p = images_subdoc.add_paragraph()
                    r = p.add_run()
                    r.add_picture(img_path, width=Mm(70))

                # Signatories (names/titles + signatures)
                sign_info = SIGNATORIES.get(discipline, {})
                cons_sig_path = resolve_asset(sign_info.get("Consultant_Signature"))
                cont_sig_path = resolve_asset(sign_info.get("Contractor_Signature"))
                cons_sig_img = InlineImage(tpl, cons_sig_path, width=Mm(30)) if cons_sig_path else ""
                cont_sig_img = InlineImage(tpl, cont_sig_path, width=Mm(30)) if cont_sig_path else ""

                # Context for DOCX
                context = {
                    "Site_Name": site_name or "",
                    "Date": date or "",
                    "District": district or "",
                    "Work": work or "",
                    "Human_Resources": human_resources or "",
                    "Supply": supply or "",
                    "Work_Executed": work_executed or "",
                    "Comment_on_work": comment_on_work or "",
                    "Another_Work_Executed": another_work_executed or "",
                    "Comment_on_HSE": comment_on_hse or "",
                    "Consultant_Recommandation": consultant_recommandation or "",
                    "Images": images_subdoc,  # ← use subdocument, not RichText
                    "Consultant_Name": sign_info.get("Consultant_Name", ""),
                    "Consultant_Title": sign_info.get("Consultant_Title", ""),
                    "Contractor_Name": sign_info.get("Contractor_Name", ""),
                    "Contractor_Title": sign_info.get("Contractor_Title", ""),
                    "Consultant_Signature": cons_sig_img,
                    "Contractor_Signature": cont_sig_img,
                }

                tpl.render(context)

                # Filename pattern: {Site}_Day_Report_{dd.MM.YYYY}.docx
                date_for_title = format_date_title(date)
                out_name = f"{site_name}_Day_Report_{date_for_title}.docx"
                out_name = safe_filename(out_name)  # guard against illegal chars/length
                out_path = os.path.join(temp_dir, out_name)

                tpl.save(out_path)
                zipf.write(out_path, arcname=out_name)

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

# -----------------------------
# Weekly report
# -----------------------------

ACT_RE = re.compile(r'(?P<desc>[A-Za-z /&-]+)\s*(?P<qty>\d+(?:\.\d+)?)\s*(?P<unit>m|mt|nos|poles?)\b', re.I)

def activities_from_text(txt: str):
    out = []
    for m in ACT_RE.finditer(txt or ""):
        desc = m.group('desc').strip().title()
        qty = float(m.group('qty'))
        unit = m.group('unit').lower().replace('poles', 'Nos').replace('pole', 'Nos')
        unit = {'m':'mt', 'nos':'Nos', 'mt':'mt'}.get(unit, unit)
        out.append((desc, unit, qty))
    return out

def monsun_index(ts):  # 0..6
    return int(pd.to_datetime(ts).weekday())

def build_site_table(rows_this_site):
    # rows_this_site: list of daily rows for one site (your padded schema)
    agg = {}  # (desc,unit) -> [Mon..Sun]
    for r in rows_this_site:
        d = pd.to_datetime(r[0], dayfirst=True, errors='coerce'); if d is pd.NaT: continue
        dayi = monsun_index(d)
        texts = " ; ".join([(r[6] or ""), (r[8] or "")])  # Work_Executed + Another_Work_Executed
        for desc, unit, qty in activities_from_text(texts):
            key = (desc, unit)
            agg.setdefault(key, [0,0,0,0,0,0,0])[dayi] += qty
    table = []
    for (desc,unit), days in agg.items():
        table.append({
          "Description": desc, "Unit": unit,
          "Mon":days[0],"Tue":days[1],"Wed":days[2],"Thu":days[3],
          "Fri":days[4],"Sat":days[5],"Sun":days[6],
          "Total": sum(days)
        })
    # stable order: by description then unit
    table.sort(key=lambda x: (x["Description"], x["Unit"]))
    return table

def site_pictures_subdoc(tpl, uploaded_map, site, start_ymd, end_ymd):
    start = pd.to_datetime(start_ymd); end = pd.to_datetime(end_ymd)
    sub = tpl.new_subdoc()
    for (s, dstr), files in uploaded_map.items():
        if s != site: continue
        d = pd.to_datetime(dstr, dayfirst=True, errors="coerce")
        if d is pd.NaT or not (start <= d <= end): continue
        for f in files or []:
            with tempfile.NamedTemporaryFile(delete=False) as t:
                t.write(f.getbuffer()); t.flush()
                p = sub.add_paragraph(); r = p.add_run()
                r.add_picture(t.name, width=Mm(70))
    return sub

def build_weekly_context(rows, selected_sites, start_ymd, end_ymd, discipline, uploaded_map):
    start = pd.to_datetime(start_ymd); end = pd.to_datetime(end_ymd)
    week_no = int(start.isocalendar().week)
    # filter into week
    by_site = {}
    for r in rows:
        if r[1].strip() not in selected_sites: continue
        d = pd.to_datetime(r[0], dayfirst=True, errors="coerce")
        if d is pd.NaT or not (start <= d <= end): continue
        by_site.setdefault(r[1].strip(), []).append(r)

    tpl = DocxTemplate("Weekly_Report_Template.docx")

    sites_ctx, total_man, good_lines, bad_lines = [], 0, [], []
    for site, site_rows in sorted(by_site.items()):
        # table
        table = build_site_table(site_rows)
        # narrative (simple starter)
        act_lead = ", ".join({t["Description"] for t in table} or [])
        narrative = f"During the week, electrical works progressed at {site}. Main activities included {act_lead.lower()}."
        # challenges (heuristic from comments)
        challenges=[]
        for r in site_rows:
            comm = (r[7] or "") + " " + (r[10] or "")
            if any(k in comm.lower() for k in ["waiting", "damage", "approval", "lv line", "stoppage", "blocked"]):
                challenges.append({"Issue": comm.strip(), "Impact": "Schedule impact"})
        # pictures
        pics = site_pictures_subdoc(tpl, uploaded_map, site, start_ymd, end_ymd)

        # manpower sum (coerce numbers)
        site_man = sum(int(re.search(r"\d+", str(r[4]) or "")[0]) for r in site_rows if re.search(r"\d+", str(r[4]) or ""))
        total_man += site_man

        sites_ctx.append({
            "Site_Name": site,
            "Narrative": narrative,
            "Table": table,
            "Challenges": challenges[:3],
            "Pictures": pics
        })

        # collect lines for summary
        good_lines.extend([r["Description"] for r in table][:3])
        bad_lines.extend([c["Issue"] for c in challenges][:3])

    # summary text (starter you can tune)
    summary = f"This week, the {discipline.lower()} teams made progress across {len(sites_ctx)} sites, " \
              f"with key activities: {', '.join(sorted(set(good_lines)))}."
    if bad_lines:
        summary += " Delays/risks noted: " + "; ".join(sorted(set(bad_lines))) + "."

    # signatures
    sign = SIGNATORIES.get(discipline, {})
    cons_sig_path = resolve_asset(sign.get("Consultant_Signature"))
    cons_sig_img = InlineImage(tpl, cons_sig_path, width=Mm(30)) if cons_sig_path else ""

    return tpl, {
        "Week_No": f"{week_no:02d}",
        "Period_From": start.strftime("%d/%m/%Y"),
        "Period_To":   end.strftime("%d/%m/%Y"),
        "Doc_No": f"{week_no:02d}",
        "Doc_Date": pd.Timestamp.today().strftime("%d/%m/%Y"),
        "Project_Name": "Consultancy services related to Supervision of Engineering Design Supply and Installation of 15kV Switching Substations and Rehabilitation of Associated Distribution Lines in Kigali",
        "Prepared_By": SIGNATORIES.get(discipline, {}).get("Consultant_Name", ""),
        "Prepared_Signature": cons_sig_img,
        "Discipline": discipline,
        "Summary": summary,
        "Sites": sites_ctx,
        "Ongoing": [],   # you can fill from a 'Weekly_Log' sheet
        "Planned": [],   # idem
        "HSE": "Teams maintained good safety standards this week.",
        "Weekly_Images": tpl.new_subdoc(),  # or a global gallery like weekly_images_subdoc(...)
    }
