"""Map-for-Goblins item category classifier, ported faithfully from the
authoritative open-source implementation.

Source: https://github.com/VirusAlex/ERR-MapForGoblins-DLL
  - tools/generate_loot_massedit.py  (LOOT_CATEGORIES, the ordered classifier)
  - tools/map_categories.py          (slug -> icon PNG)
  - data/goods_*.json                (itemId lists: incantations, sorceries,
                                       spirit ashes, crafting, key items,
                                       crystal tears, ammo, sort groups)

The classifier is first-match-wins over an ordered list, exactly as MFG's
LOOT_CATEGORIES. It maps every item to one of the MFG category slugs, with
"misc" as the final fallback (MFG has no misc; we add it so nothing is dropped).

This is the ERR profile: spirit ashes live in 300000-399999 and the Rune Arc
goods id is 150 (both differ from vanilla per MFG's config.PROFILE == 'err').
"""
import json
import os

# This file is tools/erlib/, so the repo root is two levels up - not one. The
# loaders below fail soft, so getting this wrong costs no error at all: every
# id-list category silently degrades to "misc" instead.
_ROOT = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
_MFG_DIR = os.path.join(_ROOT, "data", "mfg")


MISSING = []          # data files that could not be read, for data_status()


def _load_set(name):
    path = os.path.join(_MFG_DIR, name)
    try:
        with open(path, encoding="utf-8") as f:
            return set(json.load(f))
    except (OSError, ValueError):
        MISSING.append(name)
        return set()


def _load_sort_groups():
    name = "goods_sort_groups.json"
    path = os.path.join(_MFG_DIR, name)
    try:
        with open(path, encoding="utf-8") as f:
            raw = json.load(f)
        return {int(k): int(v) for k, v in raw.items()}
    except (OSError, ValueError):
        MISSING.append(name)
        return {}


def data_status():
    """-> warning string when the id lists are missing, else None.

    Without them the classifier still runs, but every id-list and sort-group
    category (crystal tears, incantations, sorceries, crafting materials,
    consumables, greases, ...) quietly collapses into "misc". Callers print
    this so a bad checkout is visible rather than merely disappointing.
    """
    if not MISSING:
        return None
    return (f"warning: {len(MISSING)} Map-for-Goblins data files missing from "
            f"{_MFG_DIR}\n         items will be under-categorised: "
            + ", ".join(sorted(MISSING)))


CRYSTAL_TEAR_IDS = _load_set("goods_crystal_tear_ids.json")
INCANTATION_IDS = _load_set("goods_incantation_ids.json")
SORCERY_IDS = _load_set("goods_sorcery_ids.json")
CRAFTING_IDS = _load_set("goods_crafting_ids.json")
KEYITEM_IDS = _load_set("goods_keyitem_ids.json")
AMMO_IDS = _load_set("weapon_ammo_ids.json")
SPIRIT_ASH_IDS = _load_set("goods_spirit_ash_ids.json")
GOODS_SORT_GROUPS = _load_sort_groups()

# ERR profile constant (differs per profile in MFG): Reforged moves spirit ashes
# into this range. Vanilla spirit ashes are covered by the MFG id list below.
SPIRIT_ASH_MIN, SPIRIT_ASH_MAX = 300000, 399999

# Revered Spirit Ash (zh 灵灰 / ru Прах славного духа), the Shadow-realm
# counterpart to the Golden Seed: it raises the blessing level of your Spirit
# Ashes, where the Scadutree Fragment raises your own. 2010100 is the one DLC id
# upstream knew of. It is deliberately NOT a range: the neighbouring
# 2010000 is a Scadutree Fragment, and an earlier attempt to cover the remaining
# ranks with a guessed 2000000-2001999 window was wrong - a guess that silently
# mislabels items is worse than not guessing, so the rest are caught by name.
SPIRIT_BLESSING_ID = 2010100

PATE_IDS = {2200, 2201, 2202, 2203, 2204, 2205, 2206, 2207, 2002150}
PROGRESSION_EXTRA = {2002120, 2002130, 2190, 8867, 2170, 1000000, 2920}

