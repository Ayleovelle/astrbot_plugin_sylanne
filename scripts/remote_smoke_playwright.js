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
      url: targetUrl,
      text: text.slice(0, 1000),
      json,
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

async function main() {
  const remoteUrl = env("ASTRBOT_REMOTE_URL");
  const username = env("ASTRBOT_REMOTE_USERNAME");
  const password = env("ASTRBOT_REMOTE_PASSWORD");
  const expectedPlugin = env("ASTRBOT_EXPECT_PLUGIN");
  const expectedPluginVersion = env("ASTRBOT_EXPECT_PLUGIN_VERSION");
  const expectedPluginDisplayName = env("ASTRBOT_EXPECT_PLUGIN_DISPLAY_NAME");
  const artifactDir = env(
    "ASTRBOT_REMOTE_ARTIFACT_DIR",
    path.join("output", "playwright"),
  );

  if (!remoteUrl || !username || !password) {
    throw new Error(
      "Set ASTRBOT_REMOTE_URL, ASTRBOT_REMOTE_USERNAME and ASTRBOT_REMOTE_PASSWORD before running remote smoke.",
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
    await page.waitForLoadState("networkidle", { timeout: 30000 }).catch(() => {});
    await page.screenshot({
      path: path.join(artifactDir, "remote-login-page.png"),
      fullPage: true,
    });

    await page.locator("input").nth(0).fill(username);
    await page.locator("input").nth(1).fill(password);
    await page.locator("button[type=\"submit\"]").click();
    await page.waitForURL("**/#/dashboard/default", { timeout: 30000 });
    const authenticatedUrl = page.url();
    await page.waitForLoadState("networkidle", { timeout: 30000 }).catch(() => {});
    await page.screenshot({
      path: path.join(artifactDir, "remote-dashboard.png"),
      fullPage: true,
    });

    const version = await getJson(page, "/api/stat/version");
    const pluginPayload = await getJson(page, "/api/plugin/get");
    const failedPlugins = await getJson(page, "/api/plugin/source/get-failed-plugins");
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

    await page.evaluate(() => {
      location.hash = "#/extension#installed";
    });
    await page.waitForLoadState("networkidle", { timeout: 30000 }).catch(() => {});
    await page.waitForTimeout(2000);
    if (!page.url().includes("#/extension#installed")) {
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
        await page.waitForLoadState("networkidle", { timeout: 30000 }).catch(() => {});
      }
    }
    await page.screenshot({
      path: path.join(artifactDir, "remote-extension-installed.png"),
      fullPage: true,
    });

    const pageData = await page.evaluate(({ expected, expectedDisplayName }) => {
      const normalize = (value) => (value || "").replace(/\s+/g, " ").trim();
      const bodyText = normalize(document.body.innerText);
      const pluginTitles = [...document.querySelectorAll(".extension-title-row")]
        .map((element) => normalize(element.innerText))
        .filter(Boolean);
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
      return {
        title: document.title,
        url: location.href,
        hasExpectedPlugin: hasExpectedPluginId,
        hasExpectedPluginId,
        hasExpectedPluginDisplayName,
        hasExpectedPluginInUi: expected || expectedDisplayName
          ? Boolean(hasExpectedPluginId || hasExpectedPluginDisplayName || titleHasExpectedPlugin)
          : null,
        hasLivingMemory: bodyText.includes("astrbot_plugin_livingmemory"),
        pluginTitles,
      };
    }, {
      expected: expectedPlugin,
      expectedDisplayName: expectedPluginDisplayName
        || (expectedPluginRuntime && expectedPluginRuntime.displayName)
        || "",
    });

    const summary = {
      ok: true,
      remoteUrl,
      loggedIn: authenticatedUrl.includes("#/dashboard/default"),
      extensionRouteLoaded: page.url().includes("#/extension#installed"),
      version: version.json && version.json.data,
      pluginSummary,
      expectedPlugin: expectedPlugin || null,
      containsExpectedPlugin,
      expectedPluginRuntime,
      expectedPluginVersion: expectedPluginVersion || null,
      expectedPluginVersionMatches,
      expectedPluginDisplayName: expectedPluginDisplayName || null,
      expectedPluginDisplayNameMatches,
      expectedFailedPlugin,
      failedPlugins: failedPluginData,
      pageData,
      failedRequests,
      artifacts: {
        login: path.join(artifactDir, "remote-login-page.png"),
        dashboard: path.join(artifactDir, "remote-dashboard.png"),
        extension: path.join(artifactDir, "remote-extension-installed.png"),
      },
    };
    console.log(JSON.stringify(summary, null, 2));

    if (version.status !== 200 || pluginPayload.status !== 200) {
      process.exitCode = 1;
    }
    if (expectedPlugin && !containsExpectedPlugin) {
      process.exitCode = 2;
    }
    if (expectedPlugin && expectedFailedPlugin) {
      process.exitCode = 5;
    }
    if (
      expectedPlugin
      && expectedPluginRuntime
      && expectedPluginRuntime.activated === false
    ) {
      process.exitCode = 6;
    }
    if (expectedPluginVersion && expectedPluginRuntime && !expectedPluginVersionMatches) {
      process.exitCode = 7;
    }
    if (
      expectedPluginDisplayName
      && expectedPluginRuntime
      && !expectedPluginDisplayNameMatches
    ) {
      process.exitCode = 8;
    }
  } finally {
    await browser.close();
  }
}

main().catch((error) => {
  console.error(error.stack || error);
  process.exit(1);
});
