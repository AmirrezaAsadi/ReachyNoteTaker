"""Markdown note storage with tag index and full-text search index."""

from __future__ import annotations

import json
import os
import re
from datetime import date, datetime
from pathlib import Path
from typing import Optional

import yaml
from dotenv import load_dotenv

load_dotenv()

NOTES_DIR = Path(os.path.expanduser(os.getenv("NOTES_DIR", "~/voice-notes")))
TAG_INDEX = NOTES_DIR / "tags" / "index.json"
SEARCH_INDEX = NOTES_DIR / "search-index.json"

FRONTMATTER_RE = re.compile(r"^---\n(.*?)\n---\n(.*)$", re.DOTALL)


def _ensure_dirs():
    (NOTES_DIR / "tags").mkdir(parents=True, exist_ok=True)
    if not TAG_INDEX.exists():
        TAG_INDEX.write_text("{}")
    if not SEARCH_INDEX.exists():
        SEARCH_INDEX.write_text("{}")


def _slugify(text: str) -> str:
    s = re.sub(r"[^\w\s-]", "", text.lower()).strip()
    return re.sub(r"[\s_-]+", "-", s)[:48] or "note"


def _today_dir(d: Optional[date] = None) -> Path:
    d = d or date.today()
    p = NOTES_DIR / d.isoformat()
    p.mkdir(parents=True, exist_ok=True)
    return p


def _next_note_number(day_dir: Path) -> int:
    nums = []
    for f in day_dir.glob("note-*.md"):
        m = re.match(r"note-(\d+)-", f.name)
        if m:
            nums.append(int(m.group(1)))
    return (max(nums) + 1) if nums else 1


def save_note(
    content: str,
    title: str,
    tags: Optional[list[str]] = None,
    *,
    summary: str = "",
    duration: float = 0.0,
) -> Path:
    _ensure_dirs()
    day_dir = _today_dir()
    n = _next_note_number(day_dir)
    filename = f"note-{n:03d}-{_slugify(title)}.md"
    path = day_dir / filename

    fm = {
        "title": title,
        "date": datetime.now().isoformat(timespec="seconds"),
        "tags": tags or [],
        "summary": summary,
        "duration": round(duration, 1),
        "word_count": len(content.split()),
    }
    body = "---\n" + yaml.safe_dump(fm, sort_keys=False).strip() + "\n---\n\n" + content.strip() + "\n"
    path.write_text(body)

    update_tag_index(path, fm["tags"])
    _index_note(path, fm, content)
    return path


def load_note(filepath: str | Path) -> dict:
    path = Path(filepath)
    raw = path.read_text()
    m = FRONTMATTER_RE.match(raw)
    if not m:
        return {"path": str(path), "frontmatter": {}, "body": raw}
    fm = yaml.safe_load(m.group(1)) or {}
    return {"path": str(path), "frontmatter": fm, "body": m.group(2).strip()}


def search_notes(query: str) -> list[dict]:
    _ensure_dirs()
    idx = json.loads(SEARCH_INDEX.read_text() or "{}")
    q = query.lower()
    hits = []
    for path, entry in idx.items():
        hay = (entry.get("title", "") + " " + entry.get("body", "")).lower()
        if q in hay:
            hits.append({"path": path, **entry})
    hits.sort(key=lambda e: e.get("date", ""), reverse=True)
    return hits


def list_notes(date: Optional[str] = None, tag: Optional[str] = None) -> list[Path]:
    _ensure_dirs()
    if date:
        day_dir = NOTES_DIR / date
        files = sorted(day_dir.glob("note-*.md")) if day_dir.exists() else []
    else:
        files = sorted(NOTES_DIR.glob("*/note-*.md"))

    if tag:
        tag_idx = json.loads(TAG_INDEX.read_text() or "{}")
        keep = set(tag_idx.get(tag, []))
        files = [f for f in files if str(f) in keep]
    return files


def get_session_summary(date: str) -> Optional[Path]:
    p = NOTES_DIR / date / "session-summary.md"
    return p if p.exists() else None


def update_tag_index(filepath: Path, tags: list[str]) -> None:
    _ensure_dirs()
    idx = json.loads(TAG_INDEX.read_text() or "{}")
    s = str(filepath)
    for t in tags:
        idx.setdefault(t, [])
        if s not in idx[t]:
            idx[t].append(s)
    TAG_INDEX.write_text(json.dumps(idx, indent=2))


def _index_note(path: Path, frontmatter: dict, body: str) -> None:
    idx = json.loads(SEARCH_INDEX.read_text() or "{}")
    idx[str(path)] = {
        "title": frontmatter.get("title", ""),
        "date": frontmatter.get("date", ""),
        "tags": frontmatter.get("tags", []),
        "summary": frontmatter.get("summary", ""),
        "body": body,
    }
    SEARCH_INDEX.write_text(json.dumps(idx))


def build_search_index() -> int:
    _ensure_dirs()
    idx = {}
    for f in NOTES_DIR.glob("*/note-*.md"):
        n = load_note(f)
        idx[str(f)] = {
            "title": n["frontmatter"].get("title", ""),
            "date": n["frontmatter"].get("date", ""),
            "tags": n["frontmatter"].get("tags", []),
            "summary": n["frontmatter"].get("summary", ""),
            "body": n["body"],
        }
    SEARCH_INDEX.write_text(json.dumps(idx))
    return len(idx)
