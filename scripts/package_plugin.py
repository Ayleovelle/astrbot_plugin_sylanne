from __future__ import annotations

import argparse
import ast
import hashlib
import json
import re
import struct
import subprocess
import unicodedata
import zipfile
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
PLUGIN_NAME = "astrbot_plugin_sylanne"

# --- v3 grey/stable artifact channel -------------------------------------
#
# The v3 shadow is activated by a build-time flag, never by a user setting: the
# generated ``build_flags.py`` *replaces* the source entry inside the zip while
# the worktree stays untouched. Everything below exists to make that artifact
# auditable — a fixed archive layout, a payload digest anyone can recompute from
# the zip alone, and refusal conditions that fail the build closed.

CHANNELS = ("grey", "stable")

MANIFEST_NAME = "sylanne_build_manifest.json"
MANIFEST_ARCNAME = f"{PLUGIN_NAME}/{MANIFEST_NAME}"

BUILD_FLAGS_RELPATH = Path("sylanne_alpha/v3bridge/build_flags.py")
BUILD_FLAGS_ARCNAME = f"{PLUGIN_NAME}/{BUILD_FLAGS_RELPATH.as_posix()}"
MAIN_RELPATH = Path("main.py")
MAIN_ARCNAME = f"{PLUGIN_NAME}/{MAIN_RELPATH.as_posix()}"
METADATA_RELPATH = Path("metadata.yaml")
METADATA_ARCNAME = f"{PLUGIN_NAME}/{METADATA_RELPATH.as_posix()}"

V3_SOURCE_DIRS = ("sylanne_alpha/v3core", "sylanne_alpha/v3bridge")

# The engine is shipped as source only. Any other file under it is per-install
# runtime/identity state (e.g. the diagnostic ``_identity.json`` copy_id) and
# must never reach a distributed artifact.
ENGINE_PREFIX = f"{PLUGIN_NAME}/sylanne_alpha/_engine/"
ENGINE_ALLOWED_NAMES = ("py.typed",)

# One fixed timestamp/permission/compression policy: builds from the same
# tracked tree must be byte-identical.
ZIP_TIMESTAMP = (1980, 1, 1, 0, 0, 0)
ZIP_COMPRESSLEVEL = 6
ZIP_CREATE_SYSTEM = 3  # unix, regardless of the build host
FILE_EXTERNAL_ATTR = 0o100644 << 16
DIR_EXTERNAL_ATTR = (0o40755 << 16) | 0x10

_VERSION_PATTERN = re.compile(r"(?m)^version:[ \t]*(.+?)[ \t]*$")

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


def _git_output(args: list[str]) -> str:
    try:
        return subprocess.run(
            ["git", *args],
            cwd=ROOT,
            capture_output=True,
            text=True,
            check=True,
        ).stdout
    except (OSError, subprocess.CalledProcessError) as exc:
        raise RuntimeError(f"git {' '.join(args)} failed; refusing to package") from exc


def _paths_differing_from_head() -> set[Path]:
    """Tracked paths whose worktree/index content differs from committed HEAD.

    This is git's own content comparison, which is eol-normalized: with
    ``core.autocrlf=true`` most worktree files differ from their HEAD blob at the
    byte level while being identical as far as git is concerned. Comparing raw
    bytes instead would refuse every build on a CRLF checkout, so "differs from
    HEAD" means "``git diff HEAD`` reports it". Consequence to be aware of: a
    ``payload_digest`` is reproducible from the same checkout, not from the
    commit id alone across eol platforms.
    """
    out = _git_output(["diff", "--name-only", "-z", "HEAD", "--"])
    return {(ROOT / rel).resolve() for rel in out.split("\0") if rel}


def _head_commit() -> str:
    commit = _git_output(["rev-parse", "HEAD"]).strip()
    if not re.fullmatch(r"[0-9a-f]{40}", commit):
        raise RuntimeError(f"unexpected git HEAD commit {commit!r}; refusing to package")
    return commit


