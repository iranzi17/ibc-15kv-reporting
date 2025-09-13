import pandas as pd
import streamlit as st

    )
    
    # Controls that were mistakenly embedded in HTML in original file:
    st.sidebar.subheader("Gallery Controls")
    img_width_mm = st.sidebar.slider("Image width (mm)", min_value=30, max_value=100, value=70, step=5)
    img_per_row = st.sidebar.selectbox("Images per row", options=[1,2,3,4], index=1)
    add_border = st.sidebar.checkbox("Add border to images", value=False)
    spacing_mm = st.sidebar.slider("Spacing between images (mm)", min_value=0, max_value=20, value=2, step=1)
    
    # Get sheet data
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
    
    site_date_pairs = sorted({(row[1].strip(), row[0].strip()) for row in filtered_rows})
    
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
