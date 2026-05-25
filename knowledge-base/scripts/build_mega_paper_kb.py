#!/usr/bin/env python3
"""Build a large OpenAlex metadata knowledge base for AstrBot.

The builder stores metadata and links only. It does not download paper PDFs.
"""

from __future__ import annotations

import argparse
import gzip
import json
import math
import shutil
import time
import urllib.parse
import urllib.request
from urllib.error import HTTPError
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path


ROOT = Path(__file__).resolve().parent
OPENALEX_WORKS = "https://api.openalex.org/works"
OPENALEX_TOPICS = "https://api.openalex.org/topics"
DEFAULT_PER_PAGE = 100
DEFAULT_CHUNK_SIZE = 500
DEFAULT_FULL_TARGET = 20_000
DEFAULT_TOP_TARGET = 500

SELECT = ",".join(
    [
        "id",
        "doi",
        "title",
        "publication_year",
        "publication_date",
        "type",
        "language",
        "authorships",
        "primary_location",
        "open_access",
        "cited_by_count",
        "primary_topic",
        "topics",
        "keywords",
        "abstract_inverted_index",
        "updated_date",
    ]
)


@dataclass(frozen=True)
class Subject:
    slug: str
    zh_name: str
    en_name: str
    group: str
    filter: str
    note: str = ""
    top_filter: str = ""

    @classmethod
    def from_dict(cls, data: dict) -> "Subject":
        return cls(
            slug=data["slug"],
            zh_name=data["zh_name"],
            en_name=data["en_name"],
            group=data.get("group", ""),
            filter=data.get("filter", ""),
            note=data.get("note", ""),
            top_filter=data.get("top_filter", "") or data.get("filter", ""),
        )


def load_subjects(path: Path, only: set[str] | None = None) -> list[Subject]:
    items = json.loads(path.read_text(encoding="utf-8"))
    subjects = [Subject.from_dict(item) for item in items]
    if only:
        subjects = [subject for subject in subjects if subject.slug in only]
    missing = [subject.slug for subject in subjects if not subject.filter]
    if missing:
        raise SystemExit(f"Missing filter for subjects: {', '.join(missing)}")
    return subjects


def clean(value: object) -> str:
    if value is None:
        return ""
    if isinstance(value, bool):
        return "是" if value else "否"
    if isinstance(value, (int, float)):
        return str(value)
    text = str(value).replace("\r", " ").replace("\n", " ").strip()
    return " ".join(text.split())


def reconstruct_abstract(index: dict | None) -> str:
    if not index:
        return ""
    words: list[tuple[int, str]] = []
    for word, positions in index.items():
        for pos in positions:
            words.append((pos, word))
    return " ".join(word for _, word in sorted(words))


def source_from_location(location: dict | None) -> dict:
    if not isinstance(location, dict):
        return {
            "venue": "",
            "source_type": "",
            "publisher": "",
            "landing_page_url": "",
            "pdf_url": "",
            "issn_l": "",
        }
    source = location.get("source") or {}
    if not isinstance(source, dict):
        source = {}
    return {
        "venue": source.get("display_name") or location.get("raw_source_name") or "",
        "source_type": source.get("type") or "",
        "publisher": source.get("host_organization_name") or "",
        "landing_page_url": location.get("landing_page_url") or "",
        "pdf_url": location.get("pdf_url") or "",
        "issn_l": source.get("issn_l") or "",
    }


def list_display_names(items: list | None, limit: int) -> list[str]:
    names: list[str] = []
    for item in items or []:
        if isinstance(item, str):
            name = item
        elif isinstance(item, dict):
            name = item.get("display_name") or item.get("name") or item.get("keyword") or item.get("id") or ""
        else:
            name = str(item)
        if name:
            names.append(clean(name))
        if len(names) >= limit:
            break
    return names


