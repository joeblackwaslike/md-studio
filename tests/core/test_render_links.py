"""Link destinations are percent-encoded so a hostile href cannot break out of ``(...)``."""

from urllib.parse import unquote

import pytest

from md_studio.core import ir
from md_studio.core.render import render_inlines


def _link(href: str) -> str:
    return render_inlines((ir.Link(href, (ir.Text("t"),)),))


def test_an_ordinary_href_is_unchanged() -> None:
    assert _link("https://a.org/x?y=1#z") == "[t](https://a.org/x?y=1#z)"


def test_a_fragment_href_is_unchanged() -> None:
    assert _link("#part-i--chapter-1") == "[t](#part-i--chapter-1)"


@pytest.mark.parametrize(
    ("href", "expected"),
    [
        ("https://a/x y", "https://a/x%20y"),
        ("https://a/x(1)", "https://a/x%281%29"),
        ("https://a/<x>", "https://a/%3Cx%3E"),
        ("https://a/x\\", "https://a/x%5C"),
        ("https://a/x\n# H", "https://a/x%0A#%20H"),
        ("https://a/x\x00\x1f\x7f", "https://a/x%00%1F%7F"),
    ],
)
def test_unsafe_characters_are_percent_encoded(href: str, expected: str) -> None:
    assert _link(href) == f"[t]({expected})"


def test_a_hostile_href_cannot_inject_a_second_link() -> None:
    rendered = _link("https://a/x) [p](https://evil")

    assert rendered.count("](") == 1
    assert rendered.endswith(")")
    assert "\n" not in rendered


@pytest.mark.parametrize("char", ["\u2028", "\u2029", "\u00a0", "\u0085", "\u3000"])
def test_unicode_whitespace_is_encoded_as_utf8_bytes(char: str) -> None:
    rendered = _link(f"https://a/x{char}y")
    destination = rendered.removeprefix("[t](").removesuffix(")")

    assert char not in destination
    assert unquote(destination) == f"https://a/x{char}y"
    assert "%2028" not in destination
    assert "%3000" not in destination


def test_existing_percent_escapes_are_not_encoded_again() -> None:
    assert _link("https://a/x%20y") == "[t](https://a/x%20y)"
