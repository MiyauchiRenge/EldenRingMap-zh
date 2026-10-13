# Lands Between Map

[中文](README.md) · [Game-data mechanisms](docs/机制.md) (Chinese) · [Implementation](docs/实现.md) (Chinese)

A Chinese-first interactive map for Elden Ring, maintained by **MiyauchiRenge**. Every marker,
category and progress figure is generated from the local game files and save: the program only reads
them, and modifies neither the game nor its saves. The engine's origin and licence are stated in
section 5, "Origin, licence and disclaimer", at the end of this document.

---

## 1. Features

* **Interactive world map** covering the surface, the underground and the Shadow Realm, with zoom, pan
  and map-layer switching;
* **Markers and categories**: graces, landmarks, bosses, map fragments, items, gatherable nodes,
  farmable drops, merchants, character drops, boss rewards, event-granted items, shop shelves and quest
  rewards. Each category has one row, can be toggled, and carries a progress count; row icons use the
  item's own sprite;
* **Progress accounting**: one-time pickups are distinguished from repeatable ones. Respawning
  gatherable nodes are displayed as locations and excluded from completion, while one-time nodes are
  counted. The rule is supplied as data (see section 3 of [docs/实现.md](docs/实现.md));
* **Multiple markers on one spot**: each entry can be selected individually from the card's "also here"
  list, and bosses are excluded from cluster bubbles;
* **Regions and nearest place names** for both markers and the player marker;
* **Save sync**: picked-up state and each character's last saved position are read from the save
  (read-only) and used for tick marks, progress and the player marker;
* **Two launchers**: `Start Map.bat` (visible console) and `Start Map.vbs` (hidden window). The server
  exits on its own once the page is closed;
* Simplified-Chinese interface with names taken from the game's own Chinese text.

## 2. Changes against upstream

| Area | Change |
| --- | --- |
| Localisation | Chinese interface; item, region and grace names come from the game's FMG tables, with no hand-written translation |
| Extraction | Gatherable nodes (one-time and respawning), farm spots, character drops, boss rewards, event-granted items, follow-up items, shop shelves, quest rewards; item-icon pipeline |
| Categories | Smithing stones and gloveworts split by kind and level, runes likewise; one gatherable category per material |
| Interface | Same-spot list, item sprites in the legend, region and nearest place names, progress that separates one-time from repeatable |
| Installation | `Setup.bat` performs every generation step (17 steps); community format documents are fetched once during setup |
| Scope | No mod support, Windows only, no reading of the running game's memory |

The measured per-file difference (upstream `48f42e57` has 143 files, this repository 67: 17 identical,
19 changed, 31 added, 107 upstream-only) is in section 8 of [docs/实现.md](docs/实现.md).

## 3. Implementation notes

* **Gatherable nodes**: an asset part is named `AEG{xxx}_{yyy}_{instance}`, where
  `AEGxxx_yyy = xxx*1000+yyy` is a row of `AssetEnvironmentGeometryParam`. In that row, `+0xB8` points at
  the `ItemLotParam` lot and `+0x3C` is the lifetime byte (`0x60` one-time, `0x40` respawning). Scanning
  621,538 parts across 1,248 maps yields 19,263 nodes, 1,661 of them one-time; each was verified against
  the save's `FOEG` block, which lists permanently picked nodes only.
* **Save world state**: after the event flags, a save slot holds two blocks: `MOEG` (broken or picked
  assets) and `FOEG` (permanently picked one-time nodes). Entries are 8 bytes:
  `key = instance << 15 | state`, `model = 10000000 + AEG id`, grouped per map.
* **Quest and event rewards**: 446 lots whose flag is set in the save but which no world object references. Each
  was classified from evidence (event instruction, event record, shop shelf, map digits in the lot id,
  starting block, or none): 23 have coordinates and 423 carry a verdict and a stated reason.
* **Verification results**: all 321/321 `FOEG` nodes are present on the map, no missing marker against
  the save's flags, 114/114 gatherable icons present, coordinates agree within 0.2 px. Scadutree
  Fragments: 46 locations / 50 items; Revered Spirit Ashes: 23 locations / 25 items (some locations
  grant two).

Field offsets, decision rules and the supporting numbers are in [docs/机制.md](docs/机制.md) (Chinese).
Known limitations are listed in section 5, "Origin, licence and disclaimer", at the end.

## 4. Installation

