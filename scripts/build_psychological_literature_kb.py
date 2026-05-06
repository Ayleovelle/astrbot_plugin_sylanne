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
    "non_diagnostic_screening_distress": "non diagnostic mental health screening psychological distress wellbeing",
    "mental_health_screening_primary_care": "mental health screening primary care distress questionnaire",
    "subclinical_symptoms_monitoring": "subclinical symptoms monitoring mental health digital",
    "wellbeing_screening": "well-being screening mental health questionnaire digital health",
    "stress_burnout_screening": "stress burnout screening questionnaire mental health",
    "phq9_screening": "PHQ-9 depression screening validation questionnaire",
    "gad7_screening": "GAD-7 anxiety screening validation questionnaire",
    "dass21_distress": "DASS-21 depression anxiety stress scale validation",
    "kessler_distress": "Kessler K6 K10 psychological distress scale",
    "who5_wellbeing": "WHO-5 wellbeing index mental health screening",
    "pss_stress": "perceived stress scale PSS validation",
    "panas_affect": "PANAS positive negative affect scale",
    "ucla_loneliness": "UCLA loneliness scale validation mental health",
    "isi_sleep": "insomnia severity index mental health screening",
    "audit_substance": "AUDIT alcohol use screening mental health validation",
    "pcl5_trauma": "PCL-5 PTSD checklist validation screening",
    "columbia_suicide_severity": "Columbia Suicide Severity Rating Scale validation suicide risk assessment",
    "ema_mental_health": "ecological momentary assessment mental health mood symptoms",
    "longitudinal_mood_modeling": "longitudinal mood modeling mental health time series",
    "affective_dynamics_mental_health": "affective dynamics emotional inertia mental health",
    "digital_phenotyping": "digital phenotyping mental health passive sensing",
    "mobile_sensing_mental_health": "mobile sensing mental health smartphone behavior",
    "wearables_sleep_stress": "wearable sensing sleep stress mental health longitudinal",
    "jitai_mental_health": "just in time adaptive intervention mental health mobile",
    "measurement_based_care": "measurement based care mental health outcomes symptoms tracking",
    "digital_mental_health_interventions": "digital mental health intervention app randomized trial",
    "mental_health_apps_evaluation": "mental health apps evaluation safety efficacy engagement",
    "online_cbt_digital": "internet CBT digital mental health randomized controlled trial",
    "telepsychology_digital_care": "telepsychology digital mental health care outcomes",
    "engagement_adherence_digital": "engagement adherence digital mental health intervention",
    "chatbot_mental_health": "chatbot mental health conversational agent intervention",
    "conversational_agent_safety": "conversational agent mental health safety risk",
    "llm_mental_health_safety": "large language model mental health safety chatbot",
    "ai_therapy_risk": "AI therapy chatbot risk ethics mental health",
    "suicide_prevention_chatbot": "suicide prevention chatbot crisis response safety",
    "empathetic_dialogue_safety": "empathetic dialogue system safety mental health",
    "clinical_governance_ai_mental_health": "clinical governance artificial intelligence mental health safety",
    "digital_health_clinical_safety": "digital health clinical safety artificial intelligence mental health governance",
    "human_oversight_mental_health_ai": "human oversight AI mental health clinical decision support",
    "crisis_response_digital_mental_health": "crisis response digital mental health suicide prevention safety",
}

