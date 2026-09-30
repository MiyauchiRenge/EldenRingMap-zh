"""Why are these 19 lots missing? For each, find which world path references it and whether
that reference has a position.

Paths: a part's +0x260 gatherable field, an NpcParam's itemLotId_enemy/_map (via the parts
carrying that NPC), a treasure event's lot. For each gap lot we print every reference found,
with map and position (or "no placement"), so the cause is visible rather than guessed.
"""
from __future__ import annotations

import glob
import io
import json
import os
import sys
from collections import defaultdict

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, os.path.dirname(HERE))
sys.path.insert(0, HERE)
from erlib import dcx, emevd, fmg, msb as msblib, oodle, param, paramdef   # noqa: E402
import erlib.modfiles as modfiles                                          # noqa: E402
from erlib.dvdbnd import DvdBnd                                            # noqa: E402
from erlib.gamepath import require_game_dir                                # noqa: E402
from build_markers import LegacyConv, place                                # noqa: E402
from extract_items import (EV_TYPE, EV_TYPEDATA_PTR, TD_ITEM_LOT, TD_PART_INDEX,  # noqa: E402
                           PART_POSITION, EVENT_TYPE_TREASURE)
import er_save                                                             # noqa: E402

ROOT = os.path.dirname(os.path.dirname(HERE))
GATHER_FIELD = 0x260
TABLE_OF_KIND = {1: "GoodsName", 2: "WeaponName", 3: "ProtectorName",
                 4: "AccessoryName", 5: "GemName"}


def main():
    # the gap lots come from the report written by world_gaps.py
    rep = os.path.join(ROOT, "_world_gaps.txt")
    lots, flags = [], {}
    with io.open(rep, encoding="utf-8") as fh:
        in_gaps = False
        for line in fh:
            if line.startswith("== TRUE GAPS"):
                in_gaps = True
                continue
            if line.startswith("== NO WORLD"):
                in_gaps = False
            if in_gaps and line.startswith("flag "):
                parts = line.split()
                f, lot = int(parts[1]), int(parts[3])
                lots.append(lot)
                flags[lot] = f
    print("gap lots: %d" % len(lots))
    if not lots:
        return
    want = set(lots)

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

    npc_with_lot = {}
    for r in params["NpcParam"].rows:
        for field in ("itemLotId_enemy", "itemLotId_map"):
            v = nd.get(r.data, field)
            if v in want:
                npc_with_lot.setdefault(v, []).append(r.id)
    print("npc-referenced gap lots: %s" % {k: v[:3] for k, v in npc_with_lot.items()})

    refs = defaultdict(list)
    maps = [l.split("\t")[0] for l in open(os.path.join(ROOT, "cache", "map-list.txt"),
                                          encoding="utf-8") if l.strip()]
    for mid in maps:
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
            try:
                g = m.i32(poff + GATHER_FIELD)
            except Exception:
                g = 0
            if g in want:
                p = place(aa, bb, cc, *m.vec3(poff + PART_POSITION), conv, tier=tier)
                refs[g].append((mid, "part+0x260", (round(p[0]), round(p[1])) if p else None))
            nid = emevd.npc_id_of_part(m, poff)
            if nid in npc_with_lot:
                p = place(aa, bb, cc, *m.vec3(poff + PART_POSITION), conv, tier=tier)
                for lot in [v for v, ids in npc_with_lot.items() if nid in ids]:
                    refs[lot].append((mid, "npc %d placed" % nid,
                                      (round(p[0]), round(p[1])) if p else None))
        for off, _n in m.entries("EVENT_PARAM_ST"):
            if m.i32(off + EV_TYPE) != EVENT_TYPE_TREASURE:
                continue
            td = off + m.i64(off + EV_TYPEDATA_PTR)
            lot = m.i32(td + TD_ITEM_LOT)
            if lot in want:
                idx = m.i32(td + TD_PART_INDEX)
                ok = 0 <= idx < len(part_offsets)
                p = place(aa, bb, cc, *m.vec3(part_offsets[idx] + PART_POSITION), conv, tier=tier) \
                    if ok else None
                refs[lot].append((mid, "treasure idx %d%s" % (idx, "" if ok else " OUT-OF-RANGE"),
                                  (round(p[0]), round(p[1])) if p else None))
    out = os.path.join(ROOT, "_gap_causes.txt")
    with io.open(out, "w", encoding="utf-8") as fh:
        fh.write("gap lots: %d\n\n" % len(lots))
        for lot in lots:
            row = next((r for tbl in ("ItemLotParam_map", "ItemLotParam_enemy")
                        for r in params[tbl].rows if r.id == lot), None)
            item = ""
            if row is not None:
                for i in range(1, 9):
                    iid = ld.get(row.data, "lotItemId%02d" % i)
                    if iid:
                        t = TABLE_OF_KIND.get(ld.get(row.data, "lotItemCategory%02d" % i), "")
                        item = "%s (%s)" % (iid, t)
                        break
            fh.write("lot %-12d flag %-12d %s\n" % (lot, flags.get(lot, 0), item))
            rs = refs.get(lot) or []
            if not rs:
                fh.write("    no world reference found in the MSB sweep\n")
            for mid, how, pos in rs[:6]:
                fh.write("    %-18s %-24s %s\n" % (mid, how, pos))
            fh.write("    npc owners: %s\n\n" % (npc_with_lot.get(lot) or "none"))
    print("report: %s" % out)
    for lot in lots[:6]:
        print("lot %-12d refs=%d npc=%s" % (lot, len(refs.get(lot) or []),
                                            (npc_with_lot.get(lot) or [])[:3]))
    dvd.close()


if __name__ == "__main__":
    main()
