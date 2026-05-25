#!/usr/bin/env python3
"""Build an offline civil engineering literature metadata corpus from OpenAlex."""

from __future__ import annotations

import argparse
import gzip
import json
import time
import urllib.parse
import urllib.request
from datetime import datetime, timezone
from pathlib import Path


OPENALEX_WORKS = "https://api.openalex.org/works"
DEFAULT_FILTER = "primary_topic.subfield.id:2205"
DEFAULT_SELECT = ",".join(
    [
        "id",
        "doi",
        "title",
        "publication_year",
        "publication_date",
        "type",
        "language",
        "authorships",
        "primary_location",
        "open_access",
        "cited_by_count",
        "primary_topic",
        "updated_date",
    ]
)

THEME_KEYWORDS = {
    "building-structure-seismic": [
        "reinforced concrete",
        "frame",
        "shear wall",
        "seismic",
        "earthquake",
        "lateral load",
        "ductility",
        "story drift",
    ],
    "steel-composite": ["steel", "composite", "buckling", "stability", "connection", "weld", "bolt"],
    "geotechnical-foundation": [
        "geotechnical",
        "soil",
        "foundation",
        "pile",
        "slope",
        "retaining",
        "excavation",
        "liquefaction",
    ],
    "bridge": ["bridge", "girder", "cable-stayed", "suspension", "deck", "prestressed"],
    "road-traffic": ["pavement", "highway", "road", "traffic", "transportation", "subgrade"],
    "construction-management": ["construction management", "scheduling", "bim", "cost", "project management", "prefabricated"],
    "materials-durability": ["concrete", "durability", "corrosion", "chloride", "carbonation", "recycled aggregate", "fiber"],
    "digital-intelligent": ["digital twin", "machine learning", "finite element", "health monitoring", "optimization", "computer-aided"],
}


def default_output_dir() -> Path:
    return Path(__file__).resolve().parents[1] / "assets"


def reconstruct_abstract(index: dict | None) -> str:
    if not index:
        return ""
    words: list[tuple[int, str]] = []
    for word, positions in index.items():
        for pos in positions:
            words.append((pos, word))
    return " ".join(word for _, word in sorted(words))


def text_blob(record: dict) -> str:
    parts = [record.get("title") or "", record.get("abstract") or "", record.get("primary_topic") or ""]
    parts.extend(record.get("topics") or [])
    parts.extend(record.get("keywords") or [])
    return " ".join(parts).lower()


def classify_themes(record: dict) -> list[str]:
    blob = text_blob(record)
    themes = []
    for theme, keywords in THEME_KEYWORDS.items():
        if any(keyword in blob for keyword in keywords):
            themes.append(theme)
    return themes or ["civil-structural-general"]


def first_source(location: dict | None) -> dict:
    if not location:
        return {}
    source = location.get("source") or {}
    return {
        "venue": source.get("display_name") or location.get("raw_source_name") or "",
        "publisher": source.get("host_organization_name") or "",
        "landing_page_url": location.get("landing_page_url") or "",
        "pdf_url": location.get("pdf_url") or "",
    }


def normalize_work(work: dict, retrieved_at: str) -> dict:
    location = first_source(work.get("primary_location"))
    open_access = work.get("open_access") or {}
    topic = work.get("primary_topic") or {}
    topics = [t.get("display_name") for t in work.get("topics") or [] if t.get("display_name")]
    keywords = [k.get("display_name") for k in work.get("keywords") or [] if k.get("display_name")]
    authors = []
    for authorship in work.get("authorships") or []:
        author = authorship.get("author") or {}
        name = author.get("display_name")
        if name:
            authors.append(name)
        if len(authors) >= 12:
            break

    record = {
        "id": work.get("id"),
        "doi": work.get("doi") or "",
        "title": work.get("title") or "",
        "year": work.get("publication_year"),
        "publication_date": work.get("publication_date") or "",
        "type": work.get("type") or "",
        "language": work.get("language") or "",
        "authors": authors,
        "venue": location["venue"],
        "publisher": location["publisher"],
        "cited_by_count": work.get("cited_by_count") or 0,
        "is_oa": bool(open_access.get("is_oa")),
        "oa_status": open_access.get("oa_status") or "",
        "landing_page_url": location["landing_page_url"],
        "pdf_url": location["pdf_url"],
        "primary_topic": topic.get("display_name") or "",
        "topics": topics[:8],
        "keywords": keywords[:16],
        "abstract": reconstruct_abstract(work.get("abstract_inverted_index")),
        "source": "openalex",
        "retrieved_at": retrieved_at,
    }
    record["themes"] = classify_themes(record)
    return record


