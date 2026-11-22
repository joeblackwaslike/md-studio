"""Math: equation tables become display math, ``<math>`` becomes an ``md-math`` element.

The extractor turns an ``md-math`` element into ``ir.Math`` (inline) or ``ir.MathBlock``
(``display="block"``). The TeX is the ``alttext`` attribute, never the MathML text, and
passes through unchanged.
"""

from collections.abc import Iterable

from lxml import etree
from lxml import html as lxml_html

from md_studio.core.extract.tags import MATH_TAG, MATH_TEX_ATTR
from md_studio.readers.html import HtmlElement

_ALTTEXT = "alttext"
_ROW_CLASS = "ltx_eqn_row"
_ALIGNED = r"""\begin{{aligned}}
{rows}
\end{{aligned}}"""
_CELL_JOIN = " & "
_ROW_JOIN = r""" \\
"""
_DISPLAY = "display"
_BLOCK = "block"


def equation_block(equation: HtmlElement) -> HtmlElement | None:
    """Return a display-math element for an equation table or group, or ``None`` when empty."""
    tex = equation_tex(equation)
    if not tex:
        return None
    block = lxml_html.Element(MATH_TAG)
    block.set(MATH_TEX_ATTR, tex)
    block.set(_DISPLAY, _BLOCK)
    return block


def equation_tex(equation: HtmlElement) -> str:
    r"""Return the TeX of an equation table or group; several cells or rows become ``aligned``.

    A group's rows are joined with ``\\`` and the cells of a row with ``&``, so the
    columns line up as they did in the paper. Equation numbers are not math and are dropped.
    """
    rows = _rows(equation)
    if len(rows) == 1 and len(rows[0]) == 1:
        return rows[0][0]
    lines = _ROW_JOIN.join(_CELL_JOIN.join(row) for row in rows)
    return _ALIGNED.format(rows=lines) if lines else ""


def _is_row(node: HtmlElement) -> bool:
    classes = node.get("class", "") if isinstance(node.tag, str) else ""
    return _ROW_CLASS in classes.split()


def _is_math(node: HtmlElement) -> bool:
    return node.tag == "math" and bool(node.get(_ALTTEXT))


def _rows(equation: HtmlElement) -> list[list[str]]:
    rows: list[list[str]] = [[]]
    for _, node in etree.iterwalk(equation, events=("start",)):
        if _is_row(node) and rows[-1]:
            rows.append([])
        elif _is_math(node):
            rows[-1].append(node.get(_ALTTEXT, ""))
    return [row for row in rows if row]


def rewrite_math(maths: Iterable[HtmlElement]) -> None:
    """Turn every ``<math>`` into an ``md-math`` element carrying its ``alttext``."""
    for math in maths:
        tex = math.get(_ALTTEXT, "")
        display = math.get(_DISPLAY, "inline")
        tail = math.tail
        math.clear()
        math.tail = tail
        math.tag = MATH_TAG
        math.set(MATH_TEX_ATTR, tex)
        if display == _BLOCK:
            math.set(_DISPLAY, _BLOCK)
