from datetime import datetime
from typing import Dict

import os
import shutil
import tempfile
import zipfile


def parse_any_date(datestr: str):
    """Parse a date string in multiple formats into a ``datetime.date``.

    Supported formats:
    - ``dd.mm.YYYY``
    - ``dd/mm/YYYY``
    - ``YYYY-mm-dd``

    Parameters
    ----------
    datestr: str
        Date string to parse.

    Returns
    -------
    datetime.date
        Parsed date.

    Raises
    ------
    ValueError
        If ``datestr`` does not match any supported format.
    """
    for fmt in ("%d.%m.%Y", "%d/%m/%Y", "%Y-%m-%d"):
        try:
            return datetime.strptime(datestr, fmt).date()
        except ValueError:
            continue
    raise ValueError(f"Unknown date format: {datestr}")


def load_daily_template(template_path: str):
    """Return a ``DocxTemplate`` with placeholders converted to valid names.

    The daily report template uses placeholders that contain spaces which are
    not valid Jinja2 variable names. This helper rewrites the ``document.xml``
    so that tokens like ``{{Site Name}}`` become ``{{Site_Name}}`` before
    loading the template with ``docxtpl``.
    """

    from docxtpl import DocxTemplate  # imported lazily for test environments

    replacements: Dict[str, str] = {
        "Site Name": "Site_Name",
        "Date": "Date",
        "District": "District",
        "Cabin  or Underground Cables": "Cabin_or_Underground_Cables",
        "Personnel": "Personnel",
        "Materials and equipment": "Materials_and_equipment",
        "Civil Works": "Civil_Works",
        (
            "Comments about the activities performed and challenges faced"
        ): "Comments_about_the_activities_performed_and_challenges_faced",
        "Challenges": "Challenges",
        (
            "Comments about observation on rules of HEALTH, SAFETY & ENVIRONMENT"
        ): "Comments_about_observation_on_rules_of_HEALTH_SAFETY_AND_ENVIRONMENT",
        "General recommendation": "General_recommendation",
    }

    tmpdir = tempfile.mkdtemp()
    with zipfile.ZipFile(template_path) as zin:
        zin.extractall(tmpdir)

    doc_xml = os.path.join(tmpdir, "word", "document.xml")
    with open(doc_xml, "r", encoding="utf-8") as f:
        xml = f.read()

    for old, new in replacements.items():
        xml = xml.replace(f"{{{{{old}}}}}", f"{{{{{new}}}}}")

    with open(doc_xml, "w", encoding="utf-8") as f:
        f.write(xml)

    patched_path = os.path.join(tmpdir, "patched.docx")
    with zipfile.ZipFile(patched_path, "w") as zout:
        for root, _, files in os.walk(tmpdir):
            for file in files:
                if file == "patched.docx":
                    continue
                fp = os.path.join(root, file)
                arcname = os.path.relpath(fp, tmpdir)
                zout.write(fp, arcname)

    tpl = DocxTemplate(patched_path)
    shutil.rmtree(tmpdir)
    return tpl
