from __future__ import annotations

import argparse
import csv
import json
import time
import urllib.parse
import urllib.request
from urllib.error import HTTPError, URLError
from collections import Counter, defaultdict
from pathlib import Path
from typing import Any


OPENALEX_URL = "https://api.openalex.org/works"

QUERIES: dict[str, str] = {
    "appraisal_theory": "emotion appraisal theory action tendency",
    "cognitive_appraisal": "cognitive appraisal emotion coping anger blame",
    "occ_pad_models": "OCC model PAD emotion computational agents personality",
    "affective_computing": "affective computing emotion model personality agent",
    "emotion_dynamics": "emotion dynamics emotional inertia affective chronometry",
    "personality_reactivity": "personality emotional reactivity affect dynamics neuroticism agreeableness",
    "forgiveness_repair": "interpersonal forgiveness apology repair trust transgression",
    "apology_sincerity": "apology sincerity repair quality trust restoration forgiveness",
    "anger_attribution": "anger blame intentionality attribution offense appraisal",
    "conflict_withdrawal": "demand withdraw conflict silent treatment close relationships",
    "ostracism_cold_treatment": "ostracism silent treatment social exclusion relationship conflict",
    "trust_rupture_repair": "trust repair violation apology reconciliation interpersonal",
    "interpersonal_emotion_regulation": "interpersonal emotion regulation conflict support repair",
    "attachment_relationships": "attachment anxiety avoidance conflict forgiveness relationship",
    "social_baseline_affiliation": "affiliation social closeness trust emotion regulation",
    "believable_agents": "believable emotional agents personality emotion appraisal",
    "human_chatbot_emotion": "conversational agent emotion personality affective response",
    "llm_agents_affect": "large language model emotional agent personality affect",
}

TOP_VENUES = {
    "Annual Review of Psychology",
    "Psychological Bulletin",
    "Psychological Review",
    "Psychological Science",
    "Perspectives on Psychological Science",
    "Journal of Personality and Social Psychology",
    "Personality and Social Psychology Review",
    "Personality and Social Psychology Bulletin",
    "Journal of Experimental Social Psychology",
    "Social Psychological and Personality Science",
    "Emotion",
    "Cognition and Emotion",
    "Emotion Review",
    "Journal of Research in Personality",
    "Personality and Individual Differences",
    "Journal of Social and Personal Relationships",
    "Personal Relationships",
    "Human Communication Research",
    "Communication Monographs",
    "Journal of Communication",
    "Computers in Human Behavior",
    "International Journal of Human-Computer Studies",
    "International Journal of Human-Computer Interaction",
    "ACM Transactions on Computer-Human Interaction",
    "Proceedings of the ACM on Human-Computer Interaction",
    "CHI Conference on Human Factors in Computing Systems",
    "Proceedings of the SIGCHI Conference on Human Factors in Computing Systems",
    "Artificial Intelligence",
    "AI Magazine",
    "Autonomous Agents and Multi-Agent Systems",
    "Cognitive Systems Research",
    "Trends in Cognitive Sciences",
    "Nature Human Behaviour",
    "PNAS",
    "Proceedings of the National Academy of Sciences",
}

THEME_KEYWORDS: dict[str, tuple[str, ...]] = {
    "appraisal_and_action_tendency": (
        "appraisal",
        "action tendency",
        "action readiness",
        "coping",
        "control",
        "certainty",
    ),
    "personality_and_emotion_dynamics": (
        "personality",
        "neuroticism",
        "agreeableness",
        "extraversion",
        "emotional inertia",
        "emotion dynamics",
        "affective chronometry",
    ),
    "anger_blame_and_attribution": (
        "anger",
        "blame",
        "intentionality",
        "attribution",
        "offense",
        "transgression",
    ),
    "forgiveness_apology_and_repair": (
        "forgiveness",
        "apology",
        "repair",
        "reconciliation",
        "trust restoration",
        "sincerity",
    ),
    "withdrawal_cold_treatment_and_ostracism": (
        "withdraw",
        "withdrawal",
        "silent treatment",
        "ostracism",
        "social exclusion",
        "demand/withdraw",
    ),
    "affective_agents_and_chatbots": (
        "affective computing",
        "agent",
        "chatbot",
        "conversational agent",
        "believable",
        "large language model",
    ),
}


