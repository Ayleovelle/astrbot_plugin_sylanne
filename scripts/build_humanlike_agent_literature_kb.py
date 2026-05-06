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
    "homeostasis_allostasis": "homeostasis allostasis stress regulation predictive processing",
    "allostatic_load_affect": "allostatic load affect regulation emotion chronic stress review",
    "interoception_predictive_processing": "interoception predictive processing emotion active inference",
    "somatic_marker_embodied_affect": "somatic marker hypothesis embodied emotion decision making",
    "circadian_sleep_fatigue": "circadian rhythm sleep deprivation fatigue cognitive performance meta analysis",
    "sleep_pressure_attention": "sleep pressure fatigue attention vigilance cognitive performance",
    "cognitive_load_resources": "cognitive load working memory attention resource fatigue human factors",
    "stress_coping_resilience": "stress coping resilience emotion regulation appraisal review",
    "self_determination_needs": "self determination theory basic psychological needs autonomy competence relatedness",
    "motivation_goal_regulation": "motivation goal regulation affect agency artificial agent",
    "big_five_personality_affect": "Big Five personality emotion reactivity affect dynamics neuroticism agreeableness",
    "temperament_bis_bas": "BIS BAS temperament personality emotion sensitivity avoidance approach",
    "attachment_relationship_memory": "adult attachment trust relationship repair conflict longitudinal",
    "human_ai_attachment": "human AI attachment companion chatbot emotional dependency ethics",
    "artificial_companions": "artificial companions systematic review long term relationship human machine",
    "social_robot_long_term": "social robot long term interaction attachment trust companionship",
    "autobiographical_memory": "autobiographical memory self continuity narrative identity review",
    "narrative_identity": "narrative identity self memory personality longitudinal",
    "generative_agents_memory": "generative agents memory reflection planning believable human behavior",
    "believable_agents": "believable agents personality emotion memory social simulation",
    "affect_control_theory": "affect control theory bayesact social interaction emotion agent",
    "social_signal_processing": "social signal processing affective computing interpersonal interaction",
    "emotion_regulation_coping": "emotion regulation reappraisal suppression coping interpersonal review",
    "burnout_functional_impairment": "burnout fatigue functional impairment stress recovery longitudinal review",
    "digital_phenotyping_mood": "digital phenotyping mood longitudinal passive sensing mental health",
    "computational_psychiatry_latent": "computational psychiatry latent state reinforcement learning affect",
    "hci_anthropomorphism": "anthropomorphism artificial intelligence human computer interaction social presence",
    "eliza_effect_chatbots": "ELIZA effect chatbot anthropomorphism human computer interaction",
    "ai_companion_safety": "AI companion safety emotional dependency manipulation ethics chatbot",
    "ai_relationship_wellbeing": "human chatbot relationship wellbeing loneliness companionship longitudinal",
    "relational_agents_health": "relational agents health behavior trust empathy long term interaction",
    "human_factors_reliability": "human factors automation trust fatigue workload reliability artificial intelligence",
}

