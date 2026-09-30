'use strict';
/**
 * Elden Ring live map — client.
 *
 * Talks to the local server: markers + tile manifest once, then a Server-Sent
 * Events stream that pushes a fresh snapshot every time the save file changes.
 */

// Labels come from i18n ('cat.<key>'); only presentation lives here.
// Order here is the order shown in the sidebar: world markers from
// build_markers.py first, then the item categories from extract_items.py.
//
// Rows draw the item's own sprite from icons/items/, resolved through the iconId
// each marker carries; a row with no sprite falls back to its colour disc.

// Glovewort ladders, declared for the same reason as the runes above: a row per
// level, split by family, so the row's swatch can be the level's own sprite
// instead of whichever level happens to carry the most markers. The two level-less
// "Great" pieces get a row each beside their family. mfg_categories.py holds the
// matching id -> (family, level) table; the level is the id's offset, so nothing
// is guessed on either side.
const GLOVEWORT_LADDER = [
  { family: 'grave', max: 9, color: '#c9b5d8' },   // 墓地铃兰【1】-【9】
  { family: 'ghost', max: 9, color: '#a890c9' },   // 灵依墓地铃兰【1】-【9】
];
const GLOVEWORT_CATS = GLOVEWORT_LADDER.flatMap((l) =>
  Array.from({ length: l.max }, (_, i) => `glovewort_${l.family}_${i + 1}`));

// Rune ladders: the family, how many levels the game actually has, and how its
// rows look. Declared once and used by both CATS and the legend group, so a row
// cannot exist in one and not the other. mfg_categories.py holds the matching
// ladders on the classifier side; the level itself comes from the game's own
// item name ("Golden Rune [7]"), so no level is invented here.
// `split` is the level that starts the "high" look (0 = the family has no low/high
// distinction, which is what the old two-bucket scheme wrongly imposed on it).
const RUNE_LADDER = [
  { family: 'golden', max: 13, split: 9, low: '#d8c040', high: '#e8d04a' },
  { family: 'hero',   max: 5,  split: 0, low: '#f0c860', high: '#f0c860',
    lowIcon: 'rune_high.png', highIcon: 'rune_high.png' },
  // The DLC family keeps its own sprite so it does not read as a base-game rune.
  { family: 'shadow', max: 7,  split: 0, low: '#c8b8e8', high: '#c8b8e8',
    lowIcon: 'rune_piece.png', highIcon: 'rune_piece.png' },
];
const RUNE_CATS = RUNE_LADDER.flatMap((l) =>
  Array.from({ length: l.max }, (_, i) => `${l.family}_rune_${i + 1}`));