def reconstruct_abstract(index: dict[str, list[int]] | None) -> str:
    if not index:
        return ""
    words: list[tuple[int, str]] = []
    for word, positions in index.items():
        for position in positions:
            words.append((position, word))
    return " ".join(word for _, word in sorted(words))


def invert_date(value: str | None) -> str:
    return value or ""


def source_name(work: dict[str, Any]) -> str:
    source = (
        (work.get("primary_location") or {}).get("source")
        or (work.get("host_venue") or {})
        or {}
    )
    return str(source.get("display_name") or "")


def source_type(work: dict[str, Any]) -> str:
    source = (
        (work.get("primary_location") or {}).get("source")
        or (work.get("host_venue") or {})
        or {}
    )
    return str(source.get("type") or "")


def authors(work: dict[str, Any]) -> list[str]:
    names = []
    for item in work.get("authorships") or []:
        author = item.get("author") or {}
        name = author.get("display_name")
        if name:
            names.append(str(name))
    return names


def concepts(work: dict[str, Any]) -> list[str]:
    names = []
    for item in work.get("concepts") or []:
        name = item.get("display_name")
        if name:
            names.append(str(name))
    return names


def doi_url(doi: str) -> str:
    doi = doi.replace("https://doi.org/", "").strip()
    return f"https://doi.org/{doi}" if doi else ""


def fetch_openalex(
    query: str,
    *,
    per_page: int,
    max_results: int,
    mailto: str,
    sleep_seconds: float,
) -> list[dict[str, Any]]:
    results: list[dict[str, Any]] = []
    cursor = "*"
    while len(results) < max_results:
        params = {
            "search": query,
            "per-page": str(min(per_page, max_results - len(results))),
            "cursor": cursor,
            "mailto": mailto,
            "filter": "type:article|book-chapter|book|proceedings-article",
        }
        url = OPENALEX_URL + "?" + urllib.parse.urlencode(params)
        req = urllib.request.Request(
            url,
            headers={"User-Agent": f"astrbot-emotion-kb/1.0 ({mailto})"},
        )
        payload = None
        for attempt in range(5):
            try:
                with urllib.request.urlopen(req, timeout=60) as response:
                    payload = json.load(response)
                break
            except (HTTPError, URLError, TimeoutError) as exc:
                if attempt == 4:
                    raise
                wait = sleep_seconds + 1.5 * (attempt + 1)
                print(f"retry {attempt + 1}/5 for query={query!r}: {exc}; sleep={wait:.1f}s")
                time.sleep(wait)
        if payload is None:
            break
        batch = payload.get("results") or []
        if not batch:
            break
        results.extend(batch)
        cursor = (payload.get("meta") or {}).get("next_cursor")
        if not cursor:
            break
        time.sleep(sleep_seconds)
    return results


def simplify_work(work: dict[str, Any], *, query_key: str, query: str) -> dict[str, Any]:
    doi = str(work.get("doi") or "").replace("https://doi.org/", "")
    title = str(work.get("display_name") or "").strip()
    venue = source_name(work)
    abstract = reconstruct_abstract(work.get("abstract_inverted_index"))
    first_author = authors(work)[:1]
    all_authors = authors(work)
    return {
        "openalex_id": work.get("id"),
        "doi": doi,
        "doi_url": doi_url(doi),
        "title": title,
        "year": work.get("publication_year"),
        "publication_date": invert_date(work.get("publication_date")),
        "venue": venue,
        "venue_type": source_type(work),
        "authors": all_authors[:12],
        "author_count": len(all_authors),
        "first_author": first_author[0] if first_author else "",
        "cited_by_count": int(work.get("cited_by_count") or 0),
        "is_top_venue": venue in TOP_VENUES,
        "concepts": concepts(work)[:12],
        "abstract": abstract,
        "open_access": (work.get("open_access") or {}).get("is_oa"),
        "landing_page_url": (
            (work.get("primary_location") or {}).get("landing_page_url")
            or work.get("doi")
            or work.get("id")
        ),
        "query_keys": [query_key],
        "queries": [query],
    }


