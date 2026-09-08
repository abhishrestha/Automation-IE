"""Drag-and-drop UI: upload call recordings -> review round-wise questions ->
append them to the Google Sheet (two columns: Round | Questions).

Run:  .venv/bin/streamlit run app.py
"""
import tempfile
from pathlib import Path

import pandas as pd
import streamlit as st

from config import load_config
from extraction import extract_questions
from sheets_writer import HEADER, append_questions
from transcription import transcribe

st.set_page_config(page_title="Call → Sheet", page_icon="🎧", layout="wide")
st.title("🎧 Call recording → Google Sheet")
st.caption("Upload recordings → extract the interview questions round-wise → push to the sheet.")


@st.cache_resource
def get_config():
    return load_config("config.yaml")


try:
    cfg = get_config()
    st.sidebar.success("Config loaded")
    st.sidebar.write(f"**Sheet tab:** `{cfg['google_worksheet_name']}`")
    st.sidebar.write(f"**Transcription:** `{cfg['transcription_model']}`")
    st.sidebar.write(f"**Extraction:** `{cfg['extraction_model']}`")
except SystemExit as e:
    st.error(f"Config problem: {e}")
    st.stop()

if "rows" not in st.session_state:
    st.session_state.rows = []

uploads = st.file_uploader(
    "Call recordings", type=["mp3", "wav", "m4a", "mp4", "webm", "ogg"],
    accept_multiple_files=True,
)

col1, col2 = st.columns(2)
with col1:
    go = st.button("① Transcribe & extract questions", type="primary",
                   disabled=not uploads, use_container_width=True)
with col2:
    keep_transcripts = st.checkbox("Save transcripts to transcripts/", value=True)

if go:
    rows = []
    prog = st.progress(0.0)
    for i, up in enumerate(uploads):
        st.write(f"**{up.name}**")
        suffix = Path(up.name).suffix or ".mp3"
        with tempfile.NamedTemporaryFile(suffix=suffix, delete=False) as tmp:
            tmp.write(up.getbuffer())
            tmp_path = tmp.name
        try:
            with st.spinner(f"Transcribing {up.name} …"):
                transcript = transcribe(tmp_path, cfg["openai_api_key"], cfg["transcription_model"])
            if keep_transcripts:
                Path("transcripts").mkdir(exist_ok=True)
                (Path("transcripts") / f"{Path(up.name).stem}.txt").write_text(transcript)
            with st.spinner(f"Extracting questions from {up.name} …"):
                file_rows = extract_questions(
                    transcript, cfg["gemini_api_key"],
                    cfg["extraction_model"], int(cfg["extraction_max_tokens"]),
                )
            for r in file_rows:
                r["source"] = up.name
            rows += file_rows
            st.success(f"{len(file_rows)} questions from {up.name}")
        except Exception as exc:  # noqa: BLE001 - surface any pipeline error in the UI
            st.error(f"{up.name}: {exc}")
        finally:
            Path(tmp_path).unlink(missing_ok=True)
        prog.progress((i + 1) / len(uploads))
    st.session_state.rows = rows

if st.session_state.rows:
    st.subheader("Review & edit before pushing")
    st.caption("Fix any wording, delete junk rows, reorder if needed. Only Round + Questions get written.")
    df = pd.DataFrame(st.session_state.rows)
    if "source" not in df:
        df["source"] = ""
    edited = st.data_editor(
        df[["round", "question", "source"]],
        num_rows="dynamic", use_container_width=True, hide_index=True,
        column_config={
            "round": st.column_config.TextColumn("Round", width="small"),
            "question": st.column_config.TextColumn("Questions", width="large"),
            "source": st.column_config.TextColumn("From file", disabled=True),
        },
    )

    clean = [
        {"round": str(r["round"]).strip(), "question": str(r["question"]).strip()}
        for _, r in edited.iterrows()
        if str(r.get("round", "")).strip() and str(r.get("question", "")).strip()
    ]
    st.write(f"**{len(clean)}** rows ready.")

    if st.button("② Append to Google Sheet", type="primary", disabled=not clean):
        try:
            n = append_questions(
                clean, cfg["google_sheet_id"], cfg["google_worksheet_name"],
                cfg["google_credentials_file"],
                credentials_dict=cfg.get("google_credentials_dict"),
            )
            st.success(f"Appended {n} rows to '{cfg['google_worksheet_name']}' "
                       f"(columns {HEADER[0]} | {HEADER[1]}).")
            st.balloons()
        except Exception as exc:  # noqa: BLE001
            st.error(f"Sheet write failed: {exc}")