const CATS = {
  grace:     { color: '#ffd766', r: 6 },
  boss:      { color: '#e05a5a', r: 6 },
  poi:       { color: '#6fb7e8', r: 5 },
  region:    { color: '#9aa0a8', r: 5 },
  fragment:  { color: '#c58bea', r: 5 },
  landmark:  { color: '#8fa3b8', r: 4 },
  // --- equipment ---
  armaments:    { color: '#d4805a', r: 4 },
  armour:       { color: '#a08f76', r: 4 },
  ashes_of_war: { color: '#b58bea', r: 4 },
  spirits:      { color: '#8be8d0', r: 4 },
  talismans:    { color: '#e8b84a', r: 4 },
  // Merchants: NPC parts read out of the map files (tools/extract_items.py,
  // npcs.json), not param rows - the game's own map data has no merchant points.
  merchants:    { color: '#e0b070', r: 4 },
  // --- key items ---
  celestial_dew:      { color: '#aed8ff', r: 4 },
  cookbooks:          { color: '#d9c89a', r: 4 },
  crystal_tears:      { color: '#7dd0ff', r: 4 },
  imbued_sword_keys:  { color: '#b0c4ff', r: 4 },
  larval_tears:       { color: '#ff9dd6', r: 4 },
  lost_ashes:         { color: '#cf9fe8', r: 4 },
  pots_n_perfumes:    { color: '#c9b58a', r: 4 },
  golden_seeds:       { color: '#8ede7a', r: 4 },
  sacred_tears:       { color: '#a8e0ff', r: 4 },
  spirit_blessing:    { color: '#cfe8b0', r: 4 },
  scadutree_fragments:{ color: '#e8d8a0', r: 4 },
  whetblades:         { color: '#c9c9c9', r: 4 },
  great_runes:        { color: '#ffd766', r: 4 },
  // --- loot ---
  ammo:                  { color: '#c9a06a', r: 4 },
  // One-time rewards that hang off a character rather than a treasure event,
  // split by what the reward is (tools/extract_items.py writes data/drops.json):
  // a bell bearing is not a weapon, and that is what a player looks for.
  drop_bell_bearings:    { color: '#e0a0c8', r: 4 },
  drop_weapons:          { color: '#d8a0e0', r: 4 },
  drop_armour:           { color: '#c8a8d8', r: 4 },
  drop_talismans:        { color: '#e8b0c0', r: 4 },
  drop_items:            { color: '#d0a8c0', r: 4 },
  // Every enemy-drop item that has no placed pickup, marked where the enemy
  // stands (tools/extract_farm_nodes.py --all-unmarked). One row on purpose:
  // the marker carries the item's own name and icon, so a spot still says what
  // it is without a category per item.
  farm_spots:            { color: '#7fb0a8', r: 3 },
  // What a boss leaves behind: its loot, plus the Remembrance or Great
  // Rune. Read from the event scripts and from the item's own name
  // (tools/extract_items.py, data/boss-drops.json).
  boss_drops:            { color: '#e08a6a', r: 5 },
  // Bell bearings, split by what the Twin Maiden Husks unlock with them. These
  // icons are now only the fallback: the legend prefers the item's own sprite
  // (see legendSwatch), and for the four miner/picker families that sprite is one
  // and the same bell. mfg_categories.py sets the same sprite on the markers too.
  bell_smithing:         { color: '#c9a868', r: 4 },
  bell_somber:           { color: '#b89ad0', r: 4 },
  bell_glovewort:        { color: '#c9b5d8', r: 4 },
  bell_ghost_glovewort:  { color: '#a890c9', r: 4 },
  merchant_bell_bearings:{ color: '#d88a4a', r: 4 },
  consumables:           { color: '#9fbf8f', r: 3 },
  greases:               { color: '#c9d17a', r: 3 },
  utilities:             { color: '#8fb8a8', r: 3 },
  stat_boosts:           { color: '#d8a8c8', r: 3 },
  crafting_materials:    { color: '#7fae7f', r: 3 },
  // Picked from the ground: excluded from the progress totals below, because the
  // nodes come back when you rest. Read out of the game's own crafting list.
  gathering:             { color: '#7fae7f', r: 3 },
  // Gloveworts, split by level and family like the smithing stones. Rows that no
  // lot on the map can fill (墓地铃兰【2】-【4】, 灵依墓地铃兰【1】-【4】: shop stock,
  // see docs) are dropped by restrictCatsToData() rather than shown as 0/0.
  ...Object.fromEntries(GLOVEWORT_LADDER.flatMap((l) => [
    ...Array.from({ length: l.max }, (_, i) => {
      const n = i + 1;
      return [`glovewort_${l.family}_${n}`, { color: l.color, r: n <= 6 ? 3 : 4 }];
    }),
    [`glovewort_${l.family}_great`, { color: l.color, r: 4 }],
  ])),
  // Runes, split by level the way the smithing stones are. The previous scheme
  // was two rows, golden_runes_low and golden_runes, which cut three different
  // ladders at three different points: Golden Rune at [8]/[9] but Shadow Realm
  // Rune at [2]/[3], and Hero's Rune [1] was filed beside Golden Rune [13].
  ...Object.fromEntries(RUNE_LADDER.flatMap((l) =>
    Array.from({ length: l.max }, (_, i) => {
      const n = i + 1;
      const low = l.split === 0 || n < l.split;
      return [`${l.family}_rune_${n}`,
              { color: low ? l.low : l.high, r: low ? 3 : 4 }];
    }))),
  special_runes:         { color: '#ffe08a', r: 4 },
  broken_rune:           { color: '#a8a08a', r: 3 },
  material_nodes:        { color: '#7fae7f', r: 3 },
  mp_fingers:            { color: '#c9a8a8', r: 3 },
  prattling_pates:       { color: '#e0c8a0', r: 3 },
  gestures:              { color: '#c0c9d8', r: 3 },
  reusables:             { color: '#a8c9c0', r: 3 },
  // Smithing stones are split by level and by somber/normal, so the legend can
  // single out "Somber Smithing Stone [7]" instead of lumping every tier into
  // three rarity buckets. The ladder is [1]-[8] normal and [1]-[9] somber: the
  // game has no [10]. An earlier pass called the DLC ids [10] and so showed a
  // level that does not exist; those are the Shadow stones and get their own
  // rows below, a name that claims nothing about a level.
  ...Object.fromEntries([
    ...Array.from({ length: 8 }, (_, i) => {
      const n = i + 1;
      return [`smithing_stone_${n}`, { color: n <= 6 ? '#c9a868' : '#d8b878',
                                       r: n <= 6 ? 3 : 4,
                                       icon: n <= 6 ? 'smst_low.png' : 'smst.png' }];
    }),
    ...Array.from({ length: 9 }, (_, i) => {
      const n = i + 1;
      return [`somber_stone_${n}`, { color: '#b89ad0', r: n <= 6 ? 3 : 4,
                                     icon: n <= 6 ? 'smst_low.png' : 'smst.png' }];
    }),
  ]),
  smithing_stone_shadow: { color: '#a89e8c', r: 4 },
  somber_stone_shadow:   { color: '#9a8ab0', r: 4 },
  smithing_stone_legend: { color: '#e0c890', r: 4 },
  somber_stone_legend:   { color: '#cfaee0', r: 4 },

  // --- consumables ---
  stonesword_keys:       { color: '#b0c0e0', r: 4 },
  throwables:            { color: '#c9a0a0', r: 3 },
  rune_arcs:             { color: '#e8d878', r: 4 },
  dragon_hearts:         { color: '#e08080', r: 4 },
  // --- magic ---
  incantations:  { color: '#e8b878', r: 4 },
  memory_stones: { color: '#c9b8e0', r: 4 },
  prayerbooks:   { color: '#d8c8a0', r: 4 },
  sorceries:     { color: '#8bb8e8', r: 4 },
  // --- quest ---
  deathroot:      { color: '#c08080', r: 4 },
  progression:    { color: '#c0a8d8', r: 4 },
  seedbed_curses: { color: '#a080c0', r: 4 },
  // --- Elden Ring Reforged only ---
  ember_pieces:      { color: '#ff8a5a', r: 4 },
  items_and_changes: { color: '#d8a8e0', r: 4 },
  fortunes:          { color: '#e8c080', r: 4 },
  rune_pieces:       { color: '#ffd080', r: 4 },
  sealed_curios:     { color: '#b8a8d8', r: 4 },
  // --- fallback ---
  misc: { color: '#6f6f6f', r: 3 },
};