def merge_work(existing: dict[str, Any], incoming: dict[str, Any]) -> dict[str, Any]:
    for key in ("query_keys", "queries"):
        merged = list(dict.fromkeys(existing.get(key, []) + incoming.get(key, [])))
        existing[key] = merged
    if not existing.get("abstract") and incoming.get("abstract"):
        existing["abstract"] = incoming["abstract"]
    if incoming.get("cited_by_count", 0) > existing.get("cited_by_count", 0):
        existing["cited_by_count"] = incoming["cited_by_count"]
    existing["is_top_venue"] = bool(existing.get("is_top_venue") or incoming.get("is_top_venue"))
    return existing


def stable_key(work: dict[str, Any]) -> str:
    if work.get("doi"):
        return "doi:" + str(work["doi"]).lower()
    if work.get("openalex_id"):
        return "openalex:" + str(work["openalex_id"]).lower()
    return "title:" + str(work.get("title", "")).lower()


def classify_themes(work: dict[str, Any]) -> list[str]:
    text = " ".join(
        [
            str(work.get("title") or ""),
            str(work.get("abstract") or ""),
            " ".join(work.get("concepts") or []),
            " ".join(work.get("query_keys") or []),
        ],
    ).lower()
    themes = []
    for theme, keywords in THEME_KEYWORDS.items():
        if any(keyword.lower() in text for keyword in keywords):
            themes.append(theme)
    return themes or ["general"]


def citation(work: dict[str, Any]) -> str:
    authors_text = ", ".join(work.get("authors")[:3] or [])
    if work.get("author_count", 0) > 3:
        authors_text += ", et al."
    year = work.get("year") or "n.d."
    title = work.get("title") or "Untitled"
    venue = work.get("venue") or "Unknown venue"
    doi = work.get("doi_url") or work.get("landing_page_url") or ""
    return f"{authors_text} ({year}). {title}. {venue}. {doi}".strip()


def supported_claim_for_theme(theme: str) -> str:
    return {
        "appraisal_and_action_tendency": "Emotion should be modeled as an appraisal-driven state that changes action tendencies, not only as a discrete label.",
        "personality_and_emotion_dynamics": "A bot persona can modulate emotional baseline, inertia, reactivity and recovery speed.",
        "anger_blame_and_attribution": "Anger and boundary responses should depend on blame, intentionality, responsibility and repeated offense.",
        "forgiveness_apology_and_repair": "Forgiveness and repair should depend on apology sincerity, acknowledgement, repair effort and restored trust.",
        "withdrawal_cold_treatment_and_ostracism": "Withdrawal or cold treatment should be represented as a time-limited consequence with social-distance effects.",
        "affective_agents_and_chatbots": "Believable agents benefit from emotion, personality and context-sensitive affective response models.",
        "general": "This source provides adjacent evidence for multidimensional affective-state modeling.",
    }[theme]


def write_jsonl(path: Path, works: list[dict[str, Any]]) -> None:
    with path.open("w", encoding="utf-8", newline="\n") as handle:
        for work in works:
            handle.write(json.dumps(work, ensure_ascii=False, sort_keys=True) + "\n")


def read_jsonl(path: Path) -> list[dict[str, Any]] | None:
    works: list[dict[str, Any]] = []
    try:
        with path.open("r", encoding="utf-8") as handle:
            for line in handle:
                if line.strip():
                    works.append(json.loads(line))
    except (OSError, json.JSONDecodeError):
        return None
    return works


