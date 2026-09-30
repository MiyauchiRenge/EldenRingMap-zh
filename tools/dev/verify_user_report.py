"""Check the two things the user reported, and record the outcomes.

  1. 墓地影子 area: a secret room south of it holds a 猎犬骑士 (Bloodhound Knight)
     whose kill gives the Bloodhound Knight set, and a sarcophagus carrying the Gelmir
     Knight set. So lot 30090050 (Gelmir Knight Helm), which the candidate tool ranked
     as a strong candidate for 英雄的红狼 because only that boss is near it, is in fact
     a pickup - the candidate must be recorded as rejected.
  2. The drop list the user gave: 5400 runes and 拉达冈的烙印 (Radagon's Scarseal). It
     has to be checked which boss that belongs to and whether the lot exists.
"""
import io
import json
import os
import struct
import sys
from collections import defaultdict

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.abspath(os.path.join(HERE, "..", ".."))
sys.path.insert(0, os.path.join(HERE, ".."))

from erlib import dcx, fmg, oodle, param, paramdef
import erlib.modfiles as modfiles
from erlib.dvdbnd import DvdBnd
from erlib.gamepath import require_game_dir

WANT_ITEMS = ("拉达冈的烙印", "拉达冈的糜烂烙印", "格密尔骑士", "猎犬骑士", "血猎犬")
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


def lots_with(pred):
    out = []
    for r in params["ItemLotParam_map"].rows:
        for i in range(1, 9):
            iid = lot_def.get(r.data, "lotItemId%02d" % i)
            if not iid:
                continue
            c = lot_def.get(r.data, "lotItemCategory%02d" % i)
            nm = CAT.get(c, {}).get(iid, "")
            if nm and pred(nm):
                out.append((r.id, nm, c, lot_def.get(r.data, "getItemFlagId")))
                break
    return out


for want in ("拉达冈的烙印", "拉达冈的糜烂烙印", "格密尔骑士头盔", "猎犬骑士"):
    hits = [h for h in lots_with(lambda n, w=want: w in n)]
    print("%-14s 出现在 %d 个 map lot: %s" % (want, len(hits), hits[:4]))

# which boss flags sit near the 拉达冈的烙印 lot / the gelmir lot
print()
targets = {h[0]: h[1] for h in lots_with(lambda n: "拉达冈的烙印" in n or "格米尔骑士头盔" in n
                                         or "格密尔骑士头盔" in n)}
bosses = {}
for m in json.load(open(os.path.join(ROOT, "data", "markers.json"), encoding="utf-8"))["markers"]:
    if m.get("cat") == "boss" and m.get("flag"):
        bosses.setdefault(m["flag"], m)
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

for mid in sorted(boss_files):
    path = "/event/%s.emevd.dcx" % mid
    if not modfiles.has(dvd, mod, path):
        continue
    try:
        raw = dcx.decompress(modfiles.read(dvd, mod, path), oodle=helper)
    except Exception:
        continue
    for lid, label in targets.items():
        packed = struct.pack("<I", lid)
        pos = raw.find(packed)
        if pos < 0:
            continue
        # nearest boss flag in this file to that position
        best = None
        for flag in boss_files[mid]:
            fp = struct.pack("<I", flag)
            q = raw.find(fp)
            while q != -1:
                d = abs(q - pos)
                if best is None or d < best[0]:
                    best = (d, flag)
                q = raw.find(fp, q + 1)
        if best:
            print("lot %-10s %-18s 在 %-14s 最近 Boss: %-24s 距离 %d 字节"
                  % (lid, label[:16], mid, bosses[best[1]]["names"]["zh"][:22], best[0]))
dvd.close()