def _checked_metadata_override(metadata_override: Path | None) -> Path | None:
    """Validate a `--metadata` override before it is trusted as a generated entry.

    Generated entries are exempt from the HEAD-cleanliness check, so an override
    aimed back at the tracked `metadata.yaml` would smuggle uncommitted bytes
    into the archive while the manifest still names the old HEAD. The override
    must be a genuinely separate temporary copy.
    """
    if metadata_override is None:
        return None
    resolved = metadata_override.resolve()
    if resolved == (ROOT / METADATA_RELPATH).resolve():
        raise RuntimeError(
            "--metadata must be a temporary copy, not the tracked metadata.yaml; "
            "refusing to package"
        )
    return resolved


def _read_metadata_version(data: bytes) -> str:
    matches = _VERSION_PATTERN.findall(data.decode("utf-8"))
    if len(matches) != 1:
        raise RuntimeError(
            f"metadata.yaml must declare exactly one top-level version (found {len(matches)})"
        )
    return matches[0].strip().strip('"').strip("'")


class _ModulePluginVersionWriteVisitor(ast.NodeVisitor):
    """Find bindings that can change the module-level ``PLUGIN_VERSION`` name."""

    def __init__(self) -> None:
        self.writes: list[ast.AST] = []

    def _record_binding(self, name: str | None, node: ast.AST) -> None:
        if name == "PLUGIN_VERSION":
            self.writes.append(node)

    def visit_Name(self, node: ast.Name) -> None:
        if node.id == "PLUGIN_VERSION" and isinstance(node.ctx, (ast.Store, ast.Del)):
            self.writes.append(node)

    def _visit_function_header(self, node: ast.FunctionDef | ast.AsyncFunctionDef) -> None:
        self._record_binding(node.name, node)
        for decorator in node.decorator_list:
            self.visit(decorator)
        self.visit(node.args)
        if node.returns is not None:
            self.visit(node.returns)
        for type_param in getattr(node, "type_params", ()):  # Python 3.12+
            self.visit(type_param)

    def visit_FunctionDef(self, node: ast.FunctionDef) -> None:
        self._visit_function_header(node)

    def visit_AsyncFunctionDef(self, node: ast.AsyncFunctionDef) -> None:
        self._visit_function_header(node)

    def visit_Lambda(self, node: ast.Lambda) -> None:
        # Defaults/annotations execute in the containing scope; the body does not.
        self.visit(node.args)

    def visit_ClassDef(self, node: ast.ClassDef) -> None:
        self._record_binding(node.name, node)
        for decorator in node.decorator_list:
            self.visit(decorator)
        for base in node.bases:
            self.visit(base)
        for keyword in node.keywords:
            self.visit(keyword)
        for type_param in getattr(node, "type_params", ()):  # Python 3.12+
            self.visit(type_param)
        # The class body executes in a separate namespace, not the module namespace.

    def visit_Import(self, node: ast.Import) -> None:
        for alias in node.names:
            self._record_binding(alias.asname or alias.name.split(".", 1)[0], node)

    def visit_ImportFrom(self, node: ast.ImportFrom) -> None:
        for alias in node.names:
            self._record_binding(alias.asname or alias.name, node)

    def visit_ExceptHandler(self, node: ast.ExceptHandler) -> None:
        self._record_binding(node.name, node)
        if node.type is not None:
            self.visit(node.type)
        for statement in node.body:
            self.visit(statement)

    def visit_MatchAs(self, node: ast.MatchAs) -> None:
        self._record_binding(node.name, node)
        self.generic_visit(node)

    def visit_MatchStar(self, node: ast.MatchStar) -> None:
        self._record_binding(node.name, node)

    def visit_MatchMapping(self, node: ast.MatchMapping) -> None:
        self._record_binding(node.rest, node)
        self.generic_visit(node)


def _literal_string(node: ast.AST, label: str) -> str:
    try:
        value = ast.literal_eval(node)
    except (TypeError, ValueError) as exc:
        raise RuntimeError(f"{label} must be a string literal; refusing to package") from exc
    if not isinstance(value, str):
        raise RuntimeError(f"{label} must be a string literal; refusing to package")
    return value


