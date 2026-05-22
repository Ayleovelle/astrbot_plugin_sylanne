from __future__ import annotations

import csv
import html
import json
from pathlib import Path

from PIL import Image, ImageDraw, ImageFont


ROOT = Path(__file__).resolve().parents[2]
DATA_DIR = ROOT / "figures" / "data"
ASSET_DIR = ROOT / "docs" / "assets"

FEATURE_SUMMARY = (
    ROOT
    / "output"
    / "remote_emotion_benchmark_official"
    / "remote-emotion-v050-gpt55-feature-state-layer-real"
    / "summary.json"
)
CONTROL_SUMMARY = (
    ROOT
    / "output"
    / "remote_emotion_benchmark_official"
    / "remote-emotion-v050-gpt55-noemotion-control-state-layer-c3-250-real"
    / "summary.json"
)
LIFECYCLE_SUMMARY = ROOT / "docs" / "assets" / "lifecycle_model_fit_summary.csv"

FEATURE_CSV = DATA_DIR / "theory_feature_matrix.csv"
LIFECYCLE_CSV = DATA_DIR / "theory_lifecycle_fit.csv"

FEATURE_SVG = ASSET_DIR / "theory_feature_matrix_overhead.svg"
FEATURE_PNG = ASSET_DIR / "theory_feature_matrix_overhead.png"
LIFECYCLE_SVG = ASSET_DIR / "theory_lifecycle_fit_explanation.svg"
LIFECYCLE_PNG = ASSET_DIR / "theory_lifecycle_fit_explanation.png"

COLORS = {
    "blue": "#2E86AB",
    "purple": "#A23B72",
    "orange": "#F18F01",
    "red": "#C73E1D",
    "green": "#4C956C",
    "dark": "#111827",
    "muted": "#6B7280",
    "grid": "#E5E7EB",
    "panel": "#F8FAFC",
}

CASE_LABELS = {
    "no_emotion_control": "关闭情绪对照",
    "baseline_minimal": "最小状态注入",
    "emotion_injection": "情绪注入",
    "low_reasoning": "低推理判断",
    "humanlike": "拟人状态",
    "lifelike_learning": "生命化学习",
    "personality_drift": "人格漂移",
    "moral_repair": "道德修复",
    "fallibility_low_risk": "瑕疵模拟",
    "integrated_self_full": "综合自我",
    "all_safe_modules": "全安全模块",
}


def load_font(size: int, bold: bool = False) -> ImageFont.FreeTypeFont:
    candidates = [
        Path("C:/Windows/Fonts/msyhbd.ttc" if bold else "C:/Windows/Fonts/msyh.ttc"),
        Path("C:/Windows/Fonts/simhei.ttf"),
        Path("C:/Windows/Fonts/simsun.ttc"),
    ]
    for path in candidates:
        if path.exists():
            return ImageFont.truetype(str(path), size=size)
    return ImageFont.load_default(size=size)


def safe_float(value: object) -> float:
    if value in (None, ""):
        return 0.0
    return float(value)


def read_json(path: Path) -> dict:
    return json.loads(path.read_text(encoding="utf-8"))


def build_feature_csv() -> list[dict[str, object]]:
    feature = read_json(FEATURE_SUMMARY)
    control = read_json(CONTROL_SUMMARY)
    baseline = feature["aggregate"]["by_case"]["baseline_minimal"]
    baseline_latency = baseline["latency_ms"]["mean"]
    baseline_p95 = baseline["latency_ms"]["p95"]
    baseline_tokens = baseline["tokens"]["mean"]
    deltas = feature["aggregate"]["deltas_vs_baseline_minimal"]

    rows: list[dict[str, object]] = []
    for case, item in feature["aggregate"]["by_case"].items():
        delta = deltas.get(case, {})
        rows.append(
            {
                "case": case,
                "label": CASE_LABELS.get(case, case),
                "sample_count": item["sample_count"],
                "error_count": item["error_count"],
                "mean_latency_ms": round(item["latency_ms"]["mean"], 2),
                "p95_latency_ms": round(item["latency_ms"]["p95"], 2),
                "mean_tokens": round(item["tokens"]["mean"], 2),
                "mean_latency_delta_ms": round(
                    delta.get("latency_mean_delta_ms", 0.0),
                    2,
                ),
                "p95_latency_delta_ms": round(
                    delta.get("latency_p95_delta_ms", 0.0),
                    2,
                ),
                "token_delta": round(delta.get("token_mean_delta", 0.0), 2),
                "source_run": feature["run_id"],
            }
        )

    control_case = control["aggregate"]["by_case"]["no_emotion_control"]
    rows.insert(
        1,
        {
            "case": "no_emotion_control",
            "label": CASE_LABELS["no_emotion_control"],
            "sample_count": control_case["sample_count"],
            "error_count": control_case["error_count"],
            "mean_latency_ms": round(control_case["latency_ms"]["mean"], 2),
            "p95_latency_ms": round(control_case["latency_ms"]["p95"], 2),
            "mean_tokens": round(control_case["tokens"]["mean"], 2),
            "mean_latency_delta_ms": round(
                control_case["latency_ms"]["mean"] - baseline_latency,
                2,
            ),
            "p95_latency_delta_ms": round(control_case["latency_ms"]["p95"] - baseline_p95, 2),
            "token_delta": round(control_case["tokens"]["mean"] - baseline_tokens, 2),
            "source_run": control["run_id"],
        },
    )

    DATA_DIR.mkdir(parents=True, exist_ok=True)
    with FEATURE_CSV.open("w", encoding="utf-8-sig", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=list(rows[0].keys()))
        writer.writeheader()
        writer.writerows(rows)
    return rows


