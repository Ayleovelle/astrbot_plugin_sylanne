const fs = require("fs");
const path = require("path");
const { chromium } = require("playwright");

const ALLOWED_PLUGIN = "astrbot_plugin_sylanne";

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

function readCleanupConfig() {
  const expectedPlugin = requireEnv("ASTRBOT_EXPECT_PLUGIN");
  const config = {
    remoteUrl: requireEnv("ASTRBOT_REMOTE_URL"),
    username: requireEnv("ASTRBOT_REMOTE_USERNAME"),
    password: requireEnv("ASTRBOT_REMOTE_PASSWORD"),
    expectedPlugin,
    confirm: env("ASTRBOT_REMOTE_CLEAN_CONFIRM"),
    cleanFormal: env("ASTRBOT_REMOTE_CLEAN_FORMAL") === "1",
    cleanFailedUpload: env("ASTRBOT_REMOTE_CLEAN_FAILED_UPLOAD", "1") !== "0",
    allowMultipleFormal: env("ASTRBOT_REMOTE_CLEAN_ALLOW_MULTIPLE_FORMAL") === "1",
    artifactDir: env(
      "ASTRBOT_REMOTE_ARTIFACT_DIR",
      path.join("output", "playwright"),
    ),
  };
  validateCleanupConfig(config);
  return config;
}

function validateCleanupConfig(config) {
  if (config.expectedPlugin !== ALLOWED_PLUGIN || config.confirm !== ALLOWED_PLUGIN) {
    throw new Error(
      `Cleanup is allowlisted to ${ALLOWED_PLUGIN}; set ASTRBOT_EXPECT_PLUGIN and ASTRBOT_REMOTE_CLEAN_CONFIRM to that exact value.`,
    );
  }
  if (!config.cleanFormal && !config.cleanFailedUpload) {
    throw new Error(
      "Nothing to clean. Set ASTRBOT_REMOTE_CLEAN_FORMAL=1 or keep ASTRBOT_REMOTE_CLEAN_FAILED_UPLOAD enabled.",
    );
  }
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

function failedUploadDir(expectedPlugin) {
  return `plugin_upload_${expectedPlugin}`;
}

function formalCandidates(payload, expectedPlugin) {
  return extractPlugins(payload)
    .filter((plugin) => pluginMatchesExactly(plugin, expectedPlugin));
}

function failedUploadCandidates(payload, expectedPlugin) {
  const failedDir = failedUploadDir(expectedPlugin);
  return failedEntries(payload).filter(([key, value]) => (
    key === failedDir
    || (value && value.name === failedDir)
  ));
}

function livingMemoryCandidates(payload) {
  return extractPlugins(payload)
    .filter((plugin) => pluginMatchesExactly(plugin, "astrbot_plugin_livingmemory"));
}

function browserLaunchOptions() {
  const options = {
    headless: env("ASTRBOT_REMOTE_HEADED") !== "1",
    args: ["--no-proxy-server", "--proxy-server=direct://", "--proxy-bypass-list=*"],
  };
  const executablePath = resolveBrowserExecutable();
  if (executablePath) {
    options.executablePath = executablePath;
  }
  return options;
}

function watchFailedRequests(page) {
  const failedRequests = [];
  page.on("requestfailed", (request) => {
    failedRequests.push({
      url: request.url(),
      failure: request.failure() && request.failure().errorText,
    });
  });
  return failedRequests;
}

async function requestJson(page, url, options = {}) {
  return await page.evaluate(async ({ targetUrl, requestOptions }) => {
    const parseJson = (text) => {
      try {
        return { json: JSON.parse(text), parse_error: "" };
      } catch (error) {
        return {
          json: null,
          parse_error: error && error.message ? error.message : String(error),
        };
      }
    };
    const response = await fetch(targetUrl, {
      credentials: "include",
      ...requestOptions,
    });
    const text = await response.text();
    const parsed = parseJson(text);
    return {
      status: response.status,
      text: text.slice(0, 2000),
      json: parsed.json,
      parse_error: parsed.parse_error,
    };
  }, { targetUrl: url, requestOptions: options });
}

async function getJson(page, url) {
  return await requestJson(page, url);
}

async function postJson(page, url, body) {
  return await requestJson(page, url, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify(body),
  });
}

async function uninstallFormalPlugin(page, expectedPlugin) {
  return await postJson(page, "/api/plugin/uninstall", {
    name: expectedPlugin,
    delete_config: false,
    delete_data: false,
  });
}

async function uninstallFailedUpload(page, expectedPlugin) {
  return await postJson(page, "/api/plugin/uninstall-failed", {
    dir_name: failedUploadDir(expectedPlugin),
    delete_config: false,
    delete_data: false,
  });
}

async function loginToDashboard(page, config) {
  await page.goto(config.remoteUrl, { waitUntil: "domcontentloaded", timeout: 45000 });
  await page.locator("input").nth(0).fill(config.username);
  await page.locator("input").nth(1).fill(config.password);
  await page.locator("button[type=\"submit\"]").click();
  await page.waitForURL("**/#/dashboard/default", { timeout: 30000 });
  await page.waitForLoadState("networkidle", { timeout: 30000 }).catch(() => {});
}

