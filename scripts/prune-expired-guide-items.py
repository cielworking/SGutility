"""Remove expired HTML elements tagged with data-expires="YYYY-MM-DD" across guides."""
from __future__ import annotations

import datetime as dt
import pathlib
import re

ROOT = pathlib.Path(__file__).resolve().parents[1]
SGT = dt.timezone(dt.timedelta(hours=8))
PATTERN = re.compile(
    r'[ \t]*<(?P<tag>tr|li|div|p|section)\b[^>]*\bdata-expires="(?P<date>\d{4}-\d{2}-\d{2})"[^>]*>.*?</(?P=tag)>[ \t]*\r?\n?',
    re.DOTALL,
)


def prune_file(path: pathlib.Path, today_iso: str) -> int:
    text = path.read_text(encoding="utf-8")
    removed = 0

    def _replace(match: re.Match[str]) -> str:
        nonlocal removed
        if today_iso > match.group("date"):
            removed += 1
            return ""
        return match.group(0)

    updated = PATTERN.sub(_replace, text)
    if removed and updated != text:
        path.write_text(updated, encoding="utf-8", newline="")
    return removed


def main() -> None:
    today_iso = dt.datetime.now(SGT).strftime("%Y-%m-%d")
    total = 0
    for html_file in sorted((ROOT / "guides").glob("*.html")):
        count = prune_file(html_file, today_iso)
        if count:
            print(f"Pruned {count} expired item(s) from {html_file.relative_to(ROOT)}")
            total += count
    print(f"Done ({today_iso} SGT): {total} expired item(s) removed.")


if __name__ == "__main__":
    main()
