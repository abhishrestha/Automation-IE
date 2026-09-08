"""Append debrief-call results to a Google Sheet using a service account.

Columns:  A = Phone Number   B = Round   C = Questions   D = Reason for Rejection
"""
import time

import gspread

HEADER = ["Phone Number", "Round", "Questions", "Reason for Rejection"]
NO_QUESTIONS_TEXT = "No questions collected from the call"
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


def build_values(calls: list[dict]) -> list[list[str]]:
    """calls: [{"phone_number", "reason_for_rejection", "rows":[{"round","question"}]}]
    -> flat list of [phone, round, question, reason] rows.
    A call with no questions still produces one row (NO_QUESTIONS_TEXT)."""
    values = []
    for call in calls:
        phone = str(call.get("phone_number", "") or "")
        reason = str(call.get("reason_for_rejection", "") or "")
        rows = call.get("rows") or []
        if not rows:
            values.append([phone, "", NO_QUESTIONS_TEXT, reason])
            continue
        for r in rows:
            values.append([phone, r.get("round", ""), r.get("question", ""), reason])
    return values


def append_value_rows(values: list[list[str]], sheet_id: str, worksheet_name: str,
                      credentials_file: str = "credentials.json",
                      ensure_header: bool = True,
                      credentials_dict: dict | None = None) -> int:
    """Append pre-built [phone, round, question, reason] rows (used by the UI after
    the user has reviewed/edited them)."""
    values = [v for v in values if any(str(x).strip() for x in v)]
    if not values:
        return 0
    ws = _open_ws(sheet_id, worksheet_name, credentials_file, credentials_dict)

    if ensure_header:
        first_row = _retry(lambda: ws.row_values(1))
        if first_row[:len(HEADER)] != HEADER:
            if first_row:
                _retry(lambda: ws.insert_row(HEADER, 1))
            else:
                _retry(lambda: ws.update(f"A1:{chr(64 + len(HEADER))}1", [HEADER]))

    _retry(lambda: ws.append_rows(values, value_input_option="USER_ENTERED"))
    return len(values)


def append_calls(calls: list[dict], sheet_id: str, worksheet_name: str,
                 credentials_file: str = "credentials.json",
                 ensure_header: bool = True,
                 credentials_dict: dict | None = None) -> int:
    values = build_values(calls)
    if not values:
        return 0
    ws = _open_ws(sheet_id, worksheet_name, credentials_file, credentials_dict)

    if ensure_header:
        first_row = _retry(lambda: ws.row_values(1))
        if first_row[:len(HEADER)] != HEADER:
            if first_row:
                _retry(lambda: ws.insert_row(HEADER, 1))
            else:
                _retry(lambda: ws.update(f"A1:{chr(64 + len(HEADER))}1", [HEADER]))

    _retry(lambda: ws.append_rows(values, value_input_option="USER_ENTERED"))
    return len(values)
