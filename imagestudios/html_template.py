"""Self-contained interactive viewer page used by the HTML output.

Placeholders: __TITLE__, __META__ (JSON), __CHUNKS__ (one <script> per position
holding base64 of zlib-compressed raw pixel data, ordered T, Z, C, Y, X).
"""

HEAD = r"""<!doctype html>
<html lang="en"><head><meta charset="utf-8">
<meta name="viewport" content="width=device-width,initial-scale=1">
<meta name="generator" content="ImageStudios">
<title>__TITLE__</title>
<style>
:root{--bg:#15161b;--panel:#1f2128;--card:#191a1f;--line:#30333c;--text:#e6e9f2;--muted:#8a90a0;--accent:#6c8cff}
body.light{--bg:#f3f4f7;--panel:#ffffff;--card:#f7f8fb;--line:#d9dce3;--text:#1d2129;--muted:#5f6675}
body.light button,body.light select,body.light input{background:#fff;border-color:#c9cdd6;color:var(--text)}
body.light button:hover{background:#eef0f5}
body.light #view,body.light #xz,body.light #yz{background:#e9ebf0}
body.light .hist{background:#eceef3}
#caption{margin-left:4px}
*{box-sizing:border-box}
html,body{height:100%}
body{margin:0;background:var(--bg);color:var(--text);font:13px/1.4 "Segoe UI",system-ui,-apple-system,sans-serif;display:flex;flex-direction:column;overflow:hidden}
header{display:flex;align-items:center;gap:12px;padding:8px 14px;background:var(--panel);border-bottom:1px solid var(--line)}
header h1{font-size:15px;margin:0;font-weight:600;white-space:nowrap;overflow:hidden;text-overflow:ellipsis}
.sub{color:var(--muted)}
.sp{flex:1}
button,select,input{font:inherit;color:var(--text);background:#2a2d36;border:1px solid #3a3d47;border-radius:6px;padding:4px 8px}
button{cursor:pointer}
button:hover{background:#343844}
button.on{background:var(--accent);border-color:var(--accent);color:#fff}
input[type=range]{padding:0;accent-color:var(--accent)}
input[type=checkbox]{accent-color:var(--accent)}
main{flex:1;display:flex;min-height:0}
#gallery{width:168px;flex:none;overflow-y:auto;background:var(--panel);border-right:1px solid var(--line);padding:6px}
#gallery .th{display:block;width:100%;margin:0 0 6px;padding:3px;border:2px solid transparent;border-radius:8px;background:var(--card);cursor:pointer;color:var(--muted);font-size:11px;text-align:center}
#gallery .th img{width:100%;display:block;border-radius:5px;image-rendering:pixelated}
#gallery .th.sel{border-color:var(--accent);color:var(--text)}
#center{flex:1;display:flex;flex-direction:column;min-width:0}
#stage{flex:1;display:flex;min-height:0;position:relative}
#mainCol{flex:1;display:flex;flex-direction:column;min-width:0}
#viewWrap{flex:1;position:relative;min-height:0}
#view{position:absolute;inset:0;width:100%;height:100%;display:block;background:#0d0e11;cursor:grab}
#view.ruler{cursor:crosshair}
#xz{display:none;width:100%;height:150px;background:#0d0e11;border-top:1px solid var(--line);cursor:crosshair}
#yz{display:none;width:150px;height:100%;background:#0d0e11;border-left:1px solid var(--line);cursor:crosshair}
#mini{position:absolute;right:10px;top:10px;border:1px solid #666;background:#000;display:none;cursor:pointer;box-shadow:0 2px 10px #000a}
#controls{background:var(--panel);border-top:1px solid var(--line);padding:8px 12px;display:flex;flex-direction:column;gap:6px}
.ax{display:flex;align-items:center;gap:10px}
.ax label{width:92px;color:var(--muted)}
.ax input[type=range]{flex:1}
.ax .v{min-width:190px;text-align:right;font-variant-numeric:tabular-nums}
.row{display:flex;align-items:center;gap:8px;flex-wrap:wrap}
.gapx{width:12px}
#status{color:var(--muted);font-variant-numeric:tabular-nums;min-height:18px;white-space:nowrap;overflow:hidden;text-overflow:ellipsis}
#side{width:310px;flex:none;overflow-y:auto;background:var(--panel);border-left:1px solid var(--line);padding:10px}
.card{background:var(--card);border:1px solid var(--line);border-radius:10px;padding:8px;margin-bottom:10px}
.card h3{margin:0 0 6px;font-size:13px;display:flex;align-items:center;gap:6px}
.card h3 .nm{flex:1}
.hist{width:100%;height:96px;display:block;background:#0f1013;border-radius:6px;cursor:ew-resize}
.lutrow{display:flex;gap:6px;align-items:center;margin-top:6px}
.lutrow input[type=number]{width:84px}
.lutrow input[type=range]{flex:1}
.lutrow .lab{color:var(--muted);width:44px}
.lutrow.stats{color:var(--muted);font-size:11px;font-variant-numeric:tabular-nums}
.sw{width:26px;height:24px;padding:0;border-radius:5px}
h2{font-size:11px;text-transform:uppercase;letter-spacing:.07em;color:var(--muted);margin:10px 0 6px}
.chk{display:flex;align-items:center;gap:6px;margin:3px 0;cursor:pointer}
#modal{position:fixed;inset:0;background:#000b;display:none;align-items:center;justify-content:center;z-index:10}
#modal .box{background:var(--panel);border:1px solid var(--line);border-radius:12px;padding:16px 18px;max-width:760px;max-height:80vh;overflow:auto}
#modal pre{white-space:pre-wrap;font:12px/1.5 Consolas,monospace;margin:0}
#loading{position:absolute;left:50%;top:50%;transform:translate(-50%,-50%);color:var(--muted);display:none}
#popbar{position:absolute;display:none;align-items:center;gap:6px;height:34px;z-index:3;white-space:nowrap;overflow:hidden}
#popbar .crumb{background:none;border:none;color:var(--muted);padding:2px 4px;font-weight:600}
#popbar .crumb:hover{color:var(--text);text-decoration:underline}
#popbar .crumb.cur{color:var(--text);cursor:default;text-decoration:none}
#popbar .sep{color:var(--muted)}
#popbar .hint{color:var(--muted);font-size:11px;margin-left:6px}
#pager{display:none;align-items:center;gap:6px}
#pager .t{color:var(--muted);font-variant-numeric:tabular-nums;min-width:150px;text-align:center}
kbd{background:#2a2d36;border:1px solid #3a3d47;border-radius:4px;padding:0 4px;font-size:11px}
</style></head>
<body>
<header><h1 id="title"></h1><span class="sub" id="caption"></span><span class="sub" id="subtitle"></span><span class="sp"></span>
<button id="btnKeys" title="Keyboard shortcuts">?</button>
<button id="btnMeta">Metadata</button>
<button id="btnSnap" title="Save the current view as a PNG image">Snapshot</button></header>
<main>
<nav id="gallery"></nav>
<section id="center">
 <div id="stage">
  <div id="mainCol">
   <div id="viewWrap"><canvas id="view"></canvas><canvas id="mini" width="170" height="170"></canvas><div id="loading">Loading…</div><div id="popbar"></div></div>
   <canvas id="xz"></canvas>
  </div>
  <canvas id="yz"></canvas>
 </div>
 <div id="controls">
  <div id="axes"></div>
  <div class="row" id="ctlRow">
   <span id="grpPlay" class="row">
   <button id="play" title="Play / pause (space)">&#9654; Play</button>
   <select id="playAxis" title="Axis to play through"></select>
   <label>fps <input id="fps" type="number" min="0.5" max="120" step="0.5" style="width:66px"></label>
   <label class="chk"><input type="checkbox" id="loop" checked>loop</label>
   <span class="gapx"></span></span>
   <span id="grpProj" class="row">
   <label>Show <select id="proj"><option value="frame">single frame</option><option value="mean">mean projection</option><option value="max">max projection</option><option value="min">min projection</option></select></label>
   <label id="projOverWrap">over <select id="projAxis"></select></label>
   <span class="gapx"></span></span>
   <span id="pager"><button id="pgPrev" title="Previous page (PgUp)">&#9664;</button><span class="t" id="pgTxt"></span><button id="pgNext" title="Next page (PgDn)">&#9654;</button><span class="gapx"></span></span>
   <button id="btnRuler" title="Drag on the image to measure a distance (Esc clears)">Ruler</button>
   <button id="btnOrtho" title="XZ / YZ side views. Click the image to move the crosshair.">Ortho views</button>
   <button id="btnFit" title="Fit to window (double-click or 0)">Fit</button>
  </div>
  <div id="status">&nbsp;</div>
 </div>
</section>
<aside id="side">
 <h2 id="hLut">Channels &amp; LUT</h2><div id="luts"></div>
 <h2 id="hOvl">Overlays</h2>
 <div class="card" id="ovl"></div>
</aside>
</main>
<div id="modal"><div class="box"><pre id="modalText"></pre><div style="text-align:right;margin-top:10px"><button id="modalClose">Close</button></div></div></div>
<script id="meta" type="application/json">__META__</script>
"""

