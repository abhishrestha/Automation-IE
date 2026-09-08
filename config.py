"""Config loader with three sources, in priority order:

  1. Streamlit secrets  (st.secrets)     -> used when deployed to Streamlit Cloud
  2. Environment variables
  3. config.yaml                          -> local dev

Secrets/keys expected:
  google_sheet_id, google_worksheet_name
  openai_api_key, gemini_api_key
  Google service account: either google_credentials_file (a path) OR a
  [gcp_service_account] table / google_credentials_json string (for cloud).
"""
import json
import os
from pathlib import Path

import yaml

_DEFAULTS = {
    "google_worksheet_name": "Sheet1",
    "google_credentials_file": "credentials.json",
    "transcription_model": "whisper-1",
    "extraction_model": "gemini-3.5-flash",
    "extraction_max_tokens": 8000,
}


def _streamlit_secrets() -> dict:
    try:
        import streamlit as st  # noqa: PLC0415
        return dict(st.secrets)
    except Exception:  # not running under streamlit, or no secrets file
        return {}


def load_config(path: str = "config.yaml") -> dict:
    cfg = dict(_DEFAULTS)

    p = Path(path)
    if p.exists():
        cfg.update(yaml.safe_load(p.read_text()) or {})

    secrets = _streamlit_secrets()

    def pick(key, *env_names):
        return (secrets.get(key)
                or next((os.environ[e] for e in env_names if e in os.environ), None)
                or cfg.get(key))

    cfg["google_sheet_id"] = pick("google_sheet_id", "GOOGLE_SHEET_ID")
    cfg["google_worksheet_name"] = pick("google_worksheet_name", "GOOGLE_WORKSHEET_NAME") or "Sheet1"
    cfg["openai_api_key"] = pick("openai_api_key", "OPENAI_API_KEY")
    cfg["gemini_api_key"] = pick("gemini_api_key", "GEMINI_API_KEY", "GOOGLE_API_KEY")
    cfg["extraction_model"] = pick("extraction_model", "EXTRACTION_MODEL") or _DEFAULTS["extraction_model"]

    # Service account: prefer an inline dict (cloud), fall back to a file path (local).
    sa = secrets.get("gcp_service_account") or cfg.get("gcp_service_account")
    if not sa:
        raw = secrets.get("google_credentials_json") or os.environ.get("GOOGLE_CREDENTIALS_JSON")
        if raw:
            sa = json.loads(raw)
    cfg["google_credentials_dict"] = dict(sa) if sa else None

    missing = [k for k in ("google_sheet_id", "openai_api_key", "gemini_api_key") if not cfg.get(k)]
    if not cfg["google_credentials_dict"] and not Path(cfg["google_credentials_file"]).exists():
        missing.append("google service account (credentials.json or gcp_service_account secret)")
    if missing:
        raise SystemExit("Missing config: " + ", ".join(missing)
                         + " — set in config.yaml, env, or Streamlit secrets.")
    return cfg
