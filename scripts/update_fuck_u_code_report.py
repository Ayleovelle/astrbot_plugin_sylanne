from __future__ import annotations

import argparse
import datetime as dt
import html
import json
import math
from dataclasses import dataclass
from pathlib import Path
from typing import Any


ROOT = Path(__file__).resolve().parents[1]
DEFAULT_INPUT = ROOT / "output" / "fuck_u_code" / "raw-report.json"
DEFAULT_OFFICIAL_MARKDOWN = ROOT / "output" / "fuck_u_code" / "raw-report.md"
DEFAULT_MARKDOWN = ROOT / "docs" / "reports" / "fuck-u-code.md"
DEFAULT_FERMENTATION_BADGE = ROOT / "docs" / "reports" / "fuck-u-code-fermentation.svg"
DEFAULT_POWERED_BADGE = ROOT / "docs" / "reports" / "fuck-u-code-powered.svg"


@dataclass(frozen=True)
class FileFinding:
    path: str
    quality_score: float
    fermentation_index: int
    critical_count: int
    error_count: int
    warning_count: int


@dataclass(frozen=True)
class FuckUCodeSummary:
    quality_score: float
    fermentation_index: float
    official_level: str
    total_files: int
    analyzed_files: int
    skipped_files: int
    analysis_time_ms: int
    critical_count: int
    error_count: int
    warning_count: int
    worst_files: tuple[FileFinding, ...]


def clamp_int(value: float, lower: int = 0, upper: int = 100) -> int:
    return max(lower, min(upper, int(round(value))))


def clamp_float(value: float, lower: float = 0.0, upper: float = 100.0) -> float:
    return max(lower, min(upper, value))


def normalize_path(value: Any) -> str:
    return str(value or "").replace("\\", "/")


def fermentation_score_from_quality(score: float) -> float:
    return clamp_float(100.0 - score)


def fermentation_from_quality(score: float) -> int:
    # Fuck-U-Code JSON 的 overallScore/score 是质量分，越高越好。
    # 我们展示给用户的“发酵指数”是坏味道，必须反向，越低越好。
    return clamp_int(fermentation_score_from_quality(score))


def format_score(score: float, digits: int = 1) -> str:
    return f"{score:.{digits}f}"


def format_fermentation_score(score: float) -> str:
    return format_score(score, digits=1)


def extract_official_overall_score(markdown: str) -> float | None:
    for line in markdown.splitlines():
        columns = [column.strip().strip("*").strip() for column in line.strip().strip("|").split("|")]
        if len(columns) >= 2 and columns[0] == "糟糕指数":
            value = columns[1].split("/", 1)[0].strip()
            try:
                return float(value)
            except ValueError:
                return None
    return None


def extract_official_level(markdown: str) -> str:
    for line in markdown.splitlines():
        columns = [column.strip() for column in line.strip().strip("|").split("|")]
        if len(columns) >= 2 and columns[0] == "屎山等级":
            return columns[1]
    return ""


def severity_counts(metrics: list[dict[str, Any]]) -> tuple[int, int, int]:
    critical = error = warning = 0
    for metric in metrics:
        severity = str(metric.get("severity", "")).lower()
        if severity == "critical":
            critical += 1
        elif severity == "error":
            error += 1
        elif severity == "warning":
            warning += 1
    return critical, error, warning


