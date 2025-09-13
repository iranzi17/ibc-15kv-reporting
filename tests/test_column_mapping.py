import pytest



def test_column_mapping_order():
    rows = [
      
    ]

    sites, dates = get_unique_sites_and_dates(rows)
    assert sites == ["Site A", "Site B"]
    assert dates == ["2024-01-01", "2024-01-02", "2024-01-03"]

    selected_sites = ["Site A"]
    site_dates = sorted({row[0].strip() for row in rows if row[1].strip() in selected_sites})
    assert site_dates == ["2024-01-01", "2024-01-03"]

    filtered_rows = [
        row for row in rows
        if row[1].strip() in selected_sites and row[0].strip() in site_dates
    ]
    assert filtered_rows == [rows[0], rows[2]]

    site_date_pairs = sorted({(row[1].strip(), row[0].strip()) for row in filtered_rows})
    assert site_date_pairs == [("Site A", "2024-01-01"), ("Site A", "2024-01-03")]
