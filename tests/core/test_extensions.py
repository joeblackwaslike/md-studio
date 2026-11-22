"""Tests for the extension pipeline, built-ins, and discovery."""

import importlib

import pytest

from md_studio.core import ir
from md_studio.core.exceptions import ExtensionLoadError, UnknownExtensionError
from md_studio.core.extensions import discover, resolve
from md_studio.core.extensions import discovery as discovery_mod
from md_studio.core.extensions.base import ExtCtx, MarkdownExtension
from md_studio.core.extensions.fix_broken_links import FixBrokenLinks
from md_studio.core.extensions.fix_headings import FixHeadings
from md_studio.core.extensions.reformat_toc import ReformatToc
from md_studio.core.extensions.remove_footnotes import RemoveFootnotes


def _ctx(**kwargs: object) -> ExtCtx:
    return ExtCtx(book=ir.BookMeta(title="B"), **kwargs)  # type: ignore[arg-type]


def test_discover_includes_builtins() -> None:
    names = set(discover())
    assert {"fix-headings", "remove-footnotes", "fix-broken-links", "reformat-toc"} <= names


def test_resolve_preserves_order() -> None:
    resolved = resolve(["remove-footnotes", "fix-headings"])
    assert [type(ext) for ext in resolved] == [RemoveFootnotes, FixHeadings]


def test_resolve_unknown_raises() -> None:
    with pytest.raises(UnknownExtensionError):
        resolve(["does-not-exist"])


def test_identity_defaults_are_noops() -> None:
    paragraph = ir.Paragraph((ir.Text("x"),))
    chapter = ir.ChapterIR(title="C", blocks=(paragraph,))
    ext = MarkdownExtension()
    assert ext.transform_chapter(chapter, _ctx()) is chapter
    assert ext.transform_book((chapter,), _ctx()) == (chapter,)


def test_remove_footnotes_strips_refs_and_defs() -> None:
    paragraph = ir.Paragraph((ir.Text("a"), ir.FootnoteRef("fn1")))
    footnote_body = ir.Paragraph((ir.Text("note"),))
    chapter = ir.ChapterIR(
        title="C",
        blocks=(paragraph,),
        footnotes=(ir.FootnoteDef("fn1", (footnote_body,)),),
    )
    transformed = RemoveFootnotes().transform_chapter(chapter, _ctx())
    assert transformed.footnotes == ()
    para = transformed.blocks[0]
    assert isinstance(para, ir.Paragraph)
    assert all(not isinstance(child, ir.FootnoteRef) for child in para.children)


def test_fix_headings_promotes_styled_paragraph() -> None:
    meta = ir.Meta(tag="div", style="font-size:26px")
    para = ir.Paragraph((ir.Text("A Big Title"),), meta)
    chapter = ir.ChapterIR(title="C", blocks=(para,))
    transformed = FixHeadings().transform_chapter(chapter, _ctx())
    assert isinstance(transformed.blocks[0], ir.Heading)


def test_fix_broken_links_unwraps_unresolved() -> None:
    chapter = ir.ChapterIR(
        title="C",
        blocks=(
            ir.Paragraph((ir.Link("ch2.xhtml#s", (ir.Text("dead"),)),)),
            ir.Paragraph((ir.Link("https://x", (ir.Text("ok"),)),)),
            ir.Paragraph((ir.Link("#fn1", (ir.Text("note"),)),)),
        ),
    )
    ctx = _ctx(anchors=frozenset(("fn1",)))
    transformed = FixBrokenLinks().transform_book((chapter,), ctx)
    blocks = transformed[0].blocks
    assert blocks[0].children == (ir.Text("dead"),)  # unwrapped
    assert isinstance(blocks[1].children[0], ir.Link)  # external kept
    assert isinstance(blocks[2].children[0], ir.Link)  # valid anchor kept


