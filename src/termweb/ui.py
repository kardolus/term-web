"""Minimal dark UI — deliberately not the flightdeck design system. One inline
CSS block, JetBrains Mono, green accent. xterm.js pinned from jsdelivr with SRI.
"""

XTERM_JS = ("https://cdn.jsdelivr.net/npm/@xterm/xterm@5.5.0/lib/xterm.min.js",
            "sha384-J4qzUjBl1FxyLsl/kQPQIOeINsmp17OHYXDOMpMxlKX53ZfYsL+aWHpgArvOuof9")
XTERM_CSS = ("https://cdn.jsdelivr.net/npm/@xterm/xterm@5.5.0/css/xterm.min.css",
             "sha384-tStR1zLfWgsiXCF3IgfB3lBa8KmBe/lG287CL9WCeKgQYcp1bjb4/+mwN6oti4Co")
XTERM_FIT = ("https://cdn.jsdelivr.net/npm/@xterm/addon-fit@0.10.0/lib/addon-fit.min.js",
             "sha384-XGqKrV8Jrukp1NITJbOEHwg01tNkuXr6uB6YEj69ebpYU3v7FvoGgEg23C1Gcehk")

FAVICON_SVG = """<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 64 64">
<rect width="64" height="64" rx="12" fill="#0d1117"/>
<path d="M14 22l12 10-12 10" stroke="#3fb950" stroke-width="5" fill="none"
 stroke-linecap="round" stroke-linejoin="round"/>
<rect x="32" y="40" width="18" height="5" rx="2.5" fill="#3fb950"/>
</svg>"""

_CSS = """
* { box-sizing: border-box; margin: 0; }
:root { --bg:#0d1117; --panel:#161b22; --border:#30363d; --fg:#e6edf3;
        --dim:#8b949e; --accent:#3fb950; --accent-dim:#238636; }
html, body { overflow-x: hidden; }  /* the page never side-scrolls; tables do */
body { background: var(--bg); color: var(--fg); min-height: 100vh;
       font: 14px/1.5 "JetBrains Mono", ui-monospace, SFMono-Regular, Menlo, monospace; }
a { color: var(--accent); text-decoration: none; }
header { display:flex; align-items:center; gap:.75rem; padding:.7rem 1.2rem;
         border-bottom:1px solid var(--border); }
header .brand { color: var(--accent); font-weight:700; }
header .brand::before { content: ">_ "; }
header nav { margin-left:auto; display:flex; gap:1rem; }
header nav a { color: var(--dim); }
main { max-width: 1100px; margin: 0 auto; padding: 1.2rem; }
h2 { font-size: 1rem; color: var(--accent); margin: 1.6rem 0 .6rem;
     text-transform: lowercase; }
h2::before { content: "## "; color: var(--dim); }
.note { color: var(--dim); font-size:.85rem; margin-bottom:.5rem; }
.tablewrap { overflow-x: auto; -webkit-overflow-scrolling: touch; }
table { width:100%; border-collapse: collapse; font-size:.85rem; }
td:last-child { white-space: nowrap; }  /* keep action buttons on one line */
th { text-align:left; color:var(--dim); font-weight:400; padding:.3rem .5rem;
     border-bottom:1px solid var(--border); }
td { padding:.35rem .5rem; border-bottom:1px solid #21262d; vertical-align:top; }
tr:hover td { background: var(--panel); }
.preview { color: var(--dim); max-width: 420px; overflow:hidden;
           text-overflow:ellipsis; white-space:nowrap; }
button, select, input { font:inherit; font-size:.8rem; background:var(--panel);
  color:var(--fg); border:1px solid var(--border); border-radius:6px;
  padding:.25rem .6rem; cursor:pointer; }
input { flex:1; min-width:12rem; cursor:text; }
mark { background: rgba(63,185,80,.25); color: var(--accent);
       border-radius:3px; padding:0 .1em; }
tr.snips td { color: var(--dim); font-size:.8rem; border-bottom:1px solid #21262d; }
tr.snips:hover td { background: transparent; }
button:hover { border-color: var(--accent-dim); color: var(--accent); }
button.primary { background: var(--accent-dim); border-color: var(--accent-dim); }
button.primary:hover { color:#fff; }
.newrow { display:flex; gap:.6rem; align-items:center; flex-wrap:wrap;
          background:var(--panel); border:1px solid var(--border);
          border-radius:8px; padding: .8rem; }
.badge { font-size:.7rem; border:1px solid var(--border); border-radius:10px;
         padding:0 .5rem; color:var(--dim); }
.badge.live { color: var(--accent); border-color: var(--accent-dim); }
#status { color: var(--dim); margin:.8rem 0; min-height:1.2em; }
@media (max-width: 700px) {
  main { padding: .8rem; }
  table { font-size:.8rem; }
  .preview { max-width: 45vw; }
  header { padding:.6rem .8rem; }
}
#term { position: fixed; inset: 3.05rem 0 0 0; padding: 4px; background: var(--bg); }
#overlay { position: fixed; inset: 0; display:none; align-items:center;
  justify-content:center; background: rgba(13,17,23,.85); z-index: 10; }
#overlay .box { background:var(--panel); border:1px solid var(--border);
  border-radius:10px; padding:1.5rem 2rem; text-align:center; }
#overlay .box p { margin-bottom: 1rem; }
"""