def summarize_report(
    report: dict[str, Any],
    *,
    official_markdown: str = "",
    top: int,
) -> FuckUCodeSummary:
    quality_score = float(report.get("overallScore", 0.0) or 0.0)
    summary = report.get("summary", {}) or {}
    findings: list[FileFinding] = []
    critical_count = error_count = warning_count = 0

    for item in report.get("files", []) or []:
        metrics = item.get("metrics", []) or []
        critical, error, warning = severity_counts(metrics)
        critical_count += critical
        error_count += error
        warning_count += warning
        file_score = float(item.get("score", 0.0) or 0.0)
        findings.append(
            FileFinding(
                path=normalize_path(item.get("path")),
                quality_score=file_score,
                fermentation_index=fermentation_from_quality(file_score),
                critical_count=critical,
                error_count=error,
                warning_count=warning,
            ),
        )

    findings.sort(
        key=lambda finding: (
            -finding.fermentation_index,
            -finding.critical_count,
            -finding.error_count,
            -finding.warning_count,
            finding.path,
        ),
    )

    return FuckUCodeSummary(
        quality_score=quality_score,
        fermentation_index=fermentation_score_from_quality(
            extract_official_overall_score(official_markdown) or quality_score,
        ),
        official_level=extract_official_level(official_markdown),
        total_files=int(summary.get("totalFiles", 0) or 0),
        analyzed_files=int(summary.get("analyzedFiles", 0) or 0),
        skipped_files=int(summary.get("skippedFiles", 0) or 0),
        analysis_time_ms=int(summary.get("analysisTime", 0) or 0),
        critical_count=critical_count,
        error_count=error_count,
        warning_count=warning_count,
        worst_files=tuple(findings[:top]),
    )


def badge_color(index: int) -> str:
    if index <= 20:
        return "#3fb950"
    if index <= 40:
        return "#a3be2f"
    if index <= 60:
        return "#d29922"
    if index <= 80:
        return "#f97316"
    return "#d73a49"


def text_width(text: str) -> int:
    width = 0
    for char in text:
        codepoint = ord(char)
        if char == " ":
            width += 4
        elif codepoint <= 0x007F:
            width += 7
        elif 0x4E00 <= codepoint <= 0x9FFF:
            width += 14
        else:
            width += 13
    return max(18, width + 10)


def render_badge(label: str, message: str, color: str) -> str:
    label_width = text_width(label)
    message_width = text_width(message)
    total_width = label_width + message_width
    label_text_x = label_width / 2
    message_text_x = label_width + message_width / 2
    escaped_label = html.escape(label, quote=True)
    escaped_message = html.escape(message, quote=True)
    aria = html.escape(f"{label} {message}", quote=True)
    return f"""<svg xmlns="http://www.w3.org/2000/svg" width="{total_width}" height="20" role="img" aria-label="{aria}">
  <title>{aria}</title>
  <linearGradient id="s" x2="0" y2="100%">
    <stop offset="0" stop-color="#fff" stop-opacity=".08"/>
    <stop offset="1" stop-color="#000" stop-opacity=".08"/>
  </linearGradient>
  <clipPath id="r"><rect width="{total_width}" height="20" rx="3" fill="#fff"/></clipPath>
  <g clip-path="url(#r)">
    <rect width="{label_width}" height="20" fill="#555"/>
    <rect x="{label_width}" width="{message_width}" height="20" fill="{color}"/>
    <rect width="{total_width}" height="20" fill="url(#s)"/>
  </g>
  <g fill="#fff" text-anchor="middle" font-family="Verdana, DejaVu Sans, Microsoft YaHei, Segoe UI Emoji, sans-serif" font-size="11">
    <text x="{label_text_x:.1f}" y="14">{escaped_label}</text>
    <text x="{message_text_x:.1f}" y="14">{escaped_message}</text>
  </g>
</svg>
"""


