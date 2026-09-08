# Call Recording → Google Sheet (Round | Questions)

Upload interview-debrief call recordings → it transcribes them, pulls out every
question the learner was asked, expands shorthand into full sentences, and appends
them to a Google Sheet as **two columns only**:

| Round | Questions |
|---|---|
| R1 | Solve a balanced parentheses problem … |
| R1 | Write an SQL query based on a given requirement … |
| R2 | Using the sliding window technique, calculate the average of each window … |

No job IDs, names, modules, or rejection reasons — just the questions.

## Pipeline
`audio → OpenAI Whisper transcript → Gemini question extraction → gspread append`

## Setup

```bash
cd call-doc-automation
python3 -m venv .venv
.venv/bin/pip install -r requirements.txt

cp config.example.yaml config.yaml   # then fill in (see below)
```

**config.yaml** needs:
- `google_sheet_id` — the long id in the sheet URL (`.../d/THIS_PART/edit`)
- `google_worksheet_name` — the tab name (default `Sheet1`)
- `openai_api_key` (Whisper) and `gemini_api_key` (extraction) — or set env
  `OPENAI_API_KEY` / `GEMINI_API_KEY` instead. Get a Gemini key at
  [aistudio.google.com/apikey](https://aistudio.google.com/apikey).

**Google Sheets access (service account, no OAuth popup):**
1. [Google Cloud Console](https://console.cloud.google.com) → new project → enable **Google Sheets API**.
2. IAM & Admin → Service Accounts → create → Keys → Add Key → JSON → save as `call-doc-automation/credentials.json`.
3. Open your Sheet → Share → paste the service-account email (`…@….iam.gserviceaccount.com`) → **Editor**.

The first write adds a `Round | Questions` header row if the sheet doesn't have one.

## Use it — the UI (recommended)

```bash
.venv/bin/streamlit run app.py
```

Opens in the browser. Drag in one or more recordings → **① Transcribe & extract** →
review/edit the questions in the table (fix wording, delete junk rows) → **② Append to Google Sheet**.

## Use it — the CLI

```bash
.venv/bin/python process_call.py call1.m4a call2.mp3          # extract + append
.venv/bin/python process_call.py call.m4a --dry-run           # preview only
.venv/bin/python process_call.py call.m4a --save-transcript   # keep the transcript
.venv/bin/python process_call.py notes.txt --transcript       # already have text
```

## Files
| file | role |
|---|---|
| `app.py` | Streamlit upload UI |
| `process_call.py` | CLI entrypoint |
| `transcription.py` | OpenAI Whisper wrapper (25 MB/file limit guard) |
| `extraction.py` | Gemini call + prompt + strict-JSON parse + retry |
| `sheets_writer.py` | two-column append via gspread |
| `config.py` | config.yaml + env var loading |

## Deploy (Streamlit Community Cloud — free, best fit)

1. Push this folder to a GitHub repo (private is fine).
2. Go to [share.streamlit.io](https://share.streamlit.io) → sign in with GitHub → **New app**.
3. Pick the repo, branch `main`, main file `app.py`
   (or `call-doc-automation/app.py` if the repo root is one level up).
4. **Advanced settings → Secrets** → paste a filled-in copy of
   [.streamlit/secrets.toml.example](.streamlit/secrets.toml.example) — sheet id,
   both API keys, and the whole `credentials.json` as the `[gcp_service_account]` table.
5. **Deploy.** `config.py` reads `st.secrets` automatically in the cloud; no
   `config.yaml` or `credentials.json` is committed or needed there.

The service account still needs Editor access on the target sheet (same as local).

Other options: Render / Railway / Fly.io work too — run
`streamlit run app.py --server.port $PORT --server.address 0.0.0.0` and set the
same values as environment variables (`GOOGLE_SHEET_ID`, `OPENAI_API_KEY`,
`GEMINI_API_KEY`, `GOOGLE_CREDENTIALS_JSON` = the credentials.json contents on one line).

## Tuning the question wording
Edit `SYSTEM_PROMPT` in `extraction.py`. Test with `process_call.py <file> --dry-run`
or the UI's review table before writing to the sheet.

## Notes
- Whisper API limit is 25 MB per file. For a longer recording:
  `ffmpeg -i in.m4a -b:a 32k -ac 1 out.mp3`
- `credentials.json`, `config.yaml`, transcripts and audio files are gitignored.
