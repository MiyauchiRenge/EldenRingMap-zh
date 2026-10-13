"""Register the shop rows for limited items, and place each row on the merchant that sells it.

ShopLineupParam carries the item, price, quantity and stock flag but no merchant, and NpcParam has no
shop field either (EMEVD does not reference shop rows). The owner is declared in the talk scripts
instead: a shop is a run of ShopLineupParam rows that a talk ESD names, either as

    bank 1  cmd 22            (firstRow, lastRow)
    bank 6  cmd 2147483610    (flagA, firstRow, lastRow, flagB)

The second form carries event flags built from the owner's map id - m60_43_53's shop call passes
1043530701 / 1043532700 - so that form states its own owner instead of depending on a guess.

A talk script belongs to the MSB part it is named after: chr parts keep their talk id in the entity
data at +0x50, and the ESD file is `t<talk id>.esd` (asset parts have unrelated bytes at that offset,
so only `c*` models are read). A declaration therefore names a real NPC with a map and a position.
Rows owned by a c3200 nomad merchant are placed on the marker that merchant already has in
data/npcs.json - so the two markers sit on the same pixel - and rows owned by any other named NPC are
placed on that NPC's projected position. Rows whose only declarations belong to unnamed or absent
parts stay registered without coordinates, and the note says why.

The talk bundles are looked up by path (BHD5 stores only path hashes): one per map, plus the area
roots m60_00_00_00 / m61_00_00_00, which is where the overworld and DLC scripts live. The part table
needs every MSB, so it is cached in cache/talk-parts.json and rebuilt when the game's archives change.
"""
import argparse
import io
import json
import os
import re
import sys
import time
from collections import Counter, defaultdict

HERE = os.path.dirname(os.path.abspath(__file__))           # tools/dev
TOOLS = os.path.dirname(HERE)                               # tools
ROOT = os.path.dirname(TOOLS)                               # repository root
sys.path.insert(0, TOOLS)

from erlib import dcx, esd, fmg, msb, oodle, param, paramdef     # noqa: E402
import erlib.gamefiles as gamefiles                                 # noqa: E402
from erlib.bnd4 import BND4                                       # noqa: E402
from erlib.dvdbnd import DvdBnd                                   # noqa: E402
from erlib.gamepath import require_game_dir                       # noqa: E402
from erlib import layers
import build_markers                                              # noqa: E402

LOCALES = (("zh", "zhocn"), ("en", "engus"))
# The items this file is about: 龟裂壶 / 调香瓶 / 制作书 (cracked pot, perfume bottle, cookbook).
KEEP = ("\u9f9f\u88c2\u58f6", "\u8c03\u9999\u74f6", "\u5236\u4f5c\u4e66")
TALK_ID_OFF = 0x50              # MSB part -> entity data -> talk id
PART_NPC_PARAM_ID = 0x2AC
PART_POSITION = 0x20
SHOP_COMMANDS = {(1, 22), (6, 2147483610)}
SHOP_RANGE_MAX = 300            # a shop is a short run of rows, not a flag list
ITEM_TABLES = {0: "WeaponName", 1: "ProtectorName", 2: "AccessoryName", 3: "GoodsName",
               4: "GemName"}


# ------------------------------------------------------------------ game archives

def read_map_list():
    path = os.path.join(ROOT, "cache", "map-list.txt")
    if not os.path.isfile(path):
        sys.exit("run tools/dev/enumerate_maps.py first (creates cache/map-list.txt)")
    return [l.split("\t")[0].strip() for l in io.open(path, encoding="utf-8") if l.strip()]


def talk_stems(map_ids):
    """Every talk bundle name to try: one per map, plus each area's root bundle."""
    out, seen = [], set()
    for stem in list(map_ids) + ["%s_00_00_00" % m[:3] for m in map_ids]:
        if stem not in seen:
            seen.add(stem)
            out.append(stem)
    return out


def read_scripts(dvd, helper, map_ids):
    """-> {talk id: (bundle name, ESD)} for every talk script we can open."""
    out, bundles = {}, []
    bad = 0
    for stem in talk_stems(map_ids):
        path = "/script/talk/%s.talkesdbnd.dcx" % stem
        if not gamefiles.has(dvd, path):
            continue
        bundles.append(stem)
        raw = gamefiles.read(dvd, path)
        if dcx.is_dcx(raw):
            raw = dcx.decompress(raw, oodle=helper)
        bnd = BND4(raw)
        for e in bnd.entries:
            name = e.name.replace("\\", "/").split("/")[-1]
            m = re.match(r"^t(\d+)\.esd$", name)
            if not m:
                continue
            try:
                script = esd.ESD(bnd.read(e))
            except Exception:
                bad += 1
                continue
            out[int(m.group(1))] = (stem, script)
    print("talk bundles: %d read, %d scripts parsed%s"
          % (len(bundles), len(out), ", %d unreadable" % bad if bad else ""))
    return out, bundles


