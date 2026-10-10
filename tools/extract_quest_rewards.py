"""Script-granted items: register them, and anchor those we can place to a real grace.

These are items whose lot has a getItemFlagId that is SET in the player's save but which no world
object references (no chest, no gatherable node, no placed NPC, no farm spot). They are granted by
dialogue or by event scripts, so there is no world position - but the flag/lot number usually
carries the map, and BonfireWarpParam gives real coordinates for that map's graces.

Tier 2 in the plan: anchor to the grace of the map encoded in the lot, and say so on the marker.
Anything whose map cannot be derived is registered without a position (tier 3) rather than guessed.
Tier 1 (anchoring to the granting NPC) needs event -> entity -> part resolution and is not done.

Output: data/quest-rewards.json
"""
from __future__ import annotations

import io
import json
import os
import sys
from collections import Counter

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)
sys.path.insert(0, os.path.join(HERE, "dev"))
from erlib import fmg, oodle, param, paramdef           # noqa: E402
import erlib.modfiles as modfiles                        # noqa: E402
from erlib.dvdbnd import DvdBnd                          # noqa: E402
from erlib.gamepath import require_game_dir              # noqa: E402
from build_markers import LegacyConv, place              # noqa: E402
import er_save                                           # noqa: E402

ROOT = os.path.dirname(HERE)
LOCALES = ("zh", "en")
TABLE_OF_KIND = {1: "GoodsName", 2: "WeaponName", 3: "ProtectorName",
                 4: "AccessoryName", 5: "GemName"}
# categories that already exist in the UI
PROGRESSION = ("卢恩", "追忆", "钥匙", "符节", "铃珠", "地图", "记忆石", "灵马", "召魂")