def build_lifecycle_csv() -> list[dict[str, object]]:
    rows: list[dict[str, object]] = []
    with LIFECYCLE_SUMMARY.open("r", encoding="utf-8-sig", newline="") as handle:
        for row in csv.DictReader(handle):
            rows.append(
                {
                    "model": row["模型"],
                    "sample_count": int(row["样本数"]),
                    "error_count": int(row["错误数"]),
                    "mean_latency_ms": round(safe_float(row["平均延迟_ms"]), 2),
                    "p95_latency_ms": round(safe_float(row["p95延迟_ms"]), 2),
                    "mean_ttft_ms": round(safe_float(row["平均TTFT_ms"]), 2),
                    "mean_tokens": round(safe_float(row["平均token"]), 2),
                    "latency_slope_ms_per_log2_day": round(
                        safe_float(row["延迟斜率_ms每log2天"]),
                        2,
                    ),
                    "latency_fit_r2": round(safe_float(row["延迟拟合R2"]), 3),
                    "token_slope_per_log2_day": round(safe_float(row["token斜率_每log2天"]), 2),
                    "token_fit_r2": round(safe_float(row["token拟合R2"]), 3),
                }
            )

    with LIFECYCLE_CSV.open("w", encoding="utf-8-sig", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=list(rows[0].keys()))
        writer.writeheader()
        writer.writerows(rows)
    return rows


def scale(value: float, domain_min: float, domain_max: float, start: float, end: float) -> float:
    if domain_max == domain_min:
        return (start + end) / 2
    return start + (value - domain_min) / (domain_max - domain_min) * (end - start)


def svg_text(x: float, y: float, text: object, size: int = 14, color: str = "#111827", weight: str = "400", anchor: str = "start") -> str:
    escaped = html.escape(str(text))
    return (
        f'<text x="{x:.1f}" y="{y:.1f}" text-anchor="{anchor}" '
        f'font-family="Microsoft YaHei, Arial, sans-serif" font-size="{size}" '
        f'font-weight="{weight}" fill="{color}">{escaped}</text>'
    )