def normalize_work(work: dict, subject: Subject, corpus_type: str, retrieved_at: str) -> dict:
    location = source_from_location(work.get("primary_location"))
    open_access = work.get("open_access") or {}
    topic = work.get("primary_topic") or {}
    authors = []
    for authorship in work.get("authorships") or []:
        author = authorship.get("author") or {}
        name = author.get("display_name")
        if name:
            authors.append(clean(name))
        if len(authors) >= 12:
            break
    return {
        "id": work.get("id") or "",
        "doi": work.get("doi") or "",
        "title": work.get("title") or "",
        "year": work.get("publication_year"),
        "publication_date": work.get("publication_date") or "",
        "type": work.get("type") or "",
        "language": work.get("language") or "",
        "authors": authors,
        "venue": location["venue"],
        "source_type": location["source_type"],
        "publisher": location["publisher"],
        "issn_l": location["issn_l"],
        "cited_by_count": work.get("cited_by_count") or 0,
        "is_oa": bool(open_access.get("is_oa")),
        "oa_status": open_access.get("oa_status") or "",
        "landing_page_url": location["landing_page_url"],
        "pdf_url": location["pdf_url"],
        "primary_topic": topic.get("display_name") if isinstance(topic, dict) else "",
        "topics": list_display_names(work.get("topics"), 10),
        "keywords": list_display_names(work.get("keywords"), 20),
        "abstract": reconstruct_abstract(work.get("abstract_inverted_index")),
        "subject": subject.zh_name,
        "subject_en": subject.en_name,
        "subject_slug": subject.slug,
        "subject_group": subject.group,
        "filter_note": subject.note,
        "corpus_type": corpus_type,
        "source": "openalex",
        "retrieved_at": retrieved_at,
    }


def fetch_json(url: str, user_agent: str, retries: int = 8) -> dict:
    last_error: Exception | None = None
    for attempt in range(retries):
        request = urllib.request.Request(url, headers={"User-Agent": user_agent})
        try:
            with urllib.request.urlopen(request, timeout=90) as response:
                return json.loads(response.read().decode("utf-8"))
        except HTTPError as exc:
            last_error = exc
            if exc.code == 429:
                retry_after = exc.headers.get("Retry-After")
                if retry_after and retry_after.isdigit():
                    delay = int(retry_after)
                else:
                    delay = min(900, 300 + 60 * attempt)
                print(f"rate limited (429); sleep={delay}s before retry", flush=True)
                time.sleep(delay)
                continue
            if 400 <= exc.code < 500:
                raise
            delay = min(180, 2 ** min(attempt, 7))
            print(f"http error attempt={attempt + 1}/{retries}; sleep={delay}s; error={exc}", flush=True)
            time.sleep(delay)
        except Exception as exc:  # noqa: BLE001
            last_error = exc
            delay = min(180, 2 ** min(attempt, 7))
            print(f"request failed attempt={attempt + 1}/{retries}; sleep={delay}s; error={exc}", flush=True)
            time.sleep(delay)
    raise RuntimeError(f"OpenAlex request failed after retries: {last_error}") from last_error


def build_url(filter_expr: str, cursor: str, per_page: int) -> str:
    params = {
        "filter": filter_expr,
        "sort": "cited_by_count:desc",
        "per-page": str(per_page),
        "cursor": cursor,
        "select": SELECT,
    }
    return OPENALEX_WORKS + "?" + urllib.parse.urlencode(params)


def count_filter(filter_expr: str, per_page: int) -> int:
    url = build_url(filter_expr, "*", per_page)
    data = fetch_json(url, "mega-paper-kb-count/1.0")
    return int(data.get("meta", {}).get("count") or 0)


def load_existing_jsonl(jsonl_path: Path) -> tuple[set[str], int]:
    seen: set[str] = set()
    if not jsonl_path.exists():
        return seen, 0
    with jsonl_path.open("r", encoding="utf-8") as existing:
        for line in existing:
            line = line.strip()
            if not line:
                continue
            try:
                record = json.loads(line)
            except json.JSONDecodeError:
                continue
            work_id = record.get("id")
            if work_id:
                seen.add(work_id)
    return seen, len(seen)


