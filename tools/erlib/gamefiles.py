"""The files the installed game ships, and where regulation.bin lives.

Every tool used to ask a second source first - a loose-file mod folder, so the
helpers took a `mod_dir` argument and fell back to the archive. This branch reads
only the installed game, so the lookups are plain archive reads and the signature
lost the argument. Kept as a module rather than inlined so there is one place to
change if the game's layout ever needs more than `/map/mapstudio/...` and
`regulation.bin`.
"""
import os


def has(dvd, archive_path):
    """Is that path in the game's archives?"""
    return dvd.has(archive_path)


def read(dvd, archive_path):
    """Read one file out of the game's archives."""
    return dvd.read(archive_path)


def regulation_path(game_dir):
    """The game's own regulation.bin."""
    return os.path.join(game_dir, "regulation.bin")