def page(title: str, body: str, head_extra: str = "") -> str:
    return f"""<!doctype html>
<html lang="en"><head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<meta name="robots" content="noindex, nofollow">
<title>{title}</title>
<link rel="icon" href="/favicon.svg" type="image/svg+xml">
<style>{_CSS}</style>
{head_extra}
</head><body>
<header><span class="brand">term</span><span class="badge">forge</span>
<nav><a href="/">sessions</a><a href="/auth/logout">logout</a></nav></header>
{body}
</body></html>"""


PICKER_BODY = """
<main>
<div id="status">loading sessions…</div>

<h2>new session</h2>
<div class="newrow">
  <select id="new-agent"><option value="claude">claude</option><option value="codex">codex</option></select>
  <span class="note">in</span>
  <select id="new-dir"></select>
  <button class="primary" onclick="launchNew()">launch</button>
</div>

<h2>claude archive</h2>
<div class="note">all machines, synced to forge every 5 min. "open in codex" hands the other agent a transcript digest.</div>
<div class="newrow" style="margin-bottom:.6rem">
  <input id="q" placeholder="search transcripts — all terms must match"
         onkeydown="if(event.key==='Enter')doSearch()"
         oninput="if(!this.value.trim())clearSearch()">
  <button class="primary" onclick="doSearch()">search</button>
</div>
<div class="tablewrap" id="results-wrap" style="display:none">
  <table id="results"><thead><tr><th>when</th><th>host</th><th>project</th><th>size</th><th>matches</th><th></th></tr></thead><tbody></tbody></table>
</div>
<div class="tablewrap" id="claude-wrap"><table id="claude"><thead><tr><th>when</th><th>host</th><th>project</th><th>size</th><th>preview</th><th></th></tr></thead><tbody></tbody></table></div>

<h2>codex sessions</h2>
<div class="note">forge-local only — codex sessions from other machines aren't synced.</div>
<div class="tablewrap"><table id="codex"><thead><tr><th>when</th><th>dir</th><th>size</th><th>preview</th><th></th></tr></thead><tbody></tbody></table></div>
</main>
<script>
const esc = s => { const d = document.createElement('span'); d.textContent = s ?? ''; return d.innerHTML; };
async function launch(target) {
  document.getElementById('status').textContent = 'starting terminal…';
  const r = await fetch('/api/terminal', {method:'POST',
    headers:{'Content-Type':'application/json'}, body: JSON.stringify(target)});
  if (!r.ok) { document.getElementById('status').textContent =
    'error: ' + ((await r.json()).error || r.status); return; }
  const {ticket, name} = await r.json();
  location.href = '/t/' + encodeURIComponent(name) + '#' + ticket;
}
function launchNew() {
  launch({kind:'new', agent: document.getElementById('new-agent').value,
          workdir: document.getElementById('new-dir').value});
}
function btn(label, target, primary) {
  return `<button class="${primary?'primary':''}" onclick='launch(${JSON.stringify(target)})'>${label}</button>`;
}
const reEsc = t => t.replace(/[.*+?^${}()|[\\]\\\\]/g, '\\\\$&');
function hi(s, terms) {  // esc() every part; <mark> only the matched (odd) parts
  const re = new RegExp('(' + [...terms].sort((a,b) => b.length - a.length).map(reEsc).join('|') + ')', 'gi');
  return s.split(re).map((p, i) => i % 2 ? `<mark>${esc(p)}</mark>` : esc(p)).join('');
}
async function doSearch() {
  const q = document.getElementById('q').value.trim();
  if (!q) return clearSearch();
  document.getElementById('status').textContent = 'searching…';
  let d;
  try {
    const r = await fetch('/api/search?q=' + encodeURIComponent(q));
    if (r.status === 401) { location.href = '/auth/login'; return; }
    if (!r.ok) throw new Error(r.status);
    d = await r.json();
  } catch (e) {
    document.getElementById('status').textContent = 'search failed — try again';
    return;
  }
  document.getElementById('status').textContent =
    d.claude.length ? '' : 'no matches for "' + q + '"';
  const terms = d.terms;  // the server's canonical list — highlight exactly what matched
  document.querySelector('#results tbody').innerHTML = d.claude.map(s =>
    `<tr><td>${esc(s.when)}</td><td>${esc(s.host)}</td><td>${esc(s.project)}</td>
     <td>${s.kb}K</td><td>${s.matches}</td>
     <td>${btn('open in claude', {kind:'claude', uuid:s.uuid}, true)}
         ${btn('open in codex', {kind:'cross', source:'claude', uuid:s.uuid}, false)}</td></tr>` +
    s.snippets.map(t => `<tr class="snips"><td colspan="6">${hi(t, terms)}</td></tr>`).join('')
  ).join('');
  document.getElementById('results-wrap').style.display = '';
  document.getElementById('claude-wrap').style.display = 'none';
}
function clearSearch() {
  document.getElementById('results-wrap').style.display = 'none';
  document.getElementById('claude-wrap').style.display = '';
  document.getElementById('status').textContent = '';
}
async function load() {
  const r = await fetch('/api/sessions');
  if (r.status === 401) { location.href = '/auth/login'; return; }
  const d = await r.json();
  document.getElementById('status').textContent = '';
  const dirs = d.workdirs.map(w => `<option>${esc(w)}</option>`).join('');
  document.getElementById('new-dir').innerHTML = dirs;
  document.querySelector('#claude tbody').innerHTML = d.claude.map(s =>
    `<tr><td>${esc(s.when)}</td><td>${esc(s.host)}</td><td>${esc(s.project)}</td>
     <td>${s.kb}K</td><td class="preview" title="${esc(s.preview)}">${esc(s.preview)}</td>
     <td>${btn('open in claude', {kind:'claude', uuid:s.uuid}, true)}
         ${btn('open in codex', {kind:'cross', source:'claude', uuid:s.uuid}, false)}</td></tr>`).join('');
  document.querySelector('#codex tbody').innerHTML = d.codex.map(s =>
    `<tr><td>${esc(s.when)}</td><td>${esc((s.cwd||'').split('/').pop())}</td>
     <td>${s.kb}K</td><td class="preview" title="${esc(s.preview)}">${esc(s.preview)}</td>
     <td>${btn('open in codex', {kind:'codex', uuid:s.uuid}, true)}
         ${btn('open in claude', {kind:'cross', source:'codex', uuid:s.uuid}, false)}</td></tr>`).join('');
}
load();
</script>
"""


