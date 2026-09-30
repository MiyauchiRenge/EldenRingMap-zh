"""Sequential-lot follow-ups, with positions taken from every kind of world reference.

A placed lot P also grants P+1, P+2, ... while those rows exist (soulsmodding ItemLotParam:
"all item lots with sequential IDs will automatically be granted as well"). The first version
only used lots that already had markers, which missed the levels whose parent row (e.g.
511000000) carries no marker itself. This version collects positions from:

  * our existing markers (lot -> position)
  * MSB parts' +0x260 field            (gatherable/plant item lot)
  * NpcParam.itemLotId_enemy/_map      (via the parts that carry that NPC)
  * treasure events' lot               (chests and corpses)

then emits P+1..P+7 at P's position. Ladder materials are filed into their ladder row.
Output: data/followup.json. Prints real counts and the glovewort rows created.
"""
from __future__ import annotations

import io
import json
import os
import re
import sys
from collections import defaultdict

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)
from erlib import dcx, emevd, fmg, msb as msblib, oodle, param, paramdef     # noqa: E402
import erlib.modfiles as modfiles                                            # noqa: E402
from erlib.dvdbnd import DvdBnd                                              # noqa: E402
from erlib.gamepath import require_game_dir                                  # noqa: E402
from build_markers import LegacyConv, place                                  # noqa: E402
from extract_items import (EV_TYPE, EV_TYPEDATA_PTR, TD_ITEM_LOT,            # noqa: E402
                           TD_PART_INDEX, PART_POSITION, EVENT_TYPE_TREASURE)

ROOT = os.path.dirname(HERE)
TABLE_OF_KIND = {1: "GoodsName", 2: "WeaponName", 3: "ProtectorName",
                 4: "AccessoryName", 5: "GemName"}
DROP_CAT = {1: "drop_items", 2: "drop_weapons", 3: "drop_armour",
            4: "drop_talismans", 5: "drop_items"}
MAX_FOLLOW = 64      # follow until the run breaks (documented chain)
GATHER_FIELD = 0x260
LADDER = [
    (re.compile(r"^墓地铃兰【(\d+)】$"), "glovewort_grave_%d"),
    (re.compile(r"^大朵墓地铃兰$"), "glovewort_grave_great"),
    (re.compile(r"^灵依墓地铃兰【(\d+)】$"), "glovewort_ghost_%d"),
    (re.compile(r"^大朵灵依墓地铃兰$"), "glovewort_ghost_great"),
    (re.compile(r"^锻造石【(\d+)】$"), "smithing_stone_%d"),
    (re.compile(r"^失色锻造石【(\d+)】$"), "somber_stone_%d"),
    (re.compile(r"^古龙岩锻造石$"), "smithing_stone_legend"),
    (re.compile(r"^古龙岩失色锻造石$"), "somber_stone_legend"),
]


def ladder_cat(name):
    for rx, catform in LADDER:
        m = rx.match(name)
        if m:
            return catform % int(m.group(1)) if m.groups() else catform
    return None


