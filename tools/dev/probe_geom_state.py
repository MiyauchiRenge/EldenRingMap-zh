"""Probe the save's MOEG/FOEG blocks: which MSB parts of m12_01_00 were picked up?

Their technical docs say WorldGeomMan (magic "MOEG") holds "broken and picked up assets" and
WorldGeomMan2 ("FOEG") holds "permanently picked up one-time nodes ... every map ever visited",
with each entry naming a part in that map's MSB, keyed by the same 4-byte MapId used by
PlayerCoordinates (bytes [DD,CC,BB,AA] -> mAA_BB_CC_DD).

So: find the magics, find the map id bytes for m12_01_00 (00 00 01 0C, as er_save reads it),
and dump what follows. That should name the exact part the player picked - the gatherable whose
position no map file revealed.

Format knowledge only (their docs); no code or data is copied from that project.
"""
import io
import struct
import sys

sys.path.insert(0, r"C:\Users\13541\Desktop\AI工作\EldenRingMap\EldenRingMap-zh-main\tools")
sys.path.insert(0, r"C:\Users\13541\Desktop\AI工作\EldenRingMap\EldenRingMap-zh-main\tools\dev")
sys.stdout.reconfigure(encoding="utf-8")
import er_save

SAVE = r"C:\Users\13541\Desktop\ER0000.sl2"
MAP_BYTES = bytes((0, 0, 1, 12))          # m12_01_00, as PlayerCoordinates stores it


def main():
    data = io.open(SAVE, "rb").read()
    groups = er_save.load_flag_groups(r"C:\Users\13541\Desktop\AI工作\EldenRingMap\EldenRingMap-zh-main\data\eventflag_bst.txt")
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
    print("slot %d (%d flags), payload %d bytes" % (idx, n, len(pay)))
    pos = er_save.read_position(pay)
    print("player: map=%s pos=(%.1f, %.1f, %.1f)" % (pos["map_id"], pos["x"], pos["y"], pos["z"]))
    off = er_save.event_flags_offset(pay)
    print("event_flags offset = %d" % off)

    for magic in (b"MOEG", b"FOEG", b"CHR ", b"CSBC"):
        starts = []
        i = pay.find(magic, max(0, off - 1024))
        while i != -1 and len(starts) < 8:
            starts.append(i)
            i = pay.find(magic, i + 1)
        print("%s found at %s" % (magic.decode(errors="replace"), starts[:8]))

    for magic in (b"MOEG", b"FOEG"):
        i = pay.find(magic)
        if i < 0:
            print("%s: not found" % magic)
            continue
        print("\n=== %s block at %d ===" % (magic.decode(), i))
        # size field precedes the data per the docs ([int32 size][data]); magic is the first
        # 4 bytes of the data, so the size sits just before
        size = struct.unpack_from("<i", pay, i - 4)[0] if i >= 4 else -1
        print("   size field before magic: %d" % size)
        j = pay.find(MAP_BYTES, i, i + (size if 0 < size < 5_000_000 else 1_000_000))
        print("   map id bytes %s inside block: %s" % (list(MAP_BYTES), j))
        if j >= 0:
            base = max(0, j - 16)
            ints = [struct.unpack_from("<i", pay, base + 4 * k)[0] for k in range(24)]
            print("   dump around map record (base +%d):" % base)
            for row in range(0, 24, 8):
                print("      +%-6d %s" % (base + 4 * row,
                                          " ".join("%-11d" % v for v in ints[row:row + 8])))
    # also: any occurrence of the map id in the whole payload, to see all structures mentioning it
    hits = []
    i = pay.find(MAP_BYTES)
    while i != -1 and len(hits) < 12:
        hits.append(i)
        i = pay.find(MAP_BYTES, i + 1)
    print("\nm12_01_00 map-id occurrences in payload: %s" % hits)


if __name__ == "__main__":
    main()
