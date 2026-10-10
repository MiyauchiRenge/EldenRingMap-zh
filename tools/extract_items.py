"""Extract item pickup locations from the game's MSB map files.

An item pickup is spread across three files:

  * the MSB places a PART (a chest, a corpse, a glowing item) with a position,
  * an MSB EVENT of type 4 (Treasure) links that part to an ItemLotParam id,
  * ItemLotParam_map says which items the lot gives and, crucially, which event
    flag the save sets once you have picked it up.

Joining those gives a marker that ticks itself off, exactly like a Site of Grace.

    python tools/extract_items.py            -> data/items.json

All offsets below were derived by reading a real MSB and cross-checking against
the param tables, whose field layouts come from the Paramdex XML in
data/paramdefs/. tools/build_markers.py reads the same tables the same way.
"""
import argparse
import json
import os
import re
import struct
import sys
import time
from collections import Counter, defaultdict

reconfigure = getattr(sys.stdout, "reconfigure", None)
if reconfigure:
    reconfigure(encoding="utf-8")
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from erlib import msb as msblib, param, paramdef, fmg, dcx, oodle
import erlib.modfiles as modfiles
import erlib.mfg_categories as mfg_categories
from erlib.dvdbnd import DvdBnd
from erlib.gamepath import require_game_dir
from build_markers import LegacyConv, place, LOCALES


PARENT_FRAME = {}


def place2(aa, bb, cc, x, y, z, conv, tier=0):
    """place(); only tiles that place() cannot project are shifted into their parent frame.

    Some maps (m10_01_00) are the destination side of a WorldMapLegacyConvParam row and have no
    conversion of their own, so place() returns None for them and their local coordinates must be
    moved into the parent frame first. Maps that project fine (m60_37_54 and the rest of the
    overworld) must NOT be shifted: doing so moved a merchant 256 px away from where the game
    actually puts it, onto terrain whose height no longer matched.
    """
    p = place(aa, bb, cc, x, y, z, conv, tier=tier)
    if p is not None:
        return p
    if (aa, bb, cc) in PARENT_FRAME:
        sa, sx, sz, ox, oy, oz = PARENT_FRAME[(aa, bb, cc)]
        return place(sa, sx, sz, x + ox, y + oy, z + oz, conv, tier=0)
    return None


ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
DEFS = os.path.join(ROOT, "data", "paramdefs")

# --- MSB offsets, all verified empirically -----------------------------------
EVENT_TYPE_TREASURE = 4
EV_TYPE = 0x0C            # int32, event type
EV_TYPEDATA_PTR = 0x20    # int64, offset (entry-relative) of the type-data block
TD_PART_INDEX = 0x08      # int32, index into PARTS_PARAM_ST
TD_ITEM_LOT = 0x10        # int32, ItemLotParam_map row id
PART_POSITION = 0x20      # 3 x float32, local position
PART_TYPE = 0x0C          # int32, part type: 2 Enemy, 10 DummyEnemy
# int32, the NpcParam row id of the character this part spawns. Checked against the
# other way of getting there (the type-data block, whose pointer sits at +0x68 and
# whose id is at +0x0C): 2,175 of 2,188 sampled enemy parts agree, and this one also
# works for the type-10 DummyEnemy parts that the pointer path skips.
PART_NPC_PARAM_ID = 0x2AC
PART_TYPE_ENEMY = 2
PART_TYPE_DUMMY_ENEMY = 10

# Per-item icon field, one per lotItemCategory. Every offset here is empirical -
# there is no paramdef for these tables in data/paramdefs/ - and each was found the
# same way: sweep every offset of the param, read it once as a signed int32 and
# once as an unsigned int16, and keep the offset whose values are all real
# MENU_ItemIcon sprites. The sprite atlas is the ground truth (the SB_Icon* layout
# sheets name 2976 of them) and the distinct-value count is what separates a real
# field from a coincidence.
#
#   goods       +0x030 s32   1109 distinct across 2329 rows - the rune ladder
#                            proves it: Golden Rune [1]..[13] are 143..155 in order
#   weapon      +0x0BE u16 s32    558 across 3636   (NOT +0x0C8 - that is 2 bytes early
#                                               and yields only 118)
#   protector   +0x0A8 u16 s32    748 across  838
#   accessory   +0x026 u16    156 across  157   - and it reproduces all 116 rows of
#                            vawser/ER-Documentation's Icon List - Accessories.txt
#                            exactly, the 39 DLC rows included (18900..18939)
#   gem         +0x004 u16    116 of the 121 rows named "Ash of War: ...", all
#                            distinct, every value a real sprite (8300..8525)
#
# Two of the five are 2 bytes wide. The first version of this table only read
# int32, which is why it recorded "accessory: not found - no offset holds more than
# 4 legal sprite ids" and made every talisman wear Radagon's Scarseal.
ICON_OFFSETS = {
    1: ("EquipParamGoods", 0x030, 4),
    2: ("EquipParamWeapon", 0x0BE, 2),
    3: ("EquipParamProtector", 0x0A8, 2),
    4: ("EquipParamAccessory", 0x026, 2),
    5: ("EquipParamGem", 0x004, 2),
}

# What EquipParamGem +0x018 is instead - this table used to point at it. It holds
# exactly row_id // 100 (true for 113 of the 116 real Ash of War rows): an ordinal,
# not an icon. It survives a casual look because the base-game rows are dense
# enough that most of those ordinals collide with real sprite numbers, but the DLC
# block (200000..800000 -> 2000..8000) does not, which is why 7 of the 11 lootable
# ashes had no picture. There is no community list to fall back on for gems either:
# the modding docs' "Icon List - Ashes of War.txt" is an empty file, so EquipParamGem
# row ids have nothing to intersect with. The atlas is the only ground truth.

# lotItemCategory -> the FMG table holding that item's name.
#
# Determined by taking every id in each category and counting which name table
# actually contains them. Gems (Ashes of War) are category 5, NOT 6: category 5
# matched GemName 86/86, while category 6 matched no table at all. Guessing 6
# here silently produced zero Ash of War markers.
CATEGORY_TABLES = {
    1: "GoodsName",
    2: "WeaponName",
    3: "ProtectorName",
    4: "AccessoryName",
    5: "GemName",
}

