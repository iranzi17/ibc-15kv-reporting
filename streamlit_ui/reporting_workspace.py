from __future__ import annotations

from contextlib import nullcontext

import pandas as pd
import streamlit as st

from core.session_state import AI_IMAGE_CAPTIONS_KEY
from report import generate_reports
from report_structuring import REPORT_HEADERS
from services.converter_service import normalize_structured_rows
from services.media_service import generate_ai_photo_captions_for_reports
from services.openai_client import default_openai_model, load_openai_api_key, openai_sdk_ready
from sheets import CACHE_FILE, append_rows_to_sheet, get_sheet_data, get_unique_sites_and_dates, load_offline_cache
from streamlit_ui.helpers import (
    safe_caption,
    safe_columns,
    safe_data_editor,
    safe_image,
    safe_markdown,
    safe_rerun,
    safe_spinner,
)
from streamlit_ui.layout import render_kpi_strip, render_note, render_section_header, render_subsection


def load_sheet_context(*, get_sheet_data_fn=get_sheet_data, get_unique_sites_and_dates_fn=get_unique_sites_and_dates):
    """Return (data_rows, sites, error) while isolating failures."""
    try:
        rows = get_sheet_data_fn()
        data_rows = rows[1:] if rows else []
        sites, _ = get_unique_sites_and_dates_fn(data_rows)
        return data_rows, list(sites), None
    except Exception as exc:  # pragma: no cover - user notification
        return [], [], exc


def rows_to_structured_data(rows: list[list[str]]) -> list[dict[str, str]]:
    structured = []
    header_count = len(REPORT_HEADERS)
    for row in rows:
        padded = (row + [""] * header_count)[:header_count]
        structured.append({header: value for header, value in zip(REPORT_HEADERS, padded)})
    return structured


def normalized_review_rows(df: pd.DataFrame) -> list[list[str]]:
    if df is None or df.empty:
        return []
    normalized = df.reindex(columns=REPORT_HEADERS).fillna("")
    return [[str(cell).strip() for cell in row] for row in normalized.values.tolist()]


def generate_reports_with_gallery_options(
    review_rows: list[list[str]],
    images: dict,
    discipline: str,
    img_width_mm: int,
    img_height_mm: int,
    spacing_mm: int,
    *,
    add_border: bool,
    show_photo_placeholders: bool,
    image_caption_mapping: dict | None = None,
    generate_reports_fn=generate_reports,
):
    """Call report generation with backwards-compatible gallery options."""
    base_args = (
        review_rows,
        images,
        discipline,
        img_width_mm,
        img_height_mm,
        spacing_mm,
    )
    base_kwargs = {
        "img_per_row": 2,
        "add_border": add_border,
    }
    try:
        return generate_reports_fn(
            *base_args,
            **base_kwargs,
            show_photo_placeholders=show_photo_placeholders,
            image_caption_mapping=image_caption_mapping,
        )
    except TypeError as exc:
        if "show_photo_placeholders" not in str(exc) and "image_caption_mapping" not in str(exc):
            raise
        return generate_reports_fn(*base_args, **base_kwargs)


def fallback_caption_mapping_for_images(image_mapping: dict) -> dict[tuple[str, str], list[str]]:
    """Return a safe caption fallback that preserves image ordering."""
    fallback: dict[tuple[str, str], list[str]] = {}
    for key, images in (image_mapping or {}).items():
        if not isinstance(key, tuple) or len(key) != 2:
            continue
        site = str(key[0] or "").strip()
        date = str(key[1] or "").strip()
        normalized_key = (site, date)
        image_count = len(images) if isinstance(images, list) else 0
        fallback[normalized_key] = ["" for _ in range(image_count)]
    return fallback