// The sidebar renders one row per category. With the smithing stones and the
// runes split by level that is over a hundred rows, which is a wall, so rows are
// presented under collapsible group headers. Groups also fix the display ORDER:
// the smithing families read as normal [1]..[8], somber [1]..[9], then the
// legendary pair, instead of interleaving the families level by level. (A stale
// data/items.json adds a few rows back through EXTRA_CATS, so the row count is
// not fixed.)
const CAT_GROUPS = [
  { id: 'basic',   label: 'group.basic',
    cats: ['grace', 'boss', 'poi', 'region', 'fragment', 'landmark',
           'merchants', 'material_nodes'] },
  { id: 'gear',    label: 'group.gear',
    cats: ['armaments', 'armour', 'talismans', 'ashes_of_war', 'spirits'] },
  { id: 'upgrade', label: 'group.upgrade',
    cats: ['smithing_stone_1', 'smithing_stone_2', 'smithing_stone_3',
           'smithing_stone_4', 'smithing_stone_5', 'smithing_stone_6',
           'smithing_stone_7', 'smithing_stone_8',
           'smithing_stone_shadow', 'smithing_stone_legend',
           'somber_stone_1', 'somber_stone_2', 'somber_stone_3',
           'somber_stone_4', 'somber_stone_5', 'somber_stone_6',
           'somber_stone_7', 'somber_stone_8', 'somber_stone_9',
           'somber_stone_shadow', 'somber_stone_legend',
           ...GLOVEWORT_CATS,
           'glovewort_grave_great', 'glovewort_ghost_great', 'whetblades'] },
  { id: 'blessing', label: 'group.blessing',
    cats: ['golden_seeds', 'sacred_tears', 'spirit_blessing',
           'scadutree_fragments', 'crystal_tears', 'celestial_dew',
           'larval_tears', 'great_runes', 'memory_stones', 'imbued_sword_keys'] },
  { id: 'consum',  label: 'group.consum',
    cats: ['consumables', 'greases', 'utilities', 'stat_boosts', 'throwables',
           'pots_n_perfumes', 'gathering', 'crafting_materials', 'cookbooks', 'reusables'] },
  { id: 'runes',   label: 'group.runes',
    cats: [...RUNE_CATS, 'special_runes', 'broken_rune', 'rune_arcs'] },
  { id: 'magic',   label: 'group.magic',
    cats: ['incantations', 'sorceries', 'prayerbooks'] },
  { id: 'quest',   label: 'group.quest',
    cats: ['progression', 'deathroot', 'seedbed_curses'] },
  { id: 'loot',    label: 'group.loot',
    cats: ['bell_smithing', 'bell_somber', 'bell_glovewort',
           'bell_ghost_glovewort', 'merchant_bell_bearings', 'drop_bell_bearings', 'drop_weapons',
           'drop_armour', 'drop_talismans', 'drop_items',
           'boss_drops', 'farm_spots', 'stonesword_keys',
           'lost_ashes', 'mp_fingers', 'gestures', 'prattling_pates',
           'dragon_hearts', 'ammo'] },
  { id: 'reforged', label: 'group.reforged',
    cats: ['ember_pieces', 'items_and_changes', 'fortunes', 'sealed_curios'] },
];

