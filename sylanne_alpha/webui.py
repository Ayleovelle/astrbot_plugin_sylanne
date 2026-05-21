"""Sylanne-Embodiment WebUI -- single-page dashboard served as inline HTML."""
from __future__ import annotations

WEBUI_HTML = """\
<!DOCTYPE html>
<html lang="zh-CN">
<head>
<meta charset="UTF-8">
<meta name="viewport" content="width=device-width,initial-scale=1">
<title>Sylanne-Embodiment Dashboard</title>
<style>
*{margin:0;padding:0;box-sizing:border-box}
:root{--bg:#0f1117;--card:#1a1d27;--border:#2a2d3a;--text:#e0e0e0;--muted:#8a8f9d;
--green:#4ade80;--red:#f87171;--blue:#60a5fa;--purple:#a78bfa;--amber:#fbbf24;
--cyan:#22d3ee;--radius:10px}
body{font-family:-apple-system,BlinkMacSystemFont,'Segoe UI',Roboto,sans-serif;
background:var(--bg);color:var(--text);min-height:100vh;padding:16px}
.header{display:flex;align-items:center;justify-content:space-between;margin-bottom:16px;padding:12px 16px;
background:var(--card);border-radius:var(--radius);border:1px solid var(--border)}
.header h1{font-size:1.2rem;font-weight:600}
.header .status{font-size:0.8rem;color:var(--muted)}
.tabs{display:flex;gap:4px;margin-bottom:16px}
.tab-btn{padding:8px 20px;border:1px solid var(--border);border-radius:var(--radius);
background:var(--card);color:var(--muted);cursor:pointer;font-size:0.85rem;transition:all .2s}
.tab-btn.active{background:var(--blue);color:#fff;border-color:var(--blue)}
.tab-btn:hover:not(.active){background:#252836}
.tab-content{display:none}.tab-content.active{display:block}
.grid{display:grid;grid-template-columns:repeat(auto-fit,minmax(320px,1fr));gap:12px}
.card{background:var(--card);border:1px solid var(--border);border-radius:var(--radius);padding:16px}
.card h3{font-size:0.9rem;color:var(--muted);margin-bottom:12px;text-transform:uppercase;letter-spacing:0.5px}
.bar-chart{display:flex;flex-direction:column;gap:6px}
.bar-row{display:flex;align-items:center;gap:8px}
.bar-label{width:100px;font-size:0.75rem;text-align:right;color:var(--muted);flex-shrink:0}
.bar-track{flex:1;height:18px;background:#252836;border-radius:4px;position:relative;overflow:hidden}
.bar-fill{height:100%;border-radius:4px;transition:width .4s ease}
.bar-value{position:absolute;right:4px;top:50%;transform:translateY(-50%);font-size:0.65rem;color:#fff}
.pie-container{display:flex;align-items:center;gap:16px}
.pie-chart{width:100px;height:100px;border-radius:50%;position:relative;flex-shrink:0}
.pie-legend{display:flex;flex-direction:column;gap:4px;font-size:0.75rem}
.pie-legend span{display:flex;align-items:center;gap:6px}
.pie-dot{width:8px;height:8px;border-radius:50%;display:inline-block}
.progress-row{margin-bottom:10px}
.progress-label{display:flex;justify-content:space-between;font-size:0.75rem;margin-bottom:4px}
.progress-track{height:12px;background:#252836;border-radius:6px;overflow:hidden}
.progress-fill{height:100%;border-radius:6px;transition:width .3s ease-out,background-color .5s ease}
.metric-row{display:flex;justify-content:space-between;align-items:center;padding:6px 0;
border-bottom:1px solid var(--border);font-size:0.8rem}
.metric-row:last-child{border-bottom:none}
.metric-value{font-weight:600;font-variant-numeric:tabular-nums;transition:color .5s ease}
.timing-table{width:100%;border-collapse:collapse;font-size:0.75rem}
.timing-table th,.timing-table td{padding:6px 8px;text-align:left;border-bottom:1px solid var(--border)}
.timing-table th{color:var(--muted);font-weight:500}
.timing-table td{font-variant-numeric:tabular-nums}
.memory-list{list-style:none;font-size:0.8rem}
.memory-list li{padding:4px 0;border-bottom:1px solid var(--border);color:var(--muted);
overflow:hidden;text-overflow:ellipsis;white-space:nowrap}
.mode-badge{display:inline-block;padding:2px 8px;border-radius:4px;font-size:0.7rem;
font-weight:600;text-transform:uppercase}
.mode-hint{background:#374151;color:var(--muted)}
.mode-normal{background:#1e3a5f;color:var(--blue)}
.mode-urgent{background:#5b2121;color:var(--red)}
.mode-silent{background:#1a1d27;color:var(--muted);border:1px solid var(--border)}
.save-btn{padding:8px 20px;border:none;border-radius:6px;background:var(--blue);color:#fff;
cursor:pointer;font-size:0.85rem;transition:background .2s}
.save-btn:hover{background:#3b82f6}
.save-btn:disabled{opacity:0.5;cursor:not-allowed}
.setting-item{margin-bottom:14px;padding:10px;background:#252836;border-radius:8px}
.setting-item label{display:block;font-size:0.8rem;margin-bottom:4px;color:var(--text)}
.setting-item .hint{font-size:0.7rem;color:var(--muted);margin-top:2px}
.setting-item input[type="text"],.setting-item input[type="number"]{
width:100%;padding:6px 10px;border:1px solid var(--border);border-radius:6px;
background:var(--bg);color:var(--text);font-size:0.8rem}
.toggle{position:relative;width:40px;height:22px;display:inline-block}
.toggle input{opacity:0;width:0;height:0}
.toggle .slider{position:absolute;inset:0;background:#374151;border-radius:11px;cursor:pointer;transition:background .3s}
.toggle .slider::before{content:'';position:absolute;width:16px;height:16px;left:3px;bottom:3px;
background:#fff;border-radius:50%;transition:transform .3s}
.toggle input:checked+.slider{background:var(--green)}
.toggle input:checked+.slider::before{transform:translateX(18px)}
.tab-content{opacity:0;transition:opacity .2s ease}
.tab-content.active{opacity:1}
.card{opacity:0;transform:translateY(8px);animation:fadeIn .4s ease forwards}
@keyframes fadeIn{to{opacity:1;transform:translateY(0)}}
</style>
</head>
<body>
<div class="header">
<h1>Sylanne-Embodiment Dashboard</h1>
<div class="status">
<span id="refresh-status">加载中...</span>
<span id="session-info"></span>
</div>
</div>
<div class="tabs">
<button class="tab-btn active" data-tab="monitor">监控</button>
<button class="tab-btn" data-tab="settings">设置</button>
</div>
<div id="tab-monitor" class="tab-content active">
<div class="grid" id="dashboard-grid"></div>
</div>
<div id="tab-settings" class="tab-content">
<div class="card" id="settings-panel"><h3>插件设置</h3><div id="settings-form"></div>
<div style="margin-top:16px;display:flex;gap:8px;align-items:center">
<button id="save-settings-btn" class="save-btn">保存设置</button>
<span id="settings-msg" style="font-size:0.8rem;color:var(--muted)"></span>
</div></div>
</div>
<script>
const PLUGIN_NAME = 'astrbot_plugin_sylanne';
const API_BASE = '/' + PLUGIN_NAME;
const API_STATE = API_BASE + '/api/state';
const API_SETTINGS_GET = API_BASE + '/api/settings';
const API_SETTINGS_POST = API_BASE + '/api/settings';
let prevData = null;
let settingsSchema = null;

// Tab switching
document.querySelectorAll('.tab-btn').forEach(btn => {
  btn.addEventListener('click', () => {
    document.querySelectorAll('.tab-btn').forEach(b => b.classList.remove('active'));
    document.querySelectorAll('.tab-content').forEach(c => c.classList.remove('active'));
    btn.classList.add('active');
    document.getElementById('tab-' + btn.dataset.tab).classList.add('active');
  });
});

// Smooth number animation
function animateValue(el, start, end, duration) {
  if (Math.abs(end - start) < 0.001) { el.textContent = fmtNum(end); return; }
  const startTime = performance.now();
  function update(now) {
    const p = Math.min(1, (now - startTime) / duration);
    const val = start + (end - start) * p;
    el.textContent = fmtNum(val);
    if (p < 1) requestAnimationFrame(update);
  }
  requestAnimationFrame(update);
}
function fmtNum(v) { return typeof v === 'number' ? (Math.abs(v) < 10 ? v.toFixed(3) : v.toFixed(0)) : v; }
function fmtNs(ns) { return ns < 1000 ? ns.toFixed(0) + 'ns' : ns < 1e6 ? (ns/1000).toFixed(1) + 'us' : (ns/1e6).toFixed(2) + 'ms'; }

function barColor(v) { return v >= 0 ? 'var(--green)' : 'var(--red)'; }
function barWidth(v) { return Math.min(100, Math.abs(v) * 100) + '%'; }

function renderEmotion(d) {
  const dims = ['warmth','arousal','valence','tension','curiosity','repair_pressure','expression_drive','boundary_firmness'];
  let html = '<div class="bar-chart">';
  for (const k of dims) {
    const v = (d.emotion && d.emotion[k]) || 0;
    html += '<div class="bar-row"><span class="bar-label">' + k + '</span>'
      + '<div class="bar-track"><div class="bar-fill" data-key="emo-'+k+'" style="width:'+barWidth(v)+';background:'+barColor(v)+';transition:width .5s ease,background-color .5s ease"></div>'
      + '<span class="bar-value" data-numkey="emo-'+k+'">'+fmtNum(v)+'</span></div></div>';
  }
  return html + '</div>';
}

function renderRoute(d) {
  const rs = d.route_stats || {};
  const total = (rs.fast||0)+(rs.normal||0)+(rs.full||0)+(rs.skip||0) || 1;
  const colors = {fast:'var(--green)',normal:'var(--blue)',full:'var(--purple)',skip:'var(--muted)'};
  let grad = '', offset = 0;
  for (const k of ['fast','normal','full','skip']) {
    const pct = ((rs[k]||0)/total)*100;
    grad += (colors[k]+' '+offset+'% '+(offset+pct)+'%, ');
    offset += pct;
  }
  grad = grad.slice(0,-2);
  let html = '<div class="pie-container">';
  html += '<div class="pie-chart" style="background:conic-gradient('+grad+')"></div>';
  html += '<div class="pie-legend">';
  for (const k of ['fast','normal','full','skip']) {
    html += '<span><span class="pie-dot" style="background:'+colors[k]+'"></span>'+k+': '+(rs[k]||0)+'</span>';
  }
  html += '</div></div>';
  html += '<div class="metric-row" style="margin-top:10px"><span>surprise</span><span class="metric-value" data-numkey="surprise">'+fmtNum(d.gate?.mean_surprise||0)+'</span></div>';
  return html;
}

function renderMemory(d) {
  const m = d.memory || {};
  let html = '<div class="metric-row"><span>记忆点数量</span><span class="metric-value" data-numkey="mem-size">'+(m.size||0)+'</span></div>';
  html += '<div class="metric-row"><span>连通性</span><span class="metric-value" data-numkey="mem-conn">'+fmtNum(m.connectivity||0)+'</span></div>';
  html += '<div class="metric-row"><span>拓扑空洞</span><span class="metric-value" data-numkey="mem-holes">'+(m.holes_count||0)+'</span></div>';
  if (m.recent_recall && m.recent_recall.length) {
    html += '<h3 style="margin-top:10px;font-size:0.75rem">最近召回</h3><ul class="memory-list">';
    for (const r of m.recent_recall.slice(0,3)) html += '<li>'+r+'</li>';
    html += '</ul>';
  }
  return html;
}

function renderBoundary(d) {
  const b = d.boundary || {};
  let html = '<div class="progress-row"><div class="progress-label"><span>boundary_integrity</span><span data-numkey="b-int">'+fmtNum(b.integrity||0)+'</span></div>';
  html += '<div class="progress-track"><div class="progress-fill" data-key="b-int-bar" style="width:'+((b.integrity||0)*100)+'%;background:var(--green)"></div></div></div>';
  html += '<div class="progress-row"><div class="progress-label"><span>internal_entropy</span><span data-numkey="b-ent">'+fmtNum(b.entropy||0)+'</span></div>';
  html += '<div class="progress-track"><div class="progress-fill" data-key="b-ent-bar" style="width:'+((b.entropy||0)*100)+'%;background:var(--amber)"></div></div></div>';
  html += '<div class="metric-row"><span>phase_transitions</span><span class="metric-value" data-numkey="b-pt">'+(b.phase_transitions||0)+'</span></div>';
  html += '<div class="metric-row"><span>stability</span><span class="metric-value" data-numkey="b-stab">'+fmtNum(b.stability||0)+'</span></div>';
  return html;
}

function renderExpression(d) {
  const e = d.expression || {};
  const ratio = e.ratio || 0;
  const mode = e.mode || 'silent';
  let html = '<div class="progress-row"><div class="progress-label"><span>pressure / threshold</span><span data-numkey="ex-ratio">'+fmtNum(ratio)+'</span></div>';
  html += '<div class="progress-track"><div class="progress-fill" data-key="ex-bar" style="width:'+(ratio*100)+'%;background:'+(ratio>0.8?'var(--red)':'var(--cyan)')+'"></div></div></div>';
  html += '<div class="metric-row"><span>mode</span><span class="mode-badge mode-'+mode+'">'+mode+'</span></div>';
  html += '<div class="metric-row"><span>expression_count</span><span class="metric-value" data-numkey="ex-cnt">'+(e.count||0)+'</span></div>';
  html += '<div class="metric-row"><span>pressure</span><span class="metric-value" data-numkey="ex-p">'+fmtNum(e.pressure||0)+'</span></div>';
  html += '<div class="metric-row"><span>threshold</span><span class="metric-value" data-numkey="ex-t">'+fmtNum(e.threshold||0)+'</span></div>';
  return html;
}

function renderTiming(d) {
  const t = d.timing || {};
  const layers = ['perception','gate','ssm','memory','boundary','expression'];
  let html = '<table class="timing-table"><thead><tr><th>层</th><th>p50</th><th>p99</th></tr></thead><tbody>';
  for (const l of layers) {
    const s = t[l] || {};
    html += '<tr><td>'+l+'</td><td>'+fmtNs(s.p50_ns||0)+'</td><td>'+fmtNs(s.p99_ns||0)+'</td></tr>';
  }
  return html + '</tbody></table>';
}

function renderFeedback(d) {
  const f = d.feedback || {};
  let html = '<div class="metric-row"><span>accepted</span><span class="metric-value" style="color:var(--green)" data-numkey="fb-a">'+(f.accepted||0)+'</span></div>';
  html += '<div class="metric-row"><span>ignored</span><span class="metric-value" style="color:var(--amber)" data-numkey="fb-i">'+(f.ignored||0)+'</span></div>';
  html += '<div class="metric-row"><span>rejected</span><span class="metric-value" style="color:var(--red)" data-numkey="fb-r">'+(f.rejected||0)+'</span></div>';
  return html;
}

function renderDashboard(d) {
  const grid = document.getElementById('dashboard-grid');
  const cards = [
    {title:'情绪状态', html: renderEmotion(d)},
    {title:'计算路由', html: renderRoute(d)},
    {title:'记忆空间', html: renderMemory(d)},
    {title:'自创生边界', html: renderBoundary(d)},
    {title:'表达状态', html: renderExpression(d)},
    {title:'性能', html: renderTiming(d)},
    {title:'反馈统计', html: renderFeedback(d)},
  ];
  grid.innerHTML = cards.map(c => '<div class="card"><h3>'+c.title+'</h3>'+c.html+'</div>').join('');
  if (d.sessions && d.sessions.length) {
    document.getElementById('session-info').textContent = ' | 会话: ' + d.sessions.join(', ');
  }
}

async function fetchState() {
  try {
    const r = await fetch(API_STATE);
    if (!r.ok) throw new Error(r.status);
    const d = await r.json();
    renderDashboard(d);
    document.getElementById('refresh-status').textContent = '已连接 · ' + new Date().toLocaleTimeString();
    prevData = d;
  } catch(e) {
    document.getElementById('refresh-status').textContent = '连接失败: ' + e.message;
  }
}

// Settings
async function loadSettings() {
  try {
    const r = await fetch(API_SETTINGS_GET);
    if (!r.ok) return;
    const d = await r.json();
    settingsSchema = d.schema || {};
    const values = d.values || {};
    const form = document.getElementById('settings-form');
    let html = '';
    for (const [key, meta] of Object.entries(settingsSchema)) {
      const val = values[key] !== undefined ? values[key] : meta.default;
      const desc = meta.description || key;
      const hint = meta.hint || '';
      html += '<div class="setting-item">';
      if (meta.type === 'bool') {
        html += '<label style="display:flex;align-items:center;gap:10px"><span>'+desc+'</span>'
          + '<label class="toggle"><input type="checkbox" data-key="'+key+'" '+(val?'checked':'')+'><span class="slider"></span></label></label>';
      } else if (meta.type === 'int' || meta.type === 'float') {
        html += '<label>'+desc+'</label><input type="number" data-key="'+key+'" value="'+val+'" step="'+(meta.type==='float'?'0.1':'1')+'">';
      } else {
        html += '<label>'+desc+'</label><input type="text" data-key="'+key+'" value="'+(val||'')+'">';
      }
      if (hint) html += '<div class="hint">'+hint+'</div>';
      html += '</div>';
    }
    form.innerHTML = html;
  } catch(e) { console.error('loadSettings', e); }
}

document.getElementById('save-settings-btn').addEventListener('click', async () => {
  const btn = document.getElementById('save-settings-btn');
  const msg = document.getElementById('settings-msg');
  btn.disabled = true;
  const payload = {};
  document.querySelectorAll('#settings-form [data-key]').forEach(el => {
    const key = el.dataset.key;
    const meta = settingsSchema[key] || {};
    if (el.type === 'checkbox') payload[key] = el.checked;
    else if (meta.type === 'int') payload[key] = parseInt(el.value) || 0;
    else if (meta.type === 'float') payload[key] = parseFloat(el.value) || 0.0;
    else payload[key] = el.value;
  });
  try {
    const r = await fetch(API_SETTINGS_POST, {method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify(payload)});
    const d = await r.json();
    if (d.ok) { msg.textContent = '保存成功'; msg.style.color = 'var(--green)'; }
    else { msg.textContent = '保存失败: '+(d.error||'unknown'); msg.style.color = 'var(--red)'; }
  } catch(e) { msg.textContent = '请求失败: '+e.message; msg.style.color = 'var(--red)'; }
  btn.disabled = false;
  setTimeout(() => { msg.textContent = ''; }, 3000);
});

// Init
fetchState();
loadSettings();
setInterval(fetchState, 3000);
</script>
</body>
</html>
"""
