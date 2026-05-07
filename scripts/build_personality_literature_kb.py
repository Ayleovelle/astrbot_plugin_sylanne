from __future__ import annotations

import argparse
import csv
import json
import time
import urllib.parse
import urllib.request
from collections import Counter
from pathlib import Path
from typing import Any
from urllib.error import HTTPError, URLError


OPENALEX_URL = "https://api.openalex.org/works"

QUERIES: dict[str, str] = {
    "big_five_structure": "Big Five personality structure five factor model",
    "lexical_personality": "lexical hypothesis personality trait structure Big Five",
    "five_factor_validation": "five factor model personality validation observers instruments",
    "hexaco_model": "HEXACO model personality honesty humility agreeableness emotionality",
    "personality_development": "personality trait development stability change meta analysis",
    "personality_states_density": "personality states density distributions whole trait theory",
    "caps_personality": "cognitive affective personality system personality dynamics situations",
    "personality_emotion_reactivity": "personality emotional reactivity neuroticism affect dynamics",
    "emotion_regulation_personality": "emotion regulation personality reappraisal suppression individual differences",
    "attachment_dimensions": "adult attachment anxiety avoidance close relationships emotion regulation",
    "bis_bas_personality": "behavioral inhibition activation system BIS BAS personality affect",
    "need_for_closure": "need for cognitive closure personality uncertainty ambiguity",
    "interpersonal_circumplex": "interpersonal circumplex agency communion personality emotion",
    "personality_ai_agents": "personality modeling conversational agents believable agents affect",
    "llm_persona_personality": "large language model persona personality traits agents evaluation",
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
    "Journal of Personality",
    "Journal of Research in Personality",
    "European Journal of Personality",
    "Personality and Individual Differences",
    "Social Psychological and Personality Science",
    "American Psychologist",
    "Review of General Psychology",
    "Emotion",
    "Cognition and Emotion",
    "Emotion Review",
    "Nature Human Behaviour",
    "PNAS",
    "Proceedings of the National Academy of Sciences",
    "Computers in Human Behavior",
    "International Journal of Human-Computer Studies",
    "International Journal of Human-Computer Interaction",
    "ACM Transactions on Computer-Human Interaction",
    "Proceedings of the ACM on Human-Computer Interaction",
    "CHI Conference on Human Factors in Computing Systems",
    "Autonomous Agents and Multi-Agent Systems",
}

THEME_KEYWORDS: dict[str, tuple[str, ...]] = {
    "big_five_and_trait_structure": (
        "big five",
        "five-factor",
        "five factor",
        "personality structure",
        "lexical",
    ),
    "hexaco_and_moral_trait_extensions": (
        "hexaco",
        "honesty",
        "humility",
        "agreeableness",
        "emotionality",
    ),
    "personality_dynamics_and_state_distributions": (
        "density distribution",
        "whole trait",
        "personality state",
        "cognitive-affective",
        "situation",
    ),
    "attachment_and_relationship_priors": (
        "attachment",
        "anxiety",
        "avoidance",
        "close relationship",
        "reassurance",
    ),
    "reinforcement_sensitivity_and_uncertainty": (
        "behavioral inhibition",
        "behavioral activation",
        "bis",
        "bas",
        "need for closure",
        "uncertainty",
    ),
    "emotion_regulation_and_reactivity": (
        "emotion regulation",
        "reactivity",
        "neuroticism",
        "suppression",
        "reappraisal",
    ),
    "personality_agents_and_llm_persona": (
        "agent",
        "chatbot",
        "conversational",
        "large language model",
        "persona",
    ),
}

NEGATIVE_KEYWORDS = (
    "borderline personality disorder",
    "antisocial personality disorder",
    "personality disorder",
    "cardiovascular",
    "oncology",
    "cancer",
    "genome",
    "protein",
)

