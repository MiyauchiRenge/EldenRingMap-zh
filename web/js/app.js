import {
  ANIM_INTERVAL_MS,
  CATS,
  CAT_GROUPS,
  CAT_ICON,
  CLUSTER_CELL_PX,
  CLUSTER_STEPS,
  EDGE_PAD,
  FOUND_COLOR,
  OFF_BY_DEFAULT,
  PICK_GROUP_PX,
  PICK_RADIUS,
  UNGROUPED_CATS,
} from './catalog.js';
import {
  $,
  applyLayerPolicy,
  catLabel,
  escapeHtml,
  iconFor,
  isFound,
  map,
  isNoProgress,
  layerLabel,
  nameOf,
  restrictCatsToData,
  setMap,
  state,
  t,
} from './core.js';
import {
  annotatePlace,
  dictName,
  placeLabel,
} from './region.js';

'use strict';
/**
 * Elden Ring live map — client.
 *
 * Talks to the local server: markers + tile manifest once, then a Server-Sent
 * Events stream that pushes a fresh snapshot every time the save file changes.
 */








/* ---------------------------------------------------------------- prefs */

/**
 * What the sidebar looked like last time, kept in localStorage. Purely a
 * convenience: every read and write is wrapped, because localStorage throws
 * rather than returning null in a private window or with site data blocked,
 * and losing your panel layout should never take the map down with it.
 *
 * `known` records which categories existed when the prefs were written. A
 * category added by a later version is therefore absent from it, and takes its
 * own default rather than being silently switched off because an older save
 * did not list it.
 */
const PREFS_KEY = 'er-map-prefs-v1';

function loadPrefs() {
  try {
    const raw = localStorage.getItem(PREFS_KEY);
    return raw ? JSON.parse(raw) : null;
  } catch { return null; }
}

function savePrefs() {
  try {
    localStorage.setItem(PREFS_KEY, JSON.stringify({
      enabled: [...state.enabled],
      known: Object.keys(CATS),
      hideFound: state.hideFound,
      showLabels: state.showLabels,
      showIcons: state.showIcons,
      master: state.master,
      collapsedPanels: [...document.querySelectorAll('.panel.collapsed[data-panel]')]
        .map((el) => el.dataset.panel),
      groupOpen: [...state.groupOpen],
      sidebarCollapsed: document.getElementById('app').classList.contains('sb-collapsed'),
    }));
  } catch { /* storage full or unavailable - the UI still works */ }
}

/** Category toggles and checkboxes, before anything is rendered from them. */
function applyPrefsToState(prefs) {
  if (!prefs) return;
  if (Array.isArray(prefs.enabled)) {
    const on = new Set(prefs.enabled);
    const known = new Set(Array.isArray(prefs.known) ? prefs.known : prefs.enabled);
    state.enabled = new Set(Object.keys(CATS).filter(
      (k) => (known.has(k) ? on.has(k) : !OFF_BY_DEFAULT.has(k))));
  }
  if (typeof prefs.hideFound === 'boolean') state.hideFound = prefs.hideFound;
  if (typeof prefs.showLabels === 'boolean') state.showLabels = prefs.showLabels;
  if (typeof prefs.showIcons === 'boolean') state.showIcons = prefs.showIcons;
  // Honour a saved group layout, but tolerate an older saved state that predates
  // groups (no groupOpen key) - the all-open default then simply stands.
  if (Array.isArray(prefs.groupOpen)) {
    state.groupOpen = new Set(
      prefs.groupOpen.filter((id) => CAT_GROUPS.some((g) => g.id === id)));
  }
}

/** The parts that need the DOM to exist. */
function applyPrefsToUi(prefs) {
  if (!prefs) return;
  for (const name of (prefs.collapsedPanels || [])) {
    const el = document.querySelector(`.panel[data-panel="${CSS.escape(name)}"]`);
    if (el) el.classList.add('collapsed');
  }
  if (prefs.sidebarCollapsed) document.getElementById('app').classList.add('sb-collapsed');
  $('hide-found').checked = state.hideFound;
  $('show-labels').checked = state.showLabels;
  const gi = $('show-icons');
  if (gi) gi.checked = state.showIcons;
}

/* --------------------------------------------------------------- boot */

async function boot() {
  I18n.init();
  I18n.apply();
  buildLangSwitch();

  const [manifest, markerDoc, iconDoc, itemIconDoc, saveDoc] = await Promise.all([
    fetch('tiles/manifest.json').then((r) => r.json()).catch(() => null),
    fetch('api/markers').then((r) => r.json()).catch(() => ({ markers: [] })),
    fetch('icons/index.json').then((r) => r.json()).catch(() => null),
    fetch('icons/items.json').then((r) => r.json()).catch(() => null),
    fetch('api/saves').then((r) => r.json()).catch(() => ({ current: null, saves: [] })),
  ]);
  state.icons = iconDoc && iconDoc.icons ? iconDoc.icons : null;
  // The item's own sprite (bell bearing, rune, smithing stone...), keyed by the
  // iconId extract_items.py read out of EquipParamGoods. Optional: a marker whose
  // table is not wired up yet, or a machine that never ran extract_icons.py,
  // simply has no picture and falls back to the category swatch.
  state.itemIcons = itemIconDoc && itemIconDoc.icons ? itemIconDoc.icons : null;

  state.manifest = manifest;
  state.markers = (markerDoc.markers || []).filter((m) => m.px != null);
  // Rewards the extraction attributed but could not place: no world object, so no coordinates. They can
  // never be pins, so they are kept aside and listed in the "registered" panel instead of being dropped.
  state.registered = (markerDoc.markers || []).filter((m) => m.px == null && m.names);
  state.saves = saveDoc.saves || [];
  state.savePath = saveDoc.current || null;
  for (const m of state.markers) state.byId.set(m.id, m);
  state.regions = markerDoc.regions || [];
  // The layer document (tools/erlib/layers.py) says which categories are "places you can pick
  // something" rather than things you collect once. It is authoritative when present; the historical
  // name test below keeps an older data directory working.
  applyLayerPolicy(markerDoc.layers);
  state.places = state.markers.filter((m) => (m.cat === 'grace' || m.cat === 'poi') && m.names);
  for (const m of state.markers) annotatePlace(m);
  buildRegionButtons();
  state.categoryIconIds = categoryIconIds(state.markers);

  // Before loadPrefs()/buildCategories(): both derive from CATS, and the legend
  // is meant to list the categories this data set has - no more, no less.
  restrictCatsToData();

  if (!manifest || !manifest.masters || !Object.keys(manifest.masters).length) {
    $('foot-text').textContent = t('app.noTiles');
  }

  // Before anything renders, so the categories and checkboxes are built from
  // last session's choices rather than being built and then corrected.
  const prefs = loadPrefs();
  applyPrefsToState(prefs);
  if (prefs && prefs.master && manifest && manifest.masters && manifest.masters[prefs.master]) {
    state.master = prefs.master;
  }

  buildLayerButtons();
  buildCategories();
  buildRegistered();
  initMap(state.master);
  wireUi();
  startKeepAlive();
  applyPrefsToUi(prefs);
  buildSavePicker();
  connect();
  // The layers the server held back (data/layers.json marks them "lazy") arrive after the map is
  // already usable. Nothing waits for them: the page draws, then the heavy layers merge in.
  loadDeferredLayers(markerDoc.deferredLayers);

  // Language changes only ever affect text, so nothing needs reloading.
  I18n.onChange(() => {
    buildLangSwitch();
    buildLayerButtons();
    buildCategories();
    buildRegistered();
    buildSavePicker();          // "Level" in the option labels follows the language
    refreshCounts();
    if (state.character) renderCharacter(state.character);
    if (state.selected) {
      const m = state.byId.get(state.selected);
      if (m) showPopup(m);
    }
    $('toggle-all').textContent = state.enabled.size ? t('panel.selectNone') : t('panel.selectAll');
    if (map) map.requestDraw();
  });
}

/**
 * Merge the layers the server deferred, one request each, as they arrive.
 *
 * A failure is not fatal: those markers are simply missing, and the rest of the map (which is all the
 * server sent in the first place) is already drawn. Counts and the drawn layer are refreshed once per
 * arrival so the progress rows settle as the data lands.
 */
function loadDeferredLayers(ids) {
  for (const id of ids || []) {
    fetch(`api/layer/${encodeURIComponent(id)}`)
      .then((r) => (r.ok ? r.json() : Promise.reject(new Error(r.status))))
      .then((doc) => {
        const added = (doc.markers || []).filter((m) => m.px != null && !state.byId.has(m.id));
        if (!added.length) return;
        for (const m of added) {
          state.byId.set(m.id, m);
          annotatePlace(m);
          state.markers.push(m);
          if ((m.cat === 'grace' || m.cat === 'poi') && m.names) state.places.push(m);
        }
        refreshCounts();
        // A lazy layer's markers can be the only source of a row's item icon, and the category rows were
        // built before they arrived, so rebuild both here.
        state.categoryIconIds = categoryIconIds(state.markers);
        buildCategories();
        if (map) map.requestDraw();
        console.info(`layer ${id}: ${added.length} markers merged`);
      })
      .catch((e) => console.warn(`layer ${id} not loaded:`, e.message));
  }
}

