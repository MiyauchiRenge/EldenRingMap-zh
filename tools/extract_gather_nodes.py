"""Gather nodes: the real gatherable layer, from AssetEnvironmentGeometryParam.

Mechanism (verified against the live save, format facts only):
  * AssetEnvironmentGeometryParam row id is the AEG id ("AEGxxx_yyy" = xxx*1000 + yyy);
  * its field at +0xB8 is pickUpItemLotParamId - the lot the node awards. Confirmed on real
    rows: 99930 -> lot 999300 -> 10910 灵依墓地铃兰【１】; 99935 -> 999350 -> 10915 灵依【６】;
    99852 -> 998520 -> 蚁酸石; 998000 -> 蜕生蝶; 998010 -> 艾奥尼亚蝶; 998200 -> 黄金百足.
  * the world position comes from the MSB asset part whose name is AEG{xxx}_{yyy}_{instance}.

So every pickable node in the game can be enumerated from the game files alone - no save needed.
The save's FOEG block is only used later as verification.

Output: data/gather-nodes.json (generated, never published).
"""
from __future__ import annotations

import io
import json
import os
import re
import struct
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)
from erlib import dcx, fmg, msb as msblib, oodle, param, paramdef      # noqa: E402
import erlib.modfiles as modfiles                                       # noqa: E402
from erlib.dvdbnd import DvdBnd                                         # noqa: E402
from erlib.gamepath import require_game_dir                             # noqa: E402
from build_markers import LegacyConv, place                             # noqa: E402

