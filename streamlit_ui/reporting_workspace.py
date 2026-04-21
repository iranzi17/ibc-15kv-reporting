from __future__ import annotations

import hashlib

import pandas as pd
import streamlit as st

from core.session_state import AI_IMAGE_CAPTIONS_KEY
from report import generate_reports
from report_structuring import REPORT_HEADERS
from services.converter_service import normalize_structured_rows
from services.media_service import generate_ai_photo_captions_for_reports
from services.openai_client import active_ai_provider, default_ai_model, load_ai_api_key, openai_sdk_ready, provider_label
from sheets import CACHE_FILE, append_rows_to_sheet, get_sheet_data, get_unique_sites_and_dates, load_offline_cache
from streamlit_ui.clipboard_image_paste import render_clipboard_image_paste
from streamlit_ui.helpers import (
    safe_button,
    safe_caption,
    safe_checkbox,
    safe_columns,
    safe_container,
    safe_data_editor,
    safe_expander,
    safe_file_uploader,
    safe_image,
    safe_markdown,
    safe_multiselect,
    safe_radio,
    safe_rerun,
    safe_slider,
    safe_spinner,
)
from streamlit_ui.layout import (
    render_card_header,
    render_kpi_strip,
    render_note,
    render_status_badges,
    render_workspace_topbar,
)
from streamlit_ui.news_bar import render_live_updates_shell


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


def sanitize_multiselect_state(key: str, valid_options: list[str]) -> None:
    """Remove legacy or invalid values from persisted multiselect state."""
    current = st.session_state.get(key)
    if not isinstance(current, list):
        return
    valid = {str(option or "").strip() for option in valid_options}
    cleaned = [str(value or "").strip() for value in current if str(value or "").strip() in valid]
    if cleaned != current:
        st.session_state[key] = cleaned


def selection_summary_text(selected_values: list[str], *, total_count: int, noun: str) -> str:
    if not selected_values:
        return f"{noun.title()}: All {total_count}"
    suffix = "" if len(selected_values) == 1 else "s"
    return f"{noun.title()}: {len(selected_values)} selected {noun}{suffix}"


def photo_group_statuses(image_group: list[bytes], captions: list[str]) -> list[tuple[str, str]]:
    statuses: list[tuple[str, str]] = []
    if image_group:
        statuses.append(("Ready", "success"))
        statuses.append((f"{len(image_group)} photo(s) attached", "success"))
    else:
        statuses.append(("No photos", "warning"))
    if captions:
        statuses.append(("Captions cached", "neutral"))
    return statuses


def photo_group_label(site: str, date: str, image_group: list[bytes], captions: list[str]) -> str:
    label = f"{site} | {date}"
    if image_group and captions:
        return f"{label} · Ready · Captions cached"
    if image_group:
        return f"{label} · Photos attached"
    return f"{label} · No photos"


def count_attached_photo_groups(site_date_pairs: list[tuple[str, str]], image_mapping: dict) -> int:
    attached = 0
    for site, date in site_date_pairs:
        images = (image_mapping or {}).get((site, date), [])
        if images:
            attached += 1
    return attached


def photo_group_display_label(site: str, date: str, image_group: list[bytes], captions: list[str]) -> str:
    """Return an ASCII-only upload label for photo group expanders."""
    label = f"{site} | {date}"
    if image_group and captions:
        return f"{label} - Ready - Captions cached"
    if image_group:
        return f"{label} - Photos attached"
    return f"{label} - No photos"


def append_images_to_group(normalized_key: tuple[str, str], images: list[bytes]) -> list[bytes]:
    """Append images to the current site/date group and return the group."""
    if not images:
        return (st.session_state.get("images", {}) or {}).get(normalized_key, [])
    image_store = st.session_state.setdefault("images", {})
    current_group = list(image_store.get(normalized_key, []) or [])
    current_group.extend(bytes(image) for image in images if image)
    image_store[normalized_key] = current_group
    st.session_state["images"] = image_store
    return current_group