function buildLangSwitch() {
  const wrap = $('lang-switch');
  wrap.innerHTML = '';
  for (const l of window.I18N_LANGS) {
    const b = document.createElement('button');
    b.className = 'lang-btn' + (l.code === I18n.lang ? ' active' : '');
    b.textContent = l.code.toUpperCase();
    b.title = l.label;
    b.onclick = () => I18n.set(l.code);
    wrap.appendChild(b);
  }
}

function masterInfo(id) {
  return (state.manifest && state.manifest.masters && state.manifest.masters[id]) || null;
}

function tileIndexFor(id) {
  const info = masterInfo(id);
  if (!info || !info.tiles) return null;
  const out = {};
  for (const z of Object.keys(info.tiles)) {
    out[z] = new Set(info.tiles[z].map((p) => p[0] + ',' + p[1]));
  }
  return out;
}

/**
 * The region picker: the game's own area names, with how many markers of the
 * current layer sit in each, and a jump to the middle of the chosen one.
 *
 * The names and rectangles come from data/regions.json (WorldMapPlaceNameParam +
 * the map pieces). Most regions have a rectangle; the one that does not is the
 * starting area, which the game reveals without a map piece, so its centre is
 * taken from the markers that ended up in it instead - the same rule that put
 * them there.
 */
function buildRegionButtons() {
  const wrap = $('region-buttons');
  if (!wrap) return;
  wrap.innerHTML = '';
  const usable = state.regions.filter((r) => !r.masters || r.masters.includes(state.master));
  const counts = new Map();
  let inAny = 0;
  for (const m of state.markers) {
    if (m.master !== state.master || !m.region) continue;
    const key = dictName(m.region);
    counts.set(key, (counts.get(key) || 0) + 1);
    inAny++;
  }
  for (const r of usable) {
    const name = dictName(r.names);
    const n = counts.get(name) || 0;
    if (!n) continue;                     // nothing of this layer sits there
    const b = document.createElement('button');
    b.type = 'button';
    b.className = 'layer-btn';
    b.innerHTML = `${escapeHtml(name)}<span class="region-count">${n}</span>`;
    b.onclick = () => goToRegion(r);
    wrap.appendChild(b);
  }
}

/** Centre the map on a region: its rectangle when it has one, else its markers. */
function goToRegion(r) {
  {
    let [x, y] = [(r.rect[0] + r.rect[2]) / 2, (r.rect[1] + r.rect[3]) / 2];
    if (!r.rect) {
      const inside = state.markers.filter((m) => m.master === state.master &&
        m.region && dictName(m.region) === dictName(r.names));
      if (!inside.length) return;
      x = inside.reduce((a, m) => a + m.px, 0) / inside.length;
      y = inside.reduce((a, m) => a + m.py, 0) / inside.length;
    }
    // Fit the rectangle when there is one, otherwise a comfortable zoom on the
    // centroid; flyTo clamps both.
    const zoom = r.rect ? Math.min(map.scale, 0.55) : 0.5;
    map.flyTo(x, y, zoom);
  }
}

function initMap(masterId) {
  const info = masterInfo(masterId);
  const fmt = (state.manifest && state.manifest.format) || 'webp';
  const canvas = $('map');
  if (map) { map.destroy(); map.canvas.replaceWith(canvas.cloneNode()); }

  setMap(new TileMap($('map'), {
    tileSize: (state.manifest && state.manifest.tileSize) || 256,
    width: info ? info.width : 10496,
    height: info ? info.height : 10496,
    nativeZoom: info ? info.nativeZoom : 6,
    tileIndex: tileIndexFor(masterId),
    tileUrl: (z, x, y) => `tiles/${masterId}/${z}/${x}/${y}.${fmt}`,
    drawOverlay: drawMarkers,
    onClick: handleClick,
    onHover: handleHover,
  }));
  map.fit();

  // Dragging the map is a deliberate look-somewhere-else, so it releases
  // follow. Wheel zoom deliberately does not. This lives here rather than in
  // wireUi() because switchMaster() replaces the canvas on every layer change.
  map.canvas.addEventListener('pointerdown', () => setFollow(false));
}

/* ------------------------------------------------------------ marker draw */

function visibleMarkers() {
  const out = [];
  for (const m of state.markers) {
    if (m.master !== state.master) continue;
    if (!state.enabled.has(m.cat)) continue;
    if (state.hideFound && isFound(m)) continue;
    out.push(m);
  }
  return out;
}



/**
 * Grid-cluster so low zooms stay readable.
 *
 * The grid is anchored to the map, not to the window. Keying cells off screen
 * coordinates looks equivalent - the cells are the same size either way - but
 * toScreen() includes the pan centre, so the whole grid slides under the
 * markers as you drag and they cross cell boundaries continuously: groups keep
 * reforming at a zoom level you never changed. Bucketing by master pixel means
 * panning cannot change membership at all.
 *
 * Cell size still has to track zoom to stay a constant size on screen, so it is
 * quantised to discrete steps rather than following the scale continuously.
 * Otherwise every notch of the wheel would reshuffle the groups slightly.
 */
function cluster(list, m) {
  const level = Math.floor(Math.log2(m.scale) * CLUSTER_STEPS) / CLUSTER_STEPS;
  const cellWorld = CLUSTER_CELL_PX / Math.pow(2, level);
  const grid = new Map();
  for (const mk of list) {
    const key = Math.floor(mk.px / cellWorld) + ':' + Math.floor(mk.py / cellWorld);
    let g = grid.get(key);
    if (!g) { g = { px: 0, py: 0, items: [] }; grid.set(key, g); }
    g.px += mk.px; g.py += mk.py; g.items.push(mk);
  }
  const out = [];
  for (const g of grid.values()) {
    const n = g.items.length;
    // toScreen is affine, so projecting the world centroid is the same point
    // as averaging the projected positions - one call instead of one per item.
    const [sx, sy] = m.toScreen(g.px / n, g.py / n);
    out.push({ sx, sy, items: g.items });
  }
  return out;
}

function drawMarkers(ctx, m) {
  const r = m.canvas.getBoundingClientRect();
  const list = visibleMarkers();
  const useClusters = m.scale < 0.28;
  state.clusters = useClusters ? cluster(list, m) : null;

  ctx.save();
  ctx.lineWidth = 1.5;

  if (useClusters) {
    for (const c of state.clusters) {
      if (c.sx < -40 || c.sy < -40 || c.sx > r.width + 40 || c.sy > r.height + 40) continue;
      // Zoomed out, every cluster is a numbered bubble - a cluster of one
      // included. Drawing the lone marker's own sprite instead made the map read
      // as "some places have counts and some do not", which is exactly what the
      // counts are there to avoid; and a bubble of one still says what the number
      // said: there is one thing here. Sprites come back as soon as the zoom
      // passes the cluster threshold above (scale 0.28).
      const foundN = c.items.filter(isFound).length;
      const rad = Math.min(14, 7 + Math.log2(c.items.length) * 2.1);
      ctx.beginPath();
      ctx.arc(c.sx, c.sy, rad, 0, Math.PI * 2);
      ctx.fillStyle = 'rgba(16,14,10,.78)';
      ctx.fill();
      ctx.strokeStyle = foundN === c.items.length ? FOUND_COLOR : '#d8b45a';
      ctx.stroke();
      ctx.fillStyle = foundN === c.items.length ? '#bfe6c4' : '#e6dfcd';
      ctx.font = '600 10px "Segoe UI", sans-serif';
      ctx.textAlign = 'center';
      ctx.textBaseline = 'middle';
      ctx.fillText(String(c.items.length), c.sx, c.sy);
    }
  } else {
    for (const mk of list) {
      const [sx, sy] = m.toScreen(mk.px, mk.py);
      if (sx < -30 || sy < -30 || sx > r.width + 30 || sy > r.height + 30) continue;
      drawOne(ctx, mk, sx, sy, m);
    }
    if (state.showLabels && m.scale > 0.85) {
      ctx.font = '11px "Segoe UI", sans-serif';
      ctx.textAlign = 'center';
      ctx.textBaseline = 'top';
      // Boss markers borrow the name of the nearest landmark, so the same text
      // can land twice in one spot. Draw each name once per neighbourhood.
      const drawn = [];
      for (const mk of list) {
        if (mk.cat !== 'grace' && mk.cat !== 'boss') continue;
        const [sx, sy] = m.toScreen(mk.px, mk.py);
        if (sx < 0 || sy < 0 || sx > r.width || sy > r.height) continue;
        const label = nameOf(mk);
        if (drawn.some((d) => d.name === label &&
                       Math.abs(d.x - sx) < 90 && Math.abs(d.y - sy) < 60)) continue;
        drawn.push({ name: label, x: sx, y: sy });
        ctx.lineWidth = 3;
        ctx.strokeStyle = 'rgba(8,7,5,.9)';
        ctx.strokeText(label, sx, sy + 9);
        ctx.fillStyle = isFound(mk) ? 'rgba(160,200,165,.95)' : 'rgba(230,223,205,.95)';
        ctx.fillText(label, sx, sy + 9);
        ctx.lineWidth = 1.5;
      }
    }
  }

  drawFragmentRect(ctx, m);
  drawPlayer(ctx, m);
  ctx.restore();
}

