from io import BytesIO
import zipfile

import report


def test_safe_filename():
    assert report.safe_filename('inv?lid:name') == 'inv-lid-name'


def test_format_date_title():
    assert report.format_date_title('06/08/2025') == '06.08.2025'


def test_generate_reports_returns_zip():
    rows = [["2025-08-06", "Site A", "", "", "", "", "", "", "", "", ""]]
    uploaded = {}
    data = report.generate_reports(rows, uploaded, 'Civil', 70, 2, False)
    with zipfile.ZipFile(BytesIO(data)) as zf:
        names = zf.namelist()
    assert len(names) == 1
    assert names[0].startswith('Site A')
