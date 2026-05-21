function setText(selector, text) {
  const node = document.querySelector(selector);
  if (node) node.textContent = text;
}

function renderTokenFlow(flow) {
  const list = document.querySelector('[data-token-list]');
  if (!list) return;
  const tokens = flow?.tokens?.length ? flow.tokens : ['等待', '新的', '对话'];
  list.replaceChildren(...tokens.map((token, index) => {
    const item = document.createElement('span');
    item.className = 'token-chip';
    item.style.setProperty('--token-index', index);
    item.textContent = token;
    return item;
  }));
}

function renderMemorySpace(nodes) {
  const space = document.querySelector('[data-memory-nodes]');
  if (!space) return;
  const source = nodes?.length ? nodes : [{ id: 'empty', label: '等待记忆点', strength: 0.2 }];
  space.replaceChildren(...source.map((node, index) => {
    const point = document.createElement('span');
    point.className = 'memory-node';
    point.style.setProperty('--x', `${18 + (index * 23) % 68}%`);
    point.style.setProperty('--y', `${24 + (index * 31) % 52}%`);
    point.style.setProperty('--scale', String(0.72 + Number(node.strength || 0.2)));
    point.title = node.label || node.id;
    return point;
  }));
}

function renderPersonaModel(model) {
  const list = document.querySelector('[data-persona-traits]');
  if (!list) return;
  const traits = model?.traits || {};
  list.replaceChildren(...Object.entries(traits).flatMap(([name, value]) => {
    const term = document.createElement('dt');
    term.textContent = name;
    const detail = document.createElement('dd');
    detail.textContent = Number(value || 0).toFixed(3);
    return [term, detail];
  }));
}

function renderConfigControls(controls) {
  const list = document.querySelector('[data-config-list]');
  if (!list) return;
  list.replaceChildren(...(controls || []).map((control) => {
    const item = document.createElement('p');
    item.className = 'config-row';
    item.textContent = `${control.title}：${control.enabled ? '开启' : '关闭'}`;
    return item;
  }));
}

async function loadObservatoryStatus() {
  const response = await fetch('/astrbot_plugin_sylanne/observatory-status');
  if (!response.ok) return;
  const payload = await response.json();
  for (const card of payload.cards || []) {
    setText(`[data-summary="${card.id}"]`, card.summary || '暂无摘要。');
  }
  renderTokenFlow(payload.visualization?.token_flow);
  renderMemorySpace(payload.visualization?.memory_nodes);
  renderPersonaModel(payload.visualization?.persona_model);
  renderConfigControls(payload.config_controls);
}

loadObservatoryStatus();