/** A selected map fragment shows the region it reveals. */
function drawFragmentRect(ctx, m) {
  const mk = state.selected && state.byId.get(state.selected);
  if (!mk || mk.cat !== 'fragment' || !mk.rect || mk.master !== state.master) return;
  const [x0, y0] = m.toScreen(mk.rect[0], mk.rect[1]);
  const [x1, y1] = m.toScreen(mk.rect[2], mk.rect[3]);
  ctx.save();
  ctx.setLineDash([7, 5]);
  ctx.strokeStyle = isFound(mk) ? 'rgba(111,207,122,.85)' : 'rgba(197,139,234,.85)';
  ctx.lineWidth = 2;
  ctx.strokeRect(x0, y0, x1 - x0, y1 - y0);
  ctx.fillStyle = isFound(mk) ? 'rgba(111,207,122,.07)' : 'rgba(197,139,234,.09)';
  ctx.fillRect(x0, y0, x1 - x0, y1 - y0);
  ctx.restore();
}

function drawOne(ctx, mk, sx, sy, m) {
  const cat = CATS[mk.cat] || CATS.poi;
  const found = isFound(mk);
  const sel = state.selected === mk.id;
  const hov = state.hovered === mk.id;
  const rad = (cat.r + (hov || sel ? 2.5 : 0)) * (m.scale > 1.6 ? 1.25 : 1);

  const ic = iconFor(mk);
  if (ic) {
    // Constant display size regardless of zoom, like the game's own map.
    const h = 26 * (m.scale > 1.6 ? 1.3 : 1) * (hov || sel ? 1.25 : 1);
    const w = h * (ic.meta.w / ic.meta.h);
    ctx.save();
    // A few sprites are directional (the grace rays, the summoning-pool flames)
    // and carry the heading the game draws them at.
    if (mk.angle) {
      ctx.translate(sx, sy);
      ctx.rotate(mk.angle * Math.PI / 180);
      ctx.translate(-sx, -sy);
    }
    // Sprites have no flat colour to tint, so "found" is shown by fading the
    // sprite and putting the usual tick on top.
    ctx.globalAlpha = found ? 0.4 : 1;
    ctx.drawImage(ic.img, sx - w / 2, sy - h / 2, w, h);
    ctx.restore();
    if (found) {
      ctx.beginPath();
      ctx.moveTo(sx - rad * 0.42, sy);
      ctx.lineTo(sx - rad * 0.08, sy + rad * 0.38);
      ctx.lineTo(sx + rad * 0.46, sy - rad * 0.4);
      ctx.strokeStyle = FOUND_COLOR;
      ctx.lineWidth = 2.2;
      ctx.stroke();
    }
    if (sel) {
      ctx.beginPath();
      ctx.arc(sx, sy, h * 0.62, 0, Math.PI * 2);
      ctx.strokeStyle = cat.color;
      ctx.lineWidth = 2;
      ctx.stroke();
    }
    return;
  }

  ctx.beginPath();
  ctx.arc(sx, sy, rad, 0, Math.PI * 2);
  ctx.fillStyle = found ? 'rgba(24,34,24,.9)' : 'rgba(14,12,9,.85)';
  ctx.fill();
  ctx.strokeStyle = found ? FOUND_COLOR : cat.color;
  ctx.lineWidth = sel ? 2.6 : 1.6;
  ctx.stroke();

  if (found) {
    ctx.beginPath();
    ctx.moveTo(sx - rad * 0.42, sy);
    ctx.lineTo(sx - rad * 0.08, sy + rad * 0.38);
    ctx.lineTo(sx + rad * 0.46, sy - rad * 0.4);
    ctx.strokeStyle = FOUND_COLOR;
    ctx.lineWidth = 1.9;
    ctx.stroke();
  } else {
    ctx.beginPath();
    ctx.arc(sx, sy, Math.max(1.2, rad * 0.3), 0, Math.PI * 2);
    ctx.fillStyle = cat.color;
    ctx.fill();
  }
}

/**
 * The player dot.
 *
 * It marks the position recorded in the last save: the game writes that when it
 * autosaves, and the server re-reads the file when it changes.
 */
// The dot animates (pulse ring, eased motion), so the canvas has to keep redrawing while it settles;
// ANIM_INTERVAL_MS (catalog.js) is the pace. Nothing is scheduled while the tab is in the background.
let animTimer = null;

function scheduleAnimation() {
  if (animTimer !== null || document.hidden) return;
  animTimer = setTimeout(() => {
    animTimer = null;
    if (!document.hidden) map.requestDraw();
  }, ANIM_INTERVAL_MS);
}

document.addEventListener('visibilitychange', () => {
  if (!document.hidden && map) map.requestDraw();
});

function playerTarget() {
  const c = state.character;
  if (c && c.mapPixel) {
    return { px: c.mapPixel[0], py: c.mapPixel[1], master: c.mapMaster,
             angle: null, h: typeof c.mapHeight === 'number' ? c.mapHeight : null,
             roundtable: false };
  }
  return null;
}

/**
 * Follow mode. Engaged, every new save position re-centres the map and a cross-map
 * move switches the layer with you. It stays engaged while the position is
 * unknown - only clicking the button again, or dragging the map, releases it -
 * so turning it on before a character has saved does the right thing later.
 */
function setFollow(on) {
  if (state.followPlayer === on) return;
  state.followPlayer = on;
  const btn = $('goto-player');
  btn.classList.toggle('active', on);
  btn.title = on ? t('zoom.following') : t('zoom.player');
  if (on) recentreOnPlayer();
}

function recentreOnPlayer() {
  if (!state.followPlayer) return;
  const p = playerTarget();
  if (!p) return;
  if (p.master && p.master !== state.master) switchMaster(p.master);
  map.centerOn(p.px, p.py, Math.max(map.scale, 1.2));
}

function drawPlayer(ctx, m) {
  const target = playerTarget();
  if (!target) { state.playerRender = null; return; }
  if (target.master !== state.master) return;

  // ease toward the newest sample (snap if it teleported, e.g. a warp)
  let r = state.playerRender;
  if (!r || Math.hypot(r.px - target.px, r.py - target.py) > 400) {
    r = { px: target.px, py: target.py, angle: target.angle };
  } else {
    const k = 0.25;
    r.px += (target.px - r.px) * k;
    r.py += (target.py - r.py) * k;
    if (target.angle != null) {
      if (r.angle == null) r.angle = target.angle;
      else {
        let d = ((target.angle - r.angle + 540) % 360) - 180;   // shortest way round
        r.angle += d * k;
      }
    }
  }
  state.playerRender = r;

  const [sx, sy] = m.toScreen(r.px, r.py);
  const pulse = 10 + Math.sin(performance.now() / 600) * 3;

  // facing cone, when the live feed gives us a heading
  if (r.angle != null) {
    const a = (r.angle - 90) * Math.PI / 180;
    const spread = 0.42;
    ctx.beginPath();
    ctx.moveTo(sx, sy);
    ctx.arc(sx, sy, 26, a - spread, a + spread);
    ctx.closePath();
    const g = ctx.createRadialGradient(sx, sy, 3, sx, sy, 26);
    g.addColorStop(0, 'rgba(255,255,255,.34)');
    g.addColorStop(1, 'rgba(255,255,255,0)');
    ctx.fillStyle = g;
    ctx.fill();
  }

  ctx.beginPath();
  ctx.arc(sx, sy, pulse, 0, Math.PI * 2);
  ctx.strokeStyle = 'rgba(255,255,255,.3)';
  ctx.lineWidth = 1.5;
  ctx.stroke();

  ctx.beginPath();
  ctx.arc(sx, sy, 5, 0, Math.PI * 2);
  ctx.fillStyle = '#fff';
  ctx.fill();
  ctx.strokeStyle = '#12181c';
  ctx.lineWidth = 1.5;
  ctx.stroke();

  // Keep animating only while there is something to animate.
  const settled = Math.abs(r.px - target.px) < 0.05 && Math.abs(r.py - target.py) < 0.05;
  if (!settled) scheduleAnimation();
}

