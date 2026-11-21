"""Source-level fixes: one registry, two kinds, run before extraction."""

from dataclasses import replace
from pathlib import Path
from typing import ClassVar

import pytest

from md_studio.core import ir
from md_studio.core.convert import convert
from md_studio.core.document import Document
from md_studio.core.exceptions import ExtensionLoadError
from md_studio.core.extensions import ExtCtx, MarkdownExtension, discover, resolve
from md_studio.core.extensions import discovery as discovery_mod
from md_studio.core.extensions.source_fix import SourceFix
from md_studio.readers.epub import read_epub
from tests.readers._epub import ChapterSpec, build_epub


class _KeepFirstChapter:
    name: ClassVar[str] = "keep-first"

    def apply(self, document: Document) -> Document:
        return replace(document, chapters=document.chapters[:1])


class _AppendA:
    name: ClassVar[str] = "append-a"

    def apply(self, document: Document) -> Document:
        return replace(document, stylesheet=f"{document.stylesheet}a")


class _AppendB:
    name: ClassVar[str] = "append-b"

    def apply(self, document: Document) -> Document:
        return replace(document, stylesheet=f"{document.stylesheet}b")


class _SeesStylesheet(MarkdownExtension):
    name = "sees-stylesheet"
    seen: list[str] = []  # noqa: RUF012 -- shared test spy

    def transform_chapter(self, chapter: ir.ChapterIR, ctx: ExtCtx) -> ir.ChapterIR:
        self.seen.append(ctx.stylesheet)
        return chapter


class _TagTitle(MarkdownExtension):
    name = "tag-title"

    def transform_chapter(self, chapter: ir.ChapterIR, ctx: ExtCtx) -> ir.ChapterIR:
        return ir.ChapterIR(title=f"{chapter.title} (tagged)", blocks=chapter.blocks)


class _NotAFix:
    name: ClassVar[str] = "not-a-fix"


class _SourceFixNamedLikeBuiltin:
    name: ClassVar[str] = "fix-headings"

    def apply(self, document: Document) -> Document:
        return document


class _FirstDuplicate(MarkdownExtension):
    name = "dup"


class _SecondDuplicate:
    name: ClassVar[str] = "dup"

    def apply(self, document: Document) -> Document:
        return document


class _EntryPoint:
    def __init__(self, registered: type) -> None:
        self.name = registered.name
        self._registered = registered

    def load(self) -> type:
        return self._registered


def _install(monkeypatch: pytest.MonkeyPatch, *registered: type) -> None:
    points = [_EntryPoint(entry) for entry in registered]
    monkeypatch.setattr(discovery_mod, "entry_points", lambda group: points)


def _document(tmp_path: Path) -> Document:
    specs = [ChapterSpec("One", "<p>one</p>"), ChapterSpec("Two", "<p>two</p>")]
    return read_epub(build_epub(tmp_path / "b.epub", "T", specs))


def test_new_fix_is_one_class_plus_registry_line(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    _install(monkeypatch, _KeepFirstChapter, _TagTitle)

    rendered = convert(_document(tmp_path), extensions=["keep-first", "tag-title"])

    assert [chapter.title for chapter in rendered.chapters] == ["One (tagged)"]


def test_source_fix_satisfies_the_protocol() -> None:
    fix: SourceFix = _KeepFirstChapter()

    assert fix.name == "keep-first"


def test_source_fixes_run_before_extensions_whatever_the_listed_order(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    _install(monkeypatch, _SeesStylesheet, _AppendA)
    _SeesStylesheet.seen.clear()

    convert(_document(tmp_path), extensions=["sees-stylesheet", "append-a"])

    assert _SeesStylesheet.seen == ["a", "a"]


@pytest.mark.parametrize(
    ("names", "expected"), [(["append-a", "append-b"], "ab"), (["append-b", "append-a"], "ba")]
)
def test_source_fixes_run_in_listed_order(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, names: list[str], expected: str
) -> None:
    _install(monkeypatch, _SeesStylesheet, _AppendA, _AppendB)
    _SeesStylesheet.seen.clear()

    convert(_document(tmp_path), extensions=[*names, "sees-stylesheet"])

    assert _SeesStylesheet.seen[0] == expected


def test_source_fix_cannot_shadow_a_builtin(monkeypatch: pytest.MonkeyPatch) -> None:
    _install(monkeypatch, _SourceFixNamedLikeBuiltin)

    assert discover()["fix-headings"] is discovery_mod.FixHeadings


def test_name_collision_between_source_fix_and_extension_is_rejected(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    _install(monkeypatch, _FirstDuplicate, _SecondDuplicate)

    assert discover()["dup"] is _FirstDuplicate


def test_builtin_names_are_unique() -> None:
    names = [entry.name for entry in discovery_mod.BUILTINS]

    assert len(names) == len(set(names))


def test_registered_object_that_is_neither_kind_fails_to_load(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    _install(monkeypatch, _NotAFix)

    with pytest.raises(ExtensionLoadError, match="not-a-fix"):
        resolve(["not-a-fix"])
