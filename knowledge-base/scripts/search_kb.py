#!/usr/bin/env python3
"""Search the local civil engineering literature metadata corpus."""

from __future__ import annotations

import argparse
import gzip
import json
import re
import sys
from pathlib import Path


def default_kb_path() -> Path:
    return Path(__file__).resolve().parents[1] / "assets" / "openalex_civil_engineering_works.jsonl.gz"


def tokenize(text: str) -> list[str]:
    return [t.lower() for t in re.findall(r"[\w\-]+", text, flags=re.UNICODE) if len(t) > 1]


def score_record(record: dict, terms: list[str]) -> int:
    title = (record.get("title") or "").lower()
    abstract = (record.get("abstract") or "").lower()
    topics = " ".join(record.get("topics") or []).lower()
    keywords = " ".join(record.get("keywords") or []).lower()
    themes = " ".join(record.get("themes") or []).lower()
    score = 0
    for term in terms:
        if term in title:
            score += 8
        if term in keywords:
            score += 5
        if term in topics or term in themes:
            score += 4
        if term in abstract:
            score += 1
    score += min(int(record.get("cited_by_count") or 0) // 100, 10)
    if record.get("is_oa"):
        score += 1
    return score


def iter_records(path: Path):
    opener = gzip.open if path.suffix == ".gz" else open
    with opener(path, "rt", encoding="utf-8") as fh:
        for line in fh:
            if line.strip():
                yield json.loads(line)


def main() -> int:
    if hasattr(sys.stdout, "reconfigure"):
        sys.stdout.reconfigure(encoding="utf-8", errors="replace")

    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--query", required=True)
    parser.add_argument("--kb", type=Path, default=default_kb_path())
    parser.add_argument("--limit", type=int, default=10)
    parser.add_argument("--theme", default="")
    parser.add_argument("--year-from", type=int, default=0)
    parser.add_argument("--year-to", type=int, default=9999)
    parser.add_argument("--json", action="store_true", help="print JSON lines")
    args = parser.parse_args()

    if not args.kb.exists():
        raise SystemExit(f"Knowledge base not found: {args.kb}")

    terms = tokenize(args.query)
    scored = []
    for record in iter_records(args.kb):
        year = record.get("year") or 0
        if year < args.year_from or year > args.year_to:
            continue
        if args.theme and args.theme not in (record.get("themes") or []):
            continue
        score = score_record(record, terms)
        if score > 0:
            scored.append((score, record))

    scored.sort(key=lambda item: (item[0], item[1].get("cited_by_count") or 0), reverse=True)
    for score, record in scored[: args.limit]:
        if args.json:
            item = dict(record)
            item["_score"] = score
            print(json.dumps(item, ensure_ascii=False, sort_keys=True))
            continue
        authors = ", ".join(record.get("authors") or [])
        url = record.get("doi") or record.get("landing_page_url") or record.get("id")
        print(f"[{score}] {record.get('title')} ({record.get('year')})")
        print(f"  Authors: {authors}")
        print(f"  Venue: {record.get('venue')} | Cited: {record.get('cited_by_count')} | OA: {record.get('oa_status')}")
        print(f"  Themes: {', '.join(record.get('themes') or [])}")
        print(f"  URL: {url}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