TAIL = r"""
<script>
'use strict';
const D = JSON.parse(document.getElementById('meta').textContent);
const W = D.width, H = D.height, NP = W * H;
const AX = D.axes;                       // {T:{n,label,names[]}, Z:{...}, M:{...}}
const NT = AX.T ? AX.T.n : 1, NZ = AX.Z ? AX.Z.n : 1, NM = AX.M ? AX.M.n : 1, NC = D.channels.length;
const TA = D.dtype === 'u8' ? Uint8Array : (D.dtype === 'u16' ? Uint16Array : Float32Array);
const $ = id => document.getElementById(id);
const st = {m: 0, t: 0, z: 0, proj: 'frame', projAxis: NZ > 1 ? 'Z' : 'T', zoom: 1, vx: W / 2, vy: H / 2,
            playing: false, rulerOn: false, ruler: null, ortho: false, cx: W >> 1, cy: H >> 1, hover: null,
            };
const ch = D.channels.map(c => ({...c, gamma: 1, preset: c.preset || 'color', visible: true, hist: null}));
const UI = Object.assign({playback: true, gallery: true, lut: true, projections: true, ortho: true, zoom: true,
  inspector: true, ruler: true, snapshot: true, metadata: true, overlayToggles: true,
  autoplay: false, theme: 'dark'}, D.ui || {});
const ovl = Object.assign({scalebar: true, time: true, z: true, names: true, position: true}, D.overlays || {});
const cache = new Map();
let data = null, dirty = true, tiles = [], tileCv = [], lastLayout = null, tilesSig = '';
// Panel layout is fixed in ImageStudios (same settings as an image panel):
// axis C/T/Z/M, images per row or column, merged tile, spacing and background.
const PANEL = Object.assign({axis: '', fill: 'row', count: 0, merge: true, gap: 6, bg: 'white'}, D.panel || {});
st.panelAxis = PANEL.axis;
const LUTVIEW = D.lutView === 'beside' ? 'beside' : 'selected';
st.sel = 0;                 // tile whose frame the LUT histograms describe
if (st.panelAxis === 'C' ? NC < 2 : (st.panelAxis && !({T: NT, Z: NZ, M: NM}[st.panelAxis] > 1))) st.panelAxis = '';
const BASE_AXIS = st.panelAxis;            // the panel the page opens on
const GRIDS = PANEL.grids || {};           // tiles per page for each axis: [rows, cols], 0 = auto
st.page = 0;
let pop = null;        // tile opened above the panel: {mode: 'single' | 'panel', axis, c, saved}
let baseSnap = null;   // picture of the panel underneath the popup
const AXIS_NAME = {M: 'Positions', T: 'Time points', Z: 'Z-slices', C: 'Channels'};

// ---------- data ----------
async function b64ToBytes(s) {
  try { const r = await fetch('data:application/octet-stream;base64,' + s); return new Uint8Array(await r.arrayBuffer()); }
  catch (e) { const b = atob(s); const u = new Uint8Array(b.length); for (let i = 0; i < b.length; i++) u[i] = b.charCodeAt(i); return u; }
}
async function inflate(u8) {
  const s = new Blob([u8]).stream().pipeThrough(new DecompressionStream('deflate'));
  return new Uint8Array(await new Response(s).arrayBuffer());
}
async function loadPos(m, quiet) {
  if (cache.has(m)) return cache.get(m);
  $('loading').style.display = 'block';
  const el = document.getElementById('chunk-' + m);
  if (!el) { $('loading').style.display = 'none'; if (!quiet) modal('This preview only contains the position selected in ImageStudios. The exported page contains all positions.'); return null; }
  const raw = await inflate(await b64ToBytes(el.textContent.trim()));
  const arr = new TA(raw.buffer, 0, raw.byteLength / TA.BYTES_PER_ELEMENT);
  cache.set(m, arr);
  const keep = Math.max(4, (BASE_AXIS === 'M' ? pageGeom('M').per : 0) + 2);
  while (cache.size > keep) { const k = cache.keys().next().value; if (k === m) break; cache.delete(k); }
  $('loading').style.display = 'none';
  return arr;
}
const planeIn = (arr, t, z, c) => arr.subarray(((t * NZ + z) * NC + c) * NP, ((t * NZ + z) * NC + c + 1) * NP);
const planeAt = (t, z, c) => planeIn(data, t, z, c);
const projCache = new Map();
function chanPlane(c, f) {
  // f = {t, z, m, arr}: a specific frame (panel tile); default = the slider position
  const t = f ? f.t : st.t, z = f ? f.z : st.z, m = f ? f.m : st.m, arr = f ? f.arr : data;
  if (st.proj === 'frame') return planeIn(arr, t, z, c);
  const over = st.projAxis, n = over === 'T' ? NT : NZ;
  const key = [m, st.proj, over, c, over === 'T' ? z : t].join('|');
  if (projCache.has(key)) return projCache.get(key);
  const out = new Float32Array(NP);
  if (st.proj === 'min') out.fill(Infinity); else if (st.proj === 'max') out.fill(-Infinity);
  for (let k = 0; k < n; k++) {
    const p = over === 'T' ? planeIn(arr, k, z, c) : planeIn(arr, t, k, c);
    if (st.proj === 'mean') for (let i = 0; i < NP; i++) out[i] += p[i];
    else if (st.proj === 'max') for (let i = 0; i < NP; i++) { if (p[i] > out[i]) out[i] = p[i]; }
    else for (let i = 0; i < NP; i++) { if (p[i] < out[i]) out[i] = p[i]; }
  }
  if (st.proj === 'mean') for (let i = 0; i < NP; i++) out[i] /= n;
  if (projCache.size > 64) projCache.delete(projCache.keys().next().value);
  projCache.set(key, out);
  return out;
}

// ---------- LUTs ----------
const STOPS = {
  fire: [[0, 0, 0, 0], [.25, 90, 0, 160], [.5, 230, 40, 40], [.75, 255, 180, 0], [1, 255, 255, 255]],
  viridis: [[0, 68, 1, 84], [.25, 59, 82, 139], [.5, 33, 145, 140], [.75, 94, 201, 98], [1, 253, 231, 37]],
};
function hexToRgb(h) { const v = parseInt(h.slice(1), 16); return [v >> 16 & 255, v >> 8 & 255, v & 255]; }
function rgbToHex(c) { return '#' + c.map(x => x.toString(16).padStart(2, '0')).join(''); }
function lutTable(c) {
  const t = new Uint8Array(768), col = hexToRgb(c.color);
  for (let i = 0; i < 256; i++) {
    const y = Math.pow(i / 255, c.gamma);
    let r, g, b;
    if (c.preset === 'grey') r = g = b = y * 255;
    else if (c.preset === 'inverted') r = g = b = (1 - y) * 255;
    else if (STOPS[c.preset]) {
      const s = STOPS[c.preset]; let k = 0; while (k < s.length - 2 && y > s[k + 1][0]) k++;
      const f = (y - s[k][0]) / (s[k + 1][0] - s[k][0]);
      r = s[k][1] + f * (s[k + 1][1] - s[k][1]); g = s[k][2] + f * (s[k + 1][2] - s[k][2]); b = s[k][3] + f * (s[k + 1][3] - s[k][3]);
    } else { r = col[0] * y; g = col[1] * y; b = col[2] * y; }
    t[i * 3] = r; t[i * 3 + 1] = g; t[i * 3 + 2] = b;
  }
  return t;
}
function idxArr(p, c) {
  const out = new Uint8Array(NP), lo = c.lo, sc = 255 / Math.max(1e-9, c.hi - c.lo);
  for (let i = 0; i < NP; i++) { const v = (p[i] - lo) * sc; out[i] = v <= 0 ? 0 : v >= 255 ? 255 : v; }
  return out;
}
function renderTiles() {
  const tabs = ch.map(lutTable);
  const frames = new Map();   // one set of channel index arrays per distinct frame
  tiles.forEach((tl, i) => {
    const arr = tl.m === st.m ? data : cache.get(tl.m);
    let cv = tileCv[i];
    if (!cv) { cv = tileCv[i] = document.createElement('canvas'); cv.width = W; cv.height = H; }
    const g = cv.getContext('2d');
    if (!arr) { g.fillStyle = '#000'; g.fillRect(0, 0, W, H); tl.missing = true; return; }
    tl.missing = false;
    const fk = tl.t + '|' + tl.z + '|' + tl.m;
    if (!frames.has(fk)) frames.set(fk, ch.map(() => null));
    const ix = frames.get(fk), f = {t: tl.t, z: tl.z, m: tl.m, arr};
    const need = tl.c === 'merge' ? ch.map((c, k) => c.visible ? k : -1).filter(k => k >= 0) : [tl.c];
    for (const k of need) if (!ix[k]) ix[k] = idxArr(chanPlane(k, f), ch[k]);
    const im = g.createImageData(W, H), d = im.data;
    if (tl.c === 'merge') {
      const acc = new Uint16Array(NP * 3);
      for (const k of need) { const t = tabs[k], a = ix[k];
        for (let q = 0; q < NP; q++) { const j = a[q] * 3; acc[q * 3] += t[j]; acc[q * 3 + 1] += t[j + 1]; acc[q * 3 + 2] += t[j + 2]; } }
      for (let q = 0; q < NP; q++) { d[q * 4] = Math.min(255, acc[q * 3]); d[q * 4 + 1] = Math.min(255, acc[q * 3 + 1]); d[q * 4 + 2] = Math.min(255, acc[q * 3 + 2]); d[q * 4 + 3] = 255; }
    } else {
      const t = tabs[tl.c], a = ix[tl.c];
      for (let q = 0; q < NP; q++) { const j = a[q] * 3; d[q * 4] = t[j]; d[q * 4 + 1] = t[j + 1]; d[q * 4 + 2] = t[j + 2]; d[q * 4 + 3] = 255; }
    }
    g.putImageData(im, 0, 0);
  });
  dirty = false;
}

// ---------- layout & drawing ----------
const view = $('view'), vctx = view.getContext('2d');
function panelTileName(t0) {
  if (st.panelAxis === 'T') { const tt = D.times && D.times[t0.m]; return tt && tt[t0.t] != null ? fmtTime(tt[t0.t], timeSpan()) : 'T ' + (t0.t + 1); }
  if (st.panelAxis === 'Z') return 'Z ' + (t0.z + 1);
  if (st.panelAxis === 'M') return AX.M.names[t0.m];
  return '';
}
function parseSel(str, n) {
  const s = String(str || 'auto').trim().toLowerCase();
  if (s === 'all' || s === '*') return [...Array(n).keys()];
  if (s === '' || s === 'auto') {
    const k = Math.min(n, 12); return [...new Set([...Array(k).keys()].map(i => Math.round(i * (n - 1) / Math.max(1, k - 1))))];
  }
  const out = [];
  for (let part of s.split(/[,;\s]+/)) {
    if (!part) continue;
    let step = 1; if (part.includes(':')) { const [a, b] = part.split(':'); part = a; step = Math.max(1, parseInt(b) || 1); }
    if (part === 'last') { out.push(n); continue; }
    if (part.includes('-')) { let [a, b] = part.split('-'); a = a ? (a === 'last' ? n : parseInt(a)) : 1; b = b && b !== 'last' ? parseInt(b) : n;
      if (b >= a) for (let v = a; v <= b; v += step) out.push(v); else for (let v = a; v >= b; v -= step) out.push(v); }
    else out.push(parseInt(part));
  }
  const r = out.filter(v => v >= 1 && v <= n).map(v => v - 1);
  return r.length ? r : [0];
}
function panelValues() {
  const n = {T: NT, Z: NZ, M: NM}[st.panelAxis] || 0;
  return [...Array(n).keys()];        // the axis range in ImageStudios already chose these
}
function pageGeom(a) {
  // rows x cols per page for axis a (set in ImageStudios); auto = everything on one page
  const n = ({T: NT, Z: NZ, M: NM})[a] || 0, g = GRIDS[a] || [0, 0];
  if (!n || !(g[0] > 0 || g[1] > 0)) return {n, per: n, rows: 0, cols: 0, pages: 1};
  let rows = g[0] || Math.ceil(n / g[1]), cols = g[1] || Math.ceil(n / g[0]);
  const per = rows * cols, pages = Math.ceil(n / per);
  if (pages === 1) {      // fewer tiles than the grid holds: don't leave whole empty rows / columns
    if (PANEL.fill === 'col') { rows = Math.min(rows, n); cols = Math.ceil(n / rows); }
    else { cols = Math.min(cols, n); rows = Math.ceil(n / cols); }
  }
  return {n, per, rows, cols, pages};
}
function pageValues() {
  const g = pageGeom(st.panelAxis); st.page = clamp(st.page, 0, g.pages - 1);
  return panelValues().slice(st.page * g.per, (st.page + 1) * g.per);
}
function setPage(p) {
  const g = pageGeom(st.panelAxis), np = clamp(p, 0, g.pages - 1);
  if (np === st.page) return; st.page = np; st.sel = 0; statsKey = ''; request(true);
}
function updatePager() {
  const a = st.panelAxis, g = pageGeom(a), on = 'TZM'.includes(a || '_') && g.pages > 1;
  $('pager').style.display = on ? 'inline-flex' : 'none'; if (!on) return;
  const a0 = st.page * g.per + 1, a1 = Math.min(g.n, (st.page + 1) * g.per);
  $('pgTxt').textContent = `${AXIS_NAME[a]} ${a0}–${a1} of ${g.n}  ·  page ${st.page + 1}/${g.pages}`;
  $('pgPrev').disabled = st.page === 0; $('pgNext').disabled = st.page >= g.pages - 1;
}
$('pgPrev').onclick = () => setPage(st.page - 1);
$('pgNext').onclick = () => setPage(st.page + 1);
function arrange(n) {
  // same rule as ImageStudios: N images per row (or per column), auto = up to 4 in one row, else near-square
  const per = PANEL.count > 0 ? Math.min(PANEL.count, n) : (n <= 4 ? n : Math.ceil(Math.sqrt(n)));
  const pos = [];
  if (PANEL.fill === 'col') { const rows = Math.min(per, n), cols = Math.ceil(n / rows);
    for (let k = 0; k < n; k++) pos.push({row: k % rows, col: Math.floor(k / rows)}); return {pos, rows, cols}; }
  const cols = Math.min(per, n), rows = Math.ceil(n / cols);
  for (let k = 0; k < n; k++) pos.push({row: Math.floor(k / cols), col: k % cols});
  return {pos, rows, cols};
}
function tileList() {
  const base = {t: st.t, z: st.z, m: st.m}, single = NC > 1 ? 'merge' : 0, out = [];
  if (st.panelAxis === 'C') {
    const keys = [...Array(NC).keys()]; if (PANEL.merge) keys.push('merge');
    keys.forEach(c => out.push({...base, c}));
  } else if (st.panelAxis) {
    const ax = st.panelAxis.toLowerCase(), c = pop ? pop.c : single;
    pageValues().forEach(v => out.push({...base, [ax]: v, c}));
    const pg = pageGeom(st.panelAxis);
    if (pg.rows) {          // fixed grid per page; the last page keeps the same tile size
      out.forEach((t, k) => { if (PANEL.fill === 'col') { t.row = k % pg.rows; t.col = Math.floor(k / pg.rows); }
                              else { t.row = Math.floor(k / pg.cols); t.col = k % pg.cols; } });
      return {tiles: out, rows: pg.rows, cols: pg.cols};
    }
  } else out.push({...base, c: pop ? pop.c : single});
  const g = arrange(out.length);
  out.forEach((t, k) => { t.row = g.pos[k].row; t.col = g.pos[k].col; });
  return {tiles: out, rows: g.rows, cols: g.cols};
}
let gridRows = 1, gridCols = 1;
function layout() {
  const dpr = window.devicePixelRatio || 1;
  const vw = view.clientWidth * dpr, vh = view.clientHeight * dpr;
  if (view.width !== vw || view.height !== vh) { view.width = vw; view.height = vh; }
  // the popup sits above the panel, inset from the edges with a bar for its breadcrumb
  const pm = pop ? Math.max(14, Math.min(40, view.clientWidth * 0.03)) * dpr : 0, bar = pop ? 40 * dpr : 0;
  const R = {x: pm, y: pm + bar, w: vw - 2 * pm, h: vh - 2 * pm - bar};
  const cw = R.w, chh = R.h;
  const cols = gridCols, rows = gridRows, multi = tiles.length > 1;
  const gap = multi ? Math.max(0, PANEL.gap) * dpr : 0, margin = multi ? gap : 0, room = 8 * dpr;
  const SW = LUTVIEW === 'beside' && UI.lut ? 0.55 : 0;          // histogram strip, as a fraction of tile width
  const sgap = SW ? 4 * dpr : 0;
  const s0 = Math.min((cw - 2 * room - 2 * margin - gap * (cols - 1) - cols * sgap) / (cols * W * (1 + SW)),
                      (chh - 2 * room - 2 * margin - gap * (rows - 1)) / (rows * H));
  const tw = W * s0, th = H * s0, slot = tw * (1 + SW) + sgap;
  const gw = cols * slot + (cols - 1) * gap + 2 * margin, gh = rows * th + (rows - 1) * gap + 2 * margin;
  const gx = R.x + (cw - gw) / 2, gy = R.y + (chh - gh) / 2;
  const rects = tiles.map((tl, i) => { const x = gx + margin + tl.col * (slot + gap), y = gy + margin + tl.row * (th + gap);
    return {tile: tl, i, x, y, w: tw, h: th, hx: x + tw + sgap, hw: tw * SW}; });
  return lastLayout = {rects, s: s0 * st.zoom, s0, dpr, cols, grid: {x: gx, y: gy, w: gw, h: gh}, region: R, pm, bar};
}
function toImg(r, L, sx, sy) { return {x: st.vx + (sx - (r.x + r.w / 2)) / L.s, y: st.vy + (sy - (r.y + r.h / 2)) / L.s}; }
function toScr(r, L, ix, iy) { return {x: r.x + r.w / 2 + (ix - st.vx) * L.s, y: r.y + r.h / 2 + (iy - st.vy) * L.s}; }
function niceLen(t) { if (t <= 0) return 1; const e = Math.floor(Math.log10(t)); let best = Math.pow(10, e); for (const m of [1, 2, 5, 10]) if (m * Math.pow(10, e) <= t * 1.25) best = m * Math.pow(10, e); return best; }
function fmtUm(v) { return v >= 1000 ? (v / 1000) + ' mm' : (v < 1 ? (v * 1000).toFixed(0) + ' nm' : (+v.toPrecision(4)) + ' \u00b5m'); }
function fmtTime(sec, span) {
  if (sec == null) return '';
  const a = Math.abs(sec), sg = sec < 0 ? '-' : '';
  if (span < 120) return sg + a.toFixed(1) + ' s';
  if (span < 3 * 3600) return sg + (a / 60).toFixed(1) + ' min';
  if (span < 4 * 86400) { const m = Math.round(a / 60); return sg + Math.floor(m / 60) + ' h ' + String(m % 60).padStart(2, '0') + ' min'; }
  return sg + (a / 86400).toFixed(2) + ' d';
}
function curTime() { const tt = D.times && D.times[st.m]; return tt ? tt[st.t] : null; }
function timeSpan() { const tt = D.times && D.times[st.m]; return tt ? Math.max(...tt.map(v => Math.abs(v || 0))) : 0; }
function curZ() { const zz = D.zpos && D.zpos[st.m]; return zz ? zz[st.z] : null; }
let labelPx = 0;   // label size for the current layout (scales with tile size)
function label(g, txt, x, y, color, align, dpr) {
  const px = labelPx || Math.round(13 * dpr);
  g.font = `600 ${px}px "Segoe UI",system-ui,sans-serif`;
  g.textAlign = align; g.textBaseline = 'top'; g.lineWidth = Math.max(2, px / 4.5); g.strokeStyle = 'rgba(0,0,0,.85)';
  g.strokeText(txt, x, y); g.fillStyle = color; g.fillText(txt, x, y);
}
function draw() {
  if (!data) return;
  const tl = tileList(), sig = JSON.stringify(tl.tiles.map(x => [x.c, x.t, x.z, x.m]));
  if (sig !== tilesSig) { tiles = tl.tiles; gridCols = tl.cols; gridRows = tl.rows; tilesSig = sig; dirty = true;
    if (st.sel >= tiles.length) st.sel = 0; ensurePositions(); updatePager(); }
  if (dirty) { computeHists(); renderTiles(); }
  const L = layout(), g = vctx, dpr = L.dpr;
  const tileH = L.rects.length ? Math.min(L.rects[0].h, L.rects[0].w) : 200 * dpr;
  labelPx = Math.round(Math.max(8 * dpr, Math.min(13 * dpr, tileH * 0.085)));
  g.setTransform(1, 0, 0, 1, 0, 0); g.fillStyle = UI.theme === 'light' ? '#e9ebf0' : '#0d0e11'; g.fillRect(0, 0, view.width, view.height);
  if (pop) {
    if (baseSnap) { g.imageSmoothingEnabled = true; g.drawImage(baseSnap, 0, 0, view.width, view.height); }
    g.fillStyle = 'rgba(0,0,0,.62)'; g.fillRect(0, 0, view.width, view.height);
    const x0 = L.pm * 0.5, y0 = L.pm * 0.5, w0 = view.width - L.pm, h0 = view.height - L.pm;
    g.fillStyle = UI.theme === 'light' ? '#ffffff' : '#1f2128'; g.strokeStyle = '#6c8cff'; g.lineWidth = dpr;
    g.beginPath(); if (g.roundRect) g.roundRect(x0, y0, w0, h0, 10 * dpr); else g.rect(x0, y0, w0, h0); g.fill(); g.stroke();
    placePopBar(L, x0, y0, w0);
  }
  if (tiles.length > 1) { g.fillStyle = PANEL.bg === 'black' ? '#000' : '#fff'; g.fillRect(L.grid.x, L.grid.y, L.grid.w, L.grid.h); }
  g.imageSmoothingEnabled = L.s < 1;
  L.rects.forEach((r, i) => {
    g.save(); g.beginPath(); g.rect(r.x, r.y, r.w, r.h); g.clip();
    g.fillStyle = '#000'; g.fillRect(r.x, r.y, r.w, r.h);
    const t0 = r.tile, p = toScr(r, L, 0, 0);
    g.drawImage(tileCv[r.i], p.x, p.y, W * L.s, H * L.s);
    const pad = Math.max(3 * dpr, labelPx * 0.6), lh = labelPx * 1.3;
    if (t0.missing) label(g, 'not in preview', r.x + r.w / 2, r.y + r.h / 2 - lh / 2, '#aaa', 'center', dpr);
    if (ovl.names && NC > 1 && (st.panelAxis === 'C' || r.i === 0)) {
      const names = t0.c === 'merge' ? ch.filter(c => c.visible) : [ch[t0.c]];
      names.forEach((c, k) => label(g, c.name, r.x + r.w - pad, r.y + pad + k * lh, c.preset === 'color' ? c.color : '#fff', 'right', dpr));
    }
    // axis labels: on every row start for the panel axis, once (first tile) for the others
    const first = r.i === 0;
    const show = a => (st.panelAxis === a ? true : first);   // each tile labels its own panel value
    let y = r.y + pad;
    if (ovl.time && NT > 1 && show('T') && !(st.proj !== 'frame' && st.projAxis === 'T')) {
      const tt = D.times && D.times[t0.m], tv = tt ? tt[t0.t] : null;
      label(g, tv != null ? fmtTime(tv, timeSpan()) : 'T ' + (t0.t + 1) + '/' + NT, r.x + pad, y, '#fff', 'left', dpr); y += lh; }
    if (ovl.z && NZ > 1 && show('Z') && !(st.proj !== 'frame' && st.projAxis === 'Z')) {
      const zz = D.zpos && D.zpos[t0.m], zv = zz ? zz[t0.z] : null;
      label(g, zv != null ? 'z = ' + zv.toFixed(1) + ' \u00b5m' : 'Z ' + (t0.z + 1) + '/' + NZ, r.x + pad, y, '#fff', 'left', dpr); y += lh; }
    if (first && st.proj !== 'frame') { label(g, st.proj + ' projection over ' + (st.projAxis === 'T' ? 'time' : 'Z'), r.x + pad, y, '#ffd75e', 'left', dpr); y += lh; }
    if (ovl.position && NM > 1 && show('M')) label(g, AX.M.names[t0.m], r.x + pad, r.y + r.h - pad - lh, '#fff', 'left', dpr);
    if (ovl.scalebar && D.pixelSize && i === L.rects.length - 1) {
      const umPerPx = D.pixelSize / L.s, len = niceLen(0.2 * r.w * umPerPx), bw = len / umPerPx, bh = Math.max(3, 4 * dpr);
      const bx = r.x + r.w - pad - bw, by = r.y + r.h - pad - bh;
      g.fillStyle = 'rgba(0,0,0,.8)'; g.fillRect(bx - dpr, by - dpr, bw + 2 * dpr, bh + 2 * dpr);
      g.fillStyle = '#fff'; g.fillRect(bx, by, bw, bh);
      label(g, fmtUm(len), bx + bw / 2, by - lh, '#fff', 'center', dpr);
    }
    if (st.ruler) {
      const a = toScr(r, L, st.ruler.x0, st.ruler.y0), b = toScr(r, L, st.ruler.x1, st.ruler.y1);
      g.strokeStyle = '#ffd75e'; g.lineWidth = 2 * dpr; g.beginPath(); g.moveTo(a.x, a.y); g.lineTo(b.x, b.y); g.stroke();
      const dpx = Math.hypot(st.ruler.x1 - st.ruler.x0, st.ruler.y1 - st.ruler.y0);
      const txt = D.pixelSize ? fmtUm(dpx * D.pixelSize) + '  (' + dpx.toFixed(1) + ' px)' : dpx.toFixed(1) + ' px';
      label(g, txt, (a.x + b.x) / 2, (a.y + b.y) / 2 + 6 * dpr, '#ffd75e', 'center', dpr);
    }
    if (st.ortho && NZ > 1) {
      const c = toScr(r, L, st.cx + .5, st.cy + .5); g.strokeStyle = 'rgba(255,215,94,.7)'; g.lineWidth = dpr;
      g.beginPath(); g.moveTo(r.x, c.y); g.lineTo(r.x + r.w, c.y); g.moveTo(c.x, r.y); g.lineTo(c.x, r.y + r.h); g.stroke();
    }
    g.restore();
    if (SHOW_SEL()) { if (r.i === st.sel) { g.strokeStyle = '#6c8cff'; g.lineWidth = 3 * dpr; g.strokeRect(r.x + 1.5 * dpr, r.y + 1.5 * dpr, r.w - 3 * dpr, r.h - 3 * dpr); } }
    if (r.hw > 0) drawTileHists(g, r, dpr);
  });
  drawMini(L); drawOrtho();
}
const SHOW_SEL = () => UI.lut && tiles.length > 1 && 'TZM'.includes(st.panelAxis || '_');
const tileHistCache = new Map();
function tileHist(t0, k, lo, hi) {
  const arr = t0.m === st.m ? data : cache.get(t0.m);
  if (!arr) return null;
  const key = [t0.m, t0.t, t0.z, k, st.proj, st.projAxis, lo, hi].join('|');
  if (tileHistCache.has(key)) return tileHistCache.get(key);
  const p = chanPlane(k, {t: t0.t, z: t0.z, m: t0.m, arr}), h = new Float64Array(64), sc = 64 / Math.max(1e-9, hi - lo);
  let sum = 0;
  for (let i = 0; i < NP; i++) { const v = (p[i] - lo) * sc; h[v <= 0 ? 0 : v >= 63 ? 63 : v | 0]++; sum += p[i]; }
  const res = {h, mean: sum / NP};
  if (tileHistCache.size > 600) tileHistCache.delete(tileHistCache.keys().next().value);
  tileHistCache.set(key, res);
  return res;
}
function drawTileHists(g, r, dpr) {
  // one small histogram per channel of this tile's own frame, against the shared LUT window
  const t0 = r.tile, ks = t0.c === 'merge' ? ch.map((c, k) => c.visible ? k : -1).filter(k => k >= 0) : [t0.c];
  g.fillStyle = UI.theme === 'light' ? '#f4f5f8' : '#14151a'; g.fillRect(r.hx, r.y, r.hw, r.h);
  const bh = r.h / Math.max(1, ks.length), fs = Math.max(7 * dpr, Math.min(11 * dpr, bh * 0.16, r.hw * 0.13));
  ks.forEach((k, j) => {
    const c = ch[k], span = Math.max(1e-6, c.hi - c.lo), lo = c.lo - span * 0.25, hi = c.hi + span * 0.25;
    const th = tileHist(t0, k, lo, hi); if (!th) return;
    const y0 = r.y + j * bh, pad = 3 * dpr, ih = bh - 2 * pad - fs * 1.2, ix = r.hx + pad, iw = r.hw - 2 * pad;
    const mx = Math.log1p(Math.max(...th.h)) || 1, col = c.preset === 'color' ? c.color : '#cccccc';
    g.fillStyle = col;
    for (let b = 0; b < 64; b++) { const v = Math.log1p(th.h[b]) / mx * ih; g.fillRect(ix + b / 64 * iw, y0 + pad + fs * 1.2 + ih - v, Math.max(1, iw / 64 - 0.5), v); }
    const xl = ix + (c.lo - lo) / (hi - lo) * iw, xh = ix + (c.hi - lo) / (hi - lo) * iw;
    g.fillStyle = '#ffd75e'; g.fillRect(xl - dpr / 2, y0 + pad + fs * 1.2, dpr, ih); g.fillRect(xh - dpr / 2, y0 + pad + fs * 1.2, dpr, ih);
    g.font = `600 ${Math.round(fs)}px "Segoe UI",system-ui,sans-serif`; g.textAlign = 'left'; g.textBaseline = 'top';
    g.fillStyle = col; g.fillText(c.name, ix, y0 + pad);
    const meanTxt = (iw > 95 * dpr ? 'mean ' : '') + fmtV(th.mean);
    if (g.measureText(c.name).width + g.measureText(meanTxt).width + 6 * dpr < iw) {
      g.textAlign = 'right'; g.fillStyle = UI.theme === 'light' ? '#555' : '#9aa0b0'; g.fillText(meanTxt, ix + iw, y0 + pad); }
  });
}
let loadingPos = false;
async function ensurePositions() {
  if (loadingPos) return;
  loadingPos = true;
  try {
    for (;;) {    // re-checks after every load, so turning the page mid-way loads the new page
      if (st.panelAxis !== 'M') break;
      const m = pageValues().find(v => v !== st.m && !cache.has(v) && document.getElementById('chunk-' + v));
      if (m == null) break;
      await loadPos(m, true); request(true);
    }
  } finally { loadingPos = false; }
}

// ---------- popup: open a tile alone, then as its own time / Z panel ----------
function snapBase() {
  baseSnap = document.createElement('canvas'); baseSnap.width = view.width; baseSnap.height = view.height;
  baseSnap.getContext('2d').drawImage(view, 0, 0);
}
async function openSingle(t0) {
  if (!t0) return;
  if (!pop) { draw(); snapBase();
    pop = {saved: {axis: st.panelAxis, m: st.m, t: st.t, z: st.z, sel: st.sel, page: st.page, zoom: st.zoom, vx: st.vx, vy: st.vy}}; }
  pop.mode = 'single'; pop.axis = ''; pop.c = t0.c;
  st.panelAxis = ''; st.sel = 0; st.page = 0; st.t = t0.t; st.z = t0.z; st.zoom = 1; st.vx = W / 2; st.vy = H / 2;
  if (t0.m !== st.m) await setAxis('M', t0.m);
  afterViewChange();
}
function openAxisPanel(a) {
  if (!pop) return;
  pop.mode = 'panel'; pop.axis = a; st.panelAxis = a; st.zoom = 1; st.vx = W / 2; st.vy = H / 2;
  const cur = a === 'T' ? st.t : st.z, g = pageGeom(a);
  st.page = Math.floor(cur / g.per); st.sel = cur - st.page * g.per;     // land on the frame you were looking at
  afterViewChange();
}
async function closePop() {
  if (!pop) return;
  const s = pop.saved; pop = null; baseSnap = null;
  st.panelAxis = s.axis; st.t = s.t; st.z = s.z; st.page = s.page; st.sel = s.sel; st.zoom = s.zoom; st.vx = s.vx; st.vy = s.vy;
  if (s.m !== st.m) await setAxis('M', s.m);
  afterViewChange();
}
function afterViewChange() { statsKey = ''; tilesSig = ''; syncPanelAxisUI(); updatePopBar(); updatePager(); updateAxisLabels(); request(true); }
function focusName() {
  const parts = [];
  if (NM > 1) parts.push(AX.M.names[st.m]);
  const sa = pop && pop.saved.axis;
  if (sa === 'T' && pop.mode === 'single') parts.push(panelTileName({t: st.t, m: st.m}) || 'T ' + (st.t + 1));
  if (sa === 'Z' && pop.mode === 'single') parts.push('Z ' + (st.z + 1));
  if (pop && pop.c !== 'merge' && NC > 1) parts.push(ch[pop.c].name);
  return parts.join(' · ') || 'Frame';
}
function updatePopBar() {
  const bar = $('popbar');
  if (!pop) { bar.style.display = 'none'; return; }
  bar.innerHTML = ''; bar.style.display = 'flex';
  const crumb = (txt, fn) => { const b = document.createElement('button'); b.className = 'crumb' + (fn ? '' : ' cur'); b.textContent = txt;
    if (fn) b.onclick = fn; bar.appendChild(b); };
  const sep = () => { const s = document.createElement('span'); s.className = 'sep'; s.textContent = '›'; bar.appendChild(s); };
  crumb((AXIS_NAME[pop.saved.axis] || 'Panel') + ' panel', closePop); sep();
  if (pop.mode === 'panel') {
    crumb(focusName(), () => { const t0 = selTile(); openSingle(t0 || {t: st.t, z: st.z, m: st.m, c: pop.c}); }); sep();
    crumb(AXIS_NAME[pop.axis]);
  } else crumb(focusName());
  const sp = document.createElement('span'); sp.className = 'sp'; bar.appendChild(sp);
  if (pop.mode === 'single') for (const a of ['T', 'Z']) {
    if (({T: NT, Z: NZ})[a] < 2) continue;
    const b = document.createElement('button'); b.textContent = '▦ ' + AXIS_NAME[a] + ' panel';
    b.title = 'Show this ' + (NM > 1 ? 'position' : 'image') + ' as a panel of all its ' + AXIS_NAME[a].toLowerCase();
    b.onclick = () => openAxisPanel(a); bar.appendChild(b);
  }
  const x = document.createElement('button'); x.textContent = '✕ Back'; x.title = 'Back to the ' + (AXIS_NAME[pop.saved.axis] || '').toLowerCase() + ' panel (Esc)';
  x.onclick = closePop; bar.appendChild(x);
}
function placePopBar(L, x0, y0, w0) {
  const bar = $('popbar'), d = L.dpr, pad = 8;
  bar.style.left = (x0 / d + pad) + 'px'; bar.style.top = (y0 / d + 4) + 'px'; bar.style.width = (w0 / d - 2 * pad) + 'px';
}
let raf = 0;
function request(rerender) { if (rerender) dirty = true; if (!raf) raf = requestAnimationFrame(() => { raf = 0; draw(); }); }

// ---------- minimap ----------
const mini = $('mini');
function drawMini(L) {
  const show = UI.zoom && st.zoom > 1.01; mini.style.display = show ? 'block' : 'none'; if (!show) return;
  const g = mini.getContext('2d'), k = Math.min(mini.width / W, mini.height / H), r = L.rects[0];
  g.fillStyle = '#000'; g.fillRect(0, 0, mini.width, mini.height); g.imageSmoothingEnabled = true;
  g.drawImage(tileCv[tiles.length - 1], 0, 0, W * k, H * k);
  const a = toImg(r, L, r.x, r.y), b = toImg(r, L, r.x + r.w, r.y + r.h);
  g.strokeStyle = '#ffd75e'; g.lineWidth = 2; g.strokeRect(a.x * k, a.y * k, (b.x - a.x) * k, (b.y - a.y) * k);
}
function miniMove(e) { const rc = mini.getBoundingClientRect(), k = Math.min(mini.width / W, mini.height / H);
  st.vx = (e.clientX - rc.left) * (mini.width / rc.width) / k; st.vy = (e.clientY - rc.top) * (mini.height / rc.height) / k; request(); }
mini.addEventListener('mousedown', e => { miniMove(e); const mv = ev => miniMove(ev), up = () => { removeEventListener('mousemove', mv); removeEventListener('mouseup', up); }; addEventListener('mousemove', mv); addEventListener('mouseup', up); e.stopPropagation(); });

// ---------- orthogonal views ----------
const xz = $('xz'), yz = $('yz');
function orthoImage(horizontal) {
  // horizontal: XZ (width W, height NZ) at row cy; else YZ (width NZ, height H) at column cx
  const w = horizontal ? W : NZ, h = horizontal ? NZ : H, cv = document.createElement('canvas'); cv.width = w; cv.height = h;
  const g = cv.getContext('2d'), im = g.createImageData(w, h), d = im.data, acc = new Uint16Array(w * h * 3);
  ch.forEach((c, k) => { if (!c.visible) return; const t = lutTable(c), sc = 255 / Math.max(1e-9, c.hi - c.lo);
    for (let z = 0; z < NZ; z++) { const p = planeAt(st.t, z, k);
      for (let u = 0; u < (horizontal ? W : H); u++) {
        const v = horizontal ? p[st.cy * W + u] : p[u * W + st.cx]; let q = (v - c.lo) * sc; q = q <= 0 ? 0 : q >= 255 ? 255 : q | 0;
        const o = horizontal ? (z * w + u) * 3 : (u * w + z) * 3; acc[o] += t[q * 3]; acc[o + 1] += t[q * 3 + 1]; acc[o + 2] += t[q * 3 + 2]; } } });
  for (let i = 0; i < w * h; i++) { d[i * 4] = Math.min(255, acc[i * 3]); d[i * 4 + 1] = Math.min(255, acc[i * 3 + 1]); d[i * 4 + 2] = Math.min(255, acc[i * 3 + 2]); d[i * 4 + 3] = 255; }
  g.putImageData(im, 0, 0); return cv;
}
function drawOrtho() {
  const on = st.ortho && NZ > 1; xz.style.display = yz.style.display = on ? 'block' : 'none'; if (!on) return;
  const zr = (D.zStep && D.pixelSize) ? D.zStep / D.pixelSize : 1, dpr = window.devicePixelRatio || 1;
  for (const [cv, horiz] of [[xz, true], [yz, false]]) {
    cv.width = cv.clientWidth * dpr; cv.height = cv.clientHeight * dpr;
    const g = cv.getContext('2d'), img = orthoImage(horiz);
    const iw = horiz ? W : NZ * zr, ih = horiz ? NZ * zr : H, k = Math.min(cv.width / iw, cv.height / ih);
    const ox = (cv.width - iw * k) / 2, oy = (cv.height - ih * k) / 2;
    g.fillStyle = UI.theme === 'light' ? '#e9ebf0' : '#0d0e11'; g.fillRect(0, 0, cv.width, cv.height); g.imageSmoothingEnabled = false;
    g.drawImage(img, ox, oy, iw * k, ih * k);
    g.strokeStyle = 'rgba(255,215,94,.8)'; g.lineWidth = dpr; g.beginPath();
    if (horiz) { const y = oy + (st.z + .5) * zr * k, x = ox + (st.cx + .5) * k; g.moveTo(ox, y); g.lineTo(ox + iw * k, y); g.moveTo(x, oy); g.lineTo(x, oy + ih * k); }
    else { const x = ox + (st.z + .5) * zr * k, y = oy + (st.cy + .5) * k; g.moveTo(x, oy); g.lineTo(x, oy + ih * k); g.moveTo(ox, y); g.lineTo(ox + iw * k, y); }
    g.stroke(); cv._map = {ox, oy, k, zr};
    label(g, horiz ? 'XZ' : 'YZ', 6 * dpr, 6 * dpr, '#aeb6d6', 'left', dpr);
  }
}
function orthoClick(cv, horiz, e) {
  const m = cv._map; if (!m) return; const rc = cv.getBoundingClientRect(), dpr = window.devicePixelRatio || 1;
  const px = ((e.clientX - rc.left) * dpr - m.ox) / m.k, py = ((e.clientY - rc.top) * dpr - m.oy) / m.k;
  if (horiz) { st.cx = clamp(Math.floor(px), 0, W - 1); setAxis('Z', clamp(Math.floor(py / m.zr), 0, NZ - 1)); }
  else { st.cy = clamp(Math.floor(py), 0, H - 1); setAxis('Z', clamp(Math.floor(px / m.zr), 0, NZ - 1)); }
  request();
}
xz.addEventListener('mousedown', e => orthoClick(xz, true, e));
yz.addEventListener('mousedown', e => orthoClick(yz, false, e));
const clamp = (v, a, b) => v < a ? a : v > b ? b : v;

// ---------- mouse on main view ----------
function hit(e) {
  const L = lastLayout; if (!L) return null; const rc = view.getBoundingClientRect();
  const sx = (e.clientX - rc.left) * L.dpr, sy = (e.clientY - rc.top) * L.dpr;
  for (const r of L.rects) if (sx >= r.x && sx < r.x + r.w && sy >= r.y && sy < r.y + r.h) { const p = toImg(r, L, sx, sy); return {r, L, sx, sy, ix: p.x, iy: p.y}; }
  return null;
}
let drag = null;
view.addEventListener('mousedown', e => {
  const h = hit(e); if (!h) return;
  if (st.rulerOn) { st.ruler = {x0: h.ix, y0: h.iy, x1: h.ix, y1: h.iy}; drag = {mode: 'ruler'}; }
  else if (UI.zoom || st.ortho) { drag = {mode: 'pan', x: e.clientX, y: e.clientY, vx: st.vx, vy: st.vy, moved: false}; if (UI.zoom) view.style.cursor = 'grabbing'; }
});
addEventListener('mousemove', e => {
  if (drag && drag.mode === 'pan' && UI.zoom) { const L = lastLayout, dx = (e.clientX - drag.x) * L.dpr, dy = (e.clientY - drag.y) * L.dpr;
    if (Math.abs(dx) + Math.abs(dy) > 3) drag.moved = true; st.vx = drag.vx - dx / L.s; st.vy = drag.vy - dy / L.s; request(); }
  else if (drag && drag.mode === 'ruler') { const h = hit(e); if (h) { st.ruler.x1 = h.ix; st.ruler.y1 = h.iy; request(); } }
  if (e.target === view) inspect(e);
});
let downAt = null;
view.addEventListener('pointerdown', e => { downAt = {x: e.clientX, y: e.clientY}; });
function outsidePopup(e) {
  const L = lastLayout; if (!pop || !L) return false; const rc = view.getBoundingClientRect();
  const sx = (e.clientX - rc.left) * L.dpr, sy = (e.clientY - rc.top) * L.dpr, h = L.pm * 0.5;
  return sx < h || sy < h || sx > view.width - h || sy > view.height - h;
}
view.addEventListener('click', e => {
  if (st.rulerOn || !downAt || Math.hypot(e.clientX - downAt.x, e.clientY - downAt.y) > 4) return;
  const h = hit(e);
  if (!h) { if (outsidePopup(e)) closePop(); return; }
  if (h.r.i === st.sel) return;
  st.sel = h.r.i; computeHists(true); request();      // histograms follow the clicked tile
});
addEventListener('mouseup', e => {
  if (drag && drag.mode === 'pan' && !drag.moved && st.ortho) { const h = hit(e); if (h) { st.cx = clamp(Math.floor(h.ix), 0, W - 1); st.cy = clamp(Math.floor(h.iy), 0, H - 1); request(); } }
  drag = null; view.style.cursor = '';
});
view.addEventListener('wheel', e => {
  if (!UI.zoom) return;
  e.preventDefault(); const h = hit(e); if (!h) return;
  const f = Math.exp(-e.deltaY * 0.0015), nz = clamp(st.zoom * f, 1, 64);
  const s1 = h.L.s0 * nz;
  st.vx = h.ix - (h.sx - (h.r.x + h.r.w / 2)) / s1; st.vy = h.iy - (h.sy - (h.r.y + h.r.h / 2)) / s1; st.zoom = nz;
  if (nz === 1) { st.vx = W / 2; st.vy = H / 2; }
  request(); inspect(e);
}, {passive: false});
view.addEventListener('dblclick', e => {
  // panel: open the tile alone above the panel; single image: fit
  const h = hit(e);
  if (h && tiles.length > 1 && !st.rulerOn) { openSingle(h.r.tile); return; }
  if (UI.zoom) fit();
});
view.addEventListener('mouseleave', () => { $('status').innerHTML = '&nbsp;'; });
function fit() { st.zoom = 1; st.vx = W / 2; st.vy = H / 2; request(); }
function inspect(e) {
  if (!UI.inspector) return;
  const h = hit(e); if (!h || !data) { $('status').innerHTML = '&nbsp;'; return; }
  const x = Math.floor(h.ix), y = Math.floor(h.iy);
  if (x < 0 || y < 0 || x >= W || y >= H) { $('status').innerHTML = '&nbsp;'; return; }
  let s = `x ${x}  y ${y}`;
  if (D.pixelSize) s += `   (${(x * D.pixelSize).toFixed(2)}, ${(y * D.pixelSize).toFixed(2)} \u00b5m)`;
  const t0 = h.r.tile, arr = t0.m === st.m ? data : cache.get(t0.m);
  if (!arr) { $('status').innerHTML = '&nbsp;'; return; }
  const fr = {t: t0.t, z: t0.z, m: t0.m, arr};
  if (st.panelAxis) s += '   \u2502   ' + (st.panelAxis === 'C' ? (t0.c === 'merge' ? 'merge' : ch[t0.c].name) : panelTileName(t0));
  if (tiles.length > 1) s += '   <span class="sub">(click: histograms \u00b7 double-click: open)</span>';
  const vals = ch.map((c, k) => { const v = chanPlane(k, fr)[y * W + x]; return `<span style="color:${c.preset === 'color' ? c.color : '#ddd'}">${c.name} ${Number.isInteger(v) ? v : v.toFixed(1)}</span>`; });
  s += '   │   ' + vals.join('   ');
  if (D.bin > 1) s += `   <span class="sub">(data binned ${D.bin}×${D.bin})</span>`;
  $('status').innerHTML = s;
}

// ---------- axes & playback ----------
const sliders = {};
function axisText(a, v) {
  if (a === 'T') { const tt = D.times && D.times[st.m]; const tv = tt ? tt[v] : null; return `${v + 1} / ${NT}` + (tv != null ? '   ' + fmtTime(tv, timeSpan()) : '') + (AX.T.names ? '' : ''); }
  if (a === 'Z') { const zz = D.zpos && D.zpos[st.m]; const zv = zz ? zz[v] : null; return `${v + 1} / ${NZ}` + (zv != null ? `   z = ${zv.toFixed(1)} \u00b5m` : ''); }
  return `${v + 1} / ${NM}   ${AX.M.names[v]}`;
}
function buildAxes() {
  const box = $('axes'); box.innerHTML = '';
  for (const a of ['M', 'T', 'Z']) {
    const n = a === 'T' ? NT : a === 'Z' ? NZ : NM; if (n <= 1) continue;
    const row = document.createElement('div'); row.className = 'ax';
    row.innerHTML = `<label>${AX[a].label}</label><input type="range" min="0" max="${n - 1}" value="0"><span class="v"></span>`;
    const r = row.querySelector('input'), v = row.querySelector('.v');
    r.addEventListener('input', () => setAxis(a, +r.value));
    sliders[a] = {r, v, row}; box.appendChild(row);
    const o = document.createElement('option'); o.value = a; o.textContent = AX[a].label; $('playAxis').appendChild(o);
  }
  for (const a of ['T', 'Z']) { const n = a === 'T' ? NT : NZ; if (n > 1) { const o = document.createElement('option'); o.value = a; o.textContent = AX[a].label; $('projAxis').appendChild(o); } }
  if (!$('projAxis').options.length) { $('proj').disabled = true; $('projAxis').disabled = true; }
  else $('projAxis').value = st.projAxis = $('projAxis').options[0].value === 'T' && NZ > 1 ? 'Z' : $('projAxis').options[0].value;
  if (!$('playAxis').options.length) { $('play').disabled = true; $('playAxis').disabled = true; }
  else $('playAxis').value = NT > 1 ? 'T' : (NZ > 1 ? 'Z' : 'M');
  updateAxisLabels();
}
function syncPanelAxisUI() {
  if (UI.ortho && NZ > 1) { $('btnOrtho').style.display = st.panelAxis === 'Z' ? 'none' : ''; if (st.panelAxis === 'Z' && st.ortho) $('btnOrtho').click(); }
  for (const a in sliders) sliders[a].row.style.display = a === st.panelAxis ? 'none' : '';
  const pa = $('playAxis'); [...pa.options].forEach(o => { o.disabled = o.value === st.panelAxis; });
  if (pa.value === st.panelAxis) { const o = [...pa.options].find(o => !o.disabled); if (o) pa.value = o.value; else setPlaying(false); }
  $('play').disabled = ![...pa.options].some(o => !o.disabled);
}
function updateAxisLabels() { for (const a in sliders) { const v = a === 'T' ? st.t : a === 'Z' ? st.z : st.m; sliders[a].r.value = v; sliders[a].v.textContent = axisText(a, v); } }
async function setAxis(a, v) {
  if (a === 'T') st.t = v; else if (a === 'Z') st.z = v;
  else if (v !== st.m || !data) { const arr = await loadPos(v); if (!arr) { updateAxisLabels(); return; } st.m = v; data = arr; projCache.clear(); statsKey = ''; markGallery(); if (pop) updatePopBar(); }
  updateAxisLabels(); request(true);
}
let timer = null;
function setPlaying(on) {
  st.playing = on; $('play').innerHTML = on ? '&#10074;&#10074; Pause' : '&#9654; Play'; $('play').classList.toggle('on', on);
  clearTimeout(timer); if (on) tick();
}
async function tick() {
  if (!st.playing) return;
  const a = $('playAxis').value, n = a === 'T' ? NT : a === 'Z' ? NZ : NM, cur = a === 'T' ? st.t : a === 'Z' ? st.z : st.m;
  let nx = cur + 1; if (nx >= n) { if ($('loop').checked) nx = 0; else { setPlaying(false); return; } }
  const t0 = performance.now(); await setAxis(a, nx);
  timer = setTimeout(tick, Math.max(0, 1000 / Math.max(0.1, +$('fps').value || 10) - (performance.now() - t0)));
}
$('play').onclick = () => setPlaying(!st.playing);
$('fps').value = D.fps || 10;
$('proj').onchange = () => { st.proj = $('proj').value; $('projOverWrap').style.opacity = st.proj === 'frame' ? .5 : 1; request(true); };
$('projAxis').onchange = () => { st.projAxis = $('projAxis').value; request(true); };
$('projOverWrap').style.opacity = .5;

// ---------- histograms / LUT editor ----------
let statsKey = '';
function selTile() { return tiles[st.sel] || tiles[0] || null; }
function selFrame() {
  const t0 = selTile();
  if (!t0) return {t: st.t, z: st.z, m: st.m, arr: data};
  const arr = t0.m === st.m ? data : (cache.get(t0.m) || null);
  return arr ? {t: t0.t, z: t0.z, m: t0.m, arr} : {t: st.t, z: st.z, m: st.m, arr: data};
}
function frameKey() { const f = selFrame(); return [f.m, f.t, f.z, st.proj, st.projAxis].join('|'); }
function computeHists(force) {
  // Histogram + stats of exactly what is on screen (this frame, or the projection), per channel.
  if (!data) return;
  const key = frameKey();
  if (!force && key === statsKey) return;
  statsKey = key;
  const fr = selFrame();
  ch.forEach((c, k) => {
    const p = chanPlane(k, fr);
    let mn = Infinity, mx = -Infinity, sum = 0;
    for (let i = 0; i < NP; i++) { const v = p[i]; if (v < mn) mn = v; if (v > mx) mx = v; sum += v; }
    const step = Math.max(1, Math.floor(NP / 65536)), smp = new Float32Array(Math.ceil(NP / step));
    for (let i = 0, j = 0; i < NP; i += step, j++) smp[j] = p[i];
    smp.sort();
    const q = f => smp[Math.min(smp.length - 1, Math.max(0, Math.round(f * (smp.length - 1))))];
    c.fmin = mn; c.fmax = mx; c.fmean = sum / NP; c.flo = q(D.lowPct / 100); c.fhi = q(D.highPct / 100);
    if (!(c.fhi > c.flo)) c.fhi = c.flo + 1;
    if (c.autoFrame) { c.lo = c.flo; c.hi = c.fhi; }
    // histogram window follows this frame (and always contains the min/max handles)
    const span = Math.max(1e-6, c.fhi - c.fmin);
    c.hmin = Math.max(c.dmin, Math.min(c.fmin, c.lo));
    c.hmax = Math.min(c.dmax, Math.max(c.fhi + span * 0.5, c.hi + (c.hi - c.lo) * 0.05, c.hmin + 1));
    if (!(c.hmax > c.hmin)) c.hmax = c.hmin + 1;
    if (!UI.lut) return;
    const h = new Float64Array(256), lo = c.hmin, sc = 255 / Math.max(1e-9, c.hmax - c.hmin);
    for (let i = 0; i < NP; i++) { const v = (p[i] - lo) * sc; h[v <= 0 ? 0 : v >= 255 ? 255 : v | 0]++; }
    c.hist = h;
  });
  if (UI.lut) ch.forEach(c => { drawHist(c); showStats(c); });
}
function fmtV(v) { return Number.isInteger(v) ? String(v) : (Math.abs(v) >= 100 ? v.toFixed(0) : v.toFixed(2)); }
function showStats(c) {
  if (!c.el) return;
  c.el.lo.value = +c.lo.toPrecision(6); c.el.hi.value = +c.hi.toPrecision(6);
  const t0 = selTile();
  let what = st.proj === 'frame' ? 'this frame' : st.proj + ' projection';
  if (t0 && tiles.length > 1 && 'TZM'.includes(st.panelAxis || '_')) what += ' (' + panelTileName(t0) + ')';
  c.el.stats.textContent = `${what}: min ${fmtV(c.fmin)} \u00b7 max ${fmtV(c.fmax)} \u00b7 mean ${fmtV(c.fmean)}`;
}
function drawHist(c) {
  const cv = c.el && c.el.hist; if (!cv) return;
  const dpr = window.devicePixelRatio || 1; cv.width = cv.clientWidth * dpr; cv.height = cv.clientHeight * dpr;
  const g = cv.getContext('2d'), w = cv.width, h = cv.height, rng = c.hmax - c.hmin || 1;
  g.fillStyle = '#0f1013'; g.fillRect(0, 0, w, h);
  if (c.hist) { const mx = Math.log1p(Math.max(...c.hist)); g.fillStyle = c.preset === 'color' ? c.color + 'aa' : '#bbbbbbaa';
    for (let i = 0; i < 256; i++) { const bh = Math.log1p(c.hist[i]) / mx * (h - 4); g.fillRect(i / 256 * w, h - bh, Math.ceil(w / 256), bh); } }
  const xl = (c.lo - c.hmin) / rng * w, xh = (c.hi - c.hmin) / rng * w;
  g.strokeStyle = '#fff'; g.lineWidth = 1.5 * dpr; g.beginPath();
  for (let i = 0; i <= 40; i++) { const f = i / 40, x = xl + f * (xh - xl), y = h - Math.pow(f, c.gamma) * (h - 4) - 2; i ? g.lineTo(x, y) : g.moveTo(x, y); }
  g.moveTo(0, h - 2); g.lineTo(xl, h - 2); g.moveTo(xh, 2); g.lineTo(w, 2); g.stroke();
  for (const x of [xl, xh]) { g.fillStyle = '#ffd75e'; g.fillRect(x - 1.5 * dpr, 0, 3 * dpr, h); }
}
function defaultHmax(c) { return Math.min(c.dmax, Math.max(c.hmin + 1, c.autoHi + (c.autoHi - c.dmin) * 0.6)); }
function widen(c) {   // keep both handles inside the histogram window
  let ch2 = false;
  if (c.hi > c.hmax) { c.hmax = Math.min(c.dmax, c.hi + (c.hi - c.hmin) * 0.25); ch2 = true; }
  if (c.lo < c.hmin) { c.hmin = Math.max(c.dmin, c.lo); ch2 = true; }
  if (ch2 && data) computeHists(true);
}
function buildLuts() {
  const box = $('luts'); box.innerHTML = '';
  ch.forEach((c, k) => {
    const d = document.createElement('div'); d.className = 'card';
    d.innerHTML = `<h3><input type="checkbox" checked title="Show this channel"><span class="nm">${c.name}</span>
      <select title="Colour map"><option value="color">colour</option><option value="grey">grey</option><option value="fire">fire</option><option value="viridis">viridis</option><option value="inverted">inverted</option></select>
      <input type="color" class="sw" value="${c.color}" title="Channel colour"></h3>
      <canvas class="hist" title="Drag the yellow handles to set the display range"></canvas>
      <div class="lutrow"><span class="lab">min</span><input type="number" step="any"><span class="lab">max</span><input type="number" step="any"></div>
      <div class="lutrow"><span class="lab">gamma</span><input type="range" min="-1.6" max="1.6" step="0.02" value="0"><span class="gv">1.00</span></div>
      <div class="lutrow stats"></div>
      <div class="lutrow"><button data-a="auto" title="Set min/max from the frame on screen">Auto (this frame)</button><button data-a="full">Full range</button></div>
      <label class="chk" title="Re-stretch the contrast on every frame while scrubbing or playing"><input type="checkbox" class="af">Auto contrast on every frame</label>`;
    const [vis, , color] = [d.querySelector('h3 input[type=checkbox]'), null, d.querySelector('input[type=color]')];
    const preset = d.querySelector('select'), nums = d.querySelectorAll('input[type=number]'), gam = d.querySelector('input[type=range]'), gv = d.querySelector('.gv');
    c.el = {hist: d.querySelector('canvas'), lo: nums[0], hi: nums[1], stats: d.querySelector('.stats')};
    const af = d.querySelector('.af'); af.checked = !!c.autoFrame;
    af.onchange = () => { c.autoFrame = af.checked; if (c.autoFrame) { c.lo = c.flo; c.hi = c.fhi; } sync(); };
    preset.value = c.preset;
    const sync = () => { widen(c); nums[0].value = +c.lo.toPrecision(6); nums[1].value = +c.hi.toPrecision(6); drawHist(c); request(true); };
    vis.onchange = () => { c.visible = vis.checked; request(true); };
    preset.onchange = () => { c.preset = preset.value; sync(); };
    color.oninput = () => { c.color = color.value; sync(); };
    nums[0].onchange = () => { c.lo = +nums[0].value; c.autoFrame = af.checked = false; sync(); };
    nums[1].onchange = () => { c.hi = +nums[1].value; c.autoFrame = af.checked = false; sync(); };
    gam.oninput = () => { c.gamma = Math.pow(2, -gam.value); gv.textContent = c.gamma.toFixed(2); sync(); };
    d.querySelector('[data-a=full]').onclick = () => { c.autoFrame = af.checked = false; c.lo = c.dmin; c.hi = c.dmax; c.hmax = c.dmax; computeHists(true); sync(); };
    d.querySelector('[data-a=auto]').onclick = () => { c.lo = c.flo; c.hi = c.fhi; widen(c); computeHists(true); sync(); };
    const cv = c.el.hist;
    cv.addEventListener('mousedown', e => {
      const rc = cv.getBoundingClientRect(), rng = c.hmax - c.hmin || 1;
      const val = x => c.hmin + clamp((x - rc.left) / rc.width, 0, 1) * rng;
      const v0 = val(e.clientX), which = Math.abs(v0 - c.lo) < Math.abs(v0 - c.hi) ? 'lo' : 'hi';
      c.autoFrame = false; d.querySelector('.af').checked = false;
      const mv = ev => { const v = val(ev.clientX); if (which === 'lo') c.lo = Math.min(v, c.hi - rng * 1e-4); else c.hi = Math.max(v, c.lo + rng * 1e-4); sync(); };
      mv(e); const up = () => { removeEventListener('mousemove', mv); removeEventListener('mouseup', up); };
      addEventListener('mousemove', mv); addEventListener('mouseup', up);
    });
    box.appendChild(d); sync();
  });
}

// ---------- gallery ----------
function buildGallery() {
  const gal = $('gallery');
  if (NM <= 1 || !D.thumbs || !UI.gallery || BASE_AXIS) { gal.style.display = 'none'; return; }
  D.thumbs.forEach((src, m) => {
    const b = document.createElement('button'); b.className = 'th'; b.title = AX.M.names[m];
    b.innerHTML = `<img src="data:image/png;base64,${src}" alt=""><span>${AX.M.names[m]}</span>`;
    b.onclick = () => setAxis('M', m); gal.appendChild(b);
  });
}
function markGallery() { const ths = $('gallery').querySelectorAll('.th'); ths.forEach((b, m) => b.classList.toggle('sel', m === st.m));
  const s = ths[st.m]; if (s) s.scrollIntoView({block: 'nearest'}); }

// ---------- overlays, panel, misc ----------
function buildOverlays() {
  const box = $('ovl'), items = [['scalebar', 'Scale bar', !!D.pixelSize], ['time', 'Time stamp', NT > 1 && !!D.times], ['z', 'Z depth', NZ > 1],
    ['names', 'Channel names', NC > 1], ['position', 'Position name', NM > 1]];
  for (const [k, txt, ok] of items) { if (!ok) continue;
    const l = document.createElement('label'); l.className = 'chk'; l.innerHTML = `<input type="checkbox" ${ovl[k] ? 'checked' : ''}>${txt}`;
    l.querySelector('input').onchange = ev => { ovl[k] = ev.target.checked; request(); }; box.appendChild(l); }
  if (!box.children.length) box.innerHTML = '<span class="sub">No overlays available for this file.</span>';
}

$('btnFit').onclick = fit;
$('btnRuler').onclick = () => { st.rulerOn = !st.rulerOn; $('btnRuler').classList.toggle('on', st.rulerOn); view.classList.toggle('ruler', st.rulerOn); if (!st.rulerOn) { st.ruler = null; request(); } };
$('btnOrtho').onclick = () => { st.ortho = !st.ortho; $('btnOrtho').classList.toggle('on', st.ortho); request(); setTimeout(() => request(), 30); };
if (NZ <= 1) $('btnOrtho').style.display = 'none';
function modal(text) { $('modalText').textContent = text; $('modal').style.display = 'flex'; }
$('modalClose').onclick = () => { $('modal').style.display = 'none'; };
$('modal').onclick = e => { if (e.target === $('modal')) $('modal').style.display = 'none'; };
$('btnMeta').onclick = () => modal(D.info.join('\n'));
$('btnKeys').onclick = () => modal(['Space\tplay / pause', '← →\tprevious / next time point', '↑ ↓\tprevious / next Z slice',
  'PgUp PgDn\tprevious / next page (or position)', 'Click a tile\thistograms follow that tile',
  'Double-click a tile\topen it alone above the panel, then as a time / Z panel', 'Esc\tback to the panel (also: click outside)', 'Wheel\tzoom (synced across tiles)', 'Drag\tpan', 'Double-click or 0\tfit', 'R\truler on/off', 'Esc\tclear ruler'].join('\n'));
$('btnSnap').onclick = () => {
  draw(); const a = document.createElement('a'); a.download = `${D.name}_snapshot.png`;
  view.toBlob(b => { a.href = URL.createObjectURL(b); a.click(); setTimeout(() => URL.revokeObjectURL(a.href), 2000); });
};
addEventListener('keydown', e => {
  if (e.target.tagName === 'INPUT' || e.target.tagName === 'SELECT') return;
  const step = (a, d) => { const n = a === 'T' ? NT : a === 'Z' ? NZ : NM, cur = a === 'T' ? st.t : a === 'Z' ? st.z : st.m; if (n > 1) setAxis(a, (cur + d + n) % n); };
  if (e.key === ' ') { e.preventDefault(); if (UI.playback && !$('play').disabled) setPlaying(!st.playing); }
  else if (e.key === 'ArrowRight') step('T', 1); else if (e.key === 'ArrowLeft') step('T', -1);
  else if (e.key === 'ArrowUp') { e.preventDefault(); step('Z', 1); } else if (e.key === 'ArrowDown') { e.preventDefault(); step('Z', -1); }
  else if (e.key === 'PageDown' || e.key === 'PageUp') { const d = e.key === 'PageDown' ? 1 : -1;
    if (pageGeom(st.panelAxis).pages > 1 && 'TZM'.includes(st.panelAxis || '_')) setPage(st.page + d); else if (st.panelAxis !== 'M') step('M', d); }
  else if (e.key === '0') { if (UI.zoom) fit(); } else if ((e.key === 'r' || e.key === 'R') && UI.ruler) $('btnRuler').click();
  else if (e.key === 'Escape') { const open = $('modal').style.display === 'flex'; st.ruler = null; $('modal').style.display = 'none';
    if (!open && pop) closePop(); request(); }
});
addEventListener('resize', () => { request(); ch.forEach(drawHist); });

// ---------- start ----------
(async function init() {
  const title = D.title || D.name;
  $('title').textContent = title; document.title = title + ' \u2014 ImageStudios';
  $('caption').textContent = D.caption || '';
  if (UI.theme === 'light') document.body.classList.add('light');
  const hide = (...ids) => ids.forEach(i => { const el = $(i); if (el) el.style.display = 'none'; });
  if (!UI.playback) hide('grpPlay');
  if (!UI.projections) hide('grpProj');
  if (!UI.ortho) hide('btnOrtho');
  if (!UI.zoom) hide('btnFit');
  if (!UI.ruler) hide('btnRuler');
  if (!UI.inspector) hide('status');
  if (!UI.snapshot) hide('btnSnap');
  if (!UI.metadata) hide('btnMeta');
  if (!UI.lut) hide('hLut', 'luts');
  if (!UI.overlayToggles) hide('hOvl', 'ovl');
  if (!UI.lut && !UI.overlayToggles) hide('side');
  if (!UI.playback && !UI.projections && !UI.ortho && !UI.zoom && !UI.ruler) hide('ctlRow');
  $('subtitle').textContent = D.subtitle || '';
  if (!('DecompressionStream' in window)) { modal('This browser is too old to open ImageStudios viewers (needs DecompressionStream). Use a current Chrome, Edge, Firefox or Safari.'); return; }
  ch.forEach(c => { c.autoLo = c.lo; c.autoHi = c.hi; c.hmin = c.dmin; c.hmax = defaultHmax(c); c.autoFrame = !!D.autoFrame; });
  buildAxes(); buildLuts(); buildGallery(); buildOverlays(); syncPanelAxisUI();
  const s0 = D.start || {};
  st.t = Math.min(NT - 1, s0.t || 0); st.z = Math.min(NZ - 1, s0.z || 0);
  await setAxis('M', Math.min(NM - 1, s0.m || 0));
  if (UI.autoplay && UI.playback && !$('play').disabled) setPlaying(true);
})();
</script>
</body></html>
"""