def render_feature_svg(rows: list[dict[str, object]]) -> None:
    plot_rows = [row for row in rows if row["case"] != "baseline_minimal"]
    width, height = 1280, 820
    left_x, right_x = 300, 830
    top, row_h = 110, 54
    bar_w = 360
    latency_values = [safe_float(row["mean_latency_delta_ms"]) for row in plot_rows]
    token_values = [safe_float(row["token_delta"]) for row in plot_rows]
    latency_min, latency_max = min(latency_values), max(latency_values)
    token_min, token_max = min(token_values), max(token_values)

    parts = [
        f'<svg xmlns="http://www.w3.org/2000/svg" width="{width}" height="{height}" viewBox="0 0 {width} {height}">',
        '<rect width="1280" height="820" fill="#FFFFFF"/>',
        svg_text(48, 48, "Figure 1  功能矩阵中的状态模块增量开销", 25, COLORS["dark"], "700"),
        svg_text(48, 78, "gpt-5.5 正式远程矩阵：2500 个有效样本，失败请求 0；增量相对 baseline_minimal。", 14, COLORS["muted"]),
        svg_text(left_x, 104, "平均延迟增量 ms", 15, COLORS["dark"], "700"),
        svg_text(right_x, 104, "平均 token 增量", 15, COLORS["dark"], "700"),
    ]

    for axis_x, values, domain in (
        (left_x, latency_values, (latency_min, latency_max)),
        (right_x, token_values, (token_min, token_max)),
    ):
        zero = scale(0, domain[0], domain[1], axis_x, axis_x + bar_w)
        parts.append(f'<line x1="{zero:.1f}" y1="{top - 18}" x2="{zero:.1f}" y2="{top + row_h * len(plot_rows) - 14}" stroke="{COLORS["grid"]}" stroke-width="2"/>')

    for idx, row in enumerate(plot_rows):
        y = top + idx * row_h
        parts.append(f'<rect x="32" y="{y - 26}" width="1216" height="44" rx="8" fill="{COLORS["panel"] if idx % 2 == 0 else "#FFFFFF"}"/>')
        parts.append(svg_text(52, y + 3, row["label"], 14, COLORS["dark"]))
        parts.append(svg_text(180, y + 3, f'n={row["sample_count"]}', 12, COLORS["muted"]))

        for axis_x, value, domain, color in (
            (left_x, safe_float(row["mean_latency_delta_ms"]), (latency_min, latency_max), COLORS["blue"]),
            (right_x, safe_float(row["token_delta"]), (token_min, token_max), COLORS["orange"]),
        ):
            zero = scale(0, domain[0], domain[1], axis_x, axis_x + bar_w)
            x = scale(value, domain[0], domain[1], axis_x, axis_x + bar_w)
            bar_x = min(zero, x)
            rect_w = max(3, abs(x - zero))
            fill = color if value >= 0 else COLORS["green"]
            parts.append(f'<rect x="{bar_x:.1f}" y="{y - 13}" width="{rect_w:.1f}" height="20" rx="4" fill="{fill}" opacity="0.88"/>')
            label_x = x + (8 if value >= 0 else -8)
            anchor = "start" if value >= 0 else "end"
            parts.append(svg_text(label_x, y + 3, f'{value:+.0f}', 12, COLORS["dark"], "600", anchor))

    parts.append(svg_text(48, 762, "注：端到端延迟包含 WebUI、AstrBot、provider、网络和模型排队；该图用于解释功能组合开销，不等同于纯本地插件耗时。", 13, COLORS["muted"]))
    parts.append("</svg>")
    FEATURE_SVG.write_text("\n".join(parts), encoding="utf-8")


def draw_feature_png(rows: list[dict[str, object]]) -> None:
    plot_rows = [row for row in rows if row["case"] != "baseline_minimal"]
    width, height = 1280, 820
    image = Image.new("RGB", (width, height), "white")
    draw = ImageDraw.Draw(image)
    title_font = load_font(25, True)
    head_font = load_font(15, True)
    text_font = load_font(14)
    small_font = load_font(12)
    note_font = load_font(13)

    draw.text((48, 26), "Figure 1  功能矩阵中的状态模块增量开销", font=title_font, fill=COLORS["dark"])
    draw.text((48, 62), "gpt-5.5 正式远程矩阵：2500 个有效样本，失败请求 0；增量相对 baseline_minimal。", font=text_font, fill=COLORS["muted"])
    left_x, right_x = 300, 830
    top, row_h = 110, 54
    bar_w = 360
    draw.text((left_x, 86), "平均延迟增量 ms", font=head_font, fill=COLORS["dark"])
    draw.text((right_x, 86), "平均 token 增量", font=head_font, fill=COLORS["dark"])

    latency_values = [safe_float(row["mean_latency_delta_ms"]) for row in plot_rows]
    token_values = [safe_float(row["token_delta"]) for row in plot_rows]
    domains = [
        (min(latency_values), max(latency_values)),
        (min(token_values), max(token_values)),
    ]

    for axis_x, domain in ((left_x, domains[0]), (right_x, domains[1])):
        zero = scale(0, domain[0], domain[1], axis_x, axis_x + bar_w)
        draw.line((zero, top - 18, zero, top + row_h * len(plot_rows) - 14), fill=COLORS["grid"], width=2)

    for idx, row in enumerate(plot_rows):
        y = top + idx * row_h
        bg = COLORS["panel"] if idx % 2 == 0 else "#FFFFFF"
        draw.rounded_rectangle((32, y - 26, 1248, y + 18), radius=8, fill=bg)
        draw.text((52, y - 14), str(row["label"]), font=text_font, fill=COLORS["dark"])
        draw.text((180, y - 13), f'n={row["sample_count"]}', font=small_font, fill=COLORS["muted"])

        for axis_x, value, domain, color in (
            (left_x, safe_float(row["mean_latency_delta_ms"]), domains[0], COLORS["blue"]),
            (right_x, safe_float(row["token_delta"]), domains[1], COLORS["orange"]),
        ):
            zero = scale(0, domain[0], domain[1], axis_x, axis_x + bar_w)
            x = scale(value, domain[0], domain[1], axis_x, axis_x + bar_w)
            bar_x = min(zero, x)
            rect_w = max(3, abs(x - zero))
            fill = color if value >= 0 else COLORS["green"]
            draw.rounded_rectangle((bar_x, y - 13, bar_x + rect_w, y + 7), radius=4, fill=fill)
            label = f"{value:+.0f}"
            label_w = draw.textlength(label, font=small_font)
            label_x = x + 8 if value >= 0 else x - label_w - 8
            draw.text((label_x, y - 12), label, font=small_font, fill=COLORS["dark"])

    draw.text((48, 742), "注：端到端延迟包含 WebUI、AstrBot、provider、网络和模型排队；该图用于解释功能组合开销，不等同于纯本地插件耗时。", font=note_font, fill=COLORS["muted"])
    image.save(FEATURE_PNG, dpi=(450, 450))