def uploaded_file_bytes(uploaded_file: object) -> bytes:
    """Read one uploaded file without permanently advancing its stream when possible."""
    getvalue_fn = getattr(uploaded_file, "getvalue", None)
    if callable(getvalue_fn):
        return bytes(getvalue_fn() or b"")

    read_fn = getattr(uploaded_file, "read", None)
    if not callable(read_fn):
        return b""

    tell_fn = getattr(uploaded_file, "tell", None)
    seek_fn = getattr(uploaded_file, "seek", None)
    position = None
    if callable(tell_fn):
        try:
            position = tell_fn()
        except Exception:
            position = None

    data = bytes(read_fn() or b"")
    if callable(seek_fn) and position is not None:
        try:
            seek_fn(position)
        except Exception:
            pass
    return data


def uploaded_image_signature(files: list[object]) -> str:
    """Return a stable signature for uploaded image files."""
    digest = hashlib.sha256()
    for uploaded_file in files or []:
        name = str(getattr(uploaded_file, "name", "") or "").strip()
        data = uploaded_file_bytes(uploaded_file)
        digest.update(name.encode("utf-8"))
        digest.update(len(data).to_bytes(8, "big", signed=False))
        digest.update(hashlib.sha256(data).digest())
    return digest.hexdigest()


def append_new_uploaded_images(
    normalized_key: tuple[str, str],
    files: list[object],
    *,
    upload_key: str,
) -> list[bytes]:
    """Append uploaded images once per uploader change."""
    if not files:
        return (st.session_state.get("images", {}) or {}).get(normalized_key, [])

    signature = uploaded_image_signature(files)
    signature_store = st.session_state.setdefault("_image_upload_signatures", {})
    current_group = (st.session_state.get("images", {}) or {}).get(normalized_key, [])
    if signature_store.get(upload_key) == signature and current_group:
        return current_group

    image_bytes: list[bytes] = []
    for uploaded_file in files:
        data = uploaded_file_bytes(uploaded_file)
        if data:
            image_bytes.append(data)

    signature_store[upload_key] = signature
    st.session_state["_image_upload_signatures"] = signature_store
    return append_images_to_group(normalized_key, image_bytes)


