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
type _Rows = tuple[list[list[str]], int]
type _Equation = tuple[HtmlElement | None, int]
_DISPLAY = "display"
_BLOCK = "block"


def source_of(math: HtmlElement) -> tuple[str, bool]:
    """Return a ``<math>``'s TeX (its ``alttext``) and whether that had to be a fallback.

    Without ``alttext`` the TeX is the MathML text content, normalised, which may be empty.
    """
    tex = math.get(_ALTTEXT)
    if tex:
        return tex, False
    return " ".join("".join(math.itertext()).split()), True


def equation_block(equation: HtmlElement) -> _Equation:
    """Return a display-math element for an equation table or group, and its missing-TeX count.

    The element is ``None`` when the equation holds no text at all.
    """
    tex, missing = equation_tex(equation)
    if not tex:
        return None, missing
    block = lxml_html.Element(MATH_TAG)
    block.set(MATH_TEX_ATTR, tex)
    block.set(_DISPLAY, _BLOCK)
    return block, missing


def equation_tex(equation: HtmlElement) -> tuple[str, int]:
    r"""Return the TeX of an equation table or group, and how many of its math lacked ``alttext``.

    Several cells or rows become ``aligned``: a group's rows are joined with ``\\`` and the
    cells of a row with ``&``, so the columns line up as they did in the paper. Equation
    numbers are not math and are dropped.
    """
    rows, missing = _rows(equation)
    if len(rows) == 1 and len(rows[0]) == 1:
        return rows[0][0], missing
    lines = _ROW_JOIN.join(_CELL_JOIN.join(row) for row in rows)
    return (_ALIGNED.format(rows=lines) if lines else ""), missing


def _is_row(node: HtmlElement) -> bool:
    classes = node.get("class", "") if isinstance(node.tag, str) else ""
    return _ROW_CLASS in classes.split()


def _rows(equation: HtmlElement) -> _Rows:
    rows: list[list[str]] = [[]]
    missing = 0
    for _, node in etree.iterwalk(equation, events=("start",)):
        if _is_row(node) and rows[-1]:
            rows.append([])
        elif node.tag == "math":
            tex, fallback = source_of(node)
            missing += fallback
            if tex:
                rows[-1].append(tex)
    return [row for row in rows if row], missing


def rewrite_math(maths: Iterable[HtmlElement]) -> int:
    """Turn every ``<math>`` into an ``md-math`` element and return how many lacked ``alttext``.

    A ``<math>`` with no TeX and no text at all is removed (its tail stays); it is counted.
    """
    missing = 0
    for math in maths:
        tex, fallback = source_of(math)
        missing += fallback
        if tex:
            _convert(math, tex)
        else:
            math.drop_tree()
    return missing


def _convert(math: HtmlElement, tex: str) -> None:
    display = math.get(_DISPLAY, "inline")
    tail = math.tail
    math.clear()
    math.tail = tail
    math.tag = MATH_TAG
    math.set(MATH_TEX_ATTR, tex)
    if display == _BLOCK:
        math.set(_DISPLAY, _BLOCK)
