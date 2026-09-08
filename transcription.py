"""Audio file -> transcript text, via the OpenAI transcription API."""
from pathlib import Path

from openai import OpenAI

_MAX_BYTES = 25 * 1024 * 1024  # OpenAI hard limit per request


def transcribe(audio_path: str, api_key: str, model: str = "whisper-1") -> str:
    p = Path(audio_path)
    if not p.exists():
        raise FileNotFoundError(audio_path)
    if p.stat().st_size > _MAX_BYTES:
        raise ValueError(
            f"{p.name} is {p.stat().st_size / 1e6:.1f} MB, over the 25 MB API limit. "
            "Compress it (e.g. `ffmpeg -i in.m4a -b:a 32k -ac 1 out.mp3`) or split it."
        )

    client = OpenAI(api_key=api_key)
    with p.open("rb") as fh:
        resp = client.audio.transcriptions.create(
            model=model,
            file=fh,
            response_format="text",
            prompt="Technical interview debrief call. Indian-accented English, some Hindi. "
                   "Terms: DSA, Kafka, SQL, API, LLD, HLD, Spring Boot, sliding window.",
        )
    return resp if isinstance(resp, str) else resp.text