def fetch_json(url: str, user_agent: str, retries: int = 4) -> dict:
    for attempt in range(retries):
        request = urllib.request.Request(url, headers={"User-Agent": user_agent})
        try:
            with urllib.request.urlopen(request, timeout=60) as response:
                return json.loads(response.read().decode("utf-8"))
        except Exception:
            if attempt == retries - 1:
                raise
            time.sleep(2**attempt)
    raise RuntimeError("unreachable")


def build_url(args: argparse.Namespace, cursor: str) -> str:
    params = {
        "filter": args.filter,
        "sort": args.sort,
        "per-page": str(args.per_page),
        "cursor": cursor,
        "select": DEFAULT_SELECT,
    }
    if args.mailto:
        params["mailto"] = args.mailto
    return OPENALEX_WORKS + "?" + urllib.parse.urlencode(params)


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--target", type=int, default=20000, help="minimum unique records to collect")
    parser.add_argument("--output-dir", type=Path, default=default_output_dir())
    parser.add_argument("--filter", default=DEFAULT_FILTER, help="OpenAlex filter expression")
    parser.add_argument("--sort", default="cited_by_count:desc")
    parser.add_argument("--per-page", type=int, default=200)
    parser.add_argument("--mailto", default="", help="email for OpenAlex polite pool")
    parser.add_argument("--sleep", type=float, default=0.15, help="seconds between requests")
    args = parser.parse_args()

    args.output_dir.mkdir(parents=True, exist_ok=True)
    output_path = args.output_dir / "openalex_civil_engineering_works.jsonl.gz"
    temp_path = args.output_dir / "openalex_civil_engineering_works.jsonl"
    manifest_path = args.output_dir / "openalex_civil_engineering_manifest.json"
    retrieved_at = datetime.now(timezone.utc).isoformat()
    user_agent = "civil-engineering-thesis-kb/1.0"
    if args.mailto:
        user_agent += f" (mailto:{args.mailto})"

    seen: set[str] = set()
    count = 0
    cursor = "*"
    pages = 0
    api_count = None

    with temp_path.open("w", encoding="utf-8") as fh:
        while count < args.target:
            data = fetch_json(build_url(args, cursor), user_agent=user_agent)
            pages += 1
            api_count = data.get("meta", {}).get("count", api_count)
            results = data.get("results") or []
            if not results:
                break
            for work in results:
                work_id = work.get("id")
                if not work_id or work_id in seen:
                    continue
                seen.add(work_id)
                record = normalize_work(work, retrieved_at)
                if not record["title"]:
                    continue
                fh.write(json.dumps(record, ensure_ascii=False, sort_keys=True) + "\n")
                count += 1
                if count >= args.target:
                    break
            cursor = data.get("meta", {}).get("next_cursor")
            if not cursor:
                break
            time.sleep(args.sleep)
            if pages % 10 == 0:
                fh.flush()
                print(f"collected={count} pages={pages}", flush=True)

    with temp_path.open("rb") as src, gzip.open(output_path, "wb") as dst:
        for chunk in iter(lambda: src.read(1024 * 1024), b""):
            dst.write(chunk)
    temp_path.unlink(missing_ok=True)

    manifest = {
        "name": "openalex_civil_engineering_works",
        "records": count,
        "target": args.target,
        "source": "https://api.openalex.org/works",
        "filter": args.filter,
        "sort": args.sort,
        "api_reported_count": api_count,
        "retrieved_at": retrieved_at,
        "output": str(output_path),
        "license_note": "OpenAlex metadata; this corpus stores metadata and links, not copyrighted full-text PDFs.",
        "fields_reference": "references/schema.md",
    }
    manifest_path.write_text(json.dumps(manifest, ensure_ascii=False, indent=2), encoding="utf-8")
    print(json.dumps(manifest, ensure_ascii=False, indent=2))
    if count < args.target:
        raise SystemExit(f"Only collected {count} records; target was {args.target}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
