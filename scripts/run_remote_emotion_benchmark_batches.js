const { spawnSync } = require("child_process");
const fs = require("fs");
const path = require("path");

function env(name, fallback = "") {
  const value = process.env[name];
  return value == null || value === "" ? fallback : value;
}

function intEnv(name, fallback) {
  const value = Number(env(name, String(fallback)));
  return Number.isFinite(value) && value >= 0 ? Math.floor(value) : fallback;
}

function readJson(filePath) {
  return JSON.parse(fs.readFileSync(filePath, "utf8"));
}

function printCaseSummary(summary) {
  const byCase = summary.aggregate && summary.aggregate.by_case
    ? summary.aggregate.by_case
    : {};
  const rows = Object.entries(byCase).map(([id, item]) => ({
    id,
    ok: item.ok_count,
    error: item.error_count,
    latency_mean_ms: item.latency_ms.mean == null ? null : Number(item.latency_ms.mean.toFixed(2)),
    latency_p95_ms: item.latency_ms.p95 == null ? null : Number(item.latency_ms.p95.toFixed(2)),
    token_mean: item.tokens.mean == null ? null : Number(item.tokens.mean.toFixed(2)),
  }));
  console.log(JSON.stringify({
    ok: summary.ok,
    completed_items: summary.work_shape && summary.work_shape.completed_items,
    newly_processed_items: summary.work_shape && summary.work_shape.newly_processed_items,
    rows,
  }, null, 2));
}

const required = [
  "ASTRBOT_REMOTE_URL",
  "ASTRBOT_REMOTE_USERNAME",
  "ASTRBOT_REMOTE_PASSWORD",
];
for (const name of required) {
  if (!env(name)) {
    throw new Error(`${name} is required in the process environment.`);
  }
}

const nodeExe = process.execPath;
const script = path.join("scripts", "remote_emotion_benchmark_playwright.js");
const runId = env("ASTRBOT_BENCHMARK_RUN_ID", "remote-emotion-v010-gpt55-feature-lifecycle");
const artifactRoot = env("ASTRBOT_REMOTE_ARTIFACT_DIR", path.join("output", "remote_emotion_benchmark_official"));
const summaryPath = path.join(artifactRoot, runId, "summary.json");
const maxBatches = intEnv("ASTRBOT_BENCHMARK_BATCHES", 1);
const targetCompleted = intEnv("ASTRBOT_BENCHMARK_TARGET_COMPLETED", 0);
const batchSize = intEnv("ASTRBOT_BENCHMARK_MAX_SAMPLES", 50);

for (let batch = 1; batch <= maxBatches; batch += 1) {
  console.log(`remote benchmark batch ${batch}/${maxBatches}, max_samples=${batchSize}`);
  const childEnv = {
    ...process.env,
    ASTRBOT_BENCHMARK_RUN_ID: runId,
    ASTRBOT_BENCHMARK_MODE: env("ASTRBOT_BENCHMARK_MODE", "features"),
    ASTRBOT_BENCHMARK_FEATURE_ITERATIONS: env("ASTRBOT_BENCHMARK_FEATURE_ITERATIONS", "250"),
    ASTRBOT_BENCHMARK_LIFECYCLE_ITERATIONS: env("ASTRBOT_BENCHMARK_LIFECYCLE_ITERATIONS", "100"),
    ASTRBOT_BENCHMARK_PREWARM: env("ASTRBOT_BENCHMARK_PREWARM", "2"),
    ASTRBOT_BENCHMARK_MAX_SAMPLES: String(batchSize),
    ASTRBOT_BENCHMARK_SLEEP_MS: env("ASTRBOT_BENCHMARK_SLEEP_MS", "1000"),
    ASTRBOT_BENCHMARK_CONCURRENCY: env("ASTRBOT_BENCHMARK_CONCURRENCY", "2"),
    ASTRBOT_BENCHMARK_DRY_RUN: "0",
    ASTRBOT_BENCHMARK_CONFIRM: "RUN_REMOTE_EMOTION_BENCHMARK",
    ASTRBOT_BENCHMARK_MODEL: env("ASTRBOT_BENCHMARK_MODEL", "gpt5.5"),
    ASTRBOT_BENCHMARK_TOKEN_FALLBACK: env("ASTRBOT_BENCHMARK_TOKEN_FALLBACK", "1"),
    ASTRBOT_BENCHMARK_RESTORE_CONFIG_AT_END: env("ASTRBOT_BENCHMARK_RESTORE_CONFIG_AT_END", "1"),
    ASTRBOT_REMOTE_ARTIFACT_DIR: artifactRoot,
  };
  const result = spawnSync(nodeExe, [script], {
    cwd: process.cwd(),
    env: childEnv,
    stdio: "inherit",
    windowsHide: true,
  });
  if (result.status !== 0) {
    process.exit(result.status || 1);
  }
  const summary = readJson(summaryPath);
  printCaseSummary(summary);
  if (!summary.ok) {
    process.exit(2);
  }
  const completed = summary.work_shape && summary.work_shape.completed_items;
  if (targetCompleted > 0 && completed >= targetCompleted) {
    console.log(`target completed_items reached: ${completed}/${targetCompleted}`);
    break;
  }
}