def _main_release_identity_nodes(
    data: bytes,
) -> tuple[str, str, ast.expr, ast.expr]:
    try:
        tree = ast.parse(data.decode("utf-8"), filename=str(MAIN_RELPATH))
    except (SyntaxError, UnicodeDecodeError) as exc:
        raise RuntimeError("cannot parse main.py release identity; refusing to package") from exc

    direct_assignments: list[tuple[ast.Assign, ast.Name]] = []
    for node in tree.body:
        if isinstance(node, ast.Assign):
            direct_assignments.extend(
                (node, target)
                for target in node.targets
                if isinstance(target, ast.Name) and target.id == "PLUGIN_VERSION"
            )

    write_visitor = _ModulePluginVersionWriteVisitor()
    write_visitor.visit(tree)
    if (
        len(direct_assignments) != 1
        or len(write_visitor.writes) != 1
        or write_visitor.writes[0] is not direct_assignments[0][1]
    ):
        raise RuntimeError(
            "release identity requires exactly one PLUGIN_VERSION module-scope write, "
            "as a direct string assignment; refusing to package"
        )

    plugin_node = direct_assignments[0][0].value
    plugin_version = _literal_string(plugin_node, "PLUGIN_VERSION")

    register_nodes: list[ast.expr] = []
    for node in tree.body:
        if not isinstance(node, ast.ClassDef):
            continue
        for decorator in node.decorator_list:
            if not (
                isinstance(decorator, ast.Call)
                and isinstance(decorator.func, ast.Name)
                and decorator.func.id == "register"
            ):
                continue
            if len(decorator.args) < 4:
                raise RuntimeError(
                    "@register must declare its version as the fourth argument; "
                    "refusing to package"
                )
            register_nodes.append(decorator.args[3])

    if len(register_nodes) != 1:
        raise RuntimeError(
            "release identity requires exactly one @register version; refusing to package"
        )
    register_node = register_nodes[0]
    register_version = _literal_string(register_node, "@register version")
    return plugin_version, register_version, plugin_node, register_node


def _read_main_release_identity(data: bytes) -> tuple[str, str]:
    plugin_version, register_version, _plugin_node, _register_node = (
        _main_release_identity_nodes(data)
    )
    return plugin_version, register_version


def _ast_source_span(data: bytes, node: ast.AST) -> tuple[int, int]:
    if (
        not hasattr(node, "lineno")
        or not hasattr(node, "end_lineno")
        or node.end_lineno is None
        or node.end_col_offset is None
    ):
        raise RuntimeError("main.py release identity lacks source positions; refusing to package")
    lines = data.splitlines(keepends=True)
    if node.lineno < 1 or node.end_lineno > len(lines):
        raise RuntimeError("main.py release identity source position is invalid; refusing to package")
    start = sum(len(line) for line in lines[: node.lineno - 1]) + node.col_offset
    end = sum(len(line) for line in lines[: node.end_lineno - 1]) + node.end_col_offset
    if start < 0 or end <= start or end > len(data):
        raise RuntimeError("main.py release identity source span is invalid; refusing to package")
    return start, end


def _render_main_release_identity(data: bytes, version: str) -> bytes:
    plugin_version, register_version, plugin_node, register_node = (
        _main_release_identity_nodes(data)
    )
    if plugin_version != register_version:
        raise RuntimeError("main.py release identities disagree; refusing to package")

    replacement = repr(version).encode("utf-8")
    spans = sorted(
        (_ast_source_span(data, plugin_node), _ast_source_span(data, register_node)),
        reverse=True,
    )
    rendered = data
    previous_start = len(data)
    for (start, end) in spans:
        if end > previous_start:
            raise RuntimeError("main.py release identity spans overlap; refusing to package")
        rendered = rendered[:start] + replacement + rendered[end:]
        previous_start = start

    _validate_release_identity(version, rendered)
    return rendered


