"""End-to-end tests for ``convert``: determinism, images, result shape."""

from pathlib import Path

import pytest

from md_studio.core.convert import convert
from md_studio.core.document import Document
from md_studio.core.exceptions import UnknownExtensionError
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