# What the game calls a merchant on the map. NPC parts are named after their chr
# model ("c3200_9000", or "m60_41_32_00-c3200_9000" in the overworld grids, where
# the part name is prefixed with its own map id).
#
# c3200 is the Nomad Trader and c3210 is the Nomad Mule that stands beside him:
# both are named as such in the community chr list (vawser/ER-Documentation,
# "Info - Chr IDs.txt"), and both show up exactly once in each of the three
# merchant-shack maps in our own data - the mule is the giveaway that the pair,
# not a lone NPC, is what sits at a merchant's stall. Only the trader is marked.
#
# 29 of them exist across the base game and the DLC, which matches the merchants
# the game actually has. They carry no pickup flag, so they are ticked off by
# hand like the Reforged pieces.
MERCHANT_MODEL = "c3200"

# The NpcParam id sits at +0x2AC inside a PARTS_PARAM_ST entry. Found the way the
# icon fields were found - sweep every offset, then check the winner against
# something independent - and three checks agree:
#
#   * the merchant in m60_42_36_00 (Church of Elleh) resolves to "Merchant Kale",
#     which is the merchant who actually stands there;
#   * the three merchant-shack maps resolve to Isolated / Isolated / Hermit, and
#     their graces are named "Isolated Merchant's Shack" and "Hermit Merchant's
#     Shack";
#   * the names that come out are exactly the merchant names NpcName has:
#     Nomadic / Isolated / Hermit / Abandoned / Imprisoned / Kale.
#
# It is NOT +0x2A8: that one holds the same id (32000000, whose NpcName is
# Merchant Kale) for 21 of the 29 - a shared template, not an identity.
#
# 8 of the 29 are type-10 DummyEnemy placeholders whose id is 32009000, an
# unnamed "DLC dummy" row; the game names no merchant there, so those keep the
# generic name below.
MERCHANT_NPC_PARAM_OFF = 0x2AC

# NpcParam.nameId -> a key in the NpcName FMG. Read by field name when Paramdex's
# NpcParam.xml is present (tools/fetch_docs.py fetches it); this offset is the
# fallback, and it is what the field name resolves to - the table opens with three
# 32-bit fields, so nameId is the fourth (0x0C, not 0x08: guessing 0x08 read a
# think id and made every merchant fall back to the generic name).
NPC_PARAM_NAME_ID_OFF = 0x0C

# The fallback name, used when the game itself names no merchant there.
MERCHANT_NAME = {"en": "Merchant", "zh": "商人"}


def part_model(name):
    """-> the chr/asset model of an MSB part name ('m60_41_32_00-c3200_9000' -> c3200)."""
    return name.rsplit("-", 1)[-1].split("_")[0]


# How far either side of a boss's defeat flag the event script is searched for a
# reward lot, in 4-byte steps. See boss_rewards() for why this works at all.
#
# Measured, not guessed: tools/dev/window_probe.py re-runs the scan at several
# widths. Narrowing loses real drops - at 32 the lot behind Godrick's Ash of War:
# Storm Assault is already gone, at 8 so are the Dragon Heart and Deathroot ones -
# while widening drags in plain pickups from the same area (at 128, Golden Arrows
# and Smithing Stone [5] credited to Morgott, a Wooden Greatshield to Godrick). No
# width separates the two, so 64 stays: it keeps Godrick's ash of war, and the two
# counting filters below already drop the shared-script noise.
BOSS_WINDOW = 64


def categorise(iid, names, category):
    """-> marker category string for one lot's headline item.

    Delegates entirely to the Map-for-Goblins classifier (ported from its
    open-source repo), which already assigns every item a category; `misc` is
    its own fallback, so nothing is dropped.
    """
    return mfg_categories.categorise(iid, names, category)


