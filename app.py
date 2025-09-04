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
    Set a full-page background image with a subtle overlay for readability.
    overlay_opacity: 0.0 (no overlay) → 1.0 (solid)
    """
    # safety clamp
    overlay_opacity = max(0.0, min(1.0, overlay_opacity))

    path = Path(__file__).parent / image_path
    with open(path, "rb") as f:
        encoded = base64.b64encode(f.read()).decode()

    # white overlay for light UI; switch to rgba(0,0,0,OPACITY) for a dark overlay
    st.markdown(
        f"""
        <style>
        /* Background (image + white overlay) */
        [data-testid="stAppViewContainer"] {{
            background-image:
                linear-gradient(rgba(255,255,255,{overlay_opacity}),
                                rgba(255,255,255,{overlay_opacity})),
                url("data:image/jpg;base64,{encoded}");
            background-size: cover;
            background-position: center center;
            background-attachment: fixed;
        }}

        /* Make Streamlit header transparent so bg is visible */
        [data-testid="stHeader"] {{
            background: rgba(0,0,0,0);
        }}

        /* Content cards for readability */
        .block-container {{
            background: rgba(255,255,255,0.85);
            border-radius: 14px;
            padding: 1.2rem 2rem;
            box-shadow: 0 4px 20px rgba(0,0,0,0.08);
            backdrop-filter: blur(2px);
        }}

        /* Sidebar as a softer card */
        [data-testid="stSidebar"] > div:first-child {{
            background: rgba(255,255,255,0.75);
            border-radius: 12px;
            margin: 0.5rem;
            padding: 0.5rem;
            backdrop-filter: blur(2px);
        }}

        /* Buttons look better on photos */
        .stButton>button {{
            box-shadow: 0 2px 8px rgba(0,0,0,0.12);
        }}

        /* Mobile tweaks */
        @media (max-width: 768px) {{
          .block-container {{ background: rgba(255,255,255,0.92); }}
        }}
        </style>
        """,
        unsafe_allow_html=True,
    )

# Store and retrieve the current user's role (default to Viewer)
role = st.session_state.setdefault("user_role", "Viewer")

# Show manager-only controls
if role == "Manager":
    st.sidebar.button("Admin Settings", icon="⚙️")

overlay = st.sidebar.slider("🖼️ Background overlay", 0.0, 1.0, 0.55, 0.05)
set_background("bg.jpg", overlay)

# ---- Styled header: WorkWatch — Site Intelligence · IRANZI ----

def render_workwatch_header(
    author: str = "IRANZI",
    brand: str = "WorkWatch",
    subtitle: str = "Site Intelligence",
    logo_path: str | None = "ibc_logo.png",
    tagline: str | None = "Field reports & weekly summaries"
):
    # embed logo if available
    logo_html = ""
    if logo_path:
        p = Path(__file__).parent / logo_path
        if p.exists():
            encoded = base64.b64encode(p.read_bytes()).decode()
            logo_html = f'<img class="ww-logo" src="data:image/png;base64,{encoded}" alt="logo"/>'

    # optional discipline suffix (from your sidebar radio)
    discipline = st.session_state.get("discipline_radio")
    suffix = f' <span class="ww-suffix">— {discipline}</span>' if discipline else ""

    st.markdown(
        f"""
        <style>
        .ww-wrap {{
          display:flex; align-items:center; gap:14px; margin: .25rem 0 1rem 0;
        }}
        .ww-logo {{
          height: 46px; width:auto; border-radius:8px; box-shadow:0 2px 8px rgba(0,0,0,.12);
        }}
        .ww-title {{
          font-size: clamp(28px, 4vw, 44px);
          line-height: 1.05;
          font-weight: 800;
          margin: 0;
        }}
        .ww-brand {{
          background: linear-gradient(90deg,#111,#5a5a5a 60%,#111);
          -webkit-background-clip: text;
          background-clip: text;
          color: transparent;
        }}
        .ww-sub {{ opacity:.85; font-weight:700; }}
        .ww-dot {{ opacity:.6; font-weight:600; padding:0 .2rem; }}
        .ww-author {{ font-weight:500; opacity:.8; }}
        .ww-suffix {{ font-weight:500; opacity:.65; }}
        .ww-tagline {{ margin-top:.25rem; opacity:.75; font-size:0.95rem; }}
        </style>

        <div class="ww-wrap">
          {logo_html}
          <div>
            <div class="ww-title">
              ⚡ <span class="ww-brand">{brand}</span> — <span class="ww-sub">{subtitle}</span>
              <span class="ww-dot">·</span><span class="ww-author">{author}</span>{suffix}
            </div>
            {f'<div class="ww-tagline">{tagline}</div>' if tagline else ''}
          </div>
        </div>
        """,
        unsafe_allow_html=True,
    )

render_workwatch_header(
    author="IRANZI",
    brand="WorkWatch",
    subtitle="Site Intelligence",
    logo_path="ibc_logo.png",          # or None to hide
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




    tpl = DocxTemplate("Weekly_Report_Template.docx")

    sites_ctx = []
    total_man = 0
    good_lines, bad_lines = [], []

    # very light keyword heuristics for summary
    def is_blocker(text):
        t = (text or "").lower()
        return any(k in t for k in ["delay", "blocked", "issue", "problem", "pending", "stoppage", "approval"])

    for site, site_rows in sorted(by_site.items()):
        # table Mon..Sun
        table = build_site_table(site_rows)

        # quick site narrative
        act_lead = ", ".join({t["Description"] for t in table} or [])
        narrative = f"During the week, activities at {site} included {act_lead.lower()}."

        # simple challenges pulled from comments/recommendations
        challenges = []
        for r in site_rows:
            combined = f"{r[7] or ''} {r[10] or ''}".strip()  # Comment_on_work + Consultant_Recommandation
            if combined and is_blocker(combined):
                challenges.append({"Issue": combined, "Impact": "Schedule impact"})

        # pictures
        pics = site_pictures_subdoc(tpl, uploaded_map, site, start_ymd, end_ymd)

        # manpower sum from Human_Resources column (idx 4), best-effort integer extraction
        site_man = 0
        for r in site_rows:
            m = re.search(r"\d+", str(r[4]) or "")
            if m:
                site_man += int(m.group())
        total_man += site_man

        sites_ctx.append({
            "Site_Name": site,
            "Narrative": narrative,
            "Table": table,
            "Challenges": challenges[:3],
            "Pictures": pics
        })

        good_lines.extend([t["Description"] for t in table][:3])
        bad_lines.extend([c["Issue"] for c in challenges][:3])

    # summary paragraph
    summary = f"This week, the {discipline.lower()} teams progressed across {len(sites_ctx)} site(s)."
    if good_lines:
        summary += " Key activities: " + ", ".join(sorted(set(good_lines))) + "."
    if bad_lines:
        summary += " Risks/Delays noted: " + "; ".join(sorted(set(bad_lines))) + "."

    # signatures
    sign = SIGNATORIES.get(discipline, {})
    cons_sig_path = resolve_asset(sign.get("Consultant_Signature"))
    cons_sig_img = InlineImage(tpl, cons_sig_path, width=Mm(30)) if cons_sig_path else ""

    ctx = {
        "Week_No": f"{week_no:02d}",
        "Period_From": start.strftime("%d/%m/%Y"),
        "Period_To":   end.strftime("%d/%m/%Y"),
        "Doc_No": f"{week_no:02d}",
        "Doc_Date": pd.Timestamp.today().strftime("%d/%m/%Y"),
        "Project_Name": "Consultancy services related to Supervision of Engineering Design Supply and Installation of 15kV Switching Substations and Rehabilitation of Associated Distribution Lines in Kigali",
        "Prepared_By": sign.get("Consultant_Name", ""),
        "Prepared_Signature": cons_sig_img,
        "Discipline": discipline,
        "Summary": summary,
        "Sites": sites_ctx,
        "Ongoing": [],   # fill from a 'Weekly_Log' sheet if you add one
        "Planned": [],   # fill from a 'Weekly_Log' sheet if you add one
        "HSE": "Teams maintained good safety standards this week.",
        "Weekly_Images": tpl.new_subdoc(),  # or build a global gallery if you want
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
        "Contractor_Name": "Issac HABIMANA",
        "Contractor_Title": "Electrical Engineer",
        "Contractor_Signature": "issac_habimana",
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
st.title("📑 Site Daily Report Generator (Pro)")

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

# Uploads mapping
uploaded_image_mapping: dict[tuple[str, str], list] = {}

# Preview
st.subheader("Preview Reports to be Generated")
show_dashboard = st.checkbox("Show Dashboard")
df_preview = pd.DataFrame(
    filtered_rows,
    columns=[
        "Date", "Site_Name", "District", "Work", "Human_Resources", "Supply",
        "Work_Executed", "Comment_on_work", "Another_Work_Executed",
        "Comment_on_HSE", "Consultant_Recommandation",
    ],
)
st.dataframe(df_preview, use_container_width=True, hide_index=True)

if show_dashboard:
    dash_df = df_preview.copy()
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
# Determine the date range for the weekly report
selected_dt = pd.to_datetime(selected_dates, dayfirst=True, errors="coerce")
start_ymd = selected_dt.min().strftime("%Y-%m-%d")
end_ymd = selected_dt.max().strftime("%Y-%m-%d")

tpl, ctx = build_weekly_context(
    rows,
    selected_sites,
    start_ymd,
    end_ymd,
    discipline,
    uploaded_image_mapping,
)

# Preview box before download
with st.expander("👀 Preview Weekly Report"):
    st.write(f"**Week {ctx['Week_No']} ({ctx['Period_From']} - {ctx['Period_To']})**")
    for site in ctx.get("Sites", ctx.get("sites_ctx", [])):
        st.subheader(site.get("Site_Name", "Site"))
        st.write(site.get("Narrative", ""))
        # Try to preview images if possible
        pics = site.get("Pictures")
        if pics and hasattr(pics, "_element"):
            # Try to extract image paths from the subdoc (best effort)
            for tbl in pics._element.findall(".//w:tbl", pics._element.nsmap):
                for cell in tbl.findall(".//w:tc", pics._element.nsmap):
                    for pic in cell.findall(".//a:blip", pics._element.nsmap):
                        img_path = pic.get("{http://schemas.openxmlformats.org/officeDocument/2006/relationships}embed")
                        if img_path:
                            st.image(img_path, width=120)
        st.markdown("---")


tpl.render(ctx)
fname = (
    f"{discipline}_Weekly_Report_Week_{ctx['Week_No']}"
    f"_{ctx['Period_From'].replace('/','.')}_{ctx['Period_To'].replace('/','.')}.docx"
)
tmp = tempfile.NamedTemporaryFile(delete=False, suffix=".docx")
tpl.save(tmp.name)

# Convert DOCX to PDF for preview



with open(tmp.name, "rb") as fh:
    st.download_button(
        "⬇️ Download Weekly Report",
        data=fh.read(),
        file_name=fname,
        mime="application/vnd.openxmlformats-officedocument.wordprocessingml.document",
    )

with open(tmp.name, "rb") as fh:
    st.download_button(
        "⬇️ Download Weekly Report",
        data=fh.read(),
        file_name=fname,
        mime="application/vnd.openxmlformats-officedocument.wordprocessingml.document",
    )