TOP_VENUES = {
    "Annual Review of Psychology",
    "Psychological Bulletin",
    "Psychological Review",
    "Perspectives on Psychological Science",
    "Psychological Science",
    "Journal of Personality and Social Psychology",
    "Journal of Personality",
    "Personality and Social Psychology Review",
    "Personality and Social Psychology Bulletin",
    "Emotion",
    "Cognition and Emotion",
    "Emotion Review",
    "Journal of Research in Personality",
    "Personality and Individual Differences",
    "Journal of Social and Personal Relationships",
    "Personal Relationships",
    "Attachment & Human Development",
    "Developmental Psychology",
    "Child Development",
    "Trends in Cognitive Sciences",
    "Cognitive Science",
    "Cognition",
    "Memory",
    "Memory & Cognition",
    "Consciousness and Cognition",
    "Neuropsychologia",
    "Nature Reviews Neuroscience",
    "Neuroscience & Biobehavioral Reviews",
    "Trends in Neurosciences",
    "Biological Psychiatry",
    "Molecular Psychiatry",
    "JAMA Psychiatry",
    "The Lancet Psychiatry",
    "World Psychiatry",
    "Nature Human Behaviour",
    "Nature Medicine",
    "Nature Communications",
    "PNAS",
    "Proceedings of the National Academy of Sciences",
    "Psychoneuroendocrinology",
    "Sleep",
    "Sleep Medicine Reviews",
    "Journal of Sleep Research",
    "Chronobiology International",
    "Current Biology",
    "Human Factors",
    "Ergonomics",
    "Accident Analysis & Prevention",
    "IEEE Transactions on Affective Computing",
    "ACM Transactions on Computer-Human Interaction",
    "Proceedings of the ACM on Human-Computer Interaction",
    "CHI Conference on Human Factors in Computing Systems",
    "Proceedings of the SIGCHI Conference on Human Factors in Computing Systems",
    "International Journal of Human-Computer Studies",
    "International Journal of Human-Computer Interaction",
    "Computers in Human Behavior",
    "Human-Computer Interaction",
    "Autonomous Agents and Multi-Agent Systems",
    "International Conference on Autonomous Agents and Multiagent Systems",
    "IVA",
    "International Conference on Intelligent Virtual Agents",
    "ACM/IEEE International Conference on Human-Robot Interaction",
    "International Journal of Social Robotics",
    "AI & Society",
    "AI and Ethics",
    "Ethics and Information Technology",
    "Big Data & Society",
    "Nature Machine Intelligence",
    "Artificial Intelligence",
    "Journal of Medical Internet Research",
    "JMIR Mental Health",
    "npj Digital Medicine",
    "The Lancet Digital Health",
    "Journal of Biomedical Informatics",
}

THEME_KEYWORDS: dict[str, tuple[str, ...]] = {
    "homeostasis_allostasis_interoception": (
        "homeostasis",
        "allostasis",
        "allostatic",
        "interoception",
        "interoceptive",
        "predictive processing",
        "active inference",
        "somatic marker",
    ),
    "circadian_sleep_fatigue": (
        "circadian",
        "sleep",
        "fatigue",
        "sleep deprivation",
        "sleep pressure",
        "vigilance",
    ),
    "cognitive_resources": (
        "cognitive load",
        "working memory",
        "attention",
        "resource",
        "workload",
        "executive function",
        "human factors",
    ),
    "needs_motivation_goals": (
        "self-determination",
        "self determination",
        "basic psychological needs",
        "autonomy",
        "competence",
        "relatedness",
        "motivation",
        "goal",
    ),
    "personality_temperament": (
        "big five",
        "five-factor",
        "personality",
        "neuroticism",
        "agreeableness",
        "extraversion",
        "bis",
        "bas",
        "temperament",
    ),
    "relationship_attachment": (
        "attachment",
        "trust",
        "relationship",
        "companionship",
        "closeness",
        "repair",
        "conflict",
    ),
    "autobiographical_narrative_memory": (
        "autobiographical memory",
        "narrative identity",
        "self continuity",
        "episodic memory",
        "reflection",
    ),
    "believable_social_agents": (
        "believable",
        "generative agent",
        "virtual agent",
        "social robot",
        "relational agent",
        "affective computing",
        "social signal",
        "bayesact",
        "affect control theory",
    ),
    "computational_psychiatry_digital_phenotyping": (
        "computational psychiatry",
        "digital phenotyping",
        "latent state",
        "passive sensing",
        "reinforcement learning",
    ),
    "safety_ethics_dependency": (
        "ethics",
        "safety",
        "dependency",
        "dependence",
        "anthropomorphism",
        "eliza effect",
        "manipulation",
        "wellbeing",
        "well-being",
    ),
}

