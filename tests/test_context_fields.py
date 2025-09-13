from report import SIGNATORIES


def test_context_includes_signatory_fields():
    discipline = "Civil"
    sign_info = SIGNATORIES.get(discipline, {})
    ctx = {
        "Consultant_Name": sign_info.get("Consultant_Name", ""),
        "Consultant_Title": sign_info.get("Consultant_Title", ""),
        "Contractor_Name": sign_info.get("Contractor_Name", ""),
        "Contractor_Title": sign_info.get("Contractor_Title", ""),
    }
    assert all(ctx[field] for field in [
        "Consultant_Name",
        "Consultant_Title",
        "Contractor_Name",
        "Contractor_Title",
    ])

