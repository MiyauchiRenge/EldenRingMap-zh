
import io, json, os, struct, sys
sys.path.insert(0, r"C:\Users\13541\Desktop\AI工作\EldenRingMap\EldenRingMap-zh-main\tools")
sys.path.insert(0, r"C:\Users\13541\Desktop\AI工作\EldenRingMap\EldenRingMap-zh-main\tools\dev")
sys.stdout.reconfigure(encoding="utf-8")
import er_save
data = io.open(r"C:\Users\13541\Desktop\ER0000.sl2", "rb").read()
groups = er_save.load_flag_groups(r"C:\Users\13541\Desktop\AI工作\EldenRingMap\EldenRingMap-zh-main\data\eventflag_bst.txt")
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
have = {(m["map"], m["part"]) for m in json.load(io.open(r"C:\Users\13541\Desktop\AI工作\EldenRingMap\EldenRingMap-zh-main\data\gather-nodes.json", encoding="utf-8"))["markers"]}
pos = pay.find(b"FOEG") + 8
picked = hit = 0
miss = []
while True:
    mapid = struct.unpack_from("<I", pay, pos)[0]
    if mapid == 0xFFFFFFFF:
        break
    dd, cc, bb, aa = pay[pos], pay[pos+1], pay[pos+2], pay[pos+3]
    mid = "m%02d_%02d_%02d_00" % (aa, bb, cc)
    size, cnt, unk = struct.unpack_from("<3I", pay, pos + 4)
    if size <= 0 or size > 0x100000:
        break
    for k in range(cnt):
        key, model = struct.unpack_from("<2I", pay, pos + 16 + 8 * k)
        part = "AEG%03d_%03d_%d" % ((model - 10000000) // 1000, (model - 10000000) % 1000, key >> 15)
        picked += 1
        if (mid, part) in have:
            hit += 1
        else:
            miss.append((mid, part))
    pos += size
print("FOEG picked nodes: %d ; matched: %d ; missing: %d" % (picked, hit, len(miss)))
for m, q in miss[:8]:
    print("   MISS %s %s" % (m, q))
