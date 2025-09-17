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


def test_generate_reports_returns_zip():
    rows = [["2025-08-06", "Site A", "", "", "", "", "", "", "", "", ""]]
    uploaded = {}
    data = report.generate_reports(rows, uploaded, 'Civil', 70, 2, 2, False)
    with zipfile.ZipFile(BytesIO(data)) as zf:
        names = zf.namelist()
    assert len(names) == 1
    assert names[0].startswith('Site A')


def test_generate_reports_respects_width_and_spacing():
    rows = [["2025-08-06", "Site A", "", "", "", "", "", "", "", "", ""]]
    uploaded = {("Site A", "2025-08-06"): [SAMPLE_PNG]}
    width_mm = 42
    spacing_mm = 5
    data = report.generate_reports(
        rows,
        uploaded,
        "Civil",
        width_mm,
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

    expected_twips = int(round(spacing_mm * 1440 / 25.4))
    with zipfile.ZipFile(BytesIO(doc_bytes)) as doc_archive:
        document_xml = doc_archive.read("word/document.xml")
    root = ET.fromstring(document_xml)
    ns = {"w": "http://schemas.openxmlformats.org/wordprocessingml/2006/main"}
    expected_str = str(expected_twips)
    margin_tags = {
        f"{{{ns['w']}}}{side}" for side in ("top", "left", "bottom", "right")
    }
    found_spacing = False
    for tc_mar in root.findall(".//w:tcMar", ns):
        margins = {child.tag: child.get(f"{{{ns['w']}}}w") for child in tc_mar}
        if margin_tags.issubset(margins.keys()) and all(
            margins[tag] == expected_str for tag in margin_tags
        ):
            found_spacing = True
            break
    assert found_spacing, "Expected to find table cell margins matching the configured spacing"
