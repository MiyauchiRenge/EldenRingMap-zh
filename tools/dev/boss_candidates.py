"""Candidate boss drops for a human to check in game: tools/dev/boss_candidates.py

What it does: for every boss marker that has no attributed drop yet, scan that boss's
own .emevd around its defeat flag and list the flagged ItemLotParam_map rows nearby,
nearest first, with their items and their distance in bytes. Nothing is written into
data/ - the output is a question list for the user, because attributing a reward the
scripts do not tie to a boss needs either a human check or a curated entry.

Ranking: a lot whose items look like a unique reward (weapon, armour, talisman, ash of
war, key item) outranks one with plain consumables or materials, and a lot that no
other boss comes near outranks a shared one - the same two intuitions the real scan
uses, printed instead of applied.

    python tools/dev/boss_candidates.py            -> writes _boss_candidates.txt
"""
import io
import json
import os
import struct
import sys
from collections import Counter, defaultdict

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.abspath(os.path.join(HERE, "..", ".."))
sys.path.insert(0, os.path.join(HERE, ".."))

from erlib import dcx, fmg, oodle, param, paramdef
import erlib.modfiles as modfiles
from erlib.dvdbnd import DvdBnd
from erlib.gamepath import require_game_dir

OUT = io.open(os.path.join(ROOT, "..", "_boss_candidates.txt"), "w", encoding="utf-8")
WINDOW = 256
SURFACE = ("m10_", "m11_", "m12_", "m60_", "m61_")
# item categories worth reporting first (lotItemCategory: 2 weapon, 3 protector,
# 4 accessory, 5 gem, 1 goods)
INTERESTING = {2, 3, 4, 5}


def say(*a):
    print(*a, file=OUT)


game = require_game_dir(None)
mod = modfiles.find_mod_dir(None)
dvd = DvdBnd(game, cache_dir=os.path.join(ROOT, "cache"), verbose=False)
helper = oodle.make_helper(game)
params = param.load_params(modfiles.regulation_path(game, mod))
lot_def = paramdef.load(os.path.join(ROOT, "data", "paramdefs", "ItemLotParam.xml"))
ga_def = paramdef.load(os.path.join(ROOT, "data", "paramdefs", "GameAreaParam.xml"))
names = {}
for f in ("item.msgbnd.dcx", "item_dlc02.msgbnd.dcx"):
    p = "/msg/zhocn/%s" % f
    if modfiles.has(dvd, mod, p):
        for k, v in fmg.load_msgbnd(modfiles.read(dvd, mod, p), oodle=helper).items():
            names.setdefault(k.split("_dlc")[0], {}).update(v)
CAT = {1: names.get("GoodsName", {}), 2: names.get("WeaponName", {}),
       3: names.get("ProtectorName", {}), 4: names.get("AccessoryName", {}),
       5: names.get("GemName", {})}

lots = {r.id: r for r in params["ItemLotParam_map"].rows}
flagged = {i: r for i, r in lots.items() if lot_def.get(r.data, "getItemFlagId")}
bosses = {}
for m in json.load(open(os.path.join(ROOT, "data", "markers.json"), encoding="utf-8"))["markers"]:
    if m.get("cat") == "boss" and m.get("flag"):
        bosses.setdefault(m["flag"], m)
# lots the user has already verified are NOT boss drops (data/boss-drop-overrides.json
# -> rejected): the tool must not propose them again.
rejected = set()
_ovp = os.path.join(ROOT, "data", "boss-drop-overrides.json")
if os.path.isfile(_ovp):
    for r in json.load(open(_ovp, encoding="utf-8")).get("rejected", []):
        if r.get("lot"):
            rejected.add(r["lot"])

attributed = set(rejected)
for f in ("boss-drops.json", "drops.json"):
    p = os.path.join(ROOT, "data", f)
    if os.path.isfile(p):
        for m in json.load(open(p, encoding="utf-8"))["markers"]:
            if m.get("lot"):
                attributed.add(m["lot"])

