"""Register the shop rows for limited items (no coordinates - the data has no shop->merchant link).

ShopLineupParam holds equipId / value / sellQuantity / eventFlag_forStock but no merchant field, and
NpcParam has no shop field either, so a row cannot be attributed to one merchant. The rows are
therefore registered with their shop block, price and quantity instead of being placed on a guessed
merchant.
"""
import io
import json
import os
import re
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, os.path.dirname(HERE))
ROOT = os.path.dirname(os.path.dirname(HERE))
from erlib import fmg, oodle, param, paramdef      # noqa: E402
import erlib.modfiles as modfiles                   # noqa: E402
from erlib.dvdbnd import DvdBnd                     # noqa: E402
from erlib.gamepath import require_game_dir         # noqa: E402
KEEP = ("\u9f9f\u88c2\u58f6", "\u8c03\u9999\u74f6", "\u5236\u4f5c\u4e66")


def main():
    game = require_game_dir(None)
    mod = modfiles.find_mod_dir(None)
    dvd = DvdBnd(game, cache_dir=os.path.join(ROOT, "cache"), verbose=False)
    helper = oodle.make_helper(game)
    params = param.load_params(modfiles.regulation_path(game, mod))
    texts = {}
    for f in ("item.msgbnd.dcx", "item_dlc02.msgbnd.dcx"):
        p = "/msg/zhocn/%s" % f
        if modfiles.has(dvd, mod, p):
            for k, v in fmg.load_msgbnd(modfiles.read(dvd, mod, p), oodle=helper).items():
                texts.setdefault(k.split("_dlc")[0], {}).update(v)
    dvd.close()
    tab = {0: "WeaponName", 1: "ProtectorName", 2: "AccessoryName", 3: "GoodsName", 4: "GemName"}

    def nm(iid, et):
        for t in [tab.get(et, ""), "GoodsName", "WeaponName", "ProtectorName", "AccessoryName",
                  "GemName"]:
            v = (texts.get(t) or {}).get(iid, "") if t else ""
            if v and "[ERROR]" not in v:
                return v
        return ""

    sd = paramdef.load(os.path.join(ROOT, "data", "paramdefs", "ShopLineupParam.xml"))
    flds = re.findall(r"<\w+\s+(\w+)", " ".join(str(f) for f in getattr(sd, "fields", [])))
    out = []
    for r in params["ShopLineupParam"].rows:
        v = {}
        for f in flds:
            try:
                v[f] = sd.get(r.data, f)
            except Exception:
                pass
        n = nm(v.get("equipId"), v.get("equipType", 3))
        if any(k in n for k in KEEP):
            out.append({"id": "shop:%d" % r.id, "cat": "shop_stock",
                        "names": {"zh": n, "en": n}, "px": None, "py": None, "master": None,
                        "price": v.get("value"), "qty": v.get("sellQuantity"),
                        "stockFlag": v.get("eventFlag_forStock"), "row": r.id,
                        "shopBlock": r.id // 100000, "via": "shop-stock",
                        "note": "\u5546\u5e97\u51fa\u552e\uff1a%s \u5362\u6069 \u00d7%s\uff08\u6570\u636e\u65e0\u5546\u4eba\u5f52\u5c5e\uff0c\u4e0d\u843d\u70b9\uff09"
                                % (v.get("value"), v.get("sellQuantity"))})
    io.open(os.path.join(ROOT, "data", "shop-stock.json"), "w",
            encoding="utf-8").write(json.dumps({"locales": ["zh", "en"], "markers": out},
                                               ensure_ascii=False))
    print("shop rows registered: %d" % len(out))
    for m in out:
        print("   row %-8s block=%-3d %-20s %s" % (m["row"], m["shopBlock"], m["names"]["zh"],
                                                   m["note"][:28]))


if __name__ == "__main__":
    main()
