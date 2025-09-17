import datetime

import pytest

from utils import parse_any_date


@pytest.mark.parametrize("datestr", [
    "25.12.2023",
    "25/12/2023",
    "2023-12-25",
])
def test_valid_formats(datestr):
    expected = datetime.date(2023, 12, 25)
    assert parse_any_date(datestr) == expected


def test_invalid_format():
    with pytest.raises(ValueError):
        parse_any_date("12-25-2023")
