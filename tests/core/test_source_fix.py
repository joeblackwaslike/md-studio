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
    def __init__(self, registered: object, name: str | None = None) -> None:
        self.name = getattr(registered, "name", "unnamed") if name is None else name
        self._registered = registered

    def load(self) -> object:
        return self._registered


def _install(monkeypatch: pytest.MonkeyPatch, *registered: object) -> None:
    points = [_EntryPoint(entry) for entry in registered]
    monkeypatch.setattr(discovery_mod, "entry_points", lambda group: points)


def _install_named(monkeypatch: pytest.MonkeyPatch, name: str, registered: object) -> None:
    points = [_EntryPoint(registered, name)]
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


def test_first_registered_name_wins_over_a_later_colliding_kind(
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


class _Both(MarkdownExtension):
    name = "both"

    def apply(self, document: Document) -> Document:
        return document


class _EmptyName:
    name: ClassVar[str] = ""

    def apply(self, document: Document) -> Document:
        return document


class _NoName:
    def apply(self, document: Document) -> Document:
        return document


class _NonStringName:
    name = 3

    def apply(self, document: Document) -> Document:
        return document


class _ApplyNotCallable:
    name: ClassVar[str] = "apply-not-callable"
    apply = "nope"


class _Interrupting(MarkdownExtension):
    name = "interrupting"

    def __init__(self) -> None:
        raise KeyboardInterrupt


class _Crashing(MarkdownExtension):
    name = "crashing"

    def __init__(self) -> None:
        raise RuntimeError("constructor exploded")


def _fix_instance() -> _AppendA:
    return _AppendA()


@pytest.mark.parametrize(
    ("name", "registered", "reason"),
    [
        ("str", "not a class", "not a class"),
        ("func", _fix_instance, "not a class"),
        ("instance", _AppendA(), "not a class"),
        ("both", _Both, "both"),
        ("empty", _EmptyName, "name"),
        ("noname", _NoName, "name"),
        ("intname", _NonStringName, "name"),
        ("apply-not-callable", _ApplyNotCallable, "apply"),
    ],
)
def test_unusable_registration_is_a_load_error_naming_the_reason(
    monkeypatch: pytest.MonkeyPatch, name: str, registered: object, reason: str
) -> None:
    _install_named(monkeypatch, name, registered)

    with pytest.raises(ExtensionLoadError, match=rf"extension '{name}' failed to load: .*{reason}"):
        resolve([name])


def test_unusable_registration_is_not_discoverable(monkeypatch: pytest.MonkeyPatch) -> None:
    _install_named(monkeypatch, "both", _Both)

    assert "both" not in discover()


def test_constructor_failure_becomes_a_load_error(monkeypatch: pytest.MonkeyPatch) -> None:
    _install(monkeypatch, _Crashing)

    with pytest.raises(
        ExtensionLoadError, match=r"'crashing' failed to load: RuntimeError: .*exploded"
    ):
        resolve(["crashing"])


def test_keyboard_interrupt_during_construction_propagates(monkeypatch: pytest.MonkeyPatch) -> None:
    _install(monkeypatch, _Interrupting)

    with pytest.raises(KeyboardInterrupt):
        resolve(["interrupting"])


def test_a_built_in_still_runs_when_an_entry_point_reuses_its_name(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    _install(monkeypatch, _SourceFixNamedLikeBuiltin)

    assert [type(entry) for entry in resolve(["fix-headings"])] == [discovery_mod.FixHeadings]


def test_collision_does_not_affect_other_requested_names(monkeypatch: pytest.MonkeyPatch) -> None:
    _install(monkeypatch, _SourceFixNamedLikeBuiltin)

    assert [type(entry) for entry in resolve(["reformat-toc"])] == [discovery_mod.ReformatToc]


def test_the_first_of_two_third_party_registrations_runs_and_the_second_is_ignored(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    _install(monkeypatch, _FirstDuplicate, _SecondDuplicate)

    assert [type(entry) for entry in resolve(["dup"])] == [_FirstDuplicate]


def test_a_broken_entry_point_with_a_unique_name_still_raises_when_requested(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    _install_named(monkeypatch, "broken-load", "not a class")

    with pytest.raises(ExtensionLoadError, match="broken-load"):
        resolve(["broken-load"])


def test_a_dropped_duplicate_is_logged_not_raised(
    monkeypatch: pytest.MonkeyPatch, caplog: pytest.LogCaptureFixture
) -> None:
    _install(monkeypatch, _FirstDuplicate, _SecondDuplicate)

    with caplog.at_level("WARNING"):
        resolve(["dup"])

    assert "name already registered" in caplog.text
