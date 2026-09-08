"""Drag-and-drop UI: upload debrief call recordings -> review questions + outcome ->
append to the Google Sheet.

Sheet columns:  Phone Number | Round | Questions | Reason for Rejection

Run:  .venv/bin/streamlit run app.py
"""
import tempfile
from pathlib import Path

import pandas as pd
import streamlit as st

from config import load_config
from extraction import detect_phone_from_name, extract_call, normalize_phone
from sheets_writer import HEADER, NO_QUESTIONS_TEXT, append_value_rows
from transcription import transcribe

st.set_page_config(page_title="Call → Sheet", page_icon="🎧", layout="wide")
st.title("🎧 Interview debrief call → Google Sheet")
st.caption("Upload recordings → extract questions + rejection reason per candidate → push to the sheet.")


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

st.session_state.setdefault("calls", [])

uploads = st.file_uploader(
    "Call recordings", type=["mp3", "wav", "m4a", "mp4", "webm", "ogg"],
    accept_multiple_files=True,
)

c1, c2 = st.columns([1, 1])
with c1:
    go = st.button("① Transcribe & extract", type="primary",
                   disabled=not uploads, use_container_width=True)
with c2:
    keep_transcripts = st.checkbox("Save transcripts to transcripts/", value=True)

if go:
    calls = []
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
            with st.spinner(f"Extracting from {up.name} …"):
                call = extract_call(
                    transcript, cfg["openai_api_key"],
                    cfg["extraction_model"], int(cfg["extraction_max_tokens"]),
                )
            call["phone_number"] = call["phone_number"] or detect_phone_from_name(up.name)
            call["source"] = up.name
            calls.append(call)
            msg = f"{len(call['rows'])} questions · reason: {call['reason_for_rejection']}"
            (st.success if call["rows"] else st.warning)(f"{up.name} — {msg}")
        except Exception as exc:  # noqa: BLE001 - surface any pipeline error in the UI
            st.error(f"{up.name}: {exc}")
        finally:
            Path(tmp_path).unlink(missing_ok=True)
        prog.progress((i + 1) / len(uploads))
    st.session_state.calls = calls

calls = st.session_state.calls
if calls:
    st.subheader("Review & edit before pushing")
    st.caption("Set the phone number for each call, fix any wording, delete junk rows. "
               f"Calls with no questions are written as “{NO_QUESTIONS_TEXT}”.")

    flat = []
    for ci, call in enumerate(calls):
        st.markdown(f"**{call.get('source', f'Call {ci + 1}')}**")
        pcol, rcol = st.columns([1, 2])
        phone = pcol.text_input("Phone number", value=call["phone_number"],
                                key=f"phone_{ci}", placeholder="e.g. 9876543210")
        reason = rcol.text_input("Reason for rejection", value=call["reason_for_rejection"],
                                 key=f"reason_{ci}")
        phone = normalize_phone(phone) or phone.strip()

        rows = call["rows"] or [{"round": "", "question": NO_QUESTIONS_TEXT}]
        df = pd.DataFrame(rows)[["round", "question"]]
        edited = st.data_editor(
            df, num_rows="dynamic", use_container_width=True, hide_index=True,
            key=f"editor_{ci}",
            column_config={
                "round": st.column_config.TextColumn("Round", width="small"),
                "question": st.column_config.TextColumn("Questions", width="large"),
            },
        )
        any_q = False
        for _, r in edited.iterrows():
            q = str(r.get("question", "")).strip()
            if not q:
                continue
            any_q = True
            flat.append([phone, str(r.get("round", "")).strip(), q, reason])
        if not any_q:
            flat.append([phone, "", NO_QUESTIONS_TEXT, reason])
        st.divider()

    st.write(f"**{len(flat)}** rows ready for `{cfg['google_worksheet_name']}` "
             f"({' | '.join(HEADER)}).")

    if st.button("② Append to Google Sheet", type="primary", disabled=not flat):
        try:
            n = append_value_rows(
                flat, cfg["google_sheet_id"], cfg["google_worksheet_name"],
                cfg["google_credentials_file"],
                credentials_dict=cfg.get("google_credentials_dict"),
            )
            st.success(f"Appended {n} rows to '{cfg['google_worksheet_name']}'.")
            st.balloons()
        except Exception as exc:  # noqa: BLE001
            st.error(f"Sheet write failed: {exc}")