def collect(
    subject: Subject,
    corpus_type: str,
    filter_expr: str,
    target: int,
    per_page: int,
    request_sleep: float,
) -> tuple[Path, Path]:
    subject_dir = ROOT / "raw" / subject.slug
    subject_dir.mkdir(parents=True, exist_ok=True)
    jsonl_path = subject_dir / f"{subject.slug}_{corpus_type}.jsonl"
    gz_path = subject_dir / f"{subject.slug}_{corpus_type}.jsonl.gz"
    manifest_path = subject_dir / f"{subject.slug}_{corpus_type}_manifest.json"
    state_path = subject_dir / f"{subject.slug}_{corpus_type}_state.json"

    if gz_path.exists() and manifest_path.exists():
        try:
            manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
        except json.JSONDecodeError:
            manifest = {}
        if (
            manifest.get("records", 0) >= target
            and manifest.get("filter") == filter_expr
            and manifest.get("per_page") == per_page
        ):
            print(f"{subject.slug}/{corpus_type}: using existing {gz_path}", flush=True)
            return gz_path, manifest_path

    retrieved_at = datetime.now(timezone.utc).isoformat()
    user_agent = "mega-paper-kb-builder/1.0 (OpenAlex metadata only)"
    seen, count = load_existing_jsonl(jsonl_path)
    cursor = "*"
    pages = 0
    api_count = None
    if state_path.exists():
        try:
            state = json.loads(state_path.read_text(encoding="utf-8"))
        except json.JSONDecodeError:
            state = {}
        if state.get("filter") == filter_expr and state.get("per_page") == per_page:
            cursor = state.get("cursor") or "*"
            pages = int(state.get("pages") or 0)
            api_count = state.get("api_reported_count")
    if count:
        print(f"{subject.slug}/{corpus_type}: resuming count={count} pages={pages}", flush=True)

    with jsonl_path.open("a" if count else "w", encoding="utf-8") as fh:
        while count < target:
            data = fetch_json(build_url(filter_expr, cursor, per_page), user_agent=user_agent)
            pages += 1
            api_count = data.get("meta", {}).get("count", api_count)
            results = data.get("results") or []
            if not results:
                break
            for work in results:
                work_id = work.get("id")
                if not work_id or work_id in seen:
                    continue
                seen.add(work_id)
                record = normalize_work(work, subject, corpus_type, retrieved_at)
                if not record["title"]:
                    continue
                fh.write(json.dumps(record, ensure_ascii=False, sort_keys=True) + "\n")
                count += 1
                if count >= target:
                    break
            fh.flush()
            cursor = data.get("meta", {}).get("next_cursor")
            state_path.write_text(
                json.dumps(
                    {
                        "filter": filter_expr,
                        "per_page": per_page,
                        "cursor": cursor,
                        "count": count,
                        "pages": pages,
                        "api_reported_count": api_count,
                        "updated_at": datetime.now(timezone.utc).isoformat(),
                    },
                    ensure_ascii=False,
                    indent=2,
                ),
                encoding="utf-8",
            )
            print(f"{subject.slug}/{corpus_type}: collected={count}/{target} pages={pages}", flush=True)
            if not cursor:
                break
            time.sleep(request_sleep)

    if count < target:
        raise RuntimeError(f"{subject.slug}/{corpus_type}: only collected {count}, target {target}")

    with jsonl_path.open("rb") as src, gzip.open(gz_path, "wb") as dst:
        shutil.copyfileobj(src, dst)
    jsonl_path.unlink(missing_ok=True)
    state_path.unlink(missing_ok=True)
    manifest = {
        "name": f"{subject.slug}_{corpus_type}",
        "subject": subject.zh_name,
        "subject_en": subject.en_name,
        "subject_group": subject.group,
        "records": count,
        "target": target,
        "source": OPENALEX_WORKS,
        "filter": filter_expr,
        "sort": "cited_by_count:desc",
        "per_page": per_page,
        "api_reported_count": api_count,
        "retrieved_at": retrieved_at,
        "output": str(gz_path),
        "license_note": "OpenAlex metadata only; no copyrighted full-text PDFs are stored.",
        "note": subject.note,
    }
    manifest_path.write_text(json.dumps(manifest, ensure_ascii=False, indent=2), encoding="utf-8")
    return gz_path, manifest_path


def read_jsonl_gz(path: Path) -> list[dict]:
    records = []
    with gzip.open(path, "rt", encoding="utf-8") as fh:
        for line in fh:
            line = line.strip()
            if line:
                records.append(json.loads(line))
    return records


def record_to_markdown(record: dict, idx: int) -> str:
    title = clean(record.get("title") or "Untitled")
    doi = clean(record.get("doi")).replace("https://doi.org/", "")
    fields = [
        ("标题", title),
        ("作者", ", ".join(record.get("authors") or [])),
        ("年份", record.get("year")),
        ("出版日期", record.get("publication_date")),
        ("类型", record.get("type")),
        ("语言", record.get("language")),
        ("来源", record.get("venue")),
        ("来源类型", record.get("source_type")),
        ("出版方", record.get("publisher")),
        ("ISSN-L", record.get("issn_l")),
        ("OpenAlex 引用数", record.get("cited_by_count")),
        ("开放获取", record.get("is_oa")),
        ("OA 状态", record.get("oa_status")),
        ("DOI", doi),
        ("OpenAlex ID", record.get("id")),
        ("落地页", record.get("landing_page_url")),
        ("开放 PDF 链接", record.get("pdf_url")),
        ("主主题", record.get("primary_topic")),
        ("主题", ", ".join(record.get("topics") or [])),
        ("关键词", ", ".join(record.get("keywords") or [])),
        ("知识库方向", record.get("subject")),
        ("方向分组", record.get("subject_group")),
        ("语料类型", record.get("corpus_type")),
    ]
    lines = [f"## {idx}. {title}", ""]
    for label, value in fields:
        value_text = clean(value)
        if value_text:
            lines.append(f"- {label}：{value_text}")
    abstract = clean(record.get("abstract"))
    if abstract:
        lines.extend(["", "摘要：", abstract])
    lines.append("")
    return "\n".join(lines)


