"""Stylesheet plumbing: EPUB CSS reaches the Document and every extension."""

from pathlib import Path

import pytest

from md_studio.core import ir
from md_studio.core.convert import convert
from md_studio.core.extensions import ExtCtx, MarkdownExtension
from md_studio.core.extensions import discovery as discovery_mod
from md_studio.readers.epub import read_epub
from tests.readers._epub import (
    CSS_HEADINGS_STYLESHEET,
    ChapterSpec,
    build_css_headings_epub,
    build_epub,
)


class _Recorder(MarkdownExtension):
    name = "record-stylesheet"
    seen: list[str] = []  # noqa: RUF012 -- shared test spy

    def transform_chapter(self, chapter: ir.ChapterIR, ctx: ExtCtx) -> ir.ChapterIR:
        self.seen.append(ctx.stylesheet)
        return chapter


class _EntryPoint:
    name = _Recorder.name

    def load(self) -> type[MarkdownExtension]:
        return _Recorder


def test_stylesheet_reaches_extensions(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(discovery_mod, "entry_points", lambda group: [_EntryPoint()])
    _Recorder.seen.clear()
    document = read_epub(build_css_headings_epub(tmp_path / "styled.epub"))

    convert(document, extensions=["record-stylesheet"])

    assert _Recorder.seen == [CSS_HEADINGS_STYLESHEET]


def test_reader_concatenates_css_in_manifest_order(tmp_path: Path) -> None:
    specs = [ChapterSpec("One", "<p>x</p>")]
    epub = build_epub(tmp_path / "b.epub", "T", specs, stylesheets=(".a{}", ".b{}"))

    assert read_epub(epub).stylesheet == ".a{}\n.b{}"


def test_reader_leaves_stylesheet_empty_without_css(tmp_path: Path) -> None:
    epub = build_epub(tmp_path / "b.epub", "T", [ChapterSpec("One", "<p>x</p>")])

    assert read_epub(epub).stylesheet == ""
