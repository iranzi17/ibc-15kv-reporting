from datetime import datetime


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