def _validate_release_identity(metadata_version: str, main_data: bytes) -> None:
    plugin_version, register_version = _read_main_release_identity(main_data)
    if metadata_version != plugin_version or metadata_version != register_version:
        raise RuntimeError(
            "release identity mismatch: "
            f"metadata.yaml={metadata_version!r}, "
            f"PLUGIN_VERSION={plugin_version!r}, "
            f"@register={register_version!r}; refusing to package"
        )


def _metadata_channel_for_version(version: str) -> str:
    return "grey" if "grey" in version.lower() else "stable"


def _validate_metadata_channel(version: str, channel: str) -> None:
    metadata_channel = _metadata_channel_for_version(version)
    if channel == "grey" and metadata_channel != "grey":
        raise RuntimeError(
            f"grey channel requires grey metadata, got version {version!r}; refusing to package"
        )
    if channel == "stable" and metadata_channel != "stable":
        raise RuntimeError(
            f"stable channel rejects grey metadata version {version!r}; "
            "supply a temporary stable metadata copy via --metadata"
        )


def _render_build_flags(channel: str) -> bytes:
    enabled = channel == "grey"
    return (
        '"""Generated build flags for the v3 shadow path. Do not edit by hand."""\n'
        "\n"
        f"V3_SHADOW_ENABLED: bool = {enabled}\n"
        f'BUILD_CHANNEL: str = "{channel}"\n'
    ).encode("utf-8")


def _verify_generated_flags(content: bytes, channel: str) -> None:
    """The generated flag must say exactly what the requested channel means."""
    values: dict[str, object] = {}
    for node in ast.parse(content.decode("utf-8")).body:
        if isinstance(node, ast.AnnAssign) and isinstance(node.target, ast.Name):
            if node.value is not None:
                values[node.target.id] = ast.literal_eval(node.value)
    expected = {"V3_SHADOW_ENABLED": channel == "grey", "BUILD_CHANNEL": channel}
    if values != expected:
        raise RuntimeError(
            f"generated build flags {values!r} disagree with channel {channel!r}; "
            "refusing to package"
        )


def _untracked_v3_sources(tracked: set[Path]) -> list[Path]:
    missing: list[Path] = []
    for relative in V3_SOURCE_DIRS:
        for path in sorted((ROOT / relative).rglob("*.py")):
            if "__pycache__" in path.parts:
                continue
            if path.resolve() not in tracked:
                missing.append(path)
    return missing


def _is_engine_source(name: str) -> bool:
    """The engine ships as source only; everything else under it is runtime state."""
    basename = name.rsplit("/", 1)[-1]
    return basename.endswith(".py") or basename in ENGINE_ALLOWED_NAMES


def _normalize_arcname(name: str) -> str:
    return unicodedata.normalize("NFC", name.replace("\\", "/"))


def _archive_entries(
    channel: str,
    metadata_override: Path | None = None,
    exclude_paths: set[Path] | None = None,
) -> list[tuple[str, bytes]]:
    """Build the full (arcname, uncompressed bytes) set for one channel."""
    flags_source = (ROOT / BUILD_FLAGS_RELPATH).resolve()
    main_source = (ROOT / MAIN_RELPATH).resolve()
    metadata_source = (ROOT / METADATA_RELPATH).resolve()
    replaced_sources = {flags_source}
    dirty_exempt_sources = {flags_source}
    if _checked_metadata_override(metadata_override) is not None:
        replaced_sources.update((main_source, metadata_source))
        # The checked-in metadata is irrelevant when a separate override is
        # packaged. main.py remains a tracked input: generated main.py is derived
        # from it, so a dirty main must still fail the HEAD-cleanliness gate.
        dirty_exempt_sources.add(metadata_source)

    files = collect_files(exclude_paths=exclude_paths)
    inputs = {path.resolve() for path in files} - dirty_exempt_sources

    dirty = _paths_differing_from_head() & inputs
    if dirty:
        listed = ", ".join(sorted(str(path.relative_to(ROOT)) for path in dirty))
        raise RuntimeError(
            f"tracked archive inputs differ from committed HEAD: {listed}; refusing to package"
        )

    entries: list[tuple[str, bytes]] = [(f"{PLUGIN_NAME}/", b"")]
    for path in files:
        if path.resolve() in replaced_sources:
            continue  # replaced below; never appended as a duplicate
        arcname = _normalize_arcname(Path(PLUGIN_NAME, path.relative_to(ROOT)).as_posix())
        entries.append((arcname, path.read_bytes()))

    flags = _render_build_flags(channel)
    _verify_generated_flags(flags, channel)
    entries.append((BUILD_FLAGS_ARCNAME, flags))
    if metadata_override is not None:
        override_version = _read_metadata_version(metadata_override.read_bytes())
        entries.append(
            (
                MAIN_ARCNAME,
                _render_main_release_identity((ROOT / MAIN_RELPATH).read_bytes(), override_version),
            )
        )
        entries.append((METADATA_ARCNAME, metadata_override.read_bytes()))

    return _sort_entries(entries)


