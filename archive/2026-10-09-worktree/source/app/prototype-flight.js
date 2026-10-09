// THROWAWAY: sector-to-sector flight overlay for the offline prototype (cockpit variant).
// Self-contained: no dependencies, no network, no audio, no telemetry. Replaced by the
// production scene router later.
//
// window.playSectorFlight({from:{name,x,y},to:{name,x,y}}) -> Promise<void>
// window.cancelSectorFlight() -> void
// Coordinates are fictional 0-100 values on the conditional schematic (like the cockpit
// sector chart); the drawn sky is a decorative deterministic field, not a real map.

(function () {
'use strict';

const FLIGHT_MS = 1000;   // camera travel time
const SETTLE_MS = 340;    // short hold on arrival, then auto-close
const WORLD_W = 1800;
const WORLD_H = 1200;
const PAD_X = 170;        // keep schematic nodes away from world edges
const PAD_Y = 130;
const TAU = Math.PI * 2;

let dialog = null, canvas = null, ctx = null, els = null;
let active = null;
let rafId = 0;

/* ---------- deterministic field: same route -> same sky ---------- */

function hashSeed(str) {
  let h = 0x811c9dc5;
  for (let i = 0; i < str.length; i++) { h ^= str.charCodeAt(i); h = Math.imul(h, 0x01000193); }
  return h >>> 0;
}
function mulberry32(a) {
  return function () {
    a |= 0; a = (a + 0x6D2B79F5) | 0;
    let t = Math.imul(a ^ (a >>> 15), 1 | a);
    t = (t + Math.imul(t ^ (t >>> 7), 61 | t)) ^ t;
    return ((t ^ (t >>> 14)) >>> 0) / 4294967296;
  };
}

const spriteCache = new Map();
function hexToRgb(hex) {
  const v = parseInt(hex.slice(1), 16);
  return ((v >> 16) & 255) + ',' + ((v >> 8) & 255) + ',' + (v & 255);
}
function nebulaSprite(color) {
  if (spriteCache.has(color)) return spriteCache.get(color);
  const s = document.createElement('canvas');
  s.width = s.height = 160;
  const g = s.getContext('2d');
  const rgb = hexToRgb(color);
  const grad = g.createRadialGradient(80, 80, 4, 80, 80, 80);
  grad.addColorStop(0, 'rgba(' + rgb + ',.85)');
  grad.addColorStop(.45, 'rgba(' + rgb + ',.38)');
  grad.addColorStop(1, 'rgba(' + rgb + ',0)');
  g.fillStyle = grad;
  g.fillRect(0, 0, 160, 160);
  spriteCache.set(color, s);
  return s;
}

function buildField(seedKey) {
  const rnd = mulberry32(hashSeed(seedKey));
  const field = { stars: [], nebulas: [], lines: [] };
  const layers = [
    { depth: .34, count: 480, rMin: .5, rMax: 1.2, aMin: .4, aMax: .75 },
    { depth: .62, count: 280, rMin: .7, rMax: 1.7, aMin: .5, aMax: .9 },
    { depth: 1, count: 120, rMin: 1, rMax: 2.3, aMin: .65, aMax: 1 }
  ];
  const pickColor = () => {
    const v = rnd();
    return v < .42 ? '#dfe9ff' : v < .68 ? '#f6f8ff' : v < .85 ? '#ffeccf' : '#cfeee6';
  };
  const spanX = WORLD_W + 1800, spanY = WORLD_H + 1400;
  for (const layer of layers) {
    for (let i = 0; i < layer.count; i++) {
      field.stars.push({
        x: -900 + rnd() * spanX,
        y: -700 + rnd() * spanY,
        r: layer.rMin + rnd() * (layer.rMax - layer.rMin),
        a: layer.aMin + rnd() * (layer.aMax - layer.aMin),
        depth: layer.depth,
        color: pickColor(),
        flare: layer.depth === 1 && rnd() < .16,
        tw: layer.depth > .5 && rnd() < .3, // slow subtle breathing, no flashes
        twS: .7 + rnd() * 1.1,
        twP: rnd() * TAU,
        twA: .12
      });
    }
  }
  const palette = ['#286e86', '#475394', '#684a92', '#8b593c', '#2f7d73'];
  for (let i = 0; i < 5; i++) {
    field.nebulas.push({
      x: rnd() * WORLD_W,
      y: rnd() * WORLD_H,
      r: 260 + rnd() * 360,
      color: palette[i % palette.length],
      alpha: .4 + rnd() * .2,
      depth: .2 + rnd() * .22,
      sprite: nebulaSprite(palette[i % palette.length])
    });
  }
  for (let i = 0; i < 4; i++) {
    const pts = [];
    let px = -300 + rnd() * (WORLD_W + 600), py = -200 + rnd() * (WORLD_H + 400);
    pts.push([px, py]);
    const n = 3 + ((rnd() * 3) | 0);
    for (let k = 1; k < n; k++) { px += (rnd() - .5) * 280; py += (rnd() - .5) * 240; pts.push([px, py]); }
    field.lines.push(pts);
  }
  return field;
}

/* ---------- dialog (created once) ---------- */

function ensureDialog() {
  if (dialog) return;
  dialog = document.createElement('dialog');
  dialog.className = 'sky-flight';

  canvas = document.createElement('canvas');
  canvas.className = 'sky-flight-canvas';
  ctx = canvas.getContext('2d');

  const vignette = document.createElement('div');
  vignette.className = 'sky-flight-vignette';
  vignette.setAttribute('aria-hidden', 'true');

  const top = document.createElement('header');
  top.className = 'sky-flight-top';
  const kicker = document.createElement('span');
  kicker.className = 'sky-flight-kicker';
  kicker.textContent = 'Условная карта учебных участков';
  const note = document.createElement('span');
  note.className = 'sky-flight-note';
  note.textContent = 'Учебные синтетические данные';
  top.append(kicker, note);

  const bottom = document.createElement('div');
  bottom.className = 'sky-flight-bottom';
  const wrap = document.createElement('div');
  wrap.className = 'sky-flight-route-wrap';
  const route = document.createElement('p');
  route.className = 'sky-flight-route';
  const fromEl = document.createElement('span');
  fromEl.className = 'sky-flight-name sky-flight-from';
  const arrow = document.createElement('span');
  arrow.className = 'sky-flight-arrow';
  arrow.setAttribute('aria-hidden', 'true');
  arrow.textContent = '→';
  const toEl = document.createElement('span');
  toEl.className = 'sky-flight-name sky-flight-to';
  route.append(fromEl, arrow, toEl);
  const caption = document.createElement('p');
  caption.className = 'sky-flight-caption';
  caption.textContent = 'Позиции участков условные: это схема игры, а не реальные координаты неба.';
  wrap.append(route, caption);
  const skip = document.createElement('button');
  skip.type = 'button';
  skip.className = 'sky-flight-skip';
  skip.textContent = 'Перейти сразу';
  bottom.append(wrap, skip);

  dialog.append(canvas, vignette, top, bottom);
  document.body.appendChild(dialog);
  els = { from: fromEl, to: toEl, skip };

  skip.addEventListener('click', finishFlight);
  dialog.addEventListener('keydown', onDialogKeydown);
  dialog.addEventListener('close', () => {
    // A queued close from a cancelled flight must not stop its replacement.
    if (!dialog.open) finishFlight();
  });
}

// Keep the flight isolated from the global prototype shortcuts (arrow keys switch variants).
function onDialogKeydown(e) {
  if (e.key === 'ArrowLeft' || e.key === 'ArrowRight' || e.key === 'ArrowUp' || e.key === 'ArrowDown') {
    e.preventDefault();
    e.stopPropagation();
    return;
  }
  if (e.key === 'Escape') e.stopPropagation(); // native modal cancel still applies
}

/* ---------- helpers ---------- */

function normalize(p) {
  const x = Number(p && p.x), y = Number(p && p.y);
  const name = String((p && p.name) || '').trim().slice(0, 48) || 'Учебный участок';
  return {
    name,
    x: Number.isFinite(x) ? Math.min(100, Math.max(0, x)) : 50,
    y: Number.isFinite(y) ? Math.min(100, Math.max(0, y)) : 50
  };
}
function worldPoint(p) {
  return {
    x: PAD_X + (p.x / 100) * (WORLD_W - 2 * PAD_X),
    y: PAD_Y + (p.y / 100) * (WORLD_H - 2 * PAD_Y)
  };
}
function easeInOut(t) { return t < .5 ? 4 * t * t * t : 1 - Math.pow(-2 * t + 2, 3) / 2; }
function easeOut(t) { return 1 - Math.pow(1 - t, 3); }
function smooth(v, a, b) { const t = Math.min(1, Math.max(0, (v - a) / (b - a))); return t * t * (3 - 2 * t); }

function resizeCanvas() {
  if (!dialog || !active) return;
  const dpr = Math.min(window.devicePixelRatio || 1, 2);
  const w = dialog.clientWidth, h = dialog.clientHeight;
  active.w = w; active.h = h; active.dpr = dpr;
  canvas.width = Math.max(1, Math.round(w * dpr));
  canvas.height = Math.max(1, Math.round(h * dpr));
}

/* ---------- rendering ---------- */

function renderFrame(p, q, now) {
  const st = active;
  if (!st || !ctx) return;
  const w = st.w, h = st.h;
  ctx.setTransform(st.dpr, 0, 0, st.dpr, 0, 0);
  ctx.fillStyle = '#050e1a';
  ctx.fillRect(0, 0, w, h);

  const camX = st.a.x + (st.b.x - st.a.x) * p;
  const camY = st.a.y + (st.b.y - st.a.y) * p;
  const zoom = st.z0 + (st.z1 - st.z0) * p;
  const cx = w / 2, cy = h / 2;
  const sk = Math.sqrt(zoom); // stars shrink gently on zoom-out, never vanish
  const f = st.field;

  // nebulosity (soft additive blobs)
  ctx.globalCompositeOperation = 'screen';
  for (const n of f.nebulas) {
    const sx = cx + (n.x - camX * n.depth) * zoom;
    const sy = cy + (n.y - camY * n.depth) * zoom;
    const sr = n.r * zoom;
    if (sx + sr < -40 || sx - sr > w + 40 || sy + sr < -40 || sy - sr > h + 40) continue;
    ctx.globalAlpha = n.alpha;
    ctx.drawImage(n.sprite, sx - sr, sy - sr, sr * 2, sr * 2);
  }
  ctx.globalCompositeOperation = 'source-over';
  ctx.globalAlpha = 1;

  // layered stars with parallax
  for (const s of f.stars) {
    const sx = cx + (s.x - camX * s.depth) * zoom;
    const sy = cy + (s.y - camY * s.depth) * zoom;
    if (sx < -6 || sx > w + 6 || sy < -6 || sy > h + 6) continue;
    const tw = s.tw ? 1 - s.twA + s.twA * (.5 + .5 * Math.sin(s.twS * now * .001 + s.twP)) : 1;
    const r = s.r * sk;
    ctx.globalAlpha = Math.min(1, s.a * tw);
    ctx.fillStyle = s.color;
    ctx.beginPath();
    ctx.arc(sx, sy, r, 0, TAU);
    ctx.fill();
    if (s.flare) {
      ctx.globalAlpha = Math.min(1, s.a * tw * .32);
      ctx.strokeStyle = s.color;
      ctx.lineWidth = .9;
      const L = r * 6.5;
      ctx.beginPath();
      ctx.moveTo(sx - L, sy); ctx.lineTo(sx + L, sy);
      ctx.moveTo(sx, sy - L); ctx.lineTo(sx, sy + L);
      ctx.stroke();
    }
  }
  ctx.globalAlpha = 1;

  drawMapLayer(st, camX, camY, zoom, cx, cy, p, q, now, w, h);
}

function drawMapLayer(st, camX, camY, zoom, cx, cy, p, q, now, w, h) {
  const sx = x => cx + (x - camX) * zoom;
  const sy = y => cy + (y - camY) * zoom;

  // faint schematic grid: this is a map, not the sky
  const step = 150;
  ctx.strokeStyle = 'rgba(150,203,216,.055)';
  ctx.lineWidth = 1;
  ctx.beginPath();
  for (let gx = Math.ceil((camX - cx / zoom) / step) * step; gx <= camX + (w - cx) / zoom; gx += step) {
    const X = sx(gx); ctx.moveTo(X, 0); ctx.lineTo(X, h);
  }
  for (let gy = Math.ceil((camY - cy / zoom) / step) * step; gy <= camY + (h - cy) / zoom; gy += step) {
    const Y = sy(gy); ctx.moveTo(0, Y); ctx.lineTo(w, Y);
  }
  ctx.stroke();

  // deterministic constellation hints
  ctx.strokeStyle = 'rgba(190,216,228,.11)';
  ctx.lineWidth = 1;
  ctx.beginPath();
  for (const line of st.field.lines) {
    ctx.moveTo(sx(line[0][0]), sy(line[0][1]));
    for (let i = 1; i < line.length; i++) ctx.lineTo(sx(line[i][0]), sy(line[i][1]));
  }
  ctx.stroke();

  // dashed route from source to destination, slowly crawling forward
  const ax = sx(st.a.x), ay = sy(st.a.y), bx = sx(st.b.x), by = sy(st.b.y);
  ctx.setLineDash([9, 9]);
  ctx.lineDashOffset = -(now * .012) % 18;
  ctx.strokeStyle = 'rgba(121,224,194,.42)';
  ctx.lineWidth = 1.5;
  ctx.beginPath();
  ctx.moveTo(ax, ay);
  ctx.lineTo(bx, by);
  ctx.stroke();
  ctx.setLineDash([]);
  ctx.lineDashOffset = 0;

  const fromA = Math.max(.55, 1 - smooth(p, .2, .55));
  drawMarker(ax, ay, '#e3bc73', fromA, 0);
  drawLabel(ax, ay, st.from.name, '#e3bc73', fromA, w, h);
  const toA = .55 + .45 * smooth(p, .42, .8);
  drawMarker(bx, by, '#79e0c2', toA, q); // q > 0 only during the arrival hold
  drawLabel(bx, by, st.to.name, '#79e0c2', toA, w, h);
}

function drawMarker(x, y, color, alpha, q) {
  if (alpha <= .02) return;
  ctx.globalAlpha = alpha;
  ctx.strokeStyle = color;
  ctx.lineWidth = 1.6;
  ctx.beginPath(); ctx.arc(x, y, 9, 0, TAU); ctx.stroke();
  ctx.fillStyle = color;
  ctx.beginPath(); ctx.arc(x, y, 3, 0, TAU); ctx.fill();
  if (q > 0) { // single gentle arrival ping
    ctx.globalAlpha = alpha * (1 - q) * .6;
    ctx.lineWidth = 2;
    ctx.beginPath(); ctx.arc(x, y, 9 + 46 * easeOut(q), 0, TAU); ctx.stroke();
  }
  ctx.globalAlpha = 1;
}

function drawLabel(mx, my, text, color, alpha, w, h) {
  if (alpha <= .02 || !text) return;
  ctx.font = '600 13px system-ui,"Segoe UI",sans-serif';
  const tw = ctx.measureText(text).width;
  const bw = Math.ceil(tw) + 20, bh = 26;
  let bx = mx - bw / 2;
  bx = Math.max(10, Math.min(w - bw - 10, bx));
  let by = my - 46;
  if (by < 52) by = my + 22; // stay under the top bar
  if (by > h - 34) by = h - 34;
  ctx.globalAlpha = alpha * .92;
  ctx.fillStyle = 'rgba(6,15,24,.84)';
  pillPath(bx, by, bw, bh, 7); ctx.fill();
  ctx.globalAlpha = alpha * .65;
  ctx.strokeStyle = color;
  ctx.lineWidth = 1;
  pillPath(bx, by, bw, bh, 7); ctx.stroke();
  ctx.globalAlpha = alpha;
  ctx.fillStyle = '#edf4f8';
  ctx.textAlign = 'center';
  ctx.textBaseline = 'middle';
  ctx.fillText(text, bx + bw / 2, by + bh / 2 + .5);
  ctx.textAlign = 'start';
  ctx.textBaseline = 'alphabetic';
  ctx.globalAlpha = 1;
}

function pillPath(x, y, w, h, r) {
  ctx.beginPath();
  if (ctx.roundRect) { ctx.roundRect(x, y, w, h, r); return; }
  ctx.moveTo(x + r, y);
  ctx.arcTo(x + w, y, x + w, y + h, r);
  ctx.arcTo(x + w, y + h, x, y + h, r);
  ctx.arcTo(x, y + h, x, y, r);
  ctx.arcTo(x, y, x + w, y, r);
  ctx.closePath();
}

/* ---------- lifecycle ---------- */

function frame(now) {
  rafId = 0;
  if (!active) return;
  if (active.t0 === null) active.t0 = now;
  const el = now - active.t0;
  const t = Math.min(1, el / FLIGHT_MS);
  const q = Math.min(1, Math.max(0, (el - FLIGHT_MS) / SETTLE_MS));
  renderFrame(easeInOut(t), q, now);
  if (el < FLIGHT_MS + SETTLE_MS) {
    rafId = requestAnimationFrame(frame);
  } else {
    finishFlight(); // natural end: auto-close
  }
}

function onVisibility() {
  if (document.hidden) finishFlight();
}

// Idempotent: closes the dialog, stops rAF, resolves the promise exactly once.
function finishFlight() {
  const st = active;
  active = null;
  if (rafId) { cancelAnimationFrame(rafId); rafId = 0; }
  window.removeEventListener('resize', resizeCanvas);
  document.removeEventListener('visibilitychange', onVisibility);
  if (dialog && dialog.open) dialog.close();
  if (st && st.resolve) st.resolve();
}

function playSectorFlight(route) {
  finishFlight(); // a new call cancels the previous one cleanly; its promise resolves
  if (matchMedia('(prefers-reduced-motion: reduce)').matches || document.hidden) {
    return Promise.resolve(); // pass through without delaying gameplay
  }
  ensureDialog();
  const from = normalize(route && route.from);
  const to = normalize(route && route.to);
  dialog.setAttribute('aria-label', 'Переход между участками: ' + from.name + ' — ' + to.name);
  els.from.textContent = from.name;
  els.to.textContent = to.name;

  const field = buildField(from.name + '|' + from.x + ',' + from.y + '>' + to.name + '|' + to.x + ',' + to.y);
  let resolvePromise;
  const promise = new Promise(resolve => { resolvePromise = resolve; });
  active = {
    from, to, field,
    a: worldPoint(from),
    b: worldPoint(to),
    z0: 1.35, z1: .95,
    resolve: resolvePromise,
    t0: null, w: 0, h: 0, dpr: 1
  };
  dialog.showModal();
  resizeCanvas();
  const vfit = Math.min(1, Math.max(.42, active.w / 1250)); // narrower screens see a wider world
  active.z0 = 1.35 * vfit;
  active.z1 = .95 * vfit;

  window.addEventListener('resize', resizeCanvas);
  document.addEventListener('visibilitychange', onVisibility);
  renderFrame(0, 0, performance.now()); // paint before the first rAF: no blank first frame
  rafId = requestAnimationFrame(frame);
  return promise;
}

window.playSectorFlight = playSectorFlight;
window.cancelSectorFlight = finishFlight;
})();
