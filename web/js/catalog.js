/**
 * Categories and how they look.
 *
 * Every row the sidebar can show, in display order, with the colour and radius a marker of that
 * category falls back to, plus the few visual constants the renderer needs. Data-driven categories
 * (one per gatherable material, one per smithing-stone level) are generated here rather than listed,
 * and data/layers.json says which of them count towards progress.
 *
 * No DOM, no state: this module is a table.
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
export const GLOVEWORT_LADDER = [
  { family: 'grave', max: 9, color: '#c9b5d8' },   // 墓地铃兰【1】-【9】
  { family: 'ghost', max: 9, color: '#a890c9' },   // 灵依墓地铃兰【1】-【9】
];
export const GLOVEWORT_CATS = GLOVEWORT_LADDER.flatMap((l) =>
  Array.from({ length: l.max }, (_, i) => `glovewort_${l.family}_${i + 1}`));

// Rune ladders: the family, how many levels the game actually has, and how its
// rows look. Declared once and used by both CATS and the legend group, so a row
// cannot exist in one and not the other. mfg_categories.py holds the matching
// ladders on the classifier side; the level itself comes from the game's own
// item name ("Golden Rune [7]"), so no level is invented here.
// `split` is the level that starts the "high" look (0 = the family has no low/high
// distinction, which is what the old two-bucket scheme wrongly imposed on it).
export const RUNE_LADDER = [
  { family: 'golden', max: 13, split: 9, low: '#d8c040', high: '#e8d04a' },
  { family: 'hero',   max: 5,  split: 0, low: '#f0c860', high: '#f0c860',
    lowIcon: 'rune_high.png', highIcon: 'rune_high.png' },
  // The DLC family keeps its own sprite so it does not read as a base-game rune.
  { family: 'shadow', max: 7,  split: 0, low: '#c8b8e8', high: '#c8b8e8',
    lowIcon: 'rune_piece.png', highIcon: 'rune_piece.png' },
];
export const RUNE_CATS = RUNE_LADDER.flatMap((l) =>
  Array.from({ length: l.max }, (_, i) => `${l.family}_rune_${i + 1}`));

export const CATS = {
  grace:     { color: '#ffd766', r: 6 },
  boss:      { color: '#e05a5a', r: 6 },
  poi:       { color: '#6fb7e8', r: 5 },
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
  // Runes, split by level the way the smithing stones are. The earlier scheme was
  // two rows (a low and a high bucket) built from two id sets, which cut three
  // different ladders at three different points: Golden Rune at [8]/[9] but Shadow
  // Realm Rune at [2]/[3], and Hero's Rune [1] was filed beside Golden Rune [13].
  ...Object.fromEntries(RUNE_LADDER.flatMap((l) =>
    Array.from({ length: l.max }, (_, i) => {
      const n = i + 1;
      const low = l.split === 0 || n < l.split;
      return [`${l.family}_rune_${n}`,
              { color: low ? l.low : l.high, r: low ? 3 : 4 }];
    }))),
  special_runes:         { color: '#ffe08a', r: 4 },
  broken_rune:           { color: '#a8a08a', r: 3 },
  mp_fingers:            { color: '#c9a8a8', r: 3 },
  prattling_pates:       { color: '#e0c8a0', r: 3 },
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
export const CAT_GROUPS = [
  { id: 'basic',   label: 'group.basic',
    cats: ['grace', 'boss', 'poi', 'fragment', 'landmark',
           'merchants'] },
  { id: 'gear',    label: 'group.gear',
    cats: ['armaments', 'armour', 'talismans', 'ashes_of_war', 'spirits'] },
  { id: 'upgrade', label: 'group.upgrade',
    cats: ['smithing_stone_1', 'smithing_stone_2', 'smithing_stone_3',
           'smithing_stone_4', 'smithing_stone_5', 'smithing_stone_6',
           'smithing_stone_7', 'smithing_stone_8',
           'smithing_stone_legend',
           'somber_stone_1', 'somber_stone_2', 'somber_stone_3',
           'somber_stone_4', 'somber_stone_5', 'somber_stone_6',
           'somber_stone_7', 'somber_stone_8', 'somber_stone_9',
           'somber_stone_legend',
           ...GLOVEWORT_CATS,
           'glovewort_grave_great', 'glovewort_ghost_great', 'whetblades'] },
  { id: 'blessing', label: 'group.blessing',
    cats: ['golden_seeds', 'sacred_tears', 'spirit_blessing',
           'scadutree_fragments', 'crystal_tears', 'celestial_dew',
           'larval_tears', 'great_runes', 'memory_stones', 'imbued_sword_keys'] },
  { id: 'consum',  label: 'group.consum',
    cats: ['consumables', 'greases', 'utilities', 'stat_boosts', 'throwables',
           'pots_n_perfumes', 'gathering', 'cookbooks', 'reusables'] },
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
           'lost_ashes', 'mp_fingers', 'prattling_pates',
           'dragon_hearts', 'ammo'] },
];

// Anything not named above (misc) renders without a header, at the end.
export const GROUPED_CATS = new Set(CAT_GROUPS.flatMap((g) => g.cats));
export const UNGROUPED_CATS = Object.keys(CATS).filter((k) => !GROUPED_CATS.has(k));

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
//     never have a marker here (the Shadow-realm stones, Great
//     Runes, gestures, dragon hearts...).
//
// The dropping half has to stay honest in the other direction: a marker whose
// category is missing from CATS is unreachable, because visibleMarkers() keys
// off state.enabled and state.enabled is only ever filled from CATS. So the rule
// is "drop what nothing uses", never "drop what looks empty on this map layer" -
// otherwise updating the code without re-running extract_items.py would quietly
// take 454 smithing-stone markers off the map, which is exactly what an earlier
// version of this file did.
export const EXTRA_CATS = {
  // Limited-use tools that the umbrella category used to hide: the player asked for the
  // actual item names, so each family gets its own row.
  pots_cracked:       { color: '#b8a179', r: 4, group: 'loot' },
  pots_great_cracked: { color: '#c9b489', r: 4, group: 'loot' },
  perfume_bottle:     { color: '#a9a2c9', r: 4, group: 'loot' },
  shop_stock:         { color: '#9fb3a0', r: 3, group: 'loot' },

    };
// High-volume categories that bury the map when they are all on at once. They
// start hidden and can be switched on from the sidebar.
export const OFF_BY_DEFAULT = new Set(['misc', 'consumables', 'gathering', 'ammo']);
export const FOUND_COLOR = '#6fcf7a';
export const CLUSTER_CELL_PX = 46;     // roughly how big a cluster cell looks on screen
// Quantised zoom steps per doubling. Coarser steps mean the cell drifts further
// from CLUSTER_CELL_PX before it snaps back - at 2 it reached 65px and visibly
// over-merged; 4 holds it to 46-55px.
export const CLUSTER_STEPS = 4;

/**
 * The player dot animates (pulse ring, eased motion), which means the canvas
 * has to keep redrawing. Doing that every animation frame would spin the GPU at
 * display rate for the whole session - wasteful in general, and actively rude
 * when this is running alongside the game it is tracking. ~18 fps is smooth
 * enough for a marker and costs a fraction of that. Nothing is scheduled at all
 * while the tab is in the background.
 */
export const ANIM_INTERVAL_MS = 55;

// How far from the cursor a marker can be and still be picked, and how close two
// markers have to be before they count as one spot on screen (see pick()).
export const PICK_RADIUS = 15;
export const PICK_GROUP_PX = 6;

export const EDGE_PAD = 8;     // px the popup keeps clear of the stage edges

// Legend icons for rows whose marker icons cannot be inferred, plus four pinned by
// the user - the character-drop rows and boss drops:
//   角色武器 -> 暗月大剑 (Dark Moon Greatsword)    iconId 10089
//   角色防具 -> 雪魔女尖帽 (Snow Witch Hat)        iconId 14740
//   角色护符 -> 观星少女的传说 (Stargazer Heirloom) iconId 18090
//   Boss 掉落 -> 追忆 (Remembrance)               iconId 163
// The sprites are extracted from the user's own game (tools/extract_icons.py names
// the same four ids so they are extracted even though no marker carries them).
export const CAT_ICON = { armour: 14800, drop_weapons: 10089, drop_armour: 14740,
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
