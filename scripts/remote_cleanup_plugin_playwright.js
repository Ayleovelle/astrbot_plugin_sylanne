const fs = require("fs");
const path = require("path");
const { chromium } = require("playwright");

const ALLOWED_PLUGIN = "astrbot_plugin_emotional_state";

function env(name, fallback = "") {
  const value = process.env[name];
  return value == null || value === "" ? fallback : value;
}

function resolveBrowserExecutable() {
  const explicit = env("PLAYWRIGHT_BROWSER_EXECUTABLE");
  if (explicit) {
    return explicit;
  }
  const candidates = [
    "C:\\Program Files (x86)\\Microsoft\\Edge\\Application\\msedge.exe",
    "C:\\Program Files\\Microsoft\\Edge\\Application\\msedge.exe",
    "C:\\Program Files\\Google\\Chrome\\Application\\chrome.exe",
    "C:\\Program Files (x86)\\Google\\Chrome\\Application\\chrome.exe",
  ];
  return candidates.find((candidate) => fs.existsSync(candidate)) || "";
}

function requireEnv(name) {
  const value = env(name);
  if (!value) {
    throw new Error(`Set ${name} before running remote plugin cleanup.`);
  }
  return value;
}

function pluginIdentityFields(plugin) {
  const metadata = plugin && typeof plugin.metadata === "object"
    ? plugin.metadata
    : {};
  return [
    plugin && plugin.name,
    plugin && plugin.plugin_name,
    plugin && plugin.repo,
    metadata && metadata.name,
    plugin && plugin.id,
    plugin && plugin.dir_name,
    plugin && plugin.folder_name,
  ].filter(Boolean);
}

function pluginMatchesExactly(plugin, expectedPlugin) {
  return pluginIdentityFields(plugin).some((value) => value === expectedPlugin);
}

function extractPlugins(payload) {
  const json = payload && payload.json;
  const raw = json && (json.data || json.plugins || json);
  return Array.isArray(raw)
    ? raw
    : raw && Array.isArray(raw.plugins)
      ? raw.plugins
      : [];
}

function failedEntries(payload) {
  const data = payload && payload.json && payload.json.data;
  return data && typeof data === "object" ? Object.entries(data) : [];
}

async function getJson(page, url) {
  return await page.evaluate(async (targetUrl) => {
    const response = await fetch(targetUrl, { credentials: "include" });
    const text = await response.text();
    let json = null;
    try {
      json = JSON.parse(text);
    } catch {
      json = null;
    }
    return {
      status: response.status,
      text: text.slice(0, 2000),
      json,
    };
  }, url);
}

async function uninstallFormalPlugin(page, expectedPlugin) {
  return await page.evaluate(async ({ pluginName }) => {
    const response = await fetch("/api/plugin/uninstall", {
      method: "POST",
      credentials: "include",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({
        name: pluginName,
        delete_config: false,
        delete_data: false,
      }),
    });
    const text = await response.text();
    let json = null;
    try {
      json = JSON.parse(text);
    } catch {
      json = null;
    }
    return {
      status: response.status,
      text: text.slice(0, 2000),
      json,
    };
  }, { pluginName: expectedPlugin });
}

async function uninstallFailedUpload(page, expectedPlugin) {
  return await page.evaluate(async ({ failedDir }) => {
    const response = await fetch("/api/plugin/uninstall-failed", {
      method: "POST",
      credentials: "include",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({
        dir_name: failedDir,
        delete_config: false,
        delete_data: false,
      }),
    });
    const text = await response.text();
    let json = null;
    try {
      json = JSON.parse(text);
    } catch {
      json = null;
    }
    return {
      status: response.status,
      text: text.slice(0, 2000),
      json,
    };
  }, { failedDir: `plugin_upload_${expectedPlugin}` });
}