def _sort_entries(entries: list[tuple[str, bytes]]) -> list[tuple[str, bytes]]:
    return sorted(entries, key=lambda entry: entry[0].encode("utf-8"))


def _validate_archive_entries(entries: list[tuple[str, bytes]]) -> None:
    seen: set[str] = set()
    folded: dict[str, str] = {}
    for name, _content in entries:
        if name in seen:
            raise RuntimeError(f"duplicate archive path {name!r}; refusing to package")
        seen.add(name)

        if "\\" not in name and unicodedata.is_normalized("NFC", name):
            pass
        else:
            raise RuntimeError(f"archive path {name!r} is not forward-slash NFC")

        key = name.casefold()
        if key in folded:
            raise RuntimeError(
                f"case-fold collision between {folded[key]!r} and {name!r}; refusing to package"
            )
        folded[key] = name

        if name.startswith(ENGINE_PREFIX) and not _is_engine_source(name):
            raise RuntimeError(
                f"_engine identity/runtime file {name!r} must never be packaged; refusing"
            )


def payload_digest(entries: list[tuple[str, bytes]]) -> str:
    """SHA-256 over UTF-8-path-sorted entries, excluding the manifest itself.

    Each entry is framed as unsigned big-endian
    ``u32(path_utf8_byte_len) || path_utf8_bytes || u64(content_len) || bytes``
    so that path and content boundaries can never be confused with each other.
    """
    digest = hashlib.sha256()
    for name, content in _sort_entries(list(entries)):
        if name == MANIFEST_ARCNAME:
            continue
        path_bytes = name.encode("utf-8")
        digest.update(struct.pack(">I", len(path_bytes)))
        digest.update(path_bytes)
        digest.update(struct.pack(">Q", len(content)))
        digest.update(content)
    return digest.hexdigest()


def _render_manifest(
    channel: str,
    version: str,
    commit: str,
    generated: dict[str, bytes],
    digest: str,
) -> bytes:
    manifest = {
        "schema": "sylanne_build_manifest_v1",
        "channel": channel,
        "metadata_version": version,
        "git_commit": commit,
        "generated_file_digest": hashlib.sha256(generated[BUILD_FLAGS_ARCNAME]).hexdigest(),
        "generated_files": {
            name: hashlib.sha256(content).hexdigest()
            for name, content in sorted(generated.items())
        },
        "payload_digest": digest,
    }
    text = json.dumps(manifest, ensure_ascii=False, indent=2, sort_keys=True)
    return f"{text}\n".encode("utf-8")