def markdown_for_corpus(subject: Subject, corpus_type: str, gz_path: Path, target: int, chunk_size: int) -> Path:
    records = read_jsonl_gz(gz_path)
    out_dir = ROOT / "knowledge-docs" / subject.slug / corpus_type
    if out_dir.exists():
        shutil.rmtree(out_dir)
    out_dir.mkdir(parents=True, exist_ok=True)
    parts = math.ceil(len(records) / chunk_size)
    index_lines = [
        f"# {subject.zh_name}（{subject.en_name}）OpenAlex 文献元数据索引",
        "",
        f"- 记录数：{len(records)}",
        f"- 目标记录数：{target}",
        f"- 语料类型：{corpus_type}",
        f"- 分组：{subject.group}",
        f"- 检索口径：{subject.note}",
        f"- 分卷大小：每卷 {chunk_size} 条",
        f"- 分卷数：{parts}",
        "- 边界：只含文献元数据与链接，不含受版权保护的论文全文；正式引用前必须核对 DOI、作者、年份、期刊。",
        "",
        "## 分卷",
        "",
    ]
    for part in range(parts):
        start = part * chunk_size
        end = min(start + chunk_size, len(records))
        file_name = f"{subject.slug}_{corpus_type}_part_{part+1:02d}_{start+1:05d}-{end:05d}.md"
        path = out_dir / file_name
        lines = [
            f"# {subject.zh_name} OpenAlex 文献元数据 {corpus_type} 第 {part+1:02d} 卷",
            "",
            f"- 范围：第 {start+1} 到 {end} 条",
            f"- 方向：{subject.zh_name}（{subject.en_name}）",
            f"- 分组：{subject.group}",
            f"- 语料类型：{corpus_type}",
            "- 用途：文献综述线索、研究主题定位、关键词扩展、代表性论文检索。",
            "- 注意：本卷不是论文全文库，不能替代正式阅读和引用核验。",
            "",
        ]
        for idx, record in enumerate(records[start:end], start + 1):
            lines.append(record_to_markdown(record, idx))
        path.write_text("\n".join(lines), encoding="utf-8")
        index_lines.append(f"- `{file_name}`：第 {start+1}-{end} 条")
    (out_dir / f"{subject.slug}_{corpus_type}_index.md").write_text(
        "\n".join(index_lines) + "\n",
        encoding="utf-8",
    )
    return out_dir


def copy_plugin_assets() -> None:
    assets = ROOT / "plugin-assets"
    if assets.exists():
        shutil.rmtree(assets)
    assets.mkdir(parents=True, exist_ok=True)
    raw = ROOT / "raw"
    if not raw.exists():
        return
    for path in raw.rglob("*"):
        if path.is_file():
            target = assets / path.relative_to(raw)
            target.parent.mkdir(parents=True, exist_ok=True)
            shutil.copy2(path, target)


def build_upload_batches() -> None:
    batch_root = ROOT / "upload-batches"
    if batch_root.exists():
        shutil.rmtree(batch_root)
    batch_root.mkdir(parents=True, exist_ok=True)
    files = sorted((ROOT / "knowledge-docs").rglob("*.md"))
    for i in range(0, len(files), 10):
        batch_num = i // 10 + 1
        batch_dir = batch_root / f"batch-{batch_num:03d}"
        batch_dir.mkdir(parents=True, exist_ok=True)
        for source in files[i : i + 10]:
            rel = source.relative_to(ROOT / "knowledge-docs")
            target = batch_dir / "__".join(rel.parts)
            shutil.copy2(source, target)
    lines = ["# 上传批次清单", "", "按 AstrBot 单次最多 10 个文件的限制整理。", ""]
    for batch_dir in sorted(p for p in batch_root.iterdir() if p.is_dir()):
        files_in_batch = sorted(batch_dir.iterdir())
        lines.append(f"## {batch_dir.name} ({len(files_in_batch)} files)")
        for file in files_in_batch:
            lines.append(f"- {file.name}")
        lines.append("")
    (batch_root / "UPLOAD_ORDER.md").write_text("\n".join(lines), encoding="utf-8")


