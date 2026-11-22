"""A CPU-time doubling check shared by the linearity tests."""

import time
from collections.abc import Callable

from md_studio.core.document import Document
from md_studio.extractors.arxiv_latexml import LatexmlFix

DOUBLINGS = 4
MAX_TOTAL_RATIO = 48.0
FLOOR = 5e-3
RUNS = 5


def _best_cpu_time(document: Document) -> float:
    best = float("inf")
    for _ in range(RUNS):
        started = time.process_time()
        LatexmlFix().apply(document)
        best = min(best, time.process_time() - started)
    return best


def is_linear(times: list[float]) -> bool:
    """Decide whether timings for sizes n, 2n, 4n, 8n, 16n show linear growth.

    The largest page is 16 times the smallest, so linear growth gives a ratio near 16 and
    quadratic growth near 256. The bound of 48 sits between the two and leaves room for
    noise. The smallest timing is floored at 5 ms so a tiny baseline cannot inflate the ratio.
    """
    return times[-1] / max(times[0], FLOOR) < MAX_TOTAL_RATIO


def assert_linear(build: Callable[[int], Document], base: int) -> None:
    """Assert the fix's CPU time grows linearly over four doublings of the page.

    CPU time and the best of five runs keep a loaded machine from tripping it. Choose
    *base* so the smallest page takes about 5 ms or more.
    """
    sizes = [base * 2**step for step in range(DOUBLINGS + 1)]
    times = [_best_cpu_time(build(size)) for size in sizes]

    assert is_linear(times), (sizes, times)