FOUNDATIONAL_SOURCES: list[dict[str, Any]] = [
    {
        "source_id": "PERS-F001",
        "citation": "Digman, J. M. (1990). Personality structure: Emergence of the five-factor model. Annual Review of Psychology, 41, 417-440.",
        "doi": "10.1146/annurev.ps.41.020190.002221",
        "claim": "The Big Five provides a stable high-level trait basis for persona priors.",
        "slot": "personality-model::trait-space",
    },
    {
        "source_id": "PERS-F002",
        "citation": "Goldberg, L. R. (1990). An alternative description of personality: The Big-Five factor structure. Journal of Personality and Social Psychology, 59(6), 1216-1229.",
        "doi": "10.1037/0022-3514.59.6.1216",
        "claim": "Lexical trait evidence supports deriving persona traits from stable descriptive language.",
        "slot": "personality-model::lexical-projection",
    },
    {
        "source_id": "PERS-F003",
        "citation": "McCrae, R. R., & Costa, P. T. (1987). Validation of the five-factor model of personality across instruments and observers. Journal of Personality and Social Psychology, 52(1), 81-90.",
        "doi": "10.1037/0022-3514.52.1.81",
        "claim": "Trait estimates should be treated as latent constructs inferred from multiple imperfect indicators.",
        "slot": "personality-model::weighted-posterior",
    },
    {
        "source_id": "PERS-F004",
        "citation": "Ashton, M. C., & Lee, K. (2007). Empirical, theoretical, and practical advantages of the HEXACO model of personality structure. Personality and Social Psychology Review, 11(2), 150-166.",
        "doi": "10.1177/1088868306294907",
        "claim": "Honesty-humility is useful when modeling trust, guilt, repair, and moral posture.",
        "slot": "personality-model::hexaco-extension",
    },
    {
        "source_id": "PERS-F005",
        "citation": "DeYoung, C. G., Quilty, L. C., & Peterson, J. B. (2007). Between facets and domains: 10 aspects of the Big Five. Journal of Personality and Social Psychology, 93(5), 880-896.",
        "doi": "10.1037/0022-3514.93.5.880",
        "claim": "Facet/aspect hierarchy supports using broad traits plus derived second-order factors.",
        "slot": "personality-model::hierarchical-traits",
    },
    {
        "source_id": "PERS-F006",
        "citation": "DeYoung, C. G. (2015). Cybernetic Big Five Theory. Journal of Research in Personality, 56, 33-58.",
        "doi": "10.1016/j.jrp.2014.07.004",
        "claim": "Traits can be interpreted as parameters of goal-directed regulation and cybernetic control.",
        "slot": "personality-model::control-parameters",
    },
    {
        "source_id": "PERS-F007",
        "citation": "Fleeson, W. (2001). Toward a structure- and process-integrated view of personality: Traits as density distributions of states. Journal of Personality and Social Psychology, 80(6), 1011-1027.",
        "doi": "10.1037/0022-3514.80.6.1011",
        "claim": "A persona should define a stable distribution over states, not a fixed response script.",
        "slot": "personality-model::state-distribution",
    },
    {
        "source_id": "PERS-F008",
        "citation": "Mischel, W., & Shoda, Y. (1995). A cognitive-affective system theory of personality. Psychological Review, 102(2), 246-268.",
        "doi": "10.1037/0033-295X.102.2.246",
        "claim": "Personality should modulate if-then appraisal patterns across situations.",
        "slot": "personality-model::situation-coupling",
    },
    {
        "source_id": "PERS-F009",
        "citation": "Carver, C. S., & White, T. L. (1994). Behavioral inhibition, behavioral activation, and affective responses to impending reward and punishment. Journal of Personality and Social Psychology, 67(2), 319-333.",
        "doi": "10.1037/0022-3514.67.2.319",
        "claim": "BIS/BAS dimensions support modeling threat sensitivity and approach drive separately.",
        "slot": "personality-model::bis-bas",
    },
    {
        "source_id": "PERS-F010",
        "citation": "Webster, D. M., & Kruglanski, A. W. (1994). Individual differences in need for cognitive closure. Journal of Personality and Social Psychology, 67(6), 1049-1062.",
        "doi": "10.1037/0022-3514.67.6.1049",
        "claim": "Need for closure supports an uncertainty-to-boundary and certainty-bias parameter.",
        "slot": "personality-model::uncertainty",
    },
    {
        "source_id": "PERS-F011",
        "citation": "Fraley, R. C., Waller, N. G., & Brennan, K. A. (2000). An item-response theory analysis of self-report measures of adult attachment. Journal of Personality and Social Psychology, 78(2), 350-365.",
        "doi": "10.1037/0022-3514.78.2.350",
        "claim": "Attachment anxiety and avoidance should be separate relationship priors.",
        "slot": "personality-model::attachment",
    },
    {
        "source_id": "PERS-F012",
        "citation": "Gross, J. J., & John, O. P. (2003). Individual differences in two emotion regulation processes. Journal of Personality and Social Psychology, 85(2), 348-362.",
        "doi": "10.1037/0022-3514.85.2.348",
        "claim": "Emotion regulation capacity should dampen reactivity and shorten harmful persistence.",
        "slot": "personality-model::regulation",
    },
]


