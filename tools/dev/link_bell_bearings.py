"""Link merchant-kill bell bearings to their merchant marker (post-processing, re-runnable).

Killing a Nomadic/Isolated/Hermit merchant drops that merchant's bell bearing; the bearing already
exists in data/drops.json (category drop_bell_bearings) at the merchant's own coordinates. This adds
a `dropsBell` field on the merchant marker so the card can say what it drops.
"""
import io
import json
import math
import os
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.dirname(os.path.dirname(HERE))
MAX_PX = 40.0


def main():
    npcs_p = os.path.join(ROOT, "data", "npcs.json")
    npcs = json.load(io.open(npcs_p, encoding="utf-8"))
    bells = []
    for f in ("drops.json", "boss-drops.json", "followup.json", "items.json",
              "emevd-drops.json"):
        p = os.path.join(ROOT, "data", f)
        if not os.path.isfile(p):
            continue
        for m in json.load(io.open(p, encoding="utf-8")).get("markers") or []:
            zh = (m.get("names") or {}).get("zh", "")
            if "铃珠" in zh and m.get("px") is not None:
                bells.append((zh, m.get("master"), m["px"], m["py"]))
    print("bell-bearing markers with a position: %d" % len(bells))
    linked = 0
    for m in npcs["markers"]:
        best, bd = None, MAX_PX
        for zh, master, px, py in bells:
            if master != m.get("master"):
                continue
            d = math.hypot(px - m["px"], py - m["py"])
            if d < bd:
                best, bd = zh, d
        if best:
            m["dropsBell"] = best
            m["dropsBellPx"] = round(bd, 1)
            linked += 1
    io.open(npcs_p, "w", encoding="utf-8").write(json.dumps(npcs, ensure_ascii=False))
    print("merchants linked to a bell bearing: %d / %d" % (linked, len(npcs["markers"])))
    for m in npcs["markers"]:
        if m.get("dropsBell"):
            print("   %-34s -> %-20s %.0f px" % (m["names"]["zh"], m["dropsBell"],
                                                 m["dropsBellPx"]))


if __name__ == "__main__":
    main()
