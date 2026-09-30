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
const { LiveMemory } = require('./lib/liveMemory');

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
  const out = { port: 8099, save: null, poll: 1000, host: '127.0.0.1',
                liveMemory: false, python: 'python', hz: 20 };
  for (let i = 2; i < argv.length; i++) {
    const a = argv[i];
    if (a === '--port') out.port = Number(argv[++i]);
    else if (a === '--save') out.save = argv[++i];
    else if (a === '--poll') out.poll = Number(argv[++i]);
    else if (a === '--host') out.host = argv[++i];
    // Bind every interface so phones/tablets on the same Wi-Fi can open it.
    else if (a === '--lan') out.host = '0.0.0.0';
    // Opt-in only: reads the running game for a real-time player dot.
    else if (a === '--live-memory') out.liveMemory = true;
    else if (a === '--python') out.python = argv[++i];
    else if (a === '--hz') out.hz = Number(argv[++i]);
    // How long to keep running after the last page request. The launcher hides
    // the console, so this is what stops an invisible server outliving the page.
    else if (a === '--idle-exit') out.idleExit = Number(argv[++i]);
    else if (a === '--no-idle-exit') out.noIdleExit = true;
    else if (a === '--help' || a === '-h') out.help = true;
  }
  return out;
}

/**
 * %APPDATA%/EldenRing/<steamId>/ER0000.{err,sl2} - pick the most recent.
 * Elden Ring Reforged saves as ER0000.err, vanilla as ER0000.sl2, and both may
 * be present. Prefer .err when it is at least as recent, so a modded run is not
 * masked by a stale vanilla save.
 */