def write_readme(subjects: list[Subject]) -> None:
    by_group: dict[str, list[Subject]] = {}
    for subject in subjects:
        by_group.setdefault(subject.group, []).append(subject)
    lines = [
        "# AstrBot 大型论文知识库",
        "",
        "本包只包含 OpenAlex 文献元数据与链接，不包含受版权保护的论文全文。",
        "",
        "## 主题",
        "",
    ]
    for group, group_subjects in by_group.items():
        lines.append(f"### {group}")
        for subject in group_subjects:
            lines.append(f"- {subject.zh_name}：20000 条元数据 + 500 条高被引期刊论文线索")
        lines.append("")
    lines.extend(
        [
            "## 目录",
            "",
            "- `knowledge-docs/`：可导入 AstrBot 知识库的 Markdown 分卷。",
            "- `upload-batches/`：按 AstrBot 上传限制整理后的批次目录，每批不超过 10 个文件。",
            "- `plugin-assets/`：原始 JSONL.GZ 元数据和 manifest，用于后续插件化精确检索。",
            "- `raw/`：构建过程生成的原始压缩语料。",
            "",
            "## 上传方式",
            "",
            "在 AstrBot WebUI 中新建知识库，建议名称：`工科论文综合知识库`。",
            "",
            "按 `upload-batches/UPLOAD_ORDER.md` 的顺序逐批上传。每批上传后等待解析/向量化完成，再传下一批。",
            "",
            "## 自定义规则建议",
            "",
            "```text",
            "你有一个“工科论文综合知识库”。当用户询问机器学习、计算机科学、数学建模、有限元、土木工程、力学、数学基础、方法论等方向的论文、综述、选题、研究路线或参考文献时，优先检索该知识库。",
            "",
            "知识库中的 OpenAlex 记录只作为文献检索线索和综述方向参考，不等同于论文全文证据。生成参考文献、引用格式、具体结论前，必须提醒用户核对 DOI、作者、年份、期刊/会议和原文内容。",
            "",
            "当用户要求“顶刊”时，优先使用 top-journal 子集；这里的“顶刊”默认指按 OpenAlex 高被引期刊论文筛选的高影响论文线索，不代表 CCF、JCR、中科院分区或学校指定目录。",
            "```",
            "",
        ]
    )
    (ROOT / "README.md").write_text("\n".join(lines), encoding="utf-8")


def write_summary(subjects: list[Subject]) -> None:
    rows = []
    for subject in subjects:
        for corpus_type in ["full", "top-journal"]:
            manifest_path = ROOT / "raw" / subject.slug / f"{subject.slug}_{corpus_type}_manifest.json"
            if manifest_path.exists():
                manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
                rows.append(
                    {
                        "subject": subject.zh_name,
                        "slug": subject.slug,
                        "corpus_type": corpus_type,
                        "records": manifest.get("records"),
                        "api_reported_count": manifest.get("api_reported_count"),
                        "filter": manifest.get("filter"),
                    }
                )
    (ROOT / "build_summary.json").write_text(json.dumps(rows, ensure_ascii=False, indent=2), encoding="utf-8")


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--subjects", type=Path, default=ROOT / "subjects.json")
    parser.add_argument("--only", default="", help="comma-separated subject slugs")
    parser.add_argument("--full-target", type=int, default=DEFAULT_FULL_TARGET)
    parser.add_argument("--top-target", type=int, default=DEFAULT_TOP_TARGET)
    parser.add_argument("--per-page", type=int, default=DEFAULT_PER_PAGE)
    parser.add_argument("--chunk-size", type=int, default=DEFAULT_CHUNK_SIZE)
    parser.add_argument("--request-sleep", type=float, default=5.0, help="seconds to sleep between successful pages")
    parser.add_argument("--count-only", action="store_true")
    args = parser.parse_args()

    only = {item.strip() for item in args.only.split(",") if item.strip()} or None
    subjects = load_subjects(args.subjects, only=only)
    if args.count_only:
        counts = []
        for subject in subjects:
            counts.append(
                {
                    "slug": subject.slug,
                    "zh_name": subject.zh_name,
                    "count": count_filter(subject.filter, args.per_page),
                }
            )
        print(json.dumps(counts, ensure_ascii=False, indent=2))
        return 0

    for subject in subjects:
        full_gz, _ = collect(subject, "full", subject.filter, args.full_target, args.per_page, args.request_sleep)
        top_gz, _ = collect(subject, "top-journal", subject.top_filter, args.top_target, args.per_page, args.request_sleep)
        markdown_for_corpus(subject, "full", full_gz, args.full_target, args.chunk_size)
        markdown_for_corpus(subject, "top-journal", top_gz, args.top_target, args.chunk_size)
    copy_plugin_assets()
    build_upload_batches()
    write_readme(subjects)
    write_summary(subjects)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
