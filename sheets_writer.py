"""Append round-wise questions to a Google Sheet using a service account.

Two columns only:  A = Round   B = Questions
"""
import time

import gspread

HEADER = ["Round", "Questions"]
_RETRY_STATUS = {429, 500, 502, 503, 504}


def _retry(fn, *, tries: int = 5, base_delay: float = 1.5):
    """Retry a gspread call on transient Google API errors (429 / 5xx)."""
    for attempt in range(tries):
        try:
            return fn()
        except gspread.exceptions.APIError as e:
            code = getattr(e.response, "status_code", None)
            if code not in _RETRY_STATUS or attempt == tries - 1:
                raise
            time.sleep(base_delay * (2 ** attempt))


def _open_ws(sheet_id, worksheet_name, credentials_file, credentials_dict):
    if credentials_dict:
        gc = gspread.service_account_from_dict(credentials_dict)
    else:
        gc = gspread.service_account(filename=credentials_file)
    return _retry(lambda: gc.open_by_key(sheet_id).worksheet(worksheet_name))


def append_questions(question_rows: list[dict], sheet_id: str, worksheet_name: str,
                     credentials_file: str = "credentials.json",
                     ensure_header: bool = True,
                     credentials_dict: dict | None = None) -> int:
    """question_rows: [{"round": "R1", "question": "..."}, ...] -> rows appended."""
    if not question_rows:
        return 0
    ws = _open_ws(sheet_id, worksheet_name, credentials_file, credentials_dict)

    if ensure_header:
        first_row = _retry(lambda: ws.row_values(1))
        if first_row[:2] != HEADER:
            if first_row:
                _retry(lambda: ws.insert_row(HEADER, 1))
            else:
                _retry(lambda: ws.update("A1:B1", [HEADER]))

    values = [[r["round"], r["question"]] for r in question_rows]
    _retry(lambda: ws.append_rows(values, value_input_option="USER_ENTERED"))
    return len(values)
