import importlib.util
import os
import subprocess
import tempfile
import unittest
import zipfile
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]


def metadata_value(name: str) -> str:
    for line in (ROOT / "metadata.yaml").read_text(encoding="utf-8").splitlines():
        if line.startswith(f"{name}:"):
            return line.split(":", 1)[1].strip().strip('"')
    raise AssertionError(f"metadata.yaml missing {name}")


PLUGIN_NAME = metadata_value("name")
PLUGIN_LICENSE = "GPL-3.0-or-later"


def load_package_script():
    path = ROOT / "scripts" / "package_plugin.py"
    spec = importlib.util.spec_from_file_location("package_plugin", path)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


class PackagePluginTests(unittest.TestCase):
    def _zip_names(self):
        module = load_package_script()
        with tempfile.TemporaryDirectory() as temp_dir:
            output = Path(temp_dir) / "plugin.zip"
            module.build_package(output)
            with zipfile.ZipFile(output) as archive:
                names = set(archive.namelist())
            return names, output.stat().st_size

    def test_package_file_selection_excludes_local_artifacts(self):
        module = load_package_script()
        files = {path.relative_to(ROOT).as_posix() for path in module.collect_files()}

        self.assertIn("metadata.yaml", files)
        self.assertIn("main.py", files)
        self.assertIn("integrated_self.py", files)
        self.assertIn("lifelike_learning_engine.py", files)
        self.assertIn("personality_drift_engine.py", files)
        self.assertIn("moral_repair_engine.py", files)
        self.assertIn("fallibility_engine.py", files)
        self.assertIn("agent_identity.py", files)
        self.assertIn("group_atmosphere_engine.py", files)
        self.assertIn("LICENSE", files)
        self.assertIn("README.md", files)
        self.assertIn("docs/theory.md", files)
        self.assertIn("docs/remote_testing.md", files)
        self.assertNotIn("docs/literature_kb.md", files)
        self.assertNotIn("docs/humanlike_agent_literature_kb.md", files)
        self.assertNotIn("scripts/package_plugin.py", files)
        self.assertNotIn("task_plan.md", files)
        self.assertNotIn("progress.md", files)
        self.assertNotIn("findings.md", files)
        self.assertNotIn(".gitignore", files)
        self.assertFalse(any(path.startswith("literature_kb/") for path in files))
        self.assertFalse(any(path.startswith("personality_literature_kb/") for path in files))
        self.assertFalse(any(path.startswith("psychological_literature_kb/") for path in files))
        self.assertFalse(any(path.startswith("humanlike_agent_literature_kb/") for path in files))
        self.assertFalse(any(path.startswith("tests/") for path in files))
        self.assertFalse(any(path.startswith("output/") for path in files))
        self.assertFalse(any("/raw/" in path or path.startswith("raw/") for path in files))
        self.assertFalse(any("__pycache__" in path for path in files))

    def test_readme_install_tree_matches_release_package_boundaries(self):
        readme = (ROOT / "README.md").read_text(encoding="utf-8")
        install_tree = readme.split("```text", 1)[1].split("```", 1)[0]

        self.assertIn("astrbot_plugin_emotional_state/", install_tree)
        self.assertIn("__init__.py", install_tree)
        self.assertIn("agent_identity.py", install_tree)
        self.assertIn("group_atmosphere_engine.py", install_tree)
        self.assertIn("public_api.py", install_tree)
        self.assertNotIn("tests/", install_tree)
        self.assertIn("发布 zip 不会包含这些目录", readme)

    def test_package_plugin_name_matches_metadata(self):
        module = load_package_script()

        self.assertEqual(PLUGIN_NAME, metadata_value("name"))
        self.assertEqual(module.PLUGIN_NAME, metadata_value("name"))

    def test_license_contract_is_gpl_and_documented(self):
        readme = (ROOT / "README.md").read_text(encoding="utf-8")
        license_text = (ROOT / "LICENSE").read_text(encoding="ascii")

        self.assertEqual(PLUGIN_LICENSE, metadata_value("license"))
        self.assertIn(PLUGIN_LICENSE, readme)
        self.assertIn("GNU GENERAL PUBLIC LICENSE", license_text)
        self.assertIn("Version 3", license_text)

    def test_package_zip_has_astrbot_plugin_root(self):
        names, _ = self._zip_names()

        prefix = f"{metadata_value('name')}/"
        runtime_root_files = {
            "__init__.py",
            "agent_identity.py",
            "main.py",
            "emotion_engine.py",
            "group_atmosphere_engine.py",
            "humanlike_engine.py",
            "lifelike_learning_engine.py",
            "personality_drift_engine.py",
            "integrated_self.py",
            "moral_repair_engine.py",
            "fallibility_engine.py",
            "psychological_screening.py",
            "prompts.py",
            "public_api.py",
        }
        for filename in runtime_root_files:
            with self.subTest(filename=filename):
                self.assertIn(prefix + filename, names)
        self.assertIn(prefix + "metadata.yaml", names)
        self.assertIn(prefix + "_conf_schema.json", names)
        self.assertIn(prefix + "README.md", names)
        self.assertIn(prefix + "LICENSE", names)
        self.assertIn(prefix + "docs/remote_testing.md", names)
        self.assertNotIn(prefix + "docs/literature_kb.md", names)
        self.assertNotIn(prefix + "docs/humanlike_agent_literature_kb.md", names)
        self.assertFalse(any(name.startswith(prefix + "literature_kb/") for name in names))
        self.assertFalse(any(name.startswith(prefix + "personality_literature_kb/") for name in names))
        self.assertFalse(any(name.startswith(prefix + "psychological_literature_kb/") for name in names))
        self.assertFalse(any(name.startswith(prefix + "humanlike_agent_literature_kb/") for name in names))
        self.assertFalse(any(name.startswith(prefix + "tests/") for name in names))
        self.assertFalse(any(name.startswith(prefix + "scripts/") for name in names))
        self.assertFalse(any(name.startswith(prefix + "output/") for name in names))
        self.assertFalse(any("/raw/" in name for name in names))
        self.assertTrue(all(name.startswith(prefix) for name in names))
        self.assertTrue(all("\\" not in name for name in names))
        self.assertTrue(all(not Path(name).is_absolute() for name in names))

    def test_package_zip_starts_with_explicit_plugin_directory_entry(self):
        module = load_package_script()
        with tempfile.TemporaryDirectory() as temp_dir:
            output = Path(temp_dir) / "plugin.zip"
            module.build_package(output)
            with zipfile.ZipFile(output) as archive:
                first = archive.infolist()[0]

        self.assertEqual(first.filename, f"{metadata_value('name')}/")
        self.assertTrue(first.is_dir())

    def test_package_zip_stays_small_enough_for_remote_upload(self):
        _, size = self._zip_names()
        self.assertLess(size, 40 * 1024 * 1024)

    def test_package_excludes_output_zip_even_inside_included_directory(self):
        module = load_package_script()
        output = ROOT / "docs" / f"{PLUGIN_NAME}.zip"
        try:
            module.build_package(output)
            with zipfile.ZipFile(output) as archive:
                names = set(archive.namelist())
        finally:
            output.unlink(missing_ok=True)

        self.assertNotIn(f"{PLUGIN_NAME}/docs/{PLUGIN_NAME}.zip", names)