def main():
    game = require_game_dir(None)
    mod = modfiles.find_mod_dir(None)
    dvd = DvdBnd(game, cache_dir=os.path.join(ROOT, "cache"), verbose=False)
    helper = oodle.make_helper(game)
    params = param.load_params(modfiles.regulation_path(game, mod))
    ld = paramdef.load(os.path.join(ROOT, "data", "paramdefs", "ItemLotParam.xml"))
    nd = paramdef.load(os.path.join(ROOT, "data", "paramdefs", "NpcParam.xml"))
    conv = LegacyConv(params["WorldMapLegacyConvParam"].rows,
                      paramdef.load(os.path.join(ROOT, "data", "paramdefs",
                                                "WorldMapLegacyConvParam.xml")))
    names = {}
    for f in ("item.msgbnd.dcx", "item_dlc02.msgbnd.dcx"):
        p = "/msg/zhocn/%s" % f
        if modfiles.has(dvd, mod, p):
            for k, v in fmg.load_msgbnd(modfiles.read(dvd, mod, p), oodle=helper).items():
                names.setdefault(k.split("_dlc")[0], {}).update(v)

    def name_of(iid, kind):
        for t in [TABLE_OF_KIND.get(kind, "")] + ["GoodsName", "WeaponName", "ProtectorName",
                                                 "AccessoryName", "GemName"]:
            nm = (names.get(t) or {}).get(iid, "") if t else ""
            if nm and "[ERROR]" not in nm:
                return nm
        return ""

    lots = {}
    for tbl in ("ItemLotParam_map", "ItemLotParam_enemy"):
        for r in params[tbl].rows:
            items = []
            for i in range(1, 9):
                if ld.get(r.data, "lotItemCategory%02d" % i) == -1:
                    continue
                iid = ld.get(r.data, "lotItemId%02d" % i)
                if iid:
                    items.append((iid, ld.get(r.data, "lotItemCategory%02d" % i),
                                  ld.get(r.data, "lotItemNum%02d" % i)))
            if items:
                lots[r.id] = items
    npc_lots = {}
    for r in params["NpcParam"].rows:
        for field in ("itemLotId_enemy", "itemLotId_map"):
            lot = nd.get(r.data, field)
            if lot and lot > 0:
                npc_lots.setdefault(r.id, set()).add(lot)
    print("lots with items: %d ; npcs with lot fields: %d" % (len(lots), len(npc_lots)))

    # positions: existing markers first
    placed = defaultdict(list)
    existing = set()
    for f in ("items.json", "drops.json", "boss-drops.json", "farm.json", "emevd-drops.json",
              "user-placed.json"):
        p = os.path.join(ROOT, "data", f)
        if not os.path.isfile(p):
            continue
        for m in json.load(open(p, encoding="utf-8"))["markers"]:
            existing.add((m["names"]["zh"], round(m["px"]), round(m["py"])))
            if m.get("lot"):
                placed[m["lot"]].append(m)
    print("from markers: %d referenced lots" % len(placed))

    # world positions
    map_ids = [l.split("\t")[0] for l in open(os.path.join(ROOT, "cache", "map-list.txt"),
                                             encoding="utf-8") if l.strip()]
    parts = 0
    for mid in map_ids:
        path = "/map/mapstudio/%s.msb.dcx" % mid
        if not modfiles.has(dvd, mod, path):
            continue
        try:
            m = msblib.load(dcx.decompress(modfiles.read(dvd, mod, path), oodle=helper))
        except Exception:
            continue
        aa, bb, cc = int(mid[1:3]), int(mid[4:6]), int(mid[7:9])
        tier = int(mid[10:12]) if aa in (60, 61) else 0
        part_offsets = [po for po, _n in m.entries("PARTS_PARAM_ST")]
        for poff, _n in m.entries("PARTS_PARAM_ST"):
            parts += 1
            p = place(aa, bb, cc, *m.vec3(poff + PART_POSITION), conv, tier=tier)
            if p is None:
                continue
            rec = {"px": round(p[0], 1), "py": round(p[1], 1), "h": round(p[3]),
                   "master": p[2], "map": mid}
            # 1) gatherable field
            try:
                glot = m.i32(poff + GATHER_FIELD)
            except Exception:
                glot = 0
            if glot and glot > 0:
                placed[glot].append(rec)
            # 2) npc lot fields
            nid = emevd.npc_id_of_part(m, poff)
            if nid in npc_lots:
                for l in npc_lots[nid]:
                    placed[l].append(rec)
        # 3) treasure events
        for off, _n in m.entries("EVENT_PARAM_ST"):
            if m.i32(off + EV_TYPE) != EVENT_TYPE_TREASURE:
                continue
            lot = m.i32(off + m.i64(off + EV_TYPEDATA_PTR) + TD_ITEM_LOT)
            if lot and lot > 0:
                idx = m.i32(off + m.i64(off + EV_TYPEDATA_PTR) + TD_PART_INDEX)
                if 0 <= idx < len(part_offsets):
                    p = place(aa, bb, cc, *m.vec3(part_offsets[idx] + PART_POSITION),
                              conv, tier=tier)
                    if p is not None:
                        placed[lot].append({"px": round(p[0], 1), "py": round(p[1], 1),
                                            "h": round(p[3]), "master": p[2], "map": mid})
    print("scanned parts: %d ; referenced lots now: %d" % (parts, len(placed)))

    out = []
    new_names = set()
    dupes = 0
    for lot, ms in sorted(placed.items()):
        for k in range(1, MAX_FOLLOW + 1):
            items = lots.get(lot + k)
            if not items:
                break      # the documented chain stops at the first missing row

            src = ms[0]
            iid, kind, _num = items[0]
            nm = name_of(iid, kind)
            if not nm:
                continue
            key = (nm, round(src["px"]), round(src["py"]))
            if key in existing:
                dupes += 1
                continue
            existing.add(key)
            new_names.add(nm)
            out.append({
                "id": "follow:%d:%d" % (lot, lot + k),
                "cat": ladder_cat(nm) or DROP_CAT.get(kind, "drop_items"),
                "names": {"zh": nm, "en": nm},
                "flag": None, "lot": lot + k, "parentLot": lot,
                "master": src.get("master"), "px": src["px"], "py": src["py"],
                "h": src.get("h", 0), "map": src.get("map"), "via": "sequent-lot",
            })
    with io.open(os.path.join(ROOT, "data", "followup.json"), "w", encoding="utf-8") as f:
        json.dump({"locales": ["zh", "en"], "markers": out}, f, ensure_ascii=False)
    print("new markers: %d (dupes %d), new items: %d" % (len(out), dupes, len(new_names)))
    glove = sorted(n for n in new_names if "铃兰" in n)
    print("glovewort added (%d): %s" % (len(glove), glove))
    for n in glove:
        cats = sorted({mk["cat"] for mk in out if mk["names"]["zh"] == n})
        print("   %s -> %s" % (n, cats))
    dvd.close()


if __name__ == "__main__":
    main()