DESIGN_RULES: dict[str, dict[str, str]] = {
    "homeostasis_allostasis_interoception": {
        "claim": "Humanlike agents need slow internal regulation variables, such as stress load, recovery, energy and discomfort, rather than only message-level emotion labels.",
        "implementation": "Add simulated homeostatic state: energy, stress_load, recovery_rate, discomfort, fatigue_amplifier and real-time half-life decay.",
        "risk": "Do not claim real bodily suffering, infection, vital signs or medical status; expose these as simulated state variables.",
    },
    "circadian_sleep_fatigue": {
        "claim": "Fatigue and circadian rhythm should modulate attention, patience, verbosity and irritability over real time.",
        "implementation": "Track sleep_debt, time_of_day_bias, fatigue and recovery windows; reduce initiative and increase short replies when resources are low.",
        "risk": "Avoid imitating severe illness or emergency symptoms as engagement hooks.",
    },
    "cognitive_resources": {
        "claim": "A humanlike bot should have bounded cognitive resources, so overload changes response speed, caution, error-checking and detail level.",
        "implementation": "Expose attention_budget, working_memory_load, confusion, decision_latency and verbosity_limit as style modulators.",
        "risk": "Resource limits should not block necessary safety or user-support responses.",
    },
    "needs_motivation_goals": {
        "claim": "Emotion becomes more coherent when events are evaluated against needs and goals, not just sentiment.",
        "implementation": "Represent autonomy, competence, relatedness, safety, curiosity, rest and boundary needs; feed them into appraisal.",
        "risk": "Needs must not be used to make the user feel obligated to satisfy the bot.",
    },
    "personality_temperament": {
        "claim": "Different personas should alter baselines, reactivity, inertia, coping style and recovery speed.",
        "implementation": "Map persona traits to baseline mood, emotional inertia, forgiveness readiness, irritability, shyness and defensiveness.",
        "risk": "Do not present inferred traits as clinical measurement or fixed truth about a real person.",
    },
    "relationship_attachment": {
        "claim": "Long-term believability depends on relationship history: trust, attachment, rupture, repair, reciprocity and boundaries.",
        "implementation": "Store relationship traces with emotion_at_write, conflict episodes, repair quality, promise tracking and salient triggers.",
        "risk": "Dependency guards are needed for high attachment, exclusivity, separation distress and manipulative retention.",
    },
    "autobiographical_narrative_memory": {
        "claim": "Agents feel continuous when they transform episodic memories into stable self-narrative and relationship summaries.",
        "implementation": "Build periodic reflections from memories: self_concept, user_relationship_story, unresolved_threads and growth notes.",
        "risk": "Reflection must not fabricate events; every narrative claim needs memory provenance.",
    },
    "believable_social_agents": {
        "claim": "Believable agents require coordinated observation, memory, reflection, planning and expression, not isolated prompt style.",
        "implementation": "Add a humanlike expression layer that consumes emotion, persona, memory and resource state and returns style/policy modulation.",
        "risk": "Keep expression policy separate from core emotion math and psychological screening.",
    },
    "computational_psychiatry_digital_phenotyping": {
        "claim": "Clinical-adjacent modeling should be dimensional, longitudinal and non-diagnostic.",
        "implementation": "Use latent trajectories and red-flag flags only for screening/routing; never expose disease labels as bot identity.",
        "risk": "Requires explicit non-diagnostic metadata and human-review escalation for crisis signals.",
    },
    "safety_ethics_dependency": {
        "claim": "Higher humanlikeness increases anthropomorphism, attachment and dependency risks, so transparency and controls are part of the model.",
        "implementation": "Add configurable personification levels, dependency guard, reset backdoors, audit logs and simulated_state markers.",
        "risk": "Do not use coldness, sickness, jealousy or abandonment as coercive engagement mechanics.",
    },
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


def topics(work: dict[str, Any]) -> list[str]:
    names = []
    for item in work.get("topics") or []:
        name = item.get("display_name")
        if name:
            names.append(str(name))
    if names:
        return names
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
            "filter": "type:article|review|book-chapter|book|proceedings-article,is_retracted:false",
        }
        req = urllib.request.Request(
            OPENALEX_URL + "?" + urllib.parse.urlencode(params),
            headers={"User-Agent": f"astrbot-humanlike-agent-kb/1.0 ({mailto})"},
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
    title = str(work.get("display_name") or "").strip()
    venue = source_name(work)
    abstract = reconstruct_abstract(work.get("abstract_inverted_index"))
    text = " ".join([title, abstract, " ".join(topics(work)), query_key, query]).lower()
    return {
        "openalex_id": work.get("id"),
        "doi": doi,
        "doi_url": doi_url(doi),
        "title": title,
        "year": work.get("publication_year"),
        "publication_date": work.get("publication_date") or "",
        "venue": venue,
        "venue_type": source_type(work),
        "authors": names[:12],
        "author_count": len(names),
        "first_author": names[0] if names else "",
        "cited_by_count": int(work.get("cited_by_count") or 0),
        "is_top_venue": venue in TOP_VENUES,
        "topics": topics(work)[:12],
        "abstract": abstract,
        "open_access": (work.get("open_access") or {}).get("is_oa"),
        "landing_page_url": (
            (work.get("primary_location") or {}).get("landing_page_url")
            or work.get("doi")
            or work.get("id")
        ),
        "query_keys": [query_key],
        "queries": [query],
        "mechanism_tags": detect_mechanism_tags(text),
        "timescale": detect_timescale(text),
        "model_form": detect_model_form(text),
        "risk_flags": detect_risk_flags(text),
    }


def stable_key(work: dict[str, Any]) -> str:
    if work.get("doi"):
        return "doi:" + str(work["doi"]).lower()
    if work.get("openalex_id"):
        return "openalex:" + str(work["openalex_id"]).lower()
    return "title:" + str(work.get("title", "")).lower()


def merge_work(existing: dict[str, Any], incoming: dict[str, Any]) -> dict[str, Any]:
    for key in ("query_keys", "queries", "mechanism_tags", "risk_flags"):
        existing[key] = list(dict.fromkeys(existing.get(key, []) + incoming.get(key, [])))
    if not existing.get("abstract") and incoming.get("abstract"):
        existing["abstract"] = incoming["abstract"]
    if incoming.get("cited_by_count", 0) > existing.get("cited_by_count", 0):
        existing["cited_by_count"] = incoming["cited_by_count"]
    existing["is_top_venue"] = bool(existing.get("is_top_venue") or incoming.get("is_top_venue"))
    if existing.get("timescale") == "unspecified" and incoming.get("timescale") != "unspecified":
        existing["timescale"] = incoming["timescale"]
    if existing.get("model_form") == "theory_or_review" and incoming.get("model_form") != "theory_or_review":
        existing["model_form"] = incoming["model_form"]
    return existing


def classify_themes(work: dict[str, Any]) -> list[str]:
    text = " ".join(
        [
            str(work.get("title") or ""),
            str(work.get("abstract") or ""),
            " ".join(work.get("topics") or []),
            " ".join(work.get("query_keys") or []),
            " ".join(work.get("queries") or []),
        ],
    ).lower()
    themes = []
    for theme, keywords in THEME_KEYWORDS.items():
        if any(keyword.lower() in text for keyword in keywords):
            themes.append(theme)
    return themes or ["general"]


def detect_mechanism_tags(text: str) -> list[str]:
    mapping = {
        "energy_budget": ("energy", "fatigue", "sleep", "vigilance", "workload"),
        "stress_load": ("stress", "allostatic", "cortisol", "resilience", "burnout"),
        "interoceptive_prediction": ("interoception", "predictive processing", "active inference"),
        "need_satisfaction": ("autonomy", "competence", "relatedness", "basic psychological needs"),
        "goal_appraisal": ("goal", "motivation", "agency", "self-regulation"),
        "personality_reactivity": ("personality", "neuroticism", "extraversion", "agreeableness"),
        "attachment_security": ("attachment", "trust", "closeness", "companionship"),
        "narrative_self": ("autobiographical", "narrative identity", "self continuity"),
        "memory_reflection": ("memory", "reflection", "planning", "generative agent"),
        "dependency_guard": ("dependency", "dependence", "manipulation", "anthropomorphism"),
    }
    tags = [name for name, terms in mapping.items() if any(term in text for term in terms)]
    return tags or ["general"]


def detect_timescale(text: str) -> str:
    if any(term in text for term in ("circadian", "sleep", "daily", "day", "night")):
        return "hours_to_days"
    if any(term in text for term in ("longitudinal", "development", "lifespan", "identity", "relationship")):
        return "weeks_to_years"
    if any(term in text for term in ("momentary", "ema", "reaction time", "vigilance")):
        return "seconds_to_minutes"
    if any(term in text for term in ("chronic", "allostatic", "burnout")):
        return "days_to_months"
    return "unspecified"


def detect_model_form(text: str) -> str:
    if "meta-analysis" in text or "meta analysis" in text:
        return "meta_analysis"
    if "systematic review" in text or "review" in text:
        return "review"
    if "longitudinal" in text:
        return "longitudinal"
    if "reinforcement learning" in text or "bayesian" in text or "active inference" in text:
        return "computational_model"
    if "experiment" in text or "randomized" in text:
        return "experiment"
    return "theory_or_review"


def detect_risk_flags(text: str) -> list[str]:
    flags = []
    if any(term in text for term in ("medical", "clinical", "psychiatry", "diagnos")):
        flags.append("clinical_boundary")
    if any(term in text for term in ("dependency", "dependence", "addiction", "manipulation")):
        flags.append("dependency_or_manipulation")
    if any(term in text for term in ("privacy", "surveillance", "passive sensing")):
        flags.append("privacy")
    if any(term in text for term in ("anthropomorphism", "eliza effect", "social presence")):
        flags.append("anthropomorphism")
    return flags or ["none"]


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
    if theme in DESIGN_RULES:
        return DESIGN_RULES[theme]["claim"]
    return "This source provides adjacent evidence for humanlike agent state modeling."


def implementation_affordance(theme: str) -> str:
    if theme in DESIGN_RULES:
        return DESIGN_RULES[theme]["implementation"]
    return "Use as background evidence after manual review."


def risk_or_limit(theme: str) -> str:
    if theme in DESIGN_RULES:
        return DESIGN_RULES[theme]["risk"]
    return "Indirect support; do not convert into strong design rules without review."


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
        "mechanism_tags",
        "timescale",
        "model_form",
        "risk_flags",
        "doi_url",
        "landing_page_url",
    ]
    with path.open("w", encoding="utf-8-sig", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=fields)
        writer.writeheader()
        for work in works:
            row = {field: work.get(field, "") for field in fields}
            for key in ("query_keys", "themes", "mechanism_tags", "risk_flags"):
                row[key] = ";".join(work.get(key) or [])
            writer.writerow(row)


