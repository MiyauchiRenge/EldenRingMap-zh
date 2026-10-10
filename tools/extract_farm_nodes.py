"""Mark where a farmable enemy drop actually comes from: data/farm.json.

The map's pickups come from treasure events, which carry coordinates. Enemy-drop
lots do not: `NpcParam.itemLotId_enemy` hangs off the *character*, so one lot is
carried by every placement of that character. The sibling project
(ChenxiLiu-code/EldenRingTool) stops there and lists such items as enemy_drop with
no position at all; this walks the other half of the chain - MSB part ->
`PART_NPC_PARAM_ID` -> NpcParam -> itemLotId_enemy - and marks the placements, so
"where do I farm 灵依墓地铃兰【２】" has an answer on the map.

Scope: by default only the items the game places nowhere, which for the glovewort
ladder is 墓地【2】-【4】 and 灵依【1】-【4】. Those are exactly the ones whose legend
row is missing, so this also completes the 1-9 ladder. A common enemy would
otherwise flood the map, so each lot is capped at --per-lot markers and carries the
full count in `sites`.

    python tools/extract_farm_nodes.py  ->  data/farm.json
"""
import argparse
import json
import os
import re
import sys
import time
from collections import defaultdict

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)

from erlib import dcx, fmg, oodle, param, paramdef
from erlib import msb as msblib
import erlib.modfiles as modfiles
from erlib.dvdbnd import DvdBnd
from erlib.gamepath import require_game_dir
from build_markers import LegacyConv, place          # the same projection
# everything else uses

from extract_items import (CATEGORY_TABLES, NPC_PARAM_NAME_ID_OFF, PART_NPC_PARAM_ID,
                           PART_POSITION, PART_TYPE, PART_TYPE_DUMMY_ENEMY,
                           PART_TYPE_ENEMY, part_model)

ROOT = os.path.dirname(HERE)
DEFS = os.path.join(ROOT, "data", "paramdefs")
LOCALES = {"en": "engus", "zh": "zhocn"}
TABLE_OF_NAME = {1: "GoodsName", 2: "WeaponName", 3: "ProtectorName",
                 4: "AccessoryName", 5: "GemName"}

LADDERS = ((re.compile(r"^墓地铃兰【(\d+)】$"), "glovewort_grave_%d"),
           (re.compile(r"^灵依墓地铃兰【(\d+)】$"), "glovewort_ghost_%d"))