def render_gallery_sidebar() -> dict[str, object]:
    """Render restrained report output controls in the sidebar."""
    st.sidebar.subheader("Report Output Settings")
    img_width_mm = st.sidebar.slider("Gallery width (mm)", min_value=120, max_value=250, value=185, step=5)
    img_height_mm = st.sidebar.slider("Wide photo height (mm)", min_value=70, max_value=180, value=120, step=5)
    show_photo_placeholders = st.sidebar.checkbox("Show placeholders when photos are missing", value=False)
    auto_caption_images = st.sidebar.checkbox("Generate AI photo captions", value=True)
    add_border = st.sidebar.checkbox("Add border around gallery slots", value=False)
    spacing_mm = st.sidebar.slider("Gap between photos (mm)", min_value=0, max_value=20, value=5, step=1)
    st.sidebar.caption("Output settings affect the generated report files only.")
    return {
        "img_width_mm": img_width_mm,
        "img_height_mm": img_height_mm,
        "show_photo_placeholders": show_photo_placeholders,
        "auto_caption_images": auto_caption_images,
        "add_border": add_border,
        "spacing_mm": spacing_mm,
    }


def render_reporting_workspace(
    *,
    record_runtime_issue,
    active_guidance_text,
    get_sheet_data_fn=get_sheet_data,
    get_unique_sites_and_dates_fn=get_unique_sites_and_dates,
    load_offline_cache_fn=load_offline_cache,
    append_rows_to_sheet_fn=append_rows_to_sheet,
    generate_reports_fn=generate_reports,
) -> None:
    """Render the main reporting workflow as the primary product path."""
    render_section_header(
        "1. Reporting Workspace",
        "Review daily rows from Google Sheets, attach site photos, and generate final report files.",
    )

    data_rows, sites, data_error = load_sheet_context(
        get_sheet_data_fn=get_sheet_data_fn,
        get_unique_sites_and_dates_fn=get_unique_sites_and_dates_fn,
    )
    if data_error is not None:  # pragma: no cover - user notification
        st.error(f"Failed to load site data: {data_error}")
        record_runtime_issue("sheet_data", "Failed to load site data.", details=str(data_error))
        return

    gallery_settings = render_gallery_sidebar()

    cache = load_offline_cache_fn()
    if cache and cache.get("rows"):
        render_note("Cached offline data is waiting to be synced back to Google Sheets.")
        if st.button("Sync cached data to Google Sheet"):
            try:
                append_rows_to_sheet_fn(cache.get("rows", []))
                CACHE_FILE.unlink()
                st.success("Cached data synced to Google Sheet.")
            except Exception as exc:  # pragma: no cover - user notification
                st.error(f"Sync failed: {exc}")
                record_runtime_issue("sheet_sync", "Failed to sync cached data to Google Sheet.", details=str(exc))

    render_subsection("Filters", "Select the reporting discipline, sites, and dates before review.")
    discipline_column, selectors_column = safe_columns((0.9, 1.8), gap="large")
    with discipline_column:
        discipline = st.radio("Discipline", ["Civil", "Electrical"], key="discipline_radio")
    with selectors_column:
        sites_column, dates_column = safe_columns(2, gap="large")
        site_options = ["All Sites"] + sites if sites else ["All Sites"]
        with sites_column:
            selected_sites_raw = st.multiselect("Sites", site_options, default=["All Sites"], key="sites_ms")
        selected_sites = sites.copy() if "All Sites" in selected_sites_raw or not selected_sites_raw else selected_sites_raw

        available_dates = sorted({row[0].strip() for row in data_rows if not selected_sites or row[1].strip() in selected_sites})
        date_options = ["All Dates"] + available_dates if available_dates else ["All Dates"]
        with dates_column:
            selected_dates_raw = st.multiselect("Dates", date_options, default=["All Dates"], key="dates_ms")
        selected_dates = available_dates if "All Dates" in selected_dates_raw or not selected_dates_raw else selected_dates_raw

    filtered_rows = [row for row in data_rows if row[1].strip() in selected_sites and row[0].strip() in selected_dates]
    site_date_pairs = sorted({(row[1].strip(), row[0].strip()) for row in filtered_rows})
    render_kpi_strip(
        [
            ("Rows in scope", len(filtered_rows)),
            ("Sites", len({row[1].strip() for row in filtered_rows})),
            ("Site/date sets", len(site_date_pairs)),
        ]
    )

    render_subsection("Review Table", "Edit report content before generation. Date and Site_Name remain locked to preserve file mapping.")
    df_preview = pd.DataFrame(filtered_rows, columns=REPORT_HEADERS)
    st.dataframe(df_preview, width="stretch")
    safe_caption("Locked fields in the editor: Date, Site_Name.")
    review_df = safe_data_editor(
        df_preview,
        width="stretch",
        hide_index=True,
        disabled=["Date", "Site_Name"],
        key="review_editor",
    )
    review_rows = normalized_review_rows(review_df) or [(row + [""] * len(REPORT_HEADERS))[: len(REPORT_HEADERS)] for row in filtered_rows]

    structured_from_rows = rows_to_structured_data(review_rows)
    if st.session_state.get("_structured_origin") != "manual":
        st.session_state["structured_report_data"] = structured_from_rows
        st.session_state["_structured_origin"] = "rows"

    render_subsection("Site Photo Uploads", "Attach photos by site and date. Existing AI captions remain visible when available.")
    if not site_date_pairs:
        safe_caption("No filtered rows are available for photo attachment.")
    for site, date in site_date_pairs:
        with st.expander(f"{site} | {date}", expanded=False):
            files = st.file_uploader(
                f"Upload images for {site} - {date}",
                accept_multiple_files=True,
                type=["png", "jpg", "jpeg", "webp"],
                key=f"uploader_{site}_{date}",
            )
            if files:
                key = (site.strip(), date.strip())
                st.session_state.setdefault("images", {})[key] = [f.read() for f in files]
            image_group = (st.session_state.get("images", {}) or {}).get((site.strip(), date.strip()), [])
            if image_group:
                safe_image(image_group, width=220)
            cached_captions = (st.session_state.get(AI_IMAGE_CAPTIONS_KEY, {}) or {}).get(f"{site.strip()}|{date.strip()}", {})
            if isinstance(cached_captions, dict):
                captions = cached_captions.get("captions", [])
                if isinstance(captions, list) and captions:
                    safe_caption("AI captions: " + " | ".join(str(caption or "").strip() for caption in captions))

    render_subsection("Report Generation", "Generate the final ZIP after review and photo checks are complete.")
    if st.button("Generate Reports"):
        if not review_rows:
            st.warning("No data is available for the selected sites and dates.")
            return

        try:
            image_mapping = st.session_state.get("images", {})
            image_caption_mapping = None
            if gallery_settings["auto_caption_images"] and image_mapping:
                api_key = load_openai_api_key()
                sdk_ready, sdk_error = openai_sdk_ready()
                if api_key and sdk_ready:
                    try:
                        with safe_spinner("Generating AI photo captions..."):
                            image_caption_mapping = generate_ai_photo_captions_for_reports(
                                review_rows,
                                image_mapping,
                                api_key=api_key,
                                model=default_openai_model(),
                                discipline=discipline,
                                persistent_guidance=active_guidance_text("captions", "converter"),
                            )
                    except Exception as caption_error:
                        image_caption_mapping = fallback_caption_mapping_for_images(image_mapping)
                        st.warning("AI photo captions failed and were skipped. Report export will continue.")
                        record_runtime_issue(
                            "photo_captioning",
                            "AI photo captions failed; report export continued with fallback captions.",
                            details=str(caption_error),
                        )
                elif not sdk_ready:
                    st.warning(f"Photo captions skipped because the OpenAI SDK is unavailable. {sdk_error}")
                else:
                    st.warning("Photo captions skipped because no OpenAI API key is configured.")

            zip_bytes = generate_reports_with_gallery_options(
                review_rows,
                image_mapping,
                discipline,
                int(gallery_settings["img_width_mm"]),
                int(gallery_settings["img_height_mm"]),
                int(gallery_settings["spacing_mm"]),
                add_border=bool(gallery_settings["add_border"]),
                show_photo_placeholders=bool(gallery_settings["show_photo_placeholders"]),
                image_caption_mapping=image_caption_mapping,
                generate_reports_fn=generate_reports_fn,
            )
        except Exception as exc:
            st.error(f"Failed to generate reports: {exc}")
            record_runtime_issue("report_generation", "Report generation failed.", details=str(exc))
        else:
            st.download_button("Download report ZIP", zip_bytes, "reports.zip")

    st.session_state["structured_report_data"] = normalize_structured_rows(rows_to_structured_data(review_rows))
    safe_markdown("---")
