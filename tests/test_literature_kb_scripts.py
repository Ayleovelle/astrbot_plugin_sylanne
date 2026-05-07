import importlib.util
import json
import tempfile
import unittest
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]


def load_script(name):
    path = ROOT / "scripts" / f"{name}.py"
    spec = importlib.util.spec_from_file_location(name, path)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def sample_openalex_work(
    *,
    title="Apology and forgiveness in close relationships",
    doi="https://doi.org/10.1234/example",
    venue="Journal of Personality and Social Psychology",
    cited_by=321,
    abstract_terms=None,
):
    abstract_terms = abstract_terms or {
        "apology": [0],
        "repair": [1],
        "trust": [2],
        "forgiveness": [3],
    }
    return {
        "id": "https://openalex.org/W123",
        "doi": doi,
        "display_name": title,
        "publication_year": 2024,
        "publication_date": "2024-01-01",
        "abstract_inverted_index": abstract_terms,
        "cited_by_count": cited_by,
        "primary_location": {
            "source": {
                "display_name": venue,
                "type": "journal",
            },
            "landing_page_url": "https://example.test/work",
        },
        "authorships": [
            {"author": {"display_name": "Alice Example"}},
            {"author": {"display_name": "Bob Example"}},
        ],
        "concepts": [
            {"display_name": "Psychology"},
            {"display_name": "Emotion"},
        ],
        "topics": [
            {"display_name": "Relationship repair"},
        ],
        "open_access": {"is_oa": True},
    }


