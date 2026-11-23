"""CLI wiring of the arXiv extractor, with a stub transport and no network."""

from collections.abc import Iterator
from dataclasses import replace
from pathlib import Path

import httpx
import pytest
from typer.testing import CliRunner

from md_studio.cli import app, sources
from md_studio.extractors import ExtractionPlan, Extractor
from md_studio.extractors.arxiv import ArxivClient, ArxivExtractor

PAGE = b"<html><head><title>Paper</title></head><body><h1>Paper</h1><p>Body text.</p></body></html>"


class _Raw(httpx.SyncByteStream):
    def __iter__(self) -> Iterator[bytes]:
        yield PAGE


class _Server:
    def __init__(self, status: int = 200, redirect: str | None = None) -> None:
        self.status = status
        self.redirect = redirect
        self.paths: list[str] = []

    def __call__(self, request: httpx.Request) -> httpx.Response:
        self.paths.append(request.url.path)
        if self.redirect is not None:
            return httpx.Response(302, headers={"location": self.redirect})
        return httpx.Response(self.status, stream=_Raw())


class _Fixless:
    def __init__(self, inner: ArxivExtractor, fixes: tuple[str, ...]) -> None:
        self._inner = inner
        self._fixes = fixes

    def matches(self, source: str) -> bool:
        return self._inner.matches(source)

    def resolve(self, source: str) -> ExtractionPlan:
        return replace(self._inner.resolve(source), source_fixes=self._fixes)


def _install(monkeypatch: pytest.MonkeyPatch, server: _Server, fixes: tuple[str, ...] = ()) -> None:
    client = ArxivClient(0, transport=httpx.MockTransport(server))
    extractors: tuple[Extractor, ...] = (_Fixless(ArxivExtractor(client), fixes),)
    monkeypatch.setattr(sources, "build_extractors", lambda: extractors)


def _convert(*args: Path | str):
    return CliRunner().invoke(app, ["convert", *map(str, args)])


def test_cli_converts_an_arxiv_url(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    server = _Server()
    _install(monkeypatch, server)
    dest = tmp_path / "paper.md"

    outcome = _convert("https://arxiv.org/abs/2606.24937v3", "-o", dest)

    assert outcome.exit_code == 0, outcome.output
    assert "Body text." in dest.read_text(encoding="utf-8")
    assert server.paths == ["/html/2606.24937v3"]


def test_cli_names_the_default_output_after_the_paper(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    _install(monkeypatch, _Server())
    monkeypatch.chdir(tmp_path)

    plain = _convert("2606.24937v3")
    old_style = _convert("hep-th/9901001")

    assert plain.exit_code == 0, plain.output
    assert old_style.exit_code == 0, old_style.output
    assert (tmp_path / "arxiv-2606.24937v3.md").exists()
    assert (tmp_path / "arxiv-hep-th_9901001.md").exists()


def test_arxiv_id_option_overrides_detection(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    server = _Server()
    _install(monkeypatch, server)

    outcome = _convert("paper.pdf", "--arxiv-id", "2606.24937", "-o", tmp_path / "p.md")

    assert outcome.exit_code == 0, outcome.output
    assert server.paths == ["/html/2606.24937"]


def test_arxiv_id_option_rejects_a_non_arxiv_id(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    server = _Server()
    _install(monkeypatch, server)

    outcome = _convert("paper.pdf", "--arxiv-id", "https://example.com/x", "-o", tmp_path / "p.md")

    assert outcome.exit_code == 1
    assert "not an arXiv" in outcome.output
    assert server.paths == []


def test_unregistered_source_fix_fails_clearly_before_any_request(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    server = _Server()
    _install(monkeypatch, server, fixes=("no-such-fix",))

    outcome = _convert("2606.24937", "-o", tmp_path / "p.md")

    assert outcome.exit_code == 1
    assert "no-such-fix" in outcome.output
    assert server.paths == []
    assert not (tmp_path / "p.md").exists()


def test_missing_html_exits_with_a_clear_error(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    _install(monkeypatch, _Server(status=404))

    outcome = _convert("2606.24937", "-o", tmp_path / "p.md")

    assert outcome.exit_code == 1
    assert "no HTML or PDF version of 2606.24937" in outcome.output


def test_an_existing_local_file_is_never_claimed_by_an_extractor(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    server = _Server()
    _install(monkeypatch, server)
    monkeypatch.chdir(tmp_path)
    (tmp_path / "2606.24937").write_bytes(b"not an epub")

    outcome = _convert("2606.24937")

    assert outcome.exit_code == 1
    assert "Unsupported source type" in outcome.output
    assert server.paths == []


def test_default_extractors_list_arxiv_first() -> None:
    first = sources.build_extractors()[0]

    assert isinstance(first, ArxivExtractor)


@pytest.mark.parametrize(
    "location",
    ["https://xn--arxiv-.org/html/1", "https://evil.example/html/1?token=abc123", "/e-print/1"],
)
def test_hostile_redirects_exit_with_one_error_line(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, location: str
) -> None:
    server = _Server(redirect=location)
    _install(monkeypatch, server)

    outcome = _convert("2606.24937", "-o", tmp_path / "p.md")

    assert outcome.exit_code == 1
    assert outcome.output.startswith("Error: ")
    assert len(outcome.output.strip().splitlines()) == 1
    assert "abc123" not in outcome.output
    assert server.paths == ["/html/2606.24937"]


FIXTURE = Path(__file__).parents[1] / "fixtures" / "latexml_mini.html"


class _FixtureBytes(httpx.SyncByteStream):
    def __iter__(self) -> Iterator[bytes]:
        yield FIXTURE.read_bytes()


def _serve_fixture(request: httpx.Request) -> httpx.Response:
    return httpx.Response(
        200, stream=_FixtureBytes(), headers={"content-type": "text/html; charset=utf-8"}
    )


def test_cli_converts_a_served_page_with_the_real_extractor(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    client = ArxivClient(0, transport=httpx.MockTransport(_serve_fixture))
    monkeypatch.setattr(sources, "build_extractors", lambda: (ArxivExtractor(client),))
    destination = tmp_path / "paper.md"

    outcome = _convert("2606.24937v3", "-o", destination)

    assert outcome.exit_code == 0, outcome.output
    text = destination.read_text(encoding="utf-8")
    assert "\n## Part I \u00b7 Chapter 1 Basics\n" in text
    assert "\n### 1.1 Softmax\n" in text
    assert "ltx_" not in text
