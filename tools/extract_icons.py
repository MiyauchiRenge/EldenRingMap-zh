"""Extract the game's own world-map icon sprites.

The map screen labels a lot of places with an icon and no text - grace rays,
rebirth monuments, NPC markers. Those markers exist in our dataset but had
nothing to draw except a coloured dot. This pulls the real sprites out.

    /menu/hi/01_common.tpf.dcx       -> 56 textures; 3 are the map-cursor sheets
    /menu/hi/01_common.sblytbnd.dcx  -> BND4 of .layout XML atlases giving the
                                        sub-rectangle of every sprite

    python tools/extract_icons.py    -> web/icons/*.png + data/map-icons.json

Output lands under web/ so the existing static handler serves it. Like the map
tiles, these are FromSoftware assets: extracted locally, never committed.
"""
import argparse
import json
import os
import re
import sys
import time
import xml.etree.ElementTree as ET
from collections import Counter

reconfigure = getattr(sys.stdout, "reconfigure", None)
if reconfigure:
    reconfigure(encoding="utf-8")
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from PIL import Image

from erlib import dcx, oodle, bnd4, param, paramdef, tpf as tpflib
import erlib.modfiles as modfiles
from erlib.dvdbnd import DvdBnd
from erlib.gamepath import require_game_dir

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
DEFS = os.path.join(ROOT, "data", "paramdefs")

# Image.Resampling only exists from Pillow 9.1; the flat alias works everywhere.
LANCZOS = getattr(Image, "Resampling", Image).LANCZOS

TPF_PATH = "/menu/hi/01_common.tpf.dcx"
LAYOUT_PATH = "/menu/hi/01_common.sblytbnd.dcx"
SHEETS = ("SB_MapCursor", "SB_MapCursor_02", "SB_MapCursor_03_dlc")

# iconId -> sprite name. Everything else is MENU_MAP_%02d.
SPRITE_EXCEPTIONS = {
    1: "MENU_MAP_01_Bonfire",     # Sites of Grace
    3: "MENU_MAP_Church",
}
NO_SPRITE = {0, 15}               # 0 = no icon at all; 15 (River Well) has none

# Sprites are kept near their native size. This used to be 64, which shrank EVERY
# sprite (all 808 extracted item icons came out exactly 64x64, and the map icons
# too) and threw away detail the player can see: the game's item icons are drawn
# larger than that and are only ever displayed small by CSS, so capping them at the
# extraction step was pure loss. The cap now only exists to bound an outlier.
MAX_HEIGHT = 512

# Item icons: the same TPF and the same layout BND4, different sheets. An item
# marker carries the item's own iconId (EquipParamGoods +0x030, see
# extract_items.py) and the sprite is MENU_ItemIcon_%05d.
ITEM_SPRITE = "MENU_ItemIcon_%05d"
ITEM_DIR = "items"

# Legend rows that draw a sprite no marker carries, so nothing in items.json asks
# for it: web/js/app.js CAT_ICON decides those rows' pictures, and this is where
# their files come from. Currently the armour row, whose markers all carry a
# different iconId (so the inferred picture is arbitrary) and which is drawn with
# the Albinauric Mask instead. Keeping the list here means re-running this script
# does not silently drop the file and turn that row back into a colour dot.
EXTRA_ITEM_ICONS = {
    14800: "armour",   # Albinauric Mask
}


# Legend icons pinned by hand (web/js/app.js CAT_ICON points category rows at
# these ids). Item sprites are otherwise extracted on demand - only the iconIds
# that markers carry - and these four belong to items no marker has: a script
# reward, a hat, a talisman and a Remembrance. Ids only, no artwork here.
LEGEND_ICON_IDS = {163, 2100, 2101, 2102, 2103, 2104, 2105, 2106, 2107, 2108, 2109, 2110, 2111, 2112, 2113, 2114, 2115, 2116, 2117, 2118, 2119, 10089, 14740, 18090}


def sprite_name(icon_id):
    if icon_id in NO_SPRITE:
        return None
    return SPRITE_EXCEPTIONS.get(icon_id, f"MENU_MAP_{icon_id:02d}")


def load_atlases(dvd, helper, mod, keep):
    """-> ({spriteName: (sheet, x, y, w, h)}, Counter of sheets)

    `keep(sheetName)` decides which layouts are read: the map-cursor sheets for
    the map markers, the SB_Icon_* sheets for item icons.
    """
    data = modfiles.read(dvd, mod, LAYOUT_PATH)
    b = bnd4.BND4(dcx.decompress(data, oodle=helper))
    atlas = {}
    sheets_seen = Counter()
    for e in b.entries:
        base = e.name.replace(chr(92), "/").split("/")[-1]
        if not base.lower().endswith(".layout"):
            continue
        sheet = base[:-len(".layout")]
        if not keep(sheet):
            continue
        root = ET.fromstring(b.read(e).decode("utf-8", "replace"))
        for st in root.iter("SubTexture"):
            nm = (st.get("name") or "").rsplit(".", 1)[0]
            try:
                rect = tuple(int(st.attrib[key]) for key in ("x", "y", "width", "height"))
            except (TypeError, ValueError):
                continue
            atlas[nm] = (sheet, *rect)
            sheets_seen[sheet] += 1
    return atlas, sheets_seen


