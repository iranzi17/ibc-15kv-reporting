import pandas as pd
import streamlit as st
import gspread

from config import SHEET_ID, SHEET_NAME

from sheets import (
    CACHE_FILE,
    append_rows_to_sheet,
    get_sheet_data,
    get_unique_sites_and_dates,
    load_offline_cache,
    get_service_account_credentials,
)

from ui import render_workwatch_header, set_background
from report import generate_reports
from chatgpt_helpers import REPORT_HEADERS, clean_and_structure_report


def get_gsheet(sheet_id: str, sheet_name: str):
    """Return a gspread worksheet for the given sheet ID and worksheet name."""
    credentials = get_service_account_credentials()
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

    st.session_state.setdefault("structured_report_data", None)

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
        data_rows = rows[1:] if rows else []
        sites, _ = get_unique_sites_and_dates(data_rows)

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
                {
                    row[0].strip()
                    for row in data_rows
                    if row[1].strip() in selected_sites
                }
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
        row for row in data_rows
        if row[1].strip() in selected_sites and row[0].strip() in selected_dates
    ]

    site_date_pairs = sorted({(row[1].strip(), row[0].strip()) for row in filtered_rows})

    st.subheader("Process Contractor Report with Hugging Face")
    raw_report_text = st.text_area(
        "Paste the contractor's raw report:",
        key="structured_raw_report_text",
        height=300,
    )
    if st.button("Clean & Structure with Hugging Face"):
        if not raw_report_text.strip():
            st.warning("Please paste the contractor report before processing.")
        else:
            try:
                structured_payload = clean_and_structure_report(raw_report_text)
            except ValueError as exc:
                st.warning(str(exc))
            except Exception as exc:  # pragma: no cover - user notification
                st.error(f"Hugging Face processing failed: {exc}")
            else:
                st.session_state["structured_report_data"] = structured_payload
                st.success("Report processed with Hugging Face.")

    # Preview
    st.subheader("Preview Reports to be Generated")
    df_preview = pd.DataFrame(
        filtered_rows,
        columns=REPORT_HEADERS,
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
            spacing_mm,
            img_per_row,
            add_border,
        )
        st.download_button("Download ZIP", zip_bytes, "reports.zip")

        structured_rows = [
            dict(
                zip(
                    REPORT_HEADERS,
                    (row + [""] * len(REPORT_HEADERS))[: len(REPORT_HEADERS)],
                )
            )
            for row in filtered_rows
        ]
        if structured_rows:
            st.session_state["structured_report_data"] = (
                structured_rows[0]
                if len(structured_rows) == 1
                else structured_rows
            )
        else:
            st.session_state["structured_report_data"] = None

    structured_report = st.session_state.get("structured_report_data")
    if structured_report is not None:
        st.subheader("Generated Report JSON")
        st.json(structured_report)
        if st.button("Send to Google Sheet"):
            try:
                worksheet = get_gsheet(SHEET_ID, SHEET_NAME)
                rows_to_append = (
                    structured_report
                    if isinstance(structured_report, list)
                    else [structured_report]
                )
                for row_payload in rows_to_append:
                    if not isinstance(row_payload, dict):
                        raise ValueError("Report rows must be dictionaries.")
                    append_to_sheet(row_payload, worksheet)
                st.success("✅ Report saved to Google Sheet!")
            except Exception as e:  # pragma: no cover - user notification
                st.error(f"Failed to save report: {e}")


if __name__ == "__main__":
    run_app()

