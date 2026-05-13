import importlib.util
import json
import sys
import tempfile
import unittest
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]


def load_report_script():
    path = ROOT / "scripts" / "update_fuck_u_code_report.py"
    spec = importlib.util.spec_from_file_location("update_fuck_u_code_report", path)
    module = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = module
    spec.loader.exec_module(module)
    return module


class FuckUCodeReportTests(unittest.TestCase):
    def test_fermentation_index_is_inverse_quality_score(self):
        module = load_report_script()

        self.assertEqual(29, module.fermentation_from_quality(71.28))
        self.assertAlmostEqual(28.72, module.fermentation_score_from_quality(71.28))
        self.assertEqual(0, module.fermentation_from_quality(100))
        self.assertEqual(100, module.fermentation_from_quality(0))
        official_markdown = "| 屎山等级 | 😷 屎气扑鼻 |\n"
        self.assertEqual(71.28, module.extract_official_overall_score("| 糟糕指数 | **71.28/100** |\n"))
        self.assertEqual("😷 屎气扑鼻", module.extract_official_level(official_markdown))

    def test_generates_badges_and_markdown_from_json_report(self):
        module = load_report_script()
        report = {
            "overallScore": 71.2822332874792,
            "summary": {
                "totalFiles": 12,
                "analyzedFiles": 3,
                "skippedFiles": 9,
                "analysisTime": 123,
            },
            "files": [
                {
                    "path": "main.py",
                    "score": 60,
                    "metrics": [
                        {"severity": "critical"},
                        {"severity": "error"},
                        {"severity": "warning"},
                    ],
                },
                {
                    "path": "README.md",
                    "score": 90,
                    "metrics": [{"severity": "info"}],
                },
            ],
        }

        with tempfile.TemporaryDirectory() as temp_dir:
            base = Path(temp_dir)
            input_path = base / "raw-report.json"
            markdown_path = base / "fuck-u-code.md"
            fermentation_badge = base / "fuck-u-code-fermentation.svg"
            input_path.write_text(json.dumps(report), encoding="utf-8")
            args = type(
                "Args",
                (),
                {
                    "input": input_path,
                    "markdown": markdown_path,
                    "fermentation_badge": fermentation_badge,
                },
            )()

            summary = module.summarize_report(
                report,
                official_markdown=(
                    "| 糟糕指数 | **71.28/100** |\n"
                    "| 屎山等级 | 😷 屎气扑鼻 |\n"
                ),
                top=10,
            )
            module.write_report(summary, args)

            markdown = markdown_path.read_text(encoding="utf-8")
            ferment_svg = fermentation_badge.read_text(encoding="utf-8")

        self.assertIn("💩 发酵指数：`28.7/100`，官方评价：`😷 屎气扑鼻`", markdown)
        self.assertIn("官方 JSON overallScore：`71.3/100`", markdown)
        self.assertIn("powered by Fuck-U-Code", markdown)
        self.assertIn("| 40.0/100 | 60.0/100 | 1 | 1 | 1 | `main.py` |", markdown)
        self.assertIn("CODE SMELL BY", ferment_svg)
        self.assertIn("SCORE", ferment_svg)
        self.assertIn("28.7", ferment_svg)
        self.assertIn("屎气扑鼻", ferment_svg)
        self.assertFalse((base / "fuck-u-code-powered.svg").exists())


if __name__ == "__main__":
    unittest.main()
