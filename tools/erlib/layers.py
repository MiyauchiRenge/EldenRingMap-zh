"""The data-layer contract: what each generated file under data/ is, and the one way to write it.

Every file under data/ that holds markers is a *layer*. This module is the single place that says

  * which file a layer is, which tool produces it and with which arguments - so the install script can
    be checked against the registry instead of being kept in step by hand (Setup.bat silently skipped
    four layers before this existed);
  * what the layer is for, and whether the map is complete without it;
  * how its categories count towards the progress figure ("counts" vs "spots", see below);
  * the one writer every tool uses, so the document shape ({"locales": [...], "markers": [...]}) and
    the byte layout cannot drift apart between tools.

Adding a layer therefore means adding one row here, running its extractor, and re-running
`python tools/erlib/layers.py policy` - not editing the client, the server and Setup.bat in three
different places.

Progress policy: "counts" means every marker of the layer is part of the completion percentage.
"spots" means the layer lists places where something *can* be found rather than things you collect
once (respawnable gathering nodes, farmable enemy drops), so counting them would make the bar
unreachable. Two rules refine it, and both live in the client data document as well:
  * a marker with "once": true inside a spots layer never comes back, so it does count;
  * a category that a spots layer and a counting layer both use is scored on the counting layer's
    markers only (the farm layer reuses its categories for nodes that are also pickups).
"""
from __future__ import annotations

import io
import json
import os
import re
import sys

ROOT = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
DATA = os.path.join(ROOT, "data")
LOCALES = ("en", "zh")


class Layer:
    """One generated data file."""

    def __init__(self, id, file, producer, note, progress="counts", optional=False,
                 marker_doc=True, client="initial"):
        self.id = id
        self.file = file
        self.producer = producer          # argv relative to the repo root, or None
        self.note = note
        self.progress = progress          # "counts" | "spots" | "other"
        self.optional = optional          # is the map complete without it?
        self.marker_doc = marker_doc      # {"locales","markers"} vs something else
        # "initial": part of the document the page loads first. "lazy": fetched right after the first
        # paint, because it is big and nothing visible depends on it (the map is already usable).
        self.client = client

    @property
    def path(self):
        return os.path.join(DATA, self.file)

    def as_dict(self):
        return {"id": self.id, "file": self.file, "producer": self.producer, "note": self.note,
                "progress": self.progress, "optional": self.optional,
                "markerDoc": self.marker_doc, "client": self.client}


LAYERS = (
    Layer("markers", "markers.json", ["tools/build_markers.py"],
          "graces, bosses, points of interest, map fragments, region labels"),
    Layer("items", "items.json", ["tools/extract_items.py"],
          "world pickups, merchants, one-time character drops, boss rewards"),
    Layer("npcs", "npcs.json", ["tools/extract_items.py"],
          "merchant stalls, named after the nearest grace", progress="other"),
    Layer("drops", "drops.json", ["tools/extract_items.py"],
          "one-time rewards that hang off a placed character"),
    Layer("boss-drops", "boss-drops.json", ["tools/extract_items.py"],
          "rewards of a boss the game names"),
    Layer("emevd-drops", "emevd-drops.json", ["tools/extract_emevd_drops.py"],
          "drops granted by an event script rather than a placed treasure"),
    Layer("emevd-rewards", "emevd-rewards.json", ["tools/extract_emevd_rewards.py"],
          "rewards an event script grants with no world object at all"),
    Layer("followup", "followup.json", ["tools/extract_followup_lots.py"],
          "the item a sequential lot hands over after its documented lot+1 chain", client="lazy"),
    Layer("gather-nodes", "gather-nodes.json", ["tools/extract_gather_nodes.py"],
          "gatherable AEG nodes; 'once' marks the ones that never respawn", progress="spots",
          client="lazy"),
    Layer("farm", "farm.json", ["tools/extract_farm_nodes.py", "--all-unmarked"],
          "enemy placements worth farming a material from", progress="spots"),
    Layer("shop-stock", "shop-stock.json", ["tools/dev/shop_register.py"],
          "what each merchant's shelf holds and which merchant it is", progress="other"),
    Layer("quest-rewards", "quest-rewards.json", ["tools/extract_quest_rewards.py"],
          "script-granted items that could be anchored to a place"),
    Layer("quest-rewards-unplaced", "quest-rewards-unplaced.json",
          ["tools/extract_quest_rewards.py"],
          "script-granted items with no world object yet - registered, not drawn",
          progress="other"),
    Layer("user-verified", "user-verified.json", None,
          "hand-checked positions; written by the operator, never regenerated"),
    Layer("regions", "regions.json", ["tools/build_markers.py"],
          "the game's region labels for the map layers", progress="other", marker_doc=False),
    Layer("quantities", "quantities.json", ["tools/annotate_quantities.py"],
          "per-category item totals the extractors' lots actually grant", progress="other",
          marker_doc=False),
)

