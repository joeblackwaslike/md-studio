"""A stylesheet changes nothing unless an extension that reads it is enabled."""

from pathlib import Path

from md_studio.core.convert import convert
from md_studio.core.extensions import ExtCtx
from md_studio.core.extensions.audit import PromotionRecord
from md_studio.core.extensions.base import is_extension
from md_studio.core.extensions.discovery import BUILTINS
from md_studio.core.extensions.fix_headings import FixHeadings
from md_studio.core.extensions.pipeline import resolve, split
from md_studio.core.extensions.reformat_toc import ReformatToc
from md_studio.readers.epub import read_epub
from tests.readers._epub import CSS_HEADINGS_BODY, ChapterSpec, build_css_headings_epub, build_epub


def test_default_conversion_ignores_the_stylesheet(tmp_path: Path) -> None:
    (tmp_path / "with").mkdir()
    (tmp_path / "without").mkdir()
    styled = build_css_headings_epub(tmp_path / "with" / "book.epub")
    plain = build_epub(
        tmp_path / "without" / "book.epub",
        "Styled",
        [ChapterSpec("Chapter One", CSS_HEADINGS_BODY)],
    )

    with_css = convert(read_epub(styled))
    without_css = convert(read_epub(plain))

    assert with_css.text == without_css.text
    assert with_css.notes == ()
    assert with_css.promotions == ()


def test_extensions_that_ignore_css_leave_the_output_unchanged(tmp_path: Path) -> None:
    (tmp_path / "with").mkdir()
    (tmp_path / "without").mkdir()
    styled = build_css_headings_epub(tmp_path / "with" / "book.epub")
    plain = build_epub(
        tmp_path / "without" / "book.epub",
        "Styled",
        [ChapterSpec("Chapter One", CSS_HEADINGS_BODY)],
    )

    names = ["remove-footnotes", "fix-broken-links", "reformat-toc"]

    assert convert(read_epub(styled), extensions=names).text == (
        convert(read_epub(plain), extensions=names).text
    )


def test_context_equality_and_hash_ignore_the_collectors() -> None:
    from md_studio.core import ir  # noqa: PLC0415

    book = ir.BookMeta(title="B")
    first = ExtCtx(book=book, stylesheet=".a{}")
    second = ExtCtx(book=book, stylesheet=".a{}")

    first.audit.append(PromotionRecord("C", "T", "div", (), 1))
    first.notes.append("lost something")

    assert first == second
    assert hash(first) == hash(second)


def test_all_built_ins_are_markdown_extensions_in_listed_order() -> None:
    assert all(is_extension(registered) for registered in BUILTINS)

    fixes, extensions = split(resolve(["reformat-toc", "fix-headings"]))

    assert fixes == []
    assert [type(extension) for extension in extensions] == [ReformatToc, FixHeadings]


def test_is_extension_distinguishes_classes_and_instances() -> None:
    assert is_extension(FixHeadings)
    assert is_extension(FixHeadings())
    assert not is_extension(dict)
    assert not is_extension(object())