TOP_VENUES = {
    "Annual Review of Psychology",
    "Psychological Bulletin",
    "Psychological Review",
    "Perspectives on Psychological Science",
    "Psychological Science",
    "Clinical Psychological Science",
    "Psychological Medicine",
    "Clinical Psychology Review",
    "Journal of Abnormal Psychology",
    "Journal of Psychopathology and Clinical Science",
    "Assessment",
    "Psychological Assessment",
    "Journal of Clinical Psychology",
    "Behaviour Research and Therapy",
    "Cognitive Behaviour Therapy",
    "Journal of Affective Disorders",
    "Depression and Anxiety",
    "Anxiety Stress & Coping",
    "Health Psychology",
    "Psychosomatic Medicine",
    "JAMA Psychiatry",
    "The Lancet Psychiatry",
    "World Psychiatry",
    "American Journal of Psychiatry",
    "British Journal of Psychiatry",
    "Epidemiology and Psychiatric Sciences",
    "Social Psychiatry and Psychiatric Epidemiology",
    "BMC Psychiatry",
    "Internet Interventions",
    "npj Digital Medicine",
    "The Lancet Digital Health",
    "Journal of Medical Internet Research",
    "JMIR Mental Health",
    "Digital Health",
    "Journal of Biomedical Informatics",
    "Journal of the American Medical Informatics Association",
    "Nature Medicine",
    "Nature Human Behaviour",
    "Nature Machine Intelligence",
    "Computers in Human Behavior",
    "International Journal of Human-Computer Studies",
    "International Journal of Human-Computer Interaction",
    "ACM Transactions on Computer-Human Interaction",
    "Proceedings of the ACM on Human-Computer Interaction",
    "CHI Conference on Human Factors in Computing Systems",
    "IEEE Transactions on Affective Computing",
    "Artificial Intelligence",
    "AI & Society",
    "Ethics and Information Technology",
}