BY_ID = {layer.id: layer for layer in LAYERS}
BY_FILE = {layer.file: layer for layer in LAYERS}

# Layers Setup.bat has to run, in order. annotate_quantities runs last because it
# post-processes every other layer.
SETUP_ORDER = ("markers", "items", "drops", "boss-drops", "emevd-drops", "emevd-rewards",
               "farm", "followup", "gather-nodes", "quest-rewards", "shop-stock",
               "quantities")


def layer_path(name):
    """Absolute path of a layer, by id or by file name."""
    layer = BY_ID.get(name) or BY_FILE.get(name)
    if layer is None:
        raise KeyError("unknown layer %r" % name)
    return layer.path


def dumps(doc):
    """The canonical byte layout: UTF-8, no BOM, LF, no ASCII escaping, sorted keys.

    Sorted keys make a rerun byte-identical, which is what lets the publish check compare files with
    `git show` instead of eyeballing a diff.
    """
    return json.dumps(doc, ensure_ascii=False, sort_keys=True, separators=(",", ":"))


def write_doc(path, markers, locales=LOCALES, extra=None):
    """Write a marker document atomically and return how many markers it holds."""
    doc = {"locales": list(locales), "markers": list(markers)}
    if extra:
        doc.update(extra)
    write_raw(path, doc)
    return len(doc["markers"])


def write_layer(name, markers, locales=LOCALES, extra=None):
    """Write one registered layer by id (or file name)."""
    return write_doc(layer_path(name), markers, locales=locales, extra=extra)


def write_raw(path, doc, indent=None):
    """Write any JSON document with the canonical layout, via a temp file and a replace.

    Compact separators when there is no indentation: the default `, ` / `: ` pair costs two bytes per
    pair, which over 28,000 markers is most of a megabyte on the wire. The browser does not care.

    The replace matters: several tools rewrite a layer that the server may be reading right now, and
    a half-written file would be a JSON error in the browser rather than a stale marker.
    """
    os.makedirs(os.path.dirname(path), exist_ok=True)
    kwargs = {"ensure_ascii": False, "sort_keys": True}
    if indent is None:
        kwargs["separators"] = (",", ":")
    else:
        kwargs["indent"] = indent
    text = json.dumps(doc, **kwargs).replace("\r\n", "\n")
    tmp = path + ".tmp"
    with io.open(tmp, "w", encoding="utf-8", newline="\n") as fh:
        fh.write(text)
    os.replace(tmp, path)
    return len(text)


def read_layer(name):
    """Read a registered layer; raises if the file is not there."""
    with io.open(layer_path(name), encoding="utf-8") as fh:
        return json.load(fh)


def read_markers(name):
    """-> the marker list of a layer, or [] when the file is missing."""
    try:
        return read_layer(name).get("markers") or []
    except (OSError, ValueError):
        return []


