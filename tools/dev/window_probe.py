"""How does the boss-reward window change the result?

The scan looks +/- BOSS_WINDOW bytes around a boss's defeat flag inside that boss's
own .emevd for a flagged ItemLotParam_map row, then keeps a lot only if it sits near
exactly one boss and appears in exactly one .emevd. Narrowing the window can only
drop candidates, so the question is whether what it drops is noise or real loot - the
Bell Bearing Hunter's own rewards, for instance, are real and sit in the current set.

Prints the surviving set per window and the differences against the widest one, with
the boss and item names, so the answer is data rather than a guess.
"""
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

WINDOWS = [64, 96, 128, 192, 256]

# Report to a UTF-8 file: the console mangles Chinese here.
import io as _io
PROBE_OUT = _io.open(r"C:\\Users\\13541\\Desktop\\AI工作\\EldenRingMap\\_window_probe.txt",
                     "w", encoding="utf-8")
sys.stdout = PROBE_OUT
DEFS = os.path.join(ROOT, "data", "paramdefs")

game = require_game_dir(None)
mod = modfiles.find_mod_dir(None)
dvd = DvdBnd(game, cache_dir=os.path.join(ROOT, "cache"), verbose=False)
helper = oodle.make_helper(game)
params = param.load_params(modfiles.regulation_path(game, mod))
lot_def = paramdef.load(os.path.join(DEFS, "ItemLotParam.xml"))
ga_def = paramdef.load(os.path.join(DEFS, "GameAreaParam.xml"))
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
boss_markers = {}
with open(os.path.join(ROOT, "data", "markers.json"), encoding="utf-8") as f:
    for m in json.load(f).get("markers", []):
        if m.get("cat") == "boss" and m.get("flag"):
            boss_markers[m["flag"]] = m
boss_files, flag_file = defaultdict(set), {}
for r in params["GameAreaParam"].rows:
    flag = ga_def.get(r.data, "defeatBossFlagId")
    if not flag or flag not in boss_markers:
        continue
    mid = "m%02d_%02d_%02d_00" % (ga_def.get(r.data, "bossMapAreaNo"),
                                 ga_def.get(r.data, "bossMapBlockNo"),
                                 ga_def.get(r.data, "bossMapMapNo"))
    flag_file[flag] = mid
    boss_files[mid].add(flag)
print("boss map files: %d, boss flags: %d" % (len(boss_files), len(flag_file)))

raw_events = {}
for mid in sorted(boss_files):
    path = "/event/%s.emevd.dcx" % mid
    if not modfiles.has(dvd, mod, path):
        continue
    try:
        raw_events[mid] = dcx.decompress(modfiles.read(dvd, mod, path), oodle=helper)
    except Exception:
        pass
print("emevd files read: %d" % len(raw_events))


def item_label(lot_id):
    row = lots.get(lot_id)
    if row is None:
        return "?"
    for i in range(1, 9):
        iid = lot_def.get(row.data, "lotItemId%02d" % i)
        if iid:
            c = lot_def.get(row.data, "lotItemCategory%02d" % i)
            return CAT.get(c, {}).get(iid, "id %s" % iid)
    return "(空 lot)"


def survivors(window):
    near = defaultdict(set)
    for mid in raw_events:
        raw = raw_events[mid]
        for flag in boss_files[mid]:
            packed = struct.pack("<I", flag)
            i = raw.find(packed)
            while i != -1:
                for delta in range(-window, window + 1, 4):
                    j = i + delta
                    if 0 <= j <= len(raw) - 4:
                        lot_id = struct.unpack_from("<I", raw, j)[0]
                        if lot_id in flagged:
                            near[lot_id].add(flag)
                i = raw.find(packed, i + 1)
    out = {}
    for lot_id, flags in near.items():
        if len(flags) != 1:
            continue
        if sum(1 for raw in raw_events.values() if struct.pack("<I", lot_id) in raw) != 1:
            continue
        out[lot_id] = next(iter(flags))
    return out


sets = {}
for w in WINDOWS:
    sets[w] = survivors(w)
    print("window %-3d -> 存活 lot %d" % (w, len(sets[w])))

base = sets[max(WINDOWS)]
print()
for w in WINDOWS:
    lost = {k: v for k, v in base.items() if k not in sets[w]}
    extra = {k: v for k, v in sets[w].items() if k not in base}
    print("window %-3d: 比 %d 少 %d 个, 多 %d 个" % (w, max(WINDOWS), len(lost), len(extra)))
    for lot_id, flag in sorted(lost.items())[:8]:
        boss = boss_markers.get(flag, {}).get("names", {}).get("zh", "?")
        print("      丢失 lot %-11s %-22s ← %s" % (lot_id, item_label(lot_id), boss))
    for lot_id, flag in sorted(extra.items())[:14]:
        boss = boss_markers.get(flag, {}).get("names", {}).get("zh", "?")
        print("      多出 lot %-11s %-22s ← %s" % (lot_id, item_label(lot_id), boss))
dvd.close()