def reconstruct_abstract(index: dict[str, list[int]] | None) -> str:
    if not index:
        return ""
    words: list[tuple[int, str]] = []
    for word, positions in index.items():
        for position in positions:
            words.append((position, word))
    return " ".join(word for _, word in sorted(words))


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
            headers={"User-Agent": f"astrbot-personality-kb/0.0.2 ({mailto})"},
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
    all_authors = authors(work)
    venue = source_name(work)
    abstract = reconstruct_abstract(work.get("abstract_inverted_index"))
    return {
        "openalex_id": work.get("id"),
        "doi": doi,
        "doi_url": doi_url(doi),
        "title": str(work.get("display_name") or "").strip(),
        "year": work.get("publication_year"),
        "publication_date": work.get("publication_date") or "",
        "venue": venue,
        "venue_type": source_type(work),
        "authors": all_authors[:12],
        "author_count": len(all_authors),
        "first_author": all_authors[0] if all_authors else "",
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
        "evidence_status": "abstract-only" if abstract else "metadata-only",
    }


def stable_key(work: dict[str, Any]) -> str:
    if work.get("doi"):
        return "doi:" + str(work["doi"]).lower()
    if work.get("openalex_id"):
        return "openalex:" + str(work["openalex_id"]).lower()
    return "title:" + str(work.get("title", "")).lower()


def merge_work(existing: dict[str, Any], incoming: dict[str, Any]) -> dict[str, Any]:
    for key in ("query_keys", "queries"):
        existing[key] = list(dict.fromkeys(existing.get(key, []) + incoming.get(key, [])))
    if not existing.get("abstract") and incoming.get("abstract"):
        existing["abstract"] = incoming["abstract"]
        existing["evidence_status"] = "abstract-only"
    if incoming.get("cited_by_count", 0) > existing.get("cited_by_count", 0):
        existing["cited_by_count"] = incoming["cited_by_count"]
    existing["is_top_venue"] = bool(existing.get("is_top_venue") or incoming.get("is_top_venue"))
    return existing


def classify_themes(work: dict[str, Any]) -> list[str]:
    text = " ".join(
        [
            str(work.get("title") or ""),
            str(work.get("abstract") or ""),
            " ".join(work.get("concepts") or []),
            " ".join(work.get("query_keys") or []),
        ],
    ).lower()
    themes = [
        theme
        for theme, keywords in THEME_KEYWORDS.items()
        if any(keyword.lower() in text for keyword in keywords)
    ]
    return themes or ["general_personality"]


def relevance_score(work: dict[str, Any]) -> float:
    themes = [theme for theme in work.get("themes", []) if theme != "general_personality"]
    text = f"{work.get('title', '')} {work.get('abstract', '')}".lower()
    penalty = 0.25 * sum(1 for keyword in NEGATIVE_KEYWORDS if keyword in text)
    score = 0.18 * len(themes)
    score += 0.22 if work.get("is_top_venue") else 0.0
    score += min(0.30, float(work.get("cited_by_count") or 0) / 2500.0)
    score += 0.10 if work.get("doi") else 0.0
    score += 0.10 if work.get("abstract") else 0.0
    score += min(0.10, 0.02 * len(work.get("query_keys") or []))
    return max(0.0, round(score - penalty, 6))


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
        "big_five_and_trait_structure": "Persona priors should include stable broad trait dimensions rather than only local style keywords.",
        "hexaco_and_moral_trait_extensions": "Honesty-humility and related moral traits can inform trust repair and guilt-like simulation.",
        "personality_dynamics_and_state_distributions": "Personality should constrain distributions and situation-response dynamics, not fixed scripts.",
        "attachment_and_relationship_priors": "Attachment anxiety and avoidance should separately affect reassurance needs and social distance.",
        "reinforcement_sensitivity_and_uncertainty": "Threat sensitivity, approach drive and need for closure can modulate certainty, caution and boundaries.",
        "emotion_regulation_and_reactivity": "Emotion regulation traits can dampen reactivity, persistence and escalation risk.",
        "personality_agents_and_llm_persona": "Agent personality should be exposed as a versioned, inspectable state for other plugins.",
        "general_personality": "This source is adjacent evidence for personality quantification and should be manually screened before use.",
    }[theme]


