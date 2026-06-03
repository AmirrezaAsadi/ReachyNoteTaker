"""Barnaby Bat persona — in-character LLM replies via local llama-server.

Loads the character profile and maintains multi-turn conversation history,
calling the local Gemma model (OpenAI-compatible endpoint) to generate
friendly, in-character responses.
"""

from __future__ import annotations

import os
from pathlib import Path

import httpx
from dotenv import load_dotenv

load_dotenv()

SERVER_PORT = int(os.getenv("SERVER_PORT", "8080"))
BASE_URL = f"http://127.0.0.1:{SERVER_PORT}/v1"
TIMEOUT = httpx.Timeout(60.0, connect=5.0)

PROFILE_PATH = Path(__file__).parent / "assets" / "Barnaby_Bat_Profile.md"


def _load_profile() -> str:
    try:
        return PROFILE_PATH.read_text()
    except FileNotFoundError:
        return "Barnaby is a friendly Big Brown Bat from Cincinnati, Ohio."


SYSTEM_PROMPT = f"""You are Barnaby, a friendly Big Brown Bat from Cincinnati, Ohio. \
You are a gentle, cheerful, slightly anxious-but-brave nighttime superhero who eats \
bugs and just wants humans to know bats are kind neighbors, not scary.

Stay fully in character as Barnaby at all times. Speak warmly and simply, like you're \
talking to a curious friend (often a child who might be a little nervous about bats). \
Be encouraging and reassuring. Use occasional gentle bat facts from your profile. \
Keep replies short and spoken-friendly: 2-4 sentences, no markdown, no lists, no emojis \
in the spoken text. Never break character or mention that you are an AI or a language model.

Here is everything about you:

{_load_profile()}
"""


class BarnabyConversation:
    """Maintains conversation history and generates in-character replies."""

    def __init__(self, max_history: int = 12):
        self.max_history = max_history
        self.history: list[dict] = []

    def reply(self, user_text: str) -> str:
        self.history.append({"role": "user", "content": user_text})
        messages = [{"role": "system", "content": SYSTEM_PROMPT}] + self.history[-self.max_history :]

        payload = {
            "model": "local",
            "messages": messages,
            "max_tokens": 200,
            "temperature": 0.8,
            # Gemma 4 E4B is a reasoning model; disable thinking so the reply
            # lands in `content` instead of `reasoning_content`.
            "chat_template_kwargs": {"enable_thinking": False},
        }
        with httpx.Client(timeout=TIMEOUT) as client:
            r = client.post(f"{BASE_URL}/chat/completions", json=payload)
            r.raise_for_status()
            msg = r.json()["choices"][0]["message"]
            text = (msg.get("content") or msg.get("reasoning_content") or "").strip()

        self.history.append({"role": "assistant", "content": text})
        return text

    def greeting(self) -> str:
        """A fixed in-character opening line (no LLM call needed)."""
        return (
            "Oh, hello there, friend! I'm Barnaby, your friendly neighborhood bat. "
            "Don't be scared, I'm much more afraid of you than you are of me! "
            "What would you like to chat about?"
        )
