"""Release identity, artifact-channel, and CI workflow contracts."""

from __future__ import annotations

import ast
import json
import shlex
import textwrap
import zipfile
from pathlib import Path

import pytest

from scripts import package_plugin


ROOT = Path(__file__).resolve().parents[1]
EXPECTED_GREY_VERSION = "2.5.0-grey.6"
EXPECTED_STABLE_VERSION = "2.5.0"
_RESOLVE_CHANNEL_COMMAND = (
    "CHANNEL=$(python -c \"from pathlib import Path; "
    "from scripts.package_plugin import _metadata_channel_for_version, "
    "_read_metadata_version; "
    "print(_metadata_channel_for_version(_read_metadata_version("
    "Path('metadata.yaml').read_bytes())))\")"
)


def _main_source(
    *,
    plugin_version: str = EXPECTED_GREY_VERSION,
    register_version: str = EXPECTED_GREY_VERSION,
    extra_module_source: str = "",
) -> bytes:
    return "\n".join(
        (
            f"PLUGIN_VERSION = {plugin_version!r}",
            extra_module_source,
            "",
            "@register(",
            '    "astrbot_plugin_sylanne",',
            '    "author",',
            '    "description",',
            f"    {register_version!r},",
            '    "https://example.invalid/plugin",',
            ")",
            "class Plugin:",
            "    pass",
            "",
        )
    ).encode("utf-8")


def _module_string_assignment(tree: ast.Module, name: str) -> str:
    values: list[str] = []
    writes = 0
    for node in tree.body:
        if not isinstance(node, ast.Assign):
            continue
        matching_targets = [
            target
            for target in node.targets
            if isinstance(target, ast.Name) and target.id == name
        ]
        writes += len(matching_targets)
        if not matching_targets:
            continue
        value = ast.literal_eval(node.value)
        if isinstance(value, str):
            values.append(value)
    assert writes == 1, f"expected exactly one assignment to {name}, got {writes}"
    assert len(values) == 1, f"expected one string assignment to {name}, got {values!r}"
    return values[0]


def _register_version(tree: ast.Module) -> str:
    versions: list[str] = []
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
            assert len(decorator.args) >= 4, "@register must declare its fourth argument"
            version = ast.literal_eval(decorator.args[3])
            assert isinstance(version, str), "@register version must be a string literal"
            versions.append(version)
    assert len(versions) == 1, f"expected exactly one @register version, got {versions!r}"
    return versions[0]


def _workflow_job_steps_from_text(text: str, job_name: str) -> list[dict[str, str]]:
    """Parse only the small, indentation-stable GitHub Actions steps subset we assert.

    This deliberately returns structured ``run`` scalars instead of searching raw
    YAML text, so comments and similarly named jobs cannot satisfy a contract.
    """

    lines = text.splitlines()
    start = lines.index(f"  {job_name}:")
    end = next(
        (
            index
            for index in range(start + 1, len(lines))
            if lines[index].startswith("  ") and not lines[index].startswith("    ")
        ),
        len(lines),
    )
    steps_start = lines.index("    steps:", start, end)
    steps: list[dict[str, str]] = []
    current: dict[str, str] | None = None
    index = steps_start + 1

    while index < end:
        line = lines[index]
        if line.startswith("      - "):
            if current is not None:
                steps.append(current)
            current = {}
            first = line[8:]
            key, separator, value = first.partition(":")
            if separator:
                current[key.strip()] = value.strip()
            index += 1
            continue

        if current is None or not line.startswith("        ") or line.startswith("          "):
            index += 1
            continue

        field = line[8:]
        key, separator, value = field.partition(":")
        if not separator:
            index += 1
            continue
        key = key.strip()
        value = value.strip()
        if key == "run" and value in {"|", "|-", ">", ">-"}:
            body: list[str] = []
            index += 1
            while index < end:
                body_line = lines[index]
                if not body_line.strip():
                    body.append("")
                    index += 1
                    continue
                if not body_line.startswith("          "):
                    break
                body.append(body_line[10:])
                index += 1
            current["run"] = "\n".join(body)
            continue
        current[key] = value
        index += 1

    if current is not None:
        steps.append(current)
    return steps