// Anything not named above (misc) renders without a header, at the end.
const GROUPED_CATS = new Set(CAT_GROUPS.flatMap((g) => g.cats));
const UNGROUPED_CATS = Object.keys(CATS).filter((k) => !GROUPED_CATS.has(k));

// The legend shows one row per category the loaded markers actually use.
//
// That takes two halves, and both are needed:
//
//   * EXTRA_CATS below names categories an older tools/extract_items.py wrote
//     and the current one does not. data/items.json is a build product, so a copy
//     generated before a reclassification still carries the old names; these are
//     folded back in when the file on disk really uses them.
//   * every CATS entry the data does not use is dropped by restrictCatsToData().
//     That is what keeps the sidebar to what exists on this game, profile and
//     content install, instead of a wall of 0/0 rows for categories that can
//     never have a marker here (Reforged's five, the Shadow-realm stones, Great
//     Runes, gestures, dragon hearts...).
//
// The dropping half has to stay honest in the other direction: a marker whose
// category is missing from CATS is unreachable, because visibleMarkers() keys
// off state.enabled and state.enabled is only ever filled from CATS. So the rule
// is "drop what nothing uses", never "drop what looks empty on this map layer" -
// otherwise updating the code without re-running extract_items.py would quietly
// take 454 smithing-stone markers off the map, which is exactly what an earlier
// version of this file did.
const EXTRA_CATS = {
  smithing_stones:      { group: 'upgrade',  color: '#c9a868', r: 3 },
  // The pre-split material bucket: an items.json from before gathering was split
  // out still names it, and a marker whose category is missing from CATS is
  // unreachable, so it stays until the data is rebuilt.
  crafting_materials:   { group: 'consum',   color: '#7fae7f', r: 3 },
  // The pre-split reward category: a data/drops.json generated before the
  // rewards were split by kind still names it, and a marker whose category is
  // missing from CATS is unreachable, so it stays until the data is rebuilt.
  one_time_drops:       { group: 'loot',     color: '#e0a0c8', r: 4 },
  smithing_stones_low:  { group: 'upgrade',  color: '#c9a868', r: 3 },
  smithing_stones_rare: { group: 'upgrade',  color: '#e0c890', r: 4 },
  // The pre-split glovewort rows: a data/items.json generated before the ladder
  // above still names them, and a marker whose category is missing from CATS is
  // unreachable, so they stay until the dataset is rebuilt.
  gloveworts:           { group: 'upgrade',  color: '#c9b5d8', r: 3 },
  great_gloveworts:     { group: 'upgrade',  color: '#a890c9', r: 3 },
  seeds_tears:          { group: 'blessing', color: '#8ede7a', r: 4 },
  bell_bearings:        { group: 'loot',     color: '#e0a35a', r: 4 },
  golden_runes:         { group: 'runes',    color: '#e8d04a', r: 4 },
  golden_runes_low:     { group: 'runes',    color: '#d8c040', r: 3 },
};


// High-volume categories that bury the map when they are all on at once. They
// start hidden and can be switched on from the sidebar.
const OFF_BY_DEFAULT = new Set(['misc', 'consumables', 'gathering', 'crafting_materials', 'ammo']);
const FOUND_COLOR = '#6fcf7a';

const $ = (id) => document.getElementById(id);
const t = (k) => I18n.t(k);
const nameOf = (m) => I18n.name(m);
const catLabel = (k) => t('cat.' + k);
// A raw master code (M10) is a developer's handle for a map; the player knows the
// layer by its name. t() returns the key unchanged when a translation is missing,
// so a master added by a future patch still shows something rather than nothing.
const layerLabel = (id) => {
  if (!id) return '';
  const name = t('master.' + id);
  return name === 'master.' + id ? id : name;
};

/* Where a marker is, in the game's own words.
 *
 * "The Lands Between" is the whole game, so it tells a player nothing about which
 * of the eleven Nomadic Merchants - or which of the 3,300 items - a marker is.
 * data/regions.json (build_markers.py) carries the region labels the world map
 * itself shows: Limgrave, Liurnia of the Lakes, Caelid, Ainsel River, Realm of
 * Shadow. Those labels have rectangles, but the rectangles overlap and leave
 * gaps, and the starting area has no rectangle at all because the game reveals it
 * from the start - that one is flagged `default` and is what a marker falls back
 * to when no rectangle is near.
 *
 * Beside the region goes the nearest grace or POI, which is the part that is
 * actually actionable: "Liurnia of the Lakes (Bellum Church)". It is dropped when
 * the marker's own name already says it - a grace is its own nearest place, and a
 * merchant's name carries its spot.
 */