def archive_stamp(dvd):
    """Enough to notice a patch: the size and mtime of every .bhd we opened."""
    parts = []
    for name in DvdBnd.ARCHIVES:
        p = os.path.join(dvd.game_dir, name + ".bhd")
        if os.path.isfile(p):
            st = os.stat(p)
            parts.append("%s:%d:%.0f" % (name, st.st_size, st.st_mtime))
    return "|".join(parts)


def part_table(dvd, helper, map_ids):
    """-> {talk id: [part records]}; cached, because it reads every MSB in the game."""
    cache = os.path.join(ROOT, "cache", "talk-parts.json")
    stamp = archive_stamp(dvd)
    if os.path.isfile(cache):
        try:
            cached = json.load(io.open(cache, encoding="utf-8"))
        except ValueError:
            cached = None
        if cached and cached.get("stamp") == stamp:
            print("part table: %d talk ids, %d parts (cache)"
                  % (len(cached["parts"]), sum(len(v) for v in cached["parts"].values())))
            return {int(k): v for k, v in cached["parts"].items()}
    t0 = time.time()
    parts = defaultdict(list)
    read = 0
    for map_id in map_ids:
        path = "/map/mapstudio/%s.msb.dcx" % map_id
        if not gamefiles.has(dvd, path):
            continue
        try:
            m = msb.load(dcx.decompress(gamefiles.read(dvd, path), oodle=helper))
        except Exception:
            continue
        read += 1
        aa = int(map_id[1:3])
        tier = int(map_id[10:12]) if aa in (60, 61) else 0
        for poff, pname in m.entries("PARTS_PARAM_ST"):
            model = pname.rsplit("-", 1)[-1].split("_")[0]
            if not model.startswith(esd.CHR):
                continue                    # only chr parts carry a talk id at +0x50
            rel = m.i64(poff + 0x60)
            if rel <= 0:
                continue
            talk = m.i32(poff + rel + TALK_ID_OFF)
            if talk <= 0:
                continue
            x, y, z = m.vec3(poff + PART_POSITION)
            parts[talk].append({"map": map_id, "part": pname, "model": model, "tier": tier,
                                "npc": m.i32(poff + PART_NPC_PARAM_ID),
                                "pos": [round(x, 2), round(y, 2), round(z, 2)]})
    print("part table: %d maps read, %d talk ids, %d parts (%.0fs)"
          % (read, len(parts), sum(len(v) for v in parts.values()), time.time() - t0))
    os.makedirs(os.path.dirname(cache), exist_ok=True)
    io.open(cache, "w", encoding="utf-8").write(json.dumps(
        {"stamp": stamp, "parts": {str(k): v for k, v in parts.items()}}, ensure_ascii=False))
    return dict(parts)


# ------------------------------------------------------------------------ scripts

def declarations(scripts):
    """Every (talk id, bank/cmd, first row, last row) a script declares."""
    out = []
    for talk, (_stem, script) in scripts.items():
        for c in script.commands():
            vals = [v for v in c.constants() if v is not None]
            for a, b in zip(vals, vals[1:]):
                if 1000 <= a < b <= 3000000 and 2 <= (b - a) <= SHOP_RANGE_MAX:
                    out.append({"talk": talk, "bank": c.bank, "cmd": c.id, "start": a, "end": b})
    return out


# --------------------------------------------------------------------------- names

def load_names(dvd, helper, folder, files):
    tables = {}
    for f in files:
        path = "/msg/%s/%s" % (folder, f)
        if not gamefiles.has(dvd, path):
            continue
        for k, v in fmg.load_msgbnd(gamefiles.read(dvd, path), oodle=helper).items():
            tables.setdefault(k.split("_dlc")[0], {}).update(v)
    return tables


# ---------------------------------------------------------------------- placement

def map_parts(map_id):
    aa = int(map_id[1:3])
    return aa, int(map_id[4:6]), int(map_id[7:9]), (int(map_id[10:12]) if aa in (60, 61) else 0)


