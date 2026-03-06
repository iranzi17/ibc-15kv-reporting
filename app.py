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

# ---- Background image (full page, readable) ----
def set_background(image_path: str, overlay_opacity: float = 0.55):
    """
    Minimal background setup. Remove overlays and excessive styling.
    """
    pass  # No background or overlay for a clean, professional look

# Store and retrieve the current user's role (default to Viewer)


# ---- Styled header: WorkWatch - Site Intelligence - IRANZI ----


def render_workwatch_header(
    author: str = "IRANZI",
    brand: str = "WorkWatch",
    subtitle: str = "Site Intelligence",
    logo_path: Optional[str] = None,
    tagline: str = "",
):
    """Render a compact header with optional subtitle text."""
    st.header("Site Weekly Report Generator")
    if tagline:
        st.caption(tagline)

render_workwatch_header(
    author="IRANZI",
    brand="WorkWatch",
    subtitle="Site Intelligence",
    logo_path="ibc_logo.png",  # or None to hide
    tagline="Field reports & weekly summaries",
)
# -----------------------------
# Paths & small helpers
# -----------------------------
BASE_DIR = Path(__file__).parent.resolve()

# Column index (0-based) for the "Discipline" field in sheet rows.
# Sheet structure: Date, Site_Name, District, Work, Human_Resources, Supply,
# Work_Executed, Comment_on_work, Another_Work_Executed, Comment_on_HSE,
# Consultant_Recommandation, Discipline
DISCIPLINE_COL = 11