def _write_archive(output: Path, entries: list[tuple[str, bytes]]) -> None:
    with zipfile.ZipFile(
        output,
        "w",
        compression=zipfile.ZIP_DEFLATED,
        compresslevel=ZIP_COMPRESSLEVEL,
    ) as archive:
        for name, content in entries:
            info = zipfile.ZipInfo(filename=name, date_time=ZIP_TIMESTAMP)
            info.compress_type = zipfile.ZIP_DEFLATED
            info.create_system = ZIP_CREATE_SYSTEM
            info.external_attr = DIR_EXTERNAL_ATTR if name.endswith("/") else FILE_EXTERNAL_ATTR
            # compresslevel must be passed here: ZipFile's constructor default is
            # only consulted when writestr builds the ZipInfo itself, so handing
            # it a pre-built ZipInfo would silently fall back to the zlib default.
            archive.writestr(info, content, compresslevel=ZIP_COMPRESSLEVEL)


def build_package(
    output: Path,
    channel: str,
    metadata_override: Path | None = None,
) -> Path:
    if channel not in CHANNELS:
        raise ValueError(f"unknown channel {channel!r}; expected one of {list(CHANNELS)}")

    _checked_metadata_override(metadata_override)

    untracked = _untracked_v3_sources(_tracked_files())
    if untracked:
        listed = ", ".join(str(path.relative_to(ROOT)) for path in untracked)
        raise RuntimeError(f"untracked v3 source files: {listed}; refusing to package")

    checked_in_version = _read_metadata_version((ROOT / METADATA_RELPATH).read_bytes())
    _validate_release_identity(checked_in_version, (ROOT / MAIN_RELPATH).read_bytes())

    metadata_path = metadata_override or (ROOT / METADATA_RELPATH)
    version = _read_metadata_version(metadata_path.read_bytes())
    _validate_metadata_channel(version, channel)

    commit = _head_commit()
    output.parent.mkdir(parents=True, exist_ok=True)
    checksum_path = output.parent / f"{output.name}.sha256"

    entries = _archive_entries(
        channel,
        metadata_override=metadata_override,
        exclude_paths={output, checksum_path},
    )
    _validate_archive_entries(entries)

    entry_map = dict(entries)
    try:
        effective_metadata = _read_metadata_version(entry_map[METADATA_ARCNAME])
        effective_main = entry_map[MAIN_ARCNAME]
    except KeyError as exc:
        raise RuntimeError("release identity files missing from archive; refusing to package") from exc
    if effective_metadata != version:
        raise RuntimeError("effective archive metadata version drifted; refusing to package")
    _validate_release_identity(effective_metadata, effective_main)

    generated = {name: content for name, content in entries if name == BUILD_FLAGS_ARCNAME}
    if metadata_override is not None:
        generated.update(
            {
                name: content
                for name, content in entries
                if name in {MAIN_ARCNAME, METADATA_ARCNAME}
            }
        )
    if BUILD_FLAGS_ARCNAME not in generated:
        raise RuntimeError("generated build flags missing from archive; refusing to package")

    manifest = _render_manifest(channel, version, commit, generated, payload_digest(entries))
    _write_archive(output, _sort_entries([*entries, (MANIFEST_ARCNAME, manifest)]))

    # The whole-zip digest describes the closed file, so it can only live beside
    # it — never inside the archive it is supposed to authenticate.
    checksum_path.write_text(
        f"{hashlib.sha256(output.read_bytes()).hexdigest()}  {output.name}\n",
        encoding="utf-8",
    )
    return output


def main() -> None:
    parser = argparse.ArgumentParser(
        description="Build an AstrBot plugin zip without tests or local artifacts.",
    )
    parser.add_argument(
        "--channel",
        required=True,
        choices=list(CHANNELS),
        help="Artifact channel: grey enables the v3 shadow flag, stable disables it.",
    )
    parser.add_argument(
        "--metadata",
        type=Path,
        default=None,
        help="Alternative metadata.yaml to package (stable builds need a stable version).",
    )
    parser.add_argument(
        "--output",
        type=Path,
        default=ROOT / "dist" / f"{PLUGIN_NAME}.zip",
        help="Output zip path.",
    )
    args = parser.parse_args()
    output = build_package(args.output, channel=args.channel, metadata_override=args.metadata)
    print(output)


if __name__ == "__main__":
    main()