```
1. Run Setup.bat        (all data is generated locally, 17 steps)
2. Run Start Map.bat    (visible console) or Start Map.vbs (hidden window)
3. Open the address printed by the launcher
```

Windows only. Node.js 18+ and Python 3 are required (Python only during setup). The service listens on
localhost by default; `--lan` exposes it to the local network. Detailed steps and troubleshooting are in
section 6 of [docs/实现.md](docs/实现.md) (Chinese).

## 5. Origin, licence and disclaimer

**Origin and licence**

* **Engine origin**: the map engine, game-data parsing and save sync started from
  [egormagurin/EldenRingMap](https://github.com/egormagurin/EldenRingMap). This repository has since
  been maintained on its own and no longer tracks upstream; the measured file-by-file difference (67
  files here against upstream's 143: 17 identical, 19 changed, 31 added, 107 upstream-only) is in
  section 8 of [docs/实现.md](docs/实现.md).
* **Licence**: upstream ships no licence, so its code remains all rights reserved. This repository's MIT
  grant covers only its own additions and modifications and not the upstream code; see [LICENSE](LICENSE)
  and section 9 of [docs/实现.md](docs/实现.md).

**Disclaimer**

* This is a personal hobby project. It is not affiliated with FromSoftware, Bandai Namco or the upstream
  project's authors, and does not represent them.
* Maintenance is irregular; no schedule or response time is promised.
* The program only reads local game files and saves. It does not modify the game or its saves, does not
  go online and does not inject into any process.
* The repository contains no game assets and no third-party guide text: map tiles and icons are generated
  from the local game files, and `data/**` commits only [README.md](data/README.md) while everything else
  is excluded by `.gitignore`.
* Names and classifications may contain individual errors. Issue reports should include evidence (an
  in-game screenshot or a data source).

## 6. Changelog

The rest of this document is the stable description. Entries are grouped by theme, newest first within a
group.

### Terminology

* **"family / tier" replaced by "kind / level"**: the game names these items as kind plus level
  (`黄金卢恩【１】`, `英雄卢恩【５】`, `墓地铃兰【１】`, `灵依墓地铃兰【９】`), so the descriptions of how
  smithing stones, gloveworts and runes are split now say "by kind and level" throughout.
* **"据点" (stronghold) replaced by "地标" (landmark)**: the 294 markers in that category are cities and
  places - Stormveil Castle, Leyndell, the Academy of Raya Lucaria, Volcano Manor, the Stranded Graveyard,
  the Hero's Grave at the border, Minor Erdtrees, the Artist's Shack - which "stronghold" cannot cover.
  The UI label `cat.poi` changed from "据点与地标" to "地标", and its English label from
  "Points of interest" to "Landmarks" (the English prose already used landmarks).
* **"quest rewards" replaced by "quest and event rewards"**: that data layer collects lots whose flag is
  set while no world object references them, and the per-entry verdicts include 69 shop sales and 7 items
  held from the start, so naming it after quests alone was inaccurate. The data-layer and file ids
  (`quest-rewards.json`, `quest-rewards-unplaced.json`) are unchanged.
* **"layer" disambiguated**: [docs/实现.md](docs/实现.md) now states the convention - a generated file in
  the registry is a **data layer**, while the surface, underground and Shadow Realm are **map layers** -
  and the mixed uses in this README and both documents were corrected accordingly (the UI's "layers" panel
  means map layers, `/api/layer/<id>` means data layers).

### Renaming

* **Renamed to "Lands Between Map" (交界地地图)**: this branch no longer tracks upstream (of upstream's
  143 files, 107 are absent here, 19 are modified and only 17 are byte-identical), so keeping the upstream
  name invited the reading that it is a localisation patch. Changed: the Chinese and English README
  titles and intro paragraphs, `package.json`'s `name` and `description`, the page title and the sidebar
  title (new i18n key `app.title`, switching with the language), the server banner, and the window titles
  of `Setup.bat`, `Start Map.bat` and `Start Map.vbs`. The GitHub repository was renamed to
  `LandsBetweenMap` (the old address redirects), and `package.json`'s `repository.url` and the local
  directory names follow it. The README's former "Upstream and licence" section moved to the end and was
  merged with the disclaimer into section 5, "Origin, licence and disclaimer"; the remaining sections were
  renumbered accordingly. The upstream attribution and the download address used for the `data/` format
  documents are unchanged. `package.json` version 1.4.0 -> **2.0.0**, marking the first independent
  release of this branch.

### Scope

* **Mod support removed**: this branch reads the unmodified game only. Removed `tools/erlib/modfiles.py`
  (the loose-file-first lookup layer), `tools/extract_pieces.py` (the Reforged rune and ember piece data layer)
  and its data, the `--mod-dir` and `ER_MOD_DIR` plumbing, the MODDIR and piece steps in `Setup.bat`, the
  branch in `server/index.js` that preferred the modded save `ER0000.err`, and the ERR-only classifier
  entries (fortunes, sealed curios, added items) together with the ERR spirit-ash id range. Classification
  now uses the vanilla profile: spirit ashes are identified by id list, and Rune Arc and Furlcalling
  Finger Remedy by name. Measured: all 496 item ids keep the category they had before the change.
* **Windows only, live-memory mode removed**: removed Linux support (`setup-linux.sh`, `start-map.sh`,
  the `ER_LINOODLE` branch in `erlib/oodle.py`) and the live-memory mode (`tools/live_memory.py`,
  `erlib/memory.py`, `erlib/memory_linux.py`, `server/lib/liveMemory.js`, `Check Live Mode.bat`, the
  `--live-memory`, `--python` and `--hz` options, the server's `liveHeight` and `matchActiveSlot`, and the
  client's live state and labels). `Start Map.bat` therefore no longer needs administrator rights or a
  Python probe and provides a single launch path; the player marker now uses the last saved position and
  refreshes when the save changes.
* **Dangling third-party route-text pipeline removed**: the Fextralife fetcher had already been removed,
  but its remains were still present: the fetch prompt in `Setup.bat`, the `tips.json` injection in
  `server/index.js`, the client's route block and its HTML allow-list, and the route and via labels in
  i18n. All of it is gone, which also removes the bug where `TIPS=yes` skipped two data layers.

### Data and decisions

* **Four extractors read only the Chinese message table, so their English names were Chinese**: 
  `extract_gather_nodes.py`, `extract_followup_lots.py`, `extract_emevd_drops.py` and
  `extract_emevd_rewards.py` read `/msg/zhocn/` and then wrote the Chinese string into both `names.en`
  and `names.zh`, which made **22,905 markers** (19,263 gatherable nodes, 3,369 follow-up items, 272
  event drops, 1 event reward) show Chinese in the English interface. Added `tools/erlib/msg.py`, which
  reads `engus` and `zhocn` together and falls back per locale, and switched all four to it. Measured:
  markers whose English name held Chinese **22,905 -> 0**, and a per-marker comparison confirms the id,
  category, coordinates, flag, `num` and Chinese name are **unchanged** (only `names.en` differs):
  `托莉娜睡莲` -> `Trina's Lily`.
* **A "Registered (no coordinates)" list**: the 423 rows of `data/quest-rewards-unplaced.json` and the
  two shop shelves in `data/shop-stock.json` whose owner no script declares (Cracked Pot ×2) were filtered
  out by `px != null` when the client loaded, so they were invisible - which is also why the merchant bell
  bearings look incomplete: **21 of them have no coordinates** (Smithing-Stone Miner's [1] and [4],
  Glovewort Picker's [1] and [2], Somber Smithing-Stone Miner's [1] and [2], among others) and exist only
  in that registry. The sidebar now lists all **425 entries** (name plus the verdict the extractor
  recorded: sold by a merchant / no reference in the data / held from the start, falling back to the
  category when there is no verdict), with the count in the title and a re-render on every language
  switch. They have no world object and no coordinates, so they are neither drawn nor navigable; a list is
  the only honest form for them.
* **Rows for lazy-layer categories (the gatherable categories had none at all)**: `restrictCatsToData()`
  created rows only for `EXTRA_CATS` (6 entries), while the 79 per-material `gather_*` categories exist
  only in the layer policy, so they had no CATS row; `state.enabled` is built from `Object.keys(CATS)`
  alone and `visibleMarkers()` keys off `state.enabled`, so **18,837 markers of the gather-nodes layer
  could not be shown at all** (one category, `gather_20720`, holds 3,395 of them) and the sidebar had no
  rows for them - contradicting "one gatherable category per material" in section 2. Now the categories
  of layers the registry marks `lazy` get their row at boot (`LAZY_CATS`, sent with `data/layers.json`),
  reusing the `gathering` colour and radius in the same group, and they start **switched off** (matching
  `gathering`, so the map does not open with nineteen thousand extra dots). `catLabel()` gained a
  fallback chain (hand-written label, then the bare item key in i18n, then a marker's own game name),
  which is where the Chinese material names come from. Measured: CATS rows 122 -> **201**, markers with
  no row **18,837 -> 0**, and the labels resolve to 遗迹石 / 罗亚果实 in Chinese and "Ruin Fragment" /
  "Rowa Fruit" in English. `unplaced` (the 423 registered rewards without coordinates) deliberately gets
  no row - its markers have no position, so an empty row would only mislead; the list section below is
  where they belong.

* **Per-entry verdicts for the 446 quest and event rewards**: `tools/extract_quest_rewards.py` is now
  evidence-driven instead of deriving a map from the lot number. Result: 71 sold on a merchant shelf,
  20 whose lot id carries a map, 1 event-script record, 7 held from the start (flag block 60000-60999)
  and 347 with no reference anywhere in the game data. 23 of them have coordinates (the owning merchant,
  or the boss or grace of the corresponding map); the other 423 record their verdict, flag block and
  reason in `data/quest-rewards-unplaced.json`. Evidence and checks: the EMEVD record shape
  `(type, entity, entityFlag, lot)` holds for 199/199 lots independently known to be event-granted; the
  `ItemLotParam_map` numbering `<lead><area:2><grid:2><seq:4>` matches 1,669 of the 6,958 lots already
  placed by other layers (the previous `// 10_000_000` reading matched 18, which is why the earlier
  version could place none of them); small lots are excluded from numeric searches (lot 2000 matches
  9,929 constants in the event files); and a shop counts only when the row's `equipType` agrees with the
  item's kind (without that check 88 entries were misclassified, reduced to 71).
* **Layer contract and registry**: `tools/erlib/layers.py` declares every layer in one table: file name,
  producing tool and arguments, whether it is required, its progress accounting (`counts` / `spots`) and
  how it is delivered (`initial` / `lazy`). Every extractor writes through `write_layer()` /
  `write_raw()` (16 call sites), giving one `{"locales","markers"}` structure, sorted keys, LF line
  endings, compact separators and a temp-file-plus-replace write. Measured: two consecutive runs of the
  same tool are byte-identical; total data-layer size fell from 9.53 MB to 8.54 MB (-10%).
* **`Setup.bat` can no longer skip a data layer**: the registry self-check
  (`python tools/erlib/layers.py check`) found four data layers missing from the install script (EMEVD rewards,
  quest and event rewards, shop shelves, quantity annotation). They were added, the check now runs at the end of
  setup, and the hardcoded step numbers were removed so new data layers need no renumbering.
* **Progress accounting is supplied as data**: `data/layers.json` states which data layer each category
  belongs to and how it is counted. The client prefers it and falls back to the `gather_*` prefix rule
  when the file is absent. Measured: the two rules agree on all 202 categories, including 35 categories
  that appear in both a location layer and a counting layer (`smithing_stone_*`, `glovewort_*`,
  `somber_stone_*`), which are counted as progress, matching the client's previous logic.
* **Shop shelf attribution**: a shelf is a run of `ShopLineupParam` rows declared by a talk script, either
  `bank 1 cmd 22 (first,last)` or `bank 6 cmd 2147483610 (flagA,first,last,flagB)`, where the latter's
  flags are built from the map number (`m60_43_53` -> `1043530701` / `1043532700`). Result: 6 of 8 shelves
  belong to a named merchant (five to the nomad and hermit merchants whose own scripts declare the range,
  one to Thiollier in the Shadow Realm); the remaining 2 are declared by no script and are recorded as
  unowned. Merchant count is 20 merchants and 21 markers: merchant `32001520` is placed twice in the base
  game (Scenic Isle and Liurnia Lake Shore, each with its own mule), matching the 20 shelf ranges.
* **Bell-bearing post-processing added to the install flow**: `tools/dev/fix_bell_positions.py` (moves the
  19 merchant bell bearings onto their owner's coordinates, `via: bell-owner`) and `link_bell_bearings.py`
  (adds `dropsBell` and `dropsBellPx` to 20 merchant markers) had never been applied to the published
  data, although the changelog already recorded that field. They now run for real and are steps 16 and 17
  of `Setup.bat`, declared in the registry so the self-check still reports zero undeclared calls.
  Measured: only `npcs.json` and `drops.json` changed, the other 19 data files are byte-identical, the
  data layer still holds 21 markers with all 21 names unchanged, and two consecutive runs produce the same
  result. `tools/dev/rename_merchants.py` was deleted: it is a stale duplicate of the merchant naming
  (older "kind·place" style plus a suppression file only it read), while the actual naming is done by
  `extract_items.py` as "kind (nearest grace)".
* **Curated boss-drop table**: the `data/boss-drop-overrides.json` mechanism (not committed) is retained;
  entries only supply the owning boss, the marker lands on that boss and carries `via: curated`.
  Currently no such file exists locally, so all 152 rows of `boss-drops.json` come from the script
  (`via` is only `name` or `script`).
* **Gatherable lifetime byte**: `+0x3C` of `AssetEnvironmentGeometryParam` is the lifetime byte (`0x60`
  does not respawn, `0x40` returns after resting, `0x00` has no world node). Verified against the save's
  `FOEG` block: all 44 rows it lists are `0x60` with no counter-example, and a second save (1,669 flags)
  agrees. Gatherable nodes are therefore split into 1,661 one-time and 17,602 respawning, and only the
  one-time ones count towards completion.
* **Same-spot list and boss cluster exemption**: `pick()` collects a group by screen distance (6 px
  threshold) and the card gained an "also here" list whose entries are individually selectable in a fixed
  order with the current one boxed; `cluster()` keeps bosses outside the bubbles. Measured: grouping by
  same map layer and pixel distance <= 3, the 28,177 placed markers form 2,651 overlapping groups (8,025
  markers), 886 of which are exactly co-located.
* **Regions and nearest place names**: added `WorldMapPlaceNameParam` parsing and `data/regions.json`
  (9 regions with rectangles); markers and the player marker show "region (nearest place)". The region is
  the nearest rectangle (further than 400 master pixels does not count), and a place name containing the
  region name takes precedence.
* **Category and label corrections**: smithing stones and gloveworts are split by kind and level, runes
  likewise; labels were corrected against the game's own translations (砥石小刀 to 砥石刀,
  丢失的战灰 to 失力战灰, 多话的帕特 to 唤声泥颅, among others). The check compares all 101 category
  labels with the items they actually contain.
* **Item icons**: the icon fields of five `EquipParam*` tables are used; the last four are 2 bytes wide
  and reading them as 4 bytes shows another item's icon. Cross-checked against an external table
  (armour 50/50, weapons 133/133, ammo 69/69, talismans 73/73). The legend now uses the items' own icons,
  with four rows pinned in `CAT_ICON`.
* **Merchant count and naming**: 20 merchants and 21 markers (`c3200` has 29 parts, 8 of which point at
  a placeholder row whose map has no mule). Names take the nearest grace on the same master (within
  300 px), otherwise the nearest non-boss landmark, with manual overrides taking priority.
* **Sub-map coordinates**: only maps that `place()` cannot project (such as `m10_01_00`) are shifted into
  the parent frame; maps that project normally are no longer shifted. This corrected one merchant marker
  that was 256 px off and at the wrong terrain height.
* **Merchant bell bearings**: the bearing a merchant drops sits at that merchant's own coordinates (0 px)
  and the merchant marker carries a `dropsBell` field.

### Transport and performance

* **Response layer and compression**: `server/lib/respond.js` selects brotli or gzip from
  `Accept-Encoding` and caches the encoded copy by content ETag; responses carry an ETag and conditional
  requests get a 304; `/tiles/**` and `/icons/**` are cached for a day while everything else is
  `no-cache`. Measured: the first-paint marker document went from 8,564,838 B to 1,560,023 B
  uncompressed and 173,122 B with brotli (-98%); `js/app.js` 93,960 to 30,282 B, `js/i18n.js` 30,786 to
  8,293 B, `css/app.css` 17,659 to 4,742 B; a repeated request hits the ETag and returns 304 with 0 bytes.
* **Lazy loading of heavy data layers**: the registry gained a `client` field (`initial` / `lazy`);
  `followup` (855 KB) and `gather-nodes` (6.15 MB) are marked lazy, the server exposes them through
  `/api/layer/<id>` and the page fetches and merges them after its first paint, so a failure only means
  those markers are missing. Initial marker count fell from 28,156 to 5,970; the lazy data layers arrive as
  385,863 B and 55,417 B compressed. The initial document carries 121 categories while the policy file
  declares 202, and the sidebar and tick state are built from the policy, so gatherable categories are
  not dropped while their data is in flight.
* **Rendering cost**: measured by driving the real draw callback with the real data, a full set (28,177
  markers, 201 categories enabled) costs 5.09 ms per draw and the first paint (5,971 markers) 1.93 ms,
  so lazy loading reduces the first-paint draw cost to about 38%. The measurement uses Node and a
  simulated canvas without rasterisation and is therefore a lower bound.

### Scripts and documents

* **Client modularisation**: `web/js/app.js` (2,159 lines) was split along its dependency direction into
  `catalog.js` (categories and visual constants, 18 exports), `core.js` (state, helpers and the progress
  policy, 18) and `region.js` (regions and nearest place names, 8) behind an entry `app.js`;
  `index.html` now uses `type="module"`, while `i18n.js` and `map.js` remain classic scripts that run
  first so the module can read their globals. The split only moved declarations and kept their names, so
  no function body in app.js changed. Verification: the full module graph is loaded in Node against a DOM
  stub, `boot()` is executed, and the extracted modules are asserted behaviourally; this step found a
  missing `$` import in app.js that raised a `ReferenceError` and that the static checks had not covered.
* **Drawing code fix**: one cut during the split started inside a comment, which merged `animTimer`,
  `scheduleAnimation`, `playerTarget` and the `visibilitychange` listener into that comment (a class of
  error that `node --check` cannot detect). The draw benchmark above exposed it and it was fixed.
* **`Setup.bat` execution order fixed**: the last two steps (follow-up items of sequential lots and
  gatherable nodes) sat at the end of the file after `Done` and were never executed, so a fresh install
  lacked both data layers. They are now in execution order and the steps are numbered afresh.
* **Unused files removed**: deleted seven probe dumps at the repository root (`_gap_*.txt`,
  `_raw_lot_hits.txt`, `_save_verify.txt`, `_world_gaps.txt`) and 14 one-off investigation scripts under
  `tools/dev/` (their conclusions are recorded in [docs/机制.md](docs/机制.md), and the checks worth
  re-running remain as `gather_lifetime_check.py`, `verify_with_save.py`, `shop_register.py` and
  others). Tracked files went from 89 to 67. `.gitignore` was rewritten (removing entries for
  `extract_pieces`, `tips`, `timeline.jsonl` and the upstream category icons, and stating that nothing
  under `data/` is published), and `data/README.md` now lists all 17 data files with their producers
  instead of the removed `catalog.json`, `pieces.json` and `tips.json`.
* **Ten obsolete category declarations removed**: `material_nodes`, `golden_runes`, `golden_runes_low`,
  `one_time_drops`, `smithing_stones`, `smithing_stones_low`, `smithing_stones_rare`,
  `crafting_materials`, `gloveworts` and `great_gloveworts` have no markers in the data and are absent
  from the 202 categories in `data/layers.json` (so `restrictCatsToData()` drops them at boot as unused),
  yet their declarations remained in `web/js/catalog.js` (CATS rows, EXTRA_CATS rows and a group entry)
  and in `web/js/i18n.js` (20 label lines across both languages); `material_nodes` even duplicated the
  `gathering` label. All of them are gone, and the comments in `catalog.js` and `mfg_categories.py` that
  had become untrue were rewritten; `crafting_materials` still has an internal use (the classifier returns
  it and `extract_items.py` rewrites it to `gathering`), which is now noted in place. The generated data
  is unaffected: after re-running `extract_items.py` -> `annotate_quantities.py` -> the two bell-bearing
  post-processing steps, **all 20 data files are byte-identical**.
* **Category-declaration check added** (`_check_categories.mjs`, run with the other self-checks): it
  verifies that every category appearing in the data is declared by the client (`CATS`, `EXTRA_CATS` or
  the layer policy) and reports group entries without a row plus declarations that this data set never
  fills. Current result: **202 data categories, 0 undeclared**, 0 group entries without a row.
* **Documentation restructured**: the former `docs/汉化说明.md` was split into
  [docs/机制.md](docs/机制.md) (game-data mechanisms) and [docs/实现.md](docs/实现.md) (code structure,
  layer contract, transport, verification and release flow, and the file-by-file difference from
  upstream). This README was rewritten around the current feature set, with the changelog grouped by
  theme.
* **Disclaimer merged into the final section**: the disclaimer was the only unnumbered section, and it sat
  between section 4, "Installation", and section 5, "Origin and licence", which is structurally
  inconsistent; its "the repository ships no game content" bullet also repeated the origin section. The
  two are now one section, 5, "Origin, licence and disclaimer", with an "Origin and licence" group and a
  "Disclaimer" group, and the in-text references to it were updated.
