"""Gatherables: the pickups we never read, because their lot lives in the part's +0x260 field.

extract_items.py only ever followed treasure events and NpcParam drop fields, so every
gatherable wired through the part field (fireflies, butterflies, mushrooms, bones, leaves...)
was invisible. The player's save proves it: 20 items they had taken were referenced by a world
object yet had no marker.

This walks every part of every map, reads +0x260, resolves that lot's first item (with the
[ERROR] placeholder guard and table fallback), projects the part position, and emits a marker
carrying the lot's getItemFlagId - which is what makes the save check able to reach zero.

Output: data/gatherables.json (generated, never published).
"""
from __future__ import annotations

import io
import json
import os
import re
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)
from erlib import dcx, fmg, msb as msblib, oodle, param, paramdef     # noqa: E402
import erlib.modfiles as modfiles                                     # noqa: E402
from erlib.dvdbnd import DvdBnd                                       # noqa: E402
from erlib.gamepath import require_game_dir                           # noqa: E402
from build_markers import LegacyConv, place                           # noqa: E402
from erlib import emevd                                               # noqa: E402

ROOT = os.path.dirname(HERE)
GATHER_FIELD = 0x260
TABLE_OF_KIND = {1: "GoodsName", 2: "WeaponName", 3: "ProtectorName",
                 4: "AccessoryName", 5: "GemName"}
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
                    items.append((iid, ld.get(r.data, "lotItemCategory%02d" % i)))
            if items:
                lots[r.id] = (items, ld.get(r.data, "getItemFlagId"))
    print("lots with items: %d" % len(lots))

    map_ids = [l.split("\t")[0] for l in open(os.path.join(ROOT, "cache", "map-list.txt"),
                                             encoding="utf-8") if l.strip()]
    markers = []
    seen_key = set()
    parts = skipped_no_pos = skipped_no_name = 0
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
        for poff, _n in m.entries("PARTS_PARAM_ST"):
            parts += 1
            try:
                lot = m.i32(poff + GATHER_FIELD)
            except Exception:
                continue
            if not lot or lot <= 0 or lot not in lots:
                continue
            items, flag = lots[lot]
            iid, kind = items[0]
            nm = name_of(iid, kind)
            if not nm:
                skipped_no_name += 1
                continue
            p = place(aa, bb, cc, *m.vec3(poff + emevd.PART_POSITION), conv, tier=tier)
            if p is None:
                skipped_no_pos += 1
                continue
            key = (nm, round(p[0]), round(p[1]))
            if key in seen_key:
                continue
            seen_key.add(key)
            markers.append({
                "id": "gather:%s:%d:%d" % (mid, poff, lot),
                "cat": ladder_cat(nm) or "gathering",
                "names": {"zh": nm, "en": nm},
                "flag": flag or None,
                "lot": lot,
                "master": p[2],
                "px": round(p[0], 1), "py": round(p[1], 1), "h": round(p[3]),
                "map": mid, "via": "gather-field",
            })
    with io.open(os.path.join(ROOT, "data", "gatherables.json"), "w", encoding="utf-8") as f:
        json.dump({"locales": ["zh", "en"], "markers": markers}, f, ensure_ascii=False)
    print("scanned parts %d" % parts)
    print("gatherable markers: %d (no name %d, no position %d)"
          % (len(markers), skipped_no_name, skipped_no_pos))
    with_flag = sum(1 for m in markers if m["flag"])
    print("carrying a flag: %d" % with_flag)
    dvd.close()


if __name__ == "__main__":
    main()
