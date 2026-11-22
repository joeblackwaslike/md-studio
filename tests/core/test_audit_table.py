"""Audit rows split into the same cells under every GFM table escape rule."""

import re

import pytest

from md_studio.core.extensions import audit

_HOSTILE = (
    r"x\|[click](https://evil.example)",
    r"\|<img src=x onerror=alert(1)>",
    r"lead\|<img src=\"https://attacker.example/pixel\">",
    r"a\\|b",
    "trailing backslash\\",
    "".join(("\\" * 9, "|", "\\" * 4, "|")),
    "`ticks` and |pipes| and `|`",
    "||||",
    "plain",
)
_CELLS_PER_ROW = 5
_ESCAPED_PIPE = re.compile(r"(?<!\\)\|")


def _split_naive(row: str) -> list[str]:
    inner = row.strip()[1:-1]
    return [cell.strip() for cell in _ESCAPED_PIPE.split(inner)]


def _split_by_backslash_parity(row: str) -> list[str]:
    inner = row.strip()[1:-1]
    cells: list[str] = []
    current: list[str] = []
    backslashes = 0
    for char in inner:
        if char == "|" and backslashes % 2 == 0:
            cells.append("".join(current).strip())
            current = []
        else:
            current.append(char)
        backslashes = backslashes + 1 if char == "\\" else 0
    cells.append("".join(current).strip())
    return cells


def _row(text: str) -> str:
    record = audit.PromotionRecord("Chapter", text, "div", ("class-a",), 1)
    return audit.render([record]).splitlines()[-1]


@pytest.mark.parametrize("text", _HOSTILE)
@pytest.mark.parametrize("splitter", [_split_naive, _split_by_backslash_parity])
def test_every_row_splits_into_the_expected_cells(text: str, splitter) -> None:
    row = _row(text)

    cells = splitter(row)

    assert len(cells) == _CELLS_PER_ROW
    assert cells[4] == "1"


@pytest.mark.parametrize("text", _HOSTILE)
@pytest.mark.parametrize("splitter", [_split_naive, _split_by_backslash_parity])
def test_no_text_escapes_its_code_span(text: str, splitter) -> None:
    row = _row(text)

    for cell in splitter(row)[:4]:
        assert cell == "" or (cell.startswith("`") and cell.endswith("`") and cell.count("`") == 2)


def test_the_only_backslashes_in_a_cell_are_the_pipe_escapes() -> None:
    row = _row(r"a\\|b\\")

    assert re.findall(r"\\+", row) == ["\\"]