FORTUNE_IDS = {
    900218, 900238, 900258, 900268, 900278, 900288,
    900308, 900318, 900328, 900338, 900348, 900368,
}
SEALED_CURIO_IDS = {
    1301900, 1302900, 1303900, 1304900, 1305900,
    1306900, 1307900, 1308900, 1309900,
}
PRAYERBOOK_IDS = {
    8850, 8851, 8852, 8854, 8855, 8856, 8857, 8858,
    8859, 8862, 8864, 8865, 8866, 2008014,
}
# Smithing stones, split by LEVEL and by SOMBER vs normal.
#
# The game's ids interleave the two families, so the upstream grouping (low /
# mid / rare, by drop rarity) cannot express "Smithing Stone [3]" as a category
# of its own. This table maps goods id -> (level, is_somber) instead, and
# categorise() turns that into "smithing_stone_<n>" or "somber_stone_<n>".
#
# Somber ids sit 60 above their normal counterpart for [1]-[8] (10100 -> 10160),
# then the two families drift apart: normal stops at [8] while somber runs on to
# [9] and [10].
#
# The DLC ids (10110/10111 normal, 10170-10173 somber, plus the Scadushards
# 10150/10151) sit in the same family but are NOT "Smithing Stone [10]": the
# game's ladder stops at [8] normal and [9] somber, and upstream's own comments
# name these "Shadow stones" and "Scadushards". They get their own slugs rather
# than a level number that does not exist. Names are provisional - these ids
# yield no pickups in the data we could check, so nothing rides on the wording.
SMITHING_LEVELS = {}
for _n in range(1, 9):                      # [1]-[8], both families
    SMITHING_LEVELS[10100 + _n - 1] = (_n, False)
    SMITHING_LEVELS[10160 + _n - 1] = (_n, True)
SMITHING_LEVELS[10200] = (9, True)          # Somber [9] - the ladder ends here

SMITHING_SHADOW_IDS = {10110, 10111, 10150, 10151}
SOMBER_SHADOW_IDS = set(range(10170, 10174))

# Ancient Dragon (10140 normal / 10168 somber) and Primordial (10114/10174).
SMITHING_RARE_IDS = {10140, 10168, 10114, 10174}

# The old three-bucket split, kept because other callers/tools still ask for it.
SMITHING_LOW_IDS = {i for i, (lvl, somber) in SMITHING_LEVELS.items()
                    if lvl <= 6}
SMITHING_IDS = ({i for i, (lvl, somber) in SMITHING_LEVELS.items()
                 if lvl >= 7}
                | SMITHING_SHADOW_IDS | SOMBER_SHADOW_IDS | SMITHING_RARE_IDS)

# Gloveworts, split by LEVEL and by FAMILY, exactly like the smithing stones.
#
# All one row before this: 49 markers holding both 墓地铃兰【1】【5】-【9】 and
# 灵依墓地铃兰【5】-【9】. The legend's row picture is "the iconId most of the
# category's markers carry", so that row could only ever show an arbitrary level
# (墓地铃兰【7】, 8 of 49) - the same tie-break that made the armour row draw a
# scarab. A row per level fixes it at the source: the swatch becomes that level's
# own sprite, and the counts start meaning "which tier am I short of".
#
# The ids run in step with the level, so the level is the offset:
#   10900..10908 = Grave Glovewort [1]..[9]   10909 = Great Grave Glovewort
#   10910..10918 = Ghost Glovewort [1]..[9]   10919 = Great Ghost Glovewort
GLOVEWORT_LEVELS = {}
for _n in range(1, 10):
    GLOVEWORT_LEVELS[10900 + _n - 1] = ("grave", _n)
    GLOVEWORT_LEVELS[10910 + _n - 1] = ("ghost", _n)

# The two level-less pieces: one row each, still split by family.
GLOVEWORT_GREAT_IDS = {10909: "grave", 10919: "ghost"}


# Runes, per level. The level is in the item's own name ("Golden Rune [7]"), and
# the name rule below reads it there; these tables are the fallback for an item
# whose name is missing, and they are also the evidence for the ladder the name
# rule is allowed to accept. 2900..2912 run Golden Rune [1]..[13], 2914..2918 run
# Hero's Rune [1]..[5], 2002952..2002958 run Shadow Realm Rune [1]..[7].
GOLDEN_RUNE_LEVEL_IDS = {2900 + i: i + 1 for i in range(13)}
HERO_RUNE_LEVEL_IDS = {2914 + i: i + 1 for i in range(5)}
SHADOW_RUNE_LEVEL_IDS = {2002952 + i: i + 1 for i in range(7)}
# Runes with no level in the name: one legend row between them.
SPECIAL_RUNE_IDS = {2913, 2919, 2002959, 2002960}   # Numen's, Lord's, Unsung Hero, Marika's
BROKEN_RUNE_IDS = {2002951}
# A name like "Golden Rune [14]" must not invent a category: the legend would have
# no row for it, and a marker whose category is missing from CATS is unreachable.
# So the name rule accepts only levels these ladders actually have, and anything
# else falls through to the ordinary rules.
RUNE_FAMILIES = {"golden": 13, "hero": 5, "shadow": 7}
RUNE_PREFIXES = (("golden", "golden rune ["),
                 ("hero", "hero's rune ["),
                 ("shadow", "shadow realm rune ["))
