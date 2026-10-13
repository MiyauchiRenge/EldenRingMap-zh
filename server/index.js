'use strict';
/**
 * Local live-map server for Elden Ring.
 *
 * Watches your save file, decodes it, and pushes progress to the browser over
 * Server-Sent Events. Zero dependencies - Node built-ins only.
 *
 *   node server/index.js [--port 8099] [--save <path to ER0000.sl2>]
 *
 * Read-only: the save is opened for reading and never written.
 */
const http = require('http');
const fs = require('fs');
const path = require('path');
const os = require('os');

const { SaveReader } = require('./lib/saveParser');
const { Projector, TILE_WORLD, OFFSET_X, OFFSET_Y } = require('./lib/project');
const { sendJson, sendFile } = require('./lib/respond');

const ROOT = path.join(__dirname, '..');
const WEB = path.join(ROOT, 'web');
const DATA = path.join(ROOT, 'data');
const USER_STATE = path.join(DATA, 'user-state.json');

/**
 * Bind addresses the quit button accepts. Only these mean "this machine is the
 * only client": the default bind, and the spellings of loopback a user might
 * pass to --host. Anything else - --lan's 0.0.0.0, or a named interface - means
 * the map is reachable from the network, so /api/shutdown stays shut.
 */
const LOOPBACK_HOSTS = new Set(['127.0.0.1', 'localhost', '::1', '::ffff:127.0.0.1']);

/* ------------------------------------------------------------------ config */

function parseArgs(argv) {
  const out = { port: 8099, save: null, poll: 1000, host: '127.0.0.1' };
  for (let i = 2; i < argv.length; i++) {
    const a = argv[i];
    if (a === '--port') out.port = Number(argv[++i]);
    else if (a === '--save') out.save = argv[++i];
    else if (a === '--poll') out.poll = Number(argv[++i]);
    else if (a === '--host') out.host = argv[++i];
    // Bind every interface so phones/tablets on the same Wi-Fi can open it.
    else if (a === '--lan') out.host = '0.0.0.0';
    // How long to keep running after the last page request. The launcher hides
    // the console, so this is what stops an invisible server outliving the page.
    else if (a === '--idle-exit') out.idleExit = Number(argv[++i]);
    else if (a === '--no-idle-exit') out.noIdleExit = true;
    else if (a === '--help' || a === '-h') out.help = true;
  }
  return out;
}

/**
 * %APPDATA%/EldenRing/<steamId>/ER0000.sl2 - the most recently written one.
 *
 * Only the game's own save file is read. Earlier versions also considered
 * ER0000.err, which is what a loose-file mod writes; this branch reads the
 * unmodded game, so a modded save is not something it can interpret.
 */
function findSave() {
  const appdata = process.env.APPDATA || path.join(os.homedir(), 'AppData', 'Roaming');
  const base = path.join(appdata, 'EldenRing');
  const candidates = [];
  try {
    for (const dir of fs.readdirSync(base)) {
      if (!/^\d+$/.test(dir)) continue;
      const p = path.join(base, dir, 'ER0000.sl2');
      try {
        const st = fs.statSync(p);
        if (st.isFile()) candidates.push({ path: p, mtimeMs: st.mtimeMs });
      } catch { /* not present */ }
    }
  } catch { /* no EldenRing folder */ }
  if (!candidates.length) return null;
  candidates.sort((a, b) => b.mtimeMs - a.mtimeMs);
  return candidates[0].path;
}

/** Every ER0000.* under the same %APPDATA%/EldenRing root, newest first. */
function listSaves(selectedPath) {
  const root = path.dirname(path.dirname(selectedPath));
  const saves = [];
  try {
    for (const account of fs.readdirSync(root)) {
      if (!/^\d+$/.test(account)) continue;
      const accountDir = path.join(root, account);
      for (const file of fs.readdirSync(accountDir)) {
        const match = /^ER0000\.([a-z0-9]+)$/i.exec(file);
        if (!match) continue;
        const savePath = path.join(accountDir, file);
        const stat = fs.statSync(savePath);
        if (!stat.isFile()) continue;
        saves.push({ path: savePath, account, extension: `.${match[1].toLowerCase()}`,
                     mtime: stat.mtimeMs });
      }
    }
  } catch { return []; }
  return saves.sort((a, b) => b.mtime - a.mtime);
}