def main():
    t0 = time.time()
    ap = argparse.ArgumentParser(description=__doc__,
                                 formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--game-dir", default=None)
    ap.add_argument("--per-lot", type=int, default=60,
                    help="keep at most this many placements per lot (default 60)")
    ap.add_argument("--all-gloveworts", action="store_true",
                    help="also include the levels that already have placed pickups")
    ap.add_argument("--all-unmarked", action="store_true",
                    help="every enemy-lot item that has no marker yet, instead of the ladder")
    ap.add_argument("--items", default=None,
                    help="comma-separated item names (zh) instead of the ladder levels")
    args = ap.parse_args()

    game = require_game_dir(args.game_dir)
    mod = modfiles.find_mod_dir(None)
    dvd = DvdBnd(game, cache_dir=os.path.join(ROOT, "cache"), verbose=False)
    helper = oodle.make_helper(game)
    params = param.load_params(modfiles.regulation_path(game, mod))
    lot_def = paramdef.load(os.path.join(DEFS, "ItemLotParam.xml"))
    npc_def = paramdef.load(os.path.join(DEFS, "NpcParam.xml"))
    conv = LegacyConv(params["WorldMapLegacyConvParam"].rows,
                      paramdef.load(os.path.join(DEFS, "WorldMapLegacyConvParam.xml")))

    names = {}
    for loc, folder in LOCALES.items():
        tables = {}
        for f in ("item.msgbnd.dcx", "item_dlc02.msgbnd.dcx"):
            p = f"/msg/{folder}/{f}"
            if modfiles.has(dvd, mod, p):
                for k, v in fmg.load_msgbnd(modfiles.read(dvd, mod, p), oodle=helper).items():
                    tables.setdefault(k.split("_dlc")[0], {}).update(v)
        names[loc] = tables
    goods = names["en"].get("GoodsName", {})
    # The ladder names are matched in Chinese, so the Chinese table is what has to be
    # read here - matching Chinese names against the English table found nothing.
    zh_goods = names["zh"].get("GoodsName", {})

    def lot_items(row):
        out = []
        for i in range(1, 9):
            iid = lot_def.get(row.data, "lotItemId%02d" % i)
            if iid and lot_def.get(row.data, "lotItemCategory%02d" % i) == 1:
                out.append(iid)
        return out

    # What the map already shows, not what any lot mentions: several of these items do
    # sit in ItemLotParam_map rows that never became markers (script-granted lots, or
    # parts that are not treasure events), and those levels are exactly the ones whose
    # legend row is missing.
    rows_by_id = {r.id: r for r in params["ItemLotParam_map"].rows}
    npc_rows = {r.id: r for r in params["NpcParam"].rows}

    def item_names(iid, cat, loc):
        tbl = CATEGORY_TABLES.get(cat)
        if not tbl:
            return ""
        v = names[loc].get(tbl, {}).get(iid, "")
        if not v or v.startswith("%null%"):
            v = names["en"].get(tbl, {}).get(iid, "")
        return "" if v.startswith("%null%") else v

    # Human-supplied names for enemies the game leaves unnamed (data/enemy-names.json),
    # keyed by chr model, since that is the only stable handle such an enemy has.
    curated_names = {}
    curated_path = os.path.join(ROOT, "data", "enemy-names.json")
    if os.path.isfile(curated_path):
        with open(curated_path, encoding="utf-8") as f:
            curated_names = {k: v for k, v in json.load(f).get("names", {}).items()
                             if isinstance(v, dict) and not k.startswith("_")}

    def npc_name(npc_id):
        """NpcParam id -> {loc: name}; most enemies are unnamed, which is fine."""
        row = npc_rows.get(npc_id)
        if row is None:
            return {}
        try:
            name_id = npc_def.get(row.data, "nameId")
        except Exception:
            try:
                import struct
                name_id = struct.unpack_from("<i", row.data, NPC_PARAM_NAME_ID_OFF)[0]
            except Exception:
                return {}
        out = {}
        for loc in LOCALES:
            v = names[loc].get("NpcName", {}).get(name_id, "")
            if not v or v.startswith("%null%") or "dummy" in v.lower():
                v = ""
            out[loc] = v
        return out

    def lot_table(lot_id):
        """-> [{names, qty, kind}] for every slot of an enemy lot."""
        row = {r.id: r for r in params["ItemLotParam_enemy"].rows}.get(lot_id)
        if row is None:
            return []
        out = []
        for i in range(1, 9):
            iid = lot_def.get(row.data, "lotItemId%02d" % i)
            if not iid:
                continue
            cat = lot_def.get(row.data, "lotItemCategory%02d" % i)
            nm = {loc: item_names(iid, cat, loc) for loc in LOCALES}
            if not nm.get("en") and not nm.get("zh"):
                continue
            out.append({"names": nm,
                        "qty": lot_def.get(row.data, "lotItemNum%02d" % i),
                        "kind": cat})
        return out

    placed = set()
    items_json = os.path.join(ROOT, "data", "items.json")
    if os.path.isfile(items_json):
        for mk in json.load(open(items_json, encoding="utf-8"))["markers"]:
            row = rows_by_id.get(mk.get("lot"))
            if row is not None:
                placed.update(lot_items(row))
    print("items with a marker already: %d" % len(placed))
    enemy_by_item = defaultdict(list)
    for r in params["ItemLotParam_enemy"].rows:
        for iid in lot_items(r):
            enemy_by_item[iid].append(r.id)

    targets = {}
    if args.all_unmarked:
        # Every item that some ItemLotParam_enemy row awards and that we do not mark
        # anywhere yet. One category for all of them: the marker carries the item's own
        # name and icon, so it still says what it is.
        marked = set()
        for fname in ("markers.json", "items.json", "drops.json", "boss-drops.json"):
            fpath = os.path.join(ROOT, "data", fname)
            if os.path.isfile(fpath):
                with open(fpath, encoding="utf-8") as f:
                    for mk in json.load(f).get("markers", []):
                        marked.add(mk["names"].get("zh") or mk["names"].get("en"))
        # name -> (id, kind) for everything any enemy lot awards
        by_name = {}
        for row in params["ItemLotParam_enemy"].rows:
            for i in range(1, 9):
                iid = lot_def.get(row.data, "lotItemId%02d" % i)
                if not iid:
                    continue
                cat = lot_def.get(row.data, "lotItemCategory%02d" % i)
                nm = names["zh"].get(TABLE_OF_NAME.get(cat, ""), {}).get(iid, "")
                if nm and nm not in marked:
                    by_name[nm] = (iid, cat)
        for nm, (iid, cat) in by_name.items():
            lots = sorted(set(enemy_by_item.get(iid, [])))
            if not lots:
                continue
            # A ladder level keeps its own row (the glovewort legend is the point there);
            # everything else shares farm_spots, where the marker's own name and icon say
            # what it is.
            tcat = "farm_spots"
            for rx, lcat in LADDERS:
                m = rx.match(nm)
                if m:
                    tcat = lcat % int(m.group(1))
                    break
            targets[iid] = {"cat": tcat, "lots": lots, "kind": cat}
    for iid, name in ({} if args.all_unmarked else zh_goods).items():
        for rx, cat in LADDERS:
            m = rx.match(name or "")
            if not m:
                continue
            if iid in placed and not args.all_gloveworts:
                continue                       # it already has a fixed pickup
            targets[iid] = {"cat": cat % int(m.group(1)),
                            "lots": sorted(set(enemy_by_item.get(iid, [])))}
    print("target items: %d" % len(targets))
    for iid, t in sorted(targets.items(), key=lambda kv: kv[1]["cat"]):
        print("   id %-8s %-14s enemy lots %d" % (iid, t["cat"], len(t["lots"])))
    if not targets:
        sys.exit("nothing to do")

    wanted = defaultdict(list)                 # lot_id -> [item id]
    for iid, t in targets.items():
        for lot_id in t["lots"]:
            wanted[lot_id].append(iid)

    map_list = os.path.join(ROOT, "cache", "map-list.txt")
    if not os.path.exists(map_list):
        sys.exit("run tools/dev/enumerate_maps.py first (creates cache/map-list.txt)")
    map_ids = [l.split("\t")[0] for l in open(map_list, encoding="utf-8") if l.strip()]
    print("scanning %d MSB files ..." % len(map_ids))

    found = defaultdict(list)                  # lot -> [(map, x, y, z, npc, model)]
    part_types = defaultdict(int)
    for map_id in map_ids:
        aa = int(map_id[1:3])
        tier = int(map_id[10:12]) if aa in (60, 61) else 0
        if tier:
            continue                           # a LOD copy, not a real spawn
        path = "/map/mapstudio/%s.msb.dcx" % map_id
        if not modfiles.has(dvd, mod, path):
            continue
        try:
            m = msblib.load(dcx.decompress(modfiles.read(dvd, mod, path), oodle=helper))
        except Exception:
            continue
        for poff, pname in m.entries("PARTS_PARAM_ST"):
            # No PART_TYPE filter here: four of the seven levels hang off parts that
            # are neither Enemy nor DummyEnemy, and any part that names an NpcParam can
            # carry that NpcParam's enemy lot. The type is recorded so the count can be
            # checked against what the earlier pass saw.
            nrow = npc_rows.get(m.i32(poff + PART_NPC_PARAM_ID))
            if nrow is None:
                continue
            lot_id = npc_def.get(nrow.data, "itemLotId_enemy")
            if lot_id not in wanted:
                continue
            x, y, z = m.vec3(poff + PART_POSITION)
            part_types[m.u32(poff + PART_TYPE)] += 1
            found[lot_id].append((map_id, x, y, z, m.i32(poff + PART_NPC_PARAM_ID),
                                  part_model(pname)))

    markers, hidden = [], 0
    bb, cc = 0, 0
    for lot_id, hits in sorted(found.items()):
        kept, seen = [], set()
        for hit in hits:
            key = (hit[0], round(hit[1], 1), round(hit[2], 1))
            if key in seen:
                continue
            seen.add(key)
            kept.append(hit)
        total = len(kept)
        if total > args.per_lot:
            hidden += total - args.per_lot
            kept = kept[:args.per_lot]
        for iid in wanted[lot_id]:
            for map_id, x, y, z, npc_id, model in kept:
                aa = int(map_id[1:3]); bb = int(map_id[4:6]); cc = int(map_id[7:9])
                tier = int(map_id[10:12]) if aa in (60, 61) else 0
                p = place(aa, bb, cc, x, y, z, conv, tier=tier)
                if p is None:
                    # Many maps need no legacy conversion, so they have no
                    # projected position: skip rather than crash.
                    continue
                enames = npc_name(npc_id)
                if not (enames.get("zh") or enames.get("en")):
                    enames = curated_names.get(model, enames)
                markers.append({
                    "id": "farm:%s:%s:%d" % (lot_id, map_id, len(markers)),
                    "enemy": {"npc": npc_id, "model": model, "names": enames},
                    "drops": lot_table(lot_id),
                    "cat": targets[iid]["cat"],
                    "names": {loc: (names[loc].get("GoodsName", {}).get(iid) or goods.get(iid))
                              for loc in LOCALES},
                    "flag": None,
                    "farm": True,
                    "lot": lot_id,
                    "npc": npc_id,
                    "model": model,
                    "sites": total,
                    "master": p[2],
                    "px": round(p[0], 1), "py": round(p[1], 1), "h": round(p[3]),
                    "map": map_id,
                })
    print("part types carrying these lots: %s"
          % dict(sorted(part_types.items())))
    print("farm markers: %d (%d placements hidden by --per-lot %d)"
          % (len(markers), hidden, args.per_lot))
    enemies = defaultdict(int)
    for mk in markers:
        e = mk["enemy"]
        label = e["names"].get("zh") or e["names"].get("en") or e["model"]
        enemies[label] += 1
    print("enemies involved: %s" % dict(sorted(enemies.items(), key=lambda kv: -kv[1])))
    by_cat = defaultdict(int)
    for mk in markers:
        by_cat[mk["cat"]] += 1
    for cat, n in sorted(by_cat.items()):
        print("   %-20s %d" % (cat, n))

    out = os.path.join(ROOT, "data", "farm.json")
    with open(out, "w", encoding="utf-8") as f:
        json.dump({"markers": markers}, f, ensure_ascii=False)
    print("-> %s  (%.0fs)" % (out, time.time() - t0))
    dvd.close()


if __name__ == "__main__":
    main()