MP_FINGER_IDS = {
    100, 101, 103, 104, 105, 106, 108, 110, 111, 112,
}


def _sg(iid):
    return GOODS_SORT_GROUPS.get(iid, -1)


def categorise(iid, name, category):
    """-> MFG category slug for one item.

    iid      : item id (goods/weapon/protector/accessory/gem id)
    name     : English item name (may be empty)
    category : lotItemCategory (1=Goods 2=Weapon 3=Protector 4=Accessory 5=Gem)
    """
    low = (name or "").lower()

    if category == 1:
        # --- name-driven rules, checked before every id rule ------------------
        #
        # extract_items.py always passes the English name (engus), so a test on
        # it is language-independent as well as id-independent. These exist
        # because there are two families the id tables cannot be trusted for:
        #
        #   * anything the ERR and vanilla item tables disagree about. MFG's ERR
        #     profile puts the Rune Arc at goods id 150, but on a vanilla game
        #     150 is the Furlcalling Finger Remedy. Running that constant on a
        #     vanilla install filed 22 remedies under "Rune Arcs" and left all 55
        #     real rune arcs to fall through into "stat boosts". The name says
        #     which item it is on either profile.
        #   * the DLC blessing items, whose ids are not a range we can infer.
        if "rune arc" in low:
            return "rune_arcs"
        if "furlcalling finger remedy" in low:
            return "mp_fingers"
        if "revered spirit ash" in low:
            return "spirit_blessing"
        if "golden seed" in low:
            return "golden_seeds"
        if "sacred tear" in low:
            return "sacred_tears"
        if "scadutree fragment" in low:
            return "scadutree_fragments"
        # Bell bearings, split by what the Twin Maiden Husks unlock with them.
        # Upstream tested for "merchant" in the name, which never appears: the
        # merchant-side bearings are named Seller's / Monger's / Herbalist's /
        # Spellmachinist's, so merchant_bell_bearings was unreachable and all 16
        # landed in one row.
        if "bell bearing" in low:
            if "somberstone miner" in low:
                return "bell_somber"
            if "smithing-stone miner" in low:
                return "bell_smithing"
            if "ghost-glovewort picker" in low:
                return "bell_ghost_glovewort"
            if "glovewort picker" in low:
                return "bell_glovewort"
            return "merchant_bell_bearings"

        # Runes, split by level the way the smithing stones are. The old split was
        # two rows, golden_runes_low and golden_runes, built from two id sets; it
        # cut three different ladders at three different points - Golden Rune at
        # [8]/[9] but Shadow Realm Rune at [2]/[3] - so "low" and "high" described
        # nothing, and Hero's Rune [1] ended up filed beside Golden Rune [13].
        # The level is in the item's own name, so read it from there.
        if "rune" in low:
            for family, prefix in RUNE_PREFIXES:
                if low.startswith(prefix) and low.endswith("]"):
                    level = low[len(prefix):-1]
                    if level.isdigit() and 1 <= int(level) <= RUNE_FAMILIES[family]:
                        return f"{family}_rune_{int(level)}"
            if "broken rune" in low:
                return "broken_rune"
            if ("lord's rune" in low or "marika's rune" in low
                    or "numen's rune" in low or "unsung hero" in low):
                return "special_runes"

        # Key items (specific ids first, most specific -> least specific)
        if iid == 2130:
            return "celestial_dew"
        if "cookbook" in low:
            return "cookbooks"
        if iid in CRYSTAL_TEAR_IDS or iid in (250, 251, 2011010):
            return "crystal_tears"
        if iid == 8186:
            return "imbued_sword_keys"
        if iid in (8185, 2008033):
            return "larval_tears"
        if iid == 10070:
            return "lost_ashes"
        if iid in (9500, 9501, 9510, 2009500) or _sg(iid) in (30, 40):
            return "pots_n_perfumes"
        # Id fallbacks for what the name rules above already caught, kept for the
        # case where a name is missing. 10010/10020/2010100 come from upstream,
        # which grouped exactly these three as one "seeds_tears" bucket - which
        # is why 18 Shadow-realm blessing pickups shared a legend row with
        # Limgrave's Golden Seeds until this split.
        if iid == SPIRIT_BLESSING_ID:
            return "spirit_blessing"
        if iid == 10010:
            return "golden_seeds"
        if iid == 10020:
            return "sacred_tears"
        if iid == 2010000:
            return "scadutree_fragments"
        if iid in (8970, 8971, 8972, 8973, 8974):
            return "whetblades"

        # Quest
        if iid == 2090:
            return "deathroot"
        if iid == 8193:
            return "seedbed_curses"

        # Reforged (ERR-specific)
        if iid in (900000, 900010, 22000):
            return "items_and_changes"
        if iid in FORTUNE_IDS:
            return "fortunes"
        if iid in SEALED_CURIO_IDS:
            return "sealed_curios"

        # Equipment via goods. Reforged moves spirit ashes to 300000-399999;
        # the id list also covers the vanilla ones, which that range misses -
        # without it every summon on an unmodded game lands in "misc".
        if SPIRIT_ASH_MIN <= iid <= SPIRIT_ASH_MAX or iid in SPIRIT_ASH_IDS:
            return "spirits"
        if iid in INCANTATION_IDS:
            return "incantations"
        if iid in SORCERY_IDS:
            return "sorceries"
        if iid == 10030:
            return "memory_stones"
        if iid in PRAYERBOOK_IDS:
            return "prayerbooks"

        # Loot
        if iid == 8000:
            return "stonesword_keys"
        if iid in SMITHING_LEVELS:
            lvl, somber = SMITHING_LEVELS[iid]
            return f"{'somber' if somber else 'smithing'}_stone_{lvl}"
        if iid in SMITHING_SHADOW_IDS:
            return "smithing_stone_shadow"
        if iid in SOMBER_SHADOW_IDS:
            return "somber_stone_shadow"
        if iid in SMITHING_RARE_IDS:
            return ("somber_stone_legend" if iid in (10168, 10174)
                    else "smithing_stone_legend")
        if iid in GOLDEN_RUNE_LEVEL_IDS:
            return f"golden_rune_{GOLDEN_RUNE_LEVEL_IDS[iid]}"
        if iid in HERO_RUNE_LEVEL_IDS:
            return f"hero_rune_{HERO_RUNE_LEVEL_IDS[iid]}"
        if iid in SHADOW_RUNE_LEVEL_IDS:
            return f"shadow_rune_{SHADOW_RUNE_LEVEL_IDS[iid]}"
        if iid in SPECIAL_RUNE_IDS:
            return "special_runes"
        if iid in BROKEN_RUNE_IDS:
            return "broken_rune"
        if iid == 10060:
            return "dragon_hearts"
        if iid in GLOVEWORT_LEVELS:
            family, lvl = GLOVEWORT_LEVELS[iid]
            return f"glovewort_{family}_{lvl}"
        if iid in GLOVEWORT_GREAT_IDS:
            return f"glovewort_{GLOVEWORT_GREAT_IDS[iid]}_great"
        if iid in PATE_IDS:
            return "prattling_pates"
        if iid in MP_FINGER_IDS:
            return "mp_fingers"

        # Sort-group driven loot (uses MFG's goods sort groups)
        sg = _sg(iid)
        if sg in (20, 61):
            return "consumables"
        if sg == 70:
            return "greases"
        if sg == 80:
            return "utilities"
        if sg == 10:
            return "stat_boosts"
        if sg == 50:
            return "throwables"
        if iid in CRAFTING_IDS:
            return "crafting_materials"
        if sg in (60, 81) and iid < 4000000 and iid != 2008000:
            return "reusables"

        # Catch-all: quest progression key items. Must be last for category 1.
        if not low.startswith("map:") and (
            iid in KEYITEM_IDS or iid in PROGRESSION_EXTRA or sg == 90
        ):
            return "progression"

        return "misc"

    if category == 2:
        if iid in AMMO_IDS:
            return "ammo"
        return "armaments"
    if category == 3:
        return "armour"
    if category == 4:
        return "talismans"
    if category == 5:
        return "ashes_of_war"

    return "misc"


# Category slug -> icon PNG basename (from MFG tools/map_categories.py).
