import { chart } from './charts.js';

const $ = (s, r = document) => r.querySelector(s);
const esc = s => String(s ?? '').replace(/[&<>"']/g, c => ({ '&': '&amp;', '<': '&lt;', '>': '&gt;', '"': '&quot;', "'": '&#39;' }[c]));
const compact = new Intl.NumberFormat('en', { notation: 'compact', maximumFractionDigits: 1 });
const FORMAT = { count: v => compact.format(v), percent: v => v.toFixed(2) + '%', ms: v => Math.round(v) + ' ms' };
const RANGES = { '1h': 'Last hour', '6h': 'Last 6 hours', '24h': 'Last 24 hours', '7d': 'Last 7 days' };
const store = { get: (k, d) => { try { return localStorage.getItem(k) ?? d; } catch { return d; } }, set: (k, v) => { try { localStorage.setItem(k, v); } catch { /* storage unavailable */ } } };

const state = { range: store.get('range', '24h'), auto: false, timer: null };
const view = $('#view');

async function api(path, opts) {
  const res = await fetch(path, opts);
  if (!res.ok) {
    let msg = res.statusText;
    try { msg = (await res.json()).detail || msg; } catch { /* not json */ }
    throw new Error(msg);
  }
  return res.json();
}
function toast(msg) {
  const t = $('#toast'); t.textContent = msg; t.classList.add('show');
  clearTimeout(toast.id); toast.id = setTimeout(() => t.classList.remove('show'), 2200);
}
const fmtClock = ms => new Date(ms).toLocaleTimeString([], { hour: '2-digit', minute: '2-digit' });
const fmtFull = ms => new Date(ms).toLocaleString([], { month: 'short', day: 'numeric', hour: '2-digit', minute: '2-digit' });
const tickFmt = () => state.range === '7d' ? ms => new Date(ms).toLocaleDateString([], { weekday: 'short', day: 'numeric' }) : fmtClock;
const ago = sec => {
  const s = Math.max(0, Date.now() / 1000 - sec);
  return s < 90 ? 'just now' : s < 5400 ? `${Math.round(s / 60)} min ago` : s < 129600 ? `${Math.round(s / 3600)} h ago` : `${Math.round(s / 86400)} d ago`;
};
const rangeButtons = () => `<div class="seg" role="group" aria-label="Time range">${Object.keys(RANGES).map(k => `<button type="button" data-range="${k}" aria-pressed="${k === state.range}">${k}</button>`).join('')}</div>`;

/* ---------- Overview ---------- */
async function overview() {
  view.innerHTML = `
    <div class="page-head">
      <div><h1>Overview</h1><p class="sub" id="ov-sub">Loading…</p></div>
      <div class="tools">
        <label class="check"><input type="checkbox" id="auto"> Refresh every 30s</label>
        ${rangeButtons()}
        <button class="btn" id="refresh" type="button">Refresh</button>
      </div>
    </div>
    <div id="ov"><div class="skeleton"></div><div class="skeleton" style="height:300px"></div></div>`;

  const load = async () => {
    try { paintOverview(await api(`/api/overview?range=${state.range}`)); }
    catch (e) { $('#ov').innerHTML = `<div class="error-box"><b>Couldn't load data.</b> ${esc(e.message)} Check the connection details on the Settings page.</div>`; $('#ov-sub').textContent = ''; }
  };
  view.querySelectorAll('[data-range]').forEach(b => b.addEventListener('click', () => {
    state.range = b.dataset.range; store.set('range', state.range);
    view.querySelectorAll('[data-range]').forEach(x => x.setAttribute('aria-pressed', x === b)); load();
  }));
  $('#refresh').addEventListener('click', load);
  $('#auto').checked = state.auto;
  $('#auto').addEventListener('change', e => { state.auto = e.target.checked; clearInterval(state.timer); if (state.auto) state.timer = setInterval(load, 30000); });
  if (state.auto) state.timer = setInterval(load, 30000);
  load();
}

function paintOverview(d) {
  $('#ov-sub').textContent = `${RANGES[d.range]} · updated ${new Date(d.generated_at).toLocaleTimeString([], { hour: '2-digit', minute: '2-digit' })}${d.mode === 'demo' ? ' · sample data' : ''}`;
  const kpis = d.kpis.map(k => {
    let delta = '<span class="kpi-delta">No previous data</span>';
    if (k.delta !== null) {
      const up = k.delta > 0, big = Math.abs(k.delta) >= 1;
      const tone = !big ? '' : (up === (k.good === 'up')) ? 'good' : 'bad';
      delta = `<span class="kpi-delta ${tone}">${up ? '▲' : '▼'} ${Math.abs(k.delta).toFixed(1)}% vs previous</span>`;
    }
    return `<div class="kpi"><div class="kpi-label">${k.label}</div><div class="kpi-value">${FORMAT[k.unit](k.value)}</div>${delta}</div>`;
  }).join('');

  const maxP = Math.max(1, ...d.endpoints.map(e => e.p95));
  const maxR = Math.max(0.01, ...d.services.map(s => s.error_rate));
  const nAnom = d.logins.anomalies.length;
  const firstAnom = nAnom ? fmtFull(d.logins.t[d.logins.anomalies[0]]) : '';

  $('#ov').innerHTML = `
    <section class="kpis">${kpis}</section>
    <section class="panel" style="margin-bottom:16px">
      <div class="panel-head"><h2>Traffic and errors</h2>
        <div class="legend"><span><i style="background:var(--accent)"></i>Events</span><span><i style="background:var(--bad)"></i>Errors (right axis)</span></div></div>
      <div class="chart" id="c-main"></div>
    </section>
    <div class="grid g-2-1">
      <section class="panel">
        <div class="panel-head"><h2>Failed logins</h2>
          <span class="note">${nAnom ? `<b style="color:var(--bad)">${nAnom} unusual ${nAnom === 1 ? 'interval' : 'intervals'}</b>, first at ${firstAnom}` : 'No unusual activity detected'}</span></div>
        <div class="chart" id="c-login"></div>
      </section>
      <section class="panel">
        <div class="panel-head"><h2>Slowest endpoints</h2><span class="note">p95</span></div>
        <div class="rows">${d.endpoints.map(e => `<div class="row"><span class="name" title="${esc(e.endpoint)}">${esc(e.endpoint)}</span><span class="bar"><i style="width:${e.p95 / maxP * 100}%"></i></span><span class="val">${Math.round(e.p95)} ms</span></div>`).join('') || '<p class="empty">No data</p>'}</div>
      </section>
    </div>
    <div class="grid g-1-2">
      <section class="panel">
        <div class="panel-head"><h2>Error rate by service</h2></div>
        <div class="rows">${d.services.map(s => `<div class="row err"><span class="name">${esc(s.service)}</span><span class="bar"><i style="width:${s.error_rate / maxR * 100}%"></i></span><span class="val">${s.error_rate.toFixed(2)}%</span></div>`).join('') || '<p class="empty">No data</p>'}</div>
      </section>
      <section class="panel">
        <div class="panel-head"><h2>Recent errors</h2><a href="#search" class="note">Open in Search</a></div>
        <div class="table-wrap"><table><thead><tr><th>Time</th><th>Service</th><th>Host</th><th>Message</th></tr></thead><tbody>
          ${d.errors.map(e => `<tr><td class="t">${fmtFull(e.time)}</td><td>${esc(e.service)}</td><td>${esc(e.host)}</td><td class="wrap">${esc(e.message)}</td></tr>`).join('') || '<tr><td colspan="4" class="empty">No errors in this range</td></tr>'}
        </tbody></table></div>
      </section>
    </div>`;

  const tick = tickFmt();
  chart($('#c-main'), {
    labels: d.timeseries.t, tick, tipTitle: fmtFull, height: 280, label: 'Events and errors over time',
    series: [
      { name: 'Events', values: d.timeseries.events, color: 'var(--accent)', type: 'area' },
      { name: 'Errors', values: d.timeseries.errors, color: 'var(--bad)', type: 'line', axis: 'right' },
    ],
  });
  chart($('#c-login'), {
    labels: d.logins.t, tick, tipTitle: fmtFull, height: 220, label: 'Failed logins over time',
    markers: d.logins.anomalies,
    series: [{ name: 'Failed logins', values: d.logins.failures, color: 'var(--accent)', type: 'bar' }],
  });
}

/* ---------- Search ---------- */
const EXAMPLES = [
  ['Recent errors', 'index=app_logs level=ERROR | head 50'],
  ['Errors by service', 'index=app_logs level=ERROR | stats count by service'],
  ['Slow requests', 'index=app_logs endpoint=/api/checkout | head 50'],
  ['Failed logins', 'index=security action=failure | head 50'],
  ['Failures by user', 'index=security action=failure | stats count by user'],
];

function search() {
  const history = JSON.parse(store.get('history', '[]'));
  view.innerHTML = `
    <div class="page-head"><div><h1>Search</h1><p class="sub">Run Splunk searches and export the results.</p></div></div>
    <div class="editor">
      <textarea id="q" spellcheck="false" aria-label="Search query" placeholder="index=app_logs level=ERROR | head 50">${esc(history[0] || EXAMPLES[0][1])}</textarea>
      <div class="editor-foot">
        <div class="tools"><select id="s-range" aria-label="Time range">${Object.entries(RANGES).map(([k, v]) => `<option value="${k}" ${k === state.range ? 'selected' : ''}>${v}</option>`).join('')}</select>
          <span class="note">Ctrl/⌘ + Enter to run</span></div>
        <button class="btn primary" id="run" type="button">Run search</button>
      </div>
    </div>
    <div class="chips">${EXAMPLES.map(([l, q], i) => `<button class="chip" type="button" data-ex="${i}">${l}</button>`).join('')}</div>
    <div id="res"></div>`;

  const q = $('#q'), res = $('#res');
  view.querySelectorAll('[data-ex]').forEach(b => b.addEventListener('click', () => { q.value = EXAMPLES[b.dataset.ex][1]; run(); }));
  q.addEventListener('keydown', e => { if (e.key === 'Enter' && (e.ctrlKey || e.metaKey)) { e.preventDefault(); run(); } });
  $('#run').addEventListener('click', run);

  async function run() {
    const query = q.value.trim(); if (!query) return;
    const btn = $('#run'); btn.disabled = true; btn.textContent = 'Running…';
    try {
      const d = await api('/api/search', { method: 'POST', headers: { 'Content-Type': 'application/json' }, body: JSON.stringify({ query, range: $('#s-range').value }) });
      store.set('history', JSON.stringify([query, ...history.filter(h => h !== query)].slice(0, 8)));
      paintResults(d, res);
    } catch (e) { res.innerHTML = `<div class="error-box">${esc(e.message)}</div>`; }
    btn.disabled = false; btn.textContent = 'Run search';
  }
}

function paintResults(d, el) {
  if (!d.count) { el.innerHTML = `<div class="result-bar"><span>No results.</span></div>${d.note ? `<p class="note">${esc(d.note)}</p>` : ''}`; return; }
  let rows = d.rows.slice(), sort = null;
  const cell = (c, v) => c === 'level' ? `<span class="pill ${esc(v)}">${esc(v)}</span>` : c === '_time' ? esc(new Date(v).toLocaleString([], { month: 'short', day: 'numeric', hour: '2-digit', minute: '2-digit', second: '2-digit' })) : esc(v);
  const render = () => {
    el.innerHTML = `
      <div class="result-bar"><span><b class="num">${d.count.toLocaleString()}</b> ${d.count === 1 ? 'result' : 'results'} · ${d.elapsed_ms} ms</span><button class="btn small" id="csv" type="button">Export CSV</button></div>
      <div class="table-wrap"><table><thead><tr>${d.columns.map(c => `<th class="sortable" data-col="${esc(c)}">${esc(c === '_time' ? 'time' : c)}${sort?.c === c ? (sort.dir > 0 ? ' ▲' : ' ▼') : ''}</th>`).join('')}</tr></thead>
      <tbody>${rows.map(r => `<tr>${d.columns.map(c => `<td class="${c === '_time' ? 't' : c === 'message' ? 'wrap' : ''}">${cell(c, r[c] ?? '')}</td>`).join('')}</tr>`).join('')}</tbody></table></div>
      ${d.note ? `<p class="note" style="margin-top:10px">${esc(d.note)}</p>` : ''}`;
    el.querySelectorAll('th').forEach(th => th.addEventListener('click', () => {
      const c = th.dataset.col, dir = sort?.c === c ? -sort.dir : 1; sort = { c, dir };
      rows.sort((a, b) => { const x = a[c], y = b[c], nx = parseFloat(x), ny = parseFloat(y); return (isNaN(nx) || isNaN(ny) ? String(x ?? '').localeCompare(String(y ?? '')) : nx - ny) * dir; });
      render();
    }));
    $('#csv').addEventListener('click', () => {
      const q = v => `"${String(v ?? '').replace(/"/g, '""')}"`;
      const csv = [d.columns.map(q).join(','), ...rows.map(r => d.columns.map(c => q(r[c])).join(','))].join('\n');
      const a = Object.assign(document.createElement('a'), { href: URL.createObjectURL(new Blob([csv], { type: 'text/csv' })), download: 'splunk-results.csv' });
      a.click(); URL.revokeObjectURL(a.href); toast('CSV exported');
    });
  };
  render();
}

/* ---------- Alerts ---------- */
let alertFilter = 'open';
async function alerts() {
  view.innerHTML = `<div class="page-head"><div><h1>Alerts</h1><p class="sub" id="al-sub"></p></div>
    <div class="seg" id="al-filter" role="group" aria-label="Filter">${['open', 'acknowledged', 'resolved', 'all'].map(s => `<button type="button" data-s="${s}" aria-pressed="${s === alertFilter}">${s[0].toUpperCase() + s.slice(1)}</button>`).join('')}</div></div>
    <div class="list" id="al-list"></div>`;
  view.querySelectorAll('[data-s]').forEach(b => b.addEventListener('click', () => { alertFilter = b.dataset.s; alerts(); }));
  try {
    const d = await api('/api/alerts');
    const items = d.alerts.filter(a => alertFilter === 'all' || a.status === alertFilter);
    $('#al-sub').textContent = `${d.counts.open} open · ${d.counts.acknowledged} acknowledged · ${d.counts.resolved} resolved`;
    $('#al-list').innerHTML = items.map(a => `
      <div class="alert ${a.status === 'resolved' ? 'done' : ''}">
        <span class="pill ${a.severity}">${a.severity}</span>
        <div><h3>${esc(a.name)}</h3><p>${esc(a.summary) || 'No details provided.'}</p>
          <div class="meta">${a.status === 'acknowledged' ? 'Acknowledged · ' : ''}${a.count > 1 ? `Fired ${a.count} times · ` : ''}last seen ${ago(a.last_seen)}${a.link ? ` · <a href="${esc(a.link)}" target="_blank" rel="noopener">View in Splunk</a>` : ''}</div></div>
        <div class="actions">
          ${a.status === 'open' ? `<button class="btn small" data-act="acknowledged" data-id="${a.id}">Acknowledge</button>` : ''}
          ${a.status !== 'resolved' ? `<button class="btn small" data-act="resolved" data-id="${a.id}">Resolve</button>` : `<button class="btn small" data-act="open" data-id="${a.id}">Reopen</button>`}
        </div></div>`).join('') || `<p class="empty">No ${alertFilter === 'all' ? '' : alertFilter + ' '}alerts. Splunk alerts that use the webhook action appear here.</p>`;
    $('#al-list').querySelectorAll('[data-act]').forEach(b => b.addEventListener('click', async () => {
      try { await api(`/api/alerts/${b.dataset.id}/status`, { method: 'POST', headers: { 'Content-Type': 'application/json' }, body: JSON.stringify({ status: b.dataset.act }) }); toast(`Alert ${b.dataset.act === 'open' ? 'reopened' : b.dataset.act}`); alerts(); badge(); }
      catch (e) { toast(e.message); }
    }));
  } catch (e) { $('#al-list').innerHTML = `<div class="error-box">${esc(e.message)}</div>`; }
}
async function badge() {
  try { const { counts } = await api('/api/alerts'); const b = $('#alert-badge'); b.hidden = !counts.open; b.textContent = counts.open; } catch { /* ignore */ }
}

/* ---------- Settings ---------- */
async function settings() {
  view.innerHTML = '<div class="page-head"><div><h1>Settings</h1><p class="sub">Connection status and integration details.</p></div></div><div id="st"></div>';
  let h; try { h = await api('/api/health'); } catch (e) { $('#st').innerHTML = `<div class="error-box">${esc(e.message)}</div>`; return; }
  const s = h.splunk, url = `${location.origin}/api/webhooks/splunk`;
  $('#st').innerHTML = `
    <div class="grid g-2-1"><section class="panel"><div class="panel-head"><h2>Splunk connection</h2></div>
      <dl class="kv"><dt>Mode</dt><dd>${h.mode === 'demo' ? 'Demo (sample data)' : 'Live'}</dd>
        <dt>Status</dt><dd>${s.connected ? '<span class="pill resolved">Connected</span>' : '<span class="pill critical">Not connected</span>'}</dd>
        <dt>Host</dt><dd>${esc(s.host || '—')}</dd><dt>Version</dt><dd>${esc(s.version || '—')}</dd>
        ${s.error ? `<dt>Error</dt><dd>${esc(s.error)}</dd>` : ''}</dl>
      <p class="note" style="margin-top:16px">${h.mode === 'demo' ? 'To use your own data, set SPLUNK_MODE=live and your Splunk host and token in the .env file, then restart.' : 'Connection details come from the .env file.'}</p></section>
      <section class="panel"><div class="panel-head"><h2>Alert webhook</h2></div>
        <p class="note">In Splunk, add a <b>Webhook</b> alert action that posts to this address:</p>
        <pre class="code">${esc(url)}</pre>
        <p class="note" style="margin-top:12px">Try it from a terminal:</p>
        <pre class="code">curl -X POST ${esc(url)} \\
  -H "Content-Type: application/json" \\
  -d '{"search_name":"Test alert","result":{"severity":"high","summary":"Hello"}}'</pre></section></div>`;
}

/* ---------- shell ---------- */
const routes = { overview, search, alerts, settings };
function route() {
  clearInterval(state.timer);
  const name = (location.hash.slice(1) || 'overview'); const fn = routes[name] || overview;
  document.querySelectorAll('.nav a').forEach(a => a.classList.toggle('active', a.dataset.route === (routes[name] ? name : 'overview')));
  fn(); view.focus({ preventScroll: true }); window.scrollTo(0, 0);
}
function setTheme(t) { if (t) document.documentElement.dataset.theme = t; }
setTheme(store.get('theme', ''));
$('#theme').addEventListener('click', () => {
  const dark = document.documentElement.dataset.theme ? document.documentElement.dataset.theme === 'dark' : matchMedia('(prefers-color-scheme: dark)').matches;
  const next = dark ? 'light' : 'dark'; setTheme(next); store.set('theme', next);
  if (location.hash === '' || location.hash === '#overview') route();
});
window.addEventListener('hashchange', route);
api('/api/health').then(h => { const c = $('#conn'); c.classList.add(h.splunk.connected ? 'ok' : 'bad'); $('#conn-text').textContent = h.mode === 'demo' ? 'Demo data' : h.splunk.connected ? 'Splunk connected' : 'Splunk unreachable'; }).catch(() => { $('#conn').classList.add('bad'); $('#conn-text').textContent = 'API unreachable'; });
badge(); route();