THEME_KEYWORDS: dict[str, tuple[str, ...]] = {
    "non_diagnostic_screening": (
        "screening",
        "distress",
        "well-being",
        "wellbeing",
        "subclinical",
        "primary care",
    ),
    "clinical_scale_instruments": (
        "phq",
        "gad",
        "dass",
        "kessler",
        "who-5",
        "perceived stress scale",
        "panas",
        "ucla loneliness",
        "insomnia severity",
        "audit",
        "pcl-5",
        "columbia suicide",
    ),
    "longitudinal_state_modeling": (
        "longitudinal",
        "ecological momentary assessment",
        "ema",
        "time series",
        "digital phenotyping",
        "passive sensing",
        "wearable",
        "mood modeling",
        "affective dynamics",
    ),
    "digital_mental_health": (
        "digital mental health",
        "mental health app",
        "internet cbt",
        "telepsychology",
        "mobile health",
        "mhealth",
        "engagement",
        "adherence",
        "jitai",
    ),
    "llm_chatbot_safety": (
        "chatbot",
        "conversational agent",
        "large language model",
        "llm",
        "ai therapy",
        "crisis response",
        "suicide prevention",
        "clinical governance",
        "human oversight",
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
    return [
        str(item.get("display_name"))
        for item in work.get("concepts") or []
        if item.get("display_name")
    ]


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
        req = urllib.request.Request(
            OPENALEX_URL + "?" + urllib.parse.urlencode(params),
            headers={"User-Agent": f"astrbot-psychological-kb/1.0 ({mailto})"},
        )
        payload = None
        for attempt in range(5):
            try:
                with urllib.request.urlopen(req, timeout=90) as response:
                    payload = json.load(response)
                break
            except (HTTPError, URLError, TimeoutError) as exc:
                if attempt == 4:
                    raise
                wait = sleep_seconds + 1.5 * (attempt + 1)
                print(f"retry {attempt + 1}/5 query={query!r}: {exc}; sleep={wait:.1f}s")
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
    names = authors(work)
    venue = source_name(work)
    text = " ".join(
        [
            str(work.get("display_name") or ""),
            reconstruct_abstract(work.get("abstract_inverted_index")),
            " ".join(concepts(work)),
            query_key,
        ],
    ).lower()
    return {
        "openalex_id": work.get("id"),
        "doi": doi,
        "doi_url": doi_url(doi),
        "title": str(work.get("display_name") or "").strip(),
        "year": work.get("publication_year"),
        "publication_date": work.get("publication_date") or "",
        "venue": venue,
        "venue_type": source_type(work),
        "authors": names[:12],
        "author_count": len(names),
        "first_author": names[0] if names else "",
        "cited_by_count": int(work.get("cited_by_count") or 0),
        "is_top_venue": venue in TOP_VENUES,
        "concepts": concepts(work)[:12],
        "abstract": reconstruct_abstract(work.get("abstract_inverted_index")),
        "open_access": (work.get("open_access") or {}).get("is_oa"),
        "landing_page_url": (
            (work.get("primary_location") or {}).get("landing_page_url")
            or work.get("doi")
            or work.get("id")
        ),
        "query_keys": [query_key],
        "queries": [query],
        "scale_or_instrument": detect_scale(text),
        "diagnostic_boundary": diagnostic_boundary(text),
        "safety_risk_type": detect_safety_risk(text),
        "human_oversight": detect_human_oversight(text),
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
    if incoming.get("cited_by_count", 0) > existing.get("cited_by_count", 0):
        existing["cited_by_count"] = incoming["cited_by_count"]
    existing["is_top_venue"] = bool(existing.get("is_top_venue") or incoming.get("is_top_venue"))
    for key in ("scale_or_instrument", "diagnostic_boundary", "safety_risk_type", "human_oversight"):
        if incoming.get(key) and incoming.get(key) not in {"none", "screening_only"}:
            existing[key] = incoming[key]
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
    themes = []
    for theme, keywords in THEME_KEYWORDS.items():
        if any(keyword.lower() in text for keyword in keywords):
            themes.append(theme)
    return themes or ["general"]


def detect_scale(text: str) -> str:
    mapping = {
        "PHQ": ("phq-9", "phq9", "patient health questionnaire"),
        "GAD": ("gad-7", "gad7", "generalized anxiety disorder"),
        "DASS": ("dass-21", "dass21", "depression anxiety stress scale"),
        "Kessler": ("kessler", "k6", "k10"),
        "WHO-5": ("who-5", "who5", "well-being index"),
        "PSS": ("perceived stress scale", "pss"),
        "PANAS": ("panas", "positive and negative affect"),
        "UCLA Loneliness": ("ucla loneliness", "loneliness scale"),
        "ISI": ("insomnia severity index", "isi"),
        "AUDIT": ("audit", "alcohol use disorders identification"),
        "PCL-5": ("pcl-5", "ptsd checklist"),
        "C-SSRS": ("columbia suicide", "c-ssrs", "suicide severity"),
    }
    hits = [name for name, terms in mapping.items() if any(term in text for term in terms)]
    return ";".join(hits) if hits else "none"


def diagnostic_boundary(text: str) -> str:
    if "diagnos" in text or "clinical diagnosis" in text:
        return "diagnostic_claim_present"
    if "validation" in text or "screening" in text:
        return "screening_or_validation"
    return "screening_only"


def detect_safety_risk(text: str) -> str:
    if "suicide" in text or "self-harm" in text or "crisis" in text:
        return "crisis_or_self_harm"
    if "ethic" in text or "safety" in text or "risk" in text:
        return "ai_or_intervention_safety"
    return "none"


def detect_human_oversight(text: str) -> str:
    if "human oversight" in text or "clinical governance" in text:
        return "explicit"
    if "clinical decision support" in text or "clinician" in text:
        return "clinical_review_context"
    return "not_specified"


def citation(work: dict[str, Any]) -> str:
    author_text = ", ".join(work.get("authors")[:3] or [])
    if work.get("author_count", 0) > 3:
        author_text += ", et al."
    return (
        f"{author_text} ({work.get('year') or 'n.d.'}). "
        f"{work.get('title') or 'Untitled'}. "
        f"{work.get('venue') or 'Unknown venue'}. "
        f"{work.get('doi_url') or work.get('landing_page_url') or ''}"
    ).strip()


def supported_claim(theme: str) -> str:
    return {
        "non_diagnostic_screening": "Psychological-state modules should present screening and monitoring signals rather than diagnostic conclusions.",
        "clinical_scale_instruments": "Validated instruments can inspire structured dimensions, but score interpretation must preserve their intended screening boundaries.",
        "longitudinal_state_modeling": "Longitudinal mental-health signals should be modeled as personal trends with missingness and context, not one-shot labels.",
        "digital_mental_health": "Digital mental-health tools require evidence, engagement tracking, safety review and clear limits on clinical interpretation.",
        "llm_chatbot_safety": "Mental-health chatbots and LLM tools require crisis escalation, human oversight and non-substitution boundaries.",
        "general": "This source provides adjacent evidence for non-diagnostic psychological state modeling.",
    }[theme]


def write_jsonl(path: Path, works: list[dict[str, Any]]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", encoding="utf-8", newline="\n") as handle:
        for work in works:
            handle.write(json.dumps(work, ensure_ascii=False, sort_keys=True) + "\n")


def read_jsonl(path: Path) -> list[dict[str, Any]] | None:
    works = []
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
        "query_keys",
        "themes",
        "scale_or_instrument",
        "diagnostic_boundary",
        "safety_risk_type",
        "human_oversight",
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


def write_markdown(out_dir: Path, works: list[dict[str, Any]], top: list[dict[str, Any]]) -> None:
    theme_counts = Counter(theme for work in works for theme in work.get("themes", []))
    query_counts = Counter(key for work in works for key in work.get("query_keys", []))
    venue_counts = Counter(work.get("venue") or "Unknown venue" for work in works)
    readme = [
        "# Psychological Screening Literature Knowledge Base",
        "",
        "Generated from OpenAlex metadata. This KB supports non-diagnostic psychological-state screening, long-term monitoring, digital mental-health safety, and chatbot/LLM governance.",
        "",
        "It must not be used as a standalone clinical diagnostic source. Claims are based on metadata and abstracts unless manually reviewed.",
        "",
        "## Counts",
        "",
        f"- Deduplicated works: `{len(works)}`",
        f"- Top/high-impact candidates: `{len(top)}`",
        "",
        "## Rebuild",
        "",
        "```powershell",
        "py -3.13 scripts\\build_psychological_literature_kb.py --out psychological_literature_kb --per-query 150 --top-count 260",
        "```",
    ]
    (out_dir / "README.md").write_text("\n".join(readme) + "\n", encoding="utf-8")

    summary = ["# Topic Summary", "", "## Query Coverage", "", "| Query | Count |", "| --- | ---: |"]
    for key, count in query_counts.most_common():
        summary.append(f"| `{key}` | {count} |")
    summary.extend(["", "## Theme Coverage", "", "| Theme | Count |", "| --- | ---: |"])
    for theme, count in theme_counts.most_common():
        summary.append(f"| `{theme}` | {count} |")
    summary.extend(["", "## Frequent Venues", "", "| Venue | Count |", "| --- | ---: |"])
    for venue, count in venue_counts.most_common(60):
        summary.append(f"| {venue} | {count} |")
    (out_dir / "topic-summary.md").write_text("\n".join(summary) + "\n", encoding="utf-8")

    evidence = [
        "# Evidence Map",
        "",
        "Rows are generated from title, abstract-level metadata, DOI metadata, venue and query context. Risk stays `abstract-only` until full text is reviewed.",
        "",
        "| Source ID | Citation | Themes | Scale / Instrument | Diagnostic boundary | Safety risk | Human oversight | Abstract-level finding | Supported design claim | Citation slot | Risk |",
        "| --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- |",
    ]
    for work in top[:120]:
        theme = (work.get("themes") or ["general"])[0]
        evidence.append(
            "| "
            + " | ".join(
                [
                    str(work.get("source_id")),
                    citation(work).replace("|", " "),
                    ", ".join(work.get("themes") or []),
                    str(work.get("scale_or_instrument")),
                    str(work.get("diagnostic_boundary")),
                    str(work.get("safety_risk_type")),
                    str(work.get("human_oversight")),
                    (work.get("abstract") or "No abstract in metadata.").replace("|", " ")[:220],
                    supported_claim(theme),
                    f"psychological-screening::{theme}",
                    "abstract-only",
                ],
            )
            + " |"
        )
    (out_dir / "evidence-map.md").write_text("\n".join(evidence) + "\n", encoding="utf-8")

    report = [
        "# Validation Report",
        "",
        f"- Deduplicated works >= 3000: `{len(works) >= 3000}` ({len(works)})",
        f"- Top candidates >= 200: `{len(top) >= 200}` ({len(top)})",
        "- Diagnostic boundary: records marked `diagnostic_claim_present` must not be converted into chatbot diagnosis rules without manual review.",
        "- Review status: generated from metadata; sample full-text/abstract verification is still required before strong clinical claims.",
    ]
    (out_dir / "validation-report.md").write_text("\n".join(report) + "\n", encoding="utf-8")


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--out", default="psychological_literature_kb")
    parser.add_argument("--per-query", type=int, default=150)
    parser.add_argument("--per-page", type=int, default=100)
    parser.add_argument("--top-count", type=int, default=260)
    parser.add_argument("--mailto", default="codex@example.com")
    parser.add_argument("--sleep", type=float, default=0.1)
    args = parser.parse_args()

    out_dir = Path(args.out)
    raw_dir = out_dir / "raw"
    raw_dir.mkdir(parents=True, exist_ok=True)
    deduped: dict[str, dict[str, Any]] = {}
    raw_counts: dict[str, int] = {}
    for key, query in QUERIES.items():
        raw_path = raw_dir / f"{key}.jsonl"
        works = read_jsonl(raw_path) if raw_path.exists() else None
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
            key_ = stable_key(simple)
            deduped[key_] = merge_work(deduped[key_], simple) if key_ in deduped else simple

    works = list(deduped.values())
    works.sort(key=lambda item: (item.get("cited_by_count") or 0, item.get("year") or 0), reverse=True)
    for index, work in enumerate(works, start=1):
        work["source_id"] = f"PSY{index:04d}"
        work["themes"] = classify_themes(work)

    top = [work for work in works if work.get("is_top_venue")]
    if len(top) < args.top_count:
        seen = {stable_key(work) for work in top}
        for work in works:
            if stable_key(work) in seen:
                continue
            if work.get("cited_by_count", 0) >= 250:
                top.append(work)
                seen.add(stable_key(work))
            if len(top) >= args.top_count:
                break
    top = sorted(
        top,
        key=lambda item: (item.get("is_top_venue"), item.get("cited_by_count") or 0),
        reverse=True,
    )[: args.top_count]

    write_jsonl(out_dir / "works.jsonl", works)
    write_csv(out_dir / "works.csv", works)
    write_jsonl(out_dir / "top_journal_candidates.jsonl", top)
    write_csv(out_dir / "top_journal_candidates.csv", top)
    write_jsonl(out_dir / "curated" / "top_200.jsonl", top[:200])
    write_markdown(out_dir, works, top)
    manifest = {
        "generated_at": time.strftime("%Y-%m-%dT%H:%M:%S%z"),
        "source": "OpenAlex Works API",
        "source_url": OPENALEX_URL,
        "queries": QUERIES,
        "raw_counts": raw_counts,
        "deduplicated_count": len(works),
        "top_candidate_count": len(top),
        "top_200_count": len(top[:200]),
        "top_venues": sorted(TOP_VENUES),
        "theme_keywords": THEME_KEYWORDS,
        "non_diagnostic_boundary": True,
    }
    (out_dir / "manifest.json").write_text(
        json.dumps(manifest, ensure_ascii=False, indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
    )
    print(json.dumps(manifest, ensure_ascii=False, indent=2, sort_keys=True))


if __name__ == "__main__":
    main()
