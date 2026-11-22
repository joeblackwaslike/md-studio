"""Tests for the format-neutral Document model."""

from md_studio.core.document import Document, DocumentMetadata


def test_document_defaults_exclude_math() -> None:
    document = Document(metadata=DocumentMetadata())
    assert document.stylesheet == ""
    assert document.has_math is False


def test_positional_construction_keeps_warnings_in_place() -> None:
    document = Document(DocumentMetadata(), (), "", False, ("w",))  # noqa: FBT003 -- positional order is the point

    assert document.warnings == ("w",)
    assert document.embed_images is False