def scan():
    """-> [(layer, present, marker count, {category: count})], read from disk.

    `present` is True/False, or the error string when the file exists but does not parse.
    """
    out = []
    for layer in LAYERS:
        counts = {}
        present = os.path.isfile(layer.path)
        if present and layer.marker_doc:
            try:
                with io.open(layer.path, encoding="utf-8") as fh:
                    doc = json.load(fh)
                for m in doc.get("markers") or []:
                    cat = m.get("cat") or "(none)"
                    counts[cat] = counts.get(cat, 0) + 1
            except ValueError as exc:
                out.append((layer, "unreadable: %s" % exc, 0, {}))
                continue
        out.append((layer, present, sum(counts.values()), counts))
    return out


# Steps Setup.bat runs that do not produce a layer: the community format documents, the tile pyramid
# and the map-id index. Declared here so a tool call in Setup.bat that is neither a layer producer nor
# one of these is reported rather than ignored.
SETUP_INFRA = (
    "tools/fetch_docs.py",
    "tools/extract_tiles.py",
    "tools/dev/enumerate_maps.py",
    "tools/extract_icons.py",
    "tools/erlib/layers.py",      # the registry check Setup runs at the end
    # Post-processing of the merchant layer, not layer producers of their own: the first rewrites the
    # bell-bearing markers from NpcParam, the second records which bearing each merchant drops.
    "tools/dev/fix_bell_positions.py",
    "tools/dev/link_bell_bearings.py",
)


def setup_invocations():
    """-> the tool calls Setup.bat makes, as [tool, *args] with the game-dir plumbing removed."""
    path = os.path.join(ROOT, "Setup.bat")
    text = io.open(path, encoding="utf-8").read()
    found = []
    for line in text.splitlines():
        m = re.search(r"%PY%\s+(tools\\[\w\\.\-]+\.py)(.*)$", line.strip())
        if not m:
            continue
        args = [a for a in m.group(2).replace('"', " ").split()
                if a and not a.startswith("%GAMEDIR%") and a not in ("--game-dir", ">nul")]
        found.append([m.group(1).replace("\\", "/")] + args)
    return found


def producer_tools():
    """-> the layer-producing tools, in the order Setup should run them."""
    out = []
    for name in SETUP_ORDER:
        layer = BY_ID[name]
        if layer.producer and layer.producer[0] not in [t for t, *_ in out]:
            out.append((layer.producer[0], layer.producer[1:]))
    return out


def check_setup():
    """Compare Setup.bat with the registry.

    -> (tools the registry expects Setup to run, tool calls Setup makes that nothing declares,
        arguments the registry declares but Setup.bat does not pass)
    """
    have = setup_invocations()
    have_tools = {call[0]: call[1:] for call in have}
    want = producer_tools()
    missing = [([tool] + args) for tool, args in want if tool not in have_tools]
    known = {tool for tool, _args in want} | set(SETUP_INFRA)
    extra = [call for call in have if call[0] not in known]
    missing_args = []
    for tool, args in want:
        if tool in have_tools and args:
            passed = have_tools[tool]
            for a in args:
                if a not in passed:
                    missing_args.append([tool, a])
    return missing, extra, missing_args


def category_names():
    """Localised name per category, taken from one marker of that category.

    The client labels a sidebar row with it. Hand-written labels cover the categories the code names
    itself; a gatherable category (gather_<item id>, one per collected material) has no such label, and
    the item's own name - read out of the game's message files, so Chinese comes from the game itself -
    is the right one in both languages.
    """
    names = {}
    for layer in LAYERS:
        if not os.path.isfile(layer_path(layer.id)):
            continue
        for marker in read_layer(layer.id).get("markers") or []:
            cat = marker.get("cat")
            if not cat or cat in names:
                continue
            labelled = {loc: marker["names"][loc] for loc in LOCALES
                        if (marker.get("names") or {}).get(loc)}
            if labelled:
                names[cat] = labelled
    return names


