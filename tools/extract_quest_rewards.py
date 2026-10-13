"""Script-granted items: find out how each one is actually handed over, and give every entry a verdict.

These are the lots whose getItemFlagId is set in the player's save but which no world object references:
no chest, no gatherable node, no placed character, no farm spot. The old version of this tool guessed a
map out of the lot number and anchored at that map's grace, which worked for none of them, and left the
rest as "granted by a quest or a script, no coordinates".

This version collects evidence instead, from the game's own files, and records it per entry:

  1. event-instruction  an EMEVD instruction has the lot id as an operand. Only lots of six digits or
                        more are trusted: small ids collide with the constants that appear everywhere
                        (the cheap check matched lot 2000 in 9,929 places).
  2. event-record       the lot appears in an EMEVD parameter record shaped (type, entity, entityFlag,
                        lot) with entity == entityFlag > 1000. That is the shape the EMEVD drop layer
                        already uses, and it finds 199/199 lots that are independently known to be
                        granted by an event.
  3. event-flag         an EMEVD instruction carries the item's own getItemFlagId, so that event is what
                        sets the flag the item comes with.
  4. shop               a ShopLineupParam row sells the item; the marker goes on the merchant that owns
                        that shelf when data/shop-stock.json knows one.
  5. starting           the flag is in the 60000-60999 block, which the game sets before you ever move.
  6. unreferenced       nothing in the game's data mentions the lot, its flag or the item as a grant.

1-3 are anchored to the entity's own marker when a placed marker carries that entity, else to the boss
of that event's map, else to its first grace, and the note says which. 4 goes to the merchant. 5 and 6
are registered without coordinates, with the block their flag lives in, rather than invented.

Output: data/quest-rewards.json (the ones with a position) and data/quest-rewards-unplaced.json (every
other entry, each with its verdict and evidence).
"""
from __future__ import annotations

import io
import json
import os
import struct
import sys
from collections import Counter, defaultdict

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)
sys.path.insert(0, os.path.join(HERE, "dev"))
from erlib import dcx, emevd, fmg, oodle, param, paramdef   # noqa: E402
import erlib.gamefiles as gamefiles                          # noqa: E402
from erlib.dvdbnd import DvdBnd                              # noqa: E402
from erlib.gamepath import require_game_dir                  # noqa: E402
from erlib import layers                                     # noqa: E402
from build_markers import LegacyConv, place                  # noqa: E402
import er_save                                               # noqa: E402

ROOT = os.path.dirname(HERE)
TABLE_OF_KIND = {1: "GoodsName", 2: "WeaponName", 3: "ProtectorName",
                 4: "AccessoryName", 5: "GemName"}
# categories that already exist in the UI
PROGRESSION = ("卢恩", "追忆", "钥匙", "符节", "铃珠", "地图", "记忆石", "灵马", "召魂")
MIN_TRUSTED_LOT = 100000        # below this a lot id is not distinctive enough to search for
START_BLOCK = (60000, 61000)    # flags the game sets at character creation

VERDICTS = {
    "event-instruction": "事件脚本指令里出现该物品的 lot（位置取该实体/该图 Boss/赐福）",
    "event-record": "事件脚本数据记录里出现该 lot（位置取该实体/该图 Boss/赐福）",
    "event-flag": "事件脚本指令里出现该物品的旗标（位置取该事件所在图的 Boss/赐福）",
    "shop": "由商人货架出售（位置取货架所属商人）",
    "lot-map": "lot 编号里带地图位：按 ItemLotParam_map 的编号规律落在该图的 Boss/赐福",
    "starting": "开局即持有：旗标属 60000–60999 段，游戏在角色创建时设置，没有世界物件",
    "unreferenced": "游戏数据里没有任何脚本、世界物件或商店行引用它；只能记下它来自哪一段旗标",
}


def load_markers(name):
    p = os.path.join(ROOT, "data", name)
    if not os.path.isfile(p):
        return []
    with io.open(p, encoding="utf-8") as fh:
        return json.load(fh).get("markers") or []