def test_reformat_toc_rebuilds_contents_chapter() -> None:
    garbage = ir.Paragraph((ir.Text("garbage"),))
    chapters = (
        ir.ChapterIR(title="Contents", blocks=(garbage,)),
        ir.ChapterIR(title="Chapter 1", blocks=()),
        ir.ChapterIR(title="Chapter 2", blocks=()),
    )
    transformed = ReformatToc().transform_book(chapters, _ctx())
    toc_blocks = transformed[0].blocks
    assert isinstance(toc_blocks[0], ir.ListBlock)
    assert len(toc_blocks[0].items) == 2


class _FakeEntryPoint:
    def __init__(self, name: str, type_: type) -> None:
        self.name = name
        self._type = type_

    def load(self) -> type:
        return self._type


class _ShadowFixHeadings(MarkdownExtension):
    """Third-party extension that tries to shadow the built-in ``fix-headings``."""

    name = "fix-headings"


class _FreshThirdPartyExtension(MarkdownExtension):
    """Genuinely new third-party extension name."""

    name = "third-party"


def test_discovery_reserves_builtin_names(monkeypatch: pytest.MonkeyPatch) -> None:
    fake_entry_points = [
        _FakeEntryPoint("fix-headings", _ShadowFixHeadings),
        _FakeEntryPoint("third-party", _FreshThirdPartyExtension),
    ]
    monkeypatch.setattr(discovery_mod, "entry_points", lambda group: fake_entry_points)
    registry = discover()
    assert registry["fix-headings"] is FixHeadings  # built-in wins
    assert registry["third-party"] is _FreshThirdPartyExtension


def test_entry_point_group_uses_md_studio_name() -> None:
    assert discovery_mod.ENTRY_POINT_GROUP == "md_studio.extensions"


class _BrokenEntryPoint:
    name = "broken"

    def load(self) -> type[MarkdownExtension]:
        raise ImportError("boom: missing dependency")


def test_resolve_reports_why_an_extension_failed_to_load(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(discovery_mod, "entry_points", lambda group: [_BrokenEntryPoint()])

    with pytest.raises(ExtensionLoadError, match=r"extension 'broken' failed to load: .*boom"):
        resolve(["broken"])


def test_resolve_still_reports_unknown_names_when_another_extension_failed(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(discovery_mod, "entry_points", lambda group: [_BrokenEntryPoint()])

    with pytest.raises(UnknownExtensionError, match="nope"):
        resolve(["nope"])


@pytest.mark.parametrize("style", ["font-size:.", "font-size:1.2.3", "font-size: ..;"])
def test_fix_headings_ignores_malformed_font_sizes(style: str) -> None:
    para = ir.Paragraph((ir.Text("Not A Title"),), ir.Meta(tag="div", style=style))
    chapter = ir.ChapterIR(title="C", blocks=(para,))

    transformed = FixHeadings().transform_chapter(chapter, _ctx())

    assert isinstance(transformed.blocks[0], ir.Paragraph)


class _LazyImportExtension(MarkdownExtension):
    name = "lazy"

    def __init__(self) -> None:
        importlib.import_module("md_studio_missing_module")


class _BuggyExtension(MarkdownExtension):
    name = "buggy"

    def __init__(self) -> None:
        raise ValueError("programming error")


class _ClassEntryPoint:
    def __init__(self, extension_cls: type[MarkdownExtension]) -> None:
        self.name = extension_cls.name

        self._cls = extension_cls

    def load(self) -> type[MarkdownExtension]:
        return self._cls


def _install(monkeypatch: pytest.MonkeyPatch, *classes: type[MarkdownExtension]) -> None:
    points = [_ClassEntryPoint(extension_cls) for extension_cls in classes]
    monkeypatch.setattr(discovery_mod, "entry_points", lambda group: points)


def test_resolve_reports_import_errors_raised_while_constructing(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    _install(monkeypatch, _LazyImportExtension)

    with pytest.raises(
        ExtensionLoadError, match=r"extension 'lazy' failed to load: .*md_studio_missing"
    ):
        resolve(["lazy"])


def test_resolve_reports_any_construction_error_as_a_load_error(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    _install(monkeypatch, _BuggyExtension)

    with pytest.raises(
        ExtensionLoadError, match=r"extension 'buggy' failed to load: .*programming"
    ):
        resolve(["buggy"])
