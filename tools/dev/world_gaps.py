"""True gaps: flags the player has set whose lot IS referenced by a world object, yet our map
has no marker for it.

The plain save check (verify_with_save.py) lists 72 items, but most are quest rewards, starting
kit and boss-granted Great Runes - things that legitimately have no world position. This tool
adds the missing filter: only lots that some map object actually references (a part's +0x260
gatherable field, an NpcParam drop field, or a treasure event) can be a marker we failed to
emit. Anything else is reported separately as "no world position".

Output: UTF-8 report at _world_gaps.txt.
"""
from __future__ import annotations

import glob
import io
import json
import os
import sys
import traceback
from collections import defaultdict

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, os.path.dirname(HERE))
sys.path.insert(0, HERE)
from erlib import dcx, emevd, fmg, msb as msblib, oodle, param, paramdef   # noqa: E402
import erlib.modfiles as modfiles                                          # noqa: E402
from erlib.dvdbnd import DvdBnd                                            # noqa: E402
from erlib.gamepath import require_game_dir                                # noqa: E402
from extract_items import (EV_TYPE, EV_TYPEDATA_PTR, TD_ITEM_LOT,          # noqa: E402
                           EVENT_TYPE_TREASURE)
import er_save                                                             # noqa: E402

ROOT = os.path.dirname(os.path.dirname(HERE))
GATHER_FIELD = 0x260
TABLE_OF_KIND = {1: "GoodsName", 2: "WeaponName", 3: "ProtectorName",
                 4: "AccessoryName", 5: "GemName"}
DATA_FILES = ("items.json", "drops.json", "boss-drops.json", "farm.json",
              "emevd-drops.json", "followup.json", "gatherables.json", "npcs.json", "markers.json")


def main():
    cands = glob.glob(os.path.join(os.environ.get("APPDATA", ""), "EldenRing", "*", "ER0000.sl2"))
    save = cands[0] if cands else None
    if not save:
        sys.exit("no save found")
    data = io.open(save, "rb").read()
    groups = er_save.load_flag_groups(os.path.join(ROOT, "data", "eventflag_bst.txt"))
    flags = er_save.EventFlags(er_save.slot_payload(data, 0), groups)
    print("save: %s" % save)

    game = require_game_dir(None)
    mod = modfiles.find_mod_dir(None)
    dvd = DvdBnd(game, cache_dir=os.path.join(ROOT, "cache"), verbose=False)
    helper = oodle.make_helper(game)
    params = param.load_params(modfiles.regulation_path(game, mod))
    ld = paramdef.load(os.path.join(ROOT, "data", "paramdefs", "ItemLotParam.xml"))
    nd = paramdef.load(os.path.join(ROOT, "data", "paramdefs", "NpcParam.xml"))
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

    # world-referenced lots
    # NPC lot fields only count if that NPC is actually placed in some map (parts are swept
    # below); otherwise a quest/starting grant with no world position looks like a pickup.
    npc_lot = {}
    for r in params["NpcParam"].rows:
        for field in ("itemLotId_enemy", "itemLotId_map"):
            v = nd.get(r.data, field)
            if v and v > 0:
                npc_lot.setdefault(r.id, set()).add(v)
    world = set()
    placed_npcs = set()
    maps = [l.split("\t")[0] for l in open(os.path.join(ROOT, "cache", "map-list.txt"),
                                          encoding="utf-8") if l.strip()]
    parts = treasures = 0
    for mid in maps:
        path = "/map/mapstudio/%s.msb.dcx" % mid
        if not modfiles.has(dvd, mod, path):
            continue
        try:
            m = msblib.load(dcx.decompress(modfiles.read(dvd, mod, path), oodle=helper))
        except Exception:
            continue
        for poff, _n in m.entries("PARTS_PARAM_ST"):
            parts += 1
            nid = emevd.npc_id_of_part(m, poff)
            if nid:
                placed_npcs.add(nid)
            try:
                v = m.i32(poff + GATHER_FIELD)
            except Exception:
                continue
            if v and v > 0:
                world.add(v)
        for off, _n in m.entries("EVENT_PARAM_ST"):
            if m.i32(off + EV_TYPE) != EVENT_TYPE_TREASURE:
                continue
            treasures += 1
            v = m.i32(off + m.i64(off + EV_TYPEDATA_PTR) + TD_ITEM_LOT)
            if v and v > 0:
                world.add(v)
    for nid in placed_npcs:
        world |= npc_lot.get(nid, set())
    print("scanned parts %d, treasure events %d -> placed npcs %d, world-referenced lots %d"
          % (parts, treasures, len(placed_npcs), len(world)))

    our_flags = {}
    our_lots = set()
    for f in DATA_FILES:
        p = os.path.join(ROOT, "data", f)
        if not os.path.isfile(p):
            continue
        for m in json.load(open(p, encoding="utf-8"))["markers"]:
            if m.get("flag"):
                our_flags.setdefault(m["flag"], m)
            if m.get("lot"):
                our_lots.add(m["lot"])

    def covered(flag, lot):
        """A gap only counts if neither the flag nor the lot is already on the map.

        Comparing by flag alone reported 15 items that DO have markers whose flag field is
        empty - a flaw in the check, not a gap in the data.
        """
        return flag in our_flags or lot in our_lots

    flag_lot = {}
    for tbl in ("ItemLotParam_map", "ItemLotParam_enemy"):
        for r in params[tbl].rows:
            f = ld.get(r.data, "getItemFlagId")
            if not f:
                continue
            for i in range(1, 9):
                if ld.get(r.data, "lotItemCategory%02d" % i) == -1:
                    continue
                iid = ld.get(r.data, "lotItemId%02d" % i)
                if iid:
                    flag_lot.setdefault(f, (r.id, name_of(iid, ld.get(r.data, "lotItemCategory%02d" % i)),
                                            ld.get(r.data, "lotItemCategory%02d" % i)))
                    break

    true_gaps, no_world = [], []
    for f, (lot, nm, kind) in sorted(flag_lot.items()):
        try:
            if not flags.get(f):
                continue
        except Exception:
            continue
        if covered(f, lot):
            continue
        (true_gaps if lot in world else no_world).append((f, lot, nm, kind))
    out = os.path.join(ROOT, "_world_gaps.txt")
    with io.open(out, "w", encoding="utf-8") as fh:
        fh.write("save: %s\n" % save)
        fh.write("world-referenced lots: %d\n" % len(world))
        fh.write("flags set and unmarked: %d  ->  referenced by a world object: %d ; no world position: %d\n\n"
                 % (len(true_gaps) + len(no_world), len(true_gaps), len(no_world)))
        fh.write("== TRUE GAPS (world object exists, marker missing) ==\n")
        for f, lot, nm, kind in true_gaps:
            fh.write("flag %-12d lot %-12d kind %-2d %s\n" % (f, lot, kind, nm or "(no name)"))
        fh.write("\n== NO WORLD POSITION (quest/starting/boss-granted) ==\n")
        for f, lot, nm, kind in no_world:
            fh.write("flag %-12d lot %-12d kind %-2d %s\n" % (f, lot, kind, nm or "(no name)"))
    print("true gaps: %d ; no world position: %d" % (len(true_gaps), len(no_world)))
    print("report: %s" % out)
    print("first true gaps: %s" % [(f, lot) for f, lot, _n, _k in true_gaps[:10]])
    dvd.close()


if __name__ == "__main__":
    main()