/** Slot names and levels for the save picker. Best-effort: [] if unreadable. */
function readSaveCharacters(savePath, bst) {
  try {
    const reader = new SaveReader(savePath, bst);
    return reader.read().characters.map((c) => ({ slot: c.slot, name: c.name, level: c.level }));
  } catch { return []; }
}

/* ------------------------------------------------------------------- state */

function loadJson(file, fallback) {
  try { return JSON.parse(fs.readFileSync(file, 'utf8')); } catch { return fallback; }
}

const projector = new Projector(loadJson(path.join(DATA, 'legacy-conv.json'), null));

/**
 * Markers come from the generated files under data/ - one file per layer, any of which may be absent
 * on a fresh clone. Which files exist and whether one belongs in the document the page loads first or
 * is fetched straight afterwards is decided by data/layers.json, which tools/erlib/layers.py writes:
 * the two big layers (gatherable nodes, follow-up items) are almost 7 MB together and nothing visible
 * depends on them, so they are marked "lazy" there and reach the page a moment later.
 */
const layerPolicy = loadJson(path.join(DATA, 'layers.json'), { layers: [], cats: {} });

function loadLayers() {
  const initial = [];
  const lazy = new Map();
  const declared = (layerPolicy.layers || []).filter((l) => l.present !== false);
  const ids = declared.length
    ? declared.map((l) => ({ id: l.id, file: l.file, client: l.client || 'initial' }))
    // No policy document (an older data directory): every file that exists is initial.
    : ['markers', 'items', 'npcs', 'drops', 'boss-drops', 'emevd-drops', 'followup',
       'gather-nodes', 'emevd-rewards', 'shop-stock', 'quest-rewards', 'user-verified', 'farm']
      .map((id) => ({ id, file: `${id}.json`, client: 'initial' }));
  for (const { id, file, client } of ids) {
    const doc = loadJson(path.join(DATA, file), null);
    if (!doc || !Array.isArray(doc.markers)) continue;
    if (client === 'lazy') lazy.set(id, doc.markers);
    else initial.push(...doc.markers);
  }
  return { initial, lazy };
}

const { initial: INITIAL_MARKERS, lazy: LAZY_LAYERS } = loadLayers();
const MARKERS = [...INITIAL_MARKERS, ...[...LAZY_LAYERS.values()].flat()];
const FLAG_MARKERS = MARKERS.filter((m) => m.flag || (m.flags && m.flags.length));

const MARKER_DOC = {
  locales: loadJson(path.join(DATA, 'markers.json'), {}).locales || ['en'],
  markers: INITIAL_MARKERS,
  // The lazy layers, by id: the page asks for each of these after its first paint.
  deferredLayers: [...LAZY_LAYERS.keys()],
  // The game's region labels (build_markers.py). Sent to the client rather than
  // stamped onto every marker: the client also labels things the server never
  // sees, such as the player's last saved position, and it can do the whole
  // lookup with one pass over this handful of rows.
  regions: loadJson(path.join(DATA, 'regions.json'), { regions: [] }).regions || [],
  // Which layer each category comes from and whether it counts towards progress
  // (tools/erlib/layers.py writes this). Sent rather than hardcoded in the client
  // so a new layer needs no client edit to be counted correctly.
  layers: layerPolicy,
};

let userState = loadJson(USER_STATE, {});
if (!userState.checked) userState.checked = {};
if (!userState.slots) userState.slots = {};     // save path -> slot on screen last time
function saveUserState() {
  try {
    fs.mkdirSync(DATA, { recursive: true });
    fs.writeFileSync(USER_STATE, JSON.stringify(userState, null, 2));
  } catch (e) { console.error('could not persist user state:', e.message); }
}

/**
 * Marker ids whose event flag is set for this character.
 *
 * A marker can carry several flags. Leyndell, Royal Capital and Leyndell,
 * Ashen Capital are two versions of one map block, so five of its graces exist
 * twice - same pixel, different flag - and build_markers.py folds each pair
 * into a single marker. Any one of the flags means the player has been there.
 */
function computeFound(character) {
  const ef = character._flags;
  if (!ef) return [];
  const found = [];
  for (const m of FLAG_MARKERS) {
    const flags = m.flags || [m.flag];
    if (flags.some((f) => ef.get(f) === true)) found.push(m.id);
  }
  return found;
}

