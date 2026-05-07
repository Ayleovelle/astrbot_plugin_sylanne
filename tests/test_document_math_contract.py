import re
import unittest
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
MATH_DOCUMENTS = (
    ROOT / "README.md",
    ROOT / "docs" / "theory.md",
)

ALLOWED_MATH_MACROS = {
    "Delta",
    "Pi",
    "Sigma",
    "alpha",
    "arg",
    "begin",
    "beta",
    "delta",
    "end",
    "eta",
    "exp",
    "frac",
    "gamma",
    "ge",
    "in",
    "lambda",
    "left",
    "mathsf",
    "max",
    "min",
    "mathrm",
    "mu",
    "partial",
    "phi",
    "qquad",
    "right",
    "sqrt",
    "sum",
    "tanh",
    "theta",
}

GITHUB_SENSITIVE_MACROS = {
    "bbox",
    "boldsymbol",
    "class",
    "cssId",
    "def",
    "gdef",
    "href",
    "html",
    "let",
    "lVert",
    "lvert",
    "mathbb",
    "newcommand",
    "operatorname",
    "overset",
    "renewcommand",
    "require",
    "rVert",
    "rvert",
    "style",
    "underset",
    "url",
}

COMMAND_PATTERN = re.compile(r"\\([A-Za-z]+)\*?")
FENCE_PATTERN = re.compile(r"^```([A-Za-z0-9_-]*)\s*$")


def iter_fenced_blocks(path):
    lines = path.read_text(encoding="utf-8").splitlines()
    in_fence = False
    language = ""
    start_line = 0
    body = []

    for index, line in enumerate(lines, start=1):
        match = FENCE_PATTERN.match(line)
        if not match:
            if in_fence:
                body.append((index, line))
            continue

        if not in_fence:
            in_fence = True
            language = match.group(1)
            start_line = index
            body = []
            continue

        yield {
            "path": path,
            "language": language,
            "start_line": start_line,
            "end_line": index,
            "body": body,
        }
        in_fence = False
        language = ""
        start_line = 0
        body = []

    if in_fence:
        raise AssertionError(f"{path} has an unclosed fenced block at line {start_line}")


def iter_math_blocks():
    for path in MATH_DOCUMENTS:
        for block in iter_fenced_blocks(path):
            if block["language"] == "math":
                yield block


class DocumentMathContractTests(unittest.TestCase):
    def test_theory_sections_default_to_summary_with_collapsed_full_version(self):
        readme = (ROOT / "README.md").read_text(encoding="utf-8")
        theory = (ROOT / "docs" / "theory.md").read_text(encoding="utf-8")

        self.assertIn("### 默认阅读：核心模型摘要", readme)
        self.assertIn("<summary>展开完整公式推导与顶刊依据</summary>", readme)
        self.assertIn("<summary>展开扩展冲突成因与关系修复公式</summary>", readme)
        self.assertIn("#### 顶刊证据映射", readme)
        self.assertIn("10.1177/0956797610372634", readme)
        self.assertIn("10.1037/a0013965", readme)
        self.assertIn("astrbot.personality_profile.v1", readme)
        self.assertIn("personality_literature_kb/curated/top_500.jsonl", readme)
        self.assertIn("Raw retrieved records: `21964`", readme)
        self.assertIn("Deduplicated works: `19196`", readme)
        self.assertIn(
            "<summary>展开行动倾向、关系决策与后果衰减公式</summary>",
            readme,
        )
        self.assertIn("O_t = 2^{-\\Delta t/H_o}O_{t-1}", readme)
        self.assertIn("## 重点版", theory)
        self.assertIn(
            "<summary>展开完整理论论证、公式推导与参考文献</summary>",
            theory,
        )
        self.assertEqual(theory.count("## 2. 从认知评价到维度观测"), 0)
        self.assertIn("## 2. 输入与建模假设", theory)
        self.assertIn("PUBLIC_PERSONALITY_PROFILE_SCHEMA_VERSION", theory)
        self.assertIn("PERS-F001", theory)
        self.assertIn("10.1146/annurev.ps.41.020190.002221", theory)
        self.assertNotIn("Q_t", readme)
        self.assertNotIn("Q_t", theory)
        self.assertNotIn("E_(t-1)", readme)
        self.assertNotIn("E_(t-1)", theory)

    def test_formula_blocks_use_github_math_fences(self):
        counts = {}
        for path in MATH_DOCUMENTS:
            blocks = list(iter_fenced_blocks(path))
            counts[path.name] = sum(1 for block in blocks if block["language"] == "math")
            suspicious_plain_formula_blocks = [
                block["start_line"]
                for block in blocks
                if block["language"] in {"text", ""}
                and any(COMMAND_PATTERN.search(line) for _, line in block["body"])
            ]

            with self.subTest(path=path.name):
                self.assertEqual(suspicious_plain_formula_blocks, [])

        self.assertGreaterEqual(counts["README.md"], 20)
        self.assertGreaterEqual(counts["theory.md"], 30)

    def test_math_blocks_use_only_github_safe_macro_surface(self):
        violations = []
        unknown = []
        for block in iter_math_blocks():
            for line_number, line in block["body"]:
                for command in COMMAND_PATTERN.findall(line):
                    if command in GITHUB_SENSITIVE_MACROS:
                        violations.append(f"{block['path']}:{line_number}:\\{command}")
                    elif command not in ALLOWED_MATH_MACROS:
                        unknown.append(f"{block['path']}:{line_number}:\\{command}")

        self.assertEqual(violations, [])
        self.assertEqual(unknown, [])

    def test_math_blocks_avoid_markdown_and_unicode_fragility(self):
        fragile = []
        for block in iter_math_blocks():
            for line_number, line in block["body"]:
                if any(ord(char) > 127 for char in line):
                    fragile.append(f"{block['path']}:{line_number}: non-ascii math")
                if "->" in line or "=>" in line:
                    fragile.append(f"{block['path']}:{line_number}: text arrow in math")
                if "$$" in line:
                    fragile.append(f"{block['path']}:{line_number}: nested dollar math")

        self.assertEqual(fragile, [])

    def test_argmin_and_indicator_notation_are_braced_and_stable(self):
        issues = []
        for block in iter_math_blocks():
            for line_number, line in block["body"]:
                if re.search(r"\\arg\\min_[A-Za-z]", line):
                    issues.append(f"{block['path']}:{line_number}: unbraced argmin subscript")
                if r"\mathrm{I}[" in line:
                    issues.append(f"{block['path']}:{line_number}: bracketed indicator")
                if r"\operatorname" in line:
                    issues.append(f"{block['path']}:{line_number}: GitHub rejects operatorname")

        self.assertEqual(issues, [])


if __name__ == "__main__":
    unittest.main()