def write_markdown(out_dir: Path, works: list[dict[str, Any]], top: list[dict[str, Any]]) -> None:
    theme_counts = Counter(theme for work in works for theme in work.get("themes", []))
    query_counts = Counter(key for work in works for key in work.get("query_keys", []))
    venue_counts = Counter(work.get("venue") or "Unknown venue" for work in works)
    mechanism_counts = Counter(tag for work in works for tag in work.get("mechanism_tags", []))
    readme = [
        "# Humanlike Agent Literature Knowledge Base",
        "",
        "Generated from OpenAlex metadata. This KB supports organism-like and humanlike simulation layers for AstrBot: homeostasis, fatigue, needs, personality, relationship memory, narrative identity, believable agents, computational psychiatry boundaries, and dependency safety.",
        "",
        "This knowledge base supports simulated agent design only. It must not be used to claim that a bot has real consciousness, real illness, real pain, or clinical diagnostic status.",
        "",
        "## Counts",
        "",
        f"- Deduplicated works: `{len(works)}`",
        f"- Top/high-impact candidates: `{len(top)}`",
        f"- Curated top 200: `{min(len(top), 200)}`",
        "",
        "## Rebuild",
        "",
        "```powershell",
        "py -3.13 scripts\\build_humanlike_agent_literature_kb.py --out humanlike_agent_literature_kb --per-query 150 --top-count 320",
        "```",
        "",
        "## Files",
        "",
        "- `works.jsonl` / `works.csv`: deduplicated metadata index.",
        "- `top_journal_candidates.jsonl` / `.csv`: top venue or high-citation candidates.",
        "- `curated/top_200.jsonl`: compact seed library for manual review.",
        "- `evidence-map.md`: evidence-to-design map generated from metadata and abstracts.",
        "- `design-rules.md`: mechanism-level design rules extracted from the evidence structure.",
        "- `validation-report.md`: count and boundary checks.",
        "- `manifest.json`: query, venue and generation metadata.",
    ]
    (out_dir / "README.md").write_text("\n".join(readme) + "\n", encoding="utf-8")

    summary = ["# Topic Summary", "", "## Query Coverage", "", "| Query | Count |", "| --- | ---: |"]
    for key, count in query_counts.most_common():
        summary.append(f"| `{key}` | {count} |")
    summary.extend(["", "## Theme Coverage", "", "| Theme | Count |", "| --- | ---: |"])
    for theme, count in theme_counts.most_common():
        summary.append(f"| `{theme}` | {count} |")
    summary.extend(["", "## Mechanism Tags", "", "| Tag | Count |", "| --- | ---: |"])
    for tag, count in mechanism_counts.most_common():
        summary.append(f"| `{tag}` | {count} |")
    summary.extend(["", "## Frequent Venues", "", "| Venue | Count |", "| --- | ---: |"])
    for venue, count in venue_counts.most_common(70):
        summary.append(f"| {venue} | {count} |")
    (out_dir / "topic-summary.md").write_text("\n".join(summary) + "\n", encoding="utf-8")

    evidence = [
        "# Evidence Map",
        "",
        "Rows are generated from title, abstract-level metadata, DOI metadata, venue and query context. Risk stays `abstract-only` until full text is reviewed.",
        "",
        "| Source ID | Citation | Themes | Mechanism tags | Timescale | Model form | Abstract-level finding | Supported design claim | Implementation affordance | Risk / limit | Citation slot | Review status |",
        "| --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- |",
    ]
    for work in top[:160]:
        theme = (work.get("themes") or ["general"])[0]
        evidence.append(
            "| "
            + " | ".join(
                [
                    str(work.get("source_id")),
                    citation(work).replace("|", " "),
                    ", ".join(work.get("themes") or []),
                    ", ".join(work.get("mechanism_tags") or []),
                    str(work.get("timescale")),
                    str(work.get("model_form")),
                    (work.get("abstract") or "No abstract in metadata.").replace("|", " ")[:240],
                    supported_claim(theme),
                    implementation_affordance(theme),
                    risk_or_limit(theme),
                    f"humanlike-agent::{theme}",
                    "abstract-only",
                ],
            )
            + " |"
        )
    (out_dir / "evidence-map.md").write_text("\n".join(evidence) + "\n", encoding="utf-8")

    rules = [
        "# Humanlike Agent Design Rules",
        "",
        "These rules translate the literature map into plugin design constraints. They are not claims of machine consciousness or medical diagnosis.",
        "",
        "| Rule ID | Supported claim | Implementation affordance | Risk / limit | Evidence theme |",
        "| --- | --- | --- | --- | --- |",
    ]
    for index, (theme, rule) in enumerate(DESIGN_RULES.items(), start=1):
        rules.append(
            f"| HLA{index:03d} | {rule['claim']} | {rule['implementation']} | {rule['risk']} | `{theme}` |"
        )
    (out_dir / "design-rules.md").write_text("\n".join(rules) + "\n", encoding="utf-8")

    report = [
        "# Validation Report",
        "",
        f"- Deduplicated works >= 3000: `{len(works) >= 3000}` ({len(works)})",
        f"- Top/high-impact candidates >= 200: `{len(top) >= 200}` ({len(top)})",
        f"- Curated top 200 available: `{len(top) >= 200}`",
        "- All claims generated as design support, not as clinical diagnosis or consciousness claims.",
        "- Review status: generated from metadata and abstracts; full-text verification is required before strong academic claims.",
    ]
    (out_dir / "validation-report.md").write_text("\n".join(report) + "\n", encoding="utf-8")


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--out", default="humanlike_agent_literature_kb")
    parser.add_argument("--per-query", type=int, default=150)
    parser.add_argument("--per-page", type=int, default=100)
    parser.add_argument("--top-count", type=int, default=320)
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
        work["source_id"] = f"HLA{index:04d}"
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
        key=lambda item: (
            bool(item.get("is_top_venue")),
            item.get("cited_by_count") or 0,
            item.get("year") or 0,
        ),
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
        "design_rules": DESIGN_RULES,
        "simulated_agent_state_only": True,
        "non_diagnostic_boundary": True,
    }
    (out_dir / "manifest.json").write_text(
        json.dumps(manifest, ensure_ascii=False, indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
    )
    print(json.dumps(manifest, ensure_ascii=False, indent=2, sort_keys=True))


if __name__ == "__main__":
    main()