class LiteratureKbScriptTests(unittest.TestCase):
    def test_emotion_kb_simplifies_merges_and_writes_outputs(self):
        module = load_script("build_literature_kb")
        work = module.simplify_work(
            sample_openalex_work(),
            query_key="forgiveness_repair",
            query="forgiveness apology repair",
        )
        duplicate = dict(work)
        duplicate["query_keys"] = ["trust_rupture_repair"]
        duplicate["queries"] = ["trust repair"]
        duplicate["cited_by_count"] = 999
        duplicate["abstract"] = ""

        merged = module.merge_work(work, duplicate)
        merged["source_id"] = "KB0001"
        merged["themes"] = module.classify_themes(merged)

        self.assertEqual(module.stable_key(merged), "doi:10.1234/example")
        self.assertEqual(merged["doi_url"], "https://doi.org/10.1234/example")
        self.assertEqual(merged["cited_by_count"], 999)
        self.assertEqual(
            merged["query_keys"],
            ["forgiveness_repair", "trust_rupture_repair"],
        )
        self.assertIn("forgiveness_apology_and_repair", merged["themes"])

        with tempfile.TemporaryDirectory() as temp_dir:
            out_dir = Path(temp_dir)
            module.write_jsonl(out_dir / "works.jsonl", [merged])
            module.write_csv(out_dir / "works.csv", [merged])
            module.write_markdown_outputs(out_dir, [merged], [merged])

            self.assertEqual(module.read_jsonl(out_dir / "works.jsonl")[0]["source_id"], "KB0001")
            self.assertIn("KB0001", (out_dir / "evidence-map.md").read_text(encoding="utf-8"))
            self.assertIn("forgiveness_apology_and_repair", (out_dir / "topic-summary.md").read_text(encoding="utf-8"))
            self.assertTrue((out_dir / "works.csv").read_text(encoding="utf-8-sig").startswith("openalex_id,"))

    def test_psychological_kb_detects_screeners_and_safety_boundaries(self):
        module = load_script("build_psychological_literature_kb")
        text = (
            "PHQ-9 GAD-7 screening validation with suicide crisis safety, "
            "clinical governance and human oversight"
        ).lower()
        work = module.simplify_work(
            sample_openalex_work(
                title="PHQ-9 and GAD-7 screening validation for suicide crisis safety",
                venue="JAMA Psychiatry",
                abstract_terms={
                    "phq-9": [0],
                    "gad-7": [1],
                    "screening": [2],
                    "suicide": [3],
                    "human": [4],
                    "oversight": [5],
                },
            ),
            query_key="phq9_screening",
            query="PHQ-9 depression screening validation questionnaire",
        )
        work["source_id"] = "PSY0001"
        work["themes"] = module.classify_themes(work)

        self.assertIn("PHQ", module.detect_scale(text))
        self.assertIn("GAD", module.detect_scale(text))
        self.assertEqual(module.detect_safety_risk(text), "crisis_or_self_harm")
        self.assertEqual(module.detect_human_oversight(text), "explicit")
        self.assertEqual(work["diagnostic_boundary"], "screening_or_validation")
        self.assertIn("clinical_scale_instruments", work["themes"])

        with tempfile.TemporaryDirectory() as temp_dir:
            out_dir = Path(temp_dir)
            module.write_jsonl(out_dir / "curated" / "top_200.jsonl", [work])
            module.write_csv(out_dir / "works.csv", [work])
            module.write_markdown(out_dir, [work], [work])

            self.assertEqual(module.read_jsonl(out_dir / "curated" / "top_200.jsonl")[0]["source_id"], "PSY0001")
            self.assertIn("non-diagnostic", (out_dir / "README.md").read_text(encoding="utf-8").lower())
            self.assertIn("PSY0001", (out_dir / "evidence-map.md").read_text(encoding="utf-8"))
            self.assertIn("clinical_scale_instruments", (out_dir / "topic-summary.md").read_text(encoding="utf-8"))

    def test_humanlike_kb_detects_mechanisms_and_design_rules(self):
        module = load_script("build_humanlike_agent_literature_kb")
        work = module.simplify_work(
            sample_openalex_work(
                title="Sleep fatigue workload and attachment in AI companions",
                venue="Computers in Human Behavior",
                abstract_terms={
                    "sleep": [0],
                    "fatigue": [1],
                    "workload": [2],
                    "attachment": [3],
                    "dependency": [4],
                    "anthropomorphism": [5],
                },
            ),
            query_key="ai_companion_safety",
            query="AI companion safety emotional dependency manipulation ethics chatbot",
        )
        work["source_id"] = "HLA0001"
        work["themes"] = module.classify_themes(work)

        self.assertIn("energy_budget", work["mechanism_tags"])
        self.assertIn("attachment_security", work["mechanism_tags"])
        self.assertIn("dependency_guard", work["mechanism_tags"])
        self.assertEqual(work["timescale"], "hours_to_days")
        self.assertIn("dependency_or_manipulation", work["risk_flags"])
        self.assertIn("safety_ethics_dependency", work["themes"])

        with tempfile.TemporaryDirectory() as temp_dir:
            out_dir = Path(temp_dir)
            module.write_jsonl(out_dir / "works.jsonl", [work])
            module.write_csv(out_dir / "works.csv", [work])
            module.write_markdown(out_dir, [work], [work])

            self.assertEqual(module.read_jsonl(out_dir / "works.jsonl")[0]["source_id"], "HLA0001")
            self.assertIn("HLA0001", (out_dir / "evidence-map.md").read_text(encoding="utf-8"))
            self.assertIn("simulated agent design only", (out_dir / "README.md").read_text(encoding="utf-8"))
            self.assertIn("dependency", (out_dir / "design-rules.md").read_text(encoding="utf-8"))

    def test_personality_kb_scores_traits_and_documents_20k_contract(self):
        module = load_script("build_personality_literature_kb")
        work = module.simplify_work(
            sample_openalex_work(
                title="Big Five personality structure and attachment anxiety in emotion regulation",
                venue="Journal of Personality and Social Psychology",
                abstract_terms={
                    "big": [0],
                    "five": [1],
                    "personality": [2],
                    "attachment": [3],
                    "anxiety": [4],
                    "emotion": [5],
                    "regulation": [6],
                },
            ),
            query_key="big_five_structure",
            query="Big Five personality structure five factor model",
        )
        work["themes"] = module.classify_themes(work)
        work["relevance_score"] = module.relevance_score(work)
        work["source_id"] = "PERS00001"

        self.assertIn("big_five_and_trait_structure", work["themes"])
        self.assertIn("attachment_and_relationship_priors", work["themes"])
        self.assertGreater(work["relevance_score"], 0.4)
        self.assertGreaterEqual(len(module.FOUNDATIONAL_SOURCES), 10)

        with tempfile.TemporaryDirectory() as temp_dir:
            out_dir = Path(temp_dir)
            module.write_jsonl(out_dir / "works.jsonl", [work])
            module.write_csv(out_dir / "works.csv", [work])
            module.write_markdown(out_dir, [work], [work], raw_total=20000, target=20000)

            self.assertEqual(module.read_jsonl(out_dir / "works.jsonl")[0]["source_id"], "PERS00001")
            self.assertIn("full-text reading", (out_dir / "README.md").read_text(encoding="utf-8"))
            self.assertIn("PERS-F001", (out_dir / "evidence-map.md").read_text(encoding="utf-8"))
            self.assertIn("Candidate Evidence Rows", (out_dir / "evidence-map.md").read_text(encoding="utf-8"))
            self.assertIn("big_five_and_trait_structure", (out_dir / "topic-summary.md").read_text(encoding="utf-8"))

    def test_jsonl_reader_returns_none_for_bad_cache(self):
        module = load_script("build_literature_kb")
        with tempfile.TemporaryDirectory() as temp_dir:
            bad_cache = Path(temp_dir) / "bad.jsonl"
            bad_cache.write_text("{not-json}\n", encoding="utf-8")
            self.assertIsNone(module.read_jsonl(bad_cache))


if __name__ == "__main__":
    unittest.main()
