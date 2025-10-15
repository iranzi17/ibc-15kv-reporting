import base64
from io import BytesIO
import zipfile
import xml.etree.ElementTree as ET

from docx import Document
from docx.shared import Mm

import report


SAMPLE_PNG = base64.b64decode(
    "iVBORw0KGgoAAAANSUhEUgAAAAEAAAABCAYAAAAfFcSJAAAADUlEQVR4nGNgYGBgAAAABQABDQottAAAAABJRU5ErkJggg=="
)


def test_safe_filename():
    assert report.safe_filename('inv?lid:name') == 'inv-lid-name'


def test_format_date_title():
    assert report.format_date_title('06/08/2025') == '06.08.2025'


def _empty_row(site: str, date: str) -> list[str]:
    return [date, site] + [""] * 12


def test_generate_reports_returns_zip():
    rows = [_empty_row("Site A", "2025-08-06")]
    uploaded = {}
    data = report.generate_reports(rows, uploaded, 'Civil', 70, 60, 2, 2, False)
    with zipfile.ZipFile(BytesIO(data)) as zf:
        names = zf.namelist()
    assert len(names) == 1
    assert names[0].startswith('Site A')


def test_generate_reports_respects_width_and_spacing():
    rows = [_empty_row("Site A", "2025-08-06")]
    uploaded = {("Site A", "2025-08-06"): [SAMPLE_PNG]}
    width_mm = 42
    height_mm = 25
    spacing_mm = 5
    data = report.generate_reports(
        rows,
        uploaded,
        "Civil",
        width_mm,
        height_mm,
        spacing_mm,
        img_per_row=1,
        add_border=False,
    )
    with zipfile.ZipFile(BytesIO(data)) as zf:
        docx_name = zf.namelist()[0]
        doc_bytes = zf.read(docx_name)

    document = Document(BytesIO(doc_bytes))
    widths = [shape.width for shape in document.inline_shapes]
    assert Mm(width_mm) in widths
    heights = [shape.height for shape in document.inline_shapes]
    assert Mm(height_mm) in heights

    expected_twips = str(report._mm_to_twips(spacing_mm))
    with zipfile.ZipFile(BytesIO(doc_bytes)) as doc_archive:
        document_xml = doc_archive.read("word/document.xml")

    root = ET.fromstring(document_xml)
    ns = {"w": "http://schemas.openxmlformats.org/wordprocessingml/2006/main"}
    margin_sets = []
    for tc_mar in root.findall(".//w:tcMar", ns):
        values = {child.tag.split("}")[-1]: child.get(f"{{{ns['w']}}}w") for child in tc_mar}
        margin_sets.append(values)

    assert any(
        margins.get("left") == margins.get("right") == margins.get("top") == margins.get("bottom") == expected_twips
        for margins in margin_sets
    ), "Expected symmetric margins matching the configured spacing"


def test_generate_reports_two_images_gap_distribution():
    rows = [_empty_row("Site A", "2025-08-06")]
    uploaded = {("Site A", "2025-08-06"): [SAMPLE_PNG, SAMPLE_PNG]}
    spacing_mm = 5
    data = report.generate_reports(
        rows,
        uploaded,
        "Civil",
        185,
        148,
        spacing_mm,
        img_per_row=2,
        add_border=False,
    )

    with zipfile.ZipFile(BytesIO(data)) as zf:
        docx_name = zf.namelist()[0]
        doc_bytes = zf.read(docx_name)

    with zipfile.ZipFile(BytesIO(doc_bytes)) as doc_archive:
        document_xml = doc_archive.read("word/document.xml")

    root = ET.fromstring(document_xml)
    ns = {"w": "http://schemas.openxmlformats.org/wordprocessingml/2006/main"}
    margin_sets = []
    for tc_mar in root.findall(".//w:tcMar", ns):
        values = {child.tag.split("}")[-1]: child.get(f"{{{ns['w']}}}w") for child in tc_mar}
        margin_sets.append(values)

    outer = str(report._mm_to_twips(spacing_mm))
    inner = str(report._mm_to_twips(spacing_mm / 2))

    assert any(
        margins.get("left") == outer and margins.get("right") == inner for margins in margin_sets
    ), "Expected left cell to keep full outer margin and inner half-gap"
    assert any(
        margins.get("left") == inner and margins.get("right") == outer for margins in margin_sets
    ), "Expected right cell to keep inner half-gap and full outer margin"
