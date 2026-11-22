"""Convert a plain CSS ``font-size`` length to rem."""

import re
from types import MappingProxyType

_MAX_VALUE_CHARS = 32
_PX_PER_REM = 16
_PT_PER_REM = 12
_PERCENT = 100
_PRECISION = 9
_UNITS_PER_REM = MappingProxyType({
    "rem": 1,
    "em": 1,
    "px": _PX_PER_REM,
    "pt": _PT_PER_REM,
    "%": _PERCENT,
})
_SIZE = re.compile(r"(\d+(?:\.\d+)?|\.\d+)(rem|em|px|pt|%)")


def size_in_rem(raw: str) -> float | None:
    """Return a CSS font size in rem, or ``None`` when it is not a plain length.

    ``em`` and ``%`` are taken as relative to the root font size; ``px`` and ``pt`` are
    converted at 16px and 12pt per rem. Anything else (``calc()``, ``var()``, keywords)
    is not a plain length. Division and rounding keep exact boundaries exact.
    """
    if len(raw) > _MAX_VALUE_CHARS:
        return None
    match = _SIZE.fullmatch(raw)
    if match is None:
        return None
    number, unit = match.groups()
    return round(float(number) / _UNITS_PER_REM[unit], _PRECISION)
