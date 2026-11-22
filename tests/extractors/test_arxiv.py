"""Tests for arXiv id parsing, the polite client, and the extractor."""

import threading
from collections.abc import Iterator
from importlib.metadata import PackageNotFoundError

import httpx
import pytest

from md_studio.core.exceptions import ReadError
from md_studio.extractors import ExtractionPlan, arxiv_client, resolve_extractor
from md_studio.extractors.arxiv import ArxivClient, ArxivExtractor, parse_arxiv_id

PAGE = "<html><head><title>Paper</title></head><body><p>text</p></body></html>"


class _Raw(httpx.SyncByteStream):
    def __init__(self, body: bytes) -> None:
        self._body = body

    def __iter__(self) -> Iterator[bytes]:
        yield self._body


def _page(status: int = 200) -> httpx.Response:
    return httpx.Response(status, stream=_Raw(PAGE.encode()))


class _Time:
    def __init__(self) -> None:
        self.now = 1000.0
        self.sleeps: list[float] = []

    def clock(self) -> float:
        return self.now

    def sleep(self, seconds: float) -> None:
        self.sleeps.append(seconds)
        self.now += seconds


class _Server:
    def __init__(
        self,
        time: _Time,
        *,
        takes: float = 0,
        status: int = 200,
        redirects: dict[str, str] | None = None,
    ) -> None:
        self.time = time
        self.takes = takes
        self.status = status
        self.redirects = redirects or {}
        self.requests: list[httpx.Request] = []
        self.starts: list[float] = []

    def __call__(self, request: httpx.Request) -> httpx.Response:
        self.requests.append(request)
        self.starts.append(self.time.now)
        self.time.now += self.takes
        location = self.redirects.get(request.url.path)
        if location is not None:
            return httpx.Response(302, headers={"location": location})
        return _page(self.status)

    @property
    def paths(self) -> list[str]:
        return [request.url.path for request in self.requests]


def _client(time: _Time, server: _Server, interval: float = 15.0) -> ArxivClient:
    return ArxivClient(
        interval,
        transport=httpx.MockTransport(server),
        clock=time.clock,
        sleep=time.sleep,
    )


def _refusal(client: ArxivClient, url: str) -> ValueError:
    try:
        client.check_url(url)
    except ValueError as error:
        return error
    raise AssertionError(f"{url} was not refused")


@pytest.mark.parametrize(
    ("source", "expected"),
    [
        ("2606.24937", "2606.24937"),
        ("2606.24937v3", "2606.24937v3"),
        ("0704.0001", "0704.0001"),
        ("hep-th/9901001", "hep-th/9901001"),
        ("math.GT/0309136v2", "math.GT/0309136v2"),
        ("https://arxiv.org/abs/2606.24937", "2606.24937"),
        ("https://arxiv.org/abs/2606.24937v3", "2606.24937v3"),
        ("http://arxiv.org/abs/2606.24937v3", "2606.24937v3"),
        ("https://www.arxiv.org/pdf/2606.24937v3", "2606.24937v3"),
        ("https://arxiv.org/pdf/2606.24937v3.pdf", "2606.24937v3"),
        ("https://arxiv.org/pdf/2606.24937.pdf", "2606.24937"),
        ("https://arxiv.org/html/2606.24937v3", "2606.24937v3"),
        ("https://arxiv.org/html/2606.24937v3/", "2606.24937v3"),
        ("https://arxiv.org/abs/hep-th/9901001", "hep-th/9901001"),
        ("https://arxiv.org/pdf/hep-th/9901001v1.pdf", "hep-th/9901001v1"),
        ("https://arxiv.org/abs/2606.24937?context=cs", "2606.24937"),
        ("https://arxiv.org/abs/2606.24937#section", "2606.24937"),
    ],
)
def test_parse_arxiv_id_forms(source: str, expected: str) -> None:
    assert parse_arxiv_id(source) == expected


