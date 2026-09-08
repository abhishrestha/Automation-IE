# Interview Debrief Call → Google Sheet

Upload debrief call recordings (calls with candidates who interviewed at a company).
It transcribes each call, reconstructs every interview question the candidate was
asked, works out the rejection reason, and appends to a Google Sheet:

| Phone Number | Round | Questions | Reason for Rejection |
|---|---|---|---|
| 9876543210 | R1 | Solve a balanced parentheses problem … | Rejected - weak on system design fundamentals |
| 9876543210 | R1 | Write an SQL query based on a given requirement … | Rejected - weak on system design fundamentals |
| 9123456789 | | No questions collected from the call | Company Unresponsive |

Rules:
- **Phone number** — taken from the call if stated, else from the filename, else typed in the UI.
- **Reason for Rejection** — extracted from the transcript in plain readable form. If the
  candidate was rejected but no reason is stated anywhere → `Company Unresponsive`.
  If they cleared / got an offer → that is stated instead.
- **No questions found** — not an error; one row is written with
  `No questions collected from the call`.

## Pipeline
`audio → OpenAI Whisper transcript → Gemini extraction (questions + phone + outcome) → gspread append`

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

The first write adds a `Phone Number | Round | Questions | Reason for Rejection`
header row if the sheet doesn't have one.

## Use it — the UI (recommended)

```bash
.venv/bin/streamlit run app.py
```

Opens in the browser. Drag in one or more recordings → **① Transcribe & extract** →
for each call confirm the **phone number** and **reason for rejection**, review/edit the
questions in the table → **② Append to Google Sheet**.

## Use it — the CLI

```bash
.venv/bin/python process_call.py call1.m4a call2.mp3          # extract + append
.venv/bin/python process_call.py call.m4a --dry-run           # preview only
.venv/bin/python process_call.py call.m4a --phone 9876543210  # set the phone number
.venv/bin/python process_call.py notes.txt --transcript       # already have text
```

## Files
| file | role |
|---|---|
| `app.py` | Streamlit upload UI |
| `process_call.py` | CLI entrypoint |
| `transcription.py` | OpenAI Whisper wrapper (25 MB/file limit guard) |
| `extraction.py` | Gemini call + prompt + strict-JSON parse + retry |
| `sheets_writer.py` | 4-column append via gspread (+ transient-error retry) |
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