async function main() {
  const remoteUrl = requireEnv("ASTRBOT_REMOTE_URL");
  const username = requireEnv("ASTRBOT_REMOTE_USERNAME");
  const password = requireEnv("ASTRBOT_REMOTE_PASSWORD");
  const expectedPlugin = requireEnv("ASTRBOT_EXPECT_PLUGIN");
  const confirm = env("ASTRBOT_REMOTE_CLEAN_CONFIRM");
  const cleanFormal = env("ASTRBOT_REMOTE_CLEAN_FORMAL") === "1";
  const cleanFailedUpload = env("ASTRBOT_REMOTE_CLEAN_FAILED_UPLOAD", "1") !== "0";
  const allowMultipleFormal = env("ASTRBOT_REMOTE_CLEAN_ALLOW_MULTIPLE_FORMAL") === "1";
  const artifactDir = env(
    "ASTRBOT_REMOTE_ARTIFACT_DIR",
    path.join("output", "playwright"),
  );

  if (expectedPlugin !== ALLOWED_PLUGIN || confirm !== ALLOWED_PLUGIN) {
    throw new Error(
      `Cleanup is allowlisted to ${ALLOWED_PLUGIN}; set ASTRBOT_EXPECT_PLUGIN and ASTRBOT_REMOTE_CLEAN_CONFIRM to that exact value.`,
    );
  }
  if (!cleanFormal && !cleanFailedUpload) {
    throw new Error(
      "Nothing to clean. Set ASTRBOT_REMOTE_CLEAN_FORMAL=1 or keep ASTRBOT_REMOTE_CLEAN_FAILED_UPLOAD enabled.",
    );
  }

  fs.mkdirSync(artifactDir, { recursive: true });
  const executablePath = resolveBrowserExecutable();
  const launchOptions = {
    headless: env("ASTRBOT_REMOTE_HEADED") !== "1",
    args: ["--no-proxy-server", "--proxy-server=direct://", "--proxy-bypass-list=*"],
  };
  if (executablePath) {
    launchOptions.executablePath = executablePath;
  }

  const browser = await chromium.launch(launchOptions);
  const page = await browser.newPage({ viewport: { width: 1440, height: 1100 } });
  const failedRequests = [];
  page.on("requestfailed", (request) => {
    failedRequests.push({
      url: request.url(),
      failure: request.failure() && request.failure().errorText,
    });
  });

  try {
    await page.goto(remoteUrl, { waitUntil: "domcontentloaded", timeout: 45000 });
    await page.locator("input").nth(0).fill(username);
    await page.locator("input").nth(1).fill(password);
    await page.locator("button[type=\"submit\"]").click();
    await page.waitForURL("**/#/dashboard/default", { timeout: 30000 });
    await page.waitForLoadState("networkidle", { timeout: 30000 }).catch(() => {});

    const beforePlugins = await getJson(page, "/api/plugin/get");
    const beforeFailed = await getJson(
      page,
      "/api/plugin/source/get-failed-plugins",
    );
    const formalCandidates = extractPlugins(beforePlugins)
      .filter((plugin) => pluginMatchesExactly(plugin, expectedPlugin));
    const failedDir = `plugin_upload_${expectedPlugin}`;
    const failedCandidates = failedEntries(beforeFailed).filter(([key, value]) => (
      key === failedDir
      || (value && value.name === failedDir)
    ));

    let formalCleanup = null;
    if (cleanFormal && formalCandidates.length === 1) {
      formalCleanup = await uninstallFormalPlugin(page, expectedPlugin);
      await page.waitForTimeout(3000);
    } else if (cleanFormal && formalCandidates.length > 1 && allowMultipleFormal) {
      formalCleanup = [];
      for (let index = 0; index < formalCandidates.length; index += 1) {
        const result = await uninstallFormalPlugin(page, expectedPlugin);
        formalCleanup.push({
          index,
          candidate: pluginIdentityFields(formalCandidates[index]),
          result,
        });
        await page.waitForTimeout(2500);
      }
    } else if (cleanFormal && formalCandidates.length > 1) {
      throw new Error(
        `Refusing to uninstall: expected one exact formal candidate, found ${formalCandidates.length}. Set ASTRBOT_REMOTE_CLEAN_ALLOW_MULTIPLE_FORMAL=1 to remove all exact same-name candidates.`,
      );
    }

    let failedUploadCleanup = null;
    if (cleanFailedUpload && failedCandidates.length === 1) {
      failedUploadCleanup = await uninstallFailedUpload(page, expectedPlugin);
      await page.waitForTimeout(2000);
    } else if (cleanFailedUpload && failedCandidates.length > 1) {
      throw new Error(
        `Refusing to clean failed upload: expected one exact failed candidate, found ${failedCandidates.length}.`,
      );
    }

    const afterPlugins = await getJson(page, "/api/plugin/get");
    const afterFailed = await getJson(
      page,
      "/api/plugin/source/get-failed-plugins",
    );
    await page.screenshot({
      path: path.join(artifactDir, "remote-after-cleanup.png"),
      fullPage: true,
    });

    const afterFormalCandidates = extractPlugins(afterPlugins)
      .filter((plugin) => pluginMatchesExactly(plugin, expectedPlugin));
    const afterFailedCandidates = failedEntries(afterFailed).filter(([key, value]) => (
      key === failedDir
      || (value && value.name === failedDir)
    ));
    const livingMemoryBefore = extractPlugins(beforePlugins)
      .filter((plugin) => pluginMatchesExactly(plugin, "astrbot_plugin_livingmemory"));
    const livingMemoryAfter = extractPlugins(afterPlugins)
      .filter((plugin) => pluginMatchesExactly(plugin, "astrbot_plugin_livingmemory"));

    const summary = {
      ok: (!cleanFormal || afterFormalCandidates.length === 0)
        && (!cleanFailedUpload || afterFailedCandidates.length === 0),
      remoteUrl,
      expectedPlugin,
      allowlist: ALLOWED_PLUGIN,
      cleanFormal,
      cleanFailedUpload,
      allowMultipleFormal,
      delete_config: false,
      delete_data: false,
      formalCandidatesBefore: formalCandidates.map(pluginIdentityFields),
      failedUploadCandidatesBefore: failedCandidates.map(([key, value]) => ({
        key,
        name: value && value.name,
      })),
      formalCleanup,
      failedUploadCleanup,
      formalCandidatesAfter: afterFormalCandidates.map(pluginIdentityFields),
      failedUploadCandidatesAfter: afterFailedCandidates.map(([key, value]) => ({
        key,
        name: value && value.name,
      })),
      livingMemoryObserved: {
        beforeCount: livingMemoryBefore.length,
        afterCount: livingMemoryAfter.length,
        untouchedByDesign: true,
      },
      failedRequests,
      artifact: path.join(artifactDir, "remote-after-cleanup.png"),
    };
    console.log(JSON.stringify(summary, null, 2));

    if (!summary.ok) {
      process.exitCode = 3;
    }
  } finally {
    await browser.close();
  }
}

main().catch((error) => {
  console.error(error.stack || error);
  process.exit(1);
});
