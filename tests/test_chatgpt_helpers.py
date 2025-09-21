import pytest

from report_structuring import REPORT_HEADERS, clean_and_structure_report


def test_clean_and_structure_report_parses_single_section():
    raw_text = """
    Date: 2024-04-01
    Site Name: Kigali West Substation
    District - Gasabo
    Work Executed: Completed transformer plinth
    Comment on HSE - PPE used throughout the shift
    Unknown Field: Extra site notes
    Follow-up observation about material delays.
    """.strip()

    result = clean_and_structure_report(raw_text)

    assert result["Date"] == "2024-04-01"
    assert result["Site_Name"] == "Kigali West Substation"
    assert result["District"] == "Gasabo"
    assert result["Work_Executed"] == "Completed transformer plinth"
    assert result["Comment_on_HSE"] == "PPE used throughout the shift"
    assert "Extra site notes" in result["Comment_on_work"]
    assert result["Comment_on_work"].endswith("material delays.")
    assert result["Supply"] == ""


def test_clean_and_structure_report_supports_multiple_sections():
    raw_text = """
    Date: 2024-04-01
    Site: Site A
    Work Executed: Completed trenching
    ---
    Date: 2024-04-02
    Site Name: Site B
    Work Executed: Cable laying in progress
    """.strip()

    result = clean_and_structure_report(raw_text)

    assert isinstance(result, list)
    assert [row["Site_Name"] for row in result] == ["Site A", "Site B"]
    assert all(set(row) == set(REPORT_HEADERS) for row in result)


@pytest.mark.parametrize("value", ["", "   ", "\n\n"])
def test_clean_and_structure_report_requires_content(value):
    with pytest.raises(ValueError):
        clean_and_structure_report(value)


def test_clean_and_structure_report_rejects_non_string():
    with pytest.raises(TypeError):
        clean_and_structure_report(None)  # type: ignore[arg-type]
