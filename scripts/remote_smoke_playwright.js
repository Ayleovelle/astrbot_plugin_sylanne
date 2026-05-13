const fs = require("fs");
const path = require("path");
const { chromium } = require("playwright");

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

function readRemoteSmokeConfig() {
  const config = {
    remoteUrl: env("ASTRBOT_REMOTE_URL"),
    username: env("ASTRBOT_REMOTE_USERNAME"),
    password: env("ASTRBOT_REMOTE_PASSWORD"),
    expectedPlugin: env("ASTRBOT_EXPECT_PLUGIN"),
    expectedPluginVersion: env("ASTRBOT_EXPECT_PLUGIN_VERSION"),
    expectedPluginDisplayName: env("ASTRBOT_EXPECT_PLUGIN_DISPLAY_NAME"),
    artifactDir: env(
      "ASTRBOT_REMOTE_ARTIFACT_DIR",
      path.join("output", "playwright"),
    ),
  };
  if (!config.remoteUrl || !config.username || !config.password) {
    throw new Error(
      "Set ASTRBOT_REMOTE_URL, ASTRBOT_REMOTE_USERNAME and ASTRBOT_REMOTE_PASSWORD before running remote smoke.",
    );
  }
  return config;
}

function browserLaunchOptions() {
  const executablePath = resolveBrowserExecutable();
  const launchOptions = {
    headless: env("ASTRBOT_REMOTE_HEADED") !== "1",
    args: ["--no-proxy-server", "--proxy-server=direct://", "--proxy-bypass-list=*"],
  };
  if (executablePath) {
    launchOptions.executablePath = executablePath;
  }
  return launchOptions;
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

async function ignoreNetworkIdleTimeout(page) {
  await page.waitForLoadState("networkidle", { timeout: 30000 }).catch(() => {});
}

async function getJson(page, url) {
  return await page.evaluate(async (targetUrl) => {
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
    const response = await fetch(targetUrl, { credentials: "include" });
    const text = await response.text();
    const parsed = parseJson(text);
    return {
      status: response.status,
      url: targetUrl,
      text: text.slice(0, 1000),
      json: parsed.json,
      parse_error: parsed.parse_error,
    };
  }, url);
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

function pluginName(plugin) {
  return plugin && (
    plugin.name
    || plugin.plugin_name
    || plugin.repo
    || (plugin.metadata && plugin.metadata.name)
    || plugin.id
    || ""
  );
}

function summarizePluginPayload(payload) {
  const plugins = extractPlugins(payload);
  return {
    status: payload ? payload.status : 0,
    count: plugins.length,
    names: plugins.map((plugin) => pluginName(plugin)).filter(Boolean),
  };
}

function findFailedPlugin(failedPlugins, expectedPlugin) {
  if (!expectedPlugin || !failedPlugins || typeof failedPlugins !== "object") {
    return null;
  }
  return Object.entries(failedPlugins).find(([key, value]) => (
    key === expectedPlugin
    || key === `plugin_upload_${expectedPlugin}`
    || (value && (
      value.name === expectedPlugin
      || value.name === `plugin_upload_${expectedPlugin}`
    ))
  )) || null;
}

function failedPluginName(key, value) {
  return (value && (
    value.name
    || value.plugin_name
    || value.display_name
    || value.repo
  )) || key;
}

function summarizeFailedPlugins(failedPlugins, expectedPlugin) {
  const entries = failedPlugins && typeof failedPlugins === "object"
    ? Object.entries(failedPlugins)
    : [];
  const expectedEntry = findFailedPlugin(failedPlugins, expectedPlugin);
  const expectedKey = expectedEntry ? expectedEntry[0] : null;
  const names = entries
    .map(([key, value]) => failedPluginName(key, value))
    .filter(Boolean);
  return {
    count: entries.length,
    names,
    hasAny: entries.length > 0,
    hasExpectedPluginFailure: Boolean(expectedEntry),
    expectedPluginFailureKey: expectedKey,
    unrelatedCount: entries.filter(([key]) => key !== expectedKey).length,
  };
}

function findPluginByName(payload, expectedPlugin) {
  if (!expectedPlugin) {
    return null;
  }
  return extractPlugins(payload).find((plugin) => (
    pluginName(plugin) === expectedPlugin
    || plugin.dir_name === expectedPlugin
    || plugin.folder_name === expectedPlugin
  )) || null;
}

function summarizePluginRuntime(plugin) {
  if (!plugin) {
    return null;
  }
  const metadata = plugin.metadata && typeof plugin.metadata === "object"
    ? plugin.metadata
    : {};
  const booleanOrNull = (value) => (
    typeof value === "boolean" ? value : null
  );
  return {
    name: pluginName(plugin),
    displayName: plugin.display_name || metadata.display_name || "",
    version: plugin.version || metadata.version || "",
    activated: booleanOrNull(plugin.activated),
    reserved: booleanOrNull(plugin.reserved),
    author: plugin.author || metadata.author || "",
    desc: plugin.desc || metadata.desc || "",
    repo: plugin.repo || metadata.repo || "",
    astrbotVersion: plugin.astrbot_version || metadata.astrbot_version || "",
    installedAt: plugin.installed_at || "",
  };
}

async function waitForExtensionUi(page, expected, expectedDisplayName) {
  const terms = [expected, expectedDisplayName].filter(Boolean);
  return await page.waitForFunction(({ expectedTerms }) => {
    const normalize = (value) => (value || "").replace(/\s+/g, " ").trim();
    const bodyText = normalize(document.body.innerText);
    const titleRows = document.querySelectorAll(".extension-title-row").length;
    const extensionLikeNodes = document.querySelectorAll("[class*='extension']").length;
    const pluginLikeNodes = document.querySelectorAll("[class*='plugin']").length;
    return (
      expectedTerms.some((term) => bodyText.includes(term))
      || titleRows > 0
      || extensionLikeNodes > 0
      || pluginLikeNodes > 0
    );
  }, { expectedTerms: terms }, { timeout: 10000 })
    .then(() => "ready")
    .catch(() => "best_effort_timeout");
}

async function loginToDashboard(page, config) {
  await page.goto(config.remoteUrl, { waitUntil: "domcontentloaded", timeout: 45000 });
  await ignoreNetworkIdleTimeout(page);
  await page.screenshot({
    path: path.join(config.artifactDir, "remote-login-page.png"),
    fullPage: true,
  });

  await page.locator("input").nth(0).fill(config.username);
  await page.locator("input").nth(1).fill(config.password);
  await page.locator("button[type=\"submit\"]").click();
  await page.waitForURL("**/#/dashboard/default", { timeout: 30000 });
  const authenticatedUrl = page.url();
  await ignoreNetworkIdleTimeout(page);
  await page.screenshot({
    path: path.join(config.artifactDir, "remote-dashboard.png"),
    fullPage: true,
  });
  return authenticatedUrl;
}

async function collectApiSnapshot(page) {
  const version = await getJson(page, "/api/stat/version");
  const pluginPayload = await getJson(page, "/api/plugin/get");
  const failedPlugins = await getJson(page, "/api/plugin/source/get-failed-plugins");
  return {
    version,
    pluginPayload,
    failedPlugins,
    apiHealth: {
      statVersion: {
        endpoint: "/api/stat/version",
        status: version.status,
        ok: version.status === 200,
      },
      pluginGet: {
        endpoint: "/api/plugin/get",
        status: pluginPayload.status,
        ok: pluginPayload.status === 200,
      },
      failedPlugins: {
        endpoint: "/api/plugin/source/get-failed-plugins",
        status: failedPlugins.status,
        ok: failedPlugins.status === 200,
      },
    },
  };
}

function buildExpectedPluginState(api, config) {
  const { pluginPayload, failedPlugins } = api;
  const {
    expectedPlugin,
    expectedPluginVersion,
    expectedPluginDisplayName,
  } = config;
  const pluginSummary = summarizePluginPayload(pluginPayload);
  const expectedPluginRecord = findPluginByName(pluginPayload, expectedPlugin);
  const containsExpectedPlugin = expectedPlugin
    ? Boolean(expectedPluginRecord)
    : null;
  const expectedPluginRuntime = summarizePluginRuntime(expectedPluginRecord);
  const expectedPluginVersionMatches = expectedPluginVersion
    ? expectedPluginRuntime && expectedPluginRuntime.version === expectedPluginVersion
    : null;
  const expectedPluginDisplayNameMatches = expectedPluginDisplayName
    ? expectedPluginRuntime
      && expectedPluginRuntime.displayName === expectedPluginDisplayName
    : null;
  const failedPluginData = failedPlugins.json && failedPlugins.json.data;
  const expectedFailedPlugin = findFailedPlugin(failedPluginData, expectedPlugin);
  const failedPluginSummary = summarizeFailedPlugins(
    failedPluginData,
    expectedPlugin,
  );
  const expectedPluginChecks = expectedPlugin ? {
    ok: Boolean(
      containsExpectedPlugin
      && !expectedFailedPlugin
      && (!expectedPluginRuntime || expectedPluginRuntime.activated !== false)
      && (expectedPluginVersion ? Boolean(expectedPluginVersionMatches) : true)
      && (expectedPluginDisplayName ? Boolean(expectedPluginDisplayNameMatches) : true)
    ),
    found: containsExpectedPlugin,
    notFailed: !expectedFailedPlugin,
    activated: expectedPluginRuntime
      ? expectedPluginRuntime.activated !== false
      : null,
    versionMatches: expectedPluginVersion ? Boolean(expectedPluginVersionMatches) : null,
    displayNameMatches: expectedPluginDisplayName
      ? Boolean(expectedPluginDisplayNameMatches)
      : null,
  } : null;
  const expectedPluginHasDrift = Boolean(
    (expectedPluginVersion && expectedPluginRuntime && !expectedPluginVersionMatches)
    || (
      expectedPluginDisplayName
      && expectedPluginRuntime
      && !expectedPluginDisplayNameMatches
    ),
  );
  const expectedPluginDrift = expectedPlugin ? {
    hasDrift: expectedPluginHasDrift,
    version: expectedPluginVersion ? {
      expected: expectedPluginVersion,
      actual: expectedPluginRuntime ? expectedPluginRuntime.version : null,
      matches: Boolean(expectedPluginVersionMatches),
    } : null,
    displayName: expectedPluginDisplayName ? {
      expected: expectedPluginDisplayName,
      actual: expectedPluginRuntime ? expectedPluginRuntime.displayName : null,
      matches: Boolean(expectedPluginDisplayNameMatches),
    } : null,
    reason: expectedPluginHasDrift
      ? "installed runtime metadata differs from pinned expectations; upload-install does not overwrite an existing formal plugin directory"
      : null,
  } : null;
  return {
    pluginSummary,
    expectedPluginChecks,
    expectedPluginDrift,
    containsExpectedPlugin,
    expectedPluginRuntime,
    expectedPluginVersionMatches,
    expectedPluginDisplayNameMatches,
    expectedFailedPlugin,
    failedPluginSummary,
    failedPluginData,
  };
}

async function openInstalledExtensionPage(page) {
  await page.evaluate(() => {
    location.hash = "#/extension#installed";
  });
  await ignoreNetworkIdleTimeout(page);
  await page.waitForTimeout(2000);
  if (page.url().includes("#/extension#installed")) {
    return;
  }
  const clicked = await page.evaluate(() => {
    const links = [...document.querySelectorAll("a")];
    const link = links.find((item) => (
      item.href.includes("#/extension#installed")
      || item.textContent.includes("AstrBot 插件")
    ));
    if (link) {
      link.click();
      return true;
    }
    return false;
  });
  if (clicked) {
    await page.waitForTimeout(2000);
    await ignoreNetworkIdleTimeout(page);
  }
}

async function collectExtensionPageData(page, config, expectedPluginRuntime) {
  const expectedUiDisplayName = config.expectedPluginDisplayName
    || (expectedPluginRuntime && expectedPluginRuntime.displayName)
    || "";
  const uiProbeWaitStatus = await waitForExtensionUi(
    page,
    config.expectedPlugin,
    expectedUiDisplayName,
  );
  await page.screenshot({
    path: path.join(config.artifactDir, "remote-extension-installed.png"),
    fullPage: true,
  });
  return await page.evaluate(({
    expected,
    expectedDisplayName,
    waitStatus,
  }) => {
    const normalize = (value) => (value || "").replace(/\s+/g, " ").trim();
    const bodyText = normalize(document.body.innerText);
    const pluginTitles = [...document.querySelectorAll(".extension-title-row")]
      .map((element) => normalize(element.innerText))
      .filter(Boolean);
    const selectorCounts = {
      extensionTitleRows: document.querySelectorAll(".extension-title-row").length,
      extensionLikeNodes: document.querySelectorAll("[class*='extension']").length,
      pluginLikeNodes: document.querySelectorAll("[class*='plugin']").length,
      cardLikeNodes: document.querySelectorAll(
        ".ant-card, .semi-card, [class*='card']",
      ).length,
    };
    const hasExpectedPluginId = expected ? bodyText.includes(expected) : null;
    const hasExpectedPluginDisplayName = expectedDisplayName
      ? bodyText.includes(expectedDisplayName)
      : null;
    const titleHasExpectedPlugin = expected || expectedDisplayName
      ? pluginTitles.some((title) => (
        (expected && title.includes(expected))
        || (expectedDisplayName && title.includes(expectedDisplayName))
      ))
      : null;
    const hasExpectedPluginInUi = expected || expectedDisplayName
      ? Boolean(hasExpectedPluginId || hasExpectedPluginDisplayName || titleHasExpectedPlugin)
      : null;
    return {
      title: document.title,
      url: location.href,
      hasExpectedPlugin: hasExpectedPluginInUi,
      hasExpectedPluginId,
      hasExpectedPluginDisplayName,
      hasExpectedPluginInUi,
      uiProbeStatus: pluginTitles.length > 0 || hasExpectedPluginId || hasExpectedPluginDisplayName
        ? "ready"
        : waitStatus,
      selectorCounts,
      bodyTextPreview: bodyText.slice(0, 500),
      hasLivingMemory: bodyText.includes("astrbot_plugin_livingmemory"),
      pluginTitles,
    };
  }, {
    expected: config.expectedPlugin,
    expectedDisplayName: expectedUiDisplayName,
    waitStatus: uiProbeWaitStatus,
  });
}

function buildSummary(config, authenticatedUrl, api, expectedState, pageData, failedRequests) {
  return {
    ok: true,
    remoteUrl: config.remoteUrl,
    loggedIn: authenticatedUrl.includes("#/dashboard/default"),
    extensionRouteLoaded: pageData.url.includes("#/extension#installed"),
    version: api.version.json && api.version.json.data,
    apiHealth: api.apiHealth,
    pluginSummary: expectedState.pluginSummary,
    expectedPlugin: config.expectedPlugin || null,
    expectedPluginChecks: expectedState.expectedPluginChecks,
    expectedPluginDrift: expectedState.expectedPluginDrift,
    containsExpectedPlugin: expectedState.containsExpectedPlugin,
    expectedPluginRuntime: expectedState.expectedPluginRuntime,
    expectedPluginVersion: config.expectedPluginVersion || null,
    expectedPluginVersionMatches: expectedState.expectedPluginVersionMatches,
    expectedPluginDisplayName: config.expectedPluginDisplayName || null,
    expectedPluginDisplayNameMatches: expectedState.expectedPluginDisplayNameMatches,
    expectedFailedPlugin: expectedState.expectedFailedPlugin,
    failedPluginSummary: expectedState.failedPluginSummary,
    failedPlugins: expectedState.failedPluginData,
    pageData,
    failedRequests,
    artifacts: {
      login: path.join(config.artifactDir, "remote-login-page.png"),
      dashboard: path.join(config.artifactDir, "remote-dashboard.png"),
      extension: path.join(config.artifactDir, "remote-extension-installed.png"),
    },
  };
}

function updateExitCode(api, config, expectedState) {
  const { expectedPlugin, expectedPluginVersion, expectedPluginDisplayName } = config;
  const { version, pluginPayload, failedPlugins } = api;
  const runtime = expectedState.expectedPluginRuntime;
  if (version.status !== 200 || pluginPayload.status !== 200) {
    process.exitCode = 1;
  }
  if (failedPlugins.status !== 200) {
    process.exitCode = 9;
  }
  if (expectedPlugin && !expectedState.containsExpectedPlugin) {
    process.exitCode = 2;
  }
  if (expectedPlugin && expectedState.expectedFailedPlugin) {
    process.exitCode = 5;
  }
  if (expectedPlugin && runtime && runtime.activated === false) {
    process.exitCode = 6;
  }
  if (expectedPluginVersion && runtime && !expectedState.expectedPluginVersionMatches) {
    process.exitCode = 7;
  }
  if (expectedPluginDisplayName && runtime && !expectedState.expectedPluginDisplayNameMatches) {
    process.exitCode = 8;
  }
}

async function main() {
  const config = readRemoteSmokeConfig();
  fs.mkdirSync(config.artifactDir, { recursive: true });
  const browser = await chromium.launch(browserLaunchOptions());
  const page = await browser.newPage({ viewport: { width: 1440, height: 1100 } });
  const failedRequests = watchFailedRequests(page);

  try {
    const authenticatedUrl = await loginToDashboard(page, config);
    const api = await collectApiSnapshot(page);
    const expectedState = buildExpectedPluginState(api, config);
    await openInstalledExtensionPage(page);
    const pageData = await collectExtensionPageData(
      page,
      config,
      expectedState.expectedPluginRuntime,
    );
    const summary = buildSummary(
      config,
      authenticatedUrl,
      api,
      expectedState,
      pageData,
      failedRequests,
    );
    console.log(JSON.stringify(summary, null, 2));
    updateExitCode(api, config, expectedState);
  } finally {
    await browser.close();
  }
}

main().catch((error) => {
  console.error(error.stack || error);
  process.exit(1);
});
