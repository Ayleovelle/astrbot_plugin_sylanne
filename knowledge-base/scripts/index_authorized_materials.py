#!/usr/bin/env python3
"""Index user-authorized local civil engineering materials without redistributing them."""

from __future__ import annotations

import argparse
import hashlib
import json
from datetime import datetime, timezone
from pathlib import Path


ALLOWED_EXTENSIONS = {".pdf", ".docx", ".doc", ".dwg", ".dxf", ".xlsx", ".xls", ".txt", ".md"}


def classify(path: Path) -> str:
    name = path.name.lower()
    if any(word in name for word in ["计算书", "calculation", "calc"]):
        return "calculation-book"
    if path.suffix.lower() in {".dwg", ".dxf"} or any(word in name for word in ["图纸", "drawing", "plan"]):
        return "drawing"
    if any(word in name for word in ["规范", "标准", "gb", "jgj", "cjj", "standard", "code"]):
        return "standard-local-copy"
    return "civil-material"


def sha256(path: Path) -> str:
    h = hashlib.sha256()
    with path.open("rb") as fh:
        for chunk in iter(lambda: fh.read(1024 * 1024), b""):
            h.update(chunk)
    return h.hexdigest()


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--input", type=Path, required=True, help="directory containing user-authorized materials")
    parser.add_argument("--output", type=Path, required=True, help="JSONL index path")
    parser.add_argument("--hash", action="store_true", help="compute sha256 for every file")
    args = parser.parse_args()

    if not args.input.exists():
        raise SystemExit(f"Input directory not found: {args.input}")
    args.output.parent.mkdir(parents=True, exist_ok=True)
    indexed_at = datetime.now(timezone.utc).isoformat()
    count = 0
    with args.output.open("w", encoding="utf-8") as out:
        for path in args.input.rglob("*"):
            if not path.is_file() or path.suffix.lower() not in ALLOWED_EXTENSIONS:
                continue
            stat = path.stat()
            record = {
                "path": str(path.resolve()),
                "name": path.name,
                "extension": path.suffix.lower(),
                "bytes": stat.st_size,
                "modified_at": datetime.fromtimestamp(stat.st_mtime, timezone.utc).isoformat(),
                "category": classify(path),
                "indexed_at": indexed_at,
                "rights_note": "User-provided local material; do not redistribute without permission.",
            }
            if args.hash:
                record["sha256"] = sha256(path)
            out.write(json.dumps(record, ensure_ascii=False, sort_keys=True) + "\n")
            count += 1
    print(json.dumps({"indexed": count, "output": str(args.output)}, ensure_ascii=False, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
