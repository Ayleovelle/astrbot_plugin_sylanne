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
        self.assertIn("README.md", files)
        self.assertIn("docs/theory.md", files)
        self.assertIn("literature_kb/manifest.json", files)
        self.assertIn("literature_kb/works.jsonl", files)
        self.assertIn("psychological_literature_kb/curated/top_200.jsonl", files)
        self.assertIn("humanlike_agent_literature_kb/curated/top_200.jsonl", files)
        self.assertNotIn("scripts/package_plugin.py", files)
        self.assertNotIn("task_plan.md", files)
        self.assertNotIn("progress.md", files)
        self.assertNotIn("findings.md", files)
        self.assertNotIn(".gitignore", files)
        self.assertFalse(any(path.startswith("tests/") for path in files))
        self.assertFalse(any(path.startswith("output/") for path in files))
        self.assertFalse(any("/raw/" in path or path.startswith("raw/") for path in files))
        self.assertFalse(any("__pycache__" in path for path in files))

    def test_package_plugin_name_matches_metadata(self):
        module = load_package_script()

        self.assertEqual(PLUGIN_NAME, metadata_value("name"))
        self.assertEqual(module.PLUGIN_NAME, metadata_value("name"))

    def test_package_zip_has_astrbot_plugin_root(self):
        names, _ = self._zip_names()

        prefix = f"{metadata_value('name')}/"
        self.assertIn(prefix + "metadata.yaml", names)
        self.assertIn(prefix + "main.py", names)
        self.assertIn(prefix + "_conf_schema.json", names)
        self.assertIn(prefix + "README.md", names)
        self.assertIn(prefix + "literature_kb/works.jsonl", names)
        self.assertIn(prefix + "psychological_literature_kb/curated/top_200.jsonl", names)
        self.assertIn(prefix + "humanlike_agent_literature_kb/curated/top_200.jsonl", names)
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

    def _valid_entries(self) -> list[tuple[str, str]]:
        prefix = f"{PLUGIN_NAME}/"
        return [
            (prefix, ""),
            (prefix + "metadata.yaml", f"name: {PLUGIN_NAME}\n"),
            (prefix + "main.py", "# runtime\n"),
            (prefix + "README.md", "# docs\n"),
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
            ]
            self._write_zip(output, entries)

            result = self._preflight(output)

        self.assertNotEqual(result.returncode, 0)
        self.assertIn("excluded path segment", result.stderr)

    def test_zip_preflight_rejects_missing_required_runtime_file(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            output = Path(temp_dir) / f"{PLUGIN_NAME}.zip"
            entries = [
                entry for entry in self._valid_entries()
                if not entry[0].endswith("_conf_schema.json")
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