/* ---------------------------------------------------------------- picking */

function pick(sx, sy) {
  if (state.clusters) {
    for (const c of state.clusters) {
      const d = Math.hypot(c.sx - sx, c.sy - sy);
      if (d < 19) return { cluster: c };
    }
    return null;
  }
  const hits = [];
  for (const mk of visibleMarkers()) {
    const [x, y] = map.toScreen(mk.px, mk.py);
    const d = Math.hypot(x - sx, y - sy);
    if (d < PICK_RADIUS) hits.push([d, mk]);
  }
  if (!hits.length) return null;
  // Nearest first, then by name, so the order never depends on the order the
  // dataset happened to be in.
  hits.sort((a, b) => a[0] - b[0] || nameOf(a[1]).localeCompare(nameOf(b[1])));
  // Everything within a couple of pixels of the nearest is one spot as far as the
  // screen is concerned, and the map cannot know which one was meant. Returning the
  // whole group lets the popup list them instead of silently picking one - a boss
  // and its drops share a coordinate exactly, and so do stacked gathering nodes.
  // Zooming in separates them and this collapses back to a single hit.
  const group = hits.filter(([d]) => d - hits[0][0] <= PICK_GROUP_PX).map(([, mk]) => mk);
  return { marker: group[0], group };
}

function handleHover(sx, sy) {
  const hit = pick(sx, sy);
  const tip = $('tooltip');
  const id = hit && hit.marker ? hit.marker.id : null;
  if (id !== state.hovered) { state.hovered = id; map.requestDraw(); }

  if (hit && hit.marker) {
    const m = hit.marker;
    const h = typeof m.h === 'number' ? ` · ${m.h} ${t('unit.m')}` : '';
    const more = hit.group && hit.group.length > 1
      ? ` · ${t('tip.alsoHere').replace('{}', hit.group.length)}` : '';
    tip.innerHTML = `<div>${escapeHtml(nameOf(m))}</div>` +
      `<div class="tt-cat">${catLabel(m.cat)}${h}` +
      `${isFound(m) ? ' · ' + t('tip.found') : ''}${escapeHtml(more)}</div>`;
    const [x, y] = map.toScreen(m.px, m.py);
    tip.style.left = x + 'px';
    tip.style.top = y + 'px';
    tip.classList.remove('hidden');
  } else if (hit && hit.cluster) {
    const n = hit.cluster.items.length;
    tip.innerHTML = `<div>${n} ${I18n.plural('tip.markers', n)}</div>` +
      `<div class="tt-cat">${t('tip.clickZoom')}</div>`;
    tip.style.left = hit.cluster.sx + 'px';
    tip.style.top = hit.cluster.sy + 'px';
    tip.classList.remove('hidden');
  } else {
    tip.classList.add('hidden');
  }
}

function handleClick(sx, sy) {
  const hit = pick(sx, sy);
  if (!hit) { closePopup(); return; }
  if (hit.cluster) {
    const [mx, my] = map.toMaster(hit.cluster.sx, hit.cluster.sy);
    map.flyTo(mx, my, map.scale * 2.5);
    return;
  }
  showPopup(hit.marker, hit.group);
}

/* ----------------------------------------------------------------- popup */

/**
 * How high up is it?
 *
 * The extractors carry the world Y through the same translation chain as the
 * horizontal axes (see LegacyConv.convert in tools/build_markers.py), so these
 * are comparable across maps: the Forge of the Giants reads ~1970, the Siofra
 * River well bottom ~-480. A world unit is about a metre.
 *
 * Map fragments have no height - they are the centre of the region a fragment
 * reveals, not a thing standing anywhere - so their row is simply omitted.
 */
/** How many pickups share this spot (gathering nodes merged into one marker). */
/** A farm spot: the enemy here carries the lot, and the enemy comes back. */
function farmBlock(m) {
  if (!m.farm) return '';
  const sites = m.sites && m.sites > 1
    ? ' · ' + t('label.farmSites').replace('{}', m.sites) : '';
  // The enemy row appears only when the enemy actually has a name. Almost none do
  // - the four models behind these spots have no NpcName in any of their 34 NpcParam
  // rows - so a row reading "an unnamed enemy" would say the same thing everywhere
  // and is left out instead. data/enemy-names.json can supply a name, and the row
  // comes back for that enemy.
  const enamed = m.enemy && dictName(m.enemy.names);
  const whoLine = enamed
    ? '<div class="detail">' +
      `<span class="k">${escapeHtml(t('label.enemy'))}</span>` +
      `<span class="v">${escapeHtml(enamed)}</span></div>` : '';
  const drops = (m.drops || []).map((d) => dictName(d.names) +
    (d.qty > 1 ? ` ×${d.qty}` : '')).filter(Boolean);
  const dropLine = drops.length
    ? '<div class="detail">' +
      `<span class="k">${escapeHtml(t('label.enemyDrops'))}</span>` +
      `<span class="v">${escapeHtml(drops.join('、'))}</span></div>` : '';
  return whoLine + dropLine + '<div class="detail">' +
    `<span class="k">${escapeHtml(t('label.farm'))}</span>` +
    `<span class="v">${escapeHtml(t('label.farmBody'))}${escapeHtml(sites)}</span></div>`;
}

function nodesBlock(m) {
  if (!m.nodes || m.nodes < 2) return '';
  return '<div class="detail">' +
    `<span class="k">${escapeHtml(t('label.nodes'))}</span>` +
    `<span class="v">${escapeHtml(t('label.nodeCount').replace('{}', m.nodes))}</span></div>`;
}

/**
 * One-time or respawning?
 *
 * extract_gather_nodes.py reads this from the same param row that carries the pickup lot, and only
 * writes the field for gatherables, so its presence is what says the marker is a node. The same
 * material can have both kinds in the layer, which is why this is per marker rather than per item.
 */
function gatherBlock(m) {
  if (!m || typeof m.once !== 'boolean') return '';
  const what = m.once ? 'label.gatherOnce' : 'label.gatherRefresh';
  return '<div class="detail">' +
    `<span class="k">${escapeHtml(t('label.gather'))}</span>` +
    `<span class="v">${escapeHtml(t(what))}</span></div>`;
}

function heightBlock(m) {
  if (typeof m.h !== 'number') return '';
  return '<div class="detail">' +
    `<span class="k">${escapeHtml(t('label.height'))}</span>` +
    `<span class="v">${m.h} ${escapeHtml(t('unit.m'))}</span></div>`;
}

/**
 * Who gives this?
 *
 * A one-time reward (data/drops.json) is not lying in the world: an enemy drops it
 * or a character hands it over, and the game records that on the character's own
 * NpcParam row. Naming them is the whole point of the marker, so it gets its own
 * row. 74 of the 130 rewards sit on an enemy whose NpcName row is the game's
 * "DLC dummy" placeholder - there the row is omitted rather than inventing a name.
 * `sites` says how many places that character turns up in, because a marker can
 * only point at one of them.
 */
function sourceBlock(m) {
  const who = dictName(m.source);
  if (!who) return '';
  const sites = m.sites > 1 ? `（${escapeHtml(t('label.sites').replace('{}', m.sites))}）` : '';
  return '<div class="detail">' +
    `<span class="k">${escapeHtml(t('label.source'))}</span>` +
    `<span class="v">${escapeHtml(who)}${sites}</span></div>`;
}

/**
 * Every marker on this exact spot, as buttons, in a fixed order.
 *
 * A boss and its drops share a coordinate, and so do stacked gathering nodes, so
 * one click can only ever reach one of them. Rather than fanning them out (which
 * would put them where they are not) the card lists them and lets you switch.
 *
 * The list never reorders and never drops a row: the one you are looking at is
 * shown by a box around it (`current`) instead of disappearing, because a list
 * that reshuffles under the cursor loses your place. It scrolls when a spot has
 * more entries than fit - a bush with twelve fruits on it, say.
 */
function alsoBlock(also, currentId) {
  if (!also.length) return '';
  const rows = also.map((x) => {
    const cls = 'also-item' + (x.id === currentId ? ' current' : '');
    return `<button type="button" class="${cls}" data-id="${escapeHtml(x.id)}">` +
      `${escapeHtml(nameOf(x))}<span class="also-cat">${escapeHtml(catLabel(x.cat))}</span></button>`;
  }).join('');
  return '<div class="detail also">' +
    `<span class="k">${escapeHtml(t('label.also'))}</span>` +
    `<span class="v">${rows}</span></div>`;
}

