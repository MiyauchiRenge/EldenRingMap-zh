"""ESD (EZState) reader - FromSoftware's state-machine scripts, Elden Ring flavour.

Talk scripts live in `/script/talk/<map id>.talkesdbnd.dcx` (a BND4 of `t<id>.esd`
files; the overworld and DLC scripts sit in the area-root bundles
`m60_00_00_00` / `m61_00_00_00`). A script is selected by the owning MSB part's
talk id, which is why the file name *is* the link between a script and an NPC.

File layout (little-endian, ELDEN RING writes the long/"fsSL" variant):

    0x00  "fsSL"                 magic; "fSSL" is the 32-bit variant, not supported
    0x04  int32 1
    0x08  int32 darksoulsCount   (3 here)
    0x0C  int32 darksoulsCount
    0x10  int32 headerSize       (0x54)
    0x14  int32 dataSize
    0x18  int32 6
    0x1C  int32 0x48             (unnamed, asserted)
    0x20  int32 1
    0x24  int32 stateGroupSize   (0x20)
    0x28  int32 stateGroupCount
    0x2C  int32 stateSize        (0x48)
    0x30  int32 stateCount
    0x34  int32 conditionSize    (0x38)
    0x38  int32 conditionCount
    0x3C  int32 commandSize      (0x18)
    0x40  int32 commandCount
    0x44  int32 argSize          (0x10)
    0x48  int32 argCount
    0x4C  int32 conditionOffsetsOffset
    0x50  int32 conditionOffsetsCount
    0x54  int32 nameBlockOffset
    0x58  int32 nameLength
    0x5C  int32 unkOffset1
    0x60  int32 0
    0x64  int32 unkOffset2
    0x68  int32 0

then, from dataStart = 0x6C, the offsets repeat as 64-bit varints:

    +0x00 int32 1
    +0x04 int32 unk70, unk74, unk78, unk7C
    +0x14 int32 0                (long-format padding)
    +0x18 int64 stateGroupsOffset
    +0x20 int64 stateGroupCount
    +0x28 int64 nameOffset
    +0x30 int64 nameLength
    +0x38 int64 -1
    +0x40 int64 -1

The record sizes are asserted rather than assumed, so a format change fails loudly
instead of silently misreading bytes: a state group is 4 int64s (id, statesOffset,
stateCount, statesOffset again), a state is 9 int64s, a condition 7 int64s and a
command call 2 int32s (bank, id) plus 2 int64s (arguments offset, count). Every
offset in the file is relative to dataStart.

Command arguments are postfix bytecode; `constant()` decodes the ones that are a
plain integer literal, which is what a shop row range looks like.
"""
import struct

HEADER_SIZE = 0x54
DATA_START = 0x6C
CHR = "c"

# opcodes we need to name; everything else is reported as its raw byte
OP_F32, OP_F64, OP_INT, OP_CALL0, OP_CALL7 = 0x80, 0x81, 0x82, 0x84, 0x8B
OP_STR, OP_END, OP_RETVAL, OP_INTMAX = 0xA5, 0xA1, 0xB9, 0xBA
BINOPS = {0x8C, 0x8E, 0x8F, 0x90, 0x91, 0x92, 0x93, 0x94, 0x95, 0x96, 0x98, 0x99}
UNOPS = {0x8D, 0x97, 0x9A, 0x9B, 0x9C, 0x9D, 0x9E, 0x9F, 0xA6, 0xB7, 0xB8}


def _i32(b, o):
    return struct.unpack_from("<i", b, o)[0]


def _i64(b, o):
    return struct.unpack_from("<q", b, o)[0]