def render_lifecycle_svg(rows: list[dict[str, object]]) -> None:
    width, height = 1280, 820
    top, row_h = 112, 48
    left_x, right_x = 320, 805
    bar_w = 330
    latency_values = [safe_float(row["latency_slope_ms_per_log2_day"]) for row in rows]
    token_values = [safe_float(row["token_slope_per_log2_day"]) for row in rows]
    latency_domain = (min(latency_values), max(latency_values))
    token_domain = (min(token_values), max(token_values))

    parts = [
        f'<svg xmlns="http://www.w3.org/2000/svg" width="{width}" height="{height}" viewBox="0 0 {width} {height}">',
        '<rect width="1280" height="820" fill="#FFFFFF"/>',
        svg_text(48, 48, "Figure 2  跨模型生命周期模拟拟合解释", 25, COLORS["dark"], "700"),
        svg_text(48, 78, "状态级模拟时间覆盖 1d 到 1y；每个模型 9 个样本，斜率来自 y = beta0 + beta1 log2(天)。", 14, COLORS["muted"]),
        svg_text(left_x, 104, "延迟斜率 ms / log2(天)", 15, COLORS["dark"], "700"),
        svg_text(right_x, 104, "token 斜率 / log2(天)", 15, COLORS["dark"], "700"),
    ]

    for axis_x, domain in ((left_x, latency_domain), (right_x, token_domain)):
        zero = scale(0, domain[0], domain[1], axis_x, axis_x + bar_w)
        parts.append(f'<line x1="{zero:.1f}" y1="{top - 18}" x2="{zero:.1f}" y2="{top + row_h * len(rows) - 14}" stroke="{COLORS["grid"]}" stroke-width="2"/>')

    for idx, row in enumerate(rows):
        y = top + idx * row_h
        parts.append(f'<rect x="32" y="{y - 25}" width="1216" height="39" rx="8" fill="{COLORS["panel"] if idx % 2 == 0 else "#FFFFFF"}"/>')
        parts.append(svg_text(52, y + 1, row["model"], 13, COLORS["dark"]))
        parts.append(svg_text(210, y + 1, f'R2 {row["latency_fit_r2"]}/{row["token_fit_r2"]}', 11, COLORS["muted"]))
        for axis_x, value, domain, color in (
            (left_x, safe_float(row["latency_slope_ms_per_log2_day"]), latency_domain, COLORS["purple"]),
            (right_x, safe_float(row["token_slope_per_log2_day"]), token_domain, COLORS["red"]),
        ):
            zero = scale(0, domain[0], domain[1], axis_x, axis_x + bar_w)
            x = scale(value, domain[0], domain[1], axis_x, axis_x + bar_w)
            bar_x = min(zero, x)
            rect_w = max(3, abs(x - zero))
            fill = color if value >= 0 else COLORS["green"]
            parts.append(f'<rect x="{bar_x:.1f}" y="{y - 12}" width="{rect_w:.1f}" height="18" rx="4" fill="{fill}" opacity="0.88"/>')
            parts.append(svg_text(x + (8 if value >= 0 else -8), y + 1, f'{value:+.0f}', 11, COLORS["dark"], "600", "start" if value >= 0 else "end"))

    parts.append(svg_text(48, 760, "注：这是发布参考拟合。单模型每尺度 1 条样本，适合解释趋势和模型差异，不用于强因果或显著性结论。", 13, COLORS["muted"]))
    parts.append("</svg>")
    LIFECYCLE_SVG.write_text("\n".join(parts), encoding="utf-8")