def _workflow_job_steps(workflow: Path, job_name: str) -> list[dict[str, str]]:
    return _workflow_job_steps_from_text(workflow.read_text(encoding="utf-8"), job_name)


def _run_command_lines(step: dict[str, str]) -> list[str]:
    return [
        line.strip()
        for line in step.get("run", "").splitlines()
        if line.strip() and not line.lstrip().startswith("#")
    ]


def _run_command_tokens(step: dict[str, str]) -> list[list[str]]:
    tokens: list[list[str]] = []
    for line in _run_command_lines(step):
        try:
            tokens.append(shlex.split(line, posix=True))
        except ValueError:
            continue
    return tokens


def _has_exact_requirements_install(steps: list[dict[str, str]], path: str) -> bool:
    expected = ["pip", "install", "-r", path]
    return any(expected in _run_command_tokens(step) for step in steps)


def _step_by_id(steps: list[dict[str, str]], step_id: str) -> dict[str, str]:
    matches = [step for step in steps if step.get("id") == step_id]
    assert len(matches) == 1, f"expected one step id={step_id!r}, got {len(matches)}"
    return matches[0]


def _step_by_name(steps: list[dict[str, str]], name: str) -> dict[str, str]:
    matches = [step for step in steps if step.get("name") == name]
    assert len(matches) == 1, f"expected one step name={name!r}, got {len(matches)}"
    return matches[0]


def test_checked_in_release_identity_is_grey_6_and_consistent() -> None:
    metadata_version = package_plugin._read_metadata_version((ROOT / "metadata.yaml").read_bytes())
    main_tree = ast.parse((ROOT / "main.py").read_text(encoding="utf-8"))

    assert metadata_version == EXPECTED_GREY_VERSION
    assert _module_string_assignment(main_tree, "PLUGIN_VERSION") == metadata_version
    assert _register_version(main_tree) == metadata_version


def test_release_identity_rejects_metadata_only_drift() -> None:
    with pytest.raises(RuntimeError, match="release identity mismatch"):
        package_plugin._validate_release_identity("2.5.0-grey.7", _main_source())


def test_release_identity_rejects_plugin_version_only_drift() -> None:
    with pytest.raises(RuntimeError, match="release identity mismatch"):
        package_plugin._validate_release_identity(
            EXPECTED_GREY_VERSION,
            _main_source(plugin_version="2.5.0-grey.7"),
        )


def test_release_identity_rejects_register_version_only_drift() -> None:
    with pytest.raises(RuntimeError, match="release identity mismatch"):
        package_plugin._validate_release_identity(
            EXPECTED_GREY_VERSION,
            _main_source(register_version="2.5.0-grey.7"),
        )


@pytest.mark.parametrize(
    "extra_module_source",
    (
        "PLUGIN_VERSION = 42",
        'PLUGIN_VERSION: str = "2.5.0-grey.7"',
        'if True:\n    PLUGIN_VERSION = "2.5.0-grey.7"',
    ),
    ids=("second-assign", "annassign", "control-flow-assign"),
)
def test_release_identity_rejects_any_second_module_scope_write(
    extra_module_source: str,
) -> None:
    with pytest.raises(RuntimeError, match="exactly one PLUGIN_VERSION"):
        package_plugin._validate_release_identity(
            EXPECTED_GREY_VERSION,
            _main_source(extra_module_source=extra_module_source),
        )


