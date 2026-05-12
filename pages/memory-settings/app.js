const bridge = window.AstrBotPluginPage;

const providerSelect = document.getElementById("provider");
const currentText = document.getElementById("current");
const vectorText = document.getElementById("vector");
const countText = document.getElementById("count");
const detailBox = document.getElementById("providerDetail");
const refreshButton = document.getElementById("refresh");
const saveButton = document.getElementById("save");
const message = document.getElementById("message");

let lastPayload = null;

function setMessage(text, kind = "") {
  message.textContent = text || "";
  message.dataset.kind = kind;
}

function providerLabel(provider) {
  const name = provider.name && provider.name !== provider.id
    ? `${provider.name}（${provider.id}）`
    : provider.id;
  const model = provider.embedding_model ? ` / ${provider.embedding_model}` : "";
  const dims = provider.embedding_dimensions
    ? ` / ${provider.embedding_dimensions} 维`
    : "";
  return `${name}${model}${dims}`;
}

function selectedProvider() {
  if (!lastPayload) {
    return null;
  }
  return (lastPayload.embedding_providers || [])
    .find((item) => item.id === providerSelect.value) || null;
}

function renderDetail() {
  const provider = selectedProvider();
  if (!provider) {
    detailBox.innerHTML = `
      <strong>自动选择</strong>
      <span>留空时，Sylanne 会在运行时使用当前第一个可用的 Embedding 提供商。</span>
    `;
    return;
  }
  detailBox.innerHTML = `
    <strong>${provider.name || provider.id}</strong>
    <span>ID：${provider.id}</span>
    <span>模型：${provider.embedding_model || "未声明"}</span>
    <span>维度：${provider.embedding_dimensions || "未声明"}</span>
  `;
}

function render(payload) {
  lastPayload = payload;
  const providers = payload.embedding_providers || [];
  const current = payload.current_embedding_provider_id || "";

  providerSelect.innerHTML = "";
  const autoOption = document.createElement("option");
  autoOption.value = "";
  autoOption.textContent = "自动选择第一个可用 Embedding 提供商";
  providerSelect.appendChild(autoOption);

  for (const provider of providers) {
    const option = document.createElement("option");
    option.value = provider.id;
    option.textContent = providerLabel(provider);
    providerSelect.appendChild(option);
  }

  providerSelect.value = current;
  if (providerSelect.value !== current) {
    const option = document.createElement("option");
    option.value = current;
    option.textContent = `${current}（当前配置，但 AstrBot 暂未列出）`;
    providerSelect.appendChild(option);
    providerSelect.value = current;
  }

  providerSelect.disabled = false;
  saveButton.disabled = false;
  currentText.textContent = current || "自动选择";
  vectorText.textContent = payload.vector_retrieval_enabled ? "已开启" : "已关闭";
  countText.textContent = `${providers.length}`;
  renderDetail();

  if (!providers.length) {
    setMessage("AstrBot 当前没有返回可用 Embedding 提供商。你仍然可以先去模型提供商页面添加 Embedding 类型模型。", "warn");
  } else if (!payload.current_provider_known && current) {
    setMessage("当前配置的提供商没有出现在 AstrBot 返回列表里，保存前请确认是否仍然可用。", "warn");
  } else {
    setMessage("已读取可用提供商。", "ok");
  }
}

async function load() {
  providerSelect.disabled = true;
  saveButton.disabled = true;
  setMessage("正在读取 AstrBot Embedding 提供商...", "");
  const payload = await bridge.apiGet("memory-settings");
  render(payload);
}

async function save() {
  saveButton.disabled = true;
  setMessage("正在保存选择...", "");
  const payload = await bridge.apiPost("memory-settings", {
    embedding_provider_id: providerSelect.value,
  });
  if (!payload.ok) {
    setMessage(`保存失败：${payload.error || "未知错误"}`, "error");
    saveButton.disabled = false;
    return;
  }
  render({
    ...(lastPayload || {}),
    ...payload,
    native_config_embedding_selector_available: false,
  });
  setMessage("已保存。新的记忆写入和召回会使用这个选择。", "ok");
}

async function main() {
  if (!bridge) {
    setMessage("没有找到 AstrBot 插件 Page Bridge，请从 AstrBot 插件详情页打开本页面。", "error");
    return;
  }
  await bridge.ready();
  providerSelect.addEventListener("change", renderDetail);
  refreshButton.addEventListener("click", () => {
    load().catch((error) => setMessage(`刷新失败：${error.message || error}`, "error"));
  });
  saveButton.addEventListener("click", () => {
    save().catch((error) => setMessage(`保存失败：${error.message || error}`, "error"));
  });
  await load();
}

main().catch((error) => {
  setMessage(`页面初始化失败：${error.message || error}`, "error");
});