def main():
    ap = argparse.ArgumentParser(description=__doc__,
                                 formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--game-dir", default=None)
    ap.add_argument("--mod-dir", default=None)
    ap.add_argument("--limit", type=int, default=0, help="only N maps (for testing)")
    args = ap.parse_args()

    game = require_game_dir(args.game_dir)
    mod = modfiles.find_mod_dir(args.mod_dir)
    status = mfg_categories.data_status()
    if status:
        print(status)
    t0 = time.time()
    dvd = DvdBnd(game, cache_dir=os.path.join(ROOT, "cache"), verbose=False)
    helper = oodle.make_helper(game)

    print("loading params ...")
    params = param.load_params(modfiles.regulation_path(game, mod))
    lot_def = paramdef.load(os.path.join(DEFS, "ItemLotParam.xml"))
    conv = LegacyConv(params["WorldMapLegacyConvParam"].rows,
                      paramdef.load(os.path.join(DEFS, "WorldMapLegacyConvParam.xml")))
    # PLACE2_HELPER: child tiles (maps that are the DESTINATION of a conversion row, e.g.
    # m10_01_00 at (-514, 28, 200) inside m10_00_00) must be shifted into the parent frame
    # before place(), which only understands the source side.
    _cvd = paramdef.load(os.path.join(DEFS, "WorldMapLegacyConvParam.xml"))
    for _r in params["WorldMapLegacyConvParam"].rows:
        _sa = _cvd.get(_r.data, "srcAreaNo")
        _da, _dx, _dz = (_cvd.get(_r.data, "dstAreaNo"), _cvd.get(_r.data, "dstGridXNo"),
                         _cvd.get(_r.data, "dstGridZNo"))
        _sx, _sz = _cvd.get(_r.data, "srcGridXNo"), _cvd.get(_r.data, "srcGridZNo")
        if _sa and (_da, _dx, _dz) != (_sa, _sx, _sz):
            PARENT_FRAME[(_da, _dx, _dz)] = (_sa, _sx, _sz, _cvd.get(_r.data, "srcPosX"),
                                             _cvd.get(_r.data, "srcPosY"), _cvd.get(_r.data, "srcPosZ"))
    print("  parent-frame tiles: %d" % len(PARENT_FRAME))
    lots = {r.id: r for r in params["ItemLotParam_map"].rows}
    enemy_lots = {r.id: r for r in params["ItemLotParam_enemy"].rows}
    print(f"  ItemLotParam_map: {len(lots):,} rows, "
          f"ItemLotParam_enemy: {len(enemy_lots):,} rows")

    def lot_items(row):
        """-> [(item id, lotItemCategory, quantity)] for a lot row, in slot order."""
        out = []
        for i in range(1, 9):
            iid = lot_def.get(row.data, f"lotItemId{i:02d}")
            if iid:
                out.append((iid, lot_def.get(row.data, f"lotItemCategory{i:02d}"),
                            lot_def.get(row.data, f"lotItemNum{i:02d}")))
        return out

    # iconId -> the item's own sprite, per lotItemCategory. Whatever a table does
    # not provide falls back to the category icon.
    icon_tables = {}
    for cat, (table, off, width) in ICON_OFFSETS.items():
        icon_tables[cat] = ({r.id: r for r in params[table].rows}, off, width)

    def item_icon_id(item_id, cat):
        spec = icon_tables.get(cat)
        if spec is None:
            return None
        rows, off, width = spec
        row = rows.get(item_id)
        if row is None or len(row.data) < off + width:
            return None
        fmt = "<H" if width == 2 else "<i"
        return struct.unpack_from(fmt, row.data, off)[0] or None

    print("loading item names ...")
    names_by_loc = {}
    for loc, folder in LOCALES.items():
        tables = {}
        for f in ["item.msgbnd.dcx", "item_dlc02.msgbnd.dcx"]:
            p = f"/msg/{folder}/{f}"
            if modfiles.has(dvd, mod, p):
                data = modfiles.read(dvd, mod, p)
                for k, v in fmg.load_msgbnd(data, oodle=helper).items():
                    tables.setdefault(k.split("_dlc")[0], {}).update(v)
        names_by_loc[loc] = tables
    en = names_by_loc["en"]
    print("  " + ", ".join(f"{t}={len(en.get(t, {}))}" for t in CATEGORY_TABLES.values()))

    # NpcParam carries the name of every placed NPC; the map parts point at a row
    # of it. Read nameId by field name when the Paramdex definition is there.
    npc_def = None
    npc_def_path = os.path.join(DEFS, "NpcParam.xml")
    if os.path.isfile(npc_def_path):
        npc_def = paramdef.load(npc_def_path)
    npc_rows = {r.id: r for r in params["NpcParam"].rows}

    # Places for the merchant qualifiers: the graces and POIs build_markers.py has
    # already named, which are the game's own place names. Landmarks are left out on
    # purpose - their names are our own derived "Landmark near X" strings, and the
    # nearest of those read as part of the merchant's name. Markers.json is written
    # before this tool in setup (step "build the marker dataset"), and if it is
    # missing the qualifier is simply omitted.
    places = []
    markers_path = os.path.join(ROOT, "data", "markers.json")
    if os.path.isfile(markers_path):
        with open(markers_path, encoding="utf-8") as f:
            for m in json.load(f).get("markers", []):
                if m.get("cat") in ("grace", "poi") and m.get("names"):
                    places.append((m.get("master"), m["px"], m["py"], m["names"]))

    def nearest_place(px, py, master):
        """-> {loc: place name} for the closest grace/POI in the same map layer.

        The layer matters: the underground (M01) shares the master image with the
        overworld (M00), so without it a Siofra trader is labelled with a place that
        is physically above him.
        """
        best, best_d = None, None
        for pmaster, ppx, ppy, pnames in places:
            if pmaster != master:
                continue
            d = (ppx - px) ** 2 + (ppy - py) ** 2
            if best_d is None or d < best_d:
                best, best_d = pnames, d
        return best or {}

    def npc_name(npc_id, loc):
        """NpcParam id -> that NPC's own name in this locale, or "" when unnamed."""
        row = npc_rows.get(npc_id) if npc_id else None
        if row is None:
            return ""
        try:
            name_id = (npc_def.get(row.data, "nameId") if npc_def is not None
                       else struct.unpack_from("<i", row.data, NPC_PARAM_NAME_ID_OFF)[0])
        except Exception:
            return ""
        table = names_by_loc.get(loc, {}).get("NpcName", {})
        v = table.get(name_id, "")
        if not v or v.startswith("%null%"):
            v = en.get("NpcName", {}).get(name_id, "")
        if v.startswith("%null%"):
            return ""
        # The FMG names its own placeholder rows "DLC dummy". That is a developer
        # note, not a merchant: a marker called "DLC dummy" would be worse than the
        # generic name, so treat those as unnamed.
        return "" if "dummy" in v.lower() else v

    def item_name(loc, item_id, category):
        tbl = CATEGORY_TABLES.get(category)
        if not tbl:
            return ""
        v = names_by_loc.get(loc, {}).get(tbl, {}).get(item_id, "")
        if not v or v.startswith("%null%"):
            v = en.get(tbl, {}).get(item_id, "")
        return "" if v.startswith("%null%") else v

    # ---- walk every map -----------------------------------------------------
    map_list = os.path.join(ROOT, "cache", "map-list.txt")
    if not os.path.exists(map_list):
        sys.exit("run tools/dev/enumerate_maps.py first (creates cache/map-list.txt)")
    map_ids = [l.split("\t")[0] for l in open(map_list, encoding="utf-8") if l.strip()]
    if args.limit:
        map_ids = map_ids[:args.limit]
    print(f"\nscanning {len(map_ids)} MSB files ...")

    placements = {}          # lotId -> (mapId, x, y, z)
    merchants = {}           # (mapId, partName) -> (mapId, x, y, z)
    drops = {}               # lotId -> the one-time reward that lot is
    stats = Counter()
    for i, map_id in enumerate(map_ids):
        path = f"/map/mapstudio/{map_id}.msb.dcx"
        if not modfiles.has(dvd, mod, path):
            continue
        try:
            data = modfiles.read(dvd, mod, path)
            m = msblib.load(dcx.decompress(data, oodle=helper))
        except Exception as exc:
            stats["msb parse failed"] += 1
            continue
        parts = m.lists.get("PARTS_PARAM_ST")
        part_offsets = parts.entry_offsets if parts else []
        aa = int(map_id[1:3])
        tier = int(map_id[10:12]) if aa in (60, 61) else 0

        # Merchants: NPC parts, not treasure events - the game never "gives" you a
        # merchant, so no lot points at them. MERCHANT_MODEL is the Nomad Trader
        # chr, identified by the two independent checks documented at the top.
        # Collected in this pass because this is the only tool that already reads
        # every map: a second full scan would double setup's slowest step.
        for poff, pname in m.entries("PARTS_PARAM_ST"):
            if part_model(pname) != MERCHANT_MODEL:
                continue
            stats["merchant parts"] += 1
            # The same NPC is placed once per LOD tile of its area, and its part
            # name is *not* unique across maps (the overworld prefixes some parts
            # with their map id and others not), so neither the name nor the count
            # can be the identity. The tier-0 map holds the real placement: take
            # only that, and key by map so two merchants never merge.
            if tier:
                stats["merchant parts in a LOD tier"] += 1
                continue
            x, y, z = m.vec3(poff + PART_POSITION)
            npc_id = m.i32(poff + PART_NPC_PARAM_ID)
            merchants[(map_id, pname)] = (map_id, x, y, z, npc_id)

        # One-time rewards: what an enemy or a talkable character hands over.
        #
        # The treasure pass below only sees what the game places in the world as a
        # pickup. These lots hang off NpcParam instead (itemLotId_map for scripted
        # rewards, itemLotId_enemy for enemy deaths), and NpcParam's row id is in the
        # part we are already reading, so this costs one more table read per part in
        # a loop that already runs.
        #
        # Only lots with a persistent getItemFlagId are taken, because that is what
        # separates a one-time reward from a farmable drop: over the whole game it
        # discards 27,427 enemy lots and leaves 133 rewards - 59 from named
        # characters (Patches' Bell Bearing, Nepheli's Stormhawk Axe, the merchants'
        # Nomadic Merchant's Bell Bearings) and 74 from enemies the game never names
        # (the Omenkiller's Cleaver and friends).
        if not tier:
            for poff, _pname in m.entries("PARTS_PARAM_ST"):
                if m.u32(poff + PART_TYPE) not in (PART_TYPE_ENEMY, PART_TYPE_DUMMY_ENEMY):
                    continue
                npc_id = m.i32(poff + PART_NPC_PARAM_ID)
                nrow = npc_rows.get(npc_id)
                if nrow is None:
                    continue
                for which, lot_id, table in (("map", npc_def.get(nrow.data, "itemLotId_map"), lots),
                                             ("enemy", npc_def.get(nrow.data, "itemLotId_enemy"),
                                              enemy_lots)):
                    lrow = table.get(lot_id)
                    if lrow is None:
                        continue
                    flag = lot_def.get(lrow.data, "getItemFlagId")
                    if not flag and which == "enemy":
                        # A flagged enemy lot need not be reachable from NpcParam at all.
                        # The DLC picker enemies hold lot X while the row that actually
                        # awards the item is X + 1 (checked: the three sibling lots behind
                        # 灵依墓地铃兰【２】/【３】 reproduce the sibling project's NPC ids and,
                        # after projection, its coordinates to 0.0 px). So look at X + 1.
                        sib = enemy_lots.get(lot_id + 1)
                        if sib is not None and lot_def.get(sib.data, "getItemFlagId"):
                            stats["sibling lot reward (lot+1)"] += 1
                            lrow, lot_id, flag = sib, lot_id + 1, lot_def.get(
                                sib.data, "getItemFlagId")
                    if not flag:
                        stats[f"farmable {which} lot"] += 1
                        continue
                    its = lot_items(lrow)
                    if not its:
                        stats[f"{which} lot with a flag but no item"] += 1
                        continue
                    known = drops.get(lot_id)
                    if known is None:
                        x, y, z = m.vec3(poff + PART_POSITION)
                        drops[lot_id] = {"flag": flag, "items": its, "npc": npc_id,
                                         "map": map_id, "pos": (x, y, z),
                                         "sites": 1, "via": which}
                    else:
                        # A character who moves appears in several maps: one reward,
                        # one marker. Keep the first placement and count the rest so
                        # the popup can say how many places the giver turns up in.
                        known["sites"] += 1

        for off, _name in m.entries("EVENT_PARAM_ST"):
            if m.i32(off + EV_TYPE) != EVENT_TYPE_TREASURE:
                continue
            stats["treasure events"] += 1
            td = off + m.i64(off + EV_TYPEDATA_PTR)
            lot_id = m.i32(td + TD_ITEM_LOT)
            if lot_id not in lots:
                stats["lot id not in param"] += 1
                continue
            idx = m.i32(td + TD_PART_INDEX)
            if not (0 <= idx < len(part_offsets)):
                stats["part index out of range"] += 1
                continue
            x, y, z = m.vec3(part_offsets[idx] + PART_POSITION)
            # The same lot can appear in several LOD tiles of one area. Tier 0
            # is the detailed one, so let it win rather than whichever the file
            # ordering happened to reach first.
            prev = placements.get(lot_id)
            if prev is None or tier < prev[0]:
                placements[lot_id] = (tier, map_id, x, y, z)
        if (i + 1) % 200 == 0:
            print(f"    {i + 1}/{len(map_ids)} maps  ({len(placements):,} lots so far)")

    print(f"\n  {stats['treasure events']:,} treasure events -> "
          f"{len(placements):,} distinct item lots")
    for k, v in stats.most_common():
        if k != "treasure events":
            print(f"    {v:,} {k}")

    # ---- join to items + flags ---------------------------------------------
    markers = []
    dropped = Counter()
    cat_counts = Counter()
    with_item_icon = Counter()
    for lot_id, (_tier, map_id, x, y, z) in sorted(placements.items()):
        row = lots[lot_id]
        flag = lot_def.get(row.data, "getItemFlagId")
        if not flag:
            dropped["no pickup flag"] += 1
            continue
        aa, bb, cc = int(map_id[1:3]), int(map_id[4:6]), int(map_id[7:9])
        # the trailing digits of an overworld map id are its LOD tier, and each
        # tier doubles the world size of a grid cell
        tier = int(map_id[10:12]) if aa in (60, 61) else 0
        p = place2(aa, bb, cc, x, y, z, conv, tier=tier)
        if p is None:
            dropped[f"unplaceable m{aa:02d}_{bb:02d}"] += 1
            continue

        # headline item = first non-empty slot
        picked = None
        for s in range(1, 9):
            iid = lot_def.get(row.data, f"lotItemId{s:02d}")
            cat = lot_def.get(row.data, f"lotItemCategory{s:02d}")
            if iid and cat:
                nm = item_name("en", iid, cat)
                if nm:
                    picked = (iid, cat, nm)
                    break
        if not picked:
            dropped["no resolvable item name"] += 1
            continue
        iid, cat, en_name = picked
        loc_names = {loc: (item_name(loc, iid, cat) or en_name) for loc in LOCALES}
        mcat = categorise(iid, en_name, cat)
        # Gathering materials get their own category and lose their flag: the nodes
        # are picked again after every rest, so a "collected" tick on them says
        # nothing, and the map is asked a different question about them - "where do I
        # farm this" rather than "have I got it". The card still offers the manual
        # tick, because a marker with no flag is exactly the manual case.
        gather = mcat == "crafting_materials"
        if gather:
            mcat = "gathering"
            flag = None
        cat_counts[mcat] += 1
        item_icon = (item_icon_id(iid, cat)
)
        if item_icon:
            with_item_icon["real"] += 1
        else:
            with_item_icon["category only"] += 1
        markers.append({
            "id": f"item:{lot_id}",
            "cat": mcat,
            "names": loc_names,
            "flag": flag,
            "gather": True if gather else None,
            "master": p[2], "px": round(p[0], 1), "py": round(p[1], 1),
            "h": round(p[3]),
            "map": map_id,
            "lot": lot_id,
            
            "iconId": item_icon,
        })

    # Same node, several events: a bush can hold a dozen Rada Fruit pickups whose
    # coordinates are byte-identical, which the map would draw as one dot you cannot
    # count. Gatherings have no flag to preserve, so they merge by position and name
    # into one marker carrying how many pickups share the spot.
    merged_gather = {}
    kept = []
    for m in markers:
        if not m.get("gather"):
            kept.append(m)
            continue
        key = (m["master"], m["px"], m["py"], m["names"]["en"])
        first = merged_gather.get(key)
        if first is None:
            m["nodes"] = 1
            merged_gather[key] = m
            kept.append(m)
        else:
            first["nodes"] += 1
    gathered = sum(1 for m in kept if m.get("gather"))
    print(f"  gathering nodes merged: {len(markers) - len(kept)} pickups collapsed "
          f"into {gathered} nodes")
    markers = kept

    # A projection bug is silent unless you look for it - markers simply land
    # somewhere wrong. The master image is 10496px square, so anything outside
    # that is definitely a coordinate error rather than odd game data.
    MASTER = 10496
    oob = [m for m in markers
           if not (0 <= m["px"] <= MASTER and 0 <= m["py"] <= MASTER)]
    if oob:
        print(f"\n  *** {len(oob)} markers fall outside the {MASTER}px master ***")
        for m in oob[:5]:
            print(f"      {m['names']['en'][:30]:<32}{m['map']:<16}"
                  f"({m['px']:.0f},{m['py']:.0f})")

    print(f"\nitem markers: {len(markers):,}   (out of bounds: {len(oob)})")
    print("  by category: " + ", ".join(f"{k}={v}" for k, v in cat_counts.most_common()))
    if dropped:
        print("  dropped: " + ", ".join(f"{k}={v}" for k, v in dropped.most_common(6)))
    by_master = Counter(m["master"] for m in markers)
    print("  by master:   " + ", ".join(f"{k}={v}" for k, v in by_master.most_common()))
    print("  the item's own icon: "
          + ", ".join(f"{k}={v}" for k, v in with_item_icon.most_common()))

    out = os.path.join(ROOT, "data", "items.json")
    with open(out, "w", encoding="utf-8") as f:
        json.dump({"locales": list(LOCALES), "markers": markers}, f, ensure_ascii=False)
    print(f"\n-> {out}  ({os.path.getsize(out):,} bytes)   {time.time() - t0:.0f}s")

    # ---- merchants ----------------------------------------------------------
    # A separate file rather than more rows in items.json: these have no lot and
    # no pickup flag, and the server concatenates the marker files anyway, so
    # keeping them apart keeps items.json's shape honest.
    npcs = []
    npc_dropped = Counter()
    named = Counter()
    for (_map, pname), (map_id, x, y, z, npc_id) in sorted(merchants.items()):
        aa, bb, cc = int(map_id[1:3]), int(map_id[4:6]), int(map_id[7:9])
        tier = int(map_id[10:12]) if aa in (60, 61) else 0
        p = place2(aa, bb, cc, x, y, z, conv, tier=tier)
        if p is None:
            npc_dropped[f"unplaceable m{aa:02d}_{bb:02d}"] += 1
            continue
        # Each merchant carries its own NpcName when the game has one - Merchant
        # Kale at Church of Elleh, Isolated/Hermit/Abandoned/Imprisoned Merchant,
        # or simply Nomadic Merchant.
        kind = {loc: npc_name(npc_id, loc) for loc in LOCALES}
        if not any(kind.values()):
            # 8 of the 29 c3200 parts are type-10 DummyEnemy placeholders pointing at
            # the unnamed 32009000 row (NpcName literally says "DLC dummy"), and six
            # of them have no Nomad Mule anywhere in their map although every real
            # stall does (the one map with three parts has one real stall and two of
            # these). They are editing leftovers, not merchants, so they are skipped
            # rather than shown as a generic "Merchant" at a spot with nobody there.
            stats["merchant placeholders skipped"] += 1
            continue
        # Tell the eleven Nomadic Merchants apart the way the community lists do
        # ("Nomadic Merchant - Mistwood"): the kind plus the nearest named place,
        # which is the game's own grace/POI text. A place that merely repeats the
        # kind - the two "Isolated Merchant's Shack" stalls - is kept, because that
        # really is what the game calls that spot.
        qualifier = nearest_place(p[0], p[1], p[2])
        # NOMAD_SHARED_NAME: the game gives every Nomadic Merchant the same NpcName
        # entry (nameId 180000, 「“流浪商人”咖列」 / Merchant Kalé), so showing it verbatim
        # makes the map look like a dozen Kales. Use the community wording for all of
        # them except the Church of Elleh stall, which really is Kalé.
        for _loc in LOCALES:
            _k = kind.get(_loc) or ""
            _q = (qualifier.get(_loc) or qualifier.get("en") or "")
            if ("咖列" in _k or "Kalé" in _k or "Kale" in _k) and \
                    not any(x in _q for x in ("艾雷教堂", "Church of Elleh")):
                kind[_loc] = "流浪民族的商人" if _loc == "zh" else "Nomadic Merchant"
        names = {}
        for loc in LOCALES:
            q = qualifier.get(loc) or qualifier.get("en") or ""
            q = q.replace("（", "").replace("）", "")     # no nested brackets
            names[loc] = f"{kind[loc]}（{q}）" if q else kind[loc]
        named[names["en"]] += 1
        npcs.append({
            # The id has to carry the map. Part names repeat across maps (every
            # merchant in a grid area is "c3200_9000"), and the UI keys markers by
            # id, so a name-only id collapsed all 29 merchants into 3 markers.
            "id": f"npc:{map_id}:{pname}",
            "cat": "merchants",
            "names": names,
            "master": p[2], "px": round(p[0], 1), "py": round(p[1], 1),
            "h": round(p[3]),
            "map": map_id,
            "chr": MERCHANT_MODEL,
            "npcParam": npc_id,
        })
    print("  names: " + ", ".join(f"{k}={v}" for k, v in named.most_common()))
    print(f"\nmerchants: {len(npcs)} placed, from {stats['merchant parts']} "
          f"{MERCHANT_MODEL} parts ({stats['merchant parts in a LOD tier']} in LOD tiers)")
    if npc_dropped:
        print("  dropped: " + ", ".join(f"{k}={v}" for k, v in npc_dropped.most_common()))
    npc_out = os.path.join(ROOT, "data", "npcs.json")
    with open(npc_out, "w", encoding="utf-8") as f:
        json.dump({"locales": list(LOCALES), "markers": npcs}, f, ensure_ascii=False)
    print(f"-> {npc_out}  ({os.path.getsize(npc_out):,} bytes)")

    # ---- one-time rewards ---------------------------------------------------
    # A drop is not a pickup point, so it gets its own file and its own category:
    # the question it answers is "where does this come from", which the popup spells
    # out ("来源：帕奇"). The item keeps its own name and its own icon.
    drop_markers = []
    drop_dropped = Counter()
    drop_cats = Counter()
    for lot_id, d in sorted(drops.items()):
        map_id = d["map"]
        aa, bb, cc = int(map_id[1:3]), int(map_id[4:6]), int(map_id[7:9])
        tier = int(map_id[10:12]) if aa in (60, 61) else 0
        p = place2(aa, bb, cc, *d["pos"], conv, tier=tier)
        if p is None:
            drop_dropped[f"unplaceable m{aa:02d}_{bb:02d}"] += 1
            continue
        picked = None
        for iid, cat, num in d["items"]:
            if item_name("en", iid, cat):
                picked = (iid, cat, num)
                break
        if picked is None:
            drop_dropped["no resolvable item name"] += 1
            continue
        iid, cat, num = picked
        en_name = item_name("en", iid, cat)
        names = {loc: (item_name(loc, iid, cat) or en_name) for loc in LOCALES}
        # Split the rewards by what the reward *is*, which is what a player looks
        # for: a bell bearing is not a weapon. lotItemCategory gives the kind for
        # free (1 goods, 2 weapon, 3 protector, 4 accessory, 5 gem); bell bearings
        # are goods, so they are recognised by the game's own name for them.
        #
        # A bell bearing is filed by *what it unlocks*, not by who dropped it: the
        # smithing-stone, somber, glovewort and ghost-glovewort bells already have
        # rows, and asking the same classifier the pickups use means a character bell
        # that unlocked stones would land in the stone row by itself. Everything else
        # is a vendor / character bell and stays in its own row.
        if "铃珠" in names.get("zh", "") or "bell bearing" in en_name.lower():
            unlock_cat = categorise(iid, en_name, cat)
            drop_cat = (unlock_cat if unlock_cat in
                        ("bell_smithing", "bell_somber", "bell_glovewort",
                         "bell_ghost_glovewort") else "drop_bell_bearings")
        else:
            # One Ash of War is not worth a legend row of its own, and its name says
            # what it is ("战灰：重力"), so category 5 goes in with the items.
            # A ladder material keeps its ladder row: the reward is otherwise sorted by
            # kind, which would file 墓地铃兰【３】 under "items" and leave the glovewort
            # ladder incomplete. Pickups of the same items already use the ladder.
            _ladder = categorise(iid, item_name("en", iid, cat) or "", cat)
            drop_cat = (_ladder if _ladder.startswith(("glovewort_", "smithing_stone_",
                                                      "somber_stone_"))
                        else {1: "drop_items", 2: "drop_weapons", 3: "drop_armour",
                              4: "drop_talismans"}.get(cat, "drop_items"))
        drop_cats[drop_cat] += 1
        # The giver's own name where the game has one; 74 of the 133 rewards sit on
        # an enemy whose NpcName row is the "DLC dummy" placeholder, and claiming a
        # name there would be inventing one.
        source = {loc: npc_name(d["npc"], loc) for loc in LOCALES}
        if not source.get("en") or "dummy" in source["en"].lower():
            source = None
        drop_markers.append({
            "id": f"drop:{lot_id}",
            "cat": drop_cat,
            "names": names,
            "flag": d["flag"],
            "master": p[2], "px": round(p[0], 1), "py": round(p[1], 1),
            "h": round(p[3]),
            "map": map_id,
            "lot": lot_id,
            "iconId": item_icon_id(iid, cat),
            "source": source,
            "sites": d["sites"],          # how many places the giver appears in
            "via": d["via"],              # "map" = scripted reward, "enemy" = death
        })
    print(f"\none-time rewards: {len(drop_markers)} placed "
          f"({sum(1 for m in drop_markers if m['source'])} with a named giver), "
          f"from {stats['farmable map lot'] + stats['farmable enemy lot']:,} farmable lots skipped")
    print("  by kind: " + ", ".join(f"{k}={v}" for k, v in drop_cats.most_common()))
    if drop_dropped:
        print("  dropped: " + ", ".join(f"{k}={v}" for k, v in drop_dropped.most_common()))
    # ---- writing the reward files ------------------------------------------
    def dedupe_same_item(rewards):
        """Drop the second marker when two lots grant the same item at one spot.

        Godrick's Great Rune is goods 8148 *and* goods 191, and both lots hang off
        the same boss at the same coordinate - two card entries saying exactly the
        same thing on one pixel read as a bug, and the player gets the item once
        either way. Position is compared exactly because these lots overlap exactly.
        """
        seen, out = set(), []
        for m in rewards:
            key = (m["names"]["en"], m["master"], m["px"], m["py"])
            if key in seen:
                stats["same item, same spot (merged)"] += 1
                continue
            seen.add(key)
            out.append(m)
        return out

    drop_markers = dedupe_same_item(drop_markers)
    drop_out = os.path.join(ROOT, "data", "drops.json")
    with open(drop_out, "w", encoding="utf-8") as f:
        json.dump({"locales": list(LOCALES), "markers": drop_markers}, f, ensure_ascii=False)
    print(f"-> {drop_out}  ({os.path.getsize(drop_out):,} bytes)")

    # ---- boss rewards -------------------------------------------------------
    # A boss's reward is not in any param table next to the boss: GameAreaParam
    # (which we already use for the boss markers) holds only souls and flags, and
    # no ItemLotParam row carries a boss's defeat flag as its getItemFlagId - both
    # checked. The reward is awarded by the event script when the boss dies.
    #
    # Decompiling EMEVD is a project of its own, so this reuses the trick the boss
    # *names* already use in build_markers.py: the defeat flag is an exact known
    # value, so scan the boss's own .emevd for it and look nearby for a word that
    # is a real ItemLotParam_map row carrying a persistent flag. That alone is too
    # noisy - lot10000 (Talisman Pouch) and lot20000 (Lhutel the Headless) turn up
    # near 60+ bosses because shared script code mentions them - so two filters cut
    # it down, and both are pure counting:
    #
    #   * a lot may be near exactly one boss (shared code is near many), and
    #   * that lot may appear in exactly one .emevd file (shared code is in many).
    #
    # What survives is the classic boss loot table: Tree Sentinel -> Golden
    # Halberd, Black Knife Assassin -> Black Knife, Godskin Apostle -> Godskin
    # Peeler, dragons -> Dragon Heart. Remembrances and Great Runes are handled
    # separately and are exact: the game names them after the boss, so
    # "Remembrance of the Grafted" is matched to "Godrick the Grafted" by name.
    boss_markers = {}
    if os.path.isfile(markers_path):
        with open(markers_path, encoding="utf-8") as f:
            for m in json.load(f).get("markers", []):
                if m.get("cat") == "boss" and m.get("flag"):
                    boss_markers[m["flag"]] = m
    ga_def = paramdef.load(os.path.join(DEFS, "GameAreaParam.xml"))
    flagged_lots = {}
    for lot_id, row in lots.items():
        if lot_def.get(row.data, "getItemFlagId"):
            flagged_lots[lot_id] = row
    boss_files = defaultdict(set)
    flag_file = {}
    for r in params["GameAreaParam"].rows:
        flag = ga_def.get(r.data, "defeatBossFlagId")
        if not flag or flag not in boss_markers:
            continue
        mid = "m%02d_%02d_%02d_00" % (ga_def.get(r.data, "bossMapAreaNo"),
                                     ga_def.get(r.data, "bossMapBlockNo"),
                                     ga_def.get(r.data, "bossMapMapNo"))
        flag_file[flag] = mid
        boss_files[mid].add(flag)

    raw_events, near, seen_once = {}, defaultdict(set), Counter()
    for mid in sorted(boss_files):
        path = f"/event/{mid}.emevd.dcx"
        if not modfiles.has(dvd, mod, path):
            continue
        try:
            raw = dcx.decompress(modfiles.read(dvd, mod, path), oodle=helper)
        except Exception:
            continue
        raw_events[mid] = raw
        for flag in boss_files[mid]:
            packed = struct.pack("<I", flag)
            i = raw.find(packed)
            while i != -1:
                for delta in range(-BOSS_WINDOW, BOSS_WINDOW + 1, 4):
                    j = i + delta
                    if 0 <= j <= len(raw) - 4:
                        lot_id = struct.unpack_from("<I", raw, j)[0]
                        if lot_id in flagged_lots:
                            near[lot_id].add(flag)
                            seen_once[lot_id] += 1
                i = raw.find(packed, i + 1)

    claimed = {m["lot"] for m in drop_markers} | {int(m["id"].split(":")[-1])
                                                for m in markers if m["id"].startswith("item:")}
    boss_extra, boss_dropped = [], Counter()
    for lot_id, flags in sorted(near.items()):
        if len(flags) != 1 or lot_id in claimed:
            continue
        # Only one event script may mention it at all.
        if sum(1 for raw in raw_events.values() if struct.pack("<I", lot_id) in raw) != 1:
            boss_dropped["lot shared by several scripts"] += 1
            continue
        boss = boss_markers[next(iter(flags))]
        row = flagged_lots[lot_id]
        items = lot_items(row)
        picked = next(((iid, cat) for iid, cat, _n in items if item_name("en", iid, cat)), None)
        if picked is None:
            boss_dropped["no resolvable item name"] += 1
            continue
        iid, cat = picked
        en_name = item_name("en", iid, cat)
        boss_extra.append({
            "id": f"drop:{lot_id}",
            "cat": "boss_drops",
            "names": {loc: (item_name(loc, iid, cat) or en_name) for loc in LOCALES},
            "flag": lot_def.get(row.data, "getItemFlagId"),
            "master": boss["master"], "px": boss["px"], "py": boss["py"],
            "h": boss.get("h"),
            "map": boss.get("map"),
            "lot": lot_id,
            "iconId": item_icon_id(iid, cat),
            # The derived "landmark near ..." boss names are ours, not the game's;
            # using one as a source would read as a name the game never gave.
            "source": None if boss["names"]["zh"].startswith(("附近的首领战场", "首领战场"))
                      else boss["names"],
            "via": "script",
        })
    print(f"\nboss rewards: {len(boss_extra)} placed from the event scripts "
          f"({len(near)} lots were near a boss, {len(boss_dropped):,} filtered)")
    if boss_dropped:
        print("  filtered: " + ", ".join(f"{k}={v}" for k, v in boss_dropped.most_common()))

    # Remembrances and Great Runes are the exception: they are handed over by the
    # shared scripts, so the scan above misses them (and the one it did catch was
    # wrong - Radahn's Great Rune sitting in the Godskin Apostle's file). The game
    # names them after the boss, though, so "Remembrance of the Grafted" is matched
    # to "Godrick the Grafted" by name instead: exact, and it overrides the scan.
    def norm(s):
        return re.sub(r"[「」“”·\s]", "", s)

    def name_parts(m):
        """-> [(title, name)] for a boss marker name.

        Names arrive as '「接肢」葛瑞克', '"Malenia, Blade of Miquella"' or
        'Godfrey / Hoarah Loux' for a two-phase fight. Splitting the title off is
        what makes a remembrance land on the boss instead of on one of his
        soldiers: the item's key equals the *name* or the *title* of exactly one
        boss, while '葛瑞克的士兵' equals neither.
        """
        out = []
        for phase in re.split(r"[/／]", m["names"]["zh"]):
            mt = re.match(r"^[「“\"]([^」”\"]+)[」”\"]\s*(.+)$", phase.strip())
            if mt:
                out.append((norm(mt.group(1)), norm(mt.group(2))))
            else:
                out.append(("", norm(phase)))
        return out

    def match_score(key, m):
        """Lower is better: exact name, exact title, name starts with it, contained."""
        best = None
        for title, name in name_parts(m):
            if key == name:
                s = 0
            elif key and key == title:
                s = 1
            elif key and name.startswith(key):
                s = 2
            elif key and key in name:
                s = 3
            elif key and key in title:
                s = 4
            else:
                continue
            best = s if best is None else min(best, s)
        return best

    boss_by_name = [m for m in boss_markers.values()
                    if not m["names"]["zh"].startswith(("附近的首领战场", "首领战场"))]
    placed_by_name = {}
    for lot_id, row in sorted(flagged_lots.items()):
        if lot_id in claimed:
            continue
        items = lot_items(row)
        picked = next(((iid, cat) for iid, cat, _n in items if item_name("en", iid, cat)), None)
        if picked is None:
            continue
        iid, cat = picked
        name = item_name("zh", iid, cat) or ""
        key = re.sub(r"的(追忆|大卢恩)$", "", norm(name))
        if key == norm(name):          # not a remembrance or a great rune
            continue
        scored = [(match_score(key, m), m) for m in boss_by_name]
        scored = [(s, m) for s, m in scored if s is not None]
        if not scored:
            boss_dropped["remembrance with no matching boss"] += 1
            continue
        # Best name match first, then the base game over the DLC (the DLC has a
        # second Radahn), then the shorter name.
        scored.sort(key=lambda sm: (sm[0], sm[1]["master"] != "M00",
                                    len(sm[1]["names"]["zh"])))
        boss = scored[0][1]
        en_name = item_name("en", iid, cat)
        placed_by_name[lot_id] = {
            "id": f"drop:{lot_id}",
            "cat": "boss_drops",
            "names": {loc: (item_name(loc, iid, cat) or en_name) for loc in LOCALES},
            "flag": lot_def.get(row.data, "getItemFlagId"),
            "master": boss["master"], "px": boss["px"], "py": boss["py"],
            "h": boss.get("h"), "map": boss.get("map"), "lot": lot_id,
            "iconId": item_icon_id(iid, cat),
            "source": boss["names"],
            "via": "name",
        }
    overridden = [m for m in boss_extra if m["lot"] in placed_by_name]
    boss_extra = [m for m in boss_extra if m["lot"] not in placed_by_name]
    boss_extra.extend(placed_by_name.values())
    print(f"  remembrances / great runes matched by name: {len(placed_by_name)}"
          + (f" ({len(overridden)} of them replaced a script guess)" if overridden else ""))
    # Curated attributions for boss rewards the scripts do not tie to a boss (see
    # data/boss-drop-overrides.json). The lot, its flag and its items come from the
    # game; only "which boss grants it" is curated, and each entry carries its source
    # so it can be reviewed or dropped.
    overrides_path = os.path.join(ROOT, "data", "boss-drop-overrides.json")
    applied = 0
    if os.path.isfile(overrides_path):
        with open(overrides_path, encoding="utf-8") as f:
            doc = json.load(f)
        boss_by_flag = {}
        markers_path = os.path.join(ROOT, "data", "markers.json")
        if os.path.isfile(markers_path):
            with open(markers_path, encoding="utf-8") as f:
                for mk in json.load(f).get("markers", []):
                    if mk.get("cat") == "boss" and mk.get("flag"):
                        boss_by_flag.setdefault(mk["flag"], mk)
        for ov in doc.get("overrides", []):
            mk = boss_by_flag.get(ov.get("bossFlag"))
            row = lots.get(ov.get("lot"))
            if mk is None or row is None:
                stats["boss override unmatched"] += 1
                continue
            for iid, cat, _qty in lot_items(row):
                if cat is None:
                    continue
                if boss_extra is None:
                    boss_extra = []
                boss_extra.append({
                    "id": f"bossdrop:{ov['lot']}:{cat}:{iid}",
                    "cat": "boss_drops",
                    "names": {loc: (item_name(loc, iid, cat) or mk["names"].get(loc))
                              for loc in LOCALES},
                    "flag": None,
                    "master": mk["master"], "px": mk["px"], "py": mk["py"], "h": mk.get("h"),
                    "map": mk.get("map"), "lot": ov["lot"],
                    "source": ov.get("boss"),
                    "via": "curated",
                    "note": ov.get("source"),
                })
                applied += 1
    print(f"  boss drop overrides applied: {applied}")

    if boss_extra:
        boss_extra = dedupe_same_item(boss_extra)
        extra_out = os.path.join(ROOT, "data", "boss-drops.json")
        with open(extra_out, "w", encoding="utf-8") as f:
            json.dump({"locales": list(LOCALES), "markers": boss_extra}, f,
                      ensure_ascii=False)
        print(f"-> {extra_out}  ({len(boss_extra)} markers, "
              f"{os.path.getsize(extra_out):,} bytes)")

    sample_loc = next((loc for loc in LOCALES if loc != "en"), "en")
    print(f"\nsample (en / {sample_loc}):")
    for m in markers[:10]:
        print(f"   {m['names']['en'][:34]:<36}{m['names'].get(sample_loc,'')[:30]:<32}"
              f"{m['cat']:<10}flag={m['flag']}")
    dvd.close()


if __name__ == "__main__":
    main()
