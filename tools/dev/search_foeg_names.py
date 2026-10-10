"""Search every part name in m12_01_00 for the FOEG identifiers (substring, not exact).

The FOEG entries are (packed, ident) with ident like 10099852 / 10099930 / 10099935. They are
not ItemLotParam ids and not row ids in any of the 194 param tables, so the remaining candidate
is a part/asset name in the map itself. My earlier match only tested the first 20 names and
required an exact numeric name; this searches all 11,817 names as substrings and prints any hit
with the part position, so a picked gatherable can be located by the game's own record.
"""
import io
import os
import struct
import sys

sys.path.insert(0, r"C:\Users\13541\Desktop\AI工作\EldenRingMap\EldenRingMap-zh-main\tools")
sys.path.insert(0, r"C:\Users\13541\Desktop\AI工作\EldenRingMap\EldenRingMap-zh-main\tools\dev")
sys.stdout.reconfigure(encoding="utf-8")
from erlib import dcx, msb as msblib, oodle          # noqa: E402
import erlib.modfiles as modfiles                     # noqa: E402
from erlib.dvdbnd import DvdBnd                       # noqa: E402
from erlib.gamepath import require_game_dir           # noqa: E402
import er_save                                        # noqa: E402

ROOT = r"C:\Users\13541\Desktop\AI工作\EldenRingMap\EldenRingMap-zh-main"
SAVE = r"C:\Users\13541\Desktop\ER0000.sl2"
MID = "m12_01_00_00"
MAP_BYTES = bytes((0, 0, 1, 12))


def foeg_entries(pay):
    i = pay.find(b"FOEG")
    j = pay.find(MAP_BYTES, i)
    size, count, total = struct.unpack_from("<3i", pay, j + 4)
    out = []
    for k in range(count):
        packed, ident = struct.unpack_from("<2I", pay, j + 16 + 8 * k)
        out.append((packed, ident))
    return count, total, out


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
    count, total, entries = foeg_entries(pay)
    idents = sorted({e[1] for e in entries})
    print("slot %d (%d flags); player %s (%.1f, %.1f, %.1f)"
          % (idx, n, pos["map_id"], pos["x"], pos["y"], pos["z"]))
    print("FOEG m12_01_00: count=%d part_total=%d ; distinct idents=%s" % (count, total, idents))

    game = require_game_dir(None)
    mod = modfiles.find_mod_dir(None)
    dvd = DvdBnd(game, cache_dir=os.path.join(ROOT, "cache"), verbose=False)
    helper = oodle.make_helper(game)
    m = msblib.load(dcx.decompress(modfiles.read(dvd, mod, "/map/mapstudio/%s.msb.dcx" % MID),
                                   oodle=helper))
    parts = list(m.entries("PARTS_PARAM_ST"))
    print("parts: %d" % len(parts))
    names = [(po, str(nm)) for po, nm in parts]
    patterns = [str(i) for i in idents]
    hits = 0
    for po, nm in names:
        for pat in patterns:
            if pat in nm:
                x, y, z = m.vec3(po + 0x20)
                d = ((x - pos["x"]) ** 2 + (y - pos["y"]) ** 2 + (z - pos["z"]) ** 2) ** 0.5
                print("   HIT name=%-24s ident=%s at (%.1f, %.1f, %.1f) dist %.1f"
                      % (nm, pat, x, y, z, d))
                hits += 1
                break
    print("name hits: %d" % hits)
    # fallback: does the number appear anywhere in the map's raw bytes?
    raw = dcx.decompress(modfiles.read(dvd, mod, "/map/mapstudio/%s.msb.dcx" % MID), oodle=helper)
    for ident in idents:
        p4 = struct.pack("<I", ident)
        cnt = raw.count(p4)
        print("   ident %-10d as u32 in map bytes: %d occurrence(s)" % (ident, cnt))
    # sample of non-terrain-looking names, to see what gatherables are called
    odd = [nm for _po, nm in names if not nm.startswith(("m0", "m1", "m2", "m3", "c0", "c1", "c2"))][:25]
    print("sample of other name shapes: %s" % odd)
    dvd.close()


if __name__ == "__main__":
    main()