def render_markdown(summary: FuckUCodeSummary, *, source_path: Path) -> str:
    generated_at = dt.datetime.now(dt.timezone.utc).replace(microsecond=0).isoformat()
    rows = []
    for finding in summary.worst_files:
        rows.append(
            "| {ferment}/100 | {quality}/100 | {critical} | {error} | {warning} | `{path}` |".format(
                ferment=format_score(float(finding.fermentation_index)),
                quality=format_score(finding.quality_score),
                critical=finding.critical_count,
                error=finding.error_count,
                warning=finding.warning_count,
                path=finding.path,
            ),
        )
    if not rows:
        rows.append("| 0.0/100 | 100.0/100 | 0 | 0 | 0 | `暂无文件` |")

    return "\n".join(
        [
            "# Fuck-U-Code 发酵报告",
            "",
            "> powered by Fuck-U-Code；本报告由 `scripts/update_fuck_u_code_report.py` 根据官方 JSON 输出生成。",
            "",
            f"- 💩 发酵指数：`{format_fermentation_score(summary.fermentation_index)}/100`，官方评价：`{summary.official_level or '未识别'}`（由质量分反向换算，越低越好）",
            f"- 官方 JSON overallScore：`{format_score(summary.quality_score)}/100`",
            f"- 扫描规模：`{summary.analyzed_files}/{summary.total_files}` 个文件已分析，`{summary.skipped_files}` 个文件被跳过",
            f"- 问题计数：critical `{summary.critical_count}`，error `{summary.error_count}`，warning `{summary.warning_count}`",
            f"- 原始报告：`{source_path.as_posix()}`",
            f"- 生成时间：`{generated_at}`",
            "",
            "## 最需要除味的文件",
            "",
            "| 💩 发酵 | 质量分 | critical | error | warning | 文件 |",
            "| --- | --- | ---: | ---: | ---: | --- |",
            *rows,
            "",
            "## 读数说明",
            "",
            "README 徽章里的“发酵指数”按 `100 - Fuck-U-Code 质量分` 反向换算，越低越好；四字评价读取官方 Markdown 报告中的“屎山等级”。它不是发布门禁，只是一个让维护者快速闻到坏味道的仓库健康信号。",
            "",
        ],
    )


def write_report(summary: FuckUCodeSummary, args: argparse.Namespace) -> None:
    markdown_path = args.markdown
    fermentation_badge_path = args.fermentation_badge
    powered_badge_path = args.powered_badge
    for path in (markdown_path, fermentation_badge_path, powered_badge_path):
        path.parent.mkdir(parents=True, exist_ok=True)

    official_level = summary.official_level or "未识别"
    markdown_path.write_text(
        render_markdown(summary, source_path=args.input.relative_to(ROOT) if args.input.is_relative_to(ROOT) else args.input),
        encoding="utf-8",
    )
    fermentation_badge_path.write_text(
        render_badge(
            "💩 发酵指数",
            f"{format_fermentation_score(summary.fermentation_index)}/100 · {official_level}",
            badge_color(summary.fermentation_index),
        ),
        encoding="utf-8",
    )
    powered_badge_path.write_text(
        render_badge("powered by", "Fuck-U-Code", "#111827"),
        encoding="utf-8",
    )


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Generate Fuck-U-Code markdown and README badge assets.",
    )
    parser.add_argument("--input", type=Path, default=DEFAULT_INPUT)
    parser.add_argument("--official-markdown", type=Path, default=DEFAULT_OFFICIAL_MARKDOWN)
    parser.add_argument("--markdown", type=Path, default=DEFAULT_MARKDOWN)
    parser.add_argument("--fermentation-badge", type=Path, default=DEFAULT_FERMENTATION_BADGE)
    parser.add_argument("--powered-badge", type=Path, default=DEFAULT_POWERED_BADGE)
    parser.add_argument("--top", type=int, default=12)
    return parser.parse_args()


def main() -> None:
    args = parse_args()
    if not args.input.exists():
        raise SystemExit(f"Fuck-U-Code JSON report not found: {args.input}")
    report = json.loads(args.input.read_text(encoding="utf-8"))
    official_markdown = (
        args.official_markdown.read_text(encoding="utf-8")
        if args.official_markdown.exists()
        else ""
    )
    summary = summarize_report(
        report,
        official_markdown=official_markdown,
        top=max(1, args.top),
    )
    if not math.isfinite(summary.quality_score):
        raise SystemExit("Fuck-U-Code overallScore is not finite")
    write_report(summary, args)
    try:
        print(f"💩 发酵指数 {format_fermentation_score(summary.fermentation_index)}/100")
    except UnicodeEncodeError:
        print(f"发酵指数 {format_fermentation_score(summary.fermentation_index)}/100")


if __name__ == "__main__":
    main()
