"""CLI driver for ./search.sh"""

from __future__ import annotations

from datetime import date

import click
from rich.console import Console
from rich.table import Table

import note_store

console = Console()


@click.command()
@click.argument("query", required=False, default="")
@click.option("--tag", default=None, help="Filter by tag")
@click.option("--date", "date_", default=None, help="Filter by YYYY-MM-DD")
@click.option("--today", is_flag=True, help="Show today's notes")
def main(query, tag, date_, today):
    if today:
        date_ = date.today().isoformat()

    if query:
        hits = note_store.search_notes(query)
        if tag:
            hits = [h for h in hits if tag in h.get("tags", [])]
        if date_:
            hits = [h for h in hits if h.get("date", "").startswith(date_)]
        _render_hits(hits, f'query="{query}"')
    else:
        files = note_store.list_notes(date=date_, tag=tag)
        rows = []
        for f in files:
            n = note_store.load_note(f)
            fm = n["frontmatter"]
            rows.append(
                {
                    "path": str(f),
                    "title": fm.get("title", ""),
                    "date": fm.get("date", ""),
                    "tags": fm.get("tags", []),
                    "summary": fm.get("summary", ""),
                }
            )
        _render_hits(rows, "listing")


def _render_hits(hits, label):
    t = Table(title=f"Notes — {label} ({len(hits)})")
    t.add_column("Date", style="cyan")
    t.add_column("Title", style="bold")
    t.add_column("Tags", style="magenta")
    t.add_column("Path", style="dim")
    for h in hits:
        t.add_row(
            (h.get("date") or "")[:19],
            h.get("title", ""),
            ", ".join(h.get("tags", [])),
            h["path"],
        )
    console.print(t)


if __name__ == "__main__":
    main()
