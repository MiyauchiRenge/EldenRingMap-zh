"""Extract ERR Rune Piece / Ember Piece collectible locations.

These are NOT treasure lots (ItemLotParam); ERR places them as MSB entities
(model AEG099_821 = Rune Piece, AEG099_822 = Ember Piece) whose positions live
in MapForGoblins' pre-extracted JSON (MIT-licensed). This projects them onto
the master map like every other marker.

    python tools/extract_pieces.py   -> data/pieces.json

Collected-state: ERR tracks pieces via GEOF geometry memory, not save flags, so
they carry none and stay visible until checked off by hand.
data/mfg/_piece_final_map.json was meant to supply flags for 43 of them, but its
coordinates match none of the piece positions (and 22 of its 43 records are type
"unknown", which this lookup does not even consider), so in practice every piece
is flagless. The script says so rather than printing a silent 0.

Only emitted when the install being read actually defines goods 800010 / 850010,
i.e. when the ERR mod is installed. Deleting data/pieces.json is not a way to get
rid of them on vanilla: this runs again from the JSON above on the next Setup.
"""
import argparse
import json
import os
import sys

reconfigure = getattr(sys.stdout, "reconfigure", None)
if reconfigure:
    reconfigure(encoding="utf-8")
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from erlib import param, paramdef, fmg, oodle
import erlib.modfiles as modfiles
from erlib.dvdbnd import DvdBnd
from erlib.gamepath import require_game_dir
from build_markers import LegacyConv, place, LOCALES

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.dirname(HERE)
MFG = os.path.join(ROOT, "data", "mfg")

# goods id -> (category slug, icon, EN fallback name)
PIECES = {
    800010: ("rune_pieces", "rune_piece.png", "Rune Piece"),
    850010: ("ember_pieces", "ember_piece.png", "Ember Piece"),
}


def main():
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--game-dir", default=None)
    ap.add_argument("--mod-dir", default=None)
    args = ap.parse_args()

    game = require_game_dir(args.game_dir)
    mod = modfiles.find_mod_dir(args.mod_dir)
    dvd = DvdBnd(game, cache_dir=os.path.join(ROOT, "cache"), verbose=False)
    helper = oodle.make_helper(game)

    params = param.load_params(modfiles.regulation_path(game, mod))
    conv = LegacyConv(params["WorldMapLegacyConvParam"].rows,
                      paramdef.load(os.path.join(ROOT, "data", "paramdefs",
                                                 "WorldMapLegacyConvParam.xml")))

    # Names from the game's own GoodsName FMG.
    names_by_loc = {}
    for loc, folder in LOCALES.items():
        tables = {}
        for f in ["item.msgbnd.dcx", "item_dlc02.msgbnd.dcx"]:
            p = f"/msg/{folder}/{f}"
            if modfiles.has(dvd, mod, p):
                data = modfiles.read(dvd, mod, p)
                for k, v in fmg.load_msgbnd(data, oodle=helper).items():
                    tables.setdefault(k.split("_dlc")[0], {}).update(v)
        names_by_loc[loc] = tables.get("GoodsName", {})

    en_goods = names_by_loc.get("en", {})

    def goods_name(loc, goods_id, fallback):
        v = names_by_loc.get(loc, {}).get(goods_id, "")
        if not v or v.startswith("%null%"):
            v = en_goods.get(goods_id, "")
        if not v or v.startswith("%null%"):
            v = fallback
        return v
    # event flags for the few pieces that have one (keyed by rounded coords+map)
    flags = {}
    flag_path = os.path.join(MFG, "_piece_final_map.json")
    if os.path.isfile(flag_path):
        for rec in json.load(open(flag_path, encoding="utf-8")):
            key = (rec["type"], rec["map"], round(rec["x"], 1), round(rec["z"], 1))
            flags[key] = rec.get("flag", 0)

    markers = []
    seen = set()
    skipped = []
    flag_hits = 0
    for goods_id, (cat, icon, fallback) in PIECES.items():
        # Only emit a family that the install being read actually defines.
        #
        # ERR adds Rune Pieces and Ember Pieces as goods 800010 / 850010. Their
        # coordinates always come from MapForGoblins' pre-extracted JSON, but the
        # NAMES come from the game - and on a vanilla install neither id exists, so
        # every name fell back to the hardcoded English below. The result was 1449
        # markers of a mod the player does not have: a quarter of the whole map,
        # English in all three languages, not one of them tickable.
        # If the name resolves, the install (or the mod dir being read) defines the
        # item, and then these pieces are real.
        if not en_goods.get(goods_id):
            skipped.append((cat, goods_id))
            continue
        path = os.path.join(MFG, "rune_pieces.json" if goods_id == 800010
                            else "ember_pieces.json")
        if not os.path.isfile(path):
            continue
        data = json.load(open(path, encoding="utf-8"))
        for piece in data:
            map_id = piece["map"]
            aa = int(map_id[1:3])
            bb = int(map_id[4:6])
            cc = int(map_id[7:9])
            tier = int(map_id[10:12]) if aa in (60, 61) else 0
            x, y, z = piece["x"], piece.get("y", 0.0), piece["z"]
            p = place(aa, bb, cc, x, y, z, conv, tier=tier)
            if p is None:
                continue
            px, py, master, height = p
            key = (round(px, 1), round(py, 1), master)
            if key in seen:
                continue
            seen.add(key)
            flag = flags.get(("rune" if goods_id == 800010 else "ember",
                              map_id, round(x, 1), round(z, 1)), 0) or None
            if flag:
                flag_hits += 1
            markers.append({
                "id": f"{cat}:{goods_id}:{len(markers)}",
                "cat": cat,
                "names": {loc: goods_name(loc, goods_id, fallback)
                          for loc in LOCALES},
                "flag": flag,
                "master": master, "px": round(px, 1), "py": round(py, 1),
                "h": round(height),
                "map": map_id,
                "icon": icon,
            })

    out = os.path.join(ROOT, "data", "pieces.json")
    with open(out, "w", encoding="utf-8") as f:
        json.dump({"locales": list(LOCALES), "markers": markers}, f,
                  ensure_ascii=False)
    from collections import Counter
    counts = Counter(m["cat"] for m in markers)
    flagged = sum(1 for m in markers if m.get("flag"))
    print(f"pieces: {len(markers)} markers ({dict(counts)}), {flagged} with flags")
    if skipped:
        print("  skipped - this install defines no such goods id: "
              + ", ".join(f"{c} ({i})" for c, i in skipped))
    if markers and not flagged:
        # A flag table that silently matches nothing is exactly how a dead mapping
        # hides, so say so rather than printing a 0 nobody reads.
        print("  note: none of the %d records in data/mfg/_piece_final_map.json "
              "matched a piece, so nothing here can be ticked off" % len(flags))
    print(f"-> {out}")
    dvd.close()


if __name__ == "__main__":
    main()
