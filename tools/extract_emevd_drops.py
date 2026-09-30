"""Extract one-time drops from EMEVD parameter records.

Chain (every link verified; see tools/dev/EMEVD-notes.md):

  a file's parameter section holds records shaped like
      [ .., eventId, entityId, entityFlag, lotId, floats.. ]
  so a flagged item lot ties to the map entity that grants it, and that entity's MSB part
  gives the position (part +0x60 -> entity data, EntityID at +0x00 of it).

Filter measured against the sibling project's 455-record benchmark: require
entity == flag and event id > 1000 -> 189 hits at 100% entity accuracy. The loose variant
reaches 65% coverage but only 88%, so it is not used for data.

This file was truncated to 78 lines by an earlier blind patch (whole main body lost), so it
is written out in full here.
"""
from __future__ import annotations

import argparse
import io
import json
import os
import struct
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)
from erlib import dcx, emevd, fmg, msb, oodle, param, paramdef    # noqa: E402
import erlib.modfiles as modfiles                                  # noqa: E402
from erlib.dvdbnd import DvdBnd                                    # noqa: E402
from erlib.gamepath import require_game_dir                        # noqa: E402
from build_markers import LegacyConv, place                        # noqa: E402

ROOT = os.path.dirname(HERE)
DROP_CAT = {1: "drop_items", 2: "drop_weapons", 3: "drop_armour",
            4: "drop_talismans", 5: "drop_items"}
TABLE_OF_KIND = {1: "GoodsName", 2: "WeaponName", 3: "ProtectorName",
                 4: "AccessoryName", 5: "GemName"}
PLACEHOLDER = "[ERROR]"


def load_item_names(dvd, mod, helper):
    """{table: {itemId: name}} from the Chinese item message tables."""
    out = {}
    for f in ("item.msgbnd.dcx", "item_dlc02.msgbnd.dcx"):
        p = "/msg/zhocn/%s" % f
        if not modfiles.has(dvd, mod, p):
            continue
        for table, rows in fmg.load_msgbnd(modfiles.read(dvd, mod, p), oodle=helper).items():
            out.setdefault(table.split("_dlc")[0], {}).update(rows)
    return out


def name_of_item(names, iid, kind):
    """Name for an item, skipping the game's literal placeholder rows."""
    for table in (TABLE_OF_KIND.get(kind, ""), "GoodsName", "WeaponName",
                  "ProtectorName", "AccessoryName", "GemName"):
        if not table:
            continue
        nm = (names.get(table) or {}).get(iid, "")
        if nm and PLACEHOLDER not in nm:
            return nm
    return ""


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--game-dir", default=None)
    ap.add_argument("--out", default=os.path.join(ROOT, "data", "emevd-drops.json"))
    args = ap.parse_args()

    game = require_game_dir(args.game_dir)
    mod = modfiles.find_mod_dir(args.game_dir)
    dvd = DvdBnd(game, cache_dir=os.path.join(ROOT, "cache"), verbose=False)
    helper = oodle.make_helper(game)
    params = param.load_params(modfiles.regulation_path(game, mod))
    ld = paramdef.load(os.path.join(ROOT, "data", "paramdefs", "ItemLotParam.xml"))
    names = load_item_names(dvd, mod, helper)
    print("name tables: %s" % {k: len(v) for k, v in sorted(names.items())})

    lots = {}
    for tbl in ("ItemLotParam_map", "ItemLotParam_enemy"):
        for r in params[tbl].rows:
            items = []
            for i in range(1, 9):
                iid = ld.get(r.data, "lotItemId%02d" % i)
                if iid:
                    items.append((iid, ld.get(r.data, "lotItemCategory%02d" % i)))
            if items:
                lots[r.id] = {"items": items, "flag": ld.get(r.data, "getItemFlagId")}
    print("lots with items: %d" % len(lots))

    maps = [l.split("\t")[0] for l in open(os.path.join(ROOT, "cache", "map-list.txt"),
                                          encoding="utf-8") if l.strip()]
    conv = LegacyConv(params["WorldMapLegacyConvParam"].rows,
                      paramdef.load(os.path.join(ROOT, "data", "paramdefs",
                                                "WorldMapLegacyConvParam.xml")))
    entity_pos = {}
    for mid in maps:
        path = "/map/mapstudio/%s.msb.dcx" % mid
        if not modfiles.has(dvd, mod, path):
            continue
        try:
            m = msb.load(dcx.decompress(modfiles.read(dvd, mod, path), oodle=helper))
        except Exception:
            continue
        aa, bb, cc = int(mid[1:3]), int(mid[4:6]), int(mid[7:9])
        tier = int(mid[10:12]) if aa in (60, 61) else 0
        for poff, _p in m.entries("PARTS_PARAM_ST"):
            ent = emevd.entity_id_of_part(m, poff)
            if not ent:
                continue
            p = place(aa, bb, cc, *m.vec3(poff + emevd.PART_POSITION), conv, tier=tier)
            if p is None:
                continue
            entity_pos.setdefault(ent, (mid, p[0], p[1], p[2], p[3]))
    print("entity table: %d" % len(entity_pos))

    pairs = {}
    for mid in ["common", "common_macro"] + maps:
        path = "/event/%s.emevd.dcx" % mid
        if not modfiles.has(dvd, mod, path):
            continue
        try:
            raw = dcx.decompress(modfiles.read(dvd, mod, path), oodle=helper)
        except Exception:
            continue
        if not emevd.is_emevd(raw):
            continue
        h = emevd.read_header(raw)
        blob = raw[h["paramOffset"]:]
        n = len(blob) // 4
        words = struct.unpack_from("<%di" % n, blob, 0)
        for k in range(len(words) - 3):
            ev, ent, flag, lot = words[k], words[k + 1], words[k + 2], words[k + 3]
            if lot in lots and ent == flag and ent > 1000 and ev > 1000:
                pairs.setdefault(lot, set()).add(ent)
    print("lots paired: %d" % len(pairs))

    markers = []
    skipped_pos = skipped_name = 0
    for lot, ents in sorted(pairs.items()):
        for ent in sorted(ents):
            pos = entity_pos.get(ent)
            if pos is None:
                skipped_pos += 1
                continue
            mid, px, py, master, hgt = pos
            iid, kind = lots[lot]["items"][0]
            nm = name_of_item(names, iid, kind)
            if not nm:
                skipped_name += 1
                continue
            markers.append({
                "id": "edrop:%s:%s:%d" % (mid, ent, lot),
                "cat": DROP_CAT.get(kind, "drop_items"),
                "names": {"zh": nm, "en": nm},
                "flag": lots[lot]["flag"],
                "lot": lot, "entity": ent,
                "master": master,
                "px": round(px, 1), "py": round(py, 1), "h": round(hgt),
                "map": mid, "via": "emevd-param",
            })
    with io.open(args.out, "w", encoding="utf-8") as f:
        json.dump({"locales": ["zh", "en"], "markers": markers}, f, ensure_ascii=False)
    print("emevd drop markers: %d (no placement %d, no name %d) -> %s"
          % (len(markers), skipped_pos, skipped_name, args.out))
    if markers:
        print("sample: %s" % [(mk["names"]["zh"], mk["cat"]) for mk in markers[:5]])
    dvd.close()


if __name__ == "__main__":
    main()