def used_icon_ids(game, mod):
    """Every iconId referenced by the params we build markers from."""
    params = param.load_params(modfiles.regulation_path(game, mod))
    ids = Counter()
    for pname, dname, field in (("WorldMapPointParam", "WorldMapPointParam", "iconId"),
                                ("BonfireWarpParam", "BonfireWarpParam", "iconId")):
        d = paramdef.load(os.path.join(DEFS, dname + ".xml"))
        for r in params[pname].rows:
            try:
                ids[d.get(r.data, field)] += 1
            except Exception:
                pass
    return ids


def extract_item_icons(dvd, helper, mod, out_dir):
    """Write one PNG per item iconId that data/items.json actually references.

    Only the ids something on the map uses are written, so this stays in the
    hundreds of files rather than the ~3000 sprites the SB_Icon sheets hold. The
    sheets are ~8 MB of decoded RGBA each, so they are decoded one at a time and
    released, not all thirteen at once.

    EXTRA_ITEM_ICONS is merged in: legend rows that name their own sprite in
    CAT_ICON are not attached to any marker, so items.json never mentions them.
    """
    items_path = os.path.join(ROOT, "data", "items.json")
    if not os.path.isfile(items_path):
        print("\nitem icons: skipped - no data/items.json "
              "(run tools/extract_items.py first)")
        return
    with open(items_path, encoding="utf-8") as f:
        markers = json.load(f)["markers"]
    # Collect iconIds from the gather-node layer too (its markers carry iconId).
    for _extra in ("gather-nodes.json",):
        _p = os.path.join(ROOT, "data", _extra)
        if os.path.isfile(_p):
            try:
                markers += json.load(open(_p, encoding="utf-8"))["markers"]
            except Exception:
                pass

    wanted = Counter(m["iconId"] for m in markers if m.get("iconId"))
    # ...plus the pinned legend icons, which no marker references.
    for _iid in LEGEND_ICON_IDS:
        wanted.setdefault(_iid, 0)
        wanted[_iid] = max(wanted[_iid], 1)
    # count 0: no marker uses these, which is exactly why they are listed here.
    wanted.update({icon_id: 0 for icon_id in EXTRA_ITEM_ICONS})
    if not wanted:
        print("\nitem icons: nothing to do - no marker carries an iconId")
        return

    print(f"\nitem icons: {len(wanted)} distinct icon ids referenced")
    atlas, sheets_seen = load_atlases(dvd, helper, mod, lambda s: s.startswith("SB_Icon"))
    print("  atlases: " + ", ".join(f"{k}={v}" for k, v in sorted(sheets_seen.items())))

    tpf_bytes = dcx.decompress(modfiles.read(dvd, mod, TPF_PATH), oodle=helper)
    textures = {t.name: t for t in tpflib.parse(tpf_bytes)}

    os.makedirs(os.path.join(out_dir, ITEM_DIR), exist_ok=True)
    by_sheet = {}
    missing = []
    for icon_id in sorted(wanted):
        nm = ITEM_SPRITE % icon_id
        if nm not in atlas:
            missing.append(icon_id)
            continue
        by_sheet.setdefault(atlas[nm][0], []).append((icon_id, nm))

    index = {}
    for sheet_name, entries in sorted(by_sheet.items()):
        tex = textures.get(sheet_name)
        if tex is None:
            missing.extend(i for i, _ in entries)
            continue
        img, _w, _h = tpflib.texture_image(tpf_bytes, tex)
        img = img.convert("RGBA")
        for icon_id, nm in entries:
            _sheet, x, y, sw, sh = atlas[nm]
            if sw <= 0 or sh <= 0:
                continue
            crop = img.crop((x, y, x + sw, y + sh))
            if sh > MAX_HEIGHT:
                scale = MAX_HEIGHT / sh
                crop = crop.resize((max(1, round(sw * scale)), MAX_HEIGHT), LANCZOS)
            crop.save(os.path.join(out_dir, ITEM_DIR, f"{icon_id}.png"),
                      "PNG", optimize=True)
            index[str(icon_id)] = {"file": f"icons/{ITEM_DIR}/{icon_id}.png",
                                   "w": crop.width, "h": crop.height,
                                   "sprite": nm, "uses": wanted[icon_id]}
        del img
        print(f"  {sheet_name}: {len(entries)} icons")

    with open(os.path.join(out_dir, "items.json"), "w", encoding="utf-8") as f:
        json.dump({"icons": index, "missing": sorted(missing)}, f,
                  ensure_ascii=False, indent=1)
    total = sum(os.path.getsize(os.path.join(out_dir, ITEM_DIR, f"{i}.png"))
                for i in index)
    print(f"  {len(index)} item icons -> {os.path.join(out_dir, ITEM_DIR)}"
          f"  ({total / 1024:.0f} KB); {len(missing)} ids have no sprite")
    print("  index -> " + os.path.join(out_dir, "items.json"))


