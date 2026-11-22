"""Images render as alt text by default and as ``![alt](src)`` when the document embeds them."""

from dataclasses import replace
from urllib.parse import unquote

import pytest
from lxml import html

from md_studio.core import ir
from md_studio.core.convert import convert
from md_studio.core.document import Document, DocumentMetadata, SourceChapter
from md_studio.core.render import Renderer


def _body(*nodes: ir.Inline, embed: bool) -> str:
    chapter = ir.ChapterIR(title="C", blocks=(ir.Paragraph(nodes),))
    return Renderer(embed_images=embed).render((chapter,)).body


def _image(src: str, alt: str = "A diagram") -> ir.Image:
    return ir.Image(alt=alt, src=src)


def test_images_render_as_alt_text_by_default() -> None:
    assert _body(_image("x.png"), embed=False) == "## C\n\nA diagram\n"


def test_embedded_image_renders_alt_and_source() -> None:
    assert (
        _body(_image("https://a.org/x.png"), embed=True)
        == "## C\n\n![A diagram](https://a.org/x.png)\n"
    )


def test_alt_text_is_escaped_like_other_bracket_text() -> None:
    body = _body(_image("https://a.org/x.png", r"a [b] `c` \d"), embed=True)

    assert r"![a \[b\] \`c\` \\d](https://a.org/x.png)" in body


@pytest.mark.parametrize(
    ("src", "expected"),
    [
        ("https://a.org/a b.png", "https://a.org/a%20b.png"),
        ("https://a.org/a(1).png", "https://a.org/a%281%29.png"),
        ("https://a.org/<x>.png", "https://a.org/%3Cx%3E.png"),
    ],
)
def test_source_is_made_safe_inside_parentheses(src: str, expected: str) -> None:
    assert f"![A diagram]({expected})" in _body(_image(src), embed=True)


@pytest.mark.parametrize(
    "src",
    [
        "data:image/png;base64,AAAA",
        " \tdata:image/png;base64,AAAA",
        "javascript:alert(1)",
        "//evil.example/x.png",
        "http://[x",
        "//[x",
        "",
        "  ",
    ],
)
def test_unsafe_or_empty_sources_fall_back_to_alt_text(src: str) -> None:
    assert _body(_image(src), embed=True) == "## C\n\nA diagram\n"


def test_embedding_does_not_leak_into_the_next_render() -> None:
    _body(_image("https://a.org/x.png"), embed=True)

    assert "![" not in _body(_image("https://a.org/x.png"), embed=False)


def test_document_flag_controls_embedding() -> None:
    chapter = SourceChapter("C", _element('<p><img src="https://a.org/x.png" alt="Pic"></p>'))
    document = Document(DocumentMetadata(title="T"), (chapter,))

    assert "![Pic](https://a.org/x.png)" in convert(replace(document, embed_images=True)).body
    assert "![" not in convert(document).body


def _element(markup: str) -> object:
    return html.fromstring(f"<div>{markup}</div>")


def test_a_trailing_backslash_in_the_source_is_encoded() -> None:
    assert "![A diagram](https://a.org/x%5C)" in _body(_image("https://a.org/x\\"), embed=True)


def test_alt_whitespace_is_collapsed_so_it_cannot_break_out() -> None:
    body = _body(_image("https://a.org/x.png", "one\n\n# Heading\r\ntwo"), embed=True)

    assert "![one # Heading two](https://a.org/x.png)" in body


def test_alt_whitespace_is_collapsed_when_the_source_cannot_embed() -> None:
    body = _body(_image("data:x", "one\n\ntwo"), embed=True)

    assert body == "## C\n\none two\n"


@pytest.mark.parametrize("char", ["\u2028", "\u2029", "\u00a0", "\u0085", "\u3000"])
def test_unicode_whitespace_in_a_source_is_encoded_as_utf8_bytes(char: str) -> None:
    body = _body(_image(f"https://a.org/a{char}b.png"), embed=True)
    destination = body.split("](", 1)[1].split(")", 1)[0]

    assert unquote(destination) == f"https://a.org/a{char}b.png"
    assert char not in destination
