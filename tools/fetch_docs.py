"""Fetch the community-maintained documentation the tools build against.

Three sets of files are needed to turn your installation into a marker dataset,
and none of them are game assets - they are field layouts and item-id lists,
each maintained by another project and each with its own licence:

    data/paramdefs/*.xml     Paramdex      https://github.com/soulsmods/Paramdex
    data/eventflag_bst.txt   ER-Save-Lib   https://github.com/ClayAmore/ER-Save-Lib
    data/mfg/*.json          Map for Goblins
                                           https://github.com/VirusAlex/ERR-MapForGoblins-DLL

This repository ships code only: those files are deliberately not committed, in
the same way the map tiles and the game's own icons are not - so this script
fetches them once, at setup time, onto your machine.

The URLs below point at the upstream project this fork is based on
(egormagurin/EldenRingMap) rather than at the three original repositories. That
is on purpose: upstream pins the exact revisions these tools were written
against, while the original projects keep moving. The files it serves are
byte-identical to the ones the original projects publish; if upstream ever moves
them, take them from the links above and drop them in place by hand.

    python tools/fetch_docs.py              -> data/...
    python tools/fetch_docs.py --out DIR    -> DIR/...   (also used by the tests)
    python tools/fetch_docs.py --force      -> re-download what is already there

A file that is already present is left alone, so this is safe to re-run.
"""
import argparse
import json
import os
import sys
import urllib.error
import urllib.request
import xml.etree.ElementTree as ET

reconfigure = getattr(sys.stdout, "reconfigure", None)
if reconfigure:
    reconfigure(encoding="utf-8")

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
BASE = "https://raw.githubusercontent.com/egormagurin/EldenRingMap/main/"

# Two definitions upstream does not carry (both verified 404 there), taken from
# Paramdex - the same project the credits already point at. Same file names, same
# data/paramdefs/ destination, so nothing downstream has to know.
#
#   NpcParam            names every placed NPC; merchants read it for their kind.
#   WorldMapPlaceNameParam  the game's region labels (Limgrave, Liurnia ...),
#                       which build_markers turns into data/regions.json so a
#                       marker can say which region it is in.
PARAMDEX = "https://raw.githubusercontent.com/soulsmods/Paramdex/master/ER/Defs/"
FROM_PARAMDEX = {
    "data/paramdefs/NpcParam.xml",
    "data/paramdefs/WorldMapPlaceNameParam.xml",
}

FILES = [
    "data/eventflag_bst.txt",
    "data/paramdefs/BonfireWarpParam.xml",
    "data/paramdefs/ShopLineupParam.xml",
    "data/paramdefs/ShopLineupParam_Recipe.xml",
    "data/paramdefs/AssetEnvironmentGeometryParam.xml",
    "data/paramdefs/GameAreaParam.xml",
    "data/paramdefs/ItemLotParam.xml",
    # NpcParam is what names the NPCs: extract_items.py reads a merchant part's
    # NpcParam id and follows nameId into the NpcName FMG, so without this
    # definition every merchant falls back to the generic "Merchant".
    "data/paramdefs/NpcParam.xml",
    "data/paramdefs/WorldMapLegacyConvParam.xml",
    # The region labels, for the "which region is this marker in" line in the UI.
    "data/paramdefs/WorldMapPlaceNameParam.xml",
    "data/paramdefs/WorldMapPieceParam.xml",
    "data/paramdefs/WorldMapPointParam.xml",
    "data/mfg/_piece_final_map.json",
    "data/mfg/ember_pieces.json",
    "data/mfg/goods_crafting_ids.json",
    "data/mfg/goods_crystal_tear_ids.json",
    "data/mfg/goods_incantation_ids.json",
    "data/mfg/goods_keyitem_ids.json",
    "data/mfg/goods_sorcery_ids.json",
    "data/mfg/goods_sort_groups.json",
    "data/mfg/goods_spirit_ash_ids.json",
    "data/mfg/rune_pieces.json",
    "data/mfg/weapon_ammo_ids.json",
]


def verify(path):
    """Parse what was written, so a truncated or half-written file is caught here.

    A download that stops early still produces a file, and the failure would
    otherwise surface much later as a confusing "no rows in paramdef" style
    error inside a build step.
    """
    with open(path, "rb") as f:
        raw = f.read()
    if not raw:
        return "empty file"
    try:
        if path.endswith(".json"):
            json.loads(raw.decode("utf-8"))
        elif path.endswith(".xml"):
            ET.fromstring(raw)
    except Exception as exc:                     # noqa: BLE001 - report anything
        return "unreadable: %s" % exc
    return None


def main():
    ap = argparse.ArgumentParser(description=__doc__,
                                 formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--out", default=os.path.join(ROOT, "data"),
                    help="where the files go (default: this repo's data/)")
    ap.add_argument("--force", action="store_true",
                    help="download again even if the file is already there")
    args = ap.parse_args()

    kept, fetched, failed = 0, 0, []
    for rel in FILES:
        # FILES are data/... paths; --out replaces the leading data/ component
        dest = os.path.join(args.out, *rel.split("/")[1:])
        if os.path.isfile(dest) and not args.force:
            kept += 1
            continue
        url = (PARAMDEX if rel in FROM_PARAMDEX else BASE) + urllib.parse.quote(
            rel.split("/")[-1] if rel in FROM_PARAMDEX else rel)
        try:
            with urllib.request.urlopen(url, timeout=60) as r:
                blob = r.read()
            os.makedirs(os.path.dirname(dest), exist_ok=True)
            with open(dest, "wb") as f:
                f.write(blob)
        except (urllib.error.URLError, OSError, TimeoutError) as exc:
            failed.append((rel, str(exc)))
            continue
        problem = verify(dest)
        if problem:
            os.remove(dest)
            failed.append((rel, problem))
            continue
        fetched += 1
        print("  %-48s %8d bytes" % (rel, len(blob)))

    print("\n社区格式文档 / community format docs: "
          "%d fetched, %d already present, %d failed" % (fetched, kept, len(failed)))
    if failed:
        print("\n  以下文件没有拿到 / these could not be fetched:")
        for rel, why in failed:
            print("    %-48s %s" % (rel, why))
        print("\n  离线也能用：从下面任一地址手动下载后放到同样的位置即可。")
        print("  Offline is fine - download them by hand from either place:")
        print("    " + BASE + "data")
        print("    https://github.com/soulsmods/Paramdex")
        print("    https://github.com/ClayAmore/ER-Save-Lib")
        print("    https://github.com/VirusAlex/ERR-MapForGoblins-DLL")
        return 1
    return 0


if __name__ == "__main__":
    sys.exit(main())
