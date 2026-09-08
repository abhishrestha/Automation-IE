"""Transcript -> round-wise interview questions (JSON), via the Google Gemini API.

Output is intentionally minimal: a flat list of {round, question} rows. No
module/topic classification, no rejection reasons — just the questions, one per
row, expanded into clear self-contained sentences.
"""
import json

from google import genai
from google.genai import types

SYSTEM_PROMPT = """You document technical-interview debrief calls. A caller talks with a \
learner about the interview rounds they went through. From the transcript, produce one \
row per distinct interview question the learner was asked.

Rules:
- ONE row per question. Never group multiple questions into one row.
- Never leave shorthand ("DSA: sliding window question"). Expand every question into a \
clear, fully-written, self-contained sentence that a reader with no context can understand.
- Include natural follow-up questions as their own row, in the same round, in the order asked.
- Keep rounds in order. Label them "R1", "R2", "R3", ... in the order they occurred.
- Only include questions actually asked in an interview round. Ignore small talk, \
scheduling, salary talk, and the caller's own commentary.

Example:
  Input:  "Round 1: DSA: Balance and parenthesis type question. Other: SQL query. Kafka basics, partitioning."
  Output rows:
    R1 -> "Solve a balanced parentheses problem: determine whether a string of brackets ()[]{} is balanced."
    R1 -> "Write an SQL query based on a given requirement (likely involving filtering, joins, or aggregation)."
    R1 -> "Explain the basics of Kafka - what is a topic, broker, producer, and consumer?"
    R1 -> "How does Kafka partitioning work, and why is it used?"

Return STRICT JSON only, no prose, no markdown fences:
{"rows": [{"round": "R1", "question": "Full self-contained question text"}]}
"""

_RESPONSE_SCHEMA = {
    "type": "object",
    "properties": {
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
    "required": ["rows"],
}


class ExtractionError(RuntimeError):
    pass


def _parse(text: str) -> list[dict]:
    text = (text or "").strip()
    if text.startswith("```"):
        text = text.split("\n", 1)[1].rsplit("```", 1)[0]
    start, end = text.find("{"), text.rfind("}")
    if start == -1 or end == -1:
        raise ExtractionError(f"No JSON object in model output:\n{text[:500]}")
    rows = json.loads(text[start:end + 1]).get("rows", [])
    clean = []
    for i, r in enumerate(rows):
        rnd = str(r.get("round", "")).strip()
        q = str(r.get("question", "")).strip()
        if not rnd or not q:
            raise ExtractionError(f"row {i} missing round/question: {r!r}")
        clean.append({"round": rnd, "question": q})
    if not clean:
        raise ExtractionError("Model returned zero question rows")
    return clean


def extract_questions(transcript: str, api_key: str, model: str = "gemini-2.5-flash",
                      max_tokens: int = 8000, max_retries: int = 2) -> list[dict]:
    client = genai.Client(api_key=api_key)
    cfg = types.GenerateContentConfig(
        system_instruction=SYSTEM_PROMPT,
        max_output_tokens=max_tokens,
        temperature=0,
        response_mime_type="application/json",
        response_schema=_RESPONSE_SCHEMA,
    )
    prompt = f"Transcript:\n\n{transcript}"
    last_err = None
    for attempt in range(max_retries + 1):
        resp = client.models.generate_content(model=model, contents=prompt, config=cfg)
        try:
            return _parse(resp.text)
        except (ExtractionError, json.JSONDecodeError) as e:
            last_err = e
            prompt = (f"{prompt}\n\nYour previous answer failed: {e}\n"
                      "Return corrected STRICT JSON only, matching {\"rows\":[{\"round\",\"question\"}]}.")
    raise ExtractionError(f"Extraction failed after {max_retries + 1} attempts: {last_err}")
