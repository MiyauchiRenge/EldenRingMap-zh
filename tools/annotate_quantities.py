"""Annotate every marker with the quantity its lot actually grants (goal step 1).

Scadutree Fragments: 46 lots, of which 4 grant 2 - 42*1 + 4*2 = 50 items. Spirit Ashes: 23 lots,
2 of them grant 2 - 25 items. Without the count the map cannot explain "one spot gives two".

Runs as a post-processing pass over data/*.json (after the extractors, so a rerun does not lose
it), writing `num` on every marker whose `lot` is a known ItemLotParam row, plus `num_total`
sums into data/quantities.json for the UI. Idempotent.
"""
from __future__ import annotations

import io
import json
import os
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)
from erlib import param, paramdef          # noqa: E402
import erlib.modfiles as modfiles           # noqa: E402
from erlib.gamepath import require_game_dir  # noqa: E402

ROOT = os.path.dirname(HERE)
FILES = ("items.json", "drops.json", "boss-drops.json", "emevd-drops.json", "followup.json",
         "gather-nodes.json", "farm.json", "emevd-rewards.json", "user-verified.json")


def main():
    game = require_game_dir(None)
    mod = modfiles.find_mod_dir(None)
    params = param.load_params(modfiles.regulation_path(game, mod))
    ld = paramdef.load(os.path.join(ROOT, "data", "paramdefs", "ItemLotParam.xml"))

    # lot -> (total count across its item slots, first item id)
    lots = {}
    for tbl in ("ItemLotParam_map", "ItemLotParam_enemy"):
        for r in params[tbl].rows:
            # only goods: an id can collide with a weapon/armour row
            total = 0
            first = None
            for i in range(1, 9):
                if ld.get(r.data, "lotItemCategory%02d" % i) != 1:
                    continue
                iid = ld.get(r.data, "lotItemId%02d" % i)
                if not iid or iid == 0:
                    continue
                if first is None:
                    first = iid
                total += ld.get(r.data, "lotItemNum%02d" % i) or 0
            if first is not None:
                lots[r.id] = (total, first)
    print("lots with a quantity: %d" % len(lots))

    changed = per_item = 0
    totals = {}
    for name in FILES:
        p = os.path.join(ROOT, "data", name)
        if not os.path.isfile(p):
            continue
        doc = json.load(io.open(p, encoding="utf-8"))
        ms = doc.get("markers") or []
        for m in ms:
            lot = m.get("lot")
            if lot in lots:
                n, iid = lots[lot]
                if m.get("num") != n:
                    m["num"] = n
                    changed += 1
                if n and n > 1:
                    per_item += 1
                totals[iid] = totals.get(iid, 0) + n
        io.open(p, "w", encoding="utf-8").write(json.dumps(doc, ensure_ascii=False))
    print("markers annotated: %d (of which multi-count: %d)" % (changed, per_item))

    # the two headline totals, for the UI and the docs
    head = {}
    for iid, label in ((2010000, "幽影树碎片"), (2010100, "灵灰")):
        lot_total = sum(n for n, f in lots.values() if f == iid)
        lot_count = sum(1 for n, f in lots.values() if f == iid)
        head[label] = {"lots": lot_count, "items": lot_total}
        print("%s: %d 个点位 / %d 个物品" % (label, lot_count, lot_total))
    io.open(os.path.join(ROOT, "data", "quantities.json"), "w", encoding="utf-8").write(
        json.dumps(head, ensure_ascii=False, indent=1))
    print("wrote data/quantities.json")


if __name__ == "__main__":
    main()
