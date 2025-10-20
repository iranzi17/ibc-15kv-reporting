import pandas as pd
import streamlit as st

from sheets import (
    CACHE_FILE,
    append_rows_to_sheet,
    get_sheet_data,
    get_unique_sites_and_dates,
    load_offline_cache,
)

from report import generate_reports
from report_structuring import REPORT_HEADERS, clean_and_structure_report
from ui import render_workwatch_header
from ui_hero import render_hero


st.set_page_config(page_title="WorkWatch — Site Intelligence", layout="wide")


def _rows_to_structured_data(rows):
    """Convert raw sheet rows into dictionaries keyed by REPORT_HEADERS."""

    structured = []
    for row in rows:
        entry = {header: "" for header in REPORT_HEADERS}
        for index, header in enumerate(REPORT_HEADERS):
            if index < len(row):
                entry[header] = row[index]
        structured.append(entry)
    return structured


def _load_sheet_context():
    """Return tuple of (data_rows, sites, error) while isolating failures."""

    try:
        rows = get_sheet_data()
        data_rows = rows[1:] if rows else []
        sites, _ = get_unique_sites_and_dates(data_rows)
        return data_rows, list(sites), None
    except Exception as exc:  # pragma: no cover - user notification
        return [], [], exc


def run_app():
    """Render the Streamlit interface."""
    data_rows, sites, data_error = _load_sheet_context()

    render_hero(
        title="Smart Field Reporting for Electrical & Civil Works",
        subtitle="A modern reporting system for engineers, supervisors and consultants.",
        cta_primary="Generate Reports",
        cta_secondary="Upload Site Data",
        image_path="bg.jpg",
    )

    st.markdown('<div id="reports-section"></div>', unsafe_allow_html=True)
    render_workwatch_header()

    # Controls that were mistakenly embedded in HTML in original file:
    st.sidebar.subheader("Gallery Controls")
    img_width_mm = st.sidebar.slider(
        "Image width (mm)", min_value=50, max_value=250, value=185, step=5
    )
    img_height_mm = st.sidebar.slider(
        "Image height (mm)", min_value=50, max_value=250, value=148, step=5
    )
    st.sidebar.caption(
        "Images default to 185 mm × 148 mm each, arranged two per row with a 5 mm gap."
    )
    add_border = st.sidebar.checkbox("Add border to images", value=False)
    spacing_mm = st.sidebar.slider(
        "Gap between images (mm)", min_value=0, max_value=20, value=5, step=1
    )

    if data_error is not None:  # pragma: no cover - user notification
        st.error(f"Failed to load site data: {data_error}")
        return

    filters_container = st.container()
    with filters_container:
        discipline_column, selectors_column = st.columns((0.9, 1.8), gap="large")

        with discipline_column:
            discipline = st.radio(
                "Discipline",
                ["Civil", "Electrical"],
                key="discipline_radio",
            )

        with selectors_column:
            sites_column, dates_column = st.columns(2, gap="large")

            site_options = ["All Sites"] + sites if sites else ["All Sites"]
            default_sites = ["All Sites"] if site_options else []

            with sites_column:
                st.subheader("Select Sites")
                selected_sites_raw = st.multiselect(
                    "Choose sites:",
                    site_options,
                    default=default_sites,
                    key="sites_ms",
                )

            if "All Sites" in selected_sites_raw or not selected_sites_raw:
                selected_sites = sites.copy()
            else:
                selected_sites = selected_sites_raw

            available_dates = sorted(
                {
                    row[0].strip()
                    for row in data_rows
                    if not selected_sites or row[1].strip() in selected_sites
                }
            )

            date_options = ["All Dates"] + available_dates if available_dates else ["All Dates"]
            default_dates = ["All Dates"] if available_dates else []

            with dates_column:
                st.subheader("Select Dates")
                selected_dates_raw = st.multiselect(
                    "Choose dates:",
                    date_options,
                    default=default_dates,
                    key="dates_ms",
                )

            if "All Dates" in selected_dates_raw or not selected_dates_raw:
                selected_dates = available_dates
            else:
                selected_dates = selected_dates_raw

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

    # Filtered rows
    filtered_rows = [
        row for row in data_rows
        if row[1].strip() in selected_sites and row[0].strip() in selected_dates
    ]

    site_date_pairs = sorted({(row[1].strip(), row[0].strip()) for row in filtered_rows})

    # Preview
    st.subheader("Preview Reports to be Generated")
    df_preview = pd.DataFrame(
        filtered_rows,
        columns=REPORT_HEADERS,
    )
    st.dataframe(df_preview)

    structured_from_rows = _rows_to_structured_data(filtered_rows)

    if st.session_state.get("_structured_origin") != "manual":
        st.session_state["structured_report_data"] = structured_from_rows
        st.session_state["_structured_origin"] = "rows"


    st.markdown('<div id="upload-section"></div>', unsafe_allow_html=True)

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

    st.subheader("Contractor Report Parser")
    raw_report_text = st.text_area("Paste contractor report text")

    if st.button("Clean & Structure Report"):
        try:
            structured_report = clean_and_structure_report(raw_report_text)
        except (TypeError, ValueError) as exc:
            st.warning(f"Unable to structure report: {exc}")
        else:
            st.session_state["structured_report_data"] = structured_report
            st.session_state["_structured_origin"] = "manual"

    st.json(st.session_state.get("structured_report_data", structured_from_rows))

    if st.button("Generate Reports"):
        if not filtered_rows:
            st.warning("No data available for the selected sites and dates.")
            return
        zip_bytes = generate_reports(
            filtered_rows,
            st.session_state.get("images", {}),
            discipline,
            img_width_mm,
            img_height_mm,
            spacing_mm,
            img_per_row=2,
            add_border=add_border,
        )
        st.download_button("Download ZIP", zip_bytes, "reports.zip")
if __name__ == "__main__":
    run_app()

