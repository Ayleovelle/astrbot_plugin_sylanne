from __future__ import annotations

import argparse
import subprocess
import zipfile
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
PLUGIN_NAME = "astrbot_plugin_sylanne"

INCLUDE_ROOT_FILES = {
    "__init__.py",
    "main.py",
    "metadata.yaml",
    "_conf_schema.json",
    "requirements.txt",
    "README.md",
    "CHANGELOG.md",
    "LICENSE",
    "logo.png",
    "astrbot_widget.json",
}

INCLUDE_DIRS = {
    "sylanne_alpha",
    "pages",
    "UI",
}

ALLOWED_DOC_ASSETS: set[Path] = set()

EXCLUDED_FILES: set[Path] = set()

EXCLUDED_PARTS = {
    ".git",
    "__pycache__",
    ".pytest_cache",
    "output",
    "dist",
    "tests",
    "scripts",
    "raw",
    ".cache",
    "ChineseBQB",
    "auto-stickers",
    "sticker_cache",
    "sticker-cache",
    "stickers",
    "pet-frames",
    "literature_kb",
    "personality_literature_kb",
    "psychological_literature_kb",
    "humanlike_agent_literature_kb",
}

EXCLUDED_SUFFIXES = {
    ".pyc",
    ".pyo",
    ".stackdump",
}

EXCLUDED_FILENAMES = {
    "_identity.json",
    "_identity.json.tmp",
    "pet-contact-sheet.png",
    "sylanne-pet.webp",
    "BACKEND_API.md",
    "HANDOFF.md",
    "arknights-design-language.md",
}


def should_include(path: Path) -> bool:
    relative = path.relative_to(ROOT)
    if len(relative.parts) >= 2 and relative.parts[:2] == ("docs", "assets"):
        return relative in ALLOWED_DOC_ASSETS
    if len(relative.parts) >= 2 and relative.parts[:2] == ("docs", "reports"):
        return False
    if relative in EXCLUDED_FILES:
        return False
    parts = set(relative.parts)
    if parts & EXCLUDED_PARTS:
        return False
    if path.suffix in EXCLUDED_SUFFIXES:
        return False
    if path.name in EXCLUDED_FILENAMES:
        return False
    if len(relative.parts) == 1:
        return relative.name in INCLUDE_ROOT_FILES
    return relative.parts[0] in INCLUDE_DIRS


def _tracked_files() -> set[Path]:
    """Set of git-tracked files (absolute, resolved).

    Packaging must ship only tracked content: `rglob` over the working tree would
    otherwise sweep in git-ignored runtime artifacts that match the allowlist —
    e.g. ``sylanne_core/_identity.json`` (a per-install diagnostic copy_id) — which
    must never be distributed. Git lookup failures and empty results abort the
    build instead of silently widening the package to the whole working tree.
    """
    try:
        out = subprocess.run(
            ["git", "ls-files", "-z"],
            cwd=ROOT,
            capture_output=True,
            text=True,
            check=True,
        ).stdout
    except (OSError, subprocess.CalledProcessError) as exc:
        raise RuntimeError(
            "git ls-files failed; refusing to package untracked workspace files"
        ) from exc
    tracked = {(ROOT / rel).resolve() for rel in out.split("\0") if rel}
    if not tracked:
        raise RuntimeError(
            "git ls-files returned an empty file list; refusing to package"
        )
    return tracked


def collect_files(exclude_paths: set[Path] | None = None) -> list[Path]:
    resolved_excludes = {path.resolve() for path in (exclude_paths or set())}
    tracked = _tracked_files()
    files = [
        path for path in ROOT.rglob("*")
        if path.is_file()
        and path.resolve() not in resolved_excludes
        and path.resolve() in tracked
        and should_include(path)
    ]
    return sorted(files, key=lambda item: item.relative_to(ROOT).as_posix())


def build_package(output: Path) -> Path:
    output.parent.mkdir(parents=True, exist_ok=True)
    files = collect_files(exclude_paths={output})
    with zipfile.ZipFile(output, "w", compression=zipfile.ZIP_DEFLATED) as archive:
        archive.writestr(f"{PLUGIN_NAME}/", "")
        for file_path in files:
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
