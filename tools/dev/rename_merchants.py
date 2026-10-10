"""Name merchants: nearest grace within 300 px, else the nearest named landmark.

Boss names are never used - a boss can be kilometres away and would read as a wrong location. The
suppression file (data/merchant-suppress.json) is honoured, and markers already removed are not
resurrected here: run extract_items.py first.
"""
import io
import json
import math
import os
import re
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.dirname(os.path.dirname(HERE))
KIND_FIX = ("\u5496\u5217", "Kal\u00e9", "Kale")
GRACE_MAX = 300.0
BAD_CATS = {"boss", "boss_drops", "enemy", "drop_items", "drop_weapons", "drop_armour",
            "drop_talismans", "farm_spots", "gathering", "merchants"}


def strip_paren(s):
    return re.sub(r"[\uff08(][^\uff09)]*[\uff09)]$", "", s).strip()


def blob(m):
    nm = m.get("names")
    out = []
    if isinstance(nm, dict):
        out += [str(v) for v in nm.values()]
    for k in ("place", "region"):
        if m.get(k):
            out.append(str(m[k]))
    return " ".join(out)


def main():
    npcs_p = os.path.join(ROOT, "data", "npcs.json")
    mk_p = os.path.join(ROOT, "data", "markers.json")
    sp_p = os.path.join(ROOT, "data", "merchant-suppress.json")
    suppress = json.load(io.open(sp_p, encoding="utf-8")) if os.path.isfile(sp_p) else {}
    lab_p = os.path.join(ROOT, "data", "merchant-labels.json")
    labels = json.load(io.open(lab_p, encoding="utf-8")) if os.path.isfile(lab_p) else {}
    npcs = json.load(io.open(npcs_p, encoding="utf-8"))
    allm = json.load(io.open(mk_p, encoding="utf-8"))["markers"]
    graces = [m for m in allm if m.get("cat") == "grace"]
    places = [m for m in allm if m.get("cat") not in BAD_CATS and m.get("px") is not None]
    kept, dropped = [], []
    for m in npcs["markers"]:
        key9 = str(m.get("map"))[:9]
        if key9 in suppress:
            dropped.append(m["names"]["zh"])
            continue
        pool = [g for g in graces if g.get("master") == m.get("master")] or graces
        g = min(pool, key=lambda x: (x["px"] - m["px"]) ** 2 + (x["py"] - m["py"]) ** 2)
        dg = math.hypot(g["px"] - m["px"], g["py"] - m["py"])
        src, d = g, dg
        if dg > GRACE_MAX:
            cand = [p for p in places if p.get("master") == m.get("master")] or places
            p2 = min(cand, key=lambda x: (x["px"] - m["px"]) ** 2 + (x["py"] - m["py"]) ** 2)
            dp = math.hypot(p2["px"] - m["px"], p2["py"] - m["py"])
            if dp < dg:
                src, d = p2, dp
        zh_kind, en_kind = strip_paren(m["names"]["zh"]), strip_paren(m["names"].get("en") or "")
        gzh = src["names"]["zh"]
        gen = src["names"].get("en") or ""
        if any(k in zh_kind for k in KIND_FIX) and "\u827e\u96f7\u6559\u5802" not in gzh:
            zh_kind, en_kind = "\u6d41\u6d6a\u6c11\u65cf\u7684\u5546\u4eba", "Nomadic Merchant"
        forced = labels.get(key9)
        if forced:
            gzh, gen = forced, forced
        m["names"] = {"zh": "%s\u00b7%s" % (zh_kind, gzh) if gzh else zh_kind,
                      "en": "%s - %s" % (en_kind, gen) if gen else en_kind}
        m["anchorSource"], m["anchorDistance"] = src.get("cat"), round(d, 1)
        kept.append(m)
    npcs["markers"] = kept
    io.open(npcs_p, "w", encoding="utf-8").write(json.dumps(npcs, ensure_ascii=False))
    print("merchants kept: %d ; suppressed: %d" % (len(kept), len(dropped)))
    for n in dropped:
        print("   suppressed: %s" % n)
    for m in sorted(kept, key=lambda x: x["names"]["zh"]):
        print("   %-40s <- %-8s %-24s %.0f px"
              % (m["names"]["zh"], m["anchorSource"], "", m["anchorDistance"]))


if __name__ == "__main__":
    main()
