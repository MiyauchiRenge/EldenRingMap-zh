"""Event-granted collectibles: lots awarded by a map's EMEVD instead of by a chest.

Found this session: the Scadutree Fragment lots 2047390070 / 2051440500 / 2051440510 appear only in
the parameter section of m61_47_39_00 and m61_51_44_00 - map events, i.e. boss kills - so they had
no marker at all.

This scans every map's EMEVD parameter section for lots that award a one-time collectible and that
NO other mechanism references (the definition of "we were missing it"), then anchors a marker at
the map's boss marker if one exists (that is where the fragment comes from), else at the map's
first grace marker. If neither exists the point is reported as unplaceable rather than invented.

Output: data/emevd-rewards.json
"""
from __future__ import annotations

import io
import json
import os
import struct
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)
from erlib import dcx, emevd, fmg, oodle, param, paramdef      # noqa: E402
import erlib.modfiles as modfiles                               # noqa: E402
from erlib.dvdbnd import DvdBnd                                 # noqa: E402
from erlib.gamepath import require_game_dir                     # noqa: E402
from build_markers import LegacyConv, place                    # noqa: E402

ROOT = os.path.dirname(HERE)
TABLE_OF_KIND = {1: "GoodsName", 2: "WeaponName", 3: "ProtectorName",
                 4: "AccessoryName", 5: "GemName"}
# categories of interest: the one-time collectibles that scripts hand out
WANTED_CAT = {
    2010000: "scadutree_fragments",     # 幽影树碎片
    2010100: "spirit_blessing",         # 灵灰（Revered Spirit Ash）
}


