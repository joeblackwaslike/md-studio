"""Stylesheet plumbing: EPUB CSS reaches the Document and every extension."""

import tracemalloc
import zipfile
from collections.abc import Callable
from pathlib import Path

import pytest

from md_studio.core import ir
from md_studio.core.convert import convert
from md_studio.core.document import STYLESHEET_SEPARATOR
from md_studio.core.extensions import ExtCtx, MarkdownExtension
from md_studio.core.extensions import discovery as discovery_mod
from md_studio.readers.epub import read_epub
from md_studio.readers.epub import stylesheet as reader_stylesheet
from tests.readers._epub import (
    CSS_HEADINGS_STYLESHEET,
    ChapterSpec,
    build_css_headings_epub,
    build_epub,
    corrupt_first_stylesheet,
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

    assert read_epub(epub).stylesheet == f".a{{}}{STYLESHEET_SEPARATOR}.b{{}}"


def test_reader_leaves_stylesheet_empty_without_css(tmp_path: Path) -> None:
    epub = build_epub(tmp_path / "b.epub", "T", [ChapterSpec("One", "<p>x</p>")])

    assert read_epub(epub).stylesheet == ""


_BUDGET = 1_048_576


def test_corrupt_css_member_never_fails_the_book(tmp_path: Path) -> None:
    specs = [ChapterSpec("One", "<h1>One</h1><p>x</p>")]
    (tmp_path / "plain").mkdir()
    (tmp_path / "bad").mkdir()
    plain = build_epub(tmp_path / "plain" / "b.epub", "T", specs)
    styled = build_epub(tmp_path / "bad" / "src.epub", "T", specs, stylesheets=(".a{}",))
    broken = corrupt_first_stylesheet(styled, tmp_path / "bad" / "b.epub")

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


def test_leading_bom_is_dropped(tmp_path: Path) -> None:
    specs = [ChapterSpec("One", "<p>x</p>")]
    epub = build_epub(tmp_path / "b.epub", "T", specs, stylesheets=("\ufeff.a{font-size:2rem}",))

    document = read_epub(epub)

    assert document.stylesheet == ".a{font-size:2rem}"
    assert document.warnings == ()


def test_duplicate_manifest_entries_are_read_once(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    specs = [ChapterSpec("One", "<p>x</p>")]
    epub = build_epub(tmp_path / "b.epub", "T", specs, stylesheets=(".a{}",))
    duplicated = _with_repeated_css_items(epub, tmp_path / "dup" / "b.epub", 1_000)
    spy = _ReadSpy(reader_stylesheet.read_member_prefix)
    monkeypatch.setattr(reader_stylesheet, "read_member_prefix", spy)

    document = read_epub(duplicated)

    assert spy.paths == ["OEBPS/css/s0.css"]
    assert document.stylesheet == ".a{}"


def test_css_members_are_capped_and_each_attempt_costs_budget(tmp_path: Path) -> None:
    specs = [ChapterSpec("One", "<p>x</p>")]
    sheets = tuple(f".m{index}{{}}" for index in range(300))
    epub = build_epub(tmp_path / "b.epub", "T", specs, stylesheets=sheets)

    document = read_epub(epub)

    assert document.stylesheet.count(STYLESHEET_SEPARATOR) == 255
    assert any("first 256" in warning for warning in document.warnings)


def test_reader_warns_about_what_it_skipped_cut_or_replaced(tmp_path: Path) -> None:
    specs = [ChapterSpec("One", "<p>x</p>")]
    (tmp_path / "bad").mkdir()
    styled = build_epub(tmp_path / "bad" / "src.epub", "T", specs, stylesheets=(".a{}",))
    broken = corrupt_first_stylesheet(styled, tmp_path / "bad" / "b.epub")
    cut = build_epub(tmp_path / "cut.epub", "T", specs, stylesheets=(" " * (2 * _BUDGET),))
    replaced = build_epub(tmp_path / "rep.epub", "T", specs, stylesheets=(".a{}\x00",))

    assert any("skipped" in warning for warning in read_epub(broken).warnings)
    assert any("budget" in warning for warning in read_epub(cut).warnings)
    assert any("invalid characters" in warning for warning in read_epub(replaced).warnings)


class _ReadSpy:
    def __init__(self, real: Callable[[zipfile.ZipFile, str, int], bytes]) -> None:
        self._real = real
        self.paths: list[str] = []

    def __call__(self, archive: zipfile.ZipFile, path: str, limit: int) -> bytes:
        self.paths.append(path)
        return self._real(archive, path, limit)


def _with_repeated_css_items(source: Path, dest: Path, copies: int) -> Path:
    dest.parent.mkdir(parents=True, exist_ok=True)
    with zipfile.ZipFile(source) as original, zipfile.ZipFile(dest, "w") as rewritten:
        for member in original.infolist():
            payload = original.read(member.filename)
            if member.filename.endswith(".opf"):
                entry = b'<item id="c" href="css/s0.css" media-type="text/css"/>'
                payload = payload.replace(
                    b"</manifest>", b"".join((entry * copies, b"</manifest>"))
                )
            rewritten.writestr(member.filename, payload)
    return dest
