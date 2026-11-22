"""A polite arxiv.org client: allowlisted paths, a descriptive agent, spaced requests."""

import threading
import time
from collections.abc import Callable
from http import HTTPStatus
from importlib.metadata import PackageNotFoundError, version

import httpx

from md_studio.core.document import Document
from md_studio.core.exceptions import FetchStatusError, ReadError
from md_studio.extractors.arxiv_id import parse_arxiv_id
from md_studio.extractors.arxiv_policy import ForbiddenUrlError, check_url
from md_studio.readers.deadline import extend_active
from md_studio.readers.html import read_html

_HOMEPAGE = "https://github.com/joeblackwaslike/md-studio"
MIN_INTERVAL = 15.0


def user_agent() -> str:
    """Return the descriptive User-Agent, using ``unknown`` when the package has no metadata."""
    try:
        release = version("md-studio")
    except PackageNotFoundError:
        release = "unknown"
    return f"md-studio/{release} (+{_HOMEPAGE})"


class _PoliteTransport(httpx.BaseTransport):
    """Checks every request, stamps the agent, and spaces request starts."""

    def __init__(
        self,
        interval: float,
        given: httpx.BaseTransport | None,
        clock: Callable[[], float],
        sleep: Callable[[float], None],
    ) -> None:
        self._interval = interval
        self._given = given
        self._owned: httpx.BaseTransport | None = None
        self._clock = clock
        self._sleep = sleep
        self._last: float | None = None
        self._lock = threading.Lock()

    def handle_request(self, request: httpx.Request) -> httpx.Response:
        check_url(request.url)
        self._wait()
        request.headers["User-Agent"] = user_agent()
        return self._inner().handle_request(request)

    def close(self) -> None:
        if self._owned is not None:
            self._owned.close()
            self._owned = None

    def _wait(self) -> None:
        with self._lock:
            if self._last is not None:
                remaining = self._last + self._interval - self._clock()
                if remaining > 0:
                    extend_active(remaining)
                    self._sleep(remaining)
            self._last = self._clock()

    def _inner(self) -> httpx.BaseTransport:
        if self._given is not None:
            return self._given
        if self._owned is None:
            self._owned = httpx.HTTPTransport()
        return self._owned


class ArxivClient:
    """Fetches arXiv pages while honouring arXiv's access rules.

    Spacing is kept per client instance (so per process when one client is shared), measured
    from one request start to the next, and the wait is thread-safe within one client only.
    The wait does not count against a fetch's total deadline.

    Parameters
    ----------
    min_interval
        Seconds between the starts of any two requests, redirect hops included.
    transport
        Optional httpx transport, used by tests to avoid the network.
    clock, sleep
        Time sources, replaceable in tests.
    """

    def __init__(
        self,
        min_interval: float = MIN_INTERVAL,
        *,
        transport: httpx.BaseTransport | None = None,
        clock: Callable[[], float] = time.monotonic,
        sleep: Callable[[float], None] = time.sleep,
    ) -> None:
        self.min_interval = min_interval
        self.transport: httpx.BaseTransport = _PoliteTransport(
            min_interval, transport, clock, sleep
        )

    def check_url(self, url: str) -> None:
        """Raise :class:`ForbiddenUrlError` (a ``ValueError``) unless *url* may be fetched."""
        check_url(url)

    def read(self, source: str, /) -> Document:
        """Read the arXiv HTML page at *source* into a :class:`Document`.

        Raises
        ------
        ReadError
            When the page does not exist, a hop leaves the allowed paths, or the fetch fails.
        """
        self._check(source)
        try:
            return read_html(source, transport=self.transport)
        except ForbiddenUrlError as error:
            raise ReadError(str(error)) from None
        except FetchStatusError as error:
            if error.status != HTTPStatus.NOT_FOUND:
                raise
            paper = parse_arxiv_id(source) or "this paper"
            msg = f"arXiv has no HTML version of {paper}; the PDF fallback is not available yet"
            raise ReadError(msg) from None

    def _check(self, source: str) -> None:
        try:
            check_url(source)
        except ForbiddenUrlError as error:
            raise ReadError(str(error)) from None
