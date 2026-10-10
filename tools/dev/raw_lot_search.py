"""Global raw search: does ANY map file mention one of the 17 glovewort-awarding lot ids?

The missing levels (灵依【１】【３】, 墓地【３】) have lots 999300/999320/999220 and the 5110000xx
family, all with flag 0. If a ground gatherable awards them, some part record must reference
the id somewhere - possibly in a field I have not decoded (not +0x260, not the type data).

So: decompress every map and search its RAW bytes for each lot id, recording map, hit count and
the first offsets. A hit inside a long arithmetic run is a lookup table; an isolated hit inside
a part record is a real reference.
"""
from __future__ import annotations

import io
import os
import struct
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, os.path.dirname(HERE))
sys.path.insert(0, HERE)
from erlib import dcx, oodle, param, paramdef      # noqa: E402
import erlib.modfiles as modfiles                   # noqa: E402
from erlib.dvdbnd import DvdBnd                     # noqa: E402
from erlib.gamepath import require_game_dir         # noqa: E402

ROOT = os.path.dirname(os.path.dirname(HERE))
TARGET_GOODS = {10902: "墓地铃兰【３】", 10910: "灵依墓地铃兰【１】", 10912: "灵依墓地铃兰【３】"}


def main():
    game = require_game_dir(None)
    mod = modfiles.find_mod_dir(None)
    dvd = DvdBnd(game, cache_dir=os.path.join(ROOT, "cache"), verbose=False)
    helper = oodle.make_helper(game)
    params = param.load_params(modfiles.regulation_path(game, mod))
    ld = paramdef.load(os.path.join(ROOT, "data", "paramdefs", "ItemLotParam.xml"))

    lots = {}
    for tbl in ("ItemLotParam_map", "ItemLotParam_enemy"):
        for r in params[tbl].rows:
            for i in range(1, 9):
                gid = ld.get(r.data, "lotItemId%02d" % i)
                if ld.get(r.data, "lotItemCategory%02d" % i) == 1 and gid in TARGET_GOODS:
                    lots.setdefault(gid, set()).add(r.id)
    all_lots = {}
    for gid, ids in lots.items():
        for l in ids:
            all_lots[l] = gid
    print("target lots: %s" % sorted(all_lots))

    maps = [l.split("\t")[0] for l in open(os.path.join(ROOT, "cache", "map-list.txt"),
                                          encoding="utf-8") if l.strip()]
    out = os.path.join(ROOT, "_raw_lot_hits.txt")
    fh = io.open(out, "w", encoding="utf-8")
    fh.write("target lots: %s\n\n" % sorted(all_lots))
    total_hits = 0
    for mid in maps:
        path = "/map/mapstudio/%s.msb.dcx" % mid
        if not modfiles.has(dvd, mod, path):
            continue
        try:
            raw = dcx.decompress(modfiles.read(dvd, mod, path), oodle=helper)
        except Exception:
            continue
        found = []
        for lot, gid in sorted(all_lots.items()):
            pat = struct.pack("<I", lot)
            i = raw.find(pat)
            hits = []
            while i != -1 and len(hits) < 4:
                hits.append(i)
                i = raw.find(pat, i + 1)
            if hits:
                found.append((lot, gid, hits))
        if found:
            total_hits += 1
            fh.write("%s (%d bytes)\n" % (mid, len(raw)))
            for lot, gid, hits in found:
                fh.write("   lot %-12d %-18s offsets %s\n" % (lot, TARGET_GOODS[gid], hits))
    fh.write("\nmaps with any hit: %d\n" % total_hits)
    fh.close()
    print("maps with hits: %d" % total_hits)
    print("report: %s" % out)
    dvd.close()


if __name__ == "__main__":
    main()
