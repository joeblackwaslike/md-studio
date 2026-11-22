"""The decision function of the shared linearity check, on fixed timings."""

import pytest

from tests.extractors.linear import is_linear


@pytest.mark.parametrize(
    "times",
    [
        [1, 2, 4, 8, 16],
        [1, 2.2, 4.5, 9, 18],
        [0.001, 0.002, 0.004, 0.008, 0.2],
    ],
)
def test_linear_series_pass(times: list[float]) -> None:
    assert is_linear(times)


@pytest.mark.parametrize(
    "times",
    [
        [1, 4, 16, 64, 256],
        [1, 3, 9, 27, 81],
        [0.001, 0.004, 0.016, 0.064, 0.256],
    ],
)
def test_quadratic_and_worse_series_fail(times: list[float]) -> None:
    assert not is_linear(times)
