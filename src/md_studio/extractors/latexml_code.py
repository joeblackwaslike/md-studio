"""Listings: ``lstlisting`` blocks become ``<pre><code class="language-..">``."""

import re

from lxml import html as lxml_html

from md_studio.readers.html import HtmlElement

_LANGUAGE_PREFIX = "ltx_lst_language_"
_LINE_CLASS = "ltx_listingline"
_DATA_CLASS = "ltx_listing_data"
_UNSAFE_LANGUAGE = re.compile(r"[^a-z0-9_+#-]")
_NBSP = "\u00a0"
_CLASS = "class"


def listing_block(listing: HtmlElement) -> HtmlElement:
    """Return a ``pre`` holding the listing's lines, tagged with its language."""
    pre = lxml_html.Element("pre")
    code = lxml_html.Element("code")
    language = _language(listing)
    if language:
        code.set(_CLASS, f"language-{language}")
    code.text = _source(listing)
    pre.append(code)
    return pre


def _classes(element: HtmlElement) -> list[str]:
    return str(element.get(_CLASS, "")).split()


def _language(listing: HtmlElement) -> str:
    for name in _classes(listing):
        if name.startswith(_LANGUAGE_PREFIX):
            return _UNSAFE_LANGUAGE.sub("", name.removeprefix(_LANGUAGE_PREFIX).lower())
    return ""


def _source(listing: HtmlElement) -> str:
    """Return the code of *listing* one line per ``ltx_listingline``, without the data link."""
    lines = [
        "".join(line.itertext()).replace(_NBSP, " ").rstrip()
        for line in listing
        if _LINE_CLASS in _classes(line)
    ]
    if not lines and not _only_data(listing):
        return "".join(listing.itertext()).strip()
    return "\n".join(lines)


def _only_data(listing: HtmlElement) -> bool:
    return all(_DATA_CLASS in _classes(child) for child in listing)