@pytest.mark.parametrize(
    "source",
    [
        "",
        "paper.pdf",
        "/home/me/2606.24937.pdf",
        "26o6.24937",
        "2606.249",
        "2606.249371",
        "2606.24937v",
        "2606.24937v3x",
        " 2606.24937",
        "2606.24937\n",
        "https://arxiv.org/abs/2606.24937\n",
        " https://arxiv.org/abs/2606.24937",
        "https://arxiv.org/abs/2606.24937 ",
        "https://arxiv.org/abs/2606.\t24937",
        "https://arxiv.org/abs/2606.24937\x00",
        "\x1bhttps://arxiv.org/abs/2606.24937",
        "x2606.24937",
        "../2606.24937",
        "hep-th/990100",
        "hep-th/../9901001",
        "https://example.com/abs/2606.24937",
        "https://arxiv.org.evil.com/abs/2606.24937",
        "https://evilarxiv.org/abs/2606.24937",
        "https://user:pw@arxiv.org/abs/2606.24937",
        "https://arxiv.org:8443/abs/2606.24937",
        "ftp://arxiv.org/abs/2606.24937",
        "https://arxiv.org/e-print/2606.24937",
        "https://arxiv.org/src/2606.24937",
        "https://arxiv.org/abs/2606.24937/extra",
        "https://arxiv.org/abs/../e-print/2606.24937",
        "https://arxiv.org/html/2606.24937.pdf",
        "https://arxiv.org/abs/2606.24937.pdf",
        "https://arxiv.org/list/cs.AI/recent",
        "https://arxiv.org/",
    ],
)
def test_parse_arxiv_id_rejects_everything_else(source: str) -> None:
    assert parse_arxiv_id(source) is None


@pytest.mark.parametrize(
    "url",
    [
        "https://arxiv.org/e-print/2606.24937",
        "https://arxiv.org/src/2606.24937",
        "https://arxiv.org/list/cs.AI/recent",
        "https://arxiv.org/",
        "https://arxiv.org/html",
        "https://arxiv.org/abs/",
        "https://arxiv.org/abs/2606.24937?x=/e-print",
        "https://arxiv.org/html/%2e%2e/e-print/2606.24937",
        "https://arxiv.org/html/../e-print/2606.24937",
        "https://arxiv.org/html//e-print/2606.24937",
        "https://example.com/html/2606.24937",
        "https://export.arxiv.org/abs/2606.24937",
        "https://arxiv.org.evil.com/html/2606.24937",
        "http://arxiv.org/html/2606.24937",
        "https://arxiv.org:8443/html/2606.24937",
        "https://user:pw@arxiv.org/html/2606.24937",
        "not a url",
    ],
)
def test_forbidden_urls_rejected(url: str) -> None:
    time = _Time()
    client = _client(time, _Server(time))

    assert "not allowed" in str(_refusal(client, url))


@pytest.mark.parametrize(
    "url",
    [
        "https://arxiv.org/html/2606.24937v3",
        "https://arxiv.org/abs/2606.24937",
        "https://arxiv.org/pdf/2606.24937v3.pdf",
        "https://arxiv.org/html/hep-th/9901001",
        "https://arxiv.org:443/abs/2606.24937",
    ],
)
def test_allowed_urls_pass(url: str) -> None:
    time = _Time()
    _client(time, _Server(time)).check_url(url)


def test_forbidden_url_message_hides_query_and_userinfo() -> None:
    time = _Time()
    client = _client(time, _Server(time))

    error = _refusal(client, "https://user:hunter2@arxiv.org/e-print/1?token=abc123")

    text = f"{error!r} {error.__cause__!r} {error.__context__!r}"
    assert "hunter2" not in text
    assert "abc123" not in text
    assert "user" not in text


def test_redirect_to_forbidden_path_is_refused_and_never_followed() -> None:
    time = _Time()
    server = _Server(time, redirects={"/html/2606.24937": "/e-print/2606.24937?token=abc123"})

    with pytest.raises(ReadError) as caught:
        _client(time, server).read("https://arxiv.org/html/2606.24937")

    assert server.paths == ["/html/2606.24937"]
    assert "abc123" not in repr(caught.value)
    assert "abc123" not in repr(caught.value.__context__)
    assert caught.value.__cause__ is None


@pytest.mark.parametrize(
    "location",
    [
        "https://evil.example/html/2606.24937?token=abc123",
        "https://arxiv.org.evil.example/html/2606.24937",
        "http://arxiv.org/html/2606.24937",
    ],
)
def test_redirect_to_other_host_or_scheme_is_refused(location: str) -> None:
    time = _Time()
    server = _Server(time, redirects={"/html/2606.24937": location})

    with pytest.raises(ReadError, match="not allowed") as caught:
        _client(time, server).read("https://arxiv.org/html/2606.24937")

    assert [request.url.host for request in server.requests] == ["arxiv.org"]
    assert "abc123" not in str(caught.value)


def test_redirect_within_allowed_paths_is_followed_and_spaced() -> None:
    time = _Time()
    server = _Server(time, redirects={"/html/2606.24937": "/html/2606.24937v3"})

    document = _client(time, server).read("https://arxiv.org/html/2606.24937")

    assert document.metadata.title == "Paper"
    assert server.paths == ["/html/2606.24937", "/html/2606.24937v3"]
    assert server.starts[1] - server.starts[0] == pytest.approx(15)


