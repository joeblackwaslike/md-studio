"""A CPU-time doubling check shared by the linearity tests."""

import time
from collections.abc import Callable
from itertools import pairwise

from md_studio.core.document import Document
from md_studio.extractors.arxiv_latexml import LatexmlFix

DOUBLINGS = 4
MAX_RATIO = 6.0
FLOOR = 1e-3
RUNS = 5


def _best_cpu_time(document: Document) -> float:
    best = float("inf")
    for _ in range(RUNS):
        started = time.process_time()
        LatexmlFix().apply(document)
        best = min(best, time.process_time() - started)
    return best


def assert_linear(build: Callable[[int], Document], base: int) -> None:
    """Assert the fix's CPU time grows by under 6x per doubling of the page, four times over.

    Linear growth gives about 2x per doubling and quadratic about 4x, so the bound leaves
    room for noise. CPU time (not wall clock) and the best of five runs keep a loaded
    machine from tripping it.
    """
    sizes = [base * 2**step for step in range(DOUBLINGS + 1)]
    times = [_best_cpu_time(build(size)) for size in sizes]
    ratios = [later / max(earlier, FLOOR) for earlier, later in pairwise(times)]

    assert max(ratios) < MAX_RATIO, (sizes, times)