def main():
    game = require_game_dir(None)
    mod = modfiles.find_mod_dir(None)
    dvd = DvdBnd(game, cache_dir=os.path.join(ROOT, "cache"), verbose=False)
    helper = oodle.make_helper(game)
    params = param.load_params(modfiles.regulation_path(game, mod))
    ld = paramdef.load(os.path.join(ROOT, "data", "paramdefs", "ItemLotParam.xml"))
    names = {}
    for f in ("item.msgbnd.dcx", "item_dlc02.msgbnd.dcx"):
        p = "/msg/zhocn/%s" % f
        if modfiles.has(dvd, mod, p):
            for k, v in fmg.load_msgbnd(modfiles.read(dvd, mod, p), oodle=helper).items():
                names.setdefault(k.split("_dlc")[0], {}).update(v)

    def name_of(iid, kind):
        for t in [TABLE_OF_KIND.get(kind, "")] + list(TABLE_OF_KIND.values()):
            v = (names.get(t) or {}).get(iid, "") if t else ""
            if v and "[ERROR]" not in v:
                return v
        return ""

    # lots awarding a collectible of interest
    lots = {}
    for tbl in ("ItemLotParam_map", "ItemLotParam_enemy"):
        for r in params[tbl].rows:
            for i in range(1, 9):
                if ld.get(r.data, "lotItemCategory%02d" % i) != 1:
                    continue
                iid = ld.get(r.data, "lotItemId%02d" % i)
                if iid in WANTED_CAT:
                    lots[r.id] = (iid, WANTED_CAT[iid], name_of(iid, 1))
                    break
    print("lots awarding a script-granted collectible: %d" % len(lots))
    if not lots:
        dvd.close()
        return

    # which are already covered elsewhere? (treasure / AEG / placed npc)
    covered = set()
    aeg = params["AssetEnvironmentGeometryParam"]
    for r in aeg.rows:
        raw = bytes(r.data)
        if len(raw) > 0xBB:
            v = struct.unpack_from("<I", raw, 0xB8)[0]
            if v in lots:
                covered.add(v)
    nd = paramdef.load(os.path.join(ROOT, "data", "paramdefs", "NpcParam.xml"))
    for r in params["NpcParam"].rows:
        for field in ("itemLotId_enemy", "itemLotId_map"):
            v = nd.get(r.data, field)
            if v in lots:
                covered.add(v)
    for f in ("items.json", "emevd-drops.json", "boss-drops.json"):
        p = os.path.join(ROOT, "data", f)
        if os.path.isfile(p):
            for m in json.load(io.open(p, encoding="utf-8")).get("markers") or []:
                if m.get("lot"):
                    covered.add(m["lot"])
    print("already covered by another mechanism: %d ; left for EMEVD events: %d"
          % (len(covered & set(lots)), len(set(lots) - covered)))

    maps = [l.split("\t")[0] for l in open(os.path.join(ROOT, "cache", "map-list.txt"),
                                          encoding="utf-8") if l.strip()]
    # Grace fallback: real in-game coordinates from BonfireWarpParam (see build_markers.py),
    # used when a map has no boss/grace marker of its own.
    WARP_ANCHORS = {}
    try:
        wd = paramdef.load(os.path.join(ROOT, "data", "paramdefs", "BonfireWarpParam.xml"))
        conv = LegacyConv(params["WorldMapLegacyConvParam"].rows,
                          paramdef.load(os.path.join(ROOT, "data", "paramdefs",
                                                    "WorldMapLegacyConvParam.xml")))
        for r in params["BonfireWarpParam"].rows:
            v = wd.as_dict(r.data, ["eventflagId", "bonfireEntityId", "areaNo", "gridXNo",
                                    "gridZNo", "posX", "posY", "posZ", "textId1", "iconId"])
            if not v.get("areaNo"):
                continue
            q = place(v["areaNo"], v["gridXNo"], v["gridZNo"],
                      v["posX"], v["posY"], v["posZ"], conv)
            if q is None:
                continue
            key = "m%02d_%02d_%02d" % (v["areaNo"], v["gridXNo"], v["gridZNo"])
            WARP_ANCHORS.setdefault(key, {"master": q[2], "px": round(q[0], 1),
                                          "py": round(q[1], 1), "h": round(q[3]),
                                          "cat": "grace-warp"})
        print("warp (grace) anchors: %d maps" % len(WARP_ANCHORS))
    except Exception as e:
        print("warp anchors unavailable: %s" % e)

    anchors = {}
    for f, cat in (("boss-drops.json", "boss"), ("markers.json", "grace")):
        p = os.path.join(ROOT, "data", f)
        if not os.path.isfile(p):
            continue
        for m in json.load(io.open(p, encoding="utf-8")).get("markers") or []:
            mid = str(m.get("map") or "")
            if not mid:
                continue
            key = mid[:9]
            if key not in anchors or cat == "boss":
                anchors.setdefault(key, m)

    markers = []
    hit_maps = 0
    for mid in maps:
        path = "/event/%s.emevd.dcx" % mid
        if not modfiles.has(dvd, mod, path):
            continue
        try:
            raw = dcx.decompress(modfiles.read(dvd, mod, path), oodle=helper)
            if not emevd.is_emevd(raw):
                continue
            h = emevd.read_header(raw)
        except Exception:
            continue
        blob = raw[h["paramOffset"]:]
        n = len(blob) // 4
        words = struct.unpack_from("<%dI" % n, blob, 0)
        seen = set()
        for w in words:
            if w in lots and w not in seen and w not in covered:
                seen.add(w)
                iid, cat, nm = lots[w]
                a = anchors.get(mid[:9]) or WARP_ANCHORS.get(mid[:9])
                if a is None:
                    print("   %s lot %d (%s): no anchor marker in this map - not placed"
                          % (mid, w, nm))
                    continue
                markers.append({
                    "id": "emevd-reward:%s:%d" % (mid, w),
                    "cat": cat,
                    "names": {"zh": nm, "en": nm},
                    "flag": None, "lot": w, "item": iid,
                    "master": a.get("master"), "px": a.get("px"), "py": a.get("py"),
                    "h": a.get("h"),
                    "map": mid, "via": "emevd-reward",
                    "anchor": a.get("cat"),
                    "note": "由该地图事件脚本发放（Boss 击杀/事件）",
                })
        if seen:
            hit_maps += 1
    out = os.path.join(ROOT, "data", "emevd-rewards.json")
    io.open(out, "w", encoding="utf-8").write(
        json.dumps({"locales": ["zh", "en"], "markers": markers}, ensure_ascii=False))
    print("event-granted markers: %d from %d maps -> %s" % (len(markers), hit_maps, out))
    for m in markers[:8]:
        print("   %-16s %-18s px=%-8s py=%-8s anchor=%s" % (m["map"], m["names"]["zh"],
                                                            m["px"], m["py"], m.get("anchor")))
    dvd.close()


if __name__ == "__main__":
    main()
