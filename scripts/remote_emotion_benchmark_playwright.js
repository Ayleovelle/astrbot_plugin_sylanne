const fs = require("fs");
const path = require("path");
const crypto = require("crypto");
const { chromium } = require("playwright");

const PLUGIN_NAME = "astrbot_plugin_emotional_state";
const CHAT_ENDPOINT = "/api/chat/send";
const CONFIG_GET_ENDPOINT = `/api/config/get?plugin_name=${PLUGIN_NAME}`;
const CONFIG_UPDATE_ENDPOINT = `/api/config/plugin/update?plugin_name=${PLUGIN_NAME}`;
const MAX_CONCURRENCY = 2;

function env(name, fallback = "") {
  const value = process.env[name];
  return value == null || value === "" ? fallback : value;
}

function boolEnv(name, fallback = false) {
  const value = env(name);
  if (!value) {
    return fallback;
  }
  return ["1", "true", "yes", "on"].includes(value.toLowerCase());
}

function intEnv(name, fallback) {
  const value = Number(env(name, String(fallback)));
  return Number.isFinite(value) && value >= 0 ? Math.floor(value) : fallback;
}

function parseJsonEnv(name, fallback) {
  const value = env(name);
  if (!value) {
    return fallback;
  }
  try {
    return JSON.parse(value);
  } catch (error) {
    throw new Error(`${name} must be valid JSON: ${error.message}`);
  }
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

function makeRunId() {
  const stamp = new Date().toISOString().replace(/[-:.TZ]/g, "").slice(0, 14);
  return `remote-emotion-${stamp}-${crypto.randomBytes(4).toString("hex")}`;
}

function nowIso() {
  return new Date().toISOString();
}

function ensureDir(dirPath) {
  fs.mkdirSync(dirPath, { recursive: true });
}

function writeJson(filePath, value) {
  fs.writeFileSync(filePath, `${JSON.stringify(value, null, 2)}\n`, "utf8");
}

function appendJsonl(filePath, value) {
  fs.appendFileSync(filePath, `${JSON.stringify(value)}\n`, "utf8");
}

function sleep(ms) {
  return new Promise((resolve) => setTimeout(resolve, ms));
}

function createMutex() {
  let tail = Promise.resolve();
  return {
    async run(fn) {
      const previous = tail;
      let release;
      tail = new Promise((resolve) => {
        release = resolve;
      });
      await previous;
      try {
        return await fn();
      } finally {
        release();
      }
    },
  };
}

function stableJson(value) {
  if (value == null || typeof value !== "object") {
    return JSON.stringify(value);
  }
  if (Array.isArray(value)) {
    return `[${value.map((item) => stableJson(item)).join(",")}]`;
  }
  return `{${Object.keys(value).sort().map((key) => (
    `${JSON.stringify(key)}:${stableJson(value[key])}`
  )).join(",")}}`;
}

function hashValue(value) {
  return crypto.createHash("sha256").update(stableJson(value)).digest("hex");
}

function safePreview(value, maxLength = 1000) {
  if (value == null) {
    return "";
  }
  const text = typeof value === "string" ? value : stableJson(value);
  return text.slice(0, maxLength);
}

function readCompletedSampleKeys(samplesPath, expectedRunHash) {
  if (!fs.existsSync(samplesPath)) {
    return new Set();
  }
  const latestByKey = new Map();
  const lines = fs.readFileSync(samplesPath, "utf8").split(/\r?\n/);
  for (const line of lines) {
    if (!line.trim()) {
      continue;
    }
    try {
      const sample = JSON.parse(line);
      if (
        sample
        && sample.sample_key
        && sample.run_hash === expectedRunHash
        && sample.status !== "skipped"
      ) {
        latestByKey.set(sample.sample_key, sample);
      }
    } catch {
      // Keep resume tolerant of a truncated final line.
    }
  }
  const completed = new Set();
  for (const [key, sample] of latestByKey.entries()) {
    if (sample.status === "ok") {
      completed.add(key);
    }
  }
  return completed;
}

function readSamples(samplesPath, expectedRunHash) {
  if (!fs.existsSync(samplesPath)) {
    return [];
  }
  const samplesByKey = new Map();
  const unkeyed = [];
  const lines = fs.readFileSync(samplesPath, "utf8").split(/\r?\n/);
  for (const line of lines) {
    if (!line.trim()) {
      continue;
    }
    try {
      const sample = JSON.parse(line);
      if (sample && sample.run_hash === expectedRunHash && sample.status !== "skipped") {
        if (sample.sample_key) {
          samplesByKey.set(sample.sample_key, sample);
        } else {
          unkeyed.push(sample);
        }
      }
    } catch {
      // Keep summaries tolerant of a truncated final line.
    }
  }
  return [...unkeyed, ...samplesByKey.values()];
}

function defaultLifecycleDurations() {
  return {
    "1d": 86400,
    "1w": 604800,
    "1m": 2592000,
    "2m": 5184000,
    "3m": 7776000,
    "4m": 10368000,
    "5m": 12960000,
    "6m": 15552000,
    "1y": 31536000,
  };
}

function offOptionalModules() {
  return {
    enable_psychological_screening: false,
    enable_humanlike_state: false,
    enable_lifelike_learning: false,
    enable_personality_drift: false,
    enable_moral_repair_state: false,
    enable_fallibility_state: false,
    enable_shadow_diagnostics: false,
    enable_integrated_self_state: true,
    integrated_self_degradation_profile: "minimal",
  };
}

function defaultFeatureMatrix() {
  const base = {
    enabled: true,
    use_llm_assessor: false,
    low_reasoning_friendly_mode: false,
    assessment_timing: "post",
    inject_state: false,
    enable_safety_boundary: true,
    persona_modeling: true,
    reset_on_persona_change: true,
    ...offOptionalModules(),
  };
  return [
    {
      id: "baseline_minimal",
      kind: "feature",
      config: base,
    },
    {
      id: "emotion_injection",
      kind: "feature",
      config: {
        ...base,
        inject_state: true,
      },
    },
    {
      id: "low_reasoning",
      kind: "feature",
      config: {
        ...base,
        use_llm_assessor: true,
        low_reasoning_friendly_mode: true,
      },
    },
    {
      id: "humanlike",
      kind: "feature",
      config: {
        ...base,
        inject_state: true,
        enable_humanlike_state: true,
        humanlike_injection_strength: 0.35,
      },
    },
    {
      id: "lifelike_learning",
      kind: "feature",
      config: {
        ...base,
        inject_state: true,
        enable_lifelike_learning: true,
        lifelike_learning_injection_strength: 0.3,
      },
    },
    {
      id: "personality_drift",
      kind: "feature",
      config: {
        ...base,
        inject_state: true,
        enable_personality_drift: true,
        personality_drift_injection_strength: 0.22,
      },
    },
    {
      id: "moral_repair",
      kind: "feature",
      config: {
        ...base,
        inject_state: true,
        enable_moral_repair_state: true,
        moral_repair_injection_strength: 0.35,
      },
    },
    {
      id: "fallibility_low_risk",
      kind: "feature",
      config: {
        ...base,
        inject_state: true,
        enable_fallibility_state: true,
        fallibility_injection_strength: 0.0,
      },
    },
    {
      id: "integrated_self_full",
      kind: "feature",
      config: {
        ...base,
        inject_state: true,
        enable_integrated_self_state: true,
        integrated_self_degradation_profile: "full",
      },
    },
    {
      id: "all_safe_modules",
      kind: "feature",
      config: {
        ...base,
        inject_state: true,
        use_llm_assessor: true,
        low_reasoning_friendly_mode: true,
        enable_humanlike_state: true,
        enable_lifelike_learning: true,
        enable_personality_drift: true,
        enable_moral_repair_state: true,
        enable_fallibility_state: true,
        humanlike_injection_strength: 0.35,
        lifelike_learning_injection_strength: 0.3,
        personality_drift_injection_strength: 0.22,
        moral_repair_injection_strength: 0.35,
        fallibility_injection_strength: 0.0,
        integrated_self_degradation_profile: "balanced",
      },
    },
  ];
}

function defaultFeaturePrompts() {
  return [
    "Please reply in one short sentence. Benchmark marker: neutral greeting.",
    "Please reply in one short sentence. Benchmark marker: user says sorry and asks for a calm reset.",
    "Please reply in one short sentence. Benchmark marker: user introduces a new in-group term named qiaosui.",
  ];
}

function lifecyclePrompt(durationKey, durationSeconds, index) {
  return [
    "SY and AL are a long-running private companion simulation using abbreviated identities only.",
    `Elapsed real time marker: ${durationKey}, ${durationSeconds} seconds.`,
    `Lifecycle sample ${index}: keep the reply short and natural; mention no private profile details.`,
  ].join(" ");
}

function buildBenchmarkConfig() {
  const filePath = env("ASTRBOT_BENCHMARK_CONFIG");
  const fromFile = filePath
    ? JSON.parse(fs.readFileSync(path.resolve(filePath), "utf8"))
    : {};
  return {
    feature_iterations: intEnv(
      "ASTRBOT_BENCHMARK_FEATURE_ITERATIONS",
      fromFile.feature_iterations || 250,
    ),
    lifecycle_iterations: intEnv(
      "ASTRBOT_BENCHMARK_LIFECYCLE_ITERATIONS",
      fromFile.lifecycle_iterations || 100,
    ),
    prewarm: intEnv("ASTRBOT_BENCHMARK_PREWARM", fromFile.prewarm || 2),
    matrix: fromFile.matrix
      || parseJsonEnv("ASTRBOT_BENCHMARK_MATRIX_JSON", null)
      || defaultFeatureMatrix(),
    feature_prompts: fromFile.feature_prompts
      || parseJsonEnv("ASTRBOT_BENCHMARK_FEATURE_PROMPTS_JSON", null)
      || defaultFeaturePrompts(),
    lifecycle_durations: fromFile.lifecycle_durations
      || parseJsonEnv("ASTRBOT_BENCHMARK_LIFECYCLE_DURATIONS_JSON", null)
      || defaultLifecycleDurations(),
  };
}

function buildWork(config, mode) {
  const work = [];
  const includeFeatures = mode === "all" || mode === "features";
  const includeLifecycle = mode === "all" || mode === "lifecycle";
  if (includeFeatures) {
    for (const matrixItem of config.matrix) {
      const iterations = Math.max(0, Number(matrixItem.iterations || config.feature_iterations));
      const prewarm = Math.max(0, Number(matrixItem.prewarm ?? config.prewarm));
      const prompts = Array.isArray(matrixItem.prompts) && matrixItem.prompts.length
        ? matrixItem.prompts
        : config.feature_prompts;
      for (let index = 0; index < prewarm; index += 1) {
        work.push({
          phase: "prewarm",
          kind: "feature",
          case_id: matrixItem.id,
          iteration: index,
          config_patch: matrixItem.config || {},
          prompt: prompts[index % prompts.length],
          count_in_summary: false,
        });
      }
      for (let index = 0; index < iterations; index += 1) {
        work.push({
          phase: "iteration",
          kind: "feature",
          case_id: matrixItem.id,
          iteration: index,
          config_patch: matrixItem.config || {},
          prompt: prompts[index % prompts.length],
          count_in_summary: true,
        });
      }
    }
  }
  if (includeLifecycle) {
    const lifecycleConfig = {
      ...defaultFeatureMatrix().find((item) => item.id === "all_safe_modules").config,
      use_llm_assessor: false,
      low_reasoning_friendly_mode: true,
    };
    for (const [durationKey, durationSeconds] of Object.entries(config.lifecycle_durations)) {
      const simulatedLifecycleConfig = {
        ...lifecycleConfig,
        benchmark_enable_simulated_time: true,
        benchmark_time_offset_seconds: Math.max(0, Number(durationSeconds) || 0),
      };
      const prewarm = Math.max(0, config.prewarm);
      for (let index = 0; index < prewarm; index += 1) {
        work.push({
          phase: "prewarm",
          kind: "lifecycle",
          case_id: `lifecycle_${durationKey}`,
          lifecycle_duration_key: durationKey,
          lifecycle_duration_seconds: durationSeconds,
          iteration: index,
          config_patch: simulatedLifecycleConfig,
          prompt: lifecyclePrompt(durationKey, durationSeconds, index),
          count_in_summary: false,
        });
      }
      for (let index = 0; index < config.lifecycle_iterations; index += 1) {
        work.push({
          phase: "iteration",
          kind: "lifecycle",
          case_id: `lifecycle_${durationKey}`,
          lifecycle_duration_key: durationKey,
          lifecycle_duration_seconds: durationSeconds,
          iteration: index,
          config_patch: simulatedLifecycleConfig,
          prompt: lifecyclePrompt(durationKey, durationSeconds, index),
          count_in_summary: true,
        });
      }
    }
  }
  return work;
}

function sampleKey(item) {
  return [
    item.kind,
    item.case_id,
    item.phase,
    item.iteration,
    hashValue({
      config_patch: item.config_patch,
      prompt: item.prompt,
      lifecycle_duration_key: item.lifecycle_duration_key || null,
    }).slice(0, 12),
  ].join("::");
}

async function fetchJson(page, url, options = {}) {
  return await page.evaluate(async ({ targetUrl, requestOptions }) => {
    const startedAt = performance.now();
    try {
      const response = await fetch(targetUrl, {
        credentials: "include",
        ...requestOptions,
      });
      const text = await response.text();
      let json = null;
      try {
        json = JSON.parse(text);
      } catch {
        json = null;
      }
      return {
        ok: response.ok,
        status: response.status,
        content_type: response.headers.get("content-type") || "",
        elapsed_ms: performance.now() - startedAt,
        text: text.slice(0, 8000),
        json,
      };
    } catch (error) {
      return {
        ok: false,
        status: 0,
        content_type: "",
        elapsed_ms: performance.now() - startedAt,
        text: "",
        json: null,
        error: error.message || String(error),
      };
    }
  }, { targetUrl: url, requestOptions: options });
}

function extractData(payload) {
  if (!payload || !payload.json) {
    return null;
  }
  if (Object.prototype.hasOwnProperty.call(payload.json, "data")) {
    return payload.json.data;
  }
  return payload.json;
}

function normalizeConfigPayload(payload) {
  const data = extractData(payload);
  if (!data || typeof data !== "object") {
    return {};
  }
  if (data.config && typeof data.config === "object") {
    return data.config;
  }
  return data;
}

function mergeConfig(baseConfig, patch) {
  return { ...baseConfig, ...(patch || {}) };
}

async function savePluginConfig(page, config) {
  const bodies = [
    config,
    { plugin_name: PLUGIN_NAME, config },
  ];
  const attempts = [];
  for (const body of bodies) {
    const result = await fetchJson(page, CONFIG_UPDATE_ENDPOINT, {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify(body),
    });
    attempts.push({
      status: result.status,
      ok: result.ok,
      text_preview: safePreview(result.text, 500),
    });
    const statusText = result.json && String(result.json.status || "").toLowerCase();
    if (result.ok && (!statusText || ["ok", "success"].includes(statusText))) {
      return { ok: true, attempts };
    }
  }
  return { ok: false, attempts };
}

async function newSession(page) {
  const result = await fetchJson(page, "/api/chat/new_session");
  const data = extractData(result);
  const sessionId = data && (data.session_id || data.id);
  if (!result.ok || !sessionId) {
    throw new Error(`Failed to create remote chat session: ${result.status} ${safePreview(result.text, 500)}`);
  }
  return String(sessionId);
}

async function deleteSession(page, sessionId) {
  if (!sessionId) {
    return { ok: false, reason: "empty_session_id" };
  }
  return await fetchJson(page, `/api/chat/delete_session?session_id=${encodeURIComponent(sessionId)}`);
}

function parseMaybeJson(value) {
  if (value == null) {
    return value;
  }
  if (typeof value !== "string") {
    return value;
  }
  const trimmed = value.trim();
  if (!trimmed) {
    return "";
  }
  try {
    return JSON.parse(trimmed);
  } catch {
    return value;
  }
}

function flattenObject(value, prefix = "", out = {}) {
  if (value == null) {
    return out;
  }
  if (Array.isArray(value)) {
    value.forEach((item, index) => flattenObject(item, `${prefix}.${index}`, out));
    return out;
  }
  if (typeof value === "object") {
    for (const [key, child] of Object.entries(value)) {
      const next = prefix ? `${prefix}.${key}` : key;
      if (child != null && typeof child === "object") {
        flattenObject(child, next, out);
      } else {
        out[next] = child;
      }
    }
  }
  return out;
}

function extractUsageFromStats(stats) {
  const parsed = parseMaybeJson(stats);
  const flat = flattenObject(parsed);
  const allow = [
    "prompt_tokens",
    "input_tokens",
    "input",
    "input_other",
    "completion_tokens",
    "output_tokens",
    "output",
    "cached_tokens",
    "input_cached",
    "total_tokens",
    "duration",
    "duration_ms",
    "start_time",
    "end_time",
    "ttft",
    "ttft_ms",
    "time_to_first_token",
    "tpm",
  ];
  const usage = {};
  for (const [pathKey, value] of Object.entries(flat)) {
    const lower = pathKey.toLowerCase();
    if (
      lower.includes("access_token")
      || lower.includes("refresh_token")
      || lower.includes("authorization")
      || lower.includes("cookie")
      || lower.includes("csrf")
      || lower.includes("session")
    ) {
      continue;
    }
    const last = lower.split(".").pop();
    if (!allow.includes(last)) {
      continue;
    }
    if (typeof value === "number" && Number.isFinite(value)) {
      usage[pathKey] = value;
    }
  }
  const findFirst = (names) => {
    for (const [key, value] of Object.entries(usage)) {
      const last = key.toLowerCase().split(".").pop();
      if (names.includes(last)) {
        return value;
      }
    }
    return null;
  };
  const inputOther = findFirst(["input_other"]);
  const inputPlain = findFirst(["prompt_tokens", "input_tokens", "input"]);
  const outputTokens = findFirst(["completion_tokens", "output_tokens", "output"]);
  const cachedTokens = findFirst(["cached_tokens", "input_cached"]);
  const inputTokens = inputPlain != null
    ? inputPlain
    : inputOther != null || cachedTokens != null
      ? (inputOther || 0) + (cachedTokens || 0)
      : null;
  let totalTokens = findFirst(["total_tokens"]);
  if (totalTokens == null && (inputTokens != null || outputTokens != null)) {
    totalTokens = (inputTokens || 0) + (outputTokens || 0);
  }
  const startTime = findFirst(["start_time"]);
  const endTime = findFirst(["end_time"]);
  const durationSeconds = startTime != null && endTime != null
    ? Math.max(0, endTime - startTime)
    : null;
  const durationMs = findFirst(["duration_ms"]) ?? (
    durationSeconds != null ? durationSeconds * 1000 : null
  );
  const ttftMs = findFirst(["ttft_ms"]) ?? (
    findFirst(["time_to_first_token", "ttft"]) != null
      ? findFirst(["time_to_first_token", "ttft"]) * 1000
      : null
  );
  return {
    token_source: totalTokens == null && Object.keys(usage).length === 0
      ? "unavailable"
      : "agent_stats",
    token_fields: usage,
    input_tokens: inputTokens,
    output_tokens: outputTokens,
    cached_tokens: cachedTokens,
    total_tokens: totalTokens,
    agent_duration_ms: durationMs,
    agent_ttft_ms: ttftMs,
    agent_stats: parsed,
  };
}

function redactEvent(event) {
  const data = parseMaybeJson(event.data);
  const type = event.type || event.t || "";
  const chainType = event.chain_type || (data && data.chain_type) || "";
  return {
    type,
    chain_type: chainType,
    data_preview: safePreview(data, 800),
  };
}

async function sendChatSse(page, payload) {
  return await page.evaluate(async ({ endpoint, requestPayload }) => {
    const startedAt = performance.now();
    const response = await fetch(endpoint, {
      method: "POST",
      credentials: "include",
      headers: {
        "Content-Type": "application/json",
        Authorization: `Bearer ${localStorage.getItem("token") || ""}`,
      },
      body: JSON.stringify(requestPayload),
    });
    const contentType = response.headers.get("content-type") || "";
    const result = {
      ok: response.ok,
      status: response.status,
      content_type: contentType,
      elapsed_ms: 0,
      ttft_ms: null,
      event_count: 0,
      events: [],
      agent_stats: null,
      response_text: "",
      error: null,
    };
    if (!response.ok || !response.body) {
      result.response_text = (await response.text()).slice(0, 8000);
      result.elapsed_ms = performance.now() - startedAt;
      return result;
    }
    if (!contentType.includes("text/event-stream")) {
      result.response_text = (await response.text()).slice(0, 8000);
      result.elapsed_ms = performance.now() - startedAt;
      return result;
    }
    const reader = response.body.getReader();
    const decoder = new TextDecoder();
    let buffer = "";
    function emitBlock(block) {
      const lines = block.split(/\r?\n/);
      const event = { event: "", data: "" };
      for (const line of lines) {
        if (line.startsWith("event:")) {
          event.event = line.slice(6).trim();
        } else if (line.startsWith("data:")) {
          event.data += `${line.slice(5).trim()}\n`;
        }
      }
      event.data = event.data.trim();
      if (!event.event && !event.data) {
        return;
      }
      let parsed = null;
      try {
        parsed = JSON.parse(event.data);
      } catch {
        parsed = event.data;
      }
      const packet = parsed && typeof parsed === "object"
        ? { ...parsed, event: event.event || parsed.event || "" }
        : { event: event.event, type: event.event, data: parsed };
      result.event_count += 1;
      const packetType = packet.type || packet.t || packet.event || "";
      const chainType = packet.chain_type || "";
      const packetData = packet.data ?? "";
      if (result.ttft_ms == null && (
        packetType === "plain"
        || packetType === "message_saved"
        || packetType === "agent_stats"
        || chainType === "agent_stats"
      )) {
        result.ttft_ms = performance.now() - startedAt;
      }
      if (packetType === "plain" && chainType !== "reasoning") {
        result.response_text += String(packetData);
      }
      if (packetType === "agent_stats" || chainType === "agent_stats") {
        result.agent_stats = packetData;
      }
      if (result.events.length < 80) {
        result.events.push(packet);
      }
    }
    try {
      for (;;) {
        const { value, done } = await reader.read();
        if (done) {
          break;
        }
        buffer += decoder.decode(value, { stream: true });
        const blocks = buffer.split(/\r?\n\r?\n/);
        buffer = blocks.pop() || "";
        for (const block of blocks) {
          emitBlock(block);
        }
      }
      if (buffer.trim()) {
        emitBlock(buffer);
      }
    } catch (error) {
      result.error = error.message || String(error);
    }
    result.elapsed_ms = performance.now() - startedAt;
    return result;
  }, { endpoint: CHAT_ENDPOINT, requestPayload: payload });
}

async function getProviderList(page) {
  const result = await fetchJson(page, "/api/config/provider/list?provider_type=chat_completion");
  const data = extractData(result);
  return Array.isArray(data) ? data : [];
}

async function getProviderTokenSnapshot(page) {
  const result = await fetchJson(page, "/api/stat/provider-tokens?days=1");
  return {
    status: result.status,
    ok: result.ok,
    data: extractData(result),
  };
}

function normalizeProviderTokenSnapshot(snapshot, provider) {
  const data = snapshot && snapshot.data && typeof snapshot.data === "object"
    ? snapshot.data
    : {};
  const providerId = provider && provider.provider_id;
  const modelName = provider && provider.model_name;
  const totals = {
    range_total_tokens: Number(data.range_total_tokens || 0),
    today_total_tokens: Number(data.today_total_tokens || 0),
    provider_tokens: null,
    model_tokens: null,
  };
  const providerRows = []
    .concat(Array.isArray(data.range_by_provider) ? data.range_by_provider : [])
    .concat(Array.isArray(data.today_by_provider) ? data.today_by_provider : []);
  for (const row of providerRows) {
    if (!row || typeof row !== "object") {
      continue;
    }
    const id = String(row.provider_id || row.id || row.name || "");
    if (providerId && id === providerId && Number.isFinite(Number(row.tokens))) {
      totals.provider_tokens = Number(row.tokens);
    }
  }
  const modelRows = []
    .concat(Array.isArray(data.range_by_model) ? data.range_by_model : [])
    .concat(Array.isArray(data.today_by_model) ? data.today_by_model : []);
  for (const row of modelRows) {
    if (!row || typeof row !== "object") {
      continue;
    }
    const name = String(row.model || row.model_name || row.name || "");
    if (modelName && name === modelName && Number.isFinite(Number(row.tokens))) {
      totals.model_tokens = Number(row.tokens);
    }
  }
  return totals;
}

function diffProviderTokenSnapshots(before, after, provider) {
  const lhs = normalizeProviderTokenSnapshot(before, provider);
  const rhs = normalizeProviderTokenSnapshot(after, provider);
  const candidatePairs = [
    ["provider_tokens", lhs.provider_tokens, rhs.provider_tokens],
    ["model_tokens", lhs.model_tokens, rhs.model_tokens],
    ["today_total_tokens", lhs.today_total_tokens, rhs.today_total_tokens],
    ["range_total_tokens", lhs.range_total_tokens, rhs.range_total_tokens],
  ];
  for (const [field, beforeValue, afterValue] of candidatePairs) {
    if (!Number.isFinite(beforeValue) || !Number.isFinite(afterValue)) {
      continue;
    }
    const delta = afterValue - beforeValue;
    if (delta > 0 && delta < 200000) {
      return {
        token_source: "provider_tokens_delta",
        total_tokens: delta,
        token_fields: {
          [`provider_tokens_delta.${field}`]: delta,
        },
      };
    }
  }
  return {
    token_source: "unavailable",
    total_tokens: null,
    token_fields: {},
    token_delta_error: "polluted_or_ambiguous",
  };
}

function selectProvider(providerList, requestedModel) {
  const normalized = String(requestedModel || "").toLowerCase().replace(/[-_.\s]/g, "");
  if (!normalized) {
    return { provider_id: "", model_name: "", found: false, available: providerList };
  }
  const exact = providerList.find((provider) => {
    const model = String(provider.model || provider.model_name || "").toLowerCase().replace(/[-_.\s]/g, "");
    return model === normalized && provider.enable !== false;
  });
  const fuzzy = exact || providerList.find((provider) => {
    const model = String(provider.model || provider.model_name || "").toLowerCase().replace(/[-_.\s]/g, "");
    return model.includes(normalized) && provider.enable !== false;
  });
  if (!fuzzy) {
    return { provider_id: "", model_name: "", found: false, available: providerList };
  }
  return {
    provider_id: String(fuzzy.id || fuzzy.provider_id || ""),
    model_name: String(fuzzy.model || fuzzy.model_name || requestedModel),
    found: true,
    available: providerList,
  };
}

async function login(page, remoteUrl, username, password, artifactDir) {
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
  await page.waitForLoadState("networkidle", { timeout: 30000 }).catch(() => {});
  await page.screenshot({
    path: path.join(artifactDir, "remote-dashboard.png"),
    fullPage: true,
  });
  return page.url();
}

async function runSample(page, item, options) {
  const {
    runId,
    runHash,
    baseConfig,
    provider,
    samplesPath,
    dryRun,
    keepSessions,
    restoreConfig,
    tokenFallback,
    configState,
    configLock,
    workerId,
  } = options;
  const key = sampleKey(item);
  const config = mergeConfig(baseConfig, item.config_patch);
  const configHash = hashValue(config);
  const inputHash = hashValue(item.prompt);
  if (dryRun) {
    const sample = {
      run_id: runId,
      run_hash: runHash,
      sample_key: key,
      status: "ok",
      mode: "dry_run",
      recorded_at: nowIso(),
      kind: item.kind,
      case_id: item.case_id,
      phase: item.phase,
      iteration: item.iteration,
      count_in_summary: item.count_in_summary,
      lifecycle_duration_key: item.lifecycle_duration_key || null,
      lifecycle_duration_seconds: item.lifecycle_duration_seconds || null,
      config_hash: configHash,
      input_hash: inputHash,
      session_id: null,
      elapsed_ms: 0,
      ttft_ms: null,
      token_source: "unavailable",
      total_tokens: null,
    };
    appendJsonl(samplesPath, sample);
    return sample;
  }

  let sessionId = "";
  let cleanup = null;
  const started = Date.now();
  try {
    let configSave = null;
    const ensureConfig = async () => {
      if (!configState || configState.currentHash !== configHash) {
        const saved = await savePluginConfig(page, config);
        if (!saved.ok) {
          throw new Error(`Failed to save plugin config: ${safePreview(saved, 1000)}`);
        }
        if (configState) {
          configState.currentHash = configHash;
        }
        return saved;
      }
      return null;
    };
    configSave = configLock ? await configLock.run(ensureConfig) : await ensureConfig();
    sessionId = await newSession(page);
    const tokenBefore = tokenFallback ? await getProviderTokenSnapshot(page) : null;
    const payload = {
      session_id: sessionId,
      message: [{ type: "plain", text: item.prompt }],
      enable_streaming: true,
      selected_provider: provider.provider_id,
      selected_model: provider.model_name,
      _skip_user_history: false,
      _llm_checkpoint_id: null,
    };
    const result = await sendChatSse(page, payload);
    const usage = extractUsageFromStats(result.agent_stats);
    let tokenFallbackResult = null;
    if (tokenFallback && usage.total_tokens == null) {
      const tokenAfter = await getProviderTokenSnapshot(page);
      tokenFallbackResult = diffProviderTokenSnapshots(tokenBefore, tokenAfter, provider);
      if (tokenFallbackResult.total_tokens != null) {
        usage.token_source = tokenFallbackResult.token_source;
        usage.token_fields = tokenFallbackResult.token_fields;
        usage.total_tokens = tokenFallbackResult.total_tokens;
      }
    }
    const sample = {
      run_id: runId,
      run_hash: runHash,
      sample_key: key,
      status: result.ok && !result.error ? "ok" : "error",
      mode: "chat_sse",
      recorded_at: nowIso(),
      kind: item.kind,
      case_id: item.case_id,
      phase: item.phase,
      iteration: item.iteration,
      count_in_summary: item.count_in_summary,
      lifecycle_duration_key: item.lifecycle_duration_key || null,
      lifecycle_duration_seconds: item.lifecycle_duration_seconds || null,
      config_hash: configHash,
      input_hash: inputHash,
      session_id: sessionId,
      worker_id: workerId == null ? null : workerId,
      provider_id: provider.provider_id || "",
      model_name: provider.model_name || "",
      config_save_skipped: configSave == null,
      http_status: result.status,
      content_type: result.content_type,
      elapsed_ms: result.elapsed_ms,
      ttft_ms: result.ttft_ms,
      agent_duration_ms: usage.agent_duration_ms,
      agent_ttft_ms: usage.agent_ttft_ms,
      wall_clock_ms: Date.now() - started,
      event_count: result.event_count,
      response_chars: result.response_text.length,
      event_preview: result.events.slice(0, 12).map(redactEvent),
      token_source: usage.token_source,
      token_fields: usage.token_fields,
      input_tokens: usage.input_tokens,
      output_tokens: usage.output_tokens,
      cached_tokens: usage.cached_tokens,
      total_tokens: usage.total_tokens,
      agent_stats: usage.agent_stats,
      token_fallback: tokenFallbackResult,
      error: result.error,
    };
    appendJsonl(samplesPath, sample);
    return sample;
  } catch (error) {
    const sample = {
      run_id: runId,
      run_hash: runHash,
      sample_key: key,
      status: "error",
      mode: "chat_sse",
      recorded_at: nowIso(),
      kind: item.kind,
      case_id: item.case_id,
      phase: item.phase,
      iteration: item.iteration,
      count_in_summary: item.count_in_summary,
      lifecycle_duration_key: item.lifecycle_duration_key || null,
      lifecycle_duration_seconds: item.lifecycle_duration_seconds || null,
      config_hash: configHash,
      input_hash: inputHash,
      session_id: sessionId || null,
      worker_id: workerId == null ? null : workerId,
      elapsed_ms: Date.now() - started,
      ttft_ms: null,
      token_source: "unavailable",
      total_tokens: null,
      error: error.stack || String(error),
    };
    appendJsonl(samplesPath, sample);
    return sample;
  } finally {
    if (sessionId && !keepSessions) {
      cleanup = await deleteSession(page, sessionId).catch((error) => ({
        ok: false,
        error: error.message || String(error),
      }));
      appendJsonl(samplesPath.replace(/samples\.jsonl$/, "cleanup.jsonl"), {
        run_id: runId,
        sample_key: key,
        session_id: sessionId,
        recorded_at: nowIso(),
        cleanup_status: cleanup.status || 0,
        cleanup_ok: cleanup.ok !== false,
      });
    }
    if (restoreConfig) {
      await savePluginConfig(page, baseConfig).catch(() => {});
    }
  }
}

function percentile(values, p) {
  if (values.length === 0) {
    return null;
  }
  const index = Math.min(
    values.length - 1,
    Math.max(0, Math.ceil((p / 100) * values.length) - 1),
  );
  return values[index];
}

function summarizeGroup(samples) {
  const ok = samples.filter((sample) => sample.status === "ok" && sample.count_in_summary);
  const latencies = ok
    .map((sample) => sample.elapsed_ms)
    .filter((value) => Number.isFinite(value))
    .sort((a, b) => a - b);
  const ttfts = ok
    .map((sample) => sample.ttft_ms)
    .filter((value) => Number.isFinite(value))
    .sort((a, b) => a - b);
  const tokens = ok
    .map((sample) => sample.total_tokens)
    .filter((value) => Number.isFinite(value));
  const sum = (values) => values.reduce((acc, value) => acc + value, 0);
  return {
    sample_count: samples.filter((sample) => sample.count_in_summary).length,
    ok_count: ok.length,
    error_count: samples.filter((sample) => sample.count_in_summary && sample.status === "error").length,
    latency_ms: {
      p50: percentile(latencies, 50),
      p95: percentile(latencies, 95),
      max: latencies.length ? latencies[latencies.length - 1] : null,
      mean: latencies.length ? sum(latencies) / latencies.length : null,
    },
    ttft_ms: {
      p50: percentile(ttfts, 50),
      p95: percentile(ttfts, 95),
      max: ttfts.length ? ttfts[ttfts.length - 1] : null,
      mean: ttfts.length ? sum(ttfts) / ttfts.length : null,
    },
    tokens: {
      available_count: tokens.length,
      total: tokens.length ? sum(tokens) : null,
      mean: tokens.length ? sum(tokens) / tokens.length : null,
    },
    token_sources: samples.reduce((acc, sample) => {
      const source = sample.token_source || "unavailable";
      acc[source] = (acc[source] || 0) + 1;
      return acc;
    }, {}),
  };
}

function summarize(samples) {
  const byCase = {};
  for (const sample of samples) {
    const key = sample.case_id || "unknown";
    byCase[key] = byCase[key] || [];
    byCase[key].push(sample);
  }
  const caseSummary = {};
  for (const [key, group] of Object.entries(byCase)) {
    caseSummary[key] = summarizeGroup(group);
  }
  const baseline = caseSummary.baseline_minimal || null;
  const deltas = {};
  if (baseline) {
    for (const [key, value] of Object.entries(caseSummary)) {
      if (key === "baseline_minimal") {
        continue;
      }
      deltas[key] = {
        latency_mean_delta_ms: value.latency_ms.mean != null && baseline.latency_ms.mean != null
          ? value.latency_ms.mean - baseline.latency_ms.mean
          : null,
        latency_p95_delta_ms: value.latency_ms.p95 != null && baseline.latency_ms.p95 != null
          ? value.latency_ms.p95 - baseline.latency_ms.p95
          : null,
        token_mean_delta: value.tokens.mean != null && baseline.tokens.mean != null
          ? value.tokens.mean - baseline.tokens.mean
          : null,
      };
    }
  }
  return {
    all: summarizeGroup(samples),
    by_case: caseSummary,
    deltas_vs_baseline_minimal: deltas,
  };
}

function sameConfig(a, b) {
  return hashValue(a.config_patch || {}) === hashValue(b.config_patch || {});
}

async function runChunk(workerPages, chunk, options) {
  if (options.concurrency <= 1 || chunk.length <= 1) {
    const samples = [];
    for (const item of chunk) {
      const sample = await runSample(workerPages[0], item, { ...options, workerId: 0 });
      samples.push(sample);
      if (options.sleepMs > 0) {
        await sleep(options.sleepMs);
      }
    }
    return samples;
  }

  const samples = [];
  let nextIndex = 0;
  const workerCount = Math.min(options.concurrency, workerPages.length, chunk.length);
  await Promise.all(Array.from({ length: workerCount }, async (_, workerId) => {
    const page = workerPages[workerId];
    while (nextIndex < chunk.length) {
      const item = chunk[nextIndex];
      nextIndex += 1;
      const sample = await runSample(page, item, { ...options, workerId });
      samples.push(sample);
      if (options.sleepMs > 0) {
        await sleep(options.sleepMs);
      }
    }
  }));
  return samples;
}

async function runWork(workerPages, work, options) {
  const samples = [];
  const completed = readCompletedSampleKeys(options.samplesPath, options.runHash);
  const maxSamples = Math.max(0, Number(options.maxSamples || 0));
  const pending = [];
  for (const item of work) {
    const key = sampleKey(item);
    if (completed.has(key)) {
      const skipped = {
        run_id: options.runId,
        run_hash: options.runHash,
        sample_key: key,
        status: "skipped",
        mode: options.dryRun ? "dry_run" : "chat_sse",
        recorded_at: nowIso(),
        kind: item.kind,
        case_id: item.case_id,
        phase: item.phase,
        iteration: item.iteration,
        count_in_summary: false,
        reason: "already_present_with_same_run_hash",
      };
      samples.push(skipped);
      continue;
    }
    if (maxSamples > 0 && pending.length >= maxSamples) {
      break;
    }
    pending.push(item);
  }

  let chunk = [];
  for (const item of pending) {
    if (chunk.length > 0 && !sameConfig(chunk[chunk.length - 1], item)) {
      samples.push(...await runChunk(workerPages, chunk, options));
      chunk = [];
    }
    chunk.push(item);
  }
  if (chunk.length > 0) {
    samples.push(...await runChunk(workerPages, chunk, options));
  }
  return samples;
}

async function main() {
  const remoteUrl = env("ASTRBOT_REMOTE_URL");
  const username = env("ASTRBOT_REMOTE_USERNAME");
  const password = env("ASTRBOT_REMOTE_PASSWORD");
  const dryRun = env("ASTRBOT_BENCHMARK_DRY_RUN", "1") !== "0";
  const confirm = env("ASTRBOT_BENCHMARK_CONFIRM");
  const requestedModel = env("ASTRBOT_BENCHMARK_MODEL", "gpt5.5");
  const mode = env("ASTRBOT_BENCHMARK_MODE", "all");
  const runId = env("ASTRBOT_BENCHMARK_RUN_ID", makeRunId());
  const concurrency = Math.min(
    MAX_CONCURRENCY,
    Math.max(1, intEnv("ASTRBOT_BENCHMARK_CONCURRENCY", 1)),
  );
  const keepSessions = boolEnv("ASTRBOT_BENCHMARK_KEEP_SESSIONS", false);
  const restoreConfig = boolEnv("ASTRBOT_BENCHMARK_RESTORE_CONFIG_EACH_SAMPLE", false);
  const restoreConfigAtEnd = env("ASTRBOT_BENCHMARK_RESTORE_CONFIG_AT_END", "1") !== "0";
  const tokenFallback = boolEnv("ASTRBOT_BENCHMARK_TOKEN_FALLBACK", false);
  const effectiveTokenFallback = tokenFallback && concurrency <= 1;
  const maxSamples = intEnv("ASTRBOT_BENCHMARK_MAX_SAMPLES", 0);
  const sleepMs = intEnv("ASTRBOT_BENCHMARK_SLEEP_MS", 250);
  const artifactRoot = env(
    "ASTRBOT_REMOTE_ARTIFACT_DIR",
    path.join("output", "remote_emotion_benchmark"),
  );
  const artifactDir = path.join(artifactRoot, runId);
  const samplesPath = path.join(artifactDir, "samples.jsonl");
  const summaryPath = path.join(artifactDir, "summary.json");
  const config = buildBenchmarkConfig();
  const work = buildWork(config, mode);
  const runHash = hashValue({
    config,
    mode,
    requestedModel,
    chat_endpoint: CHAT_ENDPOINT,
  });

  if (!remoteUrl || !username || !password) {
    throw new Error(
      "Set ASTRBOT_REMOTE_URL, ASTRBOT_REMOTE_USERNAME and ASTRBOT_REMOTE_PASSWORD before running remote benchmark.",
    );
  }
  if (!dryRun && confirm !== "RUN_REMOTE_EMOTION_BENCHMARK") {
    throw new Error(
      "Real benchmark calls are disabled by default. Set ASTRBOT_BENCHMARK_DRY_RUN=0 and ASTRBOT_BENCHMARK_CONFIRM=RUN_REMOTE_EMOTION_BENCHMARK.",
    );
  }
  if (concurrency < 1 || concurrency > MAX_CONCURRENCY) {
    throw new Error(
      `Remote benchmark concurrency must stay between 1 and ${MAX_CONCURRENCY}.`,
    );
  }

  ensureDir(artifactDir);
  const executablePath = resolveBrowserExecutable();
  const launchOptions = {
    headless: env("ASTRBOT_REMOTE_HEADED") !== "1",
    args: ["--no-proxy-server", "--proxy-server=direct://", "--proxy-bypass-list=*"],
  };
  if (executablePath) {
    launchOptions.executablePath = executablePath;
  }

  const browser = await chromium.launch(launchOptions);
  const context = await browser.newContext({ viewport: { width: 1440, height: 1100 } });
  const page = await context.newPage();
  const workerPages = [page];
  const failedRequests = [];
  const trackFailedRequests = (workerPage, workerId) => workerPage.on("requestfailed", (request) => {
    failedRequests.push({
      worker_id: workerId,
      url: request.url(),
      failure: request.failure() && request.failure().errorText,
    });
  });
  trackFailedRequests(page, 0);

  const startedAt = nowIso();
  let authenticatedUrl = "";
  let pluginConfigPayload = null;
  let baseConfig = {};
  let providerList = [];
  let provider = null;
  let samples = [];
  const configState = { currentHash: "" };
  try {
    authenticatedUrl = await login(page, remoteUrl, username, password, artifactDir);
    pluginConfigPayload = await fetchJson(page, CONFIG_GET_ENDPOINT);
    baseConfig = normalizeConfigPayload(pluginConfigPayload);
    providerList = await getProviderList(page);
    provider = selectProvider(providerList, requestedModel);
    if (!dryRun && !provider.found) {
      throw new Error(
        `Requested model ${requestedModel} was not found in enabled provider list.`,
      );
    }
    for (let workerId = 1; workerId < concurrency; workerId += 1) {
      const workerPage = await context.newPage();
      trackFailedRequests(workerPage, workerId);
      await workerPage.goto(authenticatedUrl, { waitUntil: "domcontentloaded", timeout: 45000 });
      await workerPage.waitForLoadState("networkidle", { timeout: 30000 }).catch(() => {});
      workerPages.push(workerPage);
    }
    samples = await runWork(workerPages, work, {
      runId,
      runHash,
      baseConfig,
      provider,
      samplesPath,
      dryRun,
      keepSessions,
      restoreConfig,
      tokenFallback: effectiveTokenFallback,
      configState,
      configLock: createMutex(),
      concurrency,
      maxSamples,
      sleepMs,
    });
  } finally {
    if (restoreConfigAtEnd && Object.keys(baseConfig).length > 0) {
      await savePluginConfig(page, baseConfig).catch(() => {});
    }
    await browser.close();
  }
  const allSamples = readSamples(samplesPath, runHash);

  const summary = {
    ok: allSamples.every((sample) => sample.status !== "error"),
    run_id: runId,
    run_hash: runHash,
    started_at: startedAt,
    finished_at: nowIso(),
    remote_url: remoteUrl,
    logged_in: authenticatedUrl.includes("#/dashboard/default"),
    dry_run: dryRun,
    mode,
    concurrency,
    sleep_ms: sleepMs,
    keep_sessions: keepSessions,
    restore_config_each_sample: restoreConfig,
    restore_config_at_end: restoreConfigAtEnd,
    token_fallback_enabled: effectiveTokenFallback,
    token_fallback_requested: tokenFallback,
    max_samples_this_run: maxSamples,
    requested_model: requestedModel,
    selected_provider: provider && {
      found: provider.found,
      provider_id: provider.provider_id,
      model_name: provider.model_name,
    },
    provider_models: providerList.map((item) => ({
      id: item.id || item.provider_id || "",
      model: item.model || item.model_name || "",
      enable: item.enable !== false,
    })),
    plugin_config_probe: {
      status: pluginConfigPayload ? pluginConfigPayload.status : 0,
      config_keys: Object.keys(baseConfig).sort(),
    },
    work_shape: {
      feature_iterations: config.feature_iterations,
      lifecycle_iterations: config.lifecycle_iterations,
      prewarm: config.prewarm,
      work_items: work.length,
      completed_items: allSamples.filter((sample) => (
        sample.status === "ok" && sample.count_in_summary
      )).length,
      newly_processed_items: samples.filter((sample) => sample.status !== "skipped").length,
    },
    artifacts: {
      directory: artifactDir,
      samples_jsonl: samplesPath,
      cleanup_jsonl: path.join(artifactDir, "cleanup.jsonl"),
      summary_json: summaryPath,
      login_screenshot: path.join(artifactDir, "remote-login-page.png"),
      dashboard_screenshot: path.join(artifactDir, "remote-dashboard.png"),
    },
    aggregate: summarize(allSamples),
    failed_requests: failedRequests,
  };
  writeJson(summaryPath, summary);
  console.log(JSON.stringify(summary, null, 2));
  if (!summary.ok) {
    process.exitCode = 2;
  }
}

main().catch((error) => {
  console.error(error.stack || error);
  process.exit(1);
});