def main():
    ap = argparse.ArgumentParser(description=__doc__,
                                 formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--game-dir", default=None)
    ap.add_argument("--mod-dir", default=None)
    ap.add_argument("--out", default=os.path.join(ROOT, "web", "icons"))
    args = ap.parse_args()

    game = require_game_dir(args.game_dir)
    mod = modfiles.find_mod_dir(args.mod_dir)
    t0 = time.time()
    dvd = DvdBnd(game, cache_dir=os.path.join(ROOT, "cache"), verbose=False)
    helper = oodle.make_helper(game)

    print("reading sprite atlases ...")
    atlas, sheets_seen = load_atlases(dvd, helper, mod, lambda s: s in SHEETS)
    print(f"  {len(atlas)} sprites across "
          + ", ".join(f"{k}={v}" for k, v in sorted(sheets_seen.items())))

    print("which icons do the params actually use ...")
    ids = used_icon_ids(game, mod)
    print(f"  {len(ids)} distinct iconIds, {sum(ids.values())} references")

    wanted = {}
    missing = []
    for icon_id in sorted(ids):
        nm = sprite_name(icon_id)
        if nm is None:
            continue
        if nm not in atlas:
            missing.append(icon_id)
            continue
        wanted[icon_id] = nm
    print(f"  {len(wanted)} have a sprite; no sprite for {missing}")

    print(f"decoding the {len(SHEETS)} map-cursor sheets ...")
    data = modfiles.read(dvd, mod, TPF_PATH)
    tpf_bytes = dcx.decompress(data, oodle=helper)
    textures = {t.name: t for t in tpflib.parse(tpf_bytes)}
    sheets = {}
    for name in SHEETS:
        t = textures.get(name)
        if not t:
            print(f"  ! {name} not in the TPF")
            continue
        img, w, h = tpflib.texture_image(tpf_bytes, t)
        sheets[name] = img
        print(f"  {name}: {w}x{h}")

    os.makedirs(args.out, exist_ok=True)
    index = {}
    saved = 0
    for icon_id, nm in sorted(wanted.items()):
        sheet, x, y, w, h = atlas[nm]
        src = sheets.get(sheet)
        if src is None or w <= 0 or h <= 0:
            continue
        crop = src.crop((x, y, x + w, y + h))
        if h > MAX_HEIGHT:
            scale = MAX_HEIGHT / h
            crop = crop.resize((max(1, round(w * scale)), MAX_HEIGHT), LANCZOS)
        path = os.path.join(args.out, f"{icon_id}.png")
        crop.save(path, "PNG", optimize=True)
        index[str(icon_id)] = {"file": f"icons/{icon_id}.png",
                               "w": crop.width, "h": crop.height,
                               "sprite": nm, "uses": ids[icon_id]}
        saved += 1

    # The index lives beside the sprites so the existing static handler serves
    # it; nothing about the server needs to change.
    doc = {"icons": index, "missing": sorted(missing)}
    out_json = os.path.join(args.out, "index.json")
    with open(out_json, "w", encoding="utf-8") as f:
        json.dump(doc, f, ensure_ascii=False, indent=1)

    total = sum(os.path.getsize(os.path.join(args.out, f"{i}.png")) for i in wanted
                if os.path.exists(os.path.join(args.out, f"{i}.png")))
    print(f"\n{saved} icons -> {args.out}  ({total / 1024:.0f} KB)")
    print(f"index -> {out_json}")
    print(f"{time.time() - t0:.0f}s")

    print("\nmost-used icons:")
    for icon_id, meta in sorted(index.items(), key=lambda kv: -kv[1]["uses"])[:10]:
        print(f"   icon {icon_id:>4}  {meta['sprite']:<24}"
              f"{meta['w']:>4}x{meta['h']:<4}  used {meta['uses']}x")

    extract_item_icons(dvd, helper, mod, args.out)
    dvd.close()


if __name__ == "__main__":
    main()