def test_stable_override_rewrites_all_packaged_release_identities(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    plugin_root = tmp_path / "plugin"
    plugin_root.mkdir()
    checked_in_metadata = plugin_root / "metadata.yaml"
    checked_in_metadata.write_text(f'version: "{EXPECTED_GREY_VERSION}"\n', encoding="utf-8")
    main = plugin_root / "main.py"
    main.write_bytes(_main_source())
    override = tmp_path / "stable-metadata.yaml"
    override.write_text(f'version: "{EXPECTED_STABLE_VERSION}"\n', encoding="utf-8")

    tracked = {checked_in_metadata.resolve(), main.resolve()}
    monkeypatch.setattr(package_plugin, "ROOT", plugin_root)
    monkeypatch.setattr(package_plugin, "_tracked_files", lambda: tracked)
    monkeypatch.setattr(package_plugin, "_paths_differing_from_head", lambda: set())
    monkeypatch.setattr(package_plugin, "_head_commit", lambda: "0" * 40)

    archive = package_plugin.build_package(
        tmp_path / "plugin.zip",
        channel="stable",
        metadata_override=override,
    )
    main_arcname = f"{package_plugin.PLUGIN_NAME}/main.py"
    with zipfile.ZipFile(archive) as zipped:
        metadata_version = package_plugin._read_metadata_version(
            zipped.read(package_plugin.METADATA_ARCNAME)
        )
        plugin_version, register_version = package_plugin._read_main_release_identity(
            zipped.read(main_arcname)
        )
        manifest = json.loads(zipped.read(package_plugin.MANIFEST_ARCNAME))

    assert metadata_version == EXPECTED_STABLE_VERSION
    assert plugin_version == metadata_version
    assert register_version == metadata_version
    assert main_arcname in manifest["generated_files"]


def test_workflow_run_parser_rejects_comments_echo_and_ignored_failures() -> None:
    workflow = textwrap.dedent(
        """\
        jobs:
          sample:
            steps:
              - name: Decoys
                run: |
                  # pip install -r requirements.txt
                  echo pip install -r requirements.txt
                  pip install -r requirements.txt || true
        """
    )
    steps = _workflow_job_steps_from_text(workflow, "sample")

    assert not _has_exact_requirements_install(steps, "requirements.txt")


@pytest.mark.parametrize("job_name", ("lint", "import-test", "test"))
def test_ci_python_matrix_jobs_install_runtime_requirements(job_name: str) -> None:
    requirements = (ROOT / "requirements.txt").read_text(encoding="utf-8")
    assert any(line.strip().lower().startswith("portalocker") for line in requirements.splitlines())

    steps = _workflow_job_steps(ROOT / ".github" / "workflows" / "ci.yml", job_name)
    assert _has_exact_requirements_install(steps, "requirements.txt"), (
        f"{job_name} matrix must run an unmasked requirements install"
    )


@pytest.mark.parametrize(
    ("workflow_name", "job_name", "requirements_path"),
    (
        ("ci.yml", "package", "$GITHUB_WORKSPACE/requirements.txt"),
        ("release.yml", "release", "requirements.txt"),
    ),
)
def test_artifact_import_smoke_jobs_install_runtime_requirements(
    workflow_name: str,
    job_name: str,
    requirements_path: str,
) -> None:
    steps = _workflow_job_steps(ROOT / ".github" / "workflows" / workflow_name, job_name)
    assert _has_exact_requirements_install(steps, requirements_path)


def test_ci_package_channel_is_derived_from_metadata() -> None:
    steps = _workflow_job_steps(ROOT / ".github" / "workflows" / "ci.yml", "package")
    resolver = _step_by_id(steps, "package-channel")
    assert _RESOLVE_CHANNEL_COMMAND in _run_command_lines(resolver)

    build = _step_by_name(steps, "Build plugin zip")
    assert [
        "python",
        "scripts/package_plugin.py",
        "--channel",
        "${{ steps.package-channel.outputs.channel }}",
        "--output",
        "dist/plugin.zip",
    ] in _run_command_tokens(build)


def test_auto_release_explicitly_skips_grey_and_keeps_stable_path() -> None:
    steps = _workflow_job_steps(ROOT / ".github" / "workflows" / "release.yml", "release")
    resolver = _step_by_id(steps, "release-channel")
    commands = _run_command_lines(resolver)
    assert _RESOLVE_CHANNEL_COMMAND in commands
    assert 'if [ "$CHANNEL" = "grey" ]; then' in commands
    assert 'echo "publish=false" >> "$GITHUB_OUTPUT"' in commands
    assert 'echo "publish=true" >> "$GITHUB_OUTPUT"' in commands

    check = _step_by_name(steps, "Check if release already exists")
    assert check.get("if") == "steps.release-channel.outputs.publish == 'true'"
    stable_only = "steps.release-channel.outputs.publish == 'true'"
    for name in (
        "Extract changelog for version",
        "Install deps",
        "Build plugin zip",
        "Verify zip contents",
        "Import smoke test from zip",
        "Create tag and release",
    ):
        assert stable_only in _step_by_name(steps, name).get("if", ""), name
