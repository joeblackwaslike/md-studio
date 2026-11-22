"""Follow HTTP redirects by hand so intermediate bodies are never read."""

from collections.abc import Iterator
from contextlib import closing, contextmanager

import httpx

from md_studio.core.exceptions import ReadError
from md_studio.readers.deadline import Deadline
from md_studio.readers.urls import display_url

MAX_REDIRECTS = 3
_SCHEMES = ("http", "https")


def _send(client: httpx.Client, url: str, deadline: Deadline) -> httpx.Response:
    """Open *url* with only the remaining time budget; the body stays unread."""
    deadline.check()
    request = client.build_request("GET", url, timeout=httpx.Timeout(deadline.remaining()))
    response = client.send(request, stream=True)
    try:
        deadline.check()
    except ReadError:
        response.close()
        raise
    return response


def _redirect_target(response: httpx.Response) -> str | None:
    """Return the validated absolute redirect target of *response*, if it redirects."""
    location = response.headers.get("location")
    if not response.is_redirect or location is None:
        return None
    target = response.url.join(location)
    if target.scheme not in _SCHEMES:
        raise ReadError(f"Unsupported redirect scheme to {display_url(str(target))}")
    return str(target)


@contextmanager
def open_final(
    url: str,
    transport: httpx.BaseTransport | None,
    deadline: Deadline,
) -> Iterator[httpx.Response]:
    """Yield the final, unread response for *url* after at most ``MAX_REDIRECTS`` hops.

    Raises
    ------
    ReadError
        On a redirect to a non-http(s) scheme, too many hops, or an expired deadline.
    """
    current = url
    with httpx.Client(follow_redirects=False, transport=transport) as client:
        for _ in range(MAX_REDIRECTS + 1):
            response = _send(client, current, deadline)
            target = _redirect_target(response)
            if target is None:
                with closing(response):
                    yield response
                return
            response.close()
            current = target
    raise ReadError(f"Too many redirects (limit {MAX_REDIRECTS})")