def decode_bytecode(code):
    """One argument's postfix bytecode -> [(op, value)]. See the format notes."""
    out = []
    i, n = 0, len(code)
    while i < n:
        b = code[i]
        i += 1
        if b <= 0x7F:
            out.append(("lit", b - 64))                 # -64..+63 in one byte
        elif b == OP_F32:
            out.append(("f32", struct.unpack_from("<f", code, i)[0]))
            i += 4
        elif b == OP_F64:
            out.append(("f64", struct.unpack_from("<d", code, i)[0]))
            i += 8
        elif b == OP_INT:
            out.append(("int", struct.unpack_from("<i", code, i)[0]))
            i += 4
        elif OP_CALL0 <= b <= OP_CALL7:
            out.append(("call", b - 0x83))
        elif b == OP_STR:
            end = i
            while end + 1 < n and code[end:end + 2] != b"\x00\x00":
                end += 2
            out.append(("str", code[i - 1:end].decode("utf-16-le", "replace")))
            i = end + 2
        elif b in BINOPS or b in UNOPS:
            out.append(("op", b))
        elif 0xA7 <= b <= 0xAE:
            out.append(("setreg", b - 0xA7))
        elif 0xAF <= b <= 0xB6:
            out.append(("getreg", b - 0xAF))
        elif b == OP_END:
            out.append(("end", None))
        elif b == OP_RETVAL:
            out.append(("retval", None))
        elif b == OP_INTMAX:
            out.append(("intmax", None))
        else:
            out.append(("op%02X" % b, None))
    return out


def constant(code):
    """The integer a bytecode argument stands for, or None if it is computed."""
    toks = decode_bytecode(code)
    if len(toks) == 1 and toks[0][0] in ("int", "lit"):
        return toks[0][1]
    if len(toks) == 2 and toks[0][0] == "int" and toks[1][0] == "end":
        return toks[0][1]
    return None


class Command(object):
    """One command call: a bank/id pair plus its bytecode arguments."""
    __slots__ = ("bank", "id", "args", "index")

    def __init__(self, bank, cid, args, index):
        self.bank, self.id, self.args, self.index = bank, cid, args, index

    def constants(self):
        return [constant(a) for a in self.args]

    def __repr__(self):
        return "<command %d:%d %d arg(s)>" % (self.bank, self.id, len(self.args))


class State(object):
    __slots__ = ("id", "condition_offsets", "entry", "exit", "while_")

    def __init__(self, sid, condition_offsets, entry, exit_, while_):
        self.id = sid
        self.condition_offsets = condition_offsets
        self.entry, self.exit, self.while_ = entry, exit_, while_