def render_output_settings_panel() -> dict[str, object]:
    """Render report output settings in a low-visibility expander."""
    with safe_expander("Report output settings", expanded=False):
        render_status_badges(
            [
                ("Export-only controls", "neutral"),
                ("Gallery layout", "neutral"),
                ("Captions and placeholders", "neutral"),
            ]
        )
        dimensions_column, toggles_column = safe_columns((1.2, 1.0), gap="large")
        with dimensions_column:
            img_width_mm = safe_slider(
                "Gallery width (mm)",
                min_value=120,
                max_value=250,
                value=185,
                step=5,
            )
            img_height_mm = safe_slider(
                "Wide photo height (mm)",
                min_value=70,
                max_value=180,
                value=120,
                step=5,
            )
            spacing_mm = safe_slider(
                "Gap between photos (mm)",
                min_value=0,
                max_value=20,
                value=5,
                step=1,
            )
        with toggles_column:
            show_photo_placeholders = safe_checkbox("Show placeholders when photos are missing", value=False)
            auto_caption_images = safe_checkbox("Generate AI photo captions", value=True)
            add_border = safe_checkbox("Add border around gallery slots", value=False)
            safe_caption("These settings affect generated report files only.")
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
    render_workspace_topbar(
        "1. Reporting Workspace",
        "Review daily rows from Google Sheets, attach site photos, and generate final report files.",
        badge="Operational workspace",
        meta=["Sheet review", "Photo tracking", "DOCX / ZIP export"],
    )
    render_live_updates_shell()

    data_rows, sites, data_error = load_sheet_context(
        get_sheet_data_fn=get_sheet_data_fn,
        get_unique_sites_and_dates_fn=get_unique_sites_and_dates_fn,
    )
    if data_error is not None:  # pragma: no cover - user notification
        st.error(f"Failed to load site data: {data_error}")
        record_runtime_issue("sheet_data", "Failed to load site data.", details=str(data_error))
        return

    cache = load_offline_cache_fn()
    if cache and cache.get("rows"):
        render_note("Cached offline data is waiting to be synced back to Google Sheets.")
        if safe_button("Sync cached data to Google Sheet", type="secondary"):
            try:
                append_rows_to_sheet_fn(cache.get("rows", []))
                CACHE_FILE.unlink()
                st.success("Cached data synced to Google Sheet.")
            except Exception as exc:  # pragma: no cover - user notification
                st.error(f"Sync failed: {exc}")
                record_runtime_issue("sheet_sync", "Failed to sync cached data to Google Sheet.", details=str(exc))

    with safe_container(border=True):
        render_card_header(
            "Step 1",
            "Filter & Scope",
            "Set discipline and reporting scope without occupying the screen with default selection chips.",
            badge="Command deck",
        )
        control_columns = safe_columns((1.0, 1.45, 1.45, 0.7), gap="small")
        site_options = sites.copy()
        sanitize_multiselect_state("sites_ms", site_options)

        with control_columns[0]:
            discipline = safe_radio(
                "Discipline",
                ["Civil", "Electrical"],
                key="discipline_radio",
                horizontal=True,
            )

        with control_columns[1]:
            selected_sites_raw = safe_multiselect(
                "Sites",
                site_options,
                default=[],
                key="sites_ms",
                placeholder="All sites",
            )

        selected_sites = sites.copy() if not selected_sites_raw else list(selected_sites_raw)
        available_dates = sorted(
            {
                row[0].strip()
                for row in data_rows
                if not selected_sites or row[1].strip() in selected_sites
            }
        )
        sanitize_multiselect_state("dates_ms", available_dates)

        with control_columns[2]:
            selected_dates_raw = safe_multiselect(
                "Dates",
                available_dates,
                default=[],
                key="dates_ms",
                placeholder="All dates",
            )

        with control_columns[3]:
            reset_filters = safe_button(
                "Reset filters",
                key="reset_reporting_filters",
                type="secondary",
                use_container_width=True,
            )

        if reset_filters:
            st.session_state.pop("sites_ms", None)
            st.session_state.pop("dates_ms", None)
            selected_sites_raw = []
            selected_dates_raw = []
            selected_sites = sites.copy()
            available_dates = sorted({row[0].strip() for row in data_rows})
            safe_rerun()

        selected_dates = available_dates.copy() if not selected_dates_raw else list(selected_dates_raw)
        render_status_badges(
            [
                (f"Discipline: {discipline}", "neutral"),
                (selection_summary_text(list(selected_sites_raw), total_count=len(sites), noun="site"), "neutral"),
                (selection_summary_text(list(selected_dates_raw), total_count=len(available_dates), noun="date"), "neutral"),
            ]
        )

    filtered_rows = [row for row in data_rows if row[1].strip() in selected_sites and row[0].strip() in selected_dates]
    site_date_pairs = sorted({(row[1].strip(), row[0].strip()) for row in filtered_rows})
    image_mapping = st.session_state.get("images", {})
    attached_photo_groups = count_attached_photo_groups(site_date_pairs, image_mapping)
    missing_photo_groups = max(len(site_date_pairs) - attached_photo_groups, 0)
    render_kpi_strip(
        [
            ("Rows in scope", len(filtered_rows), "Current rows after the active scope."),
            ("Sites", len({row[1].strip() for row in filtered_rows}), "Unique sites represented in this export."),
            ("Site/date sets", len(site_date_pairs), "Distinct report groups for upload and export."),
            ("Photo groups ready", attached_photo_groups, "Site/date groups that already have attached photos."),
            ("Missing photo groups", missing_photo_groups, "Groups that still need photo attachments before export."),
        ]
    )

    with safe_container(border=True):
        render_card_header(
            "Step 2",
            "Review Data",
            "Review and edit report content before generation. Date and Site_Name remain locked to preserve file mapping.",
        )
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
        review_rows = normalized_review_rows(review_df) or [
            (row + [""] * len(REPORT_HEADERS))[: len(REPORT_HEADERS)]
            for row in filtered_rows
        ]

    structured_from_rows = rows_to_structured_data(review_rows)
    if st.session_state.get("_structured_origin") != "manual":
        st.session_state["structured_report_data"] = structured_from_rows
        st.session_state["_structured_origin"] = "rows"

    with safe_container(border=True):
        render_card_header(
            "Step 3",
            "Site Photo Uploads",
            "Attach photos by site and date. Upload status and cached AI captions stay visible per group.",
        )
        if not site_date_pairs:
            safe_caption("No filtered rows are available for photo attachment.")
        for site, date in site_date_pairs:
            normalized_key = (site.strip(), date.strip())
            image_group = (st.session_state.get("images", {}) or {}).get(normalized_key, [])
            cached_captions = (st.session_state.get(AI_IMAGE_CAPTIONS_KEY, {}) or {}).get(
                f"{normalized_key[0]}|{normalized_key[1]}",
                {},
            )
            captions = cached_captions.get("captions", []) if isinstance(cached_captions, dict) else []
            captions = captions if isinstance(captions, list) else []

            with safe_expander(
                photo_group_display_label(site.strip(), date.strip(), image_group, captions),
                expanded=False,
            ):
                render_status_badges(photo_group_statuses(image_group, captions))
                uploader_key = f"uploader_{site}_{date}"
                files = safe_file_uploader(
                    f"Upload images for {site} - {date}",
                    accept_multiple_files=True,
                    type=["png", "jpg", "jpeg", "webp"],
                    key=uploader_key,
                )
                if files:
                    image_group = append_new_uploaded_images(normalized_key, list(files), upload_key=uploader_key)
                pasted_images = render_clipboard_image_paste(
                    label=f"Paste copied images for {site} - {date}",
                    key=f"clipboard_paste_{site}_{date}",
                )
                if pasted_images:
                    image_group = append_images_to_group(normalized_key, pasted_images)
                    st.success(f"Added {len(pasted_images)} pasted image(s) to {site} - {date}.")
                if image_group:
                    safe_image(image_group, width=220)
                if captions:
                    safe_caption("AI captions: " + " | ".join(str(caption or "").strip() for caption in captions))

    with safe_container(border=True):
        render_card_header(
            "Step 4",
            "Report Output",
            "Review readiness, adjust low-frequency output settings only when needed, and generate the final report package.",
            badge="Primary action",
        )
        gallery_settings = render_output_settings_panel()
        caption_status = "AI captions on" if gallery_settings["auto_caption_images"] else "AI captions off"
        render_status_badges(
            [
                (f"{len(review_rows)} row(s) ready", "neutral"),
                (
                    f"{attached_photo_groups}/{len(site_date_pairs)} photo groups attached" if site_date_pairs else "No photo groups in scope",
                    "success" if attached_photo_groups or not site_date_pairs else "warning",
                ),
                (
                    f"{missing_photo_groups} group(s) missing photos" if missing_photo_groups else "No missing photo groups",
                    "warning" if missing_photo_groups else "success",
                ),
                (caption_status, "neutral"),
            ]
        )
        safe_caption("Reports are generated as DOCX files packaged into one ZIP using the current scope and output settings.")

        if safe_button("Generate Reports", type="primary", use_container_width=True):
            if not review_rows:
                st.warning("No data is available for the selected sites and dates.")
                return

            try:
                image_mapping = st.session_state.get("images", {})
                image_caption_mapping = None
                if gallery_settings["auto_caption_images"] and image_mapping:
                    active_provider = active_ai_provider()
                    provider_name = provider_label(active_provider)
                    api_key = load_ai_api_key(active_provider)
                    sdk_ready, sdk_error = openai_sdk_ready()
                    if api_key and sdk_ready:
                        try:
                            with safe_spinner(f"Generating AI photo captions with {provider_name}..."):
                                image_caption_mapping = generate_ai_photo_captions_for_reports(
                                    review_rows,
                                    image_mapping,
                                    api_key=api_key,
                                    model=default_ai_model(active_provider),
                                    discipline=discipline,
                                    persistent_guidance=active_guidance_text("captions", "converter"),
                                    provider=active_provider,
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
                        st.warning(f"Photo captions skipped because the OpenAI-compatible SDK is unavailable. {sdk_error}")
                    else:
                        st.warning(f"Photo captions skipped because no {provider_name} API key is configured.")

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
                st.download_button(
                    "Download report ZIP",
                    zip_bytes,
                    "reports.zip",
                    type="primary",
                    use_container_width=True,
                )

    st.session_state["structured_report_data"] = normalize_structured_rows(rows_to_structured_data(review_rows))
    safe_markdown("---")
