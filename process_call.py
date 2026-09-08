#!/usr/bin/env python3
"""CLI: call recording(s) -> round-wise questions -> Google Sheet (Round | Questions).

  python process_call.py call1.m4a call2.mp3            # transcribe + extract + append
  python process_call.py call.m4a --dry-run             # print rows, don't write
  python process_call.py --transcript notes.txt         # skip transcription
  python process_call.py call.m4a --save-transcript
"""
import argparse
import json
import sys
from datetime import datetime
from pathlib import Path

from config import load_config
from extraction import extract_questions
from sheets_writer import append_questions
from transcription import transcribe


def _rows_for_file(path, cfg, is_transcript, save):
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
    print("  extracting questions ...")
    return extract_questions(transcript, cfg["gemini_api_key"],
                             cfg["extraction_model"], int(cfg["extraction_max_tokens"]))


def main():
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("files", nargs="*", help="audio recordings (or transcripts with --transcript)")
    ap.add_argument("--transcript", action="store_true", help="treat inputs as text transcripts")
    ap.add_argument("--config", default="config.yaml")
    ap.add_argument("--dry-run", action="store_true", help="print rows, do not write to the sheet")
    ap.add_argument("--save-transcript", action="store_true")
    args = ap.parse_args()
    if not args.files:
        sys.exit("Give at least one file")

    cfg = load_config(args.config)
    all_rows = []
    for f in args.files:
        print(f"\n{f}")
        all_rows += _rows_for_file(f, cfg, args.transcript, args.save_transcript)

    print(f"\n{len(all_rows)} question rows:")
    for r in all_rows:
        print(f"  {r['round']:<4} {r['question']}")

    if args.dry_run:
        print("\n--dry-run: not writing.")
        print(json.dumps(all_rows, indent=1, ensure_ascii=False))
        return

    n = append_questions(all_rows, cfg["google_sheet_id"], cfg["google_worksheet_name"],
                         cfg["google_credentials_file"],
                         credentials_dict=cfg.get("google_credentials_dict"))
    print(f"\nAppended {n} rows to {cfg['google_worksheet_name']}")


if __name__ == "__main__":
    main()
