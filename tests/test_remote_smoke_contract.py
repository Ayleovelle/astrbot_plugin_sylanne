import unittest
import ast
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
NODE_FALLBACK_SNIPPET = [
    '$node = "$HOME\\.cache\\codex-runtimes\\codex-primary-runtime\\dependencies\\node\\bin\\node.exe"',
    '$nodeModules = "$HOME\\.cache\\codex-runtimes\\codex-primary-runtime\\dependencies\\node\\node_modules"',
    'if (Test-Path $node) { $env:NODE_PATH = $nodeModules } else { $node = "node" }',
]


class RemoteSmokeContractTests(unittest.TestCase):
    def _node_fallback_lines(self, text):
        return [
            line
            for line in text.splitlines()
            if (
                line.startswith("$node = ")
                or line.startswith("$nodeModules = ")
                or line.startswith("if (Test-Path $node)")
            )
        ]

    def test_readme_documents_remote_smoke_without_real_credentials(self):
        readme = (ROOT / "README.md").read_text(encoding="utf-8")

        self.assertIn("scripts\\remote_smoke_playwright.js", readme)
        self.assertIn("scripts\\plugin_zip_preflight.js", readme)
        self.assertIn("codex-primary-runtime", readme)
        self.assertIn("$env:NODE_PATH", readme)
        self.assertIn("& $node scripts\\remote_smoke_playwright.js", readme)
        self.assertIn("& $node scripts\\plugin_zip_preflight.js", readme)
        self.assertIn("ASTRBOT_REMOTE_URL", readme)
        self.assertIn("ASTRBOT_REMOTE_USERNAME", readme)
        self.assertIn("ASTRBOT_REMOTE_PASSWORD", readme)
        self.assertIn("ASTRBOT_EXPECT_PLUGIN", readme)
        self.assertIn("ASTRBOT_EXPECT_PLUGIN_VERSION", readme)
        self.assertIn("ASTRBOT_EXPECT_PLUGIN_DISPLAY_NAME", readme)
        self.assertIn("expectedPluginRuntime", readme)
        self.assertIn("apiHealth", readme)
        self.assertIn("uiProbeStatus", readme)
        self.assertIn("selectorCounts", readme)
        self.assertIn("best-effort", readme)
        self.assertIn("/api/plugin/source/get-failed-plugins", readme)
        self.assertIn("退出码 `9`", readme)
        self.assertIn("远程安装插件后", readme)
        self.assertIn("scripts\\package_plugin.py", readme)
        self.assertIn("raw/", readme)
        self.assertIn("task_plan.md", readme)
        self.assertIn("findings.md", readme)
        self.assertIn("progress.md", readme)
        self.assertIn("API 健康摘要", readme)
        self.assertIn("UI best-effort 字段", readme)
        self.assertIn("bundled Node 文档契约", readme)
        self.assertNotIn("154.36.178.25", readme)
        self.assertNotIn("12341234", readme)
        self.assertNotIn("\nnode --check scripts\\remote_smoke_playwright.js", readme)
        self.assertNotIn("\nnode scripts\\remote_smoke_playwright.js", readme)

    def test_release_checklist_uses_bundled_node_fallback(self):
        checklist = (ROOT / "docs" / "release_branch_sync_checklist.md").read_text(
            encoding="utf-8",
        )

        self.assertIn("codex-primary-runtime", checklist)
        self.assertIn("$env:NODE_PATH", checklist)
        self.assertIn("& $node --check scripts\\remote_smoke_playwright.js", checklist)
        self.assertIn(
            "& $node --check scripts\\remote_install_upload_playwright.js",
            checklist,
        )
        self.assertIn("& $node --check scripts\\plugin_zip_preflight.js", checklist)
        self.assertIn("& $node scripts\\remote_smoke_playwright.js", checklist)
        self.assertNotIn("\nnode --check scripts\\remote_smoke_playwright.js", checklist)
        self.assertNotIn("\nnode scripts\\remote_smoke_playwright.js", checklist)

    def test_node_fallback_is_consistent_and_before_commands(self):
        readme = (ROOT / "README.md").read_text(encoding="utf-8")
        checklist = (ROOT / "docs" / "release_branch_sync_checklist.md").read_text(
            encoding="utf-8",
        )
        fallback = self._node_fallback_lines(readme)

        self.assertEqual(NODE_FALLBACK_SNIPPET, fallback)
        self.assertEqual(fallback, self._node_fallback_lines(checklist))
        self.assertLess(readme.index("codex-primary-runtime"), readme.index("& $node scripts\\remote_smoke_playwright.js"))
        self.assertLess(checklist.index("codex-primary-runtime"), checklist.index("& $node --check scripts\\remote_smoke_playwright.js"))

    def test_remote_smoke_script_uses_environment_credentials(self):
        script = (ROOT / "scripts" / "remote_smoke_playwright.js").read_text(
            encoding="utf-8",
        )

        self.assertIn("ASTRBOT_REMOTE_USERNAME", script)
        self.assertIn("ASTRBOT_REMOTE_PASSWORD", script)
        self.assertIn("ASTRBOT_REMOTE_URL", script)
        self.assertIn("ASTRBOT_REMOTE_ARTIFACT_DIR", script)
        self.assertIn("apiHealth", script)
        self.assertIn("statVersion", script)
        self.assertIn("pluginGet", script)
        self.assertIn("expectedFailedPlugin", script)
        self.assertIn("expectedPluginRuntime", script)
        self.assertIn("hasExpectedPlugin: hasExpectedPluginInUi", script)
        self.assertIn("hasExpectedPluginDisplayName", script)
        self.assertIn("hasExpectedPluginInUi", script)
        self.assertIn("titleHasExpectedPlugin", script)
        self.assertIn("waitForExtensionUi", script)
        self.assertIn("uiProbeStatus", script)
        self.assertIn("best_effort_timeout", script)
        self.assertIn("selectorCounts", script)
        self.assertIn("bodyTextPreview", script)
        self.assertIn("ASTRBOT_EXPECT_PLUGIN_VERSION", script)
        self.assertIn("ASTRBOT_EXPECT_PLUGIN_DISPLAY_NAME", script)
        self.assertIn("process.exitCode = 5", script)
        self.assertIn("process.exitCode = 6", script)
        self.assertIn("process.exitCode = 7", script)
        self.assertIn("process.exitCode = 8", script)
        self.assertIn("process.exitCode = 9", script)
        self.assertIn("failedPlugins.status !== 200", script)
        self.assertIn("activated === false", script)
        self.assertNotIn("12341234", script)
        self.assertNotIn("154.36.178.25", script)
        self.assertNotIn("username = \"root\"", script)
        self.assertNotIn("password = \"", script)

    def test_remote_install_script_requires_explicit_confirmation(self):
        script = (
            ROOT / "scripts" / "remote_install_upload_playwright.js"
        ).read_text(encoding="utf-8")
        preflight = (
            ROOT / "scripts" / "plugin_zip_preflight.js"
        ).read_text(encoding="utf-8")

        self.assertIn("ASTRBOT_REMOTE_INSTALL_CONFIRM", script)
        self.assertIn("ASTRBOT_REMOTE_INSTALL_ZIP", script)
        self.assertIn("ASTRBOT_EXPECT_PLUGIN", script)
        self.assertIn("/api/plugin/install-upload", script)
        self.assertIn("assertZipLooksUploadable", script)
        self.assertIn("readUInt32LE(0)", preflight)
        self.assertIn("readUInt16LE(26)", preflight)
        self.assertIn("readCentralDirectoryNames", preflight)
        self.assertIn("0x02014b50", preflight)
        self.assertIn("metadata.yaml", preflight)
        self.assertIn("main.py", preflight)
        self.assertIn("_conf_schema.json", preflight)
        self.assertIn("\"tests\"", preflight)
        self.assertIn("\"scripts\"", preflight)
        self.assertIn("\"output\"", preflight)
        self.assertIn("\"raw\"", preflight)
        self.assertIn("Zip entry must be under", preflight)
        self.assertIn("Zip entry must not contain parent traversal", preflight)
        self.assertIn("alreadyInstalled", script)
        self.assertIn("目录 ${expectedPlugin} 已存在", script)
        self.assertIn("cleanupAlreadyInstalledFailure", script)
        self.assertIn("/api/plugin/uninstall-failed", script)
        self.assertIn("ASTRBOT_REMOTE_USERNAME", script)
        self.assertIn("ASTRBOT_REMOTE_PASSWORD", script)
        self.assertNotIn("12341234", script)
        self.assertNotIn("154.36.178.25", script)
        self.assertNotIn("username = \"root\"", script)
        self.assertNotIn("password = \"", script)

    def test_remote_install_script_only_allows_upload_install_mutation(self):
        script = (
            ROOT / "scripts" / "remote_install_upload_playwright.js"
        ).read_text(encoding="utf-8")
        lowered = script.lower()
        forbidden_fragments = (
            "/api/plugin/delete",
            "/api/plugin/reload",
            "/api/plugin/update",
            "/api/plugin/update-all",
            "/api/config/update",
            "/api/config/save",
            "/api/system/restart",
            "restartastrbot",
            "method: \"delete\"",
            "method:'delete'",
        )

        self.assertIn("/api/plugin/install-upload", lowered)
        self.assertIn("/api/plugin/uninstall-failed", lowered)
        self.assertIn("method: \"post\"", lowered)
        for fragment in forbidden_fragments:
            with self.subTest(fragment=fragment):
                self.assertNotIn(fragment, lowered)

    def test_remote_install_script_does_not_persist_credentials_or_sessions(self):
        script = (
            ROOT / "scripts" / "remote_install_upload_playwright.js"
        ).read_text(encoding="utf-8")
        lowered = script.lower()

        self.assertNotIn("dotenv", lowered)
        self.assertNotIn("readfile", lowered.replace("readfilesync(zippath)", ""))
        self.assertNotIn("storagestate", lowered)
        self.assertNotIn("cookie", lowered)
        self.assertNotIn("localstorage", lowered)
        self.assertNotIn("sessionstorage", lowered)

    def test_remote_smoke_script_is_read_only(self):
        script = (ROOT / "scripts" / "remote_smoke_playwright.js").read_text(
            encoding="utf-8",
        )
        lowered = script.lower()
        forbidden_fragments = (
            "/api/plugin/install",
            "/api/plugin/delete",
            "/api/plugin/reload",
            "/api/plugin/update",
            "/api/config/update",
            "/api/config/save",
            "/api/system/restart",
            "restartastrbot",
            "method: \"post\"",
            "method:'post'",
            "method: \"delete\"",
            "method:'delete'",
        )

        for fragment in forbidden_fragments:
            with self.subTest(fragment=fragment):
                self.assertNotIn(fragment, lowered)

    def test_remote_smoke_artifacts_are_gitignored(self):
        gitignore = (ROOT / ".gitignore").read_text(encoding="utf-8")
        self.assertIn("output/", gitignore)

    def test_readme_public_api_tables_match_protocol_methods(self):
        readme = (ROOT / "README.md").read_text(encoding="utf-8")
        tree = ast.parse((ROOT / "public_api.py").read_text(encoding="utf-8"))
        protocol_methods = set()
        for node in ast.walk(tree):
            if not isinstance(node, ast.ClassDef):
                continue
            if node.name not in {
                "EmotionServiceProtocol",
                "HumanlikeStateServiceProtocol",
            }:
                continue
            for item in node.body:
                if isinstance(item, ast.AsyncFunctionDef):
                    protocol_methods.add(item.name)

        for method in sorted(protocol_methods):
            with self.subTest(method=method):
                self.assertIn(f"`{method}", readme)

        self.assertIn("get_emotion_service", readme)
        self.assertIn("get_humanlike_service", readme)
        self.assertIn("校验核心方法是否完整", readme)


if __name__ == "__main__":
    unittest.main()