function showPopup(m, group) {
  state.selected = m.id;
  const el = $('popup');
  const found = isFound(m);
  const auto = state.found.has(m.id);
  // The live player marker is built fresh on every read, so it gets its region
  // and nearest place here rather than in the load-time pass over the dataset.
  if (m.px != null && !m.region) annotatePlace(m);
  // Everything sharing this spot on screen, in the order pick() found it: nearest
  // first, then by name. A boss and its drops sit on the same coordinate, so without
  // this list the rest would be unreachable - the map can only hand back one marker
  // per click.
  //
  // Deduplicated by category and name, not just by id: the game has two goods rows
  // for Godrick's Great Rune (8148 and 191) and both lots hang off the same boss, so
  // two entries with the very same text would appear.
  //
  // The marker being shown stays in the list (boxed by alsoBlock) rather than being
  // filtered out, so the list keeps its order and its length while you click through.
  const also = [];
  const seenAlso = new Set();
  for (const x of group || []) {
    const key = `${x.cat}\u0000${nameOf(x)}`;
    if (seenAlso.has(key)) continue;
    seenAlso.add(key);
    also.push(x);
  }
  // The map file id (m60_36_48) and the save's event-flag id are developer
  // handles: meaningless on screen, but the only way to trace a marker back into
  // the game data, so they move into the tooltip instead of disappearing.
  const ids = [m.map, m.flag].filter(Boolean).join(' · ');
  // The item's own sprite, when this item has one. It is drawn beside the name
  // because the category swatch only says "a smithing stone", while this says
  // which smithing stone - which is the whole point of splitting the levels.
  const itemIcon = m.iconId && state.itemIcons && state.itemIcons[String(m.iconId)];
  el.innerHTML = `
    <button class="close" title="${escapeHtml(t('popup.close'))}">×</button>
    <h3>${itemIcon ? `<img class="item-icon" src="${escapeHtml(itemIcon.file)}" alt="" width="${itemIcon.w}" height="${itemIcon.h}">` : ''}${escapeHtml(nameOf(m))}</h3>
    <div class="meta"${ids ? ` title="${escapeHtml(ids)}"` : ''}>${catLabel(m.cat)}${placeLabel(m) ? ' · ' + escapeHtml(placeLabel(m)) : ''}</div>
    ${sourceBlock(m)}
    <div class="found-state ${found ? 'found-yes' : ''}">
      ${found ? (auto ? t('popup.foundSave') : t('popup.foundManual')) : t('popup.notFound')}
    </div>
    ${nodesBlock(m)}
    ${gatherBlock(m)}
    ${farmBlock(m)}
    ${heightBlock(m)}
    ${alsoBlock(also, m.id)}
    ${auto ? '' : `<button class="toggle">${found ? t('popup.unmark') : t('popup.mark')}</button>`}
  `;
  // Each entry switches the card to that marker, keeping the same group so the list
  // keeps its order and length; the box simply moves to the row you picked.
  el.querySelectorAll('.also-item').forEach((b) => {
    b.onclick = () => {
      const next = state.byId.get(b.dataset.id);
      if (next) showPopup(next, group);
    };
  });
  const current = el.querySelector('.also-item.current');
  if (current && current.scrollIntoView) current.scrollIntoView({ block: 'nearest' });
  const [x, y] = map.toScreen(m.px, m.py);
  el.style.left = x + 'px';
  el.style.top = y + 'px';
  el.classList.remove('hidden', 'below');
  // The popup hangs above its marker. A route description can make it three
  // times its old height, so flip it under the marker when it would otherwise
  // run off the top of the window and take the close button with it.
  if (el.getBoundingClientRect().top < EDGE_PAD) el.classList.add('below');
  // ...and slide it back inside #stage horizontally. The popup is centred on
  // its marker, so one near either edge hangs half its width off - under the
  // sidebar on the left, past the zoom buttons on the right.
  const half = el.offsetWidth / 2;
  const limit = el.parentElement.clientWidth - half - EDGE_PAD;
  if (limit > half + EDGE_PAD) {
    el.style.left = Math.min(Math.max(x, half + EDGE_PAD), limit) + 'px';
  }
  el.querySelector('.close').onclick = closePopup;
  // NOT `const t` - that would shadow the translate helper used in the template
  // above and put it in the temporal dead zone for the whole function.
  const btn = el.querySelector('.toggle');
  if (btn) btn.onclick = () => toggleCheck(m.id, !found);
  map.requestDraw();
}

function closePopup() {
  state.selected = null;
  $('popup').classList.add('hidden');
  if (map) map.requestDraw();
}

async function toggleCheck(id, on) {
  if (on) state.checked[id] = true; else delete state.checked[id];
  refreshCounts();
  map.requestDraw();
  const m = state.byId.get(id);
  if (m) showPopup(m);
  try {
    await fetch('api/check', {
      method: 'POST', headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ id, on }),
    });
  } catch { /* offline; local state still applies */ }
}

/* ------------------------------------------------------------------- ui */

function buildLayerButtons() {
  const wrap = $('layer-buttons');
  wrap.innerHTML = '';
  // A layer that nothing is placed on is a blank canvas, so its button is not
  // offered: M11 ("Realm of Shadow - Underground") ships 261 tiles and the game
  // puts no grace, landmark or item on any of them. Two exceptions keep that
  // safe - the layer being viewed right now, and the layer the player is
  // standing on - because otherwise walking into a marker-less area would take
  // the floor out from under the player dot. If a patch ever does populate M11,
  // its markers bring the button back on their own.
  const used = new Set(state.markers.map((m) => m.master));
  const standing = (playerTarget() || {}).master;
  for (const id of ['M00', 'M01', 'M10', 'M11']) {
    const info = masterInfo(id);
    if (!info) continue;
    if (!used.has(id) && id !== state.master && id !== standing) continue;
    const b = document.createElement('button');
    b.className = 'layer-btn' + (id === state.master ? ' active' : '');
    b.textContent = layerLabel(id);
    b.onclick = () => switchMaster(id);
    wrap.appendChild(b);
  }
}

function switchMaster(id) {
  if (!masterInfo(id) || id === state.master) return;
  state.master = id;
  closePopup();
  buildLayerButtons();
  initMap(id);
  refreshCounts();
  buildRegionButtons();
  savePrefs();
}

/**
 * Legend rows whose picture is chosen by hand instead of inferred.
 *
 * The inference below picks "the iconId most of the category's markers carry",
 * and for a level-split category that is exactly right. It cannot work for
 * `armour`: every armour marker carries a different iconId - all sixty-three
 * counts are 1 - so the row falls to whichever sprite comes first in items.json,
 * which is the Incantation Scarab. That is a scarab-helm, but at 18px it reads
 * as the talisman it looks like, not as "防具".
 *
 * Albinauric Mask (14800) is the picture that was asked for here. It is not on
/**
 * The iconId that identifies each category: the one most of its markers carry.
 * For a level-split category that is the level's own item, which is the point.
 */
function categoryIconIds(markers) {
  const counts = new Map();
  for (const m of markers) {
    if (!m.iconId) continue;
    if (!counts.has(m.cat)) counts.set(m.cat, new Map());
    const byId = counts.get(m.cat);
    byId.set(m.iconId, (byId.get(m.iconId) || 0) + 1);
  }
  const out = new Map();
  for (const [cat, byId] of counts) {
    out.set(cat, [...byId.entries()].sort((a, b) => b[1] - a[1])[0][0]);
  }
  return out;
}

/**
 * The picture for one legend row.
 *
 * A row is a category, so its natural swatch is the category's own MIT icon. But
 * the level-split categories - eighteen smithing stones, thirteen golden runes -
 * share a handful of category icons between them, which is exactly why they could
 * not be told apart at a glance; the item's own sprite differs at every level and
 * is what the player already sees in their inventory. So the item's sprite wins
 * whenever the category has one - and for the rows in CAT_ICON that inference
 * cannot serve, the sprite named there wins outright.
 *
 * It does not try to avoid two rows showing the same sprite. The four
 * miner/picker bell bearings really do share one bell in the game, and it was
 * tempting to fall back to the category icons for those rows to keep them
 * distinct - but that drew a smithing stone for a bell bearing, which is simply
 * wrong, while a repeated bell is merely repeated. The label and the colour
 * already separate those rows.
 */
function legendSwatch(key) {
  const iconId = CAT_ICON[key] !== undefined ? CAT_ICON[key] : state.categoryIconIds.get(key);
  const meta = state.itemIcons && state.itemIcons[String(iconId)];
  if (meta) return `<img class="swatch icon" src="${escapeHtml(meta.file)}" alt="">`;
  // No item sprite for this row, so a colour dot. The bundled category icons
  // were removed: the data no longer needs them (every item marker carries its
  // own iconId) and the fallback they provided is now the dot itself.
  return `<span class="swatch" style="background:${CATS[key].color}"></span>`;
}

/**
 * Rewards that were attributed but have no world object, and therefore no coordinates.
 *
 * The extraction records a verdict for each of them (sold on a merchant's shelf, held from the start,
 * referenced by nothing in the game data), and none of them can ever be pinned on the map. Listing them
 * here is what keeps those items - among them most of the merchant bell bearings - from being invisible.
 */