def write_csv(path: Path, works: list[dict[str, Any]]) -> None:
    fields = [
        "openalex_id",
        "doi",
        "title",
        "year",
        "venue",
        "first_author",
        "author_count",
        "cited_by_count",
        "is_top_venue",
        "query_keys",
        "themes",
        "doi_url",
        "landing_page_url",
    ]
    with path.open("w", encoding="utf-8-sig", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=fields)
        writer.writeheader()
        for work in works:
            row = {field: work.get(field, "") for field in fields}
            row["query_keys"] = ";".join(work.get("query_keys") or [])
            row["themes"] = ";".join(work.get("themes") or [])
            writer.writerow(row)


def write_markdown_outputs(out_dir: Path, works: list[dict[str, Any]], top: list[dict[str, Any]]) -> None:
    theme_counts = Counter(theme for work in works for theme in work.get("themes", []))
    venue_counts = Counter(work.get("venue") or "Unknown venue" for work in works)
    query_counts = Counter(key for work in works for key in work.get("query_keys", []))

    readme = [
        "# AstrBot Emotion Literature Knowledge Base",
        "",
        "This directory is generated by `scripts/build_literature_kb.py` from OpenAlex metadata.",
        "It stores searchable metadata for emotion appraisal, personality, forgiveness, repair, cold treatment, trust, and affective agents.",
        "",
        "## Files",
        "",
        "- `works.jsonl`: deduplicated machine-readable literature records.",
        "- `works.csv`: spreadsheet-friendly index.",
        "- `top_journal_candidates.jsonl`: curated high-impact venue candidates, sorted by citation count.",
        "- `evidence-map.md`: claim-oriented evidence map for model design.",
        "- `topic-summary.md`: topic and venue statistics.",
        "- `manifest.json`: search queries, counts, and build metadata.",
        "",
        "## Counts",
        "",
        f"- Deduplicated works: `{len(works)}`",
        f"- Curated top-venue candidates: `{len(top)}`",
        "",
        "## Top Themes",
        "",
    ]
    for theme, count in theme_counts.most_common():
        readme.append(f"- `{theme}`: {count}")
    readme.append("")
    readme.append("## Rebuild")
    readme.append("")
    readme.append("```powershell")
    readme.append("py -3.13 scripts\\build_literature_kb.py --out literature_kb --per-query 120")
    readme.append("```")
    (out_dir / "README.md").write_text("\n".join(readme) + "\n", encoding="utf-8")

    summary = [
        "# Topic Summary",
        "",
        "## Query Coverage",
        "",
        "| Query key | Count |",
        "| --- | ---: |",
    ]
    for key, count in query_counts.most_common():
        summary.append(f"| `{key}` | {count} |")
    summary.extend(["", "## Theme Coverage", "", "| Theme | Count |", "| --- | ---: |"])
    for theme, count in theme_counts.most_common():
        summary.append(f"| `{theme}` | {count} |")
    summary.extend(["", "## Frequent Venues", "", "| Venue | Count |", "| --- | ---: |"])
    for venue, count in venue_counts.most_common(40):
        summary.append(f"| {venue} | {count} |")
    (out_dir / "topic-summary.md").write_text("\n".join(summary) + "\n", encoding="utf-8")

    evidence = [
        "# Evidence Map",
        "",
        "This map uses title, abstract-level metadata, DOI metadata, venue and query context. It is a design aid, not a substitute for full-text reading.",
        "",
        "| Source ID | Citation | Source type | Abstract-level finding | Usable fact | Supported claim | Citation slot | Risk |",
        "| --- | --- | --- | --- | --- | --- | --- | --- |",
    ]
    selected = top[:80]
    for work in selected:
        theme = (work.get("themes") or ["general"])[0]
        abstract = (work.get("abstract") or "").replace("|", " ")[:220]
        usable = ", ".join(work.get("themes") or [])
        evidence.append(
            "| "
            + " | ".join(
                [
                    str(work.get("source_id")),
                    citation(work).replace("|", " "),
                    "top-venue" if work.get("is_top_venue") else "indexed",
                    abstract or "No abstract in metadata.",
                    usable or "theme relevance",
                    supported_claim_for_theme(theme),
                    f"model-theory::{theme}",
                    "abstract-only",
                ],
            )
            + " |"
        )
    (out_dir / "evidence-map.md").write_text("\n".join(evidence) + "\n", encoding="utf-8")


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--out", default="literature_kb")
    parser.add_argument("--per-query", type=int, default=120)
    parser.add_argument("--per-page", type=int, default=100)
    parser.add_argument("--top-count", type=int, default=120)
    parser.add_argument("--mailto", default="codex@example.com")
    parser.add_argument("--sleep", type=float, default=0.12)
    args = parser.parse_args()

    out_dir = Path(args.out)
    raw_dir = out_dir / "raw"
    raw_dir.mkdir(parents=True, exist_ok=True)

    deduped: dict[str, dict[str, Any]] = {}
    raw_counts: dict[str, int] = {}
    for key, query in QUERIES.items():
        raw_path = raw_dir / f"{key}.jsonl"
        works: list[dict[str, Any]] | None = None
        if raw_path.exists():
            works = read_jsonl(raw_path)
            if works is None:
                print(f"cache corrupted for {key}; refetching")
                raw_path.unlink(missing_ok=True)
        if works is None:
            works = fetch_openalex(
                query,
                per_page=args.per_page,
                max_results=args.per_query,
                mailto=args.mailto,
                sleep_seconds=args.sleep,
            )
            write_jsonl(raw_path, works)
        raw_counts[key] = len(works)
        for work in works:
            simple = simplify_work(work, query_key=key, query=query)
            if not simple["title"]:
                continue
            item_key = stable_key(simple)
            if item_key in deduped:
                deduped[item_key] = merge_work(deduped[item_key], simple)
            else:
                deduped[item_key] = simple

    works = list(deduped.values())
    for index, work in enumerate(works, start=1):
        work["source_id"] = f"KB{index:04d}"
        work["themes"] = classify_themes(work)
    works.sort(key=lambda item: (item.get("cited_by_count") or 0, item.get("year") or 0), reverse=True)

    top = [work for work in works if work.get("is_top_venue")]
    if len(top) < args.top_count:
        seen = {stable_key(work) for work in top}
        for work in works:
            if stable_key(work) in seen:
                continue
            if work.get("cited_by_count", 0) >= 300:
                top.append(work)
                seen.add(stable_key(work))
            if len(top) >= args.top_count:
                break
    top.sort(key=lambda item: (item.get("is_top_venue"), item.get("cited_by_count") or 0), reverse=True)
    top = top[: args.top_count]

    write_jsonl(out_dir / "works.jsonl", works)
    write_csv(out_dir / "works.csv", works)
    write_jsonl(out_dir / "top_journal_candidates.jsonl", top)
    write_csv(out_dir / "top_journal_candidates.csv", top)
    write_markdown_outputs(out_dir, works, top)

    manifest = {
        "generated_at": time.strftime("%Y-%m-%dT%H:%M:%S%z"),
        "source": "OpenAlex Works API",
        "source_url": OPENALEX_URL,
        "queries": QUERIES,
        "raw_counts": raw_counts,
        "deduplicated_count": len(works),
        "top_candidate_count": len(top),
        "top_venues": sorted(TOP_VENUES),
        "theme_keywords": THEME_KEYWORDS,
    }
    (out_dir / "manifest.json").write_text(
        json.dumps(manifest, ensure_ascii=False, indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
    )
    print(json.dumps(manifest, ensure_ascii=False, indent=2, sort_keys=True))


if __name__ == "__main__":
    main()
