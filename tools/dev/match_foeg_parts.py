"""Match the FOEG entries of m12_01_00 to MSB parts and print their positions.

FOEG record layout (derived from the live save): [size, count, part_total, then count pairs of
(packed, identifier)]. The identifier looks like a part name/id in that map's MSB, so: read the
19 identifiers, list every part name in m12_01_00, and try exact / substring matches. Positions
come from the part record; the player's saved position (-61.4, -214.3, -122.9) is the cross-check.
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
PLAYER = (-61.4, -214.3, -122.9)


def main():
    data = io.open(SAVE, "rb").read()
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
            best = (n, idx, pay)
    n, idx, pay = best
    pos = er_save.read_position(pay)
    print("slot %d (%d flags); player at %s (%.1f, %.1f, %.1f)"
          % (idx, n, pos["map_id"], pos["x"], pos["y"], pos["z"]))
    i = pay.find(b"FOEG")
    j = pay.find(MAP_BYTES, i)
    size, count, total = struct.unpack_from("<3i", pay, j + 4)
    print("FOEG map record: size=%d count=%d part_total=%d" % (size, count, total))
    pairs = []
    for k in range(count):
        packed, ident = struct.unpack_from("<2I", pay, j + 16 + 8 * k)
        pairs.append((packed, ident))
    print("entries (%d):" % len(pairs))
    for packed, ident in pairs:
        print("   packed=%-12d (0x%08X)  ident=%-12d" % (packed, packed, ident))

    game = require_game_dir(None)
    mod = modfiles.find_mod_dir(None)
    dvd = DvdBnd(game, cache_dir=os.path.join(ROOT, "cache"), verbose=False)
    helper = oodle.make_helper(game)
    m = msblib.load(dcx.decompress(modfiles.read(dvd, mod, "/map/mapstudio/%s.msb.dcx" % MID),
                                   oodle=helper))
    parts = list(m.entries("PARTS_PARAM_ST"))
    print("parts in %s: %d" % (MID, len(parts)))
    names = [(po, nm) for po, nm in parts]
    sample = [nm for _po, nm in names[:20]]
    print("first part names: %s" % sample)
    ids = {p[1] for p in pairs}
    for po, nm in names:
        s = str(nm)
        if s.isdigit() and int(s) in ids:
            x, y, z = m.vec3(po + 0x20)
            d = ((x - pos["x"]) ** 2 + (y - pos["y"]) ** 2 + (z - pos["z"]) ** 2) ** 0.5
            print("   MATCH part name %s at (%.1f, %.1f, %.1f)  dist to player %.1f"
                  % (s, x, y, z, d))
    # also match on the numeric suffix of names like AEG099_630
    suffix = {}
    for po, nm in names:
        s = str(nm)
        if "_" in s and s.rsplit("_", 1)[-1].isdigit():
            suffix.setdefault(int(s.rsplit("_", 1)[-1]), []).append((po, s))
    hit = 0
    for packed, ident in pairs:
        for key in (ident, packed & 0x3FFF, (packed >> 2) & 0x3FFF, (packed >> 16) & 0x3FFF):
            for po, s in suffix.get(key, [])[:1]:
                x, y, z = m.vec3(po + 0x20)
                d = ((x - pos["x"]) ** 2 + (y - pos["y"]) ** 2 + (z - pos["z"]) ** 2) ** 0.5
                print("   suffix-match key=%-8d part %-16s (%.1f, %.1f, %.1f) dist %.1f"
                      % (key, s, x, y, z, d))
                hit += 1
    print("suffix matches: %d" % hit)
    dvd.close()


if __name__ == "__main__":
    main()