function buildRegistered() {
  const list = $('registered-list');
  if (!list) return;
  const rows = (state.registered || []).slice();
  const count = $('registered-count');
  if (count) {
    count.textContent = rows.length ? t('registered.count').replace('{}', rows.length) : '';
  }
  list.innerHTML = '';
  rows.sort((a, b) => nameOf(a).localeCompare(nameOf(b), I18n.lang));
  for (const m of rows) {
    const row = document.createElement('div');
    row.className = 'reg-item';
    if (m.note) row.title = m.note;
    const name = document.createElement('span');
    name.className = 'reg-name';
    name.textContent = nameOf(m);
    const verdict = document.createElement('span');
    verdict.className = 'reg-verdict';
    // The extractor's verdict when it recorded one; otherwise the category (the two shop shelves whose
    // owner no script declares carry no verdict, only their category).
    let label = '';
    if (m.verdict) {
      const key = 'verdict.' + m.verdict;
      label = t(key);
      if (label === key) label = m.verdict;
    }
    if (!label) {
      const byCat = catLabel(m.cat);
      if (byCat !== m.cat) label = byCat;
    }
    verdict.textContent = label;
    row.appendChild(name);
    row.appendChild(verdict);
    list.appendChild(row);
  }
}

function buildCategories() {
  const wrap = $('category-list');
  wrap.innerHTML = '';
  // One legend row. Kept as a closure so both grouped and ungrouped rows are
  // built by exactly the same code.
  const buildRow = (key) => {
    const row = document.createElement('div');
    row.className = 'cat' + (state.enabled.has(key) ? '' : ' off');
    row.dataset.cat = key;
    // Not loading="lazy": these are ~80 small PNGs off the local server, and a
    // lazy swatch stays blank whenever the sidebar is scrolled or collapsed.
    const swatch = legendSwatch(key);
    row.innerHTML = `
      ${swatch}
      <span class="label">${escapeHtml(catLabel(key))}<span class="minibar"><i style="width:0%"></i></span></span>
      <span class="count">0/0</span>`;
    row.onclick = () => {
      if (state.enabled.has(key)) state.enabled.delete(key); else state.enabled.add(key);
      row.classList.toggle('off', !state.enabled.has(key));
      savePrefs();
      map.requestDraw();
    };
    return row;
  };

  const buildGroup = (group) => {
    const cats = group.cats.filter((k) => k in CATS);
    if (!cats.length) return;
    const box = document.createElement('div');
    box.className = 'cat-group';
    box.dataset.group = group.id;

    const head = document.createElement('button');
    head.type = 'button';
    const on = cats.filter((k) => state.enabled.has(k)).length;
    head.className = 'cat-group-head' + (state.groupOpen.has(group.id) ? '' : ' collapsed');
    head.innerHTML =
      `<span class="chev">▾</span><span class="g-label">${escapeHtml(t(group.label))}</span>` +
      `<span class="g-count">${on}/${cats.length}</span>`;
    head.onclick = () => {
      if (state.groupOpen.has(group.id)) state.groupOpen.delete(group.id);
      else state.groupOpen.add(group.id);
      head.classList.toggle('collapsed', !state.groupOpen.has(group.id));
      box.classList.toggle('collapsed', !state.groupOpen.has(group.id));
      savePrefs();
    };
    box.appendChild(head);

    const body = document.createElement('div');
    body.className = 'cat-group-body';
    for (const key of cats) body.appendChild(buildRow(key));
    box.appendChild(body);
    if (!state.groupOpen.has(group.id)) box.classList.add('collapsed');
    wrap.appendChild(box);
  };

  for (const group of CAT_GROUPS) buildGroup(group);
  // UNGROUPED_CATS was captured at load time and restrictCatsToData() may have
  // dropped one of its members since (misc, when nothing falls through to it).
  for (const key of UNGROUPED_CATS) if (key in CATS) wrap.appendChild(buildRow(key));
}

/**
 * The save picker: one dropdown for the save file type found on disk (the game
 * itself writes .sl2) and one for the character, listing every slot of every
 * save of that type by name and level. A file holding two characters gets two
 * entries, so either can be picked; the Steam account id only appears when
 * there is more than one profile to tell apart.
 */
let pickerOptions = [];   // { path, slot, label } behind each character <option>

function buildSavePicker() {
  const extension = $('save-extension');
  const character = $('save-character');
  const extensions = [...new Set(state.saves.map((save) => save.extension))];
  const selected = state.saves.find((save) => save.path === state.savePath);
  extension.innerHTML = extensions.map((value) =>
    `<option value="${escapeHtml(value)}">${escapeHtml(value)}</option>`).join('');
  extension.value = (selected && selected.extension) || extensions[0] || '';

  const renderCharacters = () => {
    const matches = state.saves.filter((save) => save.extension === extension.value);
    const accounts = new Set(matches.map((save) => save.account));
    pickerOptions = [];
    for (const save of matches) {
      const suffix = accounts.size > 1 ? ` · ${save.account}` : '';
      const chars = save.characters || [];
      if (!chars.length) {
        pickerOptions.push({ path: save.path, slot: null,
                             label: `${t('save.account')} ${save.account}` });
      }
      for (const c of chars) {
        pickerOptions.push({ path: save.path, slot: c.slot,
                             label: `${c.name} · ${t('char.level')} ${c.level}${suffix}` });
      }
    }
    character.innerHTML = pickerOptions.map((o, i) =>
      `<option value="${i}" title="${escapeHtml(o.path)}">${escapeHtml(o.label)}</option>`).join('');
    character.disabled = pickerOptions.length === 0;
    selectPickerOption(state.savePath, state.character ? state.character.slot : null);
  };

  extension.onchange = renderCharacters;
  character.onchange = async () => {
    const option = pickerOptions[Number(character.value)];
    if (!option) return;
    const shown = state.character ? state.character.slot : null;
    if (option.path === state.savePath && option.slot === shown) return;
    extension.disabled = true;
    character.disabled = true;
    try {
      const response = await fetch('api/saves', {
        method: 'POST', headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ path: option.path, slot: option.slot }),
      });
      const result = await response.json();
      if (!response.ok) throw new Error(result.error || t('save.switchFailed'));
      state.savePath = result.current;
      // The new snapshot arrives over the event stream and syncs the picker.
    } catch (error) {
      toast(t('save.switchFailed'), error.message);
      syncSavePicker();       // back to what is actually on screen
    } finally {
      extension.disabled = false;
      character.disabled = pickerOptions.length === 0;
    }
  };
  renderCharacters();
}

/** Select (path, slot) in the character dropdown; the file's first entry when the slot is unknown. */
function selectPickerOption(path, slot) {
  let index = pickerOptions.findIndex((o) => o.path === path && o.slot === slot);
  if (index < 0) index = pickerOptions.findIndex((o) => o.path === path);
  if (index >= 0) $('save-character').value = String(index);
}

/**
 * Make the picker agree with the character on screen. Runs for every snapshot
 * and whenever the live matcher moves to another slot, so the dropdown follows
 * the running character rather than the other way round.
 */
function syncSavePicker() {
  const extension = $('save-extension');
  const save = state.saves.find((s) => s.path === state.savePath);
  if (save && extension.value !== save.extension && typeof extension.onchange === 'function') {
    extension.value = save.extension;
    extension.onchange();        // rebuilds the character list, then selects
    return;
  }
  selectPickerOption(state.savePath, state.character ? state.character.slot : null);
}

/**
 * Keep the picker's entry for the watched file current, from the snapshot: a
 * character created while the map was open should be selectable without a
 * reload, and a level-up should show.
 */
function refreshSaveEntry(s) {
  const entry = state.saves.find((save) => save.path === s.savePath);
  if (!entry) return;
  const chars = (s.characters || []).map((c) => ({ slot: c.slot, name: c.name, level: c.level }));
  if (JSON.stringify(chars) === JSON.stringify(entry.characters || [])) return;
  entry.characters = chars;
  buildSavePicker();
}

// Categories that are not part of the completion percentage. Most gathering nodes are picked again
// after every rest, so counting them as collectibles would make the progress bar a lie: it would
// never reach 100% and it would drop when you farm. The old single 'gathering' row is kept here so a
// data directory written before the layer document existed still renders correctly.