def flag_block_profile():
    """-> flag block (flag // 1000 * 1000) -> what the markers that share it are.

    Used to say something concrete about the entries nothing references: the flag an item carries is
    set when it is obtained, so the block it lives in is all the game's data tells us - and the blocks
    that are already populated by placed markers (boss rewards, shop sales, gathering nodes) name the
    family the entry belongs to.
    """
    profile = defaultdict(Counter)
    for name in ("items.json", "drops.json", "boss-drops.json", "emevd-drops.json", "followup.json",
                 "gather-nodes.json", "farm.json", "markers.json"):
        for m in load_markers(name):
            flag = m.get("flag") or 0
            if flag:
                profile[flag // 1000 * 1000][m.get("cat") or "?"] += 1
    return profile


def map_anchors():
    """-> map id -> the boss marker of that map, else its first grace."""
    out = {}
    for m in load_markers("markers.json"):
        if m.get("px") is None or not m.get("map"):
            continue
        if m["cat"] == "boss" and m["map"] not in out:
            out[m["map"]] = (m, "boss")
    for m in load_markers("markers.json"):
        if m.get("px") is None or not m.get("map"):
            continue
        if m["cat"] == "grace" and m["map"] not in out:
            out[m["map"]] = (m, "grace")
    return out


def entity_positions():
    """-> entity id -> a placed marker of that entity, from every layer that records one."""
    out = {}
    for name in ("drops.json", "emevd-drops.json", "boss-drops.json", "items.json", "followup.json"):
        for m in load_markers(name):
            ent = m.get("entity")
            if ent and m.get("px") is not None and ent not in out:
                out[ent] = m
    return out


def shop_index():
    """-> row id -> the shop-stock marker that declares the shelf the row belongs to.

    Each shelf marker carries the row range its talk script declares, so any row of that shelf maps to
    the merchant who owns it.
    """
    out = {}
    p = os.path.join(ROOT, "data", "shop-stock.json")
    if not os.path.isfile(p):
        return out
    with io.open(p, encoding="utf-8") as fh:
        for m in json.load(fh).get("markers") or []:
            rng = m.get("range")
            if rng and len(rng) == 2:
                for row in range(int(rng[0]), int(rng[1]) + 1):
                    out[row] = m
    return out


def lot_map_candidates(lot, maps_with_anchor):
    """-> the map ids whose area/grid digits the lot carries, best first.

    ItemLotParam_map ids encode the map as <lead><area:2><grid:2><seq:4> with a two-digit lead of 10
    (base overworld), 20 (DLC overworld), 30 (underground) or 60. That is the reading that matches
    1,669 of the 6,958 lots already placed by other layers; the older `// 10_000_000` reading matches
    18. The lead also says which map family the lot belongs to, which resolves most of the cases where
    a base-game and a DLC map share an area/grid pair.
    """
    digits = str(lot)
    if len(digits) < 9 or digits[:2] not in ("10", "20", "30", "60"):
        return []
    area = lot // 1_000_000 % 100
    grid = lot // 10_000 % 100
    if not area:
        return []
    found = sorted(m for m in maps_with_anchor
                   if m[4:6] == "%02d" % area and m[7:9] == "%02d" % grid)
    family = {"10": "m6", "20": "m6", "30": "m3", "60": "m6"}[digits[:2]]
    preferred = [m for m in found if m.startswith(family)]
    return preferred + [m for m in found if m not in preferred]


def scan_events(dvd, helper, lots, flags):
    """Walk every event file once; return per-lot evidence.

    -> {value: {"instructions": [...], "records": [...], "files": {...}}}
    """
    ev = defaultdict(lambda: {"instructions": [], "records": [], "flagInstructions": []})
    maps = [line.split()[0] for line in
            io.open(os.path.join(ROOT, "cache", "map-list.txt"), encoding="utf-8")
            if line.strip().startswith("m")]
    needles = {v: struct.pack("<i", v) for v in (set(lots) | set(flags))}
    files_read = 0
    for name in ["common", "common_macro"] + maps:
        path = "/event/%s.emevd.dcx" % name
        if not gamefiles.has(dvd, path):
            continue
        try:
            raw = dcx.decompress(gamefiles.read(dvd, path), oodle=helper)
        except Exception:
            continue
        if not emevd.is_emevd(raw):
            continue
        files_read += 1
        h = emevd.read_header(raw)
        ins_start = h["instructionOffset"]
        ins_end = ins_start + h["instructionCount"] * 32
        for value, needle in needles.items():
            at = raw.find(needle)
            while at >= 0:
                if ins_start <= at < ins_end:
                    slot = (at - ins_start) % 32
                    base = at - slot
                    bank, iid = struct.unpack_from("<2i", raw, base)
                    args = list(struct.unpack_from("<6i", raw, base + 8))
                    rec = {"file": name, "bank": bank, "id": iid, "args": args}
                    key = "instructions" if value in lots else "flagInstructions"
                    ev[value][key].append(rec)
                at = raw.find(needle, at + 1)
        # parameter records: (type, entity, entityFlag, lot)
        blob = raw[h["paramOffset"]:]
        words = list(struct.unpack_from("<%di" % (len(blob) // 4), blob, 0))
        for k in range(len(words) - 3):
            _type, ent, eflag, lot = words[k:k + 4]
            if lot in lots and lot >= MIN_TRUSTED_LOT and ent == eflag and ent > 1000:
                ev[lot]["records"].append({"file": name, "entity": ent, "flag": eflag})
    print("event files read: %d" % files_read)
    return ev


def main():
    save = sys.argv[1] if len(sys.argv) > 1 else None
    if not save:
        import glob
        cands = glob.glob(os.path.join(os.environ.get("APPDATA", ""), "EldenRing", "*",
                                       "ER0000.sl2"))
        save = cands[0] if cands else None
    if not save or not os.path.isfile(save):
        sys.exit("no save found")
    print("save: %s" % save)

    data = io.open(save, "rb").read()
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
            best = (n, idx, fl)
    if best is None:
        sys.exit("no non-empty slot")
    nflags, slot, flags = best
    print("slot %d (%d flags set)" % (slot, nflags))

    game = require_game_dir(None)
    dvd = DvdBnd(game, cache_dir=os.path.join(ROOT, "cache"), verbose=False)
    helper = oodle.make_helper(game)
    params = param.load_params(gamefiles.regulation_path(game))
    ld = paramdef.load(os.path.join(ROOT, "data", "paramdefs", "ItemLotParam.xml"))

    texts = {}
    for loc, tag in (("zh", "zhocn"), ("en", "engus")):
        t = {}
        for f in ("item.msgbnd.dcx", "item_dlc02.msgbnd.dcx"):
            p = "/msg/%s/%s" % (tag, f)
            if gamefiles.has(dvd, p):
                for k, v in fmg.load_msgbnd(gamefiles.read(dvd, p), oodle=helper).items():
                    t.setdefault(k.split("_dlc")[0], {}).update(v)
        texts[loc] = t

    def item_name(iid, kind, loc):
        tab = TABLE_OF_KIND
        for t in [tab.get(kind, "")] + list(tab.values()):
            v = (texts[loc].get(t) or {}).get(iid, "") if t else ""
            if v and "[ERROR]" not in v:
                return v
        return ""

    # lots already covered by another layer
    covered = set()
    for f in ("items.json", "drops.json", "boss-drops.json", "emevd-drops.json", "followup.json",
              "gather-nodes.json", "farm.json", "emevd-rewards.json"):
        for m in load_markers(f):
            if m.get("lot"):
                covered.add(m["lot"])

    # grace anchors per area/grid prefix from BonfireWarpParam (real coordinates)
    wd = paramdef.load(os.path.join(ROOT, "data", "paramdefs", "BonfireWarpParam.xml"))
    conv = LegacyConv(params["WorldMapLegacyConvParam"].rows,
                      paramdef.load(os.path.join(ROOT, "data", "paramdefs",
                                                "WorldMapLegacyConvParam.xml")))
    anchors = {}
    for r in params["BonfireWarpParam"].rows:
        v = wd.as_dict(r.data, ["areaNo", "gridXNo", "gridZNo", "posX", "posY", "posZ", "textId1"])
        if not v.get("areaNo"):
            continue
        q = place(v["areaNo"], v["gridXNo"], v["gridZNo"], v["posX"], v["posY"], v["posZ"], conv)
        if q is None:
            continue
        key = "m%02d_%02d" % (v["areaNo"], v["gridXNo"])
        anchors.setdefault(key, {"master": q[2], "px": round(q[0], 1), "py": round(q[1], 1),
                                 "h": round(q[3])})
    print("grace anchors: %d area/grid prefixes" % len(anchors))

    # ---- the candidates, before any anchoring
    candidates = []
    skipped_name = 0
    for tbl in ("ItemLotParam_map", "ItemLotParam_enemy"):
        for r in params[tbl].rows:
            flag = ld.get(r.data, "getItemFlagId")
            if not flag or not flags.get(flag) or r.id in covered:
                continue
            iid = kind = 0
            for i in range(1, 9):
                v = ld.get(r.data, "lotItemId%02d" % i)
                if v:
                    iid, kind = v, ld.get(r.data, "lotItemCategory%02d" % i)
                    break
            if not iid:
                continue
            zh = item_name(iid, kind, "zh")
            en = item_name(iid, kind, "en")
            if not zh and not en:
                skipped_name += 1
                continue
            candidates.append({"lot": r.id, "flag": flag, "item": iid, "kind": kind,
                               "zh": zh or en, "en": en or zh, "table": tbl})
    print("candidates: %d (skipped, no name: %d)" % (len(candidates), skipped_name))

    # ---- evidence
    lots = {c["lot"] for c in candidates}
    reward_flags = {c["flag"] for c in candidates}
    ev = scan_events(dvd, helper, lots, reward_flags)

    # shop rows: which item ids are sold, and by which shelf. The kind has to agree with the row's
    # equipType or an id that happens to exist in another item table would look like a sale
    # (ShopLineupParam's numbering is its own: 0 weapon, 1 protector, 2 accessory, 3 goods, 4 gem).
    shop_def = paramdef.load(os.path.join(ROOT, "data", "paramdefs", "ShopLineupParam.xml"))
    kind_to_equip_type = {2: 0, 3: 1, 4: 2, 1: 3, 5: 4}
    shops = defaultdict(list)
    for r in params["ShopLineupParam"].rows:
        v = shop_def.as_dict(r.data, ("equipId", "equipType", "value", "sellQuantity"))
        if v.get("equipId"):
            shops[int(v["equipId"])].append({"row": int(r.id), "equipType": v.get("equipType", 3),
                                             "price": v.get("value"), "qty": v.get("sellQuantity")})
    shelf_by_row = shop_index()
    ent_pos = entity_positions()
    map_anchor = map_anchors()
    maps_with_anchor = set(map_anchor)
    block_profile = flag_block_profile()

    def block_note(flag):
        """What the game's own data says about the flag block this entry lives in."""
        block = flag // 1000 * 1000
        top = block_profile.get(block)
        if not top:
            return "（旗标段 %dxxx：游戏数据里没有其它已落点标记使用该段）" % (block // 1000)
        rows = "、".join("%s×%d" % (cat, n) for cat, n in top.most_common(3))
        return "（旗标段 %dxxx：同段已落点标记 %d 个，多为 %s）" % (block // 1000,
                                                                  sum(top.values()), rows)

    print("shop rows: %d items ; placed entities: %d ; maps with an anchor: %d ; flag blocks seen: %d"
          % (len(shops), len(ent_pos), len(map_anchor), len(block_profile)))

    markers, unplaced_list = [], []
    classes = Counter()
    blocks = defaultdict(Counter)
    for c in candidates:
        lot, flag, iid = c["lot"], c["flag"], c["item"]
        ins = ev[lot]["instructions"] if lot >= MIN_TRUSTED_LOT else []
        recs = ev[lot]["records"]
        flag_ins = ev[flag]["flagInstructions"]
        sold = [s for s in (shops.get(iid) or [])
                if s["equipType"] == kind_to_equip_type.get(c["kind"])]
        lot_maps = lot_map_candidates(lot, maps_with_anchor)
        verdict = None
        anchor = None
        evidence = None
        if ins:
            verdict = "event-instruction"
            hit = ins[0]
            evidence = "m=%s bank=%d id=%d args=%s" % (hit["file"], hit["bank"], hit["id"],
                                                        hit["args"])
            for value in hit["args"]:
                if value in ent_pos:
                    anchor = ("entity", ent_pos[value])
                    break
            if anchor is None:
                a = map_anchor.get(hit["file"])
                anchor = ("map:" + hit["file"], a[0]) if a else None
        elif recs:
            verdict = "event-record"
            hit = recs[0]
            evidence = "m=%s entity=%d flag=%d" % (hit["file"], hit["entity"], hit["flag"])
            if hit["entity"] in ent_pos:
                anchor = ("entity", ent_pos[hit["entity"]])
            else:
                a = map_anchor.get(hit["file"])
                anchor = ("map:" + hit["file"], a[0]) if a else None
        elif flag_ins:
            verdict = "event-flag"
            hit = flag_ins[0]
            evidence = "m=%s bank=%d id=%d args=%s" % (hit["file"], hit["bank"], hit["id"],
                                                        hit["args"])
            for value in hit["args"]:
                if value in ent_pos:
                    anchor = ("entity", ent_pos[value])
                    break
            if anchor is None:
                a = map_anchor.get(hit["file"])
                anchor = ("map:" + hit["file"], a[0]) if a else None
        elif sold:
            verdict = "shop"
            row = sold[0]
            shelf = shelf_by_row.get(row["row"])
            evidence = "ShopLineupParam row %d (equipType %s, price %s, qty %s)" % (
                row["row"], row["equipType"], row["price"], row["qty"])
            if shelf and shelf.get("px") is not None:
                anchor = ("shelf", shelf)
                if shelf.get("names"):
                    evidence += "；货架归 %s" % shelf["names"]["zh"]
        elif lot_maps:
            verdict = "lot-map"
            mid = lot_maps[0]
            a = map_anchor.get(mid)
            evidence = "lot %d -> %s%s" % (lot, mid,
                                           "" if len(lot_maps) == 1
                                           else "（%d 张图共用该编号位）" % len(lot_maps))
            anchor = ("map:" + mid, a[0]) if a else None
        elif START_BLOCK[0] <= flag < START_BLOCK[1]:
            verdict = "starting"
        else:
            verdict = "unreferenced"
        if verdict in ("event-instruction", "event-record", "event-flag") and anchor is None:
            verdict = "unreferenced"
            evidence = (evidence or "") + " (no anchor for that map)"

        classes[verdict] += 1
        blocks[verdict][flag // 1000 * 1000] += 1

        if anchor is not None:
            src, m = anchor
            mk = {
                "id": "quest:%d" % lot,
                "cat": "progression" if any(x in c["zh"] for x in PROGRESSION) else "misc",
                "names": {"zh": c["zh"], "en": c["en"]},
                "flag": flag, "lot": lot, "item": iid,
                "master": m.get("master"), "px": m["px"], "py": m["py"], "h": m.get("h"),
                "map": m.get("map"), "via": "quest-" + verdict,
                "verdict": verdict,
                "note": VERDICTS[verdict] + ("（%s）" % evidence if evidence else ""),
            }
            if src == "entity":
                mk["anchor"] = "entity"
            elif src.startswith("map:"):
                mk["anchor"] = "boss/grace of " + src[4:]
            markers.append(mk)
        else:
            unplaced_list.append({
                "id": "quest-unplaced:%d" % lot,
                "cat": "unplaced",
                "names": {"zh": c["zh"], "en": c["en"]},
                "flag": flag, "lot": lot, "item": iid,
                "px": None, "py": None, "master": None,
                "via": "quest-" + verdict,
                "verdict": verdict,
                "block": flag // 1000 * 1000,
                "itemKind": c["kind"],
                "note": VERDICTS[verdict] + block_note(flag),
            })

    layers.write_layer("quest-rewards", markers)
    layers.write_layer("quest-rewards-unplaced", unplaced_list)
    print()
    print("verdicts (%d entries):" % len(candidates))
    for verdict, n in classes.most_common():
        print("   %-18s %4d   flag blocks %s" % (verdict, n, blocks[verdict].most_common(3)))
    print("placed: %d ; registered without a position: %d" % (len(markers), len(unplaced_list)))
    print("by category: %s" % dict(Counter(m["cat"] for m in markers).most_common()))
    for m in markers[:8]:
        print("   %-22s %-11s lot=%-10s flag=%-12s %s"
              % (m["names"]["zh"], m["cat"], m["lot"], m["flag"], m["note"][:60]))
    dvd.close()


if __name__ == "__main__":
    main()
