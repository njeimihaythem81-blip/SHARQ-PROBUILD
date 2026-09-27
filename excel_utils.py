"""
Strict parsing/validation for the master parts-list Excel file.
Expected columns (English, exact match, case-insensitive):
    Part Number | Description | Quantity
No prices or financial values are allowed anywhere in this file.
"""
import io
import pandas as pd

REQUIRED_COLUMNS = ["Part Number", "Description", "Quantity"]


def _read_df(file_like) -> pd.DataFrame:
    if hasattr(file_like, "read"):
        data = file_like.read()
        file_like.seek(0)
    else:
        data = file_like
    return pd.read_excel(io.BytesIO(data))


def validate_excel(file_obj):
    try:
        df = _read_df(file_obj)
    except Exception as e:
        return False, f"Could not read the Excel file ({e})"

    cols = [c.strip() for c in df.columns]
    normalized = [c.lower() for c in cols]
    required_lower = [c.lower() for c in REQUIRED_COLUMNS]

    if not all(rc in normalized for rc in required_lower):
        return False, f"Excel must contain exactly these columns: {', '.join(REQUIRED_COLUMNS)}"

    if df.empty:
        return False, "Excel file has no data rows."

    return True, None


def parse_rows(raw_bytes: bytes) -> list:
    """Return the parts list as a list of dicts: [{'Part Number':.., 'Description':.., 'Quantity':..}, ...]
    Used by the free local search assistant (no external API involved)."""
    df = pd.read_excel(io.BytesIO(raw_bytes))
    df.columns = [c.strip() for c in df.columns]
    col_map = {c.lower(): c for c in df.columns}
    ordered_cols = [col_map[c.lower()] for c in REQUIRED_COLUMNS if c.lower() in col_map]
    df = df[ordered_cols]
    df.columns = REQUIRED_COLUMNS  # normalize names
    return df.to_dict("records")


def to_context_string(raw_bytes: bytes) -> str:
    df = pd.read_excel(io.BytesIO(raw_bytes))
    df.columns = [c.strip() for c in df.columns]
    # Keep only the three approved columns, in order, drop anything else (e.g. price columns)
    col_map = {c.lower(): c for c in df.columns}
    ordered_cols = [col_map[c.lower()] for c in REQUIRED_COLUMNS if c.lower() in col_map]
    df = df[ordered_cols]

    lines = ["Approved Parts List for this panel (Part Number | Description | Quantity):"]
    for _, row in df.iterrows():
        lines.append(f"- {row[ordered_cols[0]]} | {row[ordered_cols[1]]} | {row[ordered_cols[2]]}")
    return "\n".join(lines)