function refreshCounts() {
  const farmOnly = new Set();
  const hasPickup = new Set();
  // One pass over every marker, then emit both totals.
  //
  // The per-category rows count the *current layer*: the map only draws that
  // layer, so a row's number has to match what clicking it shows. The headline
  // is the whole dataset - it used to be the current layer too, which meant
  // "Overall" reported 2,891 of 4,474 on the surface and made the dataset look a
  // third of its size. Hence the second line, which says what the rows are
  // counting.
  const byCat = new Map();        // "layer|cat" -> [all, found]
  const byLayer = new Map();      // layer -> [all, found]
  const onceCat = new Map();      // "layer|cat" -> [all, found] for one-time nodes only
  let total = 0, found = 0;
  for (const m of state.markers) {
    const hit = isFound(m) ? 1 : 0;
    const cat = byCat.get(`${m.master}|${m.cat}`) || [0, 0];
    cat[0]++; cat[1] += hit; byCat.set(`${m.master}|${m.cat}`, cat);
    const lay = byLayer.get(m.master) || [0, 0];
    lay[0]++; lay[1] += hit; byLayer.set(m.master, lay);
    if (m.once) {
      const o = onceCat.get(`${m.master}|${m.cat}`) || [0, 0];
      o[0]++; o[1] += hit; onceCat.set(`${m.master}|${m.cat}`, o);
    }
    // A marker that is a farm spot rather than a pickup is not collectible either:
    // the enemy respawns, so there is nothing to tick off. And a ladder rung whose
    // only markers are farm spots counts as no-progress by itself, which is how the
    // seven levels with no placed pickup behave.
    if (m.farm) { farmOnly.add(m.cat); continue; }
    if (isNoProgress(m.cat) && !m.once) continue;
    // This row has something you can actually pick up, so it shows found/total
    // even when it also contains farm spots (see the label below).
    hasPickup.add(m.cat);
    total++; found += hit;
  }
  for (const key of Object.keys(CATS)) {
    const [all, f] = byCat.get(`${state.master}|${key}`) || [0, 0];
    const row = document.querySelector(`.cat[data-cat="${key}"]`);
    if (!row) continue;
    const once = onceCat.get(`${state.master}|${key}`);
    const onceOnly = isNoProgress(key) && once && once[0] ? once : null;
    const [shownAll, shownFound] = onceOnly || [all, f];
    // A row that is not tracked shows how many there are instead of found/total -
     // "0/603" would read as a progress bar that is broken.
    const noProgress = (isNoProgress(key) && !onceOnly) ||
      (farmOnly.has(key) && !hasPickup.has(key));
    row.querySelector('.count').textContent = noProgress
      ? t('label.places').replace('{}', all) : `${shownFound}/${shownAll}`;
    row.querySelector('.minibar i').style.width = shownAll
      ? (shownFound / shownAll * 100) + '%' : '0%';
    row.style.display = all ? '' : 'none';
  }
  const bar = (label, fill, [all, f]) => {
    $(label).textContent = `${f} / ${all}`;
    $(fill).style.width = all ? (f / all * 100) + '%' : '0%';
  };
  bar('progress-label', 'progress-fill', [total, found]);
  bar('progress-layer', 'progress-layer-fill', byLayer.get(state.master) || [0, 0]);
}

/**
 * Keep the server alive only while this page is open.
 *
 * The launcher hides the console, so a server that outlives the page would be an
 * invisible process. A ping every few seconds says "still here"; pagehide sends a
 * goodbye, and the server waits a few seconds after it before exiting - a refresh
 * fires pagehide too, and the reloaded page pings again immediately.
 */
function startKeepAlive() {
  const ping = () => { fetch('api/ping', { cache: 'no-store' }).catch(() => {}); };
  ping();
  setInterval(ping, 5000);
  window.addEventListener('pagehide', () => {
    try {
      navigator.sendBeacon('api/bye', '1');
    } catch (e) { /* closing anyway */ }
  });
}

function wireUi() {
  // Collapsible panels: every [data-collapse] header folds its own section.
  document.querySelectorAll('[data-collapse]').forEach((btn) => {
    btn.addEventListener('click', () => {
      const section = btn.closest('.panel');
      if (section) section.classList.toggle('collapsed');
      savePrefs();
    });
  });

  // ...and the whole sidebar, so the map can have the full window.
  const app = $('app');
  $('sb-collapse').onclick = () => { app.classList.add('sb-collapsed'); savePrefs(); };
  $('sb-expand').onclick = () => { app.classList.remove('sb-collapsed'); savePrefs(); };

  // Quit button. The server refuses /api/shutdown unless it is bound to
  // loopback, but a page opened over the LAN should not offer a button that
  // cannot work, so the same test is repeated here: any hostname other than
  // loopback means this page arrived over the network.
  //
  // The X-ER-Map header is not decoration. A cross-origin page can POST to
  // 127.0.0.1 as a "simple request" with no preflight, which would let any
  // website the user has open quit their map; asking for a custom header forces
  // a preflight, and the server never answers OPTIONS.
  const stopBtn = $('stop-server');
  if (['localhost', '127.0.0.1', '::1', '[::1]'].includes(location.hostname)) {
    stopBtn.classList.remove('hidden');
  }
  stopBtn.onclick = async () => {
    if (!window.confirm(t('stop.confirm'))) return;
    stopBtn.disabled = true;
    stopBtn.textContent = t('stop.stopping');
    try {
      const response = await fetch('api/shutdown', {
        method: 'POST', headers: { 'X-ER-Map': '1' },
      });
      if (!response.ok) throw new Error(`HTTP ${response.status}`);
      // The event stream drops as the server goes, so the live badge falls back
      // to "no server" on its own; all that is left is to say so here.
      stopBtn.textContent = t('stop.done');
      toast(t('stop.done'), t('stop.doneSub'));
    } catch (error) {
      stopBtn.disabled = false;
      stopBtn.textContent = t('stop.button');
      toast(t('stop.failed'), error.message);
    }
  };

  $('zoom-in').onclick = () => map.zoomBy(1.6);
  $('zoom-out').onclick = () => map.zoomBy(1 / 1.6);
  $('zoom-fit').onclick = () => map.fit();
  $('goto-player').onclick = () => {
    if (state.followPlayer) { setFollow(false); return; }
    if (!playerTarget()) toast(t('zoom.noPlayer'), t('zoom.noPlayerSub'));
    setFollow(true);      // engage regardless: it takes effect once a fix arrives
  };

  $('hide-found').onchange = (e) => { state.hideFound = e.target.checked; savePrefs(); map.requestDraw(); };
  $('show-labels').onchange = (e) => { state.showLabels = e.target.checked; savePrefs(); map.requestDraw(); };
  const gi = $('show-icons');
  if (gi) {
    gi.checked = state.showIcons;
    gi.onchange = (e) => { state.showIcons = e.target.checked; savePrefs(); map.requestDraw(); };
  }

  $('toggle-all').onclick = () => {
    if (state.enabled.size) state.enabled.clear();
    else Object.keys(CATS).forEach((k) => state.enabled.add(k));   // all, incl. misc
    document.querySelectorAll('.cat').forEach((r) =>
      r.classList.toggle('off', !state.enabled.has(r.dataset.cat)));
    $('toggle-all').textContent = state.enabled.size ? t('panel.selectNone') : t('panel.selectAll');
    savePrefs();
    map.requestDraw();
  };

  const search = $('search');
  const results = $('search-results');

  // Placement of the results list. Both elements are local to wireUi(), so the
  // placer lives here too.
  const SEARCH_GAP = 4;         // px between the input and the list
  const SEARCH_MIN_H = 96;      // below this, hang the list above instead
  const SEARCH_MAX_H = 320;     // the CSS ceiling, repeated so we can clamp it

  /**
   * Put the list directly under the input, as tall as there is room for.
   *
   * The offset has to be measured, not written down: the input sits below a
   * collapsible header inside a padded panel, so its distance from the panel
   * top changes the moment the header is folded away. A constant `top` put the
   * list over the input itself, which hid what the user was typing and made a
   * click in the middle of the box land on a result row.
   *
   * Two things get clamped. Height: whatever is left between the input and the
   * bottom of the window, because the sidebar clips its overflow and anything
   * past that edge is unreachable. And direction: with less room below than a
   * couple of rows, the list opens upwards rather than shrinking to a sliver.
   */
  function placeSearchResults() {
    if (!results.classList.contains('open')) return;
    const box = search.getBoundingClientRect();
    const wrap = search.closest('.search-wrap').getBoundingClientRect();
    const room = window.innerHeight - box.bottom - SEARCH_GAP - EDGE_PAD;
    if (room >= SEARCH_MIN_H) {
      results.style.top = (box.bottom - wrap.top + SEARCH_GAP) + 'px';
      results.style.maxHeight = Math.min(SEARCH_MAX_H, room) + 'px';
      return;
    }
    // Less than a couple of rows below: open upwards instead of squashing the
    // list to a sliver. A window too short to hold it above as well is not
    // worth a third case - the floor keeps the list usable there, and the
    // sidebar clips the few pixels that hang off the top.
    const available = box.top - SEARCH_GAP - EDGE_PAD;
    const height = Math.min(SEARCH_MAX_H, Math.max(available, SEARCH_MIN_H));
    results.style.top = (box.top - wrap.top - SEARCH_GAP - height) + 'px';
    results.style.maxHeight = height + 'px';
  }

  search.oninput = () => {
    const q = search.value.trim().toLowerCase();
    // One character is a valid query. The old "fewer than 2 characters, do
    // nothing" rule meant a Chinese user typing 赐 saw an empty list and no
    // explanation, because most Chinese item names are 2-4 characters and the
    // interesting ones start with a single distinctive glyph.
    if (!q) { results.classList.remove('open'); return; }

    // Rank rather than just filter: typing more characters should visibly
    // narrow and reorder the list, not merely shorten it. Lower score = better.
    // Exact match beats prefix, which beats a word-start match, which beats a
    // match buried mid-name. Already-found markers sink so the ones still to
    // collect come first, which is the order a collector actually wants.
    const rank = (name) => {
      const n = name.toLowerCase();
      const at = n.indexOf(q);
      if (at < 0) return null;
      let score = at === 0 ? 0 : 100 + at;
      if (at === 0 && n.length === q.length) score = -10;          // exact
      else if (/[\s:：·—-]/.test(n[at - 1] || '')) score -= 5;     // word start
      return score;
    };

    const hits = [];
    for (const m of state.markers) {
      const names = m.names ? Object.values(m.names) : [m.name || ''];
      let best = null;
      for (const name of names) {
        if (!name) continue;
        const s = rank(name);
        if (s !== null && (best === null || s < best)) best = s;
      }
      if (best === null) continue;
      if (isFound(m)) best += 500;      // found ones sink, but stay reachable
      hits.push([best, m]);
    }
    hits.sort((a, b) => a[0] - b[0] || nameOf(a[1]).localeCompare(nameOf(b[1])));
    const shown = hits.slice(0, 40).map(([, m]) => m);

    results.innerHTML = shown.length
      ? shown.map((m) => `<div class="sr-item" data-id="${m.id}">
           <span class="swatch" style="width:9px;height:9px;border-radius:50%;background:${(CATS[m.cat]||CATS.poi).color}"></span>
           <span>${escapeHtml(nameOf(m))}</span>
           <span class="sr-cat">${isFound(m) ? '✓ ' : ''}${escapeHtml(placeLabel(m))}</span></div>`).join('')
      : `<div class="sr-item dim">${escapeHtml(t('search.none'))}</div>`;
    results.classList.add('open');
    placeSearchResults();
    results.querySelectorAll('.sr-item[data-id]').forEach((el) => {
      el.onclick = () => {
        const m = state.byId.get(el.dataset.id);
        if (!m) return;
        if (m.master !== state.master) switchMaster(m.master);
        results.classList.remove('open');
        search.value = '';
        map.flyTo(m.px, m.py, Math.max(map.scale, 1.4));
        setTimeout(() => showPopup(m), 430);
      };
    });
  };
  document.addEventListener('click', (e) => {
    if (!e.target.closest('.search-wrap')) results.classList.remove('open');
  });

  document.addEventListener('keydown', (e) => {
    if (e.key === 'Escape') { closePopup(); results.classList.remove('open'); }
    if (e.key === '/' && document.activeElement !== search) { e.preventDefault(); search.focus(); }
  });

  // The list is measured against the window, so a resize has to re-measure it.
  // Only the open list needs it; placing a closed one is a no-op.
  window.addEventListener('resize', placeSearchResults);

  setTimeout(() => $('hint').classList.add('gone'), 6000);
}

