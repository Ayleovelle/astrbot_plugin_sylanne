# Humanlike Agent Literature Knowledge Base

Generated from OpenAlex metadata. This KB supports organism-like and humanlike simulation layers for AstrBot: homeostasis, fatigue, needs, personality, relationship memory, narrative identity, believable agents, computational psychiatry boundaries, and dependency safety.

This knowledge base supports simulated agent design only. It must not be used to claim that a bot has real consciousness, real illness, real pain, or clinical diagnostic status.

## Counts

- Deduplicated works: `3983`
- Top/high-impact candidates: `320`
- Curated top 200: `200`

## Rebuild

```powershell
py -3.13 scripts\build_humanlike_agent_literature_kb.py --out humanlike_agent_literature_kb --per-query 150 --top-count 320
```

## Files

- `works.jsonl` / `works.csv`: deduplicated metadata index.
- `top_journal_candidates.jsonl` / `.csv`: top venue or high-citation candidates.
- `curated/top_200.jsonl`: compact seed library for manual review.
- `evidence-map.md`: evidence-to-design map generated from metadata and abstracts.
- `design-rules.md`: mechanism-level design rules extracted from the evidence structure.
- `validation-report.md`: count and boundary checks.
- `manifest.json`: query, venue and generation metadata.