class PluginZipPreflightTests(unittest.TestCase):
    def _node(self) -> str:
        bundled = (
            Path.home()
            / ".cache"
            / "codex-runtimes"
            / "codex-primary-runtime"
            / "dependencies"
            / "node"
            / "bin"
            / ("node.exe" if os.name == "nt" else "node")
        )
        return str(bundled if bundled.exists() else "node")

    def _write_zip(self, zip_path: Path, entries: list[tuple[str, str]]) -> None:
        with zipfile.ZipFile(zip_path, "w", compression=zipfile.ZIP_DEFLATED) as archive:
            for name, content in entries:
                archive.writestr(name, content)

    def _preflight(self, zip_path: Path) -> subprocess.CompletedProcess[str]:
        return subprocess.run(
            [
                self._node(),
                str(ROOT / "scripts" / "plugin_zip_preflight.js"),
                str(zip_path),
                PLUGIN_NAME,
            ],
            cwd=ROOT,
            text=True,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            check=False,
        )

    def _preflight_with_env_plugin(self, zip_path: Path) -> subprocess.CompletedProcess[str]:
        env = os.environ.copy()
        env["ASTRBOT_EXPECT_PLUGIN"] = PLUGIN_NAME
        return subprocess.run(
            [
                self._node(),
                str(ROOT / "scripts" / "plugin_zip_preflight.js"),
                str(zip_path),
            ],
            cwd=ROOT,
            env=env,
            text=True,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            check=False,
        )

    def _valid_entries(self) -> list[tuple[str, str]]:
        prefix = f"{PLUGIN_NAME}/"
        return [
            (prefix, ""),
            (prefix + "__init__.py", '"""plugin package"""\n'),
            (prefix + "metadata.yaml", f"name: {PLUGIN_NAME}\n"),
            (prefix + "agent_identity.py", "# runtime\n"),
            (prefix + "main.py", "# runtime\n"),
            (prefix + "emotion_engine.py", "# runtime\n"),
            (prefix + "group_atmosphere_engine.py", "# runtime\n"),
            (prefix + "humanlike_engine.py", "# runtime\n"),
            (prefix + "lifelike_learning_engine.py", "# runtime\n"),
            (prefix + "personality_drift_engine.py", "# runtime\n"),
            (prefix + "integrated_self.py", "# runtime\n"),
            (prefix + "moral_repair_engine.py", "# runtime\n"),
            (prefix + "fallibility_engine.py", "# runtime\n"),
            (prefix + "psychological_screening.py", "# runtime\n"),
            (prefix + "prompts.py", "# runtime\n"),
            (prefix + "public_api.py", "# public API\n"),
            (prefix + "README.md", "# docs\n"),
            (prefix + "LICENSE", "GNU GENERAL PUBLIC LICENSE\n"),
            (prefix + "requirements.txt", "# no dependencies\n"),
            (prefix + "_conf_schema.json", "{}\n"),
        ]

    def test_zip_preflight_accepts_packaged_plugin_zip(self):
        module = load_package_script()
        with tempfile.TemporaryDirectory() as temp_dir:
            output = Path(temp_dir) / f"{PLUGIN_NAME}.zip"
            module.build_package(output)

            result = self._preflight(output)

        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertIn('"ok":true', result.stdout.replace(" ", ""))

    def test_zip_preflight_rejects_missing_explicit_root_entry(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            output = Path(temp_dir) / f"{PLUGIN_NAME}.zip"
            self._write_zip(output, self._valid_entries()[1:])

            result = self._preflight(output)

        self.assertNotEqual(result.returncode, 0)
        self.assertIn("explicit plugin directory entry", result.stderr)

    def test_zip_preflight_rejects_excluded_segments(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            output = Path(temp_dir) / f"{PLUGIN_NAME}.zip"
            entries = self._valid_entries() + [
                (f"{PLUGIN_NAME}/raw/cache.jsonl", "{}\n"),
                (f"{PLUGIN_NAME}/tests/test_plugin.py", "\n"),
                (f"{PLUGIN_NAME}/literature_kb/works.jsonl", "{}\n"),
                (f"{PLUGIN_NAME}/personality_literature_kb/works.jsonl", "{}\n"),
                (f"{PLUGIN_NAME}/psychological_literature_kb/works.jsonl", "{}\n"),
                (f"{PLUGIN_NAME}/humanlike_agent_literature_kb/works.jsonl", "{}\n"),
            ]
            self._write_zip(output, entries)

            result = self._preflight(output)

        self.assertNotEqual(result.returncode, 0)
        self.assertIn("excluded path segment", result.stderr)

    def test_zip_preflight_rejects_missing_required_runtime_file(self):
        required_suffixes = (
            "__init__.py",
            "_conf_schema.json",
            "agent_identity.py",
            "group_atmosphere_engine.py",
            "integrated_self.py",
            "lifelike_learning_engine.py",
            "personality_drift_engine.py",
            "LICENSE",
            "moral_repair_engine.py",
            "fallibility_engine.py",
            "public_api.py",
            "requirements.txt",
        )
        for suffix in required_suffixes:
            with self.subTest(suffix=suffix):
                with tempfile.TemporaryDirectory() as temp_dir:
                    output = Path(temp_dir) / f"{PLUGIN_NAME}.zip"
                    entries = [
                        entry for entry in self._valid_entries()
                        if not entry[0].endswith(suffix)
                    ]
                    self._write_zip(output, entries)

                    result = self._preflight(output)

                    self.assertNotEqual(result.returncode, 0)
                    self.assertIn("missing required plugin entry", result.stderr)

    def test_zip_preflight_rejects_parent_traversal(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            output = Path(temp_dir) / f"{PLUGIN_NAME}.zip"
            entries = self._valid_entries() + [
                (f"{PLUGIN_NAME}/docs/../escape.txt", "bad\n"),
            ]
            self._write_zip(output, entries)

            result = self._preflight(output)

        self.assertNotEqual(result.returncode, 0)
        self.assertIn("parent traversal", result.stderr)

    def test_zip_preflight_rejects_unsafe_dot_path_segments(self):
        for unsafe_name in (
            f"{PLUGIN_NAME}/docs/./notes.md",
            f"{PLUGIN_NAME}/docs/../escape.txt",
        ):
            with self.subTest(unsafe_name=unsafe_name):
                with tempfile.TemporaryDirectory() as temp_dir:
                    output = Path(temp_dir) / f"{PLUGIN_NAME}.zip"
                    entries = self._valid_entries() + [(unsafe_name, "bad\n")]
                    self._write_zip(output, entries)

                    result = self._preflight(output)

                self.assertNotEqual(result.returncode, 0)
                self.assertTrue(
                    "unsafe path segment" in result.stderr
                    or "parent traversal" in result.stderr,
                )

    def test_zip_preflight_uses_expected_plugin_environment_fallback(self):
        module = load_package_script()
        with tempfile.TemporaryDirectory() as temp_dir:
            output = Path(temp_dir) / f"{PLUGIN_NAME}.zip"
            module.build_package(output)

            result = self._preflight_with_env_plugin(output)

        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertIn('"ok":true', result.stdout.replace(" ", ""))

    def test_zip_preflight_rejects_metadata_name_mismatch(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            output = Path(temp_dir) / f"{PLUGIN_NAME}.zip"
            entries = [
                (name, "name: wrong_plugin\n" if name.endswith("metadata.yaml") else content)
                for name, content in self._valid_entries()
            ]
            self._write_zip(output, entries)

            result = self._preflight(output)

        self.assertNotEqual(result.returncode, 0)
        self.assertIn("metadata.yaml name must be", result.stderr)

    def test_zip_preflight_rejects_metadata_without_name(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            output = Path(temp_dir) / f"{PLUGIN_NAME}.zip"
            entries = [
                (name, "display_name: Broken\n" if name.endswith("metadata.yaml") else content)
                for name, content in self._valid_entries()
            ]
            self._write_zip(output, entries)

            result = self._preflight(output)

        self.assertNotEqual(result.returncode, 0)
        self.assertIn("metadata.yaml name must be", result.stderr)


if __name__ == "__main__":
    unittest.main()