def test_requests_spaced_by_min_interval_between_starts() -> None:
    time = _Time()
    server = _Server(time, takes=4)
    client = _client(time, server)

    client.read("https://arxiv.org/html/2606.24937")
    client.read("https://arxiv.org/html/2606.24938")

    assert time.sleeps == [11.0]
    assert server.starts[1] - server.starts[0] == pytest.approx(15)


def test_first_request_does_not_wait() -> None:
    time = _Time()
    server = _Server(time)

    _client(time, server).read("https://arxiv.org/html/2606.24937")

    assert not time.sleeps
    assert len(server.requests) == 1


def test_no_wait_when_interval_already_elapsed() -> None:
    time = _Time()
    server = _Server(time)
    client = _client(time, server)

    client.read("https://arxiv.org/html/2606.24937")
    time.now += 40
    client.read("https://arxiv.org/html/2606.24938")

    assert not time.sleeps


def test_refused_redirect_hop_neither_sleeps_nor_consumes_the_interval() -> None:
    time = _Time()
    server = _Server(time, redirects={"/html/1": "/e-print/1"})
    client = _client(time, server)

    with pytest.raises(ReadError, match="not allowed"):
        client.read("https://arxiv.org/html/1")

    assert not time.sleeps
    assert server.paths == ["/html/1"]
    client.read("https://arxiv.org/html/2")
    assert time.sleeps == [15.0]


def test_idn_redirect_is_refused_as_a_read_error() -> None:
    time = _Time()
    server = _Server(time, redirects={"/html/1": "https://xn--arxiv-.org/html/1"})

    with pytest.raises(ReadError, match="Invalid redirect") as caught:
        _client(time, server).read("https://arxiv.org/html/1")

    assert caught.value.__cause__ is None


def test_check_url_refuses_a_bad_idn_host() -> None:
    time = _Time()

    assert "not allowed" in str(_refusal(_client(time, _Server(time)), "https://xn--arxiv-.org/x"))


@pytest.mark.parametrize("source", ["page.html", "/etc/passwd", "../x.html", "file:///etc/passwd"])
def test_read_refuses_anything_that_is_not_an_allowed_arxiv_url(source: str) -> None:
    time = _Time()
    server = _Server(time)

    with pytest.raises(ReadError, match="not allowed"):
        _client(time, server).read(source)

    assert not server.requests


def _chain(time: _Time, hops: int, *, takes: float = 0) -> _Server:
    redirects = {f"/html/{index}": f"/html/{index + 1}" for index in range(hops)}
    return _Server(time, takes=takes, redirects=redirects)