def project_position(conv, map_id, pos):
    """(map, local x/y/z) -> (px, py, master) or None, the same way build_markers does it."""
    aa, bb, cc, tier = map_parts(map_id)
    x, y, z = pos
    if aa in (60, 61):
        px, py = build_markers.project(aa, bb, cc, x, z, tier)
        return px, py, "M10" if aa == 61 else "M00"
    if conv is None:
        return None
    r = conv.convert(aa, bb, cc, x, y, z, tier=tier)
    if r is None:
        return None
    px, py, _height, dst_area = r
    if dst_area == 61:
        master = "M10"
    elif (aa, bb) in build_markers.UNDERGROUND_BLOCKS:
        master = "M01"
    else:
        master = "M00"
    return px, py, master


def main():
    ap = argparse.ArgumentParser(description=__doc__,
                                 formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--game-dir", default=None)
    args = ap.parse_args()

    game = require_game_dir(args.game_dir)
    dvd = DvdBnd(game, cache_dir=os.path.join(ROOT, "cache"), verbose=False)
    helper = oodle.make_helper(game)
    params = param.load_params(gamefiles.regulation_path(game))
    defs = {name: paramdef.load(os.path.join(ROOT, "data", "paramdefs", name + ".xml"))
            for name in ("ShopLineupParam", "NpcParam", "WorldMapLegacyConvParam")}
    # NpcName lives in the item bundle, not in a bundle of its own, so every table this tool needs
    # is read from the same pair of files (plus their DLC follow-ups, whose tables are suffixed
    # _dlc01/_dlc02 and merge back onto the base name).
    tables = {loc: load_names(dvd, helper, folder,
                             ["item.msgbnd.dcx", "item_dlc02.msgbnd.dcx",
                              "menu.msgbnd.dcx", "menu_dlc02.msgbnd.dcx"])
              for loc, folder in LOCALES}
    item_names = tables
    npc_tables = tables
    shop_def, npc_def = defs["ShopLineupParam"], defs["NpcParam"]
    npc_name_id = {}
    for r in params["NpcParam"].rows:
        try:
            npc_name_id[r.id] = npc_def.get(r.data, "nameId")
        except Exception:
            pass
    npc_names = {loc: {nid: tables.get("NpcName", {}).get(name_id, "")
                       for nid, name_id in npc_name_id.items()}
                 for loc, tables in npc_tables.items()}
    print("names loaded: items %d zh / %d en, NpcName %d zh / %d en"
          % (len(item_names["zh"].get("GoodsName", {})),
             len(item_names["en"].get("GoodsName", {})),
             len([v for v in npc_names["zh"].values() if v]),
             len([v for v in npc_names["en"].values() if v])))

    map_ids = read_map_list()
    scripts, bundles = read_scripts(dvd, helper, map_ids)
    parts = part_table(dvd, helper, map_ids)
    decls = declarations(scripts)
    print("shop-row declarations: %d from %d scripts (%d use the known shop commands)"
          % (len(decls), len({d["talk"] for d in decls}),
             sum(1 for d in decls if (d["bank"], d["cmd"]) in SHOP_COMMANDS)))

    # A merchant's own marker, so a placed row lands on the same pixel as the merchant.
    npc_markers = {}
    npcs_path = os.path.join(ROOT, "data", "npcs.json")
    if os.path.isfile(npcs_path):
        for m in json.load(io.open(npcs_path, encoding="utf-8")).get("markers") or []:
            if m.get("npcParam"):
                npc_markers.setdefault(m["npcParam"], m)

    def owner_of(talk):
        """Best part for a talk id: a nomad merchant part first, then the lowest tier."""
        rs = parts.get(talk) or []
        if not rs:
            return None
        return sorted(rs, key=lambda r: (r["model"] != "c3200", r["tier"], r["map"]))[0]

    def sold_by(decl):
        """(evidence rank, owner record or None, localised owner names)."""
        rec = owner_of(decl["talk"])
        names = {}
        if rec is not None:
            for loc, _folder in LOCALES:
                names[loc] = npc_names[loc].get(rec["npc"], "")
        named = bool(names.get("zh")) and "dummy" not in names.get("zh", "").lower()
        if rec is None:
            quality = 3
        elif rec["model"] == "c3200":
            quality = 0
        elif named:
            quality = 1
        else:
            quality = 2
        rank = (quality, 0 if (decl["bank"], decl["cmd"]) in SHOP_COMMANDS else 1,
                decl["end"] - decl["start"], decl["talk"])
        return rank, rec, names

    # ---- rows: item, price, quantity, stock flag, owner
    rows = []
    for r in params["ShopLineupParam"].rows:
        v = shop_def.as_dict(r.data, ("equipId", "value", "sellQuantity", "eventFlag_forStock",
                                      "eventFlag_forRelease", "equipType"))
        names = {loc: (item_names[loc].get(ITEM_TABLES.get(v.get("equipType", 3), ""), {})
                       .get(v.get("equipId"), "")
                       or item_names[loc].get("GoodsName", {}).get(v.get("equipId"), ""))
                 for loc, _folder in LOCALES}
        if not any(k in names["zh"] for k in KEEP):
            continue
        covering = [d for d in decls if d["start"] <= r.id <= d["end"]]
        scored = sorted(((sold_by(d), d) for d in covering), key=lambda t: t[0][0])
        best = scored[0] if scored else None
        rows.append({"id": r.id, "names": names, "value": v.get("value"),
                     "qty": v.get("sellQuantity"), "stock": v.get("eventFlag_forStock"),
                     "best": best, "all": scored})
    print("rows matching the kept items: %d" % len(rows))

    # ---- place them
    conv = None
    markers = []
    placed = unplaced = 0
    for row in rows:
        note_qty = "（不限量）" if (row["qty"] or 0) < 0 else " ×%d" % row["qty"]
        base = "商店出售：%s 卢恩%s" % (row["value"], note_qty)
        px = py = master = None
        owner_desc = ""
        if row["best"] is not None:
            _rank, rec, names = row["best"][0]
            decl = row["best"][1]
            if rec is not None:
                marker = npc_markers.get(rec["npc"])
                if marker is not None:
                    px, py, master = marker["px"], marker["py"], marker["master"]
                    owner_desc = (marker.get("names") or {}).get("zh") or names.get("zh", "")
                else:
                    if conv is None:
                        conv = build_markers.LegacyConv(
                            params["WorldMapLegacyConvParam"].rows, defs["WorldMapLegacyConvParam"])
                    got = project_position(conv, rec["map"], rec["pos"])
                    if got is not None:
                        px, py, master = got
                        owner_desc = names.get("zh") or ""
        others = []
        for (_rank, rec2, names2), _d in row["all"]:
            if rec2 is None:
                continue
            label = (npc_markers.get(rec2["npc"], {}).get("names") or {}).get("zh") \
                or names2.get("zh") or ""
            if label and label != owner_desc and label not in others:
                others.append(label)
        if px is not None:
            placed += 1
            note = "%s；商人：%s" % (base, owner_desc or "（未命名）")
            if others:
                note += "；同样出售：" + "、".join(others)
        else:
            unplaced += 1
            if row["best"] is not None:
                why = "货架 %d–%d 的归属不是具名商人" % (row["best"][1]["start"],
                                                          row["best"][1]["end"])
            else:
                why = "没有任何脚本声明它属于哪个货架"
            note = "%s；%s，未落点" % (base, why)
        m = {"id": "shop:%d" % row["id"], "cat": "shop_stock", "names": row["names"],
             "px": round(px, 1) if px is not None else None,
             "py": round(py, 1) if py is not None else None, "master": master,
             "price": row["value"], "qty": row["qty"], "stockFlag": row["stock"],
             "row": row["id"], "via": "shop-stock", "note": note}
        if row["best"] is not None:
            m["range"] = [row["best"][1]["start"], row["best"][1]["end"]]
            rec = row["best"][0][1]
            if rec is not None:
                m["ownerNpc"] = rec["npc"]
                m["ownerMap"] = rec["map"]
                m["ownerPart"] = rec["part"]
        markers.append(m)
    dvd.close()

    out = os.path.join(ROOT, "data", "shop-stock.json")
    layers.write_layer("shop-stock", markers)
    print("-> %s  (%d bytes)" % (out, os.path.getsize(out)))
    print()
    print("placed %d / %d rows" % (placed, len(markers)))
    for m in markers:
        print("   row %-8d %-10s %-20s %s" % (m["row"], m["names"]["zh"],
                                              "px=%.1f py=%.1f %s" % (m["px"], m["py"], m["master"])
                                              if m["px"] is not None else "no position",
                                              m["note"][:88]))
    print()
    print("why the unplaced rows have no owner:")
    for row in rows:
        if row["best"] is not None and row["best"][0][1] is not None:
            continue
        talks = ", ".join("t%d" % d["talk"] for _s, d in row["all"]) or "nothing declares this row"
        print("   row %-8d %s" % (row["id"], talks))


if __name__ == "__main__":
    main()