def terminal_body(name: str) -> str:
    js_url, js_sri = XTERM_JS
    fit_url, fit_sri = XTERM_FIT
    return f"""
<div id="term"></div>
<div id="overlay"><div class="box"><p id="overlay-msg">session ended</p>
<button class="primary" onclick="location.href='/'">back to sessions</button></div></div>
<script src="{js_url}" integrity="{js_sri}" crossorigin="anonymous"></script>
<script src="{fit_url}" integrity="{fit_sri}" crossorigin="anonymous"></script>
<script>
const NAME = {name!r};
const term = new Terminal({{
  fontFamily: '"JetBrains Mono", ui-monospace, Menlo, monospace',
  fontSize: 14, scrollback: 5000, cursorBlink: true,
  theme: {{ background: '#0d1117', foreground: '#e6edf3', cursor: '#3fb950',
           selectionBackground: '#264f78' }},
}});
const fit = new FitAddon.FitAddon();
term.loadAddon(fit);
term.open(document.getElementById('term'));
fit.fit();
let ws, exited = false;
function connect(ticket) {{
  exited = false;
  ws = new WebSocket((location.protocol === 'https:' ? 'wss://' : 'ws://')
                     + location.host + '/ws/term?ticket=' + encodeURIComponent(ticket));
  ws.binaryType = 'arraybuffer';
  ws.onopen = () => {{ fit.fit();
    ws.send(JSON.stringify({{t:'r', cols: term.cols, rows: term.rows}}));
    term.focus(); }};  // nothing focuses the terminal otherwise — keys would go to <body>
  ws.onmessage = ev => {{
    if (typeof ev.data === 'string') {{
      const m = JSON.parse(ev.data);
      if (m.t === 'exit') {{ exited = true;
        showOverlay('session ended (exit ' + m.code + ')'); }}
    }} else term.write(new Uint8Array(ev.data));
  }};
  ws.onclose = () => {{ if (!exited) showOverlay('disconnected — resume from the picker'); }};
}}
function showOverlay(msg) {{
  document.getElementById('overlay-msg').textContent = msg;
  document.getElementById('overlay').style.display = 'flex';
}}
term.onData(d => {{ if (ws && ws.readyState === 1) ws.send(JSON.stringify({{t:'i', d}})); }});
window.addEventListener('focus', () => term.focus());
window.addEventListener('resize', () => {{ fit.fit();
  if (ws && ws.readyState === 1)
    ws.send(JSON.stringify({{t:'r', cols: term.cols, rows: term.rows}})); }});
const ticket = location.hash.slice(1);
history.replaceState(null, '', location.pathname);  // ticket is one-shot; drop it
if (ticket) connect(ticket); else location.href = '/';  // no ticket -> picker
</script>
"""
