/**
 * Shared state, DOM helpers and the progress policy.
 *
 * Everything the other modules agree on: the `state` object, the `$`/`t`/`nameOf` helpers, the marker
 * icon loader, `isFound`, and the rule that decides which categories count towards the completion
 * figure (fed by data/layers.json through applyLayerPolicy).
 *
 * The map instance lives here too, because almost every module needs to ask it to redraw; it is set
 * once by app.js through setMap() rather than imported as a mutable binding.
 */
import { CATS, CAT_GROUPS, EXTRA_CATS, OFF_BY_DEFAULT } from './catalog.js';

export const $ = (id) => document.getElementById(id);
export const t = (k) => I18n.t(k);
export const nameOf = (m) => I18n.name(m);
/**
 * A row's label, from the first source that has this language:
 *
 * 1. the hand-written label (web/js/i18n.js, one per named category);
 * 2. the name the layer document carries for the category - a gatherable row's material name, read out of
 *    the game's own message files, so it is correct in Chinese and in English;
 * 3. a marker of that category (the same name, used when the policy predates the names field);
 * 4. the bare item key in i18n (English names only, from before the policy carried them);
 * 5. the key itself, so a future category still shows something.
 */
export const catLabel = (k) => {
  const label = t('cat.' + k);
  if (label !== 'cat.' + k) return label;
  const fromDoc = CAT_NAMES.get(k);
  if (fromDoc) {
    const name = fromDoc[I18n.lang] || fromDoc.en || fromDoc.zh;
    if (name) return name;
  }
  const named = state.catNames.get(k);
  if (named) {
    const name = nameOf(named);
    if (name) return name;
  }
  const bare = t(k);
  if (bare !== k) return bare;
  return k;
};
// A raw master code (M10) is a developer's handle for a map; the player knows the
// layer by its name. t() returns the key unchanged when a translation is missing,
// so a master added by a future patch still shows something rather than nothing.
export const layerLabel = (id) => {
  if (!id) return '';
  const name = t('master.' + id);
  return name === 'master.' + id ? id : name;
};
export const state = {
  // Which category groups are expanded. Defaults to all of them, so a first
  // run shows the full legend; loadPrefs() then applies whatever was saved.
  groupOpen: new Set(CAT_GROUPS.map((g) => g.id)),
  markers: [],
  byId: new Map(),
  // Rewards with a verdict but no coordinates (data/quest-rewards-unplaced.json): listed, never drawn.
  registered: [],
  // category -> the iconId most of its markers carry; see legendSwatch()
  categoryIconIds: new Map(),
  // category -> a marker of that category, for a row label the i18n files do not carry
  catNames: new Map(),
  regions: [],          // the game's region labels, from api/markers
  places: [],           // graces and POIs, for "nearest named place"
  manifest: null,
  master: 'M00',
  enabled: new Set(Object.keys(CATS).filter((k) => !OFF_BY_DEFAULT.has(k))),
  found: new Set(),
  checked: {},
  hideFound: false,
  showLabels: true,
  saves: [],            // every ER0000.* the server found, from api/saves
  savePath: null,       // the one it is currently watching
  characters: [],       // every slot in that save
  character: null,      // the slot being displayed
  selected: null,
  hovered: null,
  clusters: [],
  playerRender: null,   // eased toward the player's last saved position so the dot glides
  icons: null,          // iconId -> {file,w,h}, from web/icons/index.json
  iconImgs: new Map(),  // icon key -> HTMLImageElement, loaded lazily
  showIcons: true,      // draw real sprites instead of coloured dots
  followPlayer: false,  // keep re-centring on the player until told to stop
};

/**
 * Reduce CATS to the categories this data set actually uses, after folding in
 * the legacy names it also uses. See EXTRA_CATS above for why both halves exist.
 *
 * Called from boot() once the markers are in and before anything reads CATS:
 * applyPrefsToState() rebuilds state.enabled from CATS, savePrefs() records
 * Object.keys(CATS) as the "known" set, and buildCategories() renders one row
 * per key - all three have to run against the final table.
 */
export function restrictCatsToData() {
  const used = new Set(state.markers.map((m) => m.cat));
  for (const m of state.markers) {
    if (m.names && !state.catNames.has(m.cat)) state.catNames.set(m.cat, m);
  }
  // Categories of a layer that is still on its way (data/layers.json lists them) count as used: the
  // sidebar, the saved checkboxes and the progress rows are built once, at boot, and a gatherable
  // category that was dropped here could not come back when its markers arrive a moment later.
  for (const cat of POLICY_CATS) used.add(cat);
  for (const [key, def] of Object.entries(EXTRA_CATS)) {
    if (!used.has(key) || CATS[key]) continue;
    CATS[key] = { color: def.color, r: def.r, icon: def.icon };
    const group = CAT_GROUPS.find((g) => g.id === def.group);
    if (group && !group.cats.includes(key)) group.cats.push(key);
    if (!OFF_BY_DEFAULT.has(key)) state.enabled.add(key);
  }
  // A lazy layer's categories need a row before its markers arrive, because the sidebar and the saved
  // tick state are built once. One row per collected material (gather_<item id>) is what the extraction
  // produces, so without this the whole gather-nodes layer would have nowhere to show up. Rows for
  // categories that never carry a marker (the coordinate-less quest-reward registry, "unplaced") are not
  // created here: it belongs to a layer the client already has, and an empty row would only mislead.
  for (const [cat, info] of LAZY_CATS) {
    if (CATS[cat]) continue;
    CATS[cat] = { color: (CATS.gathering && CATS.gathering.color) || '#7fae7f', r: 3 };
    const group = CAT_GROUPS.find((g) => g.cats.includes('gathering'));
    if (group && !group.cats.includes(cat)) group.cats.push(cat);
    // Gatherable nodes come back when you rest, so their rows start switched off, exactly like the
    // single "gathering" row used to; a counting category of a lazy layer starts on.
    if (info.progress !== 'spots') state.enabled.add(cat);
  }
  for (const key of Object.keys(CATS)) {
    if (!used.has(key)) { delete CATS[key]; state.enabled.delete(key); }
  }
}

