import pandas as pd
import streamlit as st

from ui import render_workwatch_header, set_background
from sheets import (
    append_rows_to_sheet,
    get_sheet_data,
    get_unique_sites_and_dates,
    load_offline_cache,
    save_offline_cache,
)
from report import generate_reports, safe_filename

st.title("📑 Site Daily Report Generator (Pro)")

role = st.session_state.setdefault("user_role", "Viewer")
if role == "Manager":
    st.sidebar.button("Admin Settings", icon="⚙️")

overlay = st.sidebar.slider("🖼️ Background overlay", 0.0, 1.0, 0.55, 0.05)
set_background("bg.jpg", overlay)

render_workwatch_header(
    author="IRANZI",
    brand="WorkWatch",
    subtitle="Site Intelligence",
    logo_path="ibc_logo.png",
    tagline="Field reports & weekly summaries",
)

st.sidebar.subheader("Gallery Controls")
img_width_mm = st.sidebar.slider("Image width (mm)", min_value=30, max_value=100, value=70, step=5)
img_per_row = st.sidebar.selectbox("Images per row", options=[1, 2, 3, 4], index=1)
add_border = st.sidebar.checkbox("Add border to images", value=False)
spacing_mm = st.sidebar.slider("Spacing between images (mm)", min_value=0, max_value=20, value=2, step=1)

try:
    rows = get_sheet_data()
except Exception:
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

filtered_rows = [
    row for row in rows
    if row[1].strip() in selected_sites and row[0].strip() in selected_dates
]
site_date_pairs = sorted({(row[1].strip(), row[0].strip()) for row in filtered_rows})

uploaded_image_mapping: dict[tuple[str, str], list] = {}

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

show_dashboard = st.checkbox("Show Dashboard")
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

st.subheader("Gallery Preview & Customization")
for site_name, date in site_date_pairs:
    image_files = uploaded_image_mapping.get((site_name, date), []) or []
    if image_files:
        st.markdown(f"**Gallery for {site_name} ({date})**")
        cols = st.columns(img_per_row)
        for idx, img_file in enumerate(image_files):
            with cols[idx % img_per_row]:
                st.image(img_file, width=200)
                if add_border:
                    st.markdown(
                        "<div style='border:1px solid #888; margin-bottom:5px;'></div>",
                        unsafe_allow_html=True,
                    )

if site_date_pairs:
    for site_name, date in site_date_pairs:
        with st.expander(f"Upload Images for {site_name} ({date})"):
            imgs = st.file_uploader(
                f"Images for {site_name} ({date})",
                accept_multiple_files=True,
                key=f"uploader_{safe_filename(site_name)}_{safe_filename(date)}",
            )
            uploaded_image_mapping[(site_name, date)] = imgs
else:
    st.info("No site/date pairs in current filter. Adjust filters to upload images.")