from __future__ import annotations

import argparse
import zipfile
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
PLUGIN_NAME = "astrbot_plugin_emotional_state"

INCLUDE_ROOT_FILES = {
    "__init__.py",
    "main.py",
    "emotion_engine.py",
    "humanlike_engine.py",
    "psychological_screening.py",
    "prompts.py",
    "public_api.py",
    "metadata.yaml",
    "_conf_schema.json",
    "README.md",
    "requirements.txt",
}

INCLUDE_DIRS = {
    "docs",
    "literature_kb",
    "psychological_literature_kb",
    "humanlike_agent_literature_kb",
}

EXCLUDED_PARTS = {
    ".git",
    "__pycache__",
    ".pytest_cache",
    "output",
    "dist",
    "tests",
    "scripts",
    "raw",
}

EXCLUDED_SUFFIXES = {
    ".pyc",
    ".pyo",
}


def should_include(path: Path) -> bool:
    relative = path.relative_to(ROOT)
    parts = set(relative.parts)
    if parts & EXCLUDED_PARTS:
        return False
    if path.suffix in EXCLUDED_SUFFIXES:
        return False
    if len(relative.parts) == 1:
        return relative.name in INCLUDE_ROOT_FILES
    return relative.parts[0] in INCLUDE_DIRS


def collect_files() -> list[Path]:
    files = [
        path for path in ROOT.rglob("*")
        if path.is_file() and should_include(path)
    ]
    return sorted(files, key=lambda item: item.relative_to(ROOT).as_posix())


def build_package(output: Path) -> Path:
    output.parent.mkdir(parents=True, exist_ok=True)
    with zipfile.ZipFile(output, "w", compression=zipfile.ZIP_DEFLATED) as archive:
        archive.writestr(f"{PLUGIN_NAME}/", "")
        for file_path in collect_files():
            archive.write(
                file_path,
                Path(PLUGIN_NAME, file_path.relative_to(ROOT)).as_posix(),
            )
    return output


def main() -> None:
    parser = argparse.ArgumentParser(
        description="Build an AstrBot plugin zip without tests or local artifacts.",
    )
    parser.add_argument(
        "--output",
        type=Path,
        default=ROOT / "dist" / f"{PLUGIN_NAME}.zip",
        help="Output zip path.",
    )
    args = parser.parse_args()
    output = build_package(args.output)
    print(output)


if __name__ == "__main__":
    main()