function findSave() {
  const appdata = process.env.APPDATA || path.join(os.homedir(), 'AppData', 'Roaming');
  const base = path.join(appdata, 'EldenRing');
  const candidates = [];
  try {
    for (const dir of fs.readdirSync(base)) {
      if (!/^\d+$/.test(dir)) continue;
      for (const ext of ['err', 'sl2']) {
        const p = path.join(base, dir, `ER0000.${ext}`);
        try {
          const st = fs.statSync(p);
          if (st.isFile()) candidates.push({ path: p, ext, mtimeMs: st.mtimeMs });
        } catch { /* not present */ }
      }
    }
  } catch { /* no EldenRing folder */ }
  if (!candidates.length) return null;
  candidates.sort((a, b) => b.mtimeMs - a.mtimeMs || (a.ext === 'err' ? -1 : 1));
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
 * Markers come from four generated files: markers.json (graces, bosses, POIs,
 * map fragments - built from the param tables), the optional items.json (item
 * pickups - needs the slower MSB extraction), the optional pieces.json (Reforged
 * Rune/Ember Piece collectibles) and the optional npcs.json (merchants, read out
 * of the same MSB pass as items.json). Any of them may be absent.
 */
const markerData = loadJson(path.join(DATA, 'markers.json'), { markers: [] });
const itemData = loadJson(path.join(DATA, 'items.json'), { markers: [] });
const pieceData = loadJson(path.join(DATA, 'pieces.json'), { markers: [] });
const npcData = loadJson(path.join(DATA, 'npcs.json'), { markers: [] });
const dropData = loadJson(path.join(DATA, 'drops.json'), { markers: [] });
const bossDropData = loadJson(path.join(DATA, 'boss-drops.json'), { markers: [] });
const emevdDropData = loadJson(path.join(DATA, 'emevd-drops.json'), { markers: [] });
// Farm spots (tools/extract_farm_nodes.py): enemy placements carrying a farmable
// lot. Optional like the rest - a fresh clone has no farm.json until it is run.
const farmData = loadJson(path.join(DATA, 'farm.json'), { markers: [] });
const MARKERS = [...(markerData.markers || []), ...(itemData.markers || []),
                 ...(pieceData.markers || []), ...(npcData.markers || []),
                 ...(dropData.markers || []), ...(bossDropData.markers || []), ...(emevdDropData.markers || []),
                 ...(farmData.markers || [])];
const FLAG_MARKERS = MARKERS.filter((m) => m.flag || (m.flags && m.flags.length));

/**
 * Route descriptions, if the user has fetched them (tools/fetch_tips.py).
 *
 * Optional and deliberately separate: unlike everything else in data/, this
 * text is neither the user's own game files nor ours - it is third-party wiki
 * writing sitting on their disk for their own use. Absent by default, and the
 * app is complete without it.
 */
const tipData = loadJson(path.join(DATA, 'tips.json'), { tips: {} });
const TIPS = tipData.tips || {};
let tipped = 0;
for (const m of MARKERS) {
  const tip = TIPS[m.id];
  if (tip && tip.text) { m.tip = tip; tipped++; }
}

const MARKER_DOC = {
  locales: markerData.locales || ['en'],
  markers: MARKERS,
  // The game's region labels (build_markers.py). Sent to the client rather than
  // stamped onto every marker: the client also labels things the server never
  // sees, such as the live player position, and it can do the whole lookup with
  // one pass over this handful of rows.
  regions: loadJson(path.join(DATA, 'regions.json'), { regions: [] }).regions || [],
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
let live = null;         // optional LiveMemory bridge
let activeSlot = null;   // the slot on screen: picked in the sidebar, or matched to the running game
let slotVotes = {};      // slot -> consecutive wins, for the re-match hysteresis

const hasSlot = (snap, slot) => snap.characters.some((c) => c.slot === slot);

/** The character the browser shows: the active slot, else the first occupied one. */
function shownCharacter(snap) {
  return snap.characters.find((c) => c.slot === activeSlot) || snap.characters[0] || null;
}

/**
 * Show this slot, and remember it for the save so the map reopens on the same
 * character next time. Both the dropdown and the live matcher land here, so
 * "remembered" means whichever character was on screen last.
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

/**
 * Live height, from the player's world position - and the check that decides
 * whether to believe it.
 *
 * The reader cannot tell which of its candidate pointer chains is the right
 * one, so it sends every reading. The map-screen pixel it also sends is already
 * trusted, and in the overworld that pixel is a fixed function of the tile and
 * the block-local x/z:
 *
 *     px = block * 256 + 128 + x + OFFSET_X
 *     py = OFFSET_Y - (mapno * 256 + 128 + z)
 *
 * so inverting it recovers the tile the player is standing on - but only if x
 * and z are genuinely this player's coordinates. A chain pointing at the wrong
 * struct gives numbers that land between tiles, and is rejected. The reading
 * that resolves to whole tiles is the real one, and its y is the height.
 *
 * Legacy dungeons are deliberately not handled: their coordinates are local to
 * the dungeon while the pixel is the translated overworld position, so there is
 * nothing to check against and the save height stands in.
 */
const TILE_EPSILON = 0.01;     // 0.1px of map-screen rounding is ~0.0004 tiles
const TILE_MAX = 80;

function liveHeight(p) {
  if (!p || !Array.isArray(p.worlds) || typeof p.px !== 'number') return null;
  for (const w of p.worlds) {
    const block = (p.px - OFFSET_X - TILE_WORLD / 2 - w.x) / TILE_WORLD;
    const mapno = (OFFSET_Y - p.py - TILE_WORLD / 2 - w.z) / TILE_WORLD;
    const whole = (v) => Math.abs(v - Math.round(v)) < TILE_EPSILON
                      && Math.round(v) >= 0 && Math.round(v) <= TILE_MAX;
    if (whole(block) && whole(mapno)) return Math.round(w.y);
  }
  return null;
}

/**
 * A save holds up to ten characters and the game tells us nothing about which
 * one is loaded. Each character's save position is a good fingerprint though:
 * the running character is the slot whose last saved position is nearest the
 * live one on the same map.
 *
 * Two rules keep one reading from flipping the display for no reason. The
 * slot already on screen keeps its place unless another is nearer by more
 * than a tie margin: two characters resting at the same grace stand on the
 * same spot, so within a few pixels the reading cannot tell them apart, and
 * the one the user picked should not lose to the other on a coin toss. And a
 * reading far from every saved position decides nothing. A character that has
 * never saved has no position at all (the block reads as zeros), and the only
 * alternative would be to hand it to whichever old character is nearest -
 * which is how a brand-new character used to show up as an old one.
 *
 * Returns the slot to show, or null when the reading cannot say.
 */
const SLOT_TIE_PX = 8;        // 1 px is about a metre
const SLOT_MATCH_PX = 1024;   // four tiles: nearer than your last autosave, further than another character

/** The DLC's underground shares the DLC's pixel space (project.js never emits M11). */
const mapFamily = (master) => (master === 'M11' ? 'M10' : master);

function matchActiveSlot(position) {
  if (!current || !position) return null;
  const near = [];
  for (const character of current.characters) {
    const saved = character.mapPixel;
    if (!saved || mapFamily(saved.master) !== mapFamily(position.master)) continue;
    const distance = Math.hypot(saved.px - position.px, saved.py - position.py);
    if (distance <= SLOT_MATCH_PX) near.push({ slot: character.slot, distance });
  }
  if (!near.length) return null;
  near.sort((a, b) => a.distance - b.distance);
  const shown = near.find((c) => c.slot === activeSlot);
  if (shown && shown.distance <= near[0].distance + SLOT_TIE_PX) return activeSlot;
  return near[0].slot;
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
    live: live ? live.state : { enabled: false, status: 'off' },
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

const MIME = {
  '.html': 'text/html; charset=utf-8', '.js': 'text/javascript; charset=utf-8',
  '.css': 'text/css; charset=utf-8', '.json': 'application/json; charset=utf-8',
  '.webp': 'image/webp', '.png': 'image/png', '.jpg': 'image/jpeg',
  '.svg': 'image/svg+xml', '.ico': 'image/x-icon', '.woff2': 'font/woff2',
};

function serveStatic(req, res, urlPath) {
  const rel = decodeURIComponent(urlPath.replace(/^\/+/, '')) || 'index.html';
  const file = path.join(WEB, rel);
  // Containment is checked with path.relative, not a string prefix. A prefix
  // test ("file.startsWith(WEB)") also accepts a *sibling* whose name merely
  // begins with "web" - a directory next to web/ called "web-backup" would pass
  // it - so a crafted path could step outside web/ and read those files.
  // Resolving the relative path and rejecting anything that climbs out ("..")
  // or lands on an absolute path (a different Windows drive) closes that.
  const within = path.relative(WEB, path.resolve(file));
  if (within.startsWith('..') || path.isAbsolute(within)) {
    res.writeHead(403).end('forbidden');
    return;
  }
  fs.stat(file, (err, st) => {
    if (err || !st.isFile()) {
      res.writeHead(404, { 'Content-Type': 'text/plain' }).end('not found');
      return;
    }
    const ext = path.extname(file).toLowerCase();
    res.writeHead(200, {
      'Content-Type': MIME[ext] || 'application/octet-stream',
      'Content-Length': st.size,
      'Cache-Control': ext === '.webp' || ext === '.png' ? 'public, max-age=86400' : 'no-cache',
    });
    fs.createReadStream(file).pipe(res);
  });
}

function json(res, obj, code = 200) {
  const body = JSON.stringify(obj);
  res.writeHead(code, { 'Content-Type': 'application/json; charset=utf-8',
                        'Content-Length': Buffer.byteLength(body) });
  res.end(body);
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
    console.log('  --live-memory   读取正在运行的游戏以显示实时位置 / also read the running game for a live player dot');
    console.log('                  （只读、需要管理员权限、失败会静默回退 / read-only, needs admin, falls back silently）');
    console.log('  --hz <n>        实时读取采样率 / live-memory sample rate (default 20)');
  console.log('  --idle-exit <ms> 页面都关掉后多久退出这个服务 / exit this long after the last page request');
  console.log('  --no-idle-exit  不因页面关闭而退出 / keep running with no page open');
    console.log('  --python <exe>  实时读取器使用的 python / python used for the live reader (default python)');
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
    console.error('先运行 Setup.bat（Linux 上是 ./setup-linux.sh），它会取来这个文件并生成标记数据。');
    console.error('Run Setup.bat first (./setup-linux.sh on Linux): it fetches this file and builds the marker data.');
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
      if (req.method !== 'POST') return json(res, { error: 'POST required' }, 405);
      // sendBeacon always carries Origin; refuse anything that is not this page, so a
      // random website cannot stop someone's map.
      const origin = req.headers.origin;
      if (origin && !/^https?:\/\/(localhost|127\.0\.0\.1|\[::1\])(:\d+)?$/.test(origin)) {
        return json(res, { error: 'origin not allowed' }, 403);
      }
      byeAt = Date.now();
      return json(res, { ok: true });
    }

    if (p === '/api/state') return json(res, current);
    if (p === '/api/markers') return json(res, MARKER_DOC);

    if (p === '/api/saves' && req.method === 'GET') {
      const saves = listSaves(savePath).map((s) => ({
        ...s,
        characters: readSaveCharacters(s.path, bst),
      }));
      return json(res, { current: savePath, slot: activeSlot, saves });
    }
    if (p === '/api/saves' && req.method === 'POST') {
      let body = '';
      req.on('data', (chunk) => { body += chunk; if (body.length > 65536) req.destroy(); });
      req.on('end', () => {
        try {
          const { path: nextPath, slot } = JSON.parse(body);
          switchSave(nextPath, Number.isInteger(slot) ? slot : null);
          json(res, { ok: true, current: savePath, slot: activeSlot });
        } catch (error) { json(res, { error: error.message }, 400); }
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
      if (live && live.pos) {
        res.write(`event: pos\ndata: ${JSON.stringify(live.pos)}\n\n`);
      }
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
          if (typeof id !== 'string') return json(res, { error: 'id required' }, 400);
          if (on) userState.checked[id] = true;
          else delete userState.checked[id];
          saveUserState();
          if (current) current.checked = userState.checked;
          broadcast('checked', { id, on: !!on });
          json(res, { ok: true });
        } catch (e) { json(res, { error: e.message }, 400); }
      });
      return undefined;
    }

    if (p === '/api/refresh') {
      try {
        current = buildSnapshot(reader, savePath);
        current.activeSlot = activeSlot;
        broadcast('state', { ...current, newlyFound: [] });
        return json(res, { ok: true });
      } catch (e) { return json(res, { error: e.message }, 500); }
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
      if (req.method !== 'POST') return json(res, { error: 'POST required' }, 405);
      if (req.headers['x-er-map'] !== '1') return json(res, { error: 'missing X-ER-Map header' }, 403);
      if (!LOOPBACK_HOSTS.has(args.host)) {
        return json(res, { error: 'shutdown is disabled when listening beyond localhost' }, 403);
      }
      console.log('[stop] 网页请求关闭服务，正在退出 / shutdown requested from the browser');
      json(res, { ok: true });
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
    if (live) { try { live.stop(); } catch { /* reader already gone */ } }
    for (const res of clients) { try { res.end(); } catch { /* already gone */ } }
    clients.clear();
    server.close(() => process.exit(0));
    setTimeout(() => process.exit(0), 500).unref();
  }

  stopWatcher = startWatcher(reader, savePath, args.poll);

  if (args.liveMemory) {
    live = new LiveMemory({
      root: ROOT, python: args.python, hz: args.hz,
      onPos: (p) => {
        // Re-match on every sample, but require three consecutive wins before
        // switching. Two characters resting at the same grace, or a frame taken
        // mid-loading-screen, would otherwise flip the displayed character on a
        // single bad reading. It also self-corrects a wrong first match.
        const matched = matchActiveSlot(p);
        if (matched !== null) {
          if (matched !== activeSlot) {
            slotVotes[matched] = (slotVotes[matched] || 0) + 1;
            if (slotVotes[matched] >= 3) setActiveSlot(matched, savePath);
          } else {
            slotVotes = {};
          }
        }
        p.slot = activeSlot;
        const h = liveHeight(p);
        if (h !== null) p.h = h;
        delete p.worlds;          // candidate readings are server-side plumbing
        if (current) current.activeSlot = activeSlot;
        broadcast('pos', p);
      },
      onStatus: (st) => { if (current) current.live = st; broadcast('live', st); },
    });
    live.start();
  }

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
    console.log('  Elden Ring live map / 艾尔登法环实时地图');
    console.log(`  存档 / save      ${savePath}`);
    console.log(`  标记 / markers   ${MARKERS.length} (${FLAG_MARKERS.length} flag-tracked)` +
      (itemData.markers && itemData.markers.length
        ? `  incl. ${itemData.markers.length} items` : '  (no items.json - run tools/extract_items.py)') +
      (pieceData.markers && pieceData.markers.length
        ? `, ${pieceData.markers.length} pieces` : '') +
      (npcData.markers && npcData.markers.length
        ? `, ${npcData.markers.length} merchants` : '') +
      (dropData.markers && dropData.markers.length
        ? `, ${dropData.markers.length} one-time drops` : '') +
      (bossDropData.markers && bossDropData.markers.length
        ? `, ${bossDropData.markers.length} boss rewards` : ''));
    if (tipped) {
      console.log(`  路线 / tips      ${tipped} route descriptions` +
        (tipData.credit ? ` via ${tipData.credit}` : ''));
    }
    if (c) {
      console.log(`  角色 / character ${c.name}, level ${c.level}, ` +
        `${Math.floor(c.secondsPlayed / 3600)}h${String(Math.floor(c.secondsPlayed % 3600 / 60)).padStart(2, '0')}m` +
        `  -> ${c.found.length} found`);
    }
    if (args.liveMemory) {
      console.log('  实时 / live      来自运行中游戏的实时位置（只读） / real-time position from the running game (read-only)');
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
