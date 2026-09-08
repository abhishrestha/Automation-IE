"""Transcript -> structured call result (JSON), via the Google Gemini API.

Returns, per call:
  {
    "phone_number": "digits only, or ''",
    "reason_for_rejection": "readable phrase",
    "rows": [{"round": "R1", "question": "..."}, ...]   # may be empty
  }

Design notes:
- These are debrief calls with candidates who interviewed at some company.
- The transcript is machine-generated and may contain spelling / word errors,
  especially for technical terms and names — infer intelligently, don't quote blindly.
- If NO interview questions can be recovered, return an empty "rows" list. That is
  not an error; the caller writes a "No questions collected" row instead.
"""
import json
import re

from google import genai
from google.genai import types

SYSTEM_PROMPT = """You document debrief calls. On each call, a caller speaks with a \
candidate who recently interviewed at a company. Your job is to reconstruct, accurately \
and completely, EVERY interview question the candidate was asked, plus the outcome.

The transcript is auto-generated speech-to-text: expect misspellings, wrong word splits, \
and garbled technical terms (e.g. "load code" -> "LeetCode", "cabka" -> "Kafka", \
"dsa" -> "DSA", "system decide" -> "system design"). Interpret intent; do not copy errors.

=== QUESTIONS ===
- Extract one row per DISTINCT question actually asked in an interview round. This \
includes coding/DSA problems, CS theory, language/framework questions, system/LLD design, \
SQL, project deep-dives, and behavioral/HR questions.
- Include natural follow-up questions as their own row, same round, in order asked.
- NEVER group multiple questions into one row. NEVER leave shorthand — expand each into a \
clear, self-contained sentence understandable with zero context. Keep the technical \
substance precise (name the exact algorithm/pattern/topic when the candidate states it).
- Do NOT invent questions that were not discussed. If the candidate is vague ("some array \
question"), write the most faithful version you can and keep it appropriately general.
- Rounds: label "R1", "R2", "R3"... in the order they happened. If the candidate never \
separates rounds, put everything in "R1".
- Ignore scheduling talk, salary talk, pleasantries, and the caller's own commentary.

Example:
  Input:  "first round was online, load code medium, balance parenthesis. then they asked sql query and some cabka questions"
  Rows:
    R1 -> "Solve a LeetCode-medium problem: given a string of brackets ()[]{}, determine whether it is balanced."
    R1 -> "Write an SQL query for a given requirement (filtering / joins / aggregation)."
    R1 -> "Answer basic Kafka questions - topics, brokers, producers, consumers."

=== PHONE NUMBER ===
Set "phone_number" to the candidate's phone number ONLY if it is clearly stated on the \
call (digits only, keep country code if given). Otherwise "".

=== REASON FOR REJECTION ===
Set "reason_for_rejection" to a short, readable phrase describing the outcome:
- If the candidate was rejected and a reason is given or clearly implied, state it \
plainly and specifically, e.g. "Rejected - weak on system design fundamentals", \
"Rejected - could not optimise the DSA solution", "Rejected - communication issues in HR round".
- If the candidate was rejected but NO reason is stated or implied anywhere -> exactly \
"Company Unresponsive".
- If the candidate cleared the process / got an offer / is still in process -> state that, \
e.g. "Selected", "Cleared all rounds - offer awaited", "In process - next round pending".

=== OUTPUT ===
STRICT JSON only, no prose, no markdown fences:
{"phone_number": "", "reason_for_rejection": "", "rows": [{"round": "R1", "question": "..."}]}
"""

_RESPONSE_SCHEMA = {
    "type": "object",
    "properties": {
        "phone_number": {"type": "string"},
        "reason_for_rejection": {"type": "string"},
        "rows": {
            "type": "array",
            "items": {
                "type": "object",
                "properties": {
                    "round": {"type": "string"},
                    "question": {"type": "string"},
                },
                "required": ["round", "question"],
            },
        },
    },
    "required": ["phone_number", "reason_for_rejection", "rows"],
}

DEFAULT_REASON = "Company Unresponsive"


class ExtractionError(RuntimeError):
    pass


def normalize_phone(value: str) -> str:
    """Keep digits; drop a leading country-code 91 / 0 so numbers compare cleanly."""
    digits = re.sub(r"\D", "", value or "")
    if len(digits) > 10 and digits.startswith("91"):
        digits = digits[-10:]
    elif len(digits) == 11 and digits.startswith("0"):
        digits = digits[1:]
    return digits


def detect_phone_from_name(filename: str) -> str:
    m = re.search(r"(\+?\d[\d\s\-]{8,}\d)", filename or "")
    return normalize_phone(m.group(1)) if m else ""


def _parse(text: str) -> dict:
    text = (text or "").strip()
    if text.startswith("```"):
        text = text.split("\n", 1)[1].rsplit("```", 1)[0]
    start, end = text.find("{"), text.rfind("}")
    if start == -1 or end == -1:
        raise ExtractionError(f"No JSON object in model output:\n{text[:500]}")
    data = json.loads(text[start:end + 1])

    rows = []
    for r in data.get("rows", []) or []:
        rnd = str(r.get("round", "")).strip() or "R1"
        q = str(r.get("question", "")).strip()
        if q:
            rows.append({"round": rnd, "question": q})

    reason = str(data.get("reason_for_rejection", "")).strip() or DEFAULT_REASON
    return {
        "phone_number": normalize_phone(str(data.get("phone_number", ""))),
        "reason_for_rejection": reason,
        "rows": rows,
    }


def extract_call(transcript: str, api_key: str, model: str = "gemini-2.5-pro",
                 max_tokens: int = 8000, max_retries: int = 2) -> dict:
    client = genai.Client(api_key=api_key)
    cfg = types.GenerateContentConfig(
        system_instruction=SYSTEM_PROMPT,
        max_output_tokens=max_tokens,
        temperature=0,
        response_mime_type="application/json",
        response_schema=_RESPONSE_SCHEMA,
    )
    prompt = f"Debrief call transcript:\n\n{transcript}"
    last_err = None
    for attempt in range(max_retries + 1):
        resp = client.models.generate_content(model=model, contents=prompt, config=cfg)
        try:
            return _parse(resp.text)
        except (ExtractionError, json.JSONDecodeError) as e:
            last_err = e
            prompt = (f"{prompt}\n\nYour previous answer failed to parse: {e}\n"
                      "Return corrected STRICT JSON only.")
    raise ExtractionError(f"Extraction failed after {max_retries + 1} attempts: {last_err}")
