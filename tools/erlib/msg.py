"""Item names in every locale, read from the game's own message files.

Four extractors used to read only /msg/zhocn/ and then write the Chinese string into both the `zh` and the
`en` field, which made 22,905 markers show Chinese in the English interface. Reading every locale here
keeps that from being reintroduced one tool at a time.
"""
import erlib.gamefiles as gamefiles
from erlib import fmg

# locale -> the folder the game keeps that language's message files in
LOCALES = {"en": "engus", "zh": "zhocn"}
DEFAULT_FILES = ("item.msgbnd.dcx", "item_dlc02.msgbnd.dcx")


def load(dvd, oodle=None, files=DEFAULT_FILES):
    """{'en': {category: {id: text}}, 'zh': {...}} for the item message files present in the archive."""
    out = {loc: {} for loc in LOCALES}
    for loc, table in LOCALES.items():
        for name in files:
            path = "/msg/%s/%s" % (table, name)
            if not gamefiles.has(dvd, path):
                continue
            for key, values in fmg.load_msgbnd(gamefiles.read(dvd, path), oodle=oodle).items():
                out[loc].setdefault(key.split("_dlc")[0], {}).update(values)
    return out


def text(names, loc, category, item_id, fallback="en"):
    """The name of one item in one locale, falling back to the other locale when it is missing.

    A DLC item can exist in the base table of one language and only in the DLC table of another, so the
    fallback keeps a marker labelled rather than blank.
    """
    value = ((names.get(loc) or {}).get(category) or {}).get(item_id)
    if value:
        return value
    return ((names.get(fallback) or {}).get(category) or {}).get(item_id) or ""