const REGION_NEAR_MAX = 400;      // master px; further away is not "here"
const REGION_FAMILY = { M11: 'M10' };   // the DLC's underground shares M10's labels
const dictName = (d) => (d ? (d[I18n.lang] || d.en || '') : '');

/**
 * Longest run of characters two names share, so a place can vouch for a region.
 *
 * The rectangles are the map pieces' reveal areas, which are narrower than the
 * regions the labels name: the grace "Liurnia Lake Shore" sits just outside the
 * Liurnia rectangle, in Limgrave's. The game's own text settles it - a grace name
 * that shares a decent run with a region name ("利耶尼亚湖" / "湖之利耶尼亚",
 * "Liurnia Lake Shore" / "Liurnia of the Lakes") is evidence the rectangle rule
 * does not have.
 */
function sharedRun(a, b) {
  let best = 0;
  const prev = new Array(b.length + 1).fill(0);
  for (let i = 1; i <= a.length; i++) {
    let last = 0;
    for (let j = 1; j <= b.length; j++) {
      const cur = prev[j];
      prev[j] = a[i - 1] === b[j - 1] ? last + 1 : 0;
      if (prev[j] > best) best = prev[j];
      last = cur;
    }
  }
  return best;
}

function regionFor(m, near) {
  if (!m || m.px == null || !state.regions.length) return null;
  const layer = REGION_FAMILY[m.master] || m.master;
  const usable = state.regions.filter((r) => !r.masters || !layer || r.masters.includes(layer));
  // A nearby place whose name names a region wins over the rectangles.
  for (const name of [dictName(near), ...Object.values(near || {})]) {
    if (!name || name.length < 3) continue;
    const hinted = usable.filter((r) => sharedRun(name, dictName(r.names)) >= 3);
    if (hinted.length === 1) return hinted[0];
  }
  let best = null, bestD = Infinity, fallback = null;
  for (const r of usable) {
    if (r.default) { fallback = r; continue; }
    const [l, top, right, b] = r.rect;
    const dx = m.px < l ? l - m.px : (m.px > right ? m.px - right : 0);
    const dy = m.py < top ? top - m.py : (m.py > b ? m.py - b : 0);
    const d = Math.sqrt(dx * dx + dy * dy);
    if (d < bestD) { bestD = d; best = r; }
  }
  return (best && bestD <= REGION_NEAR_MAX) ? best : (fallback || best);
}

function nearFor(m) {
  if (!m || m.px == null) return null;
  let best = null, bestD = Infinity;
  for (const p of state.places) {
    if (p === m || p.master !== m.master) continue;
    const d = (p.px - m.px) ** 2 + (p.py - m.py) ** 2;
    if (d < bestD) { bestD = d; best = p; }
  }
  if (!best) return null;
  const mine = m.names ? Object.values(m.names) : [];
  return Object.values(best.names || {}).some((v) => v && mine.includes(v))
    ? null : best.names;
}

function annotatePlace(m) {
  const n = nearFor(m);
  if (n) m.near = n;
  const r = regionFor(m, n);
  if (r) m.region = r.names;
  return m;
}

function placeLabel(m) {
  const region = dictName(m.region);
  const near = dictName(m.near);
  if (region) return near ? `${region}（${near}）` : region;
  return m.master ? layerLabel(m.master) : '';
}

