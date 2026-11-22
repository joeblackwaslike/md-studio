"""Tests for the Docling engine boundary: failure translation and missing-extra detection."""

from collections.abc import Callable
from pathlib import Path

import pytest

from md_studio.core.exceptions import ReadError
from md_studio.readers import pdf_engines


def _convert_boom(path: Path, *, formulas: bool) -> str:
    raise RuntimeError("boom")


def _load_boom() -> Callable[..., str]:
    return _convert_boom


class _Missing:
    def __init__(self, name: str) -> None:
        self.name = name

    def __call__(self) -> Callable[..., str]:
        raise ModuleNotFoundError(f"No module named {self.name!r}", name=self.name)


def _pdf(tmp_path: Path) -> Path:
    pdf = tmp_path / "doc.pdf"
    pdf.write_bytes(b"not a pdf")
    return pdf


def test_conversion_failure_becomes_a_read_error(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setattr(pdf_engines, "_load", _load_boom)

    with pytest.raises(ReadError, match=r"Could not convert doc\.pdf: boom") as caught:
        pdf_engines.DoclingEngine().to_html(_pdf(tmp_path), tmp_path)

    assert isinstance(caught.value.__cause__, RuntimeError)


@pytest.mark.parametrize("name", ["docling", "docling_core.types", "pypdfium2"])
def test_missing_pdf_dependency_names_the_extra(
    name: str, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setattr(pdf_engines, "_load", _Missing(name))

    with pytest.raises(ReadError, match=r"md-studio\[pdf\]"):
        pdf_engines.DoclingEngine().to_html(_pdf(tmp_path), tmp_path)


def test_unrelated_missing_module_propagates(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setattr(pdf_engines, "_load", _Missing("other"))

    with pytest.raises(ModuleNotFoundError):
        pdf_engines.DoclingEngine().to_html(_pdf(tmp_path), tmp_path)


def test_garbage_bytes_are_a_read_error(tmp_path: Path) -> None:
    pytest.importorskip("docling")

    with pytest.raises(ReadError, match=r"Could not convert doc\.pdf"):
        pdf_engines.DoclingEngine().to_html(_pdf(tmp_path), tmp_path)