ROOT = os.path.dirname(HERE)
PICKUP_FIELD = 0xB8
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

    # Child tiles: WorldMapLegacyConvParam rows whose destination is another map give that
    # tile's origin inside the source (parent) frame, e.g. m10_01_00 sits at (-514, 28, 200)
    # in m10_00_00. place() only understands the source side, so such parts are moved into the
    # parent frame first: p_parent = p_local + (srcPosX, srcPosY, srcPosZ).
    cvd = paramdef.load(os.path.join(ROOT, "data", "paramdefs", "WorldMapLegacyConvParam.xml"))
    PARENT_FRAME = {}
    for r in params["WorldMapLegacyConvParam"].rows:
        sa, sx, sz = cvd.get(r.data, "srcAreaNo"), cvd.get(r.data, "srcGridXNo"), cvd.get(r.data, "srcGridZNo")
        da, dx, dz = cvd.get(r.data, "dstAreaNo"), cvd.get(r.data, "dstGridXNo"), cvd.get(r.data, "dstGridZNo")
        if (da, dx, dz) != (sa, sx, sz) and sa:
            PARENT_FRAME[(da, dx, dz)] = (sa, sx, sz,
                                          cvd.get(r.data, "srcPosX"),
                                          cvd.get(r.data, "srcPosY"),
                                          cvd.get(r.data, "srcPosZ"))
    print("parent-frame rows: %d ; m10_01 present: %s"
          % (len(PARENT_FRAME), (10, 1, 0) in PARENT_FRAME))
    names = {}
    for f in ("item.msgbnd.dcx", "item_dlc02.msgbnd.dcx"):
        p = "/msg/zhocn/%s" % f
        if modfiles.has(dvd, mod, p):
            for k, v in fmg.load_msgbnd(modfiles.read(dvd, mod, p), oodle=helper).items():
                names.setdefault(k.split("_dlc")[0], {}).update(v)

    # GATHER_ICON: the item's own icon, from the same source items.json uses.
    _goods = params.get("EquipParamGoods")
    _gdef = None
    try:
        _gdef = paramdef.load(os.path.join(ROOT, "data", "paramdefs", "EquipParamGoods.xml"))
    except Exception:
        _gdef = None
    _by_id = {r.id: r for r in _goods.rows} if _goods else {}

    def icon_of(iid):
        r = _by_id.get(iid)
        if r is None:
            return None
        try:
            if _gdef is not None:
                return _gdef.get(r.data, "iconId") or None
        except Exception:
            pass
        raw = bytes(r.data)
        if len(raw) >= 0x34:
            import struct as _st
            return _st.unpack_from("<H", raw, 0x30)[0] or None
        return None

    def item_name(iid, kind):
        for t in [TABLE_OF_KIND.get(kind, "")] + ["GoodsName", "WeaponName", "ProtectorName",
                                                  "AccessoryName", "GemName"]:
            v = (names.get(t) or {}).get(iid, "") if t else ""
            if v and "[ERROR]" not in v:
                return v
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
                lots[r.id] = (items, ld.get(r.data, "getItemFlagId"))

    aeg = params["AssetEnvironmentGeometryParam"]
    kinds = {}
    for r in aeg.rows:
        raw = bytes(r.data)
        if len(raw) < PICKUP_FIELD + 4:
            continue
        lot = struct.unpack_from("<I", raw, PICKUP_FIELD)[0]
        if lot in lots:
            kinds[r.id] = lot
    print("AssetEnvironmentGeometryParam rows: %d ; rows with a pickUp lot at +0xB8: %d"
          % (len(aeg.rows), len(kinds)))
    if not kinds:
        dvd.close()
        return
    prefix = {}
    for aegid, lot in kinds.items():
        prefix["AEG%03d_%03d" % (aegid // 1000, aegid % 1000)] = (aegid, lot)

    maps = [l.split("\t")[0] for l in open(os.path.join(ROOT, "cache", "map-list.txt"),
                                          encoding="utf-8") if l.strip()]
    markers = []
    seen = set()
    scanned_maps = scanned_parts = no_pos = named = 0
    for mid in maps:
        path = "/map/mapstudio/%s.msb.dcx" % mid
        if not modfiles.has(dvd, mod, path):
            continue
        try:
            m = msblib.load(dcx.decompress(modfiles.read(dvd, mod, path), oodle=helper))
        except Exception:
            continue
        scanned_maps += 1
        aa, bb, cc = int(mid[1:3]), int(mid[4:6]), int(mid[7:9])
        tier = int(mid[10:12]) if aa in (60, 61) else 0
        for poff, nm in m.entries("PARTS_PARAM_ST"):
            scanned_parts += 1
            s = str(nm)
            aegid = lot = None
            for pref, (aid, lt) in prefix.items():
                if s.startswith(pref + "_"):
                    aegid, lot = aid, lt
                    break
            if aegid is None:
                continue
            items, flag = lots[lot]
            iid, kind, num = items[0]
            nmz = item_name(iid, kind)
            if not nmz:
                named += 1
                continue
            vx, vy, vz = m.vec3(poff + 0x20)
            # Same rule as extract_items.place2(): shift into the parent frame only when place()
            # cannot project the tile as-is (m10_01_00 and friends). Shifting everything moved
            # otherwise-correct markers, so it must stay the fallback.
            p = place(aa, bb, cc, vx, vy, vz, conv, tier=tier)
            if p is None and (aa, bb, cc) in PARENT_FRAME:
                sa, sx, sz, ox, oy, oz = PARENT_FRAME[(aa, bb, cc)]
                p = place(sa, sx, sz, vx + ox, vy + oy, vz + oz, conv, tier=0)
            if p is None:
                no_pos += 1
                continue
            key = (s, mid)
            if key in seen:
                continue
            seen.add(key)
            markers.append({
                # Part names repeat inside a map (MSB allows it), so the offset is part of the id;
                # otherwise distinct parts collapse onto one id and the UI shows duplicates.
                "id": "gather:%s:%s:%d" % (mid, s, poff),
                "cat": ladder_cat(nmz) or ("gather_%d" % iid),
                "iconId": icon_of(iid),
                "names": {"zh": nmz, "en": nmz},
                "flag": flag or None, "lot": lot, "item": iid,
                "master": p[2], "px": round(p[0], 1), "py": round(p[1], 1), "h": round(p[3]),
                "map": mid, "part": s, "aeg": aegid, "via": "aeg-node",
            })
    with io.open(os.path.join(ROOT, "data", "gather-nodes.json"), "w", encoding="utf-8") as fh:
        json.dump({"locales": ["zh", "en"], "markers": markers}, fh, ensure_ascii=False)
    print("scanned maps %d, parts %d" % (scanned_maps, scanned_parts))
    print("gather nodes: %d (no name %d, no position %d)" % (len(markers), named, no_pos))
    print("distinct items: %d" % len({m["item"] for m in markers}))
    import collections
    top = collections.Counter(m["names"]["zh"] for m in markers).most_common(12)
    print("top items: %s" % top)
    dvd.close()


if __name__ == "__main__":
    main()