const state = {
  // Which category groups are expanded. Defaults to all of them, so a first
  // run shows the full legend; loadPrefs() then applies whatever was saved.
  groupOpen: new Set(CAT_GROUPS.map((g) => g.id)),
  markers: [],
  byId: new Map(),
  // category -> the iconId most of its markers carry; see legendSwatch()
  categoryIconIds: new Map(),
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
  livePos: null,        // newest sample from the memory reader
  liveStatus: null,     // 'live' | 'waiting' | 'error' | ...
  playerRender: null,   // eased toward livePos so the dot glides
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
function restrictCatsToData() {
  const used = new Set(state.markers.map((m) => m.cat));
  for (const [key, def] of Object.entries(EXTRA_CATS)) {
    if (!used.has(key) || CATS[key]) continue;
    CATS[key] = { color: def.color, r: def.r, icon: def.icon };
    const group = CAT_GROUPS.find((g) => g.id === def.group);
    if (group && !group.cats.includes(key)) group.cats.push(key);
    if (!OFF_BY_DEFAULT.has(key)) state.enabled.add(key);
  }
  for (const key of Object.keys(CATS)) {
    if (!used.has(key)) { delete CATS[key]; state.enabled.delete(key); }
  }
}

/** Load an icon once, redrawing when it arrives; null until it is ready. */
function loadIcon(key, src) {
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
function iconFor(mk) {
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

let map = null;

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
  state.saves = saveDoc.saves || [];
  state.savePath = saveDoc.current || null;
  for (const m of state.markers) state.byId.set(m.id, m);
  state.regions = markerDoc.regions || [];
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
  initMap(state.master);
  wireUi();
  startKeepAlive();
  applyPrefsToUi(prefs);
  buildSavePicker();
  connect();

  // Language changes only ever affect text, so nothing needs reloading.
  I18n.onChange(() => {
    buildLangSwitch();
    buildLayerButtons();
    buildCategories();
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

function initMap(masterId) {
  return _initMap(masterId);
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

  map = new TileMap($('map'), {
    tileSize: (state.manifest && state.manifest.tileSize) || 256,
    width: info ? info.width : 10496,
    height: info ? info.height : 10496,
    nativeZoom: info ? info.nativeZoom : 6,
    tileIndex: tileIndexFor(masterId),
    tileUrl: (z, x, y) => `tiles/${masterId}/${z}/${x}/${y}.${fmt}`,
    drawOverlay: drawMarkers,
    onClick: handleClick,
    onHover: handleHover,
  });
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

function isFound(m) {
  return state.found.has(m.id) || !!state.checked[m.id];
}

const CLUSTER_CELL_PX = 46;     // roughly how big a cluster cell looks on screen
// Quantised zoom steps per doubling. Coarser steps mean the cell drifts further
// from CLUSTER_CELL_PX before it snaps back - at 2 it reached 65px and visibly
// over-merged; 4 holds it to 46-55px.
const CLUSTER_STEPS = 4;

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
 * Prefers the live memory feed when it is running, otherwise falls back to the
 * position recorded in the last save. Live samples arrive at ~20 Hz while the
 * canvas redraws at display rate, so the rendered point is eased toward the
 * newest sample rather than snapped to it.
 */
const LIVE_STALE_MS = 5000;

/**
 * The player dot animates (pulse ring, eased motion), which means the canvas
 * has to keep redrawing. Doing that every animation frame would spin the GPU at
 * display rate for the whole session - wasteful in general, and actively rude
 * when this is running alongside the game it is tracking. ~18 fps is smooth
 * enough for a marker and costs a fraction of that. Nothing is scheduled at all
 * while the tab is in the background.
 */
const ANIM_INTERVAL_MS = 55;
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
  const p = state.livePos;
  if (p && Date.now() - p.t < LIVE_STALE_MS) {
    // p.h is only present when the server could verify the reading against the
    // map-screen pixel; in a legacy dungeon it cannot, so fall back to the save.
    const saved = state.character;
    const h = typeof p.h === 'number' ? p.h
            : (saved && typeof saved.mapHeight === 'number' ? saved.mapHeight : null);
    return { px: p.px, py: p.py, master: p.master, angle: p.angle, h,
             live: true, roundtable: p.roundtable };
  }
  const c = state.character;
  if (c && c.mapPixel) {
    return { px: c.mapPixel[0], py: c.mapPixel[1], master: c.mapMaster,
             angle: null, h: typeof c.mapHeight === 'number' ? c.mapHeight : null,
             live: false, roundtable: false };
  }
  return null;
}

/**
 * Follow mode. Engaged, every new position re-centres the map and a cross-map
 * move switches the layer with you. It stays engaged while the position is
 * unknown - only clicking the button again, or dragging the map, releases it -
 * so turning it on before the game is running does the right thing once the
 * reader attaches.
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
  ctx.strokeStyle = target.live ? 'rgba(120,220,255,.5)' : 'rgba(255,255,255,.3)';
  ctx.lineWidth = 1.5;
  ctx.stroke();

  ctx.beginPath();
  ctx.arc(sx, sy, 5, 0, Math.PI * 2);
  ctx.fillStyle = target.live ? '#8fe3ff' : '#fff';
  ctx.fill();
  ctx.strokeStyle = '#12181c';
  ctx.lineWidth = 1.5;
  ctx.stroke();

  // Keep animating only while there is something to animate.
  const settled = Math.abs(r.px - target.px) < 0.05 && Math.abs(r.py - target.py) < 0.05;
  if (!settled || target.live) scheduleAnimation();
}

/* ---------------------------------------------------------------- picking */

// How far from the cursor a marker can be and still be picked, and how close two
// markers have to be before they count as one spot on screen (see pick()).
const PICK_RADIUS = 15;
const PICK_GROUP_PX = 6;

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

/**
 * How do I get to it?
 *
 * The one thing the game files cannot answer. They say what a thing is and
 * where it stands; the route to it is something a person has to write. So this
 * block is optional and comes from outside: it appears only if the user ran
 * tools/fetch_tips.py, and `credit` names whose writing it is.
 *
 * The text is whatever the source had, which is English - it stays English in
 * the Chinese UI rather than pretending to be translated.
 */
function routeBlock(m) {
  const tip = m.tip;
  if (!tip || !tip.text) return '';
  // Third-party data: only ever emit a plain https link out of it.
  const href = typeof tip.link === 'string' && /^https:\/\//.test(tip.link) ? tip.link : null;
  const credit = tip.credit
    ? `<span class="credit">${escapeHtml(t('label.via'))} ` +
      (href ? `<a href="${escapeHtml(href)}" target="_blank" rel="noopener noreferrer">` +
              `${escapeHtml(tip.credit)} ↗</a>` : escapeHtml(tip.credit)) +
      '</span>'
    : '';
  // `.v` is filled by fillRoute once the popup is in the DOM - the description
  // is markup written by someone else and is never assigned as innerHTML.
  return '<div class="detail route">' +
    `<span class="k">${escapeHtml(t('label.route'))}</span>` +
    `<span class="v"></span>${credit}</div>`;
}

// Half of the route descriptions carry markup: links to the source wiki, and
// some lists and emphasis. Anything outside this set is unwrapped, keeping its
// text - that quietly discards the img tags and the handful of malformed ones.
const ROUTE_TAGS = { A: 1, B: 1, STRONG: 1, I: 1, EM: 1, U: 1, BR: 1, P: 1,
                     UL: 1, OL: 1, LI: 1 };

const EDGE_PAD = 8;     // px the popup keeps clear of the stage edges

/**
 * Third-party HTML -> a DocumentFragment of nodes we built ourselves.
 *
 * The text comes off someone else's website, so it is never handed to
 * innerHTML. DOMParser gives an inert document - no scripts run, no images
 * load - and this copies out only whitelisted elements, only ever setting an
 * href, and only an https one. Everything else about a node, its attributes
 * included, is dropped rather than sanitised, so there is nothing to get wrong.
 */
function safeMarkup(html) {
  const doc = new DOMParser().parseFromString(String(html), 'text/html');
  const frag = document.createDocumentFragment();
  (function walk(src, dst) {
    for (const node of src.childNodes) {
      if (node.nodeType === Node.TEXT_NODE) {
        dst.appendChild(document.createTextNode(node.nodeValue));
        continue;
      }
      if (node.nodeType !== Node.ELEMENT_NODE || !ROUTE_TAGS[node.tagName]) {
        walk(node, dst);                       // unwrap: keep the words, drop the tag
        continue;
      }
      if (node.tagName === 'A') {
        const href = node.getAttribute('href') || '';
        if (!/^https:\/\//i.test(href)) { walk(node, dst); continue; }
        const a = document.createElement('a');
        a.href = href;
        a.target = '_blank';
        a.rel = 'noopener noreferrer';
        walk(node, a);
        dst.appendChild(a);
        continue;
      }
      const el = document.createElement(node.tagName.toLowerCase());
      walk(node, el);
      dst.appendChild(el);
    }
  })(doc.body, frag);
  return frag;
}

function fillRoute(el, m) {
  const box = el.querySelector('.route .v');
  if (box && m.tip && m.tip.text) box.appendChild(safeMarkup(m.tip.text));
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
    ${farmBlock(m)}
    ${heightBlock(m)}
    ${alsoBlock(also, m.id)}
    ${routeBlock(m)}
    ${auto ? '' : `<button class="toggle">${found ? t('popup.unmark') : t('popup.mark')}</button>`}
  `;
  fillRoute(el, m);
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
 * any marker, so tools/extract_icons.py lists it in EXTRA_ITEM_ICONS to make
 * sure web/icons/items/14800.png exists; without that file this falls back to
 * the colour dot rather than breaking.
 */
// Legend icons for rows whose marker icons cannot be inferred, plus four pinned by
// the user - the character-drop rows and boss drops:
//   角色武器 -> 暗月大剑 (Dark Moon Greatsword)    iconId 10089
//   角色防具 -> 雪魔女尖帽 (Snow Witch Hat)        iconId 14740
//   角色护符 -> 观星少女的传说 (Stargazer Heirloom) iconId 18090
//   Boss 掉落 -> 追忆 (Remembrance)               iconId 163
// The sprites are extracted from the user's own game (tools/extract_icons.py names
// the same four ids so they are extracted even though no marker carries them).
const CAT_ICON = { armour: 14800, drop_weapons: 10089, drop_armour: 14740,
                   drop_talismans: 18090, boss_drops: 163,
                   // Each glovewort level shows its own item icon (10900+n -> 2100+n).
  glovewort_grave_1: 2100, glovewort_ghost_1: 2110,
  glovewort_grave_2: 2101, glovewort_ghost_2: 2111,
  glovewort_grave_3: 2102, glovewort_ghost_3: 2112,
  glovewort_grave_4: 2103, glovewort_ghost_4: 2113,
  glovewort_grave_5: 2104, glovewort_ghost_5: 2114,
  glovewort_grave_6: 2105, glovewort_ghost_6: 2115,
  glovewort_grave_7: 2106, glovewort_ghost_7: 2116,
  glovewort_grave_8: 2107, glovewort_ghost_8: 2117,
  glovewort_grave_9: 2108, glovewort_ghost_9: 2118,
                   glovewort_grave_great: 2109, glovewort_ghost_great: 2119 };

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
 * The save picker: one dropdown for the save extension (vanilla .sl2, Reforged
 * .err, whatever else is installed) and one for the character, listing every
 * slot of every save of that type by name and level. A file holding two
 * characters gets two entries, so either can be picked; the Steam account id
 * only appears when there is more than one profile to tell apart.
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

// Categories that are not part of the completion percentage. Gathering nodes are
// picked again after every rest, so counting them as collectibles would make the
// progress bar a lie: it would never reach 100% and it would drop when you farm.
const NO_PROGRESS = new Set(['gathering']);

function refreshCounts() {
  const farmOnly = new Set();
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
  let total = 0, found = 0;
  for (const m of state.markers) {
    const hit = isFound(m) ? 1 : 0;
    const cat = byCat.get(`${m.master}|${m.cat}`) || [0, 0];
    cat[0]++; cat[1] += hit; byCat.set(`${m.master}|${m.cat}`, cat);
    const lay = byLayer.get(m.master) || [0, 0];
    lay[0]++; lay[1] += hit; byLayer.set(m.master, lay);
    // A marker that is a farm spot rather than a pickup is not collectible either:
    // the enemy respawns, so there is nothing to tick off. And a ladder rung whose
    // only markers are farm spots counts as no-progress by itself, which is how the
    // seven levels with no placed pickup behave.
    if (NO_PROGRESS.has(m.cat) || m.farm) { farmOnly.add(m.cat); continue; }
    total++; found += hit;
  }
  for (const key of Object.keys(CATS)) {
    const [all, f] = byCat.get(`${state.master}|${key}`) || [0, 0];
    const row = document.querySelector(`.cat[data-cat="${key}"]`);
    if (!row) continue;
    // A row that is not tracked shows how many there are instead of found/total -
     // "0/603" would read as a progress bar that is broken.
    const noProgress = NO_PROGRESS.has(key) || (farmOnly.has(key) && !f);
    row.querySelector('.count').textContent = noProgress
      ? t('label.places').replace('{}', all) : `${f}/${all}`;
    row.querySelector('.minibar i').style.width = all ? (f / all * 100) + '%' : '0%';
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
  // Real-time position, only present when the server runs with --live-memory.
  es.addEventListener('pos', (ev) => {
    try {
      const p = JSON.parse(ev.data);
      state.livePos = p;
      recentreOnPlayer();
      renderWhere(state.character);      // the height moves with you
      // The server matches the running character to a save slot by position.
      // Swap the displayed progress over when that answer changes.
      const active = state.characters.find((character) => character.slot === p.slot);
      if (active && active !== state.character) {
        state.character = active;
        state.found = new Set(active.found || []);
        renderCharacter(active);
        refreshCounts();
        syncSavePicker();
      }
      if (map) map.requestDraw();
    } catch { /* ignore a malformed frame */ }
  });
  es.addEventListener('live', (ev) => {
    try {
      const st = JSON.parse(ev.data);
      state.liveStatus = st.status;
      if (st.status !== 'live') state.livePos = null;
      if (state.character) renderCharacter(state.character);
    } catch { /* ignore */ }
  });
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
  // Every snapshot carries the live reader's state. Without this the badge
  // stayed blank on a fresh page load until the status happened to change.
  if (s.live) state.liveStatus = s.live.status;
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

/** One line describing the optional live-memory feed, or nothing when it is off. */
function liveBadge() {
  const st = state.liveStatus;
  // Three distinct states, not two. "Not in live mode" is not "offline": the
  // server is still following the save file, and saying otherwise made players
  // think nothing was being read at all. The badge now names the data source.
  if (!st || st === 'off') return `<br><span style="color:#8fb87a">&#9679; ${escapeHtml(t('live.bySave'))}</span>`;
  const map = {
    live:    ['#8fe3ff', 'live.realtime'],
    waiting: ['#9a917c', 'live.waiting'],
    starting:['#9a917c', 'live.waiting'],
    error:   ['#e0a35a', 'live.denied'],
    stopped: ['#e0a35a', 'live.bySave'],
  };
  const [color, key] = map[st] || ['#9a917c', 'live.waiting'];
  return `<br><span style="color:${color}">&#9679; ${escapeHtml(t(key))}</span>`;
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

function escapeHtml(s) {
  return String(s).replace(/[&<>"']/g, (c) =>
    ({ '&': '&amp;', '<': '&lt;', '>': '&gt;', '"': '&quot;', "'": '&#39;' }[c]));
}

boot();