def resolve_asset(name: Optional[str]) -> Optional[str]:
    """
    Find an asset (e.g., signature image) whether it's in ./ or ./signatures/,
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

def update_timesheet_template_by_discipline(template_path, all_rows, selected_dates, discipline):
    wb = load_workbook(template_path)
    try:
        ws = wb.active

        for date_str in selected_dates:
            try:
                day_num = int(pd.to_datetime(date_str, dayfirst=True).day)
            except:
                continue

            # Filter rows by date AND discipline
            day_rows = [
                r for r in all_rows
                if r[0] == date_str and st.session_state.get("discipline_radio") == discipline
            ]




            # Extract and merge activities
            activities = []
            for r in day_rows:
                site = r[1]
                act1 = r[6] or ""
                act2 = r[8] or ""
                combined = " / ".join(filter(None, [act1.strip(), act2.strip()]))
                if combined:
                    activities.append(f"{site}: {combined}")

            # Fill Excel row for the matching day number
            for row in range(19, 60):
                cell_value = ws[f"A{row}"].value
                if cell_value == day_num:
                    ws[f"F{row}"] = ", ".join(sites)
                    ws[f"G{row}"] = "\n".join(activities[:8]) or "Supervision of site activities"
                    break

        output = BytesIO()
        wb.save(output)
        output.seek(0)
        return output
    finally:
        wb.close()



# ========= Weekly report helpers =========

# Extract simple (Description, Unit, Quantity) from free-text like "Trench excavation 110 m"
ACT_RE = re.compile(
    r'(?P<desc>[A-Za-z /&\-\(\)]+?)\s*(?P<qty>\d+(?:\.\d+)?)\s*(?P<unit>m|mt|nos|poles?)\b',
    re.I,
)

def activities_from_text(txt: str):
    out = []
    for m in ACT_RE.finditer(txt or ""):
        desc = m.group('desc').strip().title()
        qty = float(m.group('qty'))
        unit = m.group('unit').lower()
        # Normalize units
        if unit in ("pole", "poles"):
            unit = "Nos"
        elif unit == "m":
            unit = "mt"
        else:
            unit = unit.title()
        out.append((desc, unit, qty))
    return out

def build_site_table(rows_this_site):
    """Build Mon..Sun table for one site from daily rows."""
    agg = {}  # (desc, unit) -> [Mon..Sun]
    for r in rows_this_site:
        d = pd.to_datetime(r[0], dayfirst=True, errors='coerce')
        if pd.isna(d):
            continue
        dayi = int(d.weekday())  # Mon=0..Sun=6
        # Use Work_Executed (idx 6) + Another_Work_Executed (idx 8)
        texts = " ; ".join([(r[6] or ""), (r[8] or "")])
        for desc, unit, qty in activities_from_text(texts):
            key = (desc, unit)
            agg.setdefault(key, [0,0,0,0,0,0,0])[dayi] += qty

    table = []
    for (desc, unit), days in agg.items():
        table.append({
            "Description": desc, "Unit": unit,
            "Mon": days[0], "Tue": days[1], "Wed": days[2], "Thu": days[3],
            "Fri": days[4], "Sat": days[5], "Sun": days[6],
            "Total": sum(days)
        })
    table.sort(key=lambda x: (x["Description"], x["Unit"]))
    return table

def site_pictures_subdoc(tpl, uploaded_map, site, start_ymd, end_ymd):
    """Build a subdocument with all uploaded images for a site within the week."""
    start = pd.to_datetime(start_ymd, errors="coerce"); end = pd.to_datetime(end_ymd, errors="coerce")
    sub = tpl.new_subdoc()
    for (s, dstr), files in uploaded_map.items():
        if s != site:
            continue
        d = pd.to_datetime(dstr, dayfirst=True, errors="coerce")
        if pd.isna(d) or not (start <= d <= end):
            continue
        for f in files or []:
            with tempfile.NamedTemporaryFile(delete=False) as t:
                t.write(f.getbuffer()); t.flush()
                p = sub.add_paragraph(); r = p.add_run()
                r.add_picture(t.name, width=Mm(70))
    return sub

def build_weekly_context(rows, selected_sites, start_ymd, end_ymd, discipline, uploaded_map):
    """
    Returns (tpl, ctx) for Weekly_Report_Template.docx
    - rows: sheet rows (padded)
    - selected_sites: list[str]
    - start_ymd/end_ymd: 'YYYY-MM-DD'
    - discipline: 'Civil'|'Electrical'
    - uploaded_map: {(site, date_str): [UploadedFile, ...]}
    """
    start = pd.to_datetime(start_ymd)
    end = pd.to_datetime(end_ymd)
    week_no = int(start.isocalendar().week)

    # Filter rows into the week + sites
    by_site = {}
    for r in rows:
        site = r[1].strip()
        if site not in selected_sites:
            continue
        d = pd.to_datetime(r[0], dayfirst=True, errors="coerce")
        if pd.isna(d) or not (start <= d <= end):
            continue
        by_site.setdefault(site, []).append(r)

    tpl = DocxTemplate("Weekly_Report_Template.docx")

    sites_ctx = []
    all_challenges = []
    ongoing_activities = []
    planned_activities = []
    hse_notes = []
    pictures_by_site = {}

    # Helper for blockers
    def is_blocker(text):
        t = (text or "").lower()
        return any(k in t for k in ["delay", "blocked", "issue", "problem", "pending", "stoppage", "approval", "permit", "clearance"])

    # Site-specific narratives and tables
    for site, site_rows in sorted(by_site.items()):
        table = build_site_table(site_rows)
        # Build detailed narrative (customize per site)
        narrative = f"Progress at {site}: "
        if table:
            acts = [f"{t['Description']} ({t['Total']} {t['Unit']})" for t in table if t['Total'] > 0]
            narrative += ", ".join(acts) + ". "
        else:
            narrative += "No major activities recorded. "

        # Challenges/issues
        challenges = []
        for r in site_rows:
            combined = f"{r[7] or ''} {r[10] or ''}".strip()
            if combined and is_blocker(combined):
                challenges.append({"Site": site, "Issue": combined, "Impact": "Delay or risk"})
        all_challenges.extend(challenges)

        # Ongoing activities (example extraction)
        for t in table:
            if t['Total'] > 0:
                ongoing_activities.append({
                    "Activity": t['Description'],
                    "Location": site,
                    "Status": f"{t['Total']} {t['Unit']} completed",
                    "Remarks": "Ongoing"
                })

        # Planned activities (example: next steps)
        planned_activities.append({
            "Site": site,
            "Planned Activity": f"Continue {', '.join([t['Description'] for t in table])}",
            "Remarks": "Coordinate for next phase"
        })

        # HSE notes (example extraction)
        for r in site_rows:
            hse_comment = r[9] or ""
            if hse_comment:
                hse_notes.append(f"{site}: {hse_comment}")

        # Pictures
        pics = site_pictures_subdoc(tpl, uploaded_map, site, start_ymd, end_ymd)
        pictures_by_site[site] = pics

        sites_ctx.append({
            "Site_Name": site,
            "Narrative": narrative,
            "Table": table,
            "Challenges": challenges,
            "Pictures": pics
        })

    # Summary paragraph
    summary = f"This week, {discipline.lower()} works progressed across all active sites. "
    if sites_ctx:
        summary += "Notable advancements: " + ", ".join([s['Narrative'] for s in sites_ctx])

    # Signatures
    sign = SIGNATORIES.get(discipline, {})
    cons_sig_path = resolve_asset(sign.get("Consultant_Signature"))
    cons_sig_img = InlineImage(tpl, cons_sig_path, width=Mm(30)) if cons_sig_path else ""

    ctx = {
        "Week_No": f"{week_no:02d}",
        "Period_From": start.strftime("%d/%m/%Y"),
        "Period_To": end.strftime("%d/%m/%Y"),
        "Doc_No": f"{week_no+1:02d}",
        "Doc_Date": pd.Timestamp.today().strftime("%d/%m/%Y"),
        "Project_Name": "Consultancy services related to Supervision of Engineering Design Supply and Installation of 15kV Switching Substations and Rehabilitation of Associated Distribution Lines in Kigali",
        "Prepared_By": sign.get("Consultant_Name", ""),
        "Prepared_Signature": cons_sig_img,
        "Discipline": discipline,
        "Summary": summary,
        "Sites": sites_ctx,
        "Challenges": all_challenges,
        "Ongoing": ongoing_activities,
        "Planned": planned_activities,
        "HSE": "\n".join(hse_notes) if hse_notes else "Safety compliance remained high, with PPE usage observed on all sites. No accidents were reported.",
        "Weekly_Images": pictures_by_site,
    }
    return tpl, ctx
# ========= end weekly helpers =========

    
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

SHEET_ID = "1t6Bmm3YN7mAovNM3iT7oMGeXG3giDONSejJ9gUbUeCI"
SHEET_NAME = "Reports"
TEMPLATE_PATH = "Site_Daily_report_Template_Date.docx"
CACHE_FILE = BASE_DIR / "offline_cache.json"

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

REPORT_COLUMNS = [
    "Date",
    "Site_Name",
    "District",
    "Work",
    "Human_Resources",
    "Supply",
    "Work_Executed",
    "Comment_on_work",
    "Another_Work_Executed",
    "Comment_on_HSE",
    "Consultant_Recommandation",
]

CABIN_ACTIVITY_PATTERN = re.compile(r"\bcabin\b", re.IGNORECASE)
CABIN_CONTRACTOR_OVERRIDE = {
    "Contractor_Name": "Rutarindwa Olivier",
    "Contractor_Title": "Civil Engineer",
    "Contractor_Signature": "rutalindwa_olivier",
}


def normalize_text_cell(value: object) -> str:
    if value is None:
        return ""
    if isinstance(value, float) and pd.isna(value):
        return ""
    return str(value).strip()


def row_mentions_cabin(*fields: object) -> bool:
    return any(CABIN_ACTIVITY_PATTERN.search(normalize_text_cell(field)) for field in fields)


def signatories_for_daily_row(
    discipline: str,
    work: str,
    work_executed: str,
    another_work_executed: str,
    comment_on_work: str,
) -> dict[str, str]:
    sign_info = dict(SIGNATORIES.get(discipline, {}))
    if row_mentions_cabin(work, work_executed, another_work_executed, comment_on_work):
        sign_info.update(CABIN_CONTRACTOR_OVERRIDE)
    return sign_info


def dataframe_rows_to_report_rows(df: pd.DataFrame) -> list[list[str]]:
    if df.empty:
        return []
    normalized = df.reindex(columns=REPORT_COLUMNS).fillna("")
    return [[normalize_text_cell(cell) for cell in row] for row in normalized.values.tolist()]

# -----------------------------
# Google Sheets & offline cache
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
        range=f"{SHEET_NAME}!A:K",  # open-ended range
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
# UI
# -----------------------------
st.title("Site Daily Report Generator (Pro)")

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

# (site, date) pairs for upload mapping
site_date_pairs = sorted({(row[1].strip(), row[0].strip()) for row in filtered_rows})

# Upload mappings
uploaded_image_mapping: dict[tuple[str, str], list] = {}
image_width_mm_mapping: dict[tuple[str, str], int] = {}

# Preview
st.subheader("Preview Reports to be Generated")
show_dashboard = st.checkbox("Show Dashboard")
df_preview = pd.DataFrame(
    [(row + [""] * len(REPORT_COLUMNS))[: len(REPORT_COLUMNS)] for row in filtered_rows],
    columns=REPORT_COLUMNS,
)
st.dataframe(df_preview, use_container_width=True, hide_index=True)

st.subheader("Review Before Download")
st.caption(
    "Edit report text before generation. Date and site are locked so uploaded images stay linked."
)
review_df = st.data_editor(
    df_preview,
    use_container_width=True,
    hide_index=True,
    disabled=["Date", "Site_Name"],
    key="daily_report_review_editor",
)
review_rows = dataframe_rows_to_report_rows(review_df)

cabin_report_count = sum(
    1
    for row in review_rows
    if row_mentions_cabin(row[3], row[6], row[8], row[7])
)
if cabin_report_count:
    st.info(
        f"{cabin_report_count} report(s) mention cabin activities. "
        "The contractor representative will be set to Rutarindwa Olivier (Civil Engineer)."
    )

if show_dashboard:
    dash_df = review_df.copy()
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

            image_width_mm = st.slider(
                "Image width in report (mm)",
                min_value=40,
                max_value=140,
                value=70,
                key=f"img_width_mm_{site_name}_{date}",
            )
            image_width_mm_mapping[(site_name, date)] = image_width_mm

            if imgs:
                st.image(
                    [img.getvalue() for img in imgs],
                    caption=[img.name for img in imgs],
                    width=240,
                )
else:
    st.info("No site/date pairs in current filter. Adjust filters to upload images.")


# -----------------------------
# Generate reports
# -----------------------------
if st.button("Generate & Download All Reports"):
    if not review_rows:
        st.warning("No rows selected for generation.")
    else:
        with st.spinner("Generating reports, please wait..."):
            temp_dir = tempfile.mkdtemp()
            zip_buffer = tempfile.NamedTemporaryFile(delete=False, suffix=".zip")

            with zipfile.ZipFile(zip_buffer, "w") as zipf:
                for row in review_rows:
                    (
                        date,
                        site_name,
                        district,
                        work,
                        human_resources,
                        supply,
                        work_executed,
                        comment_on_work,
                        another_work_executed,
                        comment_on_hse,
                        consultant_recommandation,
                    ) = (row + [""] * len(REPORT_COLUMNS))[: len(REPORT_COLUMNS)]

                    tpl = DocxTemplate(TEMPLATE_PATH)

                    # Images from uploader -> put each photo in a subdocument paragraph
                    image_files = uploaded_image_mapping.get((site_name, date), []) or []
                    image_width_mm = image_width_mm_mapping.get((site_name, date), 70)
                    images_subdoc = tpl.new_subdoc()
                    for img_file in image_files:
                        img_path = os.path.join(temp_dir, img_file.name)
                        with open(img_path, "wb") as f:
                            f.write(img_file.getbuffer())
                        p = images_subdoc.add_paragraph()
                        r = p.add_run()
                        r.add_picture(img_path, width=Mm(image_width_mm))

                    # Signatories (names/titles + signatures)
                    sign_info = signatories_for_daily_row(
                        discipline,
                        work,
                        work_executed,
                        another_work_executed,
                        comment_on_work,
                    )
                    cons_sig_path = resolve_asset(sign_info.get("Consultant_Signature"))
                    cont_sig_path = resolve_asset(sign_info.get("Contractor_Signature"))
                    cons_sig_img = (
                        InlineImage(tpl, cons_sig_path, width=Mm(30)) if cons_sig_path else ""
                    )
                    cont_sig_img = (
                        InlineImage(tpl, cont_sig_path, width=Mm(30)) if cont_sig_path else ""
                    )

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
                        "Images": images_subdoc,
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
                    out_name = safe_filename(out_name)
                    out_path = os.path.join(temp_dir, out_name)

                    tpl.save(out_path)
                    zipf.write(out_path, arcname=out_name)

            zip_buffer.flush()
            zip_buffer.seek(0)
            st.download_button(
                "Download ZIP",
                data=zip_buffer.read(),
                file_name="daily_reports.zip",
                mime="application/zip",
            )
st.info("**Tip:** If you don't upload images, reports will still be generated with all your data.")
st.caption("Made for efficient, multi-site daily reporting. Feedback & customizations welcome!")

# -----------------------------
# Weekly report
# -----------------------------
# Determine the date range for the weekly report
selected_dt = pd.to_datetime(selected_dates, dayfirst=True, errors="coerce")
start_ymd = selected_dt.min().strftime("%Y-%m-%d")
end_ymd = selected_dt.max().strftime("%Y-%m-%d")

# Build context and template for the weekly report
tpl, ctx = build_weekly_context(
    rows,
    selected_sites,
    start_ymd,
    end_ymd,
    discipline,
    uploaded_image_mapping,
)

tpl.render(ctx)
fname = (
    f"{discipline}_Weekly_Report_Week_{ctx['Week_No']}"
    f"_{ctx['Period_From'].replace('/','.')}_{ctx['Period_To'].replace('/','.')}.docx"
)
tmp = tempfile.NamedTemporaryFile(delete=False, suffix=".docx")
tpl.save(tmp.name)
with open(tmp.name, "rb") as fh:
    st.download_button(
        "Download Weekly Report",
        data=fh.read(),
        file_name=fname,
        mime="application/vnd.openxmlformats-officedocument.wordprocessingml.document",
    )