def test_politeness_waits_do_not_count_against_the_fetch_deadline(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    time = _Time()
    monkeypatch.setattr("md_studio.readers.deadline._clock", time.clock)
    server = _chain(time, 3)

    document = _client(time, server).read("https://arxiv.org/html/0")

    assert document.metadata.title == "Paper"
    assert time.sleeps == [15.0, 15.0, 15.0]
    assert len(server.requests) == 4


def test_slow_network_time_still_hits_the_deadline(monkeypatch: pytest.MonkeyPatch) -> None:
    time = _Time()
    monkeypatch.setattr("md_studio.readers.deadline._clock", time.clock)
    server = _chain(time, 3, takes=12)

    with pytest.raises(ReadError, match="deadline"):
        _client(time, server).read("https://arxiv.org/html/0")

    assert time.sleeps == [3.0, 3.0]


def test_user_agent_is_descriptive_and_has_no_personal_data() -> None:
    time = _Time()
    server = _Server(time)

    _client(time, server).read("https://arxiv.org/html/2606.24937")

    agent = server.requests[0].headers["user-agent"]
    assert agent.startswith("md-studio/")
    assert agent.endswith("(+https://github.com/joeblackwaslike/md-studio)")
    assert "@" not in agent


def test_default_interval_is_fifteen_seconds() -> None:
    assert ArxivClient().min_interval == pytest.approx(15)


def test_matches_only_arxiv_sources() -> None:
    extractor = ArxivExtractor()

    assert extractor.matches("https://arxiv.org/abs/2606.24937v3")
    assert extractor.matches("hep-th/9901001")
    assert not extractor.matches("https://example.com/book.html")
    assert not extractor.matches("book.epub")


def test_resolve_plans_the_html_page_without_any_request() -> None:
    time = _Time()
    server = _Server(time)
    extractor = ArxivExtractor(_client(time, server, 0))

    plan = extractor.resolve("https://arxiv.org/pdf/2606.24937v3.pdf")

    assert isinstance(plan, ExtractionPlan)
    assert plan.source == "https://arxiv.org/html/2606.24937v3"
    assert plan.source_fixes == ("arxiv-latexml",)
    assert plan.metadata_overrides == {"arxiv_id": "2606.24937v3"}
    assert not server.requests


def test_resolve_rejects_a_non_arxiv_source() -> None:
    with pytest.raises(ReadError, match="not an arXiv"):
        ArxivExtractor().resolve("https://example.com/x")


def test_plan_reader_reads_through_the_client_transport() -> None:
    time = _Time()
    server = _Server(time)
    extractor = ArxivExtractor(_client(time, server))

    plan = resolve_extractor("2606.24937v3", [extractor])
    assert plan is not None
    document = plan.reader(plan.source)

    assert document.metadata.title == "Paper"
    assert [str(request.url) for request in server.requests] == [
        "https://arxiv.org/html/2606.24937v3"
    ]


def test_missing_html_is_a_clear_read_error() -> None:
    time = _Time()
    extractor = ArxivExtractor(_client(time, _Server(time, status=404)))
    plan = extractor.resolve("2606.24937")

    with pytest.raises(ReadError, match=r"no HTML version of 2606\.24937"):
        plan.reader(plan.source)


def test_other_http_errors_keep_their_status() -> None:
    time = _Time()
    extractor = ArxivExtractor(_client(time, _Server(time, status=503)))
    plan = extractor.resolve("2606.24937")

    with pytest.raises(ReadError, match="HTTP 503"):
        plan.reader(plan.source)


def test_wait_extends_the_deadline_before_sleeping(monkeypatch: pytest.MonkeyPatch) -> None:
    time = _Time()
    order: list[str] = []
    monkeypatch.setattr(arxiv_client, "extend_active", lambda seconds: order.append("extend"))
    client = ArxivClient(
        15,
        transport=httpx.MockTransport(_Server(time)),
        clock=time.clock,
        sleep=lambda seconds: order.append("sleep"),
    )

    client.read("https://arxiv.org/html/1")
    client.read("https://arxiv.org/html/2")

    assert order == ["extend", "sleep"]


def _no_metadata(name: str) -> str:
    raise PackageNotFoundError(name)


def _broken_reader(source: str, *, transport: httpx.BaseTransport) -> None:
    raise ValueError("boom")


def test_user_agent_falls_back_when_the_package_metadata_is_missing(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(arxiv_client, "version", _no_metadata)

    assert arxiv_client.user_agent().startswith("md-studio/unknown (+https://github.com/")


def test_a_value_error_from_the_reader_is_not_reported_as_a_malformed_url(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(arxiv_client, "read_html", _broken_reader)
    time = _Time()

    with pytest.raises(ValueError, match="boom") as caught:
        _client(time, _Server(time)).read("https://arxiv.org/html/1")

    assert not isinstance(caught.value, ReadError)


def test_a_malformed_url_is_a_read_error() -> None:
    time = _Time()

    with pytest.raises(ReadError):
        _client(time, _Server(time)).read("https://[x/html/1")


class _Gated:
    def __init__(self) -> None:
        self.time = _Time()
        self.entered = threading.Event()
        self.release = threading.Event()
        self.guard = threading.Lock()
        self.inflight = 0
        self.peak = 0

    def __call__(self, request: httpx.Request) -> httpx.Response:
        with self.guard:
            first = not self.entered.is_set()
            self.inflight += 1
            self.peak = max(self.peak, self.inflight)
        if first:
            self.entered.set()
            self.release.wait(5)
        self.time.now += 25
        with self.guard:
            self.inflight -= 1
        return _page()


def _gated_client(gated: _Gated) -> ArxivClient:
    return ArxivClient(
        0, transport=httpx.MockTransport(gated), clock=gated.time.clock, sleep=gated.time.sleep
    )


def _read_title(client: ArxivClient, url: str, titles: list[str]) -> None:
    titles.append(client.read(url).metadata.title)


def test_reads_are_serialized_and_queueing_never_counts_against_a_deadline(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    gated = _Gated()
    monkeypatch.setattr("md_studio.readers.deadline._clock", gated.time.clock)
    client = _gated_client(gated)
    titles: list[str] = []
    first = threading.Thread(target=_read_title, args=(client, "https://arxiv.org/html/1", titles))
    second = threading.Thread(target=_read_title, args=(client, "https://arxiv.org/html/2", titles))

    first.start()
    assert gated.entered.wait(5)
    second.start()
    threading.Event().wait(0.05)
    gated.release.set()
    first.join(5)
    second.join(5)

    assert titles == ["Paper", "Paper"]
    assert gated.peak == 1
