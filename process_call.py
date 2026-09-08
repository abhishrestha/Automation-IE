#!/usr/bin/env python3
"""CLI: debrief call recording(s) -> questions + outcome -> Google Sheet.

Sheet columns:  Phone Number | Round | Questions | Reason for Rejection

  python process_call.py call1.m4a call2.mp3
  python process_call.py call.m4a --dry-run
  python process_call.py call.m4a --phone 9876543210
  python process_call.py notes.txt --transcript
"""
import argparse
import json
import sys
from datetime import datetime
from pathlib import Path

from config import load_config
from extraction import detect_phone_from_name, extract_call, normalize_phone
from sheets_writer import append_calls
from transcription import transcribe


def _process(path, cfg, is_transcript, save, phone_override):
    if is_transcript:
        transcript = Path(path).read_text()
        print(f"  loaded transcript ({len(transcript)} chars)")
    else:
        print(f"  transcribing {path} ...")
        transcript = transcribe(path, cfg["openai_api_key"], cfg["transcription_model"])
        print(f"  -> {len(transcript)} chars")
        if save:
            Path("transcripts").mkdir(exist_ok=True)
            tp = Path("transcripts") / f"{Path(path).stem}_{datetime.now():%Y%m%d_%H%M%S}.txt"
            tp.write_text(transcript)
            print(f"  saved {tp}")

    print("  extracting questions + outcome ...")
    call = extract_call(transcript, cfg["gemini_api_key"],
                        cfg["extraction_model"], int(cfg["extraction_max_tokens"]))
    call["phone_number"] = (normalize_phone(phone_override) if phone_override
                            else call["phone_number"] or detect_phone_from_name(Path(path).name))
    return call


def main():
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("files", nargs="*", help="audio recordings (or transcripts with --transcript)")
    ap.add_argument("--transcript", action="store_true", help="treat inputs as text transcripts")
    ap.add_argument("--phone", help="phone number for the call (applied to every file)")
    ap.add_argument("--config", default="config.yaml")
    ap.add_argument("--dry-run", action="store_true", help="print rows, do not write to the sheet")
    ap.add_argument("--save-transcript", action="store_true")
    args = ap.parse_args()
    if not args.files:
        sys.exit("Give at least one file")

    cfg = load_config(args.config)
    calls = []
    for f in args.files:
        print(f"\n{f}")
        calls.append(_process(f, cfg, args.transcript, args.save_transcript, args.phone))

    for c in calls:
        print(f"\n  phone: {c['phone_number'] or '(unknown)'}   "
              f"reason: {c['reason_for_rejection']}")
        if not c["rows"]:
            print("    (no questions collected from the call)")
        for r in c["rows"]:
            print(f"    {r['round']:<4} {r['question']}")

    if args.dry_run:
        print("\n--dry-run: not writing.")
        print(json.dumps(calls, indent=1, ensure_ascii=False))
        return

    n = append_calls(calls, cfg["google_sheet_id"], cfg["google_worksheet_name"],
                     cfg["google_credentials_file"],
                     credentials_dict=cfg.get("google_credentials_dict"))
    print(f"\nAppended {n} rows to {cfg['google_worksheet_name']}")


if __name__ == "__main__":
    main()