def write_jsonl(path: Path, works: list[dict[str, Any]]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
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
        "source_id",
        "openalex_id",
        "doi",
        "title",
        "year",
        "venue",
        "first_author",
        "author_count",
        "cited_by_count",
        "is_top_venue",
        "relevance_score",
        "evidence_status",
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


def write_markdown(out_dir: Path, works: list[dict[str, Any]], top: list[dict[str, Any]], *, raw_total: int, target: int) -> None:
    theme_counts = Counter(theme for work in works for theme in work.get("themes", []))
    venue_counts = Counter(work.get("venue") or "Unknown venue" for work in works)
    evidence_counts = Counter(work.get("evidence_status") or "metadata-only" for work in works)
    doi_coverage = sum(1 for work in works if work.get("doi"))

    readme = [
        "# Personality Literature Knowledge Base",
        "",
        "Generated by `scripts/build_personality_literature_kb.py` from OpenAlex metadata.",
        "This is a metadata and abstract-level knowledge base for personality modeling. It does not claim full-text reading of every candidate.",
        "",
        "## Counts",
        "",
        f"- Target candidate retrieval: `{target}`",
        f"- Raw retrieved records: `{raw_total}`",
        f"- Deduplicated works: `{len(works)}`",
        f"- DOI coverage: `{doi_coverage}`",
        f"- Curated top candidates: `{len(top)}`",
        "",
        "## Evidence Status",
        "",
    ]
    for status, count in evidence_counts.most_common():
        readme.append(f"- `{status}`: {count}")
    readme.extend(["", "## Files", ""])
    readme.extend(
        [
            "- `works.jsonl`: deduplicated candidate records.",
            "- `works.csv`: spreadsheet-friendly index.",
            "- `curated/top_500.jsonl`: high-relevance candidate subset for future manual screening.",
            "- `evidence-map.md`: claim-oriented map for the plugin theory docs.",
            "- `topic-summary.md`: query, theme and venue statistics.",
            "- `manifest.json`: reproducibility metadata.",
            "",
            "## Rebuild",
            "",
            "```powershell",
            "py -3.13 scripts\\build_personality_literature_kb.py --out personality_literature_kb --target 20000 --per-query 1400 --top-count 500",
            "```",
        ],
    )
    (out_dir / "README.md").write_text("\n".join(readme) + "\n", encoding="utf-8")

    summary = [
        "# Personality KB Topic Summary",
        "",
        "## Theme Coverage",
        "",
        "| Theme | Count |",
        "| --- | ---: |",
    ]
    for theme, count in theme_counts.most_common():
        summary.append(f"| `{theme}` | {count} |")
    summary.extend(["", "## Frequent Venues", "", "| Venue | Count |", "| --- | ---: |"])
    for venue, count in venue_counts.most_common(50):
        summary.append(f"| {venue} | {count} |")
    (out_dir / "topic-summary.md").write_text("\n".join(summary) + "\n", encoding="utf-8")

    evidence = [
        "# Personality Model Evidence Map",
        "",
        "This map separates foundational verified citations from metadata-level candidates. Candidate rows are not full-text reviews.",
        "",
        "## Foundational Sources",
        "",
        "| Source ID | Citation | DOI | Supported claim | Citation slot | Evidence level |",
        "| --- | --- | --- | --- | --- | --- |",
    ]
    for item in FOUNDATIONAL_SOURCES:
        evidence.append(
            "| "
            + " | ".join(
                [
                    item["source_id"],
                    item["citation"],
                    f"https://doi.org/{item['doi']}",
                    item["claim"],
                    item["slot"],
                    "verified-doi-metadata",
                ],
            )
            + " |"
        )
    evidence.extend(
        [
            "",
            "## Candidate Evidence Rows",
            "",
            "| Source ID | Citation | Source type | Abstract-level finding | Usable fact | Supported claim | Citation slot | Risk |",
            "| --- | --- | --- | --- | --- | --- | --- | --- |",
        ],
    )
    for work in top[:120]:
        theme = (work.get("themes") or ["general_personality"])[0]
        abstract = (work.get("abstract") or "").replace("|", " ")[:220]
        evidence.append(
            "| "
            + " | ".join(
                [
                    str(work.get("source_id")),
                    citation(work).replace("|", " "),
                    "top-venue" if work.get("is_top_venue") else "indexed",
                    abstract or "No abstract in metadata.",
                    ", ".join(work.get("themes") or []),
                    supported_claim_for_theme(theme),
                    f"personality-model::{theme}",
                    work.get("evidence_status") or "metadata-only",
                ],
            )
            + " |"
        )
    (out_dir / "evidence-map.md").write_text("\n".join(evidence) + "\n", encoding="utf-8")


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--out", default="personality_literature_kb")
    parser.add_argument("--target", type=int, default=20000)
    parser.add_argument("--per-query", type=int, default=1400)
    parser.add_argument("--per-page", type=int, default=200)
    parser.add_argument("--top-count", type=int, default=500)
    parser.add_argument("--mailto", default="codex@example.com")
    parser.add_argument("--sleep", type=float, default=0.08)
    args = parser.parse_args()

    out_dir = Path(args.out)
    raw_dir = out_dir / "raw"
    raw_dir.mkdir(parents=True, exist_ok=True)

    deduped: dict[str, dict[str, Any]] = {}
    raw_counts: dict[str, int] = {}
    for key, query in QUERIES.items():
        raw_path = raw_dir / f"{key}.jsonl"
        works = read_jsonl(raw_path) if raw_path.exists() else None
        if works is not None and len(works) < args.per_query:
            works = None
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
        for raw in works:
            simple = simplify_work(raw, query_key=key, query=query)
            if not simple["title"]:
                continue
            item_key = stable_key(simple)
            if item_key in deduped:
                deduped[item_key] = merge_work(deduped[item_key], simple)
            else:
                deduped[item_key] = simple

    works = list(deduped.values())
    for work in works:
        work["themes"] = classify_themes(work)
        work["relevance_score"] = relevance_score(work)
    works.sort(
        key=lambda item: (
            item.get("relevance_score") or 0,
            item.get("cited_by_count") or 0,
            item.get("year") or 0,
        ),
        reverse=True,
    )
    for index, work in enumerate(works, start=1):
        work["source_id"] = f"PERS{index:05d}"

    top = [
        work
        for work in works
        if work.get("is_top_venue") or work.get("relevance_score", 0) >= 0.42
    ][: args.top_count]
    if len(top) < args.top_count:
        seen = {stable_key(work) for work in top}
        for work in works:
            if stable_key(work) not in seen:
                top.append(work)
                seen.add(stable_key(work))
            if len(top) >= args.top_count:
                break

    write_jsonl(out_dir / "works.jsonl", works)
    write_csv(out_dir / "works.csv", works)
    write_jsonl(out_dir / "curated" / "top_500.jsonl", top)
    write_csv(out_dir / "curated" / "top_500.csv", top)
    raw_total = sum(raw_counts.values())
    write_markdown(out_dir, works, top, raw_total=raw_total, target=args.target)

    manifest = {
        "generated_at": time.strftime("%Y-%m-%dT%H:%M:%S%z"),
        "source": "OpenAlex Works API",
        "source_url": OPENALEX_URL,
        "target_candidate_records": args.target,
        "raw_retrieved_count": raw_total,
        "target_met": raw_total >= args.target,
        "deduplicated_count": len(works),
        "top_candidate_count": len(top),
        "queries": QUERIES,
        "raw_counts": raw_counts,
        "top_venues": sorted(TOP_VENUES),
        "theme_keywords": THEME_KEYWORDS,
        "evidence_status_contract": [
            "metadata-only",
            "abstract-only",
            "verified-doi-metadata",
            "fulltext-reviewed",
        ],
        "honesty_note": (
            "This KB records automated metadata/abstract-level retrieval and "
            "does not claim manual full-text reading of 20,000 papers."
        ),
        "foundational_source_count": len(FOUNDATIONAL_SOURCES),
    }
    (out_dir / "manifest.json").write_text(
        json.dumps(manifest, ensure_ascii=False, indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
    )
    print(json.dumps(manifest, ensure_ascii=False, indent=2, sort_keys=True))


if __name__ == "__main__":
    main()
