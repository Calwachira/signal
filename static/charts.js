// Dependency-free SVG charts: area / line / bar series, dual axis, hover tooltip.
const compact = new Intl.NumberFormat('en', { notation: 'compact', maximumFractionDigits: 1 });

function niceMax(v) {
  if (v <= 0) return 1;
  const p = 10 ** Math.floor(Math.log10(v)), f = v / p;
  return (f <= 1 ? 1 : f <= 2 ? 2 : f <= 5 ? 5 : 10) * p;
}

export function chart(el, cfg) {
  el._cfg = cfg;
  if (!el._ro) { el._ro = new ResizeObserver(() => draw(el)); el._ro.observe(el); }
  draw(el);
}

function draw(el) {
  const cfg = el._cfg;
  if (!cfg || !el.isConnected) return;
  const n = cfg.labels.length;
  if (!n) { el.innerHTML = '<p class="empty">No data in this range.</p>'; return; }

  const W = Math.max(el.clientWidth, 280), H = cfg.height || 260;
  const hasRight = cfg.series.some(s => s.axis === 'right');
  const m = { l: 44, r: hasRight ? 44 : 8, t: 10, b: 24 };
  const iw = W - m.l - m.r, ih = H - m.t - m.b, band = iw / n;
  const X = i => m.l + band * (i + 0.5);
  const maxOf = ax => niceMax(Math.max(0, ...cfg.series.filter(s => (s.axis || 'left') === ax).flatMap(s => s.values)));
  const mx = { left: maxOf('left'), right: maxOf('right') };
  const Y = (v, ax = 'left') => m.t + ih - (v / mx[ax]) * ih;
  const fmt = cfg.fmt || (v => compact.format(v));

  let out = '';
  for (let k = 0; k <= 4; k++) {
    const y = m.t + (ih * k) / 4;
    out += `<line class="grid-line" x1="${m.l}" x2="${W - m.r}" y1="${y}" y2="${y}"/>`;
    out += `<text class="ax" x="${m.l - 8}" y="${y + 4}" text-anchor="end">${fmt((mx.left * (4 - k)) / 4)}</text>`;
    if (hasRight) out += `<text class="ax" x="${W - m.r + 8}" y="${y + 4}">${fmt((mx.right * (4 - k)) / 4)}</text>`;
  }
  const ticks = Math.min(6, n);
  for (let k = 0; k < ticks; k++) {
    const i = ticks === 1 ? 0 : Math.round((k * (n - 1)) / (ticks - 1));
    const anchor = k === 0 ? 'start' : k === ticks - 1 ? 'end' : 'middle';
    out += `<text class="ax" x="${X(i)}" y="${H - 6}" text-anchor="${anchor}">${cfg.tick(cfg.labels[i])}</text>`;
  }

  cfg.series.forEach(s => {
    const ax = s.axis || 'left', col = s.color;
    if (s.type === 'bar') {
      const w = Math.max(1, band * 0.72);
      s.values.forEach((v, i) => {
        const y = Y(v, ax);
        out += `<rect x="${X(i) - w / 2}" y="${y}" width="${w}" height="${Math.max(0, m.t + ih - y)}" rx="${Math.min(2, w / 2)}" style="fill:${col}"/>`;
      });
    } else {
      const pts = s.values.map((v, i) => `${X(i).toFixed(1)},${Y(v, ax).toFixed(1)}`);
      if (s.type === 'area') {
        out += `<path d="M${X(0)},${m.t + ih} L${pts.join(' L')} L${X(n - 1)},${m.t + ih}Z" style="fill:${col};opacity:.12"/>`;
      }
      out += `<path d="M${pts.join(' L')}" fill="none" style="stroke:${col}" stroke-width="2" stroke-linejoin="round" stroke-linecap="round"/>`;
    }
  });

  (cfg.markers || []).forEach(i => {
    const s = cfg.series[cfg.markerSeries || 0];
    out += `<circle cx="${X(i)}" cy="${Y(s.values[i], s.axis || 'left') - (s.type === 'bar' ? 8 : 0)}" r="4.5" style="fill:var(--bad);stroke:var(--surface)" stroke-width="2"/>`;
  });
  out += `<line class="cursor" y1="${m.t}" y2="${m.t + ih}" x1="0" x2="0" style="display:none"/>`;

  el.innerHTML = `<svg viewBox="0 0 ${W} ${H}" role="img" aria-label="${cfg.label || 'Chart'}">${out}</svg><div class="tip" hidden></div>`;

  const svg = el.querySelector('svg'), tip = el.querySelector('.tip'), cur = svg.querySelector('.cursor');
  svg.addEventListener('pointermove', e => {
    const r = svg.getBoundingClientRect(), px = (e.clientX - r.left) * (W / r.width);
    const i = Math.min(n - 1, Math.max(0, Math.floor((px - m.l) / band)));
    cur.setAttribute('x1', X(i)); cur.setAttribute('x2', X(i)); cur.style.display = '';
    tip.innerHTML = `<b>${cfg.tipTitle ? cfg.tipTitle(cfg.labels[i]) : cfg.labels[i]}</b>` +
      cfg.series.map(s => `<div><span class="sw" style="background:${s.color}"></span>${s.name}: ${(s.format || fmt)(s.values[i])}</div>`).join('');
    tip.hidden = false;
    const x = X(i) * (r.width / W);
    tip.style.left = x > r.width * 0.6 ? `${x - tip.offsetWidth - 12}px` : `${x + 12}px`;
  });
  svg.addEventListener('pointerleave', () => { tip.hidden = true; cur.style.display = 'none'; });
}