const clients = new Set();
let current = null;      // last good snapshot sent to clients
let activeSlot = null;   // the slot on screen, picked in the sidebar
let slotVotes = {};      // slot -> consecutive wins, for the re-match hysteresis

const hasSlot = (snap, slot) => snap.characters.some((c) => c.slot === slot);

/** The character the browser shows: the active slot, else the first occupied one. */
function shownCharacter(snap) {
  return snap.characters.find((c) => c.slot === activeSlot) || snap.characters[0] || null;
}

/**
 * Show this slot, and remember it for the save so the map reopens on the same
 * character next time.
 */
function setActiveSlot(slot, forPath) {
  activeSlot = slot;
  slotVotes = {};
  if (current) current.activeSlot = slot;
  if (slot === null) delete userState.slots[forPath];
  else userState.slots[forPath] = slot;
  saveUserState();
}

function rememberedSlot(forPath) {
  const slot = userState.slots[forPath];
  return Number.isInteger(slot) ? slot : null;
}

function broadcast(event, payload) {
  const frame = `event: ${event}\ndata: ${JSON.stringify(payload)}\n\n`;
  for (const res of clients) {
    try { res.write(frame); } catch { clients.delete(res); }
  }
}

function buildSnapshot(reader, savePath) {
  const parsed = reader.read();
  const chars = parsed.characters.map((c) => {
    const found = c.ok ? computeFound(c) : [];
    return {
      slot: c.slot,
      name: c.name,
      level: c.level,
      secondsPlayed: c.secondsPlayed,
      ok: c.ok,
      error: c.error || null,
      stats: c.stats || null,
      position: c.position || null,
      mapPixel: c.position ? projector.project(c.position) : null,
      deaths: c.deaths ?? null,
      lastRestedGrace: c.lastRestedGrace ?? null,
      flagOffset: c.flagOffset ?? null,
      found,
    };
  });
  let mtime = null;
  try { mtime = fs.statSync(savePath).mtimeMs; } catch { /* gone */ }
  return {
    savePath,
    mtime,
    encrypted: parsed.encrypted,
    characters: chars,
    markerCount: MARKERS.length,
    checked: userState.checked,
    at: Date.now(),
  };
}

/* ----------------------------------------------------------------- watcher */

function startWatcher(reader, savePath, pollMs) {
  let timer = null;
  const refresh = (reason) => {
    clearTimeout(timer);
    timer = setTimeout(() => {
      let snap;
      try {
        snap = buildSnapshot(reader, savePath);
      } catch (err) {
        console.error(`[watch] parse failed: ${err.message}`);
        broadcast('error', { message: err.message });
        return;
      }
      const prev = current;
      // The slot on screen can vanish - the character deleted in-game, or the
      // file swapped out underneath us - so fall back rather than keep naming
      // a slot that is no longer in the list.
      if (activeSlot !== null && !hasSlot(snap, activeSlot)) setActiveSlot(null, savePath);
      snap.activeSlot = activeSlot;
      current = snap;

      // Report newly-found markers per character so the UI can highlight them.
      const news = [];
      if (prev) {
        for (const c of snap.characters) {
          const before = prev.characters.find((x) => x.slot === c.slot);
          if (!before) continue;
          const had = new Set(before.found);
          const gained = c.found.filter((id) => !had.has(id));
          if (gained.length) news.push({ slot: c.slot, ids: gained });
        }
      }
      broadcast('state', { ...snap, newlyFound: news });
      const c0 = shownCharacter(snap);
      const label = c0 ? `${c0.name} lv${c0.level} ${c0.found.length}/${FLAG_MARKERS.length}` : 'no character';
      console.log(`[watch] ${reason}: ${label}` +
        (news.length ? `  +${news.reduce((n, x) => n + x.ids.length, 0)} new` : ''));
    }, 350);
  };

  // Returns a stop function rather than `refresh`: switching saves has to tear
  // the old watch down, or both files keep pushing snapshots at the browser.
  const onChange = (cur, prev) => {
    if (cur.mtimeMs !== prev.mtimeMs) refresh('save changed');
  };
  fs.watchFile(savePath, { interval: pollMs }, onChange);
  return () => {
    clearTimeout(timer);
    fs.unwatchFile(savePath, onChange);
  };
}

/* -------------------------------------------------------------- http serve */

