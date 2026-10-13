"""Check the one-time / respawning split of data/gather-nodes.json against a real save.

The save's WorldGeomMan2 block (magic "FOEG") only ever lists nodes that were picked permanently,
so it is independent ground truth for the split: every row it names must be one-time in the layer,
and every entry should match a node we placed (map + AEG row + instance).

Usage: python tools/dev/gather_lifetime_check.py [--save PATH]
"""
import argparse
import io
import json
import os
import sys
from collections import Counter, defaultdict

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, os.path.dirname(HERE))
ROOT = os.path.dirname(os.path.dirname(HERE))

import er_save                                            # noqa: E402
from erlib.gamepath import find_save                      # noqa: E402


def fullest_slot(data):
    """-> (slot index, flag count, payload) for the save's most-played slot."""
    groups = er_save.load_flag_groups(os.path.join(ROOT, "data", "eventflag_bst.txt"))
    best = None
    for idx in range(len(er_save.read_entries(data))):
        try:
            pay = er_save.slot_payload(data, idx)
            n = sum(1 for _ in er_save.EventFlags(pay, groups).iter_set())
        except Exception:
            continue
        if n and (best is None or n > best[1]):
            best = (idx, n, pay)
    return best


def main():
    ap = argparse.ArgumentParser(description=__doc__,
                                 formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--save", default=None, help="ER0000.sl2 (default: the most recent one)")
    args = ap.parse_args()

    save = args.save or find_save(None)
    if not save or not os.path.isfile(save):
        sys.exit("no save found; pass --save")
    layer_path = os.path.join(ROOT, "data", "gather-nodes.json")
    if not os.path.isfile(layer_path):
        sys.exit("run tools/extract_gather_nodes.py first")
    layer = json.load(io.open(layer_path, encoding="utf-8"))["markers"]
    once_items = {m["item"] for m in layer if m.get("once")}
    print("layer: %d nodes (%d one-time, %d respawning); one-time items: %d"
          % (len(layer), sum(1 for m in layer if m.get("once")),
             sum(1 for m in layer if not m.get("once")), len(once_items)))

    # node index: (map, AEG row, instance) -> marker
    node_by_key = {}
    for m in layer:
        inst = int(str(m["part"]).rsplit("_", 1)[-1])
        node_by_key[(m["map"], m["aeg"], inst)] = m

    data = io.open(save, "rb").read()
    idx, n, pay = fullest_slot(data)
    pos = er_save.read_position(pay)
    print("save: %s (slot %d, %d flags, player at %s)"
          % (save, idx, n, pos["map_id"]))
    foeg = er_save.read_world_geom(pay, b"FOEG")
    if foeg is None:
        sys.exit("no FOEG block in that slot")
    entries = [(mid, key, model) for mid, v in foeg.items() for key, model in v]
    print("FOEG: %d entries in %d maps" % (len(entries), len(foeg)))

    matched = unmatched = 0
    miss_by_map = Counter()
    wrong = []
    for mid, key, model in entries:
        aeg, inst = model - 10000000, key >> 15
        m = node_by_key.get((mid, aeg, inst))
        if m is None:
            unmatched += 1
            miss_by_map[mid] += 1
            continue
        matched += 1
        if not m.get("once"):
            wrong.append((mid, aeg, inst, m["names"]["zh"]))
    print("FOEG entries matched to a placed node: %d / %d" % (matched, len(entries)))
    if unmatched:
        print("   unmatched: %d (maps: %s)" % (unmatched, miss_by_map.most_common(6)))
    print("FOEG entries whose node is marked respawning: %d %s"
          % (len(wrong), wrong[:5]))
    rows = {model - 10000000 for _mid, _key, model in entries}
    not_once = sorted(a for a in rows if a not in {m["aeg"] for m in layer if m.get("once")})
    print("FOEG AEG rows: %d ; rows not marked one-time: %d %s"
          % (len(rows), len(not_once), not_once[:5]))
    per_map = Counter(mid for mid, _k, _m in entries)
    print("busiest maps: %s" % per_map.most_common(6))
    print("result: %s" % ("consistent" if not wrong and not not_once else "MISMATCH"))


if __name__ == "__main__":
    main()