def draw_lifecycle_png(rows: list[dict[str, object]]) -> None:
    width, height = 1280, 820
    image = Image.new("RGB", (width, height), "white")
    draw = ImageDraw.Draw(image)
    title_font = load_font(25, True)
    head_font = load_font(15, True)
    text_font = load_font(13)
    small_font = load_font(11)
    note_font = load_font(13)
    draw.text((48, 26), "Figure 2  跨模型生命周期模拟拟合解释", font=title_font, fill=COLORS["dark"])
    draw.text((48, 62), "状态级模拟时间覆盖 1d 到 1y；每个模型 9 个样本，斜率来自 y = beta0 + beta1 log2(天)。", font=text_font, fill=COLORS["muted"])

    top, row_h = 112, 48
    left_x, right_x = 320, 805
    bar_w = 330
    draw.text((left_x, 86), "延迟斜率 ms / log2(天)", font=head_font, fill=COLORS["dark"])
    draw.text((right_x, 86), "token 斜率 / log2(天)", font=head_font, fill=COLORS["dark"])

    latency_values = [safe_float(row["latency_slope_ms_per_log2_day"]) for row in rows]
    token_values = [safe_float(row["token_slope_per_log2_day"]) for row in rows]
    latency_domain = (min(latency_values), max(latency_values))
    token_domain = (min(token_values), max(token_values))
    for axis_x, domain in ((left_x, latency_domain), (right_x, token_domain)):
        zero = scale(0, domain[0], domain[1], axis_x, axis_x + bar_w)
        draw.line((zero, top - 18, zero, top + row_h * len(rows) - 14), fill=COLORS["grid"], width=2)

    for idx, row in enumerate(rows):
        y = top + idx * row_h
        bg = COLORS["panel"] if idx % 2 == 0 else "#FFFFFF"
        draw.rounded_rectangle((32, y - 25, 1248, y + 14), radius=8, fill=bg)
        draw.text((52, y - 14), str(row["model"]), font=text_font, fill=COLORS["dark"])
        draw.text((210, y - 12), f'R2 {row["latency_fit_r2"]}/{row["token_fit_r2"]}', font=small_font, fill=COLORS["muted"])
        for axis_x, value, domain, color in (
            (left_x, safe_float(row["latency_slope_ms_per_log2_day"]), latency_domain, COLORS["purple"]),
            (right_x, safe_float(row["token_slope_per_log2_day"]), token_domain, COLORS["red"]),
        ):
            zero = scale(0, domain[0], domain[1], axis_x, axis_x + bar_w)
            x = scale(value, domain[0], domain[1], axis_x, axis_x + bar_w)
            bar_x = min(zero, x)
            rect_w = max(3, abs(x - zero))
            fill = color if value >= 0 else COLORS["green"]
            draw.rounded_rectangle((bar_x, y - 12, bar_x + rect_w, y + 6), radius=4, fill=fill)
            label = f"{value:+.0f}"
            label_w = draw.textlength(label, font=small_font)
            label_x = x + 8 if value >= 0 else x - label_w - 8
            draw.text((label_x, y - 12), label, font=small_font, fill=COLORS["dark"])

    draw.text((48, 742), "注：这是发布参考拟合。单模型每尺度 1 条样本，适合解释趋势和模型差异，不用于强因果或显著性结论。", font=note_font, fill=COLORS["muted"])
    image.save(LIFECYCLE_PNG, dpi=(450, 450))


def main() -> None:
    ASSET_DIR.mkdir(parents=True, exist_ok=True)
    rows = build_feature_csv()
    lifecycle_rows = build_lifecycle_csv()
    render_feature_svg(rows)
    draw_feature_png(rows)
    render_lifecycle_svg(lifecycle_rows)
    draw_lifecycle_png(lifecycle_rows)
    for path in (FEATURE_CSV, LIFECYCLE_CSV, FEATURE_SVG, FEATURE_PNG, LIFECYCLE_SVG, LIFECYCLE_PNG):
        print(path.relative_to(ROOT).as_posix())


if __name__ == "__main__":
    main()
