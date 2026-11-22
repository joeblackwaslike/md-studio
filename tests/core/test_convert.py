"""End-to-end tests for ``convert``: determinism, images, result shape."""

import sys
from dataclasses import replace
from pathlib import Path

import pytest
import yaml
from lxml import etree
from lxml import html as lxml_html

from md_studio.core.convert import convert
from md_studio.core.document import Document, DocumentMetadata, SourceChapter
from md_studio.core.exceptions import ReadError, UnknownExtensionError
from md_studio.core.render.options import RenderOptions, current_options
from md_studio.readers.epub import read_epub
from tests.readers._epub import ChapterSpec, build_epub


def _document(tmp_path: Path) -> Document:
    specs = [
        ChapterSpec("One", "<p>Alice <em>fell</em>.</p>"),
        ChapterSpec("Two", '<p>See <img src="f.png" alt="the figure"/> here.</p>'),
    ]
    return read_epub(build_epub(tmp_path / "src.epub", "Story", specs))


def test_deterministic_output(tmp_path: Path) -> None:
    document = _document(tmp_path)
    assert convert(document).text == convert(document).text


def test_images_render_as_alt_text_only(tmp_path: Path) -> None:
    text = convert(_document(tmp_path)).text
    assert "the figure" in text
    assert "![" not in text
    assert "f.png" not in text


def test_result_parts_compose_text(tmp_path: Path) -> None:
    rendered = convert(_document(tmp_path))
    assert rendered.text == f"{rendered.front_matter}{rendered.body}"
    assert len(rendered.chapters) == 2


def test_unknown_extension_raises(tmp_path: Path) -> None:
    with pytest.raises(UnknownExtensionError):
        convert(_document(tmp_path), extensions=["nope"])


def test_rendered_chapters_are_an_immutable_tuple_of_ranges(tmp_path: Path) -> None:
    chapters = convert(_document(tmp_path)).chapters

    assert isinstance(chapters, tuple)
    assert [entry.title for entry in chapters] == ["One", "Two"]


def test_document_without_chapters_converts_to_front_matter_only() -> None:
    rendered = convert(Document(DocumentMetadata(title="Empty")))

    assert rendered.chapters == ()
    assert rendered.body == ""
    parsed = yaml.safe_load(rendered.front_matter.split("---\n")[1])
    assert parsed["title"] == "Empty"
    assert not parsed["chapters"]
    assert rendered.text == rendered.front_matter


def _nested(depth: int) -> Document:
    root = lxml_html.Element("div")
    node = root
    for _ in range(depth):
        node = etree.SubElement(node, "div")
    node.text = "deep"
    return Document(DocumentMetadata(title="T"), (SourceChapter("T", root),))


def _too_deep() -> Document:
    return replace(_nested(sys.getrecursionlimit() + 100), has_math=True, embed_images=True)


def test_a_document_nested_past_the_recursion_limit_is_a_read_error() -> None:
    with pytest.raises(ReadError, match="Document nests too deeply"):
        convert(_too_deep())


def test_a_failed_deep_conversion_leaves_no_render_state_behind() -> None:
    with pytest.raises(ReadError):
        convert(_too_deep())

    assert current_options() == RenderOptions()
    assert "deep" in convert(_nested(5)).body


def test_epub_link_destinations_are_percent_encoded(tmp_path: Path) -> None:
    html = '<p><a href="Foo_(bar).xhtml">x</a> and <a href="my file.xhtml#a">y</a></p>'
    document = read_epub(build_epub(tmp_path / "l.epub", "L", [ChapterSpec("One", html)]))

    body = convert(document).body

    assert "[x](Foo_%28bar%29.xhtml)" in body
    assert "[y](my%20file.xhtml#a)" in body
