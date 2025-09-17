import pandas as pd
import streamlit as st
import gspread
from google.oauth2.service_account import Credentials

from sheets import (
    CACHE_FILE,
    append_rows_to_sheet,
    get_sheet_data,
    get_unique_sites_and_dates,
    load_offline_cache,
)

from ui import render_workwatch_header, set_background
from report import generate_reports


def get_gsheet(sheet_id: str, sheet_name: str):
    """Return a gspread worksheet for the given sheet ID and worksheet name."""
    service_account_info = st.secrets["gcp_service_account"]
    credentials = Credentials.from_service_account_info(
        service_account_info,
        scopes=["https://www.googleapis.com/auth/spreadsheets"],
    )
    client = gspread.authorize(credentials)
    return client.open_by_key(sheet_id).worksheet(sheet_name)


def append_to_sheet(row_data: dict, sheet):
    """Append a dictionary of row data to the worksheet using header order."""

    headers = sheet.row_values(1)
    if not headers:
        raise ValueError("Worksheet must have a header row to append data.")

    ordered_row = [row_data.get(header, "") for header in headers]
    sheet.append_row(ordered_row)


def run_app():
    """Render the Streamlit interface."""
    set_background("bg.jpg")
    render_workwatch_header()

    # Controls that were mistakenly embedded in HTML in original file:
    st.sidebar.subheader("Gallery Controls")
    img_width_mm = st.sidebar.slider(
        "Image width (mm)", min_value=30, max_value=100, value=70, step=5
    )
    img_per_row = st.sidebar.selectbox(
        "Images per row", options=[1, 2, 3, 4], index=1
    )
    add_border = st.sidebar.checkbox("Add border to images", value=False)
    spacing_mm = st.sidebar.slider(
        "Spacing between images (mm)", min_value=0, max_value=20, value=2, step=1
    )

    # Get sheet data
    cache = load_offline_cache()
    if cache and cache.get("rows"):
        st.info(
            "Cached offline data detected. Use the button below to sync back to the Google Sheet."
        )
        if st.button("Sync cached data to Google Sheet"):
            try:
                append_rows_to_sheet(cache.get("rows", []))
                CACHE_FILE.unlink()
                st.success("Cached data synced to Google Sheet.")
                cache = None
            except Exception as e:  # pragma: no cover - user notification
                st.error(f"Sync failed: {e}")

    try:
        rows = get_sheet_data()
        sites, _ = get_unique_sites_and_dates(rows)

        col_left, col_right = st.columns([1, 2])

        with col_left:
            discipline = st.radio(
                "Discipline", ["Civil", "Electrical"], key="discipline_radio"
            )

        with col_right:
            st.header("Select Sites")
            site_choices = ["All Sites"] + sites
            selected_sites = st.multiselect(
                "Choose sites:", site_choices, default=["All Sites"], key="sites_ms"
            )
            if "All Sites" in selected_sites or not selected_sites:
                selected_sites = sites

            st.header("Select Dates")
            site_dates = sorted(
                {row[0].strip() for row in rows if row[1].strip() in selected_sites}
            )
            date_choices = ["All Dates"] + site_dates
            selected_dates = st.multiselect(
                "Choose dates:", date_choices, default=["All Dates"], key="dates_ms"
            )
            if "All Dates" in selected_dates or not selected_dates:
                selected_dates = site_dates
    except Exception as e:  # pragma: no cover - user notification
        st.error(f"Failed to load site data: {e}")
        return

    # Filtered rows
    filtered_rows = [
        row for row in rows
        if row[1].strip() in selected_sites and row[0].strip() in selected_dates
    ]

    site_date_pairs = sorted({(row[1].strip(), row[0].strip()) for row in filtered_rows})

    # Preview
    st.subheader("Preview Reports to be Generated")
    df_preview = pd.DataFrame(
        filtered_rows,
        columns=[
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
        ],
    )
    st.dataframe(df_preview)

    for site, date in site_date_pairs:
        files = st.file_uploader(
            f"Upload images for {site} - {date}",
            accept_multiple_files=True,
            type=["png", "jpg", "jpeg", "webp"],
            key=f"uploader_{site}_{date}",
        )
        if files:
            key = (site.strip(), date.strip())
            st.session_state.setdefault("images", {})[key] = [f.read() for f in files]

    if st.button("Generate Reports"):
        zip_bytes = generate_reports(
            filtered_rows,
            st.session_state.get("images", {}),
            discipline,
            img_width_mm,
            img_per_row,
            add_border,
        )
        st.download_button("Download ZIP", zip_bytes, "reports.zip")


if __name__ == "__main__":
    run_app()

