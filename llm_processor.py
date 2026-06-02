"""LLM-driven cleaning, structuring, titling, summarizing, and command detection.

All functions hit a local llama-server's OpenAI-compatible /v1/chat/completions
endpoint. The server is launched by run.sh.
"""

from __future__ import annotations

import json
import os
import re
from typing import Optional

import httpx
from dotenv import load_dotenv

load_dotenv()

SERVER_PORT = int(os.getenv("SERVER_PORT", "8080"))
BASE_URL = f"http://127.0.0.1:{SERVER_PORT}/v1"
TIMEOUT = httpx.Timeout(60.0, connect=5.0)

VOICE_COMMANDS = {
    "new_note": [r"\bnew note\b", r"\bstart (a )?new note\b"],
    "save_note": [r"\bsave note\b", r"\bsave (this|that|the) note\b"],
    "read_back": [r"\bread (it )?back\b", r"\bread (this|that|the) note\b"],
    "summarize": [r"\bsummarize\b", r"\bsummary\b"],
    "cancel": [r"\bcancel\b", r"\bdiscard\b", r"\bnever mind\b"],
}
TAG_PATTERN = re.compile(r"\badd tag ([\w-]+)\b", re.IGNORECASE)


def _chat(system: str, user: str, *, max_tokens: int = 512, temperature: float = 0.2) -> str:
    payload = {
        "model": "local",
        "messages": [
            {"role": "system", "content": system},
            {"role": "user", "content": user},
        ],
        "max_tokens": max_tokens,
        "temperature": temperature,
    }
    with httpx.Client(timeout=TIMEOUT) as client:
        r = client.post(f"{BASE_URL}/chat/completions", json=payload)
        r.raise_for_status()
        return r.json()["choices"][0]["message"]["content"].strip()


def clean_transcript(raw_text: str) -> str:
    system = (
        "You clean up raw speech-to-text transcripts. Remove filler words "
        "(um, uh, like, you know, sort of, kind of) when they don't carry meaning. "
        "Fix punctuation and capitalization. Do NOT paraphrase. Do NOT add information. "
        "Preserve the speaker's words. Return only the cleaned text, no preface."
    )
    return _chat(system, raw_text, max_tokens=len(raw_text.split()) * 3 + 64)


def structure_note(text: str) -> str:
    system = (
        "You format spoken notes into clean markdown. Rules:\n"
        "- Detect natural sections and add `## Heading` lines where appropriate.\n"
        "- Convert lists into `- bullet` form.\n"
        "- Prefix any action item with `TODO: `.\n"
        "- Preserve dates and numbers exactly.\n"
        "- Do NOT invent content. If the input is a single paragraph, leave it as a paragraph.\n"
        "Return only the markdown body, no code fences."
    )
    return _chat(system, text, max_tokens=1024)


def generate_title(text: str) -> str:
    system = (
        "Write a short descriptive title (3–7 words) for the note below. "
        "Return only the title, no quotes, no trailing punctuation."
    )
    title = _chat(system, text, max_tokens=32, temperature=0.3)
    # Normalize
    title = title.strip().strip('"').strip("'").rstrip(".")
    return title or "Untitled note"


def summarize_session(notes_list: list[str]) -> str:
    joined = "\n\n---\n\n".join(notes_list)
    system = (
        "You write end-of-session summaries for a notebook. "
        "Produce a concise 3–6 sentence summary covering the main themes and any TODOs. "
        "Return plain markdown."
    )
    return _chat(system, joined, max_tokens=512, temperature=0.3)


def detect_voice_command(text: str) -> Optional[dict]:
    """Return {'command': str, 'arg': str|None} or None.

    Pure-regex fast path; no LLM call needed for the common cases.
    """
    t = text.strip().lower()
    if not t:
        return None

    # Tag has an argument
    m = TAG_PATTERN.search(t)
    if m:
        return {"command": "add_tag", "arg": m.group(1)}

    for name, patterns in VOICE_COMMANDS.items():
        for pat in patterns:
            if re.search(pat, t):
                return {"command": name, "arg": None}

    return None


if __name__ == "__main__":
    # Smoke test against a running server
    sample = "um so today I want to like talk about the new project uh it's about robots"
    print("clean:", clean_transcript(sample))
    print("title:", generate_title(sample))
    print("command:", json.dumps(detect_voice_command("save note")))
