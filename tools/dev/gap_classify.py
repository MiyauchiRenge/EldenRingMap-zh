"""Classify the remaining save-vs-map gaps by evidence, not by hiding them.

The flag-based check (world_gaps.py) reports lots whose flag is set in the player's save and
which some world object references, yet which have no marker. This script decides, per item,
whether it is a *player-visible pickup that is missing* (a real gap) or something that cannot
have a world position / is not a pickup at all:

  * no name in any locale   -> internal id, not a visible pickup
  * quest/reward style name -> granted by story, no world pickup
  * otherwise               -> REAL GAP (must be fixed)

Usage: python tools/dev/gap_classify.py [report]
"""
from __future__ import annotations

import io
import os
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, os.path.dirname(HERE))
sys.path.insert(0, HERE)
from erlib import fmg, oodle, param, paramdef        # noqa: E402
import erlib.modfiles as modfiles                     # noqa: E402
from erlib.dvdbnd import DvdBnd                       # noqa: E402
from erlib.gamepath import require_game_dir           # noqa: E402

ROOT = os.path.dirname(os.path.dirname(HERE))
TAB = {1: "GoodsName", 2: "WeaponName", 3: "ProtectorName", 4: "AccessoryName", 5: "GemName"}
QUEST = ("修复卢恩", "大卢恩", "钥匙", "符节", "铃珠", "灵马", "召魂", "记忆石", "地图")


def main():
    report = sys.argv[1] if len(sys.argv) > 1 else os.path.join(ROOT, "_world_gaps.txt")
    rows = []
    inside = False
    for line in io.open(report, encoding="utf-8"):
        if line.startswith("== TRUE GAPS"):
            inside = True
            continue
        if line.startswith("== NO WORLD"):
            inside = False
        if inside and line.startswith("flag "):
            p = line.split()
            rows.append((int(p[1]), int(p[3])))
    print("gaps examined: %d (%s)" % (len(rows), report))
    if not rows:
        return
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
        for t in [TAB.get(kind, "")] + list(TAB.values()):
            v = (names.get(t) or {}).get(iid, "") if t else ""
            if v and "[ERROR]" not in v:
                return v
        return ""

    real, explained = [], []
    for flag, lot in rows:
        row = None
        for t in ("ItemLotParam_map", "ItemLotParam_enemy"):
            for r in params[t].rows:
                if r.id == lot:
                    row = (t, r)
                    break
            if row:
                break
        if row is None:
            explained.append((flag, lot, "lot not in ItemLotParam"))
            continue
        _t, r = row
        iid = kind = 0
        for i in range(1, 9):
            v = ld.get(r.data, "lotItemId%02d" % i)
            if v:
                iid, kind = v, ld.get(r.data, "lotItemCategory%02d" % i)
                break
        nm = name_of(iid, kind)
        if not nm:
            explained.append((flag, lot, "item %d has no name in any locale (internal id)" % iid))
        elif any(q in nm for q in QUEST):
            explained.append((flag, lot, "not a world pickup (quest/reward): %s" % nm))
        else:
            real.append((flag, lot, nm))
    print("REAL GAPS (player-visible pickup with no marker): %d" % len(real))
    for f, l, nm in real:
        print("   flag %-12d lot %-12d %s" % (f, l, nm))
    print("explained (cannot have a world position): %d" % len(explained))
    for f, l, why in explained:
        print("   flag %-12d lot %-12d %s" % (f, l, why))
    out = os.path.join(ROOT, "_gap_classification.txt")
    with io.open(out, "w", encoding="utf-8") as fh:
        fh.write("REAL GAPS: %d\n" % len(real))
        for f, l, nm in real:
            fh.write("  flag %d lot %d %s\n" % (f, l, nm))
        fh.write("explained: %d\n" % len(explained))
        for f, l, why in explained:
            fh.write("  flag %d lot %d %s\n" % (f, l, why))
    print("report: %s" % out)
    dvd.close()


if __name__ == "__main__":
    main()