def build_policy():
    """The document the client reads: which categories exist, in which layer, counting how.

    Derived from the files on disk, so it can never disagree with them. A category several layers use
    is resolved by strength: any counting layer makes it count (the farm layer reuses its categories
    for nodes that are also pickups), and only then does a spots layer decide.
    """
    layers = []
    cats = {}
    names = category_names()
    for layer, present, count, counts in scan():
        entry = layer.as_dict()
        entry["present"] = present is True
        entry["count"] = count
        entry["categories"] = sorted(counts)
        layers.append(entry)
        for cat, n in counts.items():
            info = cats.setdefault(cat, {"layer": layer.id, "progress": layer.progress,
                                         "count": 0, "layers": []})
            info["count"] += n
            info["layers"].append(layer.id)
            if layer.progress == "counts":
                info["progress"] = "counts"
            elif info["progress"] != "counts":
                info["progress"] = layer.progress
    for cat, info in cats.items():
        kinds = {BY_ID[lid].progress for lid in info["layers"]}
        info["shared"] = "counts" in kinds and "spots" in kinds
        if cat in names:
            info["names"] = names[cat]
    spots = sorted(c for c, v in cats.items() if v["progress"] == "spots")
    shared = sorted(c for c, v in cats.items() if v["shared"])
    return {"locales": list(LOCALES), "layers": layers, "cats": cats,
            "spotsCats": spots, "sharedCats": shared,
            "policy": {"spotsCountOnce": True, "sharedCatCounts": True}}


def main(argv):
    cmd = argv[1] if len(argv) > 1 else "check"
    if cmd == "check":
        rows = scan()
        print("%-24s %-8s %8s  %s" % ("layer", "present", "markers", "categories"))
        for layer, present, count, counts in rows:
            state = "yes" if present is True else str(present)
            shown = count if layer.marker_doc else "-"
            print("%-24s %-8s %8s  %d (progress=%s)"
                  % (layer.id, state, shown, len(counts), layer.progress))
        missing, extra, missing_args = check_setup()
        print()
        print("Setup.bat vs registry: %d tool(s) missing, %d undeclared, %d argument(s) missing"
              % (len(missing), len(extra), len(missing_args)))
        for m in missing:
            print("   MISSING in Setup.bat: %s" % " ".join(m))
        for e in extra:
            print("   undeclared tool call: %s" % " ".join(e))
        for m in missing_args:
            print("   MISSING argument:     %s" % " ".join(m))
        cats = {c for _l, _p, _n, counts in rows for c in counts}
        print("categories in use: %d" % len(cats))
        # The document has to agree with the rule it replaces, or the progress figure would change
        # the moment the client starts trusting it. The old rule was: a gather_* category (or the
        # historical 'gathering' row), plus any category only the farm layer has - those are "places
        # to farm", and a farm category that also holds real pickups already counted as progress.
        policy = build_policy()
        spots = set(policy["spotsCats"])
        # 'gathering' is the legacy single row: no layer emits it any more, and the client keeps it in
        # its own no-progress set so a data directory from before the split still renders correctly.
        legacy = {"gathering"}
        gather_only = {c for c in cats if c.startswith("gather_")}
        farm_only = {c for c, v in policy["cats"].items()
                     if v["layers"] == ["farm"] and c not in gather_only | legacy}
        expected = gather_only | farm_only
        drift = sorted(((spots - expected) | (expected - spots)) - legacy)
        print("policy vs the historical rule: %d disagreement(s) %s"
              % (len(drift), drift[:8]))
        print("shared categories (spots layer + counting layer): %d %s"
              % (len(policy["sharedCats"]), policy["sharedCats"][:6]))
        return 1 if (missing or extra or missing_args or drift) else 0
    if cmd == "policy":
        doc = build_policy()
        out = os.path.join(DATA, "layers.json")
        write_raw(out, doc, indent=1)
        print("wrote %s: %d layers, %d categories" % (out, len(doc["layers"]), len(doc["cats"])))
        return 0
    sys.exit("usage: python tools/erlib/layers.py [check|policy]")


if __name__ == "__main__":
    sys.exit(main(sys.argv))
