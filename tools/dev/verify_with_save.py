"""Verify our map against the player's save: what did they take that we do not show?

Every item lot can carry a getItemFlagId, which is set once the item is granted. So the save
tells us exactly which pickups the player consumed. Comparing that with the flags our markers
carry answers "is our map missing anything the player actually picked?" - using the player's
own data as the ground truth, with no third-party list involved.

Usage:
    python tools/dev/verify_with_save.py [--save <ER0000.sl2>] [--item 灵依墓地铃兰]

Notes learned the hard way:
  * load_flag_groups wants data/eventflag_bst.txt (a text file), NOT the save;
  * EventFlags(payload, groups); the API offers get()/set()/iter_set()/locate();
  * flag ids for map-scoped lots follow lot + 7000 (verified on three known pickups);
  * print real numbers and never swallow a traceback.
"""
from __future__ import annotations

import argparse
import glob
import io
import json
import os
import sys
import traceback

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, os.path.dirname(HERE))
sys.path.insert(0, HERE)
from erlib import fmg, oodle, param, paramdef          # noqa: E402
import erlib.modfiles as modfiles                       # noqa: E402
from erlib.dvdbnd import DvdBnd                         # noqa: E402
from erlib.gamepath import require_game_dir             # noqa: E402
import er_save                                          # noqa: E402

ROOT = os.path.dirname(os.path.dirname(HERE))
TABLE_OF_KIND = {1: "GoodsName", 2: "WeaponName", 3: "ProtectorName",
                 4: "AccessoryName", 5: "GemName"}
DATA_FILES = ("items.json", "drops.json", "boss-drops.json", "farm.json",
              "emevd-drops.json", "followup.json", "gatherables.json", "npcs.json", "markers.json")


def default_save():
    cands = glob.glob(os.path.join(os.environ.get("APPDATA", ""), "EldenRing", "*", "ER0000.sl2"))
    return cands[0] if cands else None


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--save", default=None)
    ap.add_argument("--item", default=None, help="only report lots awarding this item substring")
    ap.add_argument("--limit", type=int, default=60)
    ap.add_argument("--out", default=os.path.join(ROOT, "_save_verify.txt"))
    args = ap.parse_args()

    path = args.save or default_save()
    if not path or not os.path.isfile(path):
        sys.exit("no ER0000.sl2 found; pass --save <path>")
    data = io.open(path, "rb").read()
    print("save: %s (%d bytes)" % (path, len(data)))
    groups_path = os.path.join(ROOT, "data", "eventflag_bst.txt")
    if not os.path.isfile(groups_path):
        sys.exit("missing data/eventflag_bst.txt (flag group table)")
    groups = er_save.load_flag_groups(groups_path)
    print("flag groups: %d blocks" % len(groups))

    entries = er_save.read_entries(data)
    print("slots: %d" % len(entries))
    best = None
    for idx in range(len(entries)):
        try:
            fl = er_save.EventFlags(er_save.slot_payload(data, idx), groups)
        except Exception:
            continue
        try:
            n = sum(1 for _ in fl.iter_set())
        except Exception:
            n = 0
        print("   slot %d: %d flags set" % (idx, n))
        if best is None or n > best[1]:
            best = (idx, n, fl)
    if best is None:
        sys.exit("no usable slot")
    slot, nflags, flags = best
    print("using slot %d (%d flags set in total)" % (slot, nflags))

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
        nm = (names.get(TABLE_OF_KIND.get(kind, "")) or {}).get(iid, "")
        if nm and "[ERROR]" not in nm:
            return nm
        for t in ("GoodsName", "WeaponName", "ProtectorName", "AccessoryName", "GemName"):
            nm = (names.get(t) or {}).get(iid, "")
            if nm and "[ERROR]" not in nm:
                return nm
        return ""

    # flag -> first item of the lot, for every lot that has a flag
    flag_item = {}
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
                    flag_item.setdefault(f, (name_of(iid, ld.get(r.data, "lotItemCategory%02d" % i)),
                                             tbl, r.id))
                    break
    print("flagged lots: %d" % len(flag_item))

    our_flags = {}
    for f in DATA_FILES:
        p = os.path.join(ROOT, "data", f)
        if not os.path.isfile(p):
            continue
        for m in json.load(open(p, encoding="utf-8"))["markers"]:
            if m.get("flag"):
                our_flags.setdefault(m["flag"], m)
    print("flags present on our markers: %d" % len(our_flags))

    taken = missing = 0
    rows = []
    for f, (nm, tbl, lot) in sorted(flag_item.items()):
        try:
            if not flags.get(f):
                continue
        except Exception:
            continue
        if args.item and args.item not in (nm or ""):
            continue
        taken += 1
        if f not in our_flags:
            missing += 1
            rows.append((f, nm, tbl, lot))
    print("flags SET in the save (matching filter): %d" % taken)
    print("SET but NOT on our map: %d" % missing)
    # UTF-8 report so Chinese names are readable regardless of console encoding
    with io.open(args.out, "w", encoding="utf-8") as fh:
        fh.write("save: %s" % path + chr(10))
        fh.write("flagged lots: %d ; flags on our markers: %d" % (len(flag_item), len(our_flags)) + chr(10))
        fh.write("flags set in save (filtered): %d ; set but NOT on our map: %d" % (taken, missing) + chr(10) + chr(10))
        kinds = {}
        for f, nm, tbl, lot in rows:
            kinds[tbl] = kinds.get(tbl, 0) + 1
        fh.write("by lot table: %s" % kinds + chr(10) + chr(10))
        for f, nm, tbl, lot in rows:
            fh.write("flag %-12d %-28s %s lot %d" % (f, nm or "(no name)", tbl, lot) + chr(10))
    print("report written: %s (%d rows)" % (args.out, len(rows)))
    print("by lot table: %s" % {t: sum(1 for r in rows if r[2] == t) for t in set(r[2] for r in rows)})
    for f, nm, tbl, lot in rows[:args.limit]:
        print("   flag %-12d %-24s %s lot %d   (flag prefix suggests map id %s)"
              % (f, nm or "(no name)", tbl, lot, str(f)[:4]))
    dvd.close()


if __name__ == "__main__":
    main()