def main():
    save = sys.argv[1] if len(sys.argv) > 1 else None
    if not save:
        import glob
        cands = glob.glob(os.path.join(os.environ.get("APPDATA", ""), "EldenRing", "*", "ER0000.sl2"))
        save = cands[0] if cands else None
    if not save or not os.path.isfile(save):
        sys.exit("no save found")
    print("save: %s" % save)

    data = io.open(save, "rb").read()
    groups = er_save.load_flag_groups(os.path.join(ROOT, "data", "eventflag_bst.txt"))
    best = None
    for idx in range(len(er_save.read_entries(data))):
        try:
            pay = er_save.slot_payload(data, idx)
            fl = er_save.EventFlags(pay, groups)
            n = sum(1 for _ in fl.iter_set())
        except Exception:
            continue
        if n and (best is None or n > best[0]):
            best = (n, idx, fl)
    if best is None:
        sys.exit("no non-empty slot")
    nflags, slot, flags = best
    print("slot %d (%d flags set)" % (slot, nflags))

    game = require_game_dir(None)
    mod = modfiles.find_mod_dir(None)
    dvd = DvdBnd(game, cache_dir=os.path.join(ROOT, "cache"), verbose=False)
    helper = oodle.make_helper(game)
    params = param.load_params(modfiles.regulation_path(game, mod))
    ld = paramdef.load(os.path.join(ROOT, "data", "paramdefs", "ItemLotParam.xml"))

    texts = {}
    for loc, tag in (("zh", "zhocn"), ("en", "engus")):
        t = {}
        for f in ("item.msgbnd.dcx", "item_dlc02.msgbnd.dcx"):
            p = "/msg/%s/%s" % (tag, f)
            if modfiles.has(dvd, mod, p):
                for k, v in fmg.load_msgbnd(modfiles.read(dvd, mod, p), oodle=helper).items():
                    t.setdefault(k.split("_dlc")[0], {}).update(v)
        texts[loc] = t

    def item_name(iid, kind, loc):
        tab = TABLE_OF_KIND
        for t in [tab.get(kind, "")] + list(tab.values()):
            v = (texts[loc].get(t) or {}).get(iid, "") if t else ""
            if v and "[ERROR]" not in v:
                return v
        return ""

    # lots already covered by another layer
    covered = set()
    for f in ("items.json", "drops.json", "boss-drops.json", "emevd-drops.json", "followup.json",
              "gather-nodes.json", "farm.json", "emevd-rewards.json"):
        p = os.path.join(ROOT, "data", f)
        if os.path.isfile(p):
            for m in json.load(io.open(p, encoding="utf-8")).get("markers") or []:
                if m.get("lot"):
                    covered.add(m["lot"])

    # grace anchors per area/grid prefix from BonfireWarpParam (real coordinates)
    wd = paramdef.load(os.path.join(ROOT, "data", "paramdefs", "BonfireWarpParam.xml"))
    conv = LegacyConv(params["WorldMapLegacyConvParam"].rows,
                      paramdef.load(os.path.join(ROOT, "data", "paramdefs",
                                                "WorldMapLegacyConvParam.xml")))
    anchors = {}
    for r in params["BonfireWarpParam"].rows:
        v = wd.as_dict(r.data, ["areaNo", "gridXNo", "gridZNo", "posX", "posY", "posZ", "textId1"])
        if not v.get("areaNo"):
            continue
        q = place(v["areaNo"], v["gridXNo"], v["gridZNo"], v["posX"], v["posY"], v["posZ"], conv)
        if q is None:
            continue
        key = "m%02d_%02d" % (v["areaNo"], v["gridXNo"])
        anchors.setdefault(key, {"master": q[2], "px": round(q[0], 1), "py": round(q[1], 1),
                                 "h": round(q[3])})
    print("grace anchors: %d area/grid prefixes" % len(anchors))

    markers = []
    unplaced_list = []
    unplaced = 0
    skip_reasons = {}
    samples = {}
    for tbl in ("ItemLotParam_map", "ItemLotParam_enemy"):
        for r in params[tbl].rows:
            flag = ld.get(r.data, "getItemFlagId")
            if not flag or not flags.get(flag) or r.id in covered:
                continue
            iid = kind = 0
            for i in range(1, 9):
                v = ld.get(r.data, "lotItemId%02d" % i)
                if v:
                    iid, kind = v, ld.get(r.data, "lotItemCategory%02d" % i)
                    break
            if not iid:
                continue
            zh = item_name(iid, kind, "zh")
            en = item_name(iid, kind, "en")
            if not zh and not en:
                unplaced += 1
                skip_reasons['no name'] = skip_reasons.get('no name', 0) + 1
                samples.setdefault('no name', []).append((r.id, iid, kind, tbl))
                continue
            # The map is encoded in the LOT (e.g. 12010690 -> m12_01); the flag is lot + 7000 for
            # map-scoped lots, so deriving the map from the flag does not work.
            key = "m%02d_%02d" % (r.id // 10000000 % 100, r.id // 100000 % 100)
            a = anchors.get(key)
            cat = "progression" if any(x in zh for x in PROGRESSION) else "misc"
            mk = {
                "id": "quest:%d" % r.id,
                "cat": cat,
                "names": {"zh": zh or en, "en": en or zh},
                "flag": flag, "lot": r.id, "item": iid,
                "via": "quest-flag",
                "note": "由任务或事件脚本给予",
            }
            if a:
                mk.update({"master": a["master"], "px": a["px"], "py": a["py"], "h": a["h"],
                           "anchor": "grace", "note": mk["note"] + "；位置为该地区赐福"})
            else:
                # No map in the lot number: a starting item or a quest/script grant with
                # no world object. Registered without coordinates instead of guessed.
                unplaced += 1
                skip_reasons['no anchor'] = skip_reasons.get('no anchor', 0) + 1
                samples.setdefault('no anchor', []).append((r.id, iid, kind, key))
                unplaced_list.append({
                    'id': 'quest-unplaced:%d' % r.id,
                    'cat': 'unplaced',
                    'names': {'zh': zh or en, 'en': en or zh},
                    'flag': flag, 'lot': r.id, 'item': iid,
                    'px': None, 'py': None, 'master': None,
                    'via': 'quest-flag',
                    'note': '由任务或脚本直接给予，没有世界物件，因此没有坐标',
                })
                continue
            markers.append(mk)
    out = os.path.join(ROOT, "data", "quest-rewards.json")
    io.open(out, "w", encoding="utf-8").write(
        json.dumps({"locales": ["zh", "en"], "markers": markers}, ensure_ascii=False))
    print("script-granted markers: %d (skipped, no anchor or no name: %d)" % (len(markers), unplaced))
    reg = os.path.join(ROOT, "data", "quest-rewards-unplaced.json")
    io.open(reg, "w", encoding="utf-8").write(
        json.dumps({"locales": ["zh", "en"], "markers": unplaced_list},
                   ensure_ascii=False))
    print("registered without position: %d -> %s" % (len(unplaced_list), reg))
    print("by category: %s" % dict(Counter(m["cat"] for m in markers).most_common()))
    print("skip reasons: %s" % skip_reasons)
    for why, rows in samples.items():
        print("   %s samples: %s" % (why, rows[:8]))
    for m in markers[:8]:
        print("   %-22s %-14s lot=%-10s flag=%-12s" % (m["names"]["zh"], m["cat"], m["lot"],
                                                       m["flag"]))
    dvd.close()


if __name__ == "__main__":
    main()