// Compression, caching and the containment check live in server/lib/respond.js.
function serveStatic(req, res, urlPath) {
  sendFile(req, res, WEB, urlPath.replace(/^\/+/, '') || 'index.html');
}

function json(req, res, obj, code = 200) {
  sendJson(req, res, obj, code);
}

function main() {
  const args = parseArgs(process.argv);
  if (args.help) {
    console.log('用法 / usage: node server/index.js [options]');
    console.log('  --port <n>      监听端口 / listen port (default 8099)');
    console.log('  --save <path>   要监视的 ER0000.sl2 / ER0000.sl2 to watch (default: auto-detect)');
    console.log('  --lan           同时允许局域网访问 / also accept connections from your local network');
    console.log('  --host <addr>   绑定地址 / bind address (default 127.0.0.1)');
    console.log('  --poll <ms>     存档轮询间隔 / save-file poll interval (default 1000)');
  console.log('  --idle-exit <ms> 页面都关掉后多久退出这个服务 / exit this long after the last page request');
  console.log('  --no-idle-exit  不因页面关闭而退出 / keep running with no page open');
    return;
  }

  let savePath = args.save || findSave();
  if (!savePath || !fs.existsSync(savePath)) {
    console.error('未找到 ER0000.sl2 / Could not find ER0000.sl2.');
    console.error('请显式指定 / Pass one explicitly:  node server/index.js --save "C:\\path\\to\\ER0000.sl2"');
    process.exit(1);
  }
  const bst = path.join(DATA, 'eventflag_bst.txt');
  if (!fs.existsSync(bst)) {
    // A fresh clone has nothing under data/ yet, so this is the first thing a new
    // user can hit. Name the fix, not just the missing file.
    console.error(`缺少 ${bst} — 事件旗标分块表是必需的 / missing ${bst} - the event-flag block table is required`);
    console.error('先运行 Setup.bat，它会取来这个文件并生成标记数据。');
    console.error('Run Setup.bat first: it fetches this file and builds the marker data.');
    process.exit(1);
  }
  if (!MARKERS.length) {
    console.warn('警告：data/markers.json 为空，请运行 `python tools/build_markers.py` / warning: data/markers.json is empty - run `python tools/build_markers.py`');
  }

  let reader = new SaveReader(savePath, bst);
  try {
    current = buildSnapshot(reader, savePath);
  } catch (err) {
    console.error('首次解析存档失败 / initial save parse failed:', err.message);
    process.exit(1);
  }
  // Reopen on the character that was on screen last time, if it is still there.
  const remembered = rememberedSlot(savePath);
  activeSlot = hasSlot(current, remembered) ? remembered : null;
  current.activeSlot = activeSlot;

  let stopWatcher = () => {};

  /**
   * Point the server at a character: another ER0000.* file, a slot in the
   * current one, or both. The path must be one listSaves() discovered: it
   * arrives from the browser, and the alternative is letting any page on
   * localhost name an arbitrary file for us to open and parse.
   *
   * A null slot means no preference: the slot remembered for that file, if it
   * still exists. The live matcher is not consulted here - its last sample may
   * be minutes old - so the pick stands until fresh readings from the running
   * game say otherwise.
   */
  const switchSave = (nextPath, slot) => {
    let next = current;
    let nextReader = reader;
    if (nextPath !== savePath) {
      const allowed = listSaves(savePath).some((entry) => entry.path === nextPath);
      if (!allowed) throw new Error('save file is outside the discovered Elden Ring profiles');
      nextReader = new SaveReader(nextPath, bst);
      next = buildSnapshot(nextReader, nextPath);   // parse before tearing down
    }
    if (slot === null) {
      const remembered = rememberedSlot(nextPath);
      if (hasSlot(next, remembered)) slot = remembered;
    }
    if (slot !== null && !hasSlot(next, slot)) throw new Error(`no character in slot ${slot}`);
    if (next !== current) {
      stopWatcher();
      savePath = nextPath;
      reader = nextReader;
      current = next;
      stopWatcher = startWatcher(reader, savePath, args.poll);
    }
    setActiveSlot(slot, savePath);
    broadcast('state', { ...current, newlyFound: [] });
  };

  // ---- staying alive only while a page is open -----------------------------
  // A hidden console must not leave an invisible process behind, so the server exits
  // when the last page goes away. Three pieces, because one is not enough:
  //   * the heartbeat below refreshes lastSeen while a page is open;
  //   * /api/bye starts a short grace period - pagehide fires on a refresh as well,
  //     and the reloaded page pings again within a second, so a refresh survives;
  //   * a generous backstop covers a tab whose timers the browser has throttled.
  let lastSeen = Date.now();
  let byeAt = 0;
  const BYE_GRACE_MS = 8000;
  const IDLE_MS = args.noIdleExit ? 0 : (args.idleExit || 150000);

  const server = http.createServer((req, res) => {
    const url = new URL(req.url, 'http://localhost');
    const p = url.pathname;
    lastSeen = Date.now();

    if (p === '/api/ping') {
      res.writeHead(200, { 'Content-Type': 'application/json; charset=utf-8',
                           'Cache-Control': 'no-store' });
      return res.end(JSON.stringify({ ok: true, idleExit: IDLE_MS }));
    }
    if (p === '/api/bye') {
      if (req.method !== 'POST') return json(req, res, { error: 'POST required' }, 405);
      // sendBeacon always carries Origin; refuse anything that is not this page, so a
      // random website cannot stop someone's map.
      const origin = req.headers.origin;
      if (origin && !/^https?:\/\/(localhost|127\.0\.0\.1|\[::1\])(:\d+)?$/.test(origin)) {
        return json(req, res, { error: 'origin not allowed' }, 403);
      }
      byeAt = Date.now();
      return json(req, res, { ok: true });
    }

    if (p === '/api/state') return json(req, res, current);
    if (p === '/api/markers') return json(req, res, MARKER_DOC);
    if (p.startsWith('/api/layer/')) {
      const id = decodeURIComponent(p.slice('/api/layer/'.length));
      const markers = LAZY_LAYERS.get(id);
      if (!markers) return json(req, res, { error: 'unknown layer', id }, 404);
      return json(req, res, { id, markers });
    }

    if (p === '/api/saves' && req.method === 'GET') {
      const saves = listSaves(savePath).map((s) => ({
        ...s,
        characters: readSaveCharacters(s.path, bst),
      }));
      return json(req, res, { current: savePath, slot: activeSlot, saves });
    }
    if (p === '/api/saves' && req.method === 'POST') {
      let body = '';
      req.on('data', (chunk) => { body += chunk; if (body.length > 65536) req.destroy(); });
      req.on('end', () => {
        try {
          const { path: nextPath, slot } = JSON.parse(body);
          switchSave(nextPath, Number.isInteger(slot) ? slot : null);
          json(req, res, { ok: true, current: savePath, slot: activeSlot });
        } catch (error) { json(req, res, { error: error.message }, 400); }
      });
      return undefined;
    }

    if (p === '/api/events') {
      res.writeHead(200, {
        'Content-Type': 'text/event-stream; charset=utf-8',
        'Cache-Control': 'no-cache, no-transform',
        Connection: 'keep-alive',
        'X-Accel-Buffering': 'no',
      });
      res.write(': connected\n\n');
      res.write(`event: state\ndata: ${JSON.stringify(current)}\n\n`);
      clients.add(res);
      const ka = setInterval(() => { try { res.write(': ka\n\n'); } catch {} }, 20000);
      req.on('close', () => { clearInterval(ka); clients.delete(res); });
      return undefined;
    }

    if (p === '/api/check' && req.method === 'POST') {
      let body = '';
      req.on('data', (d) => { body += d; if (body.length > 1e6) req.destroy(); });
      req.on('end', () => {
        try {
          const { id, on } = JSON.parse(body || '{}');
          if (typeof id !== 'string') return json(req, res, { error: 'id required' }, 400);
          if (on) userState.checked[id] = true;
          else delete userState.checked[id];
          saveUserState();
          if (current) current.checked = userState.checked;
          broadcast('checked', { id, on: !!on });
          json(req, res, { ok: true });
        } catch (e) { json(req, res, { error: e.message }, 400); }
      });
      return undefined;
    }

    if (p === '/api/refresh') {
      try {
        current = buildSnapshot(reader, savePath);
        current.activeSlot = activeSlot;
        broadcast('state', { ...current, newlyFound: [] });
        return json(req, res, { ok: true });
      } catch (e) { return json(req, res, { error: e.message }, 500); }
    }

    // The sidebar's quit button. Three guards, because "stop the server" is the
    // one thing here that a request can do to the machine rather than with it.
    //
    // POST only, so nothing triggers it by being fetched: an <img>, a stylesheet
    // or a link the user clicks can all issue a GET on their behalf.
    //
    // Loopback only. With --lan the map is open to the network, and there anyone
    // who can load the page could also stop it. The route answers as if it were
    // not there, rather than pretending the request was fine.
    //
    // And a custom header, because a loopback bind alone is not enough: another
    // website the user has open can POST to 127.0.0.1 as a "simple request" with
    // no preflight. Asking for X-ER-Map forces one, and this server never
    // answers OPTIONS, so the browser drops the request before it reaches us.
    if (p === '/api/shutdown') {
      if (req.method !== 'POST') return json(req, res, { error: 'POST required' }, 405);
      if (req.headers['x-er-map'] !== '1') return json(req, res, { error: 'missing X-ER-Map header' }, 403);
      if (!LOOPBACK_HOSTS.has(args.host)) {
        return json(req, res, { error: 'shutdown is disabled when listening beyond localhost' }, 403);
      }
      console.log('[stop] 网页请求关闭服务，正在退出 / shutdown requested from the browser');
      json(req, res, { ok: true });
      shutdown();
      return undefined;
    }

    return serveStatic(req, res, p);
  });

  /**
   * Stop everything, then exit.
   *
   * The event streams in `clients` are held open by a browser that is still on
   * the page, and an open socket keeps the process alive, so they are ended
   * before asking Node to leave - server.close() on its own would sit waiting
   * for them. The timer is the backstop for a keep-alive connection that
   * outlives the close callback; the user asked to quit, so we quit.
   */
  let stopping = false;
  function shutdown() {
    if (stopping) return;
    stopping = true;
    try { stopWatcher(); } catch { /* nothing was being watched */ }
    for (const res of clients) { try { res.end(); } catch { /* already gone */ } }
    clients.clear();
    server.close(() => process.exit(0));
    setTimeout(() => process.exit(0), 500).unref();
  }

  stopWatcher = startWatcher(reader, savePath, args.poll);

  if (IDLE_MS > 0) {
    const watchdog = setInterval(() => {
      const now = Date.now();
      if (byeAt && now - byeAt > BYE_GRACE_MS && now - lastSeen > BYE_GRACE_MS) {
        console.log('[exit] 网页已关闭，服务退出 / the page closed, exiting');
        process.exit(0);
      }
      if (now - lastSeen > IDLE_MS) {
        console.log(`[exit] 已有 ${Math.round((now - lastSeen) / 1000)} 秒没有页面请求，服务退出`
                    + ` / no page request for ${Math.round((now - lastSeen) / 1000)}s, exiting`);
        process.exit(0);
      }
    }, 2000);
    watchdog.unref();
  }

  server.listen(args.port, args.host, () => {
    const c = shownCharacter(current);
    console.log('');
    console.log('  交界地地图 / Lands Between Map');
    console.log(`  存档 / save      ${savePath}`);
    console.log(`  标记 / markers   ${MARKERS.length} (${FLAG_MARKERS.length} flag-tracked)`);
    // The layer split, from the registry: what the page gets first, and what follows on its own.
    const known = layerPolicy.layers || [];
    if (known.length) {
      const initial = known.filter((l) => l.present && (l.client || 'initial') !== 'lazy');
      const lazy = known.filter((l) => l.present && l.client === 'lazy');
      console.log(`  图层 / layers    ${initial.length} now` +
        (lazy.length ? `, ${lazy.length} deferred (${lazy.map((l) => l.id).join(', ')})` : ''));
    }
    if (c) {
      console.log(`  角色 / character ${c.name}, level ${c.level}, ` +
        `${Math.floor(c.secondsPlayed / 3600)}h${String(Math.floor(c.secondsPlayed % 3600 / 60)).padStart(2, '0')}m` +
        `  -> ${c.found.length} found`);
    }
    console.log('');
    console.log(`  打开 / open  http://localhost:${args.port}`);
    if (args.host === '0.0.0.0') {
      for (const [, addrs] of Object.entries(os.networkInterfaces())) {
        for (const a of addrs || []) {
          if (a.family === 'IPv4' && !a.internal) {
            console.log(`  局域网 / LAN   http://${a.address}:${args.port}`);
          }
        }
      }
    }
    console.log('');
  });
}

main();
