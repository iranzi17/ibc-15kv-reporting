import datetime
from unittest import mock

from utils import parse_any_date

# Placeholder for the real function in app.py
# It will be patched in tests to avoid external calls

def generate_hf_summary(text: str, hf_token: str) -> str:
    raise RuntimeError("This function should be mocked in tests")


def build_weekly_context(week_rows, week_start, week_end, hf_token):
    """Replicate the weekly context creation logic from app.py."""
    week_text = "\n\n".join(
        (
            f"Date: {row[1]}\nSite: {row[0]}\nCivil: {row[2]}\nRecommendation: {row[3]}\nComments: {row[4]}\nChallenges: {row[5]}"
        )
        for row in week_rows
    )
    issues = "\n".join([row[5] for row in week_rows if row[5]])
    difficulties = "\n".join(
        [row[5] for row in week_rows if "difficult" in row[5].lower()]
    )
    ongoing_activities = "\n".join([row[3] for row in week_rows if row[3]])
    achievements = "\n".join(
        [row[2] for row in week_rows if "complete" in row[2].lower() or "finish" in row[2].lower()]
    )
    planned_activities = "\n".join([row[4] for row in week_rows if row[4]])
    hse = "No incidents reported this week."

    summary = generate_hf_summary(week_text, hf_token)

    context = {
        "WEEK_NO": week_start.isocalendar()[1],
        "PERIOD_FROM": week_start.strftime("%Y-%m-%d"),
        "PERIOD_TO": week_end.strftime("%Y-%m-%d"),
        "DOCUMENT_NO": f"WR-{week_start.strftime('%Y%m%d')}-{week_end.strftime('%Y%m%d')}",
        "DATE": datetime.date.today().strftime("%Y-%m-%d"),
        "PROJECT_NAME": "15kV Substation Project",
        "SUMMARY": summary,
        "PROJECT_PROGRESS": summary,
        "ISSUES": issues or "None.",
        "DIFFICULTIES": difficulties or "None.",
        "ONGOING_ACTIVITIES": ongoing_activities or "See attached summary.",
        "ACHIEVEMENTS": achievements or "See attached summary.",
        "PLANNED_ACTIVITIES": planned_activities or "See attached summary.",
        "HSE": hse,
    }
    return context


def test_build_weekly_context_contains_keys():
    week_rows = [
        [
            "Site A",
            "2024-01-01",
            "completed foundation",
            "install cables",
            "plan next",
            "no issues",
        ],
        [
            "Site B",
            "2024-01-02",
            "civil works ongoing",
            "testing equipment",
            "future plan",
            "Difficult terrain encountered",
        ],
    ]

    week_start = parse_any_date("2024-01-01")
    week_end = parse_any_date("2024-01-07")

    with mock.patch(
        "tests.test_weekly_report.generate_hf_summary", return_value="Mock summary"
    ):
        context = build_weekly_context(week_rows, week_start, week_end, "token")

    expected_keys = {
        "WEEK_NO",
        "PERIOD_FROM",
        "PERIOD_TO",
        "DOCUMENT_NO",
        "DATE",
        "PROJECT_NAME",
        "SUMMARY",
        "PROJECT_PROGRESS",
        "ISSUES",
        "DIFFICULTIES",
        "ONGOING_ACTIVITIES",
        "ACHIEVEMENTS",
        "PLANNED_ACTIVITIES",
        "HSE",
    }

    assert expected_keys.issubset(context.keys())
