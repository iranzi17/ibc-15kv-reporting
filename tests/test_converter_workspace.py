from report_structuring import REPORT_HEADERS
from streamlit_ui.converter_workspace import rows_for_sheet_append


def test_rows_for_sheet_append_uses_canonical_header_order():
    row = {header: f"value-{index}" for index, header in enumerate(REPORT_HEADERS)}
    row[REPORT_HEADERS[0]] = "2026-04-18"
    row[REPORT_HEADERS[1]] = "Site A"

    shuffled = {key: row[key] for key in reversed(list(row.keys()))}
    appended = rows_for_sheet_append([shuffled])

    assert appended == [[row[header] for header in REPORT_HEADERS]]
