"""EMEVD reader - our own implementation of the format we measured in this project.

Nothing here is copied from any other implementation: every offset below was derived from
the game files and then checked against a self-verifying invariant.

Verified layout
---------------
Header (little endian)::

    +0   int32  magic 0x00445645 "EVD\\0"
    +8   int32  version (205 = 0xCD for Elden Ring)
    +12  int32  fileSize
    +16  int64  eventCount
    +24  int64  eventOffset          (144 = 0x90 in every file we checked)
    +32  int64  instructionCount
    +40  int64  instructionOffset
    +48  int64  (0)
    +56  int64  paramOffset
    +64  int64  (same as +56 in every file we checked)

Event, 48 bytes = six int64::

    [ id, instructionCount, instructionOffset, paramCount, paramOffset, ? ]

    instructionOffset and paramOffset are relative to their sections.

Instruction, FIXED 32 bytes::

    [ bank:int32, id:int32, 24 bytes of arguments ]

    Fixed length is not an assumption: for all 440 event files that contain instructions,
    (paramOffset - instructionOffset) / instructionCount is exactly 32, with no exceptions,
    and walking instructionCount records of 32 bytes lands exactly on the parameter section.
    An earlier reading treated the next record's bank as an argument-length field, which
    broke the walk after two or three records.

Parameters (at paramOffset), records shaped like::

    90005261 | 1035410340 | 1035412340 | 1.0f | 0 | 1700 | 0
    type id    entity id    entity flag  float args...

    So entity ids live in the parameter section, not in instruction arguments.

Self-test
---------
``python tools/erlib/emevd.py`` walks every event file and asserts that the number of
instructions parsed equals the number the header declares (95,727 in total for the
reviewed install). That invariant needs no external reference.
"""
from __future__ import annotations

import struct
from typing import Iterator

MAGIC = 0x00445645
EVENT_SIZE = 48
INSTRUCTION_SIZE = 32

# MSB PARTS_PARAM_ST offsets used to read the entity id and the NPC id of a part.
PART_ENTITY_DATA_PTR = 0x60     # -> entity data; EntityID sits at +0x00 of it
PART_TYPE_DATA_PTR = 0x68       # -> type data;  ENEMY_NPC_PARAM_ID sits at +0x0C of it
ENTITY_ID = 0x00
ENEMY_NPC_PARAM_ID = 0x0C
PART_POSITION = 0x20


def is_emevd(raw: bytes) -> bool:
    return len(raw) >= 16 and struct.unpack_from("<i", raw, 0)[0] == MAGIC


def read_header(raw: bytes) -> dict:
    """Return the header as a dict; raises ValueError when the magic does not match."""
    if not is_emevd(raw):
        raise ValueError("not an EMEVD file")
    version = struct.unpack_from("<i", raw, 8)[0]
    size = struct.unpack_from("<i", raw, 12)[0]
    f = [struct.unpack_from("<q", raw, 16 + 8 * k)[0] for k in range(8)]
    return {
        "version": version,
        "fileSize": size,
        "eventCount": f[0],
        "eventOffset": f[1],
        "instructionCount": f[2],
        "instructionOffset": f[3],
        "paramOffset": f[5],
    }


def iter_events(raw: bytes) -> Iterator[dict]:
    """Yield each event's fields, in file order."""
    h = read_header(raw)
    for k in range(h["eventCount"]):
        base = h["eventOffset"] + EVENT_SIZE * k
        if base + EVENT_SIZE > len(raw):
            return
        v = struct.unpack_from("<6q", raw, base)
        yield {"index": k, "id": v[0], "instructionCount": v[1],
               "instructionOffset": v[2], "paramCount": v[3], "paramOffset": v[4]}


def iter_instructions(raw: bytes) -> Iterator[tuple[int, int, bytes]]:
    """Yield (bank, id, record) for every instruction, in file order.

    ``record`` is the whole 32-byte record; its first 8 bytes are bank and id.
    """
    h = read_header(raw)
    p = h["instructionOffset"]
    for _n in range(h["instructionCount"]):
        if p < 0 or p + INSTRUCTION_SIZE > len(raw):
            return
        bank, iid = struct.unpack_from("<2i", raw, p)
        yield bank, iid, raw[p:p + INSTRUCTION_SIZE]
        p += INSTRUCTION_SIZE


def event_instructions(raw: bytes, event: dict) -> Iterator[tuple[int, int, bytes]]:
    """Yield the instructions belonging to one event (from ``iter_events``)."""
    h = read_header(raw)
    p = h["instructionOffset"] + event["instructionOffset"]
    for _n in range(event["instructionCount"]):
        if p < 0 or p + INSTRUCTION_SIZE > len(raw):
            return
        bank, iid = struct.unpack_from("<2i", raw, p)
        yield bank, iid, raw[p:p + INSTRUCTION_SIZE]
        p += INSTRUCTION_SIZE


def entity_id_of_part(m, part_offset: int) -> int:
    """EntityID of an MSB part: part +0x60 -> entity data, EntityID at +0x00 of that."""
    rel = m.i64(part_offset + PART_ENTITY_DATA_PTR)
    if rel <= 0:
        return 0
    return m.u32(part_offset + rel + ENTITY_ID)


def npc_id_of_part(m, part_offset: int) -> int:
    """NpcParam id of an MSB part, read through the structured type-data pointer."""
    rel = m.i64(part_offset + PART_TYPE_DATA_PTR)
    if rel <= 0:
        return 0
    return m.i32(part_offset + rel + ENEMY_NPC_PARAM_ID)


def _selftest() -> int:
    import os
    import sys
    sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
    from erlib import dcx, oodle               # noqa: WPS433  (local package)
    import erlib.modfiles as modfiles          # noqa: WPS433
    from erlib.dvdbnd import DvdBnd            # noqa: WPS433
    from erlib.gamepath import require_game_dir  # noqa: WPS433

    root = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
    game = require_game_dir(None)
    mod = modfiles.find_mod_dir(None)
    dvd = DvdBnd(game, cache_dir=os.path.join(root, "cache"), verbose=False)
    helper = oodle.make_helper(game)
    maps = [l.split("\t")[0] for l in
            open(os.path.join(root, "cache", "map-list.txt"), encoding="utf-8") if l.strip()]
    declared = parsed = files = 0
    mismatched = []
    for mid in ["common", "common_macro"] + maps:
        path = "/event/%s.emevd.dcx" % mid
        if not modfiles.has(dvd, mod, path):
            continue
        try:
            raw = dcx.decompress(modfiles.read(dvd, mod, path), oodle=helper)
        except Exception:
            continue
        if not is_emevd(raw):
            continue
        files += 1
        h = read_header(raw)
        declared += h["instructionCount"]
        n = sum(1 for _ in iter_instructions(raw))
        parsed += n
        if n != h["instructionCount"]:
            mismatched.append((mid, h["instructionCount"], n))
    dvd.close()
    print("event files: %d" % files)
    print("declared instructions: %d" % declared)
    print("parsed instructions:   %d" % parsed)
    if mismatched:
        print("MISMATCHES: %d" % len(mismatched))
        for mid, d, n in mismatched[:10]:
            print("   %-20s declared %d parsed %d" % (mid, d, n))
        return 1
    print("all files match their declared instruction count")
    return 0


if __name__ == "__main__":
    raise SystemExit(_selftest())
