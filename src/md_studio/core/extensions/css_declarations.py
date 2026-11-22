"""Parse the declarations of one untrusted CSS rule body, with ``!important`` and cascade."""

from collections.abc import Iterator
from typing import NamedTuple


class Declared(NamedTuple):
    """A declaration value (lowercased, without ``!important``) and whether it was important."""

    text: str
    important: bool


def _declared(raw: str) -> Declared:
    """Parse the text after ``name:`` into a value and its importance."""
    text, bang, flag = raw.partition("!")
    important = bool(bang) and flag.strip().lower() == "important"
    return Declared(text.strip().lower(), important)


def override(found: dict[str, Declared], name: str, declared: Declared) -> None:
    """Record *declared* for *name* unless an important one is already there and it is not."""
    previous = found.get(name)
    if previous is None or declared.important or not previous.important:
        found[name] = declared


def declaration_list(body: str) -> Iterator[tuple[str, Declared]]:
    """Yield ``(property, declaration)`` for each declaration of *body* in order, names lowercased."""
    for declaration in body.split(";"):
        name, colon, raw = declaration.partition(":")
        if colon:
            yield name.strip().lower(), _declared(raw)


def declarations(body: str) -> dict[str, Declared]:
    """Return the winning declaration of each property in *body*, names lowercased.

    Later declarations win, except that an ``!important`` one is only replaced by another
    ``!important`` one.
    """
    found: dict[str, Declared] = {}
    for name, declared in declaration_list(body):
        override(found, name, declared)
    return found


Merged = dict[str, dict[str, Declared]]


def add_class(found: Merged, name: str, relevant: dict[str, Declared], limit: int) -> bool:
    """Cascade *relevant* into class *name*; return ``False`` if the *limit* refused a new class."""
    if name not in found and len(found) >= limit:
        return False
    merged = found.setdefault(name, {})
    for key, declared in relevant.items():
        override(merged, key, declared)
    return True
