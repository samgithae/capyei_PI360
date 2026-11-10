"""Read protected runtime settings without importing the module that owns them.

Configuration registers its reader at start-up; other modules call ``setting(key)``. If nothing is
registered the given default is used.
"""

from collections.abc import Callable

_reader: Callable[[str], object] | None = None


def register(reader: Callable[[str], object]) -> None:
    global _reader
    _reader = reader


def setting(key: str, default=None):
    return default if _reader is None else _reader(key)
