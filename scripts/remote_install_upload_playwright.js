const fs = require("fs");
const path = require("path");
const { chromium } = require("playwright");
const { assertZipLooksUploadable } = require("./plugin_zip_preflight");

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
    throw new Error(`Set ${name} before running remote install upload.`);
  }
  return value;
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

function summarizePluginPayload(payload) {
  const json = payload && payload.json;
  const raw = json && (json.data || json.plugins || json);
  const plugins = Array.isArray(raw)
    ? raw
    : raw && Array.isArray(raw.plugins)
      ? raw.plugins
      : [];
  return {
    status: payload ? payload.status : 0,
    count: plugins.length,
    names: plugins.map((plugin) => (
      plugin.name
      || plugin.plugin_name
      || plugin.repo
      || (plugin.metadata && plugin.metadata.name)
      || plugin.id
      || ""
    )).filter(Boolean),
  };
}

async function uploadPlugin(page, zipPath) {
  const zipBytes = fs.readFileSync(zipPath);
  return await page.evaluate(async ({ bytesArray, fileName }) => {
    const form = new FormData();
    form.append(
      "file",
      new File([new Uint8Array(bytesArray)], fileName, { type: "application/zip" }),
    );
    form.append("ignore_version_check", "false");
    const response = await fetch("/api/plugin/install-upload", {
      method: "POST",
      credentials: "include",
      body: form,
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
      text: text.slice(0, 4000),
      json,
    };
  }, {
    bytesArray: Array.from(zipBytes),
    fileName: path.basename(zipPath),
  });
}

async function cleanupAlreadyInstalledFailure(page, expectedPlugin) {
  const failedDir = `plugin_upload_${expectedPlugin}`;
  return await page.evaluate(async ({ targetDir }) => {
    const response = await fetch("/api/plugin/uninstall-failed", {
      method: "POST",
      credentials: "include",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({
        dir_name: targetDir,
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
  }, { targetDir: failedDir });
}

async function main() {
  const remoteUrl = requireEnv("ASTRBOT_REMOTE_URL");
  const username = requireEnv("ASTRBOT_REMOTE_USERNAME");
  const password = requireEnv("ASTRBOT_REMOTE_PASSWORD");
  const zipPath = path.resolve(requireEnv("ASTRBOT_REMOTE_INSTALL_ZIP"));
  const expectedPlugin = requireEnv("ASTRBOT_EXPECT_PLUGIN");
  const confirm = env("ASTRBOT_REMOTE_INSTALL_CONFIRM");
  if (confirm !== "1") {
    throw new Error("Set ASTRBOT_REMOTE_INSTALL_CONFIRM=1 to upload and install.");
  }
  const preflight = assertZipLooksUploadable(zipPath, expectedPlugin, {
    maxBytes: Number(env("ASTRBOT_REMOTE_INSTALL_MAX_BYTES", 40 * 1024 * 1024)),
  });
  const zipSize = preflight.size;
  const artifactDir = env(
    "ASTRBOT_REMOTE_ARTIFACT_DIR",
    path.join("output", "playwright"),
  );

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
    const upload = await uploadPlugin(page, zipPath);

    await page.waitForTimeout(7000);
    await page.evaluate(() => {
      location.hash = "#/extension#installed";
    });
    await page.waitForLoadState("networkidle", { timeout: 30000 }).catch(() => {});
    await page.waitForTimeout(3000);
    const afterPlugins = await getJson(page, "/api/plugin/get");
    let afterFailed = await getJson(
      page,
      "/api/plugin/source/get-failed-plugins",
    );
    await page.screenshot({
      path: path.join(artifactDir, "remote-after-install-upload.png"),
      fullPage: true,
    });

    const beforeSummary = summarizePluginPayload(beforePlugins);
    const afterSummary = summarizePluginPayload(afterPlugins);
    const containsExpectedPlugin = afterSummary.names.includes(expectedPlugin);
    const uploadOk = upload.status === 200
      && upload.json
      && (upload.json.status === "ok" || upload.json.status === "success");
    const alreadyInstalled = upload.status === 200
      && upload.json
      && upload.json.status === "error"
      && typeof upload.json.message === "string"
      && upload.json.message.includes(`目录 ${expectedPlugin} 已存在`)
      && containsExpectedPlugin;
    const failedData = afterFailed.json && afterFailed.json.data;
    const failedEntries = failedData && typeof failedData === "object"
      ? Object.values(failedData)
      : [];
    const expectedFailed = failedEntries.find((entry) => (
      entry
      && (entry.name === expectedPlugin || entry.name === `plugin_upload_${expectedPlugin}`)
    ));
    let cleanup = null;
    if (alreadyInstalled && expectedFailed) {
      cleanup = await cleanupAlreadyInstalledFailure(page, expectedPlugin);
      await page.waitForTimeout(2000);
      afterFailed = await getJson(page, "/api/plugin/source/get-failed-plugins");
    }
    const finalFailedData = afterFailed.json && afterFailed.json.data;
    const finalFailedEntries = finalFailedData && typeof finalFailedData === "object"
      ? Object.values(finalFailedData)
      : [];
    const finalExpectedFailed = finalFailedEntries.find((entry) => (
      entry
      && (entry.name === expectedPlugin || entry.name === `plugin_upload_${expectedPlugin}`)
    ));

    const summary = {
      ok: (uploadOk || alreadyInstalled)
        && containsExpectedPlugin
        && !finalExpectedFailed,
      remoteUrl,
      expectedPlugin,
      zipPath,
      zipSize,
      upload,
      alreadyInstalled,
      installOutcome: alreadyInstalled
        ? "already_installed_no_overwrite"
        : uploadOk
          ? "uploaded"
          : "failed",
      overwriteAttempted: false,
      formalPluginDirectoryPreserved: alreadyInstalled ? true : null,
      cleanup,
      beforeSummary,
      afterSummary,
      containsExpectedPlugin,
      beforeFailed: beforeFailed.json && beforeFailed.json.data,
      afterFailed: finalFailedData,
      failedRequests,
      artifact: path.join(artifactDir, "remote-after-install-upload.png"),
    };
    console.log(JSON.stringify(summary, null, 2));

    if (!uploadOk && !alreadyInstalled) {
      process.exitCode = 4;
    } else if (!containsExpectedPlugin) {
      process.exitCode = 2;
    } else if (finalExpectedFailed) {
      process.exitCode = 5;
    }
  } finally {
    await browser.close();
  }
}

main().catch((error) => {
  console.error(error.stack || error);
  process.exit(1);
});
