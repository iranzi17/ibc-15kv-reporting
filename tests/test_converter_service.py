from services.converter_service import (
    apply_field_locks,
    normalize_structured_rows,
    summarize_row_changes,
    validate_conversion_source_inputs,
    validate_refinement_request,
)


def _row(**overrides):
    row = {
        "Date": "2026-04-18",
        "Site_Name": "KIBAGABAGA SMART CABIN",
        "District": "Gasabo",
        "Work": "Cable works",
        "Human_Resources": "",
        "Supply": "",
        "Work_Executed": "Executed cable laying.",
        "Comment_on_work": "Work is progressing.",
        "Another_Work_Executed": "",
        "Comment_on_HSE": "",
        "Consultant_Recommandation": "",
        "Non_Compliant_work": "",
        "Reaction_and_WayForword": "",
        "challenges": "",
    }
    row.update(overrides)
    return row


def test_apply_field_locks_preserves_locked_values():
    previous = [_row(Date="2026-04-17", Site_Name="SITE A", District="Gasabo")]
    updated = [_row(Date="2026-04-18", Site_Name="SITE B", District="Kicukiro", Work_Executed="Updated.")]

    locked = apply_field_locks(previous, updated, locked_fields=["Date", "Site_Name", "District"])

    assert locked[0]["Date"] == "2026-04-17"
    assert locked[0]["Site_Name"] == "SITE A"
    assert locked[0]["District"] == "Gasabo"
    assert locked[0]["Work_Executed"] == "Updated."


def test_summarize_row_changes_lists_changed_fields():
    previous = [_row(Comment_on_work="Work is progressing.")]
    updated = normalize_structured_rows([_row(Comment_on_work="Work is progressing well.", challenges="Rain delay")])

    summary = summarize_row_changes(previous, updated)

    assert summary[0]["row_index"] == 1
    changed_fields = [entry["field"] for entry in summary[0]["changes"]]
    assert changed_fields == ["Comment_on_work", "challenges"]


def test_validation_rejects_empty_or_near_empty_requests():
    assert validate_conversion_source_inputs("", []) == [
        "Provide contractor text or attach source files before converting."
    ]
    assert validate_conversion_source_inputs("ok", []) == [
        "The pasted contractor text is too short to convert reliably."
    ]
    assert validate_refinement_request(
        "ok",
        has_voice_instruction=False,
        has_supporting_files=True,
        raw_report_text="source",
    ) == ["The refinement instruction is too short to apply reliably."]