/* --------------------------------------------------------------- live */

function connect() {
  const es = new EventSource('api/events');
  es.addEventListener('open', () => setLive(true));
  es.addEventListener('error', () => setLive(false));
  es.addEventListener('state', (ev) => {
    try { applyState(JSON.parse(ev.data)); setLive(true); }
    catch (e) { console.error('bad state frame', e); }
  });
  // Real-time position is gone: the player dot comes from the save file, and the
  // map redraws whenever the server reports a newer snapshot.
  es.addEventListener('checked', (ev) => {
    const { id, on } = JSON.parse(ev.data);
    if (on) state.checked[id] = true; else delete state.checked[id];
    refreshCounts(); map.requestDraw();
  });
}

function setLive(on) {
  $('live').classList.toggle('on', on);
  $('live').classList.toggle('off', !on);
  $('live-text').textContent = on ? t('live.on') : t('live.off');
}

function applyState(s) {
  state.checked = s.checked || {};
  state.savePath = s.savePath || state.savePath;

  // The server projects each save position with the same affine as the markers.
  // Every slot is converted, not just the displayed one, because a `pos` frame
  // can switch to any of them without another snapshot arriving first.
  state.characters = (s.characters || []).map((c) => {
    const mp = c.mapPixel;
    return {
      ...c,
      mapPixel: mp ? [mp.px, mp.py] : null,
      mapMaster: mp ? mp.master : null,
      mapHeight: mp && typeof mp.h === 'number' ? mp.h : null,
    };
  });

  // Show the slot the server names: the one picked in the sidebar, or the one
  // the live reader matched to the running game. Neither yet, the first slot.
  const c = state.characters.find((x) => x.slot === s.activeSlot) || state.characters[0] || null;
  state.character = c;
  state.found = new Set(c ? c.found || [] : []);
  refreshSaveEntry(s);
  syncSavePicker();
  if (!c) {
    $('char-name').textContent = t('app.noCharacter');
    refreshCounts();
    if (map) map.requestDraw();
    return;
  }

  renderCharacter(c);
  refreshCounts();
  if (map) map.requestDraw();
  recentreOnPlayer();

  for (const n of (s.newlyFound || [])) {
    for (const id of n.ids.slice(0, 4)) {
      const m = state.byId.get(id);
      if (m) toast(nameOf(m), catLabel(m.cat));
    }
    if (n.ids.length > 4) toast(`+${n.ids.length - 4} ${t('toast.more')}`, t('toast.discovered'));
  }
}

/** One line naming where the player dot comes from. */
function liveBadge() {
  return `<br><span style="color:#8fb87a">&#9679; ${escapeHtml(t('live.bySave'))}</span>`;
}

/** Sidebar character panel. Split out so a language switch can re-render it. */
/**
 * Your own height, so a marker's number reads as high or low without
 * arithmetic, plus the live-reader badge. Split out of renderCharacter because
 * the height moves with you: the position feed calls this on every sample,
 * which is 20 a second, and re-rendering the whole panel at that rate would
 * rebuild the stat grid for nothing.
 */
function renderWhere(c) {
  const el = $('char-where');
  if (!el) return;
  if (c && !c.position && c.error) {
    el.innerHTML = `<span style="color:#e05a5a">${escapeHtml(t('err.saveRead'))}: ${escapeHtml(c.error)}</span>`;
    return;
  }
  const you = playerTarget();
  const h = you && typeof you.h === 'number'
    ? `${escapeHtml(t('label.height'))} <b>${you.h}</b> ${escapeHtml(t('unit.m'))}` : '';
  el.innerHTML = h + liveBadge();
}

function renderCharacter(c) {
  $('char-name').textContent = c.name || '—';
  const secs = c.secondsPlayed || 0;
  const hrs = Math.floor(secs / 3600);
  const mins = Math.floor((secs % 3600) / 60);
  $('char-meta').textContent =
    `${t('char.level')} ${c.level} · ${hrs}${t('char.hoursShort')} ` +
    `${String(mins).padStart(2, '0')}${t('char.minutesShort')}` +
    (c.deaths != null ? ` · ${c.deaths} ${I18n.plural('char.deaths', c.deaths)}` : '');

  // Stat labels come from i18n so they can be the game's own wording per
  // language (生命力 / Endurance) instead of English glyphs.
  const st = c.stats;
  $('char-stats').innerHTML = st ? [
    ['vig', st.vigor], ['mnd', st.mind], ['end', st.endurance], ['str', st.strength],
    ['dex', st.dexterity], ['int', st.intelligence], ['fth', st.faith], ['arc', st.arcane],
  ].map(([k, v]) => `<div class="stat"><b>${v}</b><span>${escapeHtml(t('stat.' + k))}</span></div>`).join('') : '';

  renderWhere(c);

  if (!c.ok && c.error) {
    $('foot-text').textContent = `${t('err.parse')}: ${c.error}`;
  } else {
    $('foot-text').textContent =
      `${state.markers.length} ${t('foot.markers')} · ${t('foot.flagsAt')} 0x${(c.flagOffset || 0).toString(16)}`;
  }
}

function toast(title, sub) {
  const el = document.createElement('div');
  el.className = 'toast';
  el.innerHTML = `<div>${escapeHtml(title)}</div><div class="t-cat">${escapeHtml(sub || '')}</div>`;
  $('toasts').appendChild(el);
  setTimeout(() => { el.style.transition = 'opacity .5s'; el.style.opacity = '0'; }, 4200);
  setTimeout(() => el.remove(), 4800);
}

// Nothing runs until the DOM exists; boot() pulls the data and wires the UI.
boot();