async function collectSnapshot(page, expectedPlugin) {
  const plugins = await getJson(page, "/api/plugin/get");
  const failed = await getJson(page, "/api/plugin/source/get-failed-plugins");
  return {
    plugins,
    failed,
    formalCandidates: formalCandidates(plugins, expectedPlugin),
    failedCandidates: failedUploadCandidates(failed, expectedPlugin),
    livingMemory: livingMemoryCandidates(plugins),
  };
}

function failedUploadSummary(candidates) {
  return candidates.map(([key, value]) => ({
    key,
    name: value && value.name,
  }));
}

async function cleanupFormalCandidates(page, config, candidates) {
  if (!config.cleanFormal || candidates.length === 0) {
    return null;
  }
  if (candidates.length === 1) {
    const result = await uninstallFormalPlugin(page, config.expectedPlugin);
    await page.waitForTimeout(3000);
    return result;
  }
  if (!config.allowMultipleFormal) {
    throw new Error(
      `Refusing to uninstall: expected one exact formal candidate, found ${candidates.length}. Set ASTRBOT_REMOTE_CLEAN_ALLOW_MULTIPLE_FORMAL=1 to remove all exact same-name candidates.`,
    );
  }
  return await cleanupMultipleFormalCandidates(page, config, candidates);
}

async function cleanupMultipleFormalCandidates(page, config, candidates) {
  const cleanupResults = [];
  for (let index = 0; index < candidates.length; index += 1) {
    const result = await uninstallFormalPlugin(page, config.expectedPlugin);
    cleanupResults.push({
      index,
      candidate: pluginIdentityFields(candidates[index]),
      result,
    });
    await page.waitForTimeout(2500);
  }
  return cleanupResults;
}

async function cleanupFailedUploadCandidates(page, config, candidates) {
  if (!config.cleanFailedUpload || candidates.length === 0) {
    return null;
  }
  if (candidates.length > 1) {
    throw new Error(
      `Refusing to clean failed upload: expected one exact failed candidate, found ${candidates.length}.`,
    );
  }
  const result = await uninstallFailedUpload(page, config.expectedPlugin);
  await page.waitForTimeout(2000);
  return result;
}

async function screenshotAfterCleanup(page, artifactDir) {
  const artifact = path.join(artifactDir, "remote-after-cleanup.png");
  await page.screenshot({ path: artifact, fullPage: true });
  return artifact;
}

function cleanupSucceeded(config, after) {
  return (!config.cleanFormal || after.formalCandidates.length === 0)
    && (!config.cleanFailedUpload || after.failedCandidates.length === 0);
}

function buildSummary({
  config,
  before,
  after,
  formalCleanup,
  failedUploadCleanup,
  failedRequests,
  artifact,
}) {
  return {
    ok: cleanupSucceeded(config, after),
    remoteUrl: config.remoteUrl,
    expectedPlugin: config.expectedPlugin,
    allowlist: ALLOWED_PLUGIN,
    cleanFormal: config.cleanFormal,
    cleanFailedUpload: config.cleanFailedUpload,
    allowMultipleFormal: config.allowMultipleFormal,
    delete_config: false,
    delete_data: false,
    formalCandidatesBefore: before.formalCandidates.map(pluginIdentityFields),
    failedUploadCandidatesBefore: failedUploadSummary(before.failedCandidates),
    formalCleanup,
    failedUploadCleanup,
    formalCandidatesAfter: after.formalCandidates.map(pluginIdentityFields),
    failedUploadCandidatesAfter: failedUploadSummary(after.failedCandidates),
    livingMemoryObserved: {
      beforeCount: before.livingMemory.length,
      afterCount: after.livingMemory.length,
      untouchedByDesign: true,
    },
    failedRequests,
    artifact,
  };
}

async function openCleanupPage() {
  const browser = await chromium.launch(browserLaunchOptions());
  const page = await browser.newPage({ viewport: { width: 1440, height: 1100 } });
  return { browser, page, failedRequests: watchFailedRequests(page) };
}

async function main() {
  const config = readCleanupConfig();
  fs.mkdirSync(config.artifactDir, { recursive: true });
  const { browser, page, failedRequests } = await openCleanupPage();
  try {
    await loginToDashboard(page, config);
    const before = await collectSnapshot(page, config.expectedPlugin);
    const formalCleanup = await cleanupFormalCandidates(
      page,
      config,
      before.formalCandidates,
    );
    const failedUploadCleanup = await cleanupFailedUploadCandidates(
      page,
      config,
      before.failedCandidates,
    );
    const after = await collectSnapshot(page, config.expectedPlugin);
    const artifact = await screenshotAfterCleanup(page, config.artifactDir);
    const summary = buildSummary({
      config,
      before,
      after,
      formalCleanup,
      failedUploadCleanup,
      failedRequests,
      artifact,
    });
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
