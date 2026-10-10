"""Place each merchant's bell bearing at that merchant's own coordinates (post-processing).

A merchant's NpcParam names the lot it drops (itemLotId_map / itemLotId_enemy), and that lot's item
is the merchant's bell bearing. data/drops.json had one bearing attached to the wrong merchant, so
this rewrites the bearing markers from the merchant rows: authoritative, re-runnable, and it
cross-checks the other nineteen.
"""
import io
import json
import os
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, os.path.dirname(HERE))
ROOT = os.path.dirname(os.path.dirname(HERE))
from erlib import fmg, oodle, param, paramdef      # noqa: E402
import erlib.modfiles as modfiles                   # noqa: E402
from erlib.dvdbnd import DvdBnd                     # noqa: E402
from erlib.gamepath import require_game_dir         # noqa: E402


def main():
    game = require_game_dir(None)
    mod = modfiles.find_mod_dir(None)
    dvd = DvdBnd(game, cache_dir=os.path.join(ROOT, "cache"), verbose=False)
    helper = oodle.make_helper(game)
    params = param.load_params(modfiles.regulation_path(game, mod))
    nd = paramdef.load(os.path.join(ROOT, "data", "paramdefs", "NpcParam.xml"))
    ld = paramdef.load(os.path.join(ROOT, "data", "paramdefs", "ItemLotParam.xml"))
    texts = {}
    for f in ("item.msgbnd.dcx", "item_dlc02.msgbnd.dcx"):
        p = "/msg/zhocn/%s" % f
        if modfiles.has(dvd, mod, p):
            for k, v in fmg.load_msgbnd(modfiles.read(dvd, mod, p), oodle=helper).items():
                texts.setdefault(k.split("_dlc")[0], {}).update(v)
    dvd.close()

    rows = {r.id: r for r in params["NpcParam"].rows}
    lots = {}
    for tbl in ("ItemLotParam_map", "ItemLotParam_enemy"):
        for r in params[tbl].rows:
            for i in range(1, 9):
                iid = ld.get(r.data, "lotItemId%02d" % i)
                if iid:
                    lots[r.id] = iid
                    break
    npcs = json.load(io.open(os.path.join(ROOT, "data", "npcs.json"), encoding="utf-8"))
    drops_p = os.path.join(ROOT, "data", "drops.json")
    drops = json.load(io.open(drops_p, encoding="utf-8"))
    by_name = {}
    for m in drops["markers"]:
        zh = (m.get("names") or {}).get("zh", "")
        if "铃珠" in zh:
            by_name.setdefault(zh, m)

    fixed = added = 0
    bell_owner = {}
    for m in npcs["markers"]:
        r = rows.get(m.get("npcParam"))
        if r is None:
            continue
        lot = None
        for field in ("itemLotId_map", "itemLotId_enemy"):
            v = nd.get(r.data, field)
            if v and v > 0:
                lot = v
                break
        if not lot or lot not in lots:
            continue
        iid = lots[lot]
        zh = (texts.get("GoodsName") or {}).get(iid, "")
        if "铃珠" not in zh:
            continue
        m["dropsBell"], m["dropsBellPx"] = zh, 0.0
        owner = bell_owner.get(zh)
        if owner is not None:
            # The game reuses one NpcParam row for several stalls, so the bearing exists once.
            # Record the other stalls on the marker instead of duplicating the bearing.
            owner.setdefault("sharedWith", [])
            if m["names"]["zh"] not in owner["sharedWith"]:
                owner["sharedWith"].append(m["names"]["zh"])
            m["dropsBell"], m["dropsBellPx"] = zh, 0.0
            continue
        mk = by_name.get(zh)
        if mk is None:
            mk = {"id": "bell:%d" % lot, "cat": "drop_bell_bearings",
                  "names": {"zh": zh, "en": zh}, "flag": None, "lot": lot, "item": iid,
                  "master": m.get("master"), "px": m["px"], "py": m["py"], "h": m.get("h"),
                  "map": m.get("map"), "via": "bell-owner"}
            drops["markers"].append(mk)
            by_name[zh] = mk
            bell_owner[zh] = mk
            added += 1
        else:
            moved = (mk.get("px"), mk.get("py")) != (m["px"], m["py"])
            mk.update({"master": m.get("master"), "px": m["px"], "py": m["py"], "h": m.get("h"),
                       "map": m.get("map"), "via": "bell-owner"})
            bell_owner[zh] = mk
            if moved:
                fixed += 1
    io.open(drops_p, "w", encoding="utf-8").write(json.dumps(drops, ensure_ascii=False))
    io.open(os.path.join(ROOT, "data", "npcs.json"), "w",
            encoding="utf-8").write(json.dumps(npcs, ensure_ascii=False))
    print("bell bearings repositioned: %d ; added: %d" % (fixed, added))
    for m in npcs["markers"]:
        print("   %-38s -> %-22s (%.1f,%.1f)" % (m["names"]["zh"], m.get("dropsBell") or "-",
                                                 m["px"], m["py"]))


if __name__ == "__main__":
    main()
