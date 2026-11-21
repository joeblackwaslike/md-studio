"""Stylesheet plumbing: EPUB CSS reaches the Document and every extension."""

import tracemalloc
import zipfile
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


_BUDGET = 1_048_576


def _with_corrupt_css(source: Path, dest: Path) -> Path:
    with zipfile.ZipFile(source) as archive:
        member = archive.getinfo("OEBPS/css/s0.css")
        data_start = member.header_offset + 30 + len(member.filename.encode()) + len(member.extra)
    raw = source.read_bytes()
    dest.write_bytes(raw[:data_start] + b"\xff" * 4 + raw[data_start + 4 :])
    return dest


def test_corrupt_css_member_never_fails_the_book(tmp_path: Path) -> None:
    specs = [ChapterSpec("One", "<h1>One</h1><p>x</p>")]
    (tmp_path / "plain").mkdir()
    (tmp_path / "bad").mkdir()
    plain = build_epub(tmp_path / "plain" / "b.epub", "T", specs)
    styled = build_epub(tmp_path / "bad" / "src.epub", "T", specs, stylesheets=(".a{}",))
    broken = _with_corrupt_css(styled, tmp_path / "bad" / "b.epub")

    document = read_epub(broken)

    assert document.stylesheet == ""
    assert convert(document).text == convert(read_epub(plain)).text


def test_huge_declared_css_member_is_read_only_up_to_the_budget(tmp_path: Path) -> None:
    specs = [ChapterSpec("One", "<p>x</p>")]
    epub = build_epub(tmp_path / "b.epub", "T", specs, stylesheets=(" " * (70 * _BUDGET),))
    tracemalloc.start()
    document = read_epub(epub)
    peak = tracemalloc.get_traced_memory()[1]
    tracemalloc.stop()

    assert len(document.stylesheet) == _BUDGET
    assert peak < 20_000_000


def test_css_budget_is_shared_across_members(tmp_path: Path) -> None:
    specs = [ChapterSpec("One", "<p>x</p>")]
    sheets = tuple(f".m{index}{{}}{' ' * 600_000}" for index in range(3))
    epub = build_epub(tmp_path / "b.epub", "T", specs, stylesheets=sheets)

    stylesheet = read_epub(epub).stylesheet

    assert len(stylesheet) <= _BUDGET
    assert ".m0{}" in stylesheet
    assert ".m1{}" in stylesheet
    assert ".m2{}" not in stylesheet
