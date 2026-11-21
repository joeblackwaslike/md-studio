"""Tests for the format-neutral Document model."""

from md_studio.core.document import Document, DocumentMetadata


def test_document_defaults_exclude_math() -> None:
    document = Document(metadata=DocumentMetadata())
    assert document.stylesheet == ""
    assert document.has_math is False
