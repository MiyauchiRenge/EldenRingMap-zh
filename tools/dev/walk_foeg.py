"""Walk the save's FOEG block: every map that has permanently picked-up nodes, and how many.

The technical docs (read-only reference; no code copied) describe WorldGeomMan2 = magic "FOEG",
"permanently picked up one-time nodes ... every map ever visited", entries naming parts of that
map's MSB, keyed by the same 4-byte MapId used by PlayerCoordinates (bytes [DD,CC,BB,AA] ->
mAA_BB_CC_DD). This walks the block, splits it by plausible map ids, and reports per-map entry
counts plus the raw entries for m12_01_00, so the picked gatherables can be located later.
"""
import io
import os
import struct
import sys

sys.path.insert(0, r"C:\Users\13541\Desktop\AI工作\EldenRingMap\EldenRingMap-zh-main\tools")
sys.path.insert(0, r"C:\Users\13541\Desktop\AI工作\EldenRingMap\EldenRingMap-zh-main\tools\dev")
sys.stdout.reconfigure(encoding="utf-8")
import er_save

SAVES = [r"C:\Users\13541\Desktop\ER0000.sl2",
         os.path.join(os.environ.get("APPDATA", ""), "EldenRing", "76561198365244613",
                      "ER0000.sl2")]
AREA = {10, 11, 12, 13, 14, 15, 16, 17, 18, 19, 20, 21, 22, 25, 28, 30, 31, 32, 33, 34, 35,
        40, 41, 42, 43, 44, 45, 46, 47, 48, 49, 50, 51, 52, 53, 54, 55, 60, 61}


def map_id_at(pay, i):
    b = pay[i:i + 4]
    if len(b) < 4:
        return None
    dd, cc, bb, aa = b
    if aa in AREA and bb < 100 and cc < 100 and dd < 100:
        return "m%02d_%02d_%02d" % (aa, bb, cc)
    return None


def main():
    for path in SAVES:
        if not os.path.isfile(path):
            print("missing: %s" % path)
            continue
        print("=== %s (%d bytes, mtime %s) ==="
              % (path, os.path.getsize(path),
                 __import__("datetime").datetime.fromtimestamp(os.path.getmtime(path))))
        data = io.open(path, "rb").read()
        groups = er_save.load_flag_groups(
            r"C:\Users\13541\Desktop\AI工作\EldenRingMap\EldenRingMap-zh-main\data\eventflag_bst.txt")
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
        print("   fullest slot %d: %d flags ; player at %s (%.0f, %.0f, %.0f)"
              % (idx, n, pos["map_id"], pos["x"], pos["y"], pos["z"]))
        i = pay.find(b"FOEG")
        if i < 0:
            print("   no FOEG block")
            continue
        size = struct.unpack_from("<i", pay, i - 4)[0]
        end = min(len(pay), i + max(0, size))
        print("   FOEG at %d, size field %d, scanning %d bytes" % (i, size, end - i))
        recs = []
        j = i + 8
        while j < end - 4:
            mid = map_id_at(pay, j)
            if mid:
                recs.append((j, mid))
                j += 4
            else:
                j += 4
        print("   plausible map records: %d" % len(recs))
        total = 0
        for k, (off, mid) in enumerate(recs):
            nxt = recs[k + 1][0] if k + 1 < len(recs) else end
            entries = (nxt - off - 4) // 4
            total += max(0, entries)
            if mid in ("m12_01_00", "m12_02_00", "m12_07_00", "m61_46_40") or entries > 20:
                raw = [struct.unpack_from("<I", pay, off + 4 + 4 * t)[0] for t in range(min(8, entries))]
                print("      %-14s off %-8d entries %-5d first: %s" % (mid, off, entries, raw))
        print("   total entries across records: %d" % total)


if __name__ == "__main__":
    main()