/** Load an icon once, redrawing when it arrives; null until it is ready. */
export function loadIcon(key, src) {
  let img = state.iconImgs.get(key);
  if (img === undefined) {
    img = new Image();
    img.decoding = 'async';
    img.onload = () => { if (map) map.requestDraw(); };
    img.onerror = () => state.iconImgs.set(key, null);
    img.src = src;
    state.iconImgs.set(key, img);
  }
  return img && img.complete && img.naturalWidth ? img : null;
}

/**
 * Marker sprites, from the marker's own data. Preference order:
 *
 *   1. the item's own sprite (icons/items/<iconId>.png), so a marker on the map
 *      looks exactly like its row in the legend - gold rune [13] on the map is
 *      the same picture as gold rune [13] in the sidebar;
 *   2. otherwise the category sprite, for the few categories with no in-game
 *      icon of their own;
 *   3. a world marker's numeric iconId, cut out of the game's map atlases;
 *   4. nothing, in which case the marker falls back to a coloured dot.
 *
 * All of it is optional: without extract_icons.py the map still draws.
 */
export function iconFor(mk) {
  if (!state.showIcons) return null;
  const itemMeta = mk.iconId && state.itemIcons && state.itemIcons[String(mk.iconId)];
  if (itemMeta) {
    // Prefixed so an item icon id cannot collide with a map icon id in the cache.
    const img = loadIcon('item:' + mk.iconId, itemMeta.file);
    if (img) return { img, meta: itemMeta };
  }
  if (!mk.icon) return null;
  const key = mk.icon;
  if (!state.icons) return null;
  const meta = state.icons[key];
  if (!meta) return null;
  const img = loadIcon(key, meta.file);
  return img ? { img, meta } : null;
}
export function isFound(m) {
  return state.found.has(m.id) || !!state.checked[m.id];
}
export const NO_PROGRESS = new Set(['gathering']);
export let SPOTS_CATS = null;          // categories the layer document marks as spots, when it is present
export const POLICY_CATS = new Set();  // every category the layer document declares, loaded or not
// category -> {locale: name} as the layer document carries it, so a row can be labelled before the
// markers of a lazy layer arrive (and without depending on an i18n key existing).
export const CAT_NAMES = new Map();
// Categories of a layer the registry marks as `lazy` (its markers arrive after the first paint), with
// that layer's progress accounting, so restrictCatsToData() can give each of them a row up front.
export const LAZY_CATS = new Map();

/**
 * Adopt the layer document's progress policy (data/layers.json, sent with the markers).
 *
 * A category that a spots layer and a counting layer both use is already marked "counts" there (the
 * farm layer reuses its categories for nodes that are also pickups), so the client does not have to
 * work that out from the marker list any more.
 */
export function applyLayerPolicy(doc) {
  if (!doc || !doc.cats) return;
  const spots = new Set();
  for (const [cat, info] of Object.entries(doc.cats)) {
    POLICY_CATS.add(cat);
    if (info && info.progress === 'spots') spots.add(cat);
    if (info && info.names) CAT_NAMES.set(cat, info.names);
  }
  LAZY_CATS.clear();
  for (const layer of doc.layers || []) {
    if (layer.client !== 'lazy') continue;
    for (const cat of layer.categories || []) {
      LAZY_CATS.set(cat, { progress: layer.progress, layer: layer.id });
    }
  }
  for (const cat of NO_PROGRESS) spots.add(cat);
  SPOTS_CATS = spots;
}

/**
 * Gatherable nodes that come back when you rest are counted as spots, not as progress: one category
 * per collected material (gather_<item id>) is out of the totals, exactly like the old single
 * 'gathering' row used to be. A node the extractor marked `once` never comes back, so those count -
 * and a category holding both kinds is scored on its one-time nodes alone.
 */
export function isNoProgress(cat) {
  if (SPOTS_CATS) return SPOTS_CATS.has(cat) || cat.startsWith('gather_');
  return NO_PROGRESS.has(cat) || (typeof cat === 'string' && cat.startsWith('gather_'));
}
export function escapeHtml(s) {
  return String(s).replace(/[&<>"']/g, (c) =>
    ({ '&': '&amp;', '<': '&lt;', '>': '&gt;', '"': '&quot;', "'": '&#39;' }[c]));
}

/** The tile map, created by app.js in initMap(). */
export let map = null;

/** Called once by app.js with the new TileMap instance. */
export function setMap(instance) {
  map = instance;
}