boss_files, flag_of = defaultdict(set), {}
for r in params["GameAreaParam"].rows:
    flag = ga_def.get(r.data, "defeatBossFlagId")
    if not flag or flag not in bosses:
        continue
    mid = "m%02d_%02d_%02d_00" % (ga_def.get(r.data, "bossMapAreaNo"),
                                 ga_def.get(r.data, "bossMapBlockNo"),
                                 ga_def.get(r.data, "bossMapMapNo"))
    boss_files[mid].add(flag)
    flag_of[flag] = mid

raw_events = {}
for mid in sorted(boss_files):
    path = "/event/%s.emevd.dcx" % mid
    if modfiles.has(dvd, mod, path):
        try:
            raw_events[mid] = dcx.decompress(modfiles.read(dvd, mod, path), oodle=helper)
        except Exception:
            pass

# every boss without a drop marker at its own spot
has_drop = set()
p = os.path.join(ROOT, "data", "boss-drops.json")
if os.path.isfile(p):
    for m in json.load(open(p, encoding="utf-8"))["markers"]:
        has_drop.add((round(m["px"]), round(m["py"])))
todo = [m for m in bosses.values()
        if (round(m["px"]), round(m["py"])) not in has_drop]
say("Boss 标记 %d 个，其中没有归属掉落的 %d 个" % (len(bosses), len(todo)))
say()

# map each lot to the set of bosses it sits near, to report sharing
lot_bosses = defaultdict(set)
for mid, raw in raw_events.items():
    for flag in boss_files[mid]:
        packed = struct.pack("<I", flag)
        i = raw.find(packed)
        while i != -1:
            for d in range(-WINDOW, WINDOW + 1, 4):
                j = i + d
                if 0 <= j <= len(raw) - 4:
                    lid = struct.unpack_from("<I", raw, j)[0]
                    if lid in flagged:
                        lot_bosses[lid].add(flag)
                        if flag in {m["flag"] for m in todo}:
                            pass
            i = raw.find(packed, i + 1)

report = []
for m in todo:
    flag = m["flag"]
    mid = flag_of.get(flag)
    raw = raw_events.get(mid or "")
    if raw is None:
        continue
    packed = struct.pack("<I", flag)
    found = {}
    i = raw.find(packed)
    while i != -1:
        for d in range(-WINDOW, WINDOW + 1, 4):
            j = i + d
            if 0 <= j <= len(raw) - 4:
                lid = struct.unpack_from("<I", raw, j)[0]
                if lid in flagged and lid not in attributed:
                    if lid not in found or abs(d) < abs(found[lid][0]):
                        found[lid] = (d, len(lot_bosses[lid]))
        i = raw.find(packed, i + 1)
    if not found:
        continue
    ranked = []
    for lid, (d, shared) in found.items():
        row = flagged[lid]
        items = []
        best_cat = 9
        for s in range(1, 9):
            iid = lot_def.get(row.data, "lotItemId%02d" % s)
            if not iid:
                continue
            c = lot_def.get(row.data, "lotItemCategory%02d" % s)
            items.append(CAT.get(c, {}).get(iid, "id %s" % iid))
            best_cat = min(best_cat, c if c in INTERESTING else 9)
        ranked.append((best_cat, shared, abs(d), lid, items, d, shared))
    ranked.sort()
    top = [r for r in ranked if r[0] != 9][:4] or ranked[:3]
    report.append((m, mid, top))

report.sort(key=lambda r: (r[0].get("map") or "").startswith(SURFACE))
for m, mid, top in report:
    inner = "内部" if not (m.get("map") or "").startswith(SURFACE) else "地表"
    say("%-26s %-10s %-14s flag=%s" % (m["names"]["zh"][:24], inner, (m.get("map") or "-")[:12], m["flag"]))
    for cat, shared, dist, lid, items, d, sh in top:
        say("     lot %-10s 距离 %+5d 字节  共享 Boss 数 %d  物品: %s"
            % (lid, d, sh, "、".join(items[:3])))
    say()
OUT.close()
dvd.close()
print("written")
