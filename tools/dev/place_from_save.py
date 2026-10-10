"""Place a user-verified marker at the player's saved position.

Some gatherables (notably 灵依墓地铃兰【１】) have no readable world attachment: their lots carry
flag 0 and no map file references them, so neither our sweeps nor other tools can give a
position. But the player can stand on the spot and save - and the save stores the player's
position and map id. Projecting that position with LegacyConv puts the spot on our map.

Usage:
    python tools/dev/place_from_save.py [--save <ER0000.sl2>] --cat glovewort_ghost_1 \
        --zh "灵依墓地铃兰【１】" --note "位置由经存档核对"

The marker is appended to data/user-verified.json (local only; data/** is not published).
"""
from __future__ import annotations

import argparse
import glob
import io
import json
import os
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, os.path.dirname(HERE))
sys.path.insert(0, HERE)
from erlib import oodle, param, paramdef        # noqa: E402
import erlib.modfiles as modfiles                # noqa: E402
from erlib.dvdbnd import DvdBnd                  # noqa: E402
from erlib.gamepath import require_game_dir      # noqa: E402
from build_markers import LegacyConv, place      # noqa: E402
import er_save                                   # noqa: E402

ROOT = os.path.dirname(os.path.dirname(HERE))


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--save", default=None)
    ap.add_argument("--cat", required=True, help="category id, e.g. glovewort_ghost_1")
    ap.add_argument("--zh", required=True, help="marker name, e.g. 灵依墓地铃兰【１】")
    ap.add_argument("--en", default="")
    ap.add_argument("--note", default="位置由经存档核对")
    args = ap.parse_args()

    path = args.save
    if not path:
        cands = glob.glob(os.path.join(os.environ.get("APPDATA", ""), "EldenRing", "*", "ER0000.sl2"))
        path = cands[0] if cands else None
    if not path or not os.path.isfile(path):
        sys.exit("no save found; pass --save <ER0000.sl2>")
    data = io.open(path, "rb").read()
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
            best = (n, idx, pay)
    if best is None:
        sys.exit("no non-empty slot in that save")
    n, idx, pay = best
    pos = er_save.read_position(pay)
    print("slot %d (%d flags); map=%s pos=(%.1f, %.1f, %.1f)"
          % (idx, n, pos["map_id"], pos["x"], pos["y"], pos["z"]))

    mid = pos["map_id"]
    aa, bb, cc = int(mid[1:3]), int(mid[4:6]), int(mid[7:9])
    tier = int(mid[10:12]) if aa in (60, 61) else 0
    game = require_game_dir(None)
    mod = modfiles.find_mod_dir(None)
    dvd = DvdBnd(game, cache_dir=os.path.join(ROOT, "cache"), verbose=False)
    params = param.load_params(modfiles.regulation_path(game, mod))
    conv = LegacyConv(params["WorldMapLegacyConvParam"].rows,
                      paramdef.load(os.path.join(ROOT, "data", "paramdefs",
                                                "WorldMapLegacyConvParam.xml")))
    p = place(aa, bb, cc, pos["x"], pos["y"], pos["z"], conv, tier=tier)
    dvd.close()
    if p is None:
        sys.exit("projection failed for %s (no legacy conversion entry)" % mid)
    px, py, master, hgt = p
    print("master=%s px=%.1f py=%.1f h=%.0f" % (master, px, py, hgt))

    out = os.path.join(ROOT, "data", "user-verified.json")
    doc = {"locales": ["zh", "en"], "markers": []}
    if os.path.isfile(out):
        doc = json.load(open(out, encoding="utf-8"))
    doc.setdefault("markers", [])
    doc["markers"] = [m for m in doc["markers"] if m.get("cat") != args.cat]
    doc["markers"].append({
        "id": "user:%s:%s" % (args.cat, mid),
        "cat": args.cat,
        "names": {"zh": args.zh, "en": args.en or args.zh},
        "flag": None, "lot": None,
        "master": master, "px": round(px, 1), "py": round(py, 1), "h": round(hgt),
        "map": mid, "via": "user-verified",
        "note": "%s（存档 %s，map %s）" % (args.note, os.path.basename(path), mid),
    })
    io.open(out, "w", encoding="utf-8").write(json.dumps(doc, ensure_ascii=False, indent=1))
    print("wrote %s (%d user-verified markers)" % (out, len(doc["markers"])))


if __name__ == "__main__":
    main()