class ESD(object):
    """A parsed talk script. `state_groups` is [(groupId, [State, ...]), ...]."""

    def __init__(self, data):
        if data[:4] != b"fsSL":
            raise ValueError("not a long-format ESD (magic %r)" % (data[:4],))
        self.data = data
        assert _i32(data, 0x04) == 1, "unexpected header word at 0x04"
        self.darksouls_count = _i32(data, 0x08)
        assert _i32(data, 0x0C) == self.darksouls_count
        assert _i32(data, 0x10) == HEADER_SIZE, "header size changed"
        self.data_size = _i32(data, 0x14)
        assert _i32(data, 0x18) == 6, "unexpected header word at 0x18"
        assert _i32(data, 0x1C) == 0x48, "state size changed"
        assert _i32(data, 0x20) == 1, "unexpected header word at 0x20"
        self.state_group_size = _i32(data, 0x24)
        self.state_group_count = _i32(data, 0x28)
        self.state_size = _i32(data, 0x2C)
        self.state_count = _i32(data, 0x30)
        self.condition_size = _i32(data, 0x34)
        self.condition_count = _i32(data, 0x38)
        self.command_size = _i32(data, 0x3C)
        self.command_count = _i32(data, 0x40)
        self.arg_size = _i32(data, 0x44)
        self.arg_count = _i32(data, 0x48)
        assert (self.state_group_size, self.state_size, self.condition_size,
                self.command_size, self.arg_size) == (0x20, 0x48, 0x38, 0x18, 0x10), \
            "record sizes changed: %r" % ([self.state_group_size, self.state_size,
                                           self.condition_size, self.command_size,
                                           self.arg_size],)
        self.data_start = DATA_START
        self.state_groups_offset = _i64(data, 0x84)
        self.name_offset = _i64(data, 0x94)
        self.name_length = _i64(data, 0x9C)
        assert self.name_length == _i32(data, 0x58), "name length disagrees between headers"
        self.name = ""
        if self.name_length > 0 and self.name_offset > 0:
            raw = data[self.data_start + self.name_offset:
                       self.data_start + self.name_offset + self.name_length * 2]
            self.name = raw.decode("utf-16-le", "replace").rstrip("\x00")
        self._commands = []
        self._conditions = {}
        self._walked = set()
        self.conditions = []
        self.state_groups = self._read_state_groups()

    # ---------------------------------------------------------------- internals
    def _command(self, off):
        bank, cid = _i32(self.data, off), _i32(self.data, off + 4)
        assert bank in (1, 5, 6, 7), "unexpected command bank %d at 0x%X" % (bank, off)
        args_off, count = _i64(self.data, off + 0x08), _i64(self.data, off + 0x10)
        args = []
        if count:
            base = self.data_start + args_off
            for i in range(count):
                ao = _i64(self.data, base + i * 0x10)
                al = _i64(self.data, base + i * 0x10 + 8)
                args.append(self.data[self.data_start + ao:self.data_start + ao + al])
        cmd = Command(bank, cid, args, len(self._commands))
        self._commands.append(cmd)
        return cmd

    def _command_list(self, off, count):
        if not count:
            return []
        return [self._command(self.data_start + off + i * self.command_size)
                for i in range(count)]

    def _condition(self, off):
        got = self._conditions.get(off)
        if got is not None:
            return got
        cond = {"pass": None, "subs": None, "evaluator": None, "state_offset": _i64(self.data, off)}
        self._conditions[off] = cond
        cond["pass"] = self._command_list(_i64(self.data, off + 0x08), _i64(self.data, off + 0x10))
        n, sub_off = _i64(self.data, off + 0x20), _i64(self.data, off + 0x18)
        cond["subs"] = [_i64(self.data, self.data_start + sub_off + i * 8) for i in range(n)]
        eo, el = _i64(self.data, off + 0x28), _i64(self.data, off + 0x30)
        cond["evaluator"] = self.data[self.data_start + eo:self.data_start + eo + el]
        return cond

    def _state(self, off):
        sid = _i64(self.data, off)
        c_off, c_cnt = _i64(self.data, off + 0x08), _i64(self.data, off + 0x10)
        conds = [_i64(self.data, self.data_start + c_off + i * 8) for i in range(c_cnt)]
        entry = self._command_list(_i64(self.data, off + 0x18), _i64(self.data, off + 0x20))
        exit_ = self._command_list(_i64(self.data, off + 0x28), _i64(self.data, off + 0x30))
        while_ = self._command_list(_i64(self.data, off + 0x38), _i64(self.data, off + 0x40))
        return State(sid, conds, entry, exit_, while_)

    def _read_state_groups(self):
        groups = []
        base = self.data_start + self.state_groups_offset
        for i in range(self.state_group_count):
            off = base + i * self.state_group_size
            gid = _i64(self.data, off)
            states_off, count = _i64(self.data, off + 0x08), _i64(self.data, off + 0x10)
            assert _i64(self.data, off + 0x18) == states_off, "state-group offsets disagree"
            states = [self._state(self.data_start + states_off + j * self.state_size)
                      for j in range(count)]
            groups.append((gid, states))
        # Conditions carry pass-commands of their own, so resolve them afterwards.
        for _gid, states in groups:
            for st in states:
                for coff in st.condition_offsets:
                    self._walk_condition(self.data_start + coff)
        return groups

    def _walk_condition(self, off):
        cond = self._condition(off)
        if off in self._walked:
            return
        self._walked.add(off)
        self.conditions.append(cond)
        for sub in cond["subs"]:
            self._walk_condition(self.data_start + sub)

    # ------------------------------------------------------------------ reading
    def commands(self):
        """Every command call in the script, in file order."""
        return list(self._commands)

    def summary(self):
        return {"name": self.name, "state_groups": self.state_group_count,
                "states": self.state_count, "conditions": self.condition_count,
                "commands": self.command_count}


def _selftest():
    """Check the decoder on the argument shapes the format uses."""
    assert constant(b"\x82" + struct.pack("<i", 100500) + b"\xA1") == 100500
    assert constant(b"\x82" + struct.pack("<i", 100500)) == 100500
    assert constant(b"\x00") == -64
    # not a constant: an addition of two literals
    assert constant(b"\x00\x01\x8C") is None
    toks = decode_bytecode(b"\x8C\x00\x00\x00")
    assert toks[0][0] == "op" and toks[0][1] == 0x8C
    print("esd selftest: ok")


if __name__ == "__main__":
    _selftest()
