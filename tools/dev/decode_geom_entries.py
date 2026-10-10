"""Decode the FOEG entries of m12_01_00 through AssetEnvironmentGeometryParam.

The technical docs (read-only reference) define WorldGeomEntry as 8 bytes:
    key   = instance << 15 | state
    model = 10000000 + AEG id          (AEGxxx_yyy = xxx*1000 + yyy)
and say the permanent one-time nodes are assets in AssetEnvironmentGeometryParam with a
pickUpItemLotParamId and isEnableRepick == 1 - "Arteria Leaf, smithing and somber smithing
stones, Grave and Ghost Glovewort, Trina's and Miquella's Lily, butterflies, ...".

So: decode each entry to (instance, AEG id), find that AEG row, and locate the lot id inside it
(without a paramdef, by testing which u32 in the row is a known ItemLotParam row). Then print
what the lot awards - if one awards 10910/10912/10902, the missing glovewort is found.
"""
import io
import os
import struct
import sys

sys.path.insert(0, r"C:\Users\13541\Desktop\AI工作\EldenRingMap\EldenRingMap-zh-main\tools")
sys.path.insert(0, r"C:\Users\13541\Desktop\AI工作\EldenRingMap\EldenRingMap-zh-main\tools\dev")
sys.stdout.reconfigure(encoding="utf-8")
from erlib import fmg, oodle, param, paramdef      # noqa: E402
import erlib.modfiles as modfiles                   # noqa: E402
from erlib.dvdbnd import DvdBnd                     # noqa: E402
from erlib.gamepath import require_game_dir         # noqa: E402
import er_save                                      # noqa: E402

ROOT = r"C:\Users\13541\Desktop\AI工作\EldenRingMap\EldenRingMap-zh-main"
SAVE = r"C:\Users\13541\Desktop\ER0000.sl2"
MAP_BYTES = bytes((0, 0, 1, 12))
TAB = {1: "GoodsName", 2: "WeaponName", 3: "ProtectorName", 4: "AccessoryName", 5: "GemName"}


def main():
    data = io.open(SAVE, "rb").read()
    groups = er_save.load_flag_groups(os.path.join(ROOT, "data", "eventflag_bst.txt"))
    best = None
    for idx in range(len(er_save.read_entries(data))):
        try:
            pay = er_save.slot_payload(data, idx)
            n = sum(1 for _ in er_save.EventFlags(pay, groups).iter_set())
        except Exception:
            continue
        if n and (best is None or n > best[0]):
            best = (n, idx, pay)
    n, idx, pay = best
    pos = er_save.read_position(pay)
    print("slot %d (%d flags); player %s (%.1f, %.1f, %.1f)"
          % (idx, n, pos["map_id"], pos["x"], pos["y"], pos["z"]))
    i = pay.find(b"FOEG")
    j = pay.find(MAP_BYTES, i)
    rec_size, count, unknown = struct.unpack_from("<3I", pay, j + 4)
    print("FOEG record: record_size=%d n=%d unknown=%d" % (rec_size, count, unknown))
    entries = []
    for k in range(count):
        key, model = struct.unpack_from("<2I", pay, j + 16 + 8 * k)
        entries.append((key, model, key >> 15, key & 0x7FFF, model - 10000000))
    for key, model, inst, state, aeg in entries:
        print("   key=0x%08X state=%d instance=%-6d model=%-10d AEG id=%-8d -> AEG%03d_%03d_%d"
              % (key, state, inst, model, aeg, aeg // 1000, aeg % 1000, inst))

    game = require_game_dir(None)
    mod = modfiles.find_mod_dir(None)
    dvd = DvdBnd(game, cache_dir=os.path.join(ROOT, "cache"), verbose=False)
    helper = oodle.make_helper(game)
    params = param.load_params(modfiles.regulation_path(game, mod))
    print("\nAssetEnvironmentGeometryParam loaded: %s" % ("AssetEnvironmentGeometryParam" in params))
    if "AssetEnvironmentGeometryParam" not in params:
        dvd.close()
        return
    tbl = params["AssetEnvironmentGeometryParam"]
    lots = set()
    for t in ("ItemLotParam_map", "ItemLotParam_enemy"):
        lots |= {r.id for r in params[t].rows}
    ld = paramdef.load(os.path.join(ROOT, "data", "paramdefs", "ItemLotParam.xml"))
    names = {}
    for f in ("item.msgbnd.dcx", "item_dlc02.msgbnd.dcx"):
        p = "/msg/zhocn/%s" % f
        if modfiles.has(dvd, mod, p):
            for k, v in fmg.load_msgbnd(modfiles.read(dvd, mod, p), oodle=helper).items():
                names.setdefault(k.split("_dlc")[0], {}).update(v)

    def item_name(iid, kind):
        for t in [TAB.get(kind, "")] + ["GoodsName", "WeaponName", "ProtectorName",
                                        "AccessoryName", "GemName"]:
            v = (names.get(t) or {}).get(iid, "") if t else ""
            if v and "[ERROR]" not in v:
                return v
        return ""

    rows = {r.id: r for r in tbl.rows}
    print("AssetEnvironmentGeometryParam rows: %d" % len(rows))
    for key, model, inst, state, aeg in entries:
        r = rows.get(aeg)
        if r is None:
            print("   AEG id %-8d : no row in AssetEnvironmentGeometryParam" % aeg)
            continue
        raw = bytes(r.data)
        found = []
        for off in range(0, len(raw) - 3, 4):
            v = struct.unpack_from("<I", raw, off)[0]
            if v in lots:
                found.append((off, v))
        desc = []
        for off, v in found:
            row = None
            for t in ("ItemLotParam_map", "ItemLotParam_enemy"):
                for rr in params[t].rows:
                    if rr.id == v:
                        row = rr
                        break
                if row:
                    break
            items = []
            if row is not None:
                for k in range(1, 9):
                    iid = ld.get(row.data, "lotItemId%02d" % k)
                    if iid:
                        items.append("%d %s" % (iid, item_name(iid, ld.get(row.data, "lotItemCategory%02d" % k))))
            desc.append("off+0x%X lot=%d -> %s" % (off, v, items))
        print("   AEG%03d_%03d_%-6d -> %s" % (aeg // 1000, aeg % 1000, inst,
                                              "; ".join(desc) if desc else "no lot-like field found"))
    dvd.close()


if __name__ == "__main__":
    main()
