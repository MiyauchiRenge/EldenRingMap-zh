# EldenRingMap (Chinese edition)

An interactive **local** web map for ELDEN RING. Tiles, item icons and every marker are generated
on your own machine from your own game files; the repository contains code and documentation only.

[中文](README.md) · [Detailed notes (Chinese)](docs/汉化说明.md)

## 1. Upstream and licence

* Based on [egormagurin/EldenRingMap](https://github.com/egormagurin/EldenRingMap) (MIT). The map
  engine, game-data parsing, save sync and live position reading come from upstream; this branch
  adds Chinese localisation, extra data extraction and a few interface fixes. See [LICENSE](LICENSE).
* **The repository ships no game content**: tiles and item icons are generated from your own game
  files, `data/**` only commits [README.md](data/README.md) and everything else is git-ignored, so
  the installer builds them locally instead of redistributing them.
* No third-party guide or wiki text. An optional Fextralife scraper was removed together with its
  setup step because their terms forbid automated scraping.
* Not affiliated with FromSoftware or Bandai Namco; game assets belong to their owners.

## 2. Features

* Interactive world map: surface, underground, DLC regions, zoom and layer panel;
* Markers and categories: sites of grace, points of interest, bosses, items, gatherables,
  merchants, enemy drops; categories can be ticked off and counted;
* Item icons: every marker shows the item's own icon, extracted from the game atlas locally;
* All data generated locally from `regulation.bin`, `Data*.bhd`, MSB, EMEVD, FMG, TPF atlases and
  `ER0000.sl2`;
* Save-aware: reads collected state and the player position from a save for self-checks and for
  placing points that have no readable position;
* Two launchers: `Start Map.bat` (visible console) and `Start Map.vbs` (hidden); the server exits
  when you close the page;
* Simplified Chinese interface using the game's own Chinese names.

## 3. Changes against upstream

| Area | What changed |
| --- | --- |
| Localisation | Simplified Chinese UI; names come from the game's own Chinese tables (`FMG`) |
| Extraction | New layers for gatherables, farm spots, one-time rewards, boss drops and event grants; item-icon pipeline |
| Categories | Upgrade materials and glovewort split per level; each gatherable material is its own category |
| Interface | Colocated markers can each be clicked; markers show their own icon; progress treats pickups and respawning nodes differently |
| Install | `Setup.bat` performs every generation step; community format documents are fetched at install time |

## 4. Approach

**Gatherables**: an asset part is named `AEG{xxx}_{yyy}_{instance}`, where `AEGxxx_yyy = xxx*1000+yyy`
is the row id in `AssetEnvironmentGeometryParam`; that row's `pickUpItemLotParamId` (at `+0xB8`)
points to the lot in `ItemLotParam`, i.e. what the node gives, while the position comes from the part
itself. The layer is therefore fully enumerable: 321 of the table's 24,106 rows carry a pickup lot,
and sweeping 621,538 parts across 1,248 maps yields 19,263 gatherable nodes.

**World state in the save**: right after the event flags each slot holds `MOEG` (WorldGeomMan,
broken or picked-up assets) and `FOEG` (WorldGeomMan2, permanently picked one-time nodes). An entry
is 8 bytes: `key = instance << 15 | state` and `model = 10000000 + AEG id`, grouped per map.
Gatherables do not set event flags, so these blocks are the record of what was collected.

**Self-checks**: `tools/dev/verify_with_save.py` lists entries present in a save but missing from the
map, `world_gaps.py` filters for world-referenced lots, `gap_classify.py` separates real gaps from
entries that cannot have a position, and `place_from_save.py` places a point from the player's saved
position when nothing else can (marked as player-verified, local only).

Results: 321 / 321 collected `FOEG` nodes are found on the map, the flag-based gap count is 0, all
114 gatherable icons exist, and the coordinate check agrees to 0.2 px. Quantities: 46 Scadutree
Fragment spots (50 items) and 23 Revered Spirit Ash spots (25 items); markers carry the count.

**Known limits**: items granted directly by global scripts have no world object and therefore no
coordinates; boss-granted fragments are anchored to the boss marker; child tiles such as
`m10_01_00` must first be converted into the parent frame (implemented); per-node "one-time vs
respawning" is not split yet, so gatherables are counted as spots rather than progress.

## 5. Install

```
1. Run Setup.bat (13 steps, all generated locally)
2. Run Start Map.bat (visible console) or Start Map.vbs (hidden)
3. Open the address it prints
```

Linux: `setup-linux.sh` and `start-map.sh`. See [docs/汉化说明.md](docs/汉化说明.md) for details.

## Disclaimer

* This is a **personal hobby project**. It is not affiliated with FromSoftware, Bandai Namco or the
  upstream project's authors, and does not represent them;
* It is updated **as time allows**, with no promised schedule or support timeline;
* **The derived data may not be perfectly accurate**: map contents are generated by scripts from the
  game files and a save, so items can be missing, positions slightly off, or names and categories
  imperfect. In-game content is authoritative;
* Bug reports are welcome, but fixes are not guaranteed;
* You use this tool at your own risk; do not use it for online cheating or in ways that violate the
  game's terms of service.

## 6. Changelog

Corrections and additions; the rest of this document is the stable description.

* **Merchants**: 20 markers (`c3200` has 29 parts; 8 point at a placeholder NPC row whose map has no
  Nomad Mule). Names take the nearest site of grace on the same master (within 300 px), else the
  nearest non-boss landmark, with manual overrides taking priority.
* **Child-tile coordinates**: only maps that `place()` cannot project (such as `m10_01_00`) are
  shifted into the parent frame; maps that project normally are not shifted, correcting one merchant
  marker that had moved 256 px onto terrain of the wrong height.
* **Merchant bell bearings**: the bearing sits at its owner's coordinates (0 px) and the merchant
  marker carries `dropsBell`.
* **Shop stock**: `ShopLineupParam` gives price, quantity and stock flag, but neither it nor
  `NpcParam` has a shop-to-merchant field, so those rows are registered without coordinates.
* **Gatherables**: ids include the part offset, removing duplicate markers caused by equal part names.
* **Duplicate detection is per layer**: pickup layers use one lot per point, so the same lot at the
  same position is merged; gatherables use one lot per item per map, where a shared lot is normal.
* **Categories**: Cracked Pot, Great Cracked Pot, Perfume Bottle, Ritual Pot and Cookbooks are
  separate rows, plus shop-limited items; a category needs an `EXTRA_CATS` entry to appear.
* **Interface hint**: "nearby unnamed landmark" only considers grace / poi / region / landmark /
  fragment within 150 px.
* **Labels**: English and Chinese labels belong to the `en` and `zh` blocks of `i18n.js`.
