"""Format-neutral source document handed from a reader to the core pipeline."""

from dataclasses import dataclass, field

STYLESHEET_SEPARATOR = "\x00"
"""Joins the sheets of ``Document.stylesheet``; NUL never occurs inside a sheet."""


@dataclass(frozen=True, slots=True)
class DocumentMetadata:
    """Raw Dublin-Core style metadata pulled from the source document."""

    title: str = ""
    authors: tuple[str, ...] = ()
    publisher: str = ""
    published: str = ""
    isbn: str = ""
    language: str = ""
    source_file: str = ""


@dataclass(frozen=True, slots=True)
class SourceChapter:
    """One source chapter: a resolved title and its content element.

    ``element`` is an lxml ``HtmlElement``, typed as ``object`` to avoid
    ``no-any-unimported`` leaks. ``title_is_fallback`` is true when the source gave the
    chapter no label and the title is only the file stem the reader fell back to.
    """

    title: str
    element: object
    title_is_fallback: bool = False


@dataclass(frozen=True, slots=True)
class Document:
    """A parsed source document: metadata plus chapters in reading order."""

    metadata: DocumentMetadata
    chapters: tuple[SourceChapter, ...] = field(default_factory=tuple)
    stylesheet: str = ""
    has_math: bool = False
    embed_images: bool = False
    warnings: tuple[str, ...] = ()
