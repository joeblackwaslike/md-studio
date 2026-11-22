"""Core must stay free of CLI, sink, QA, extractor, and terminal-UI dependencies."""

import ast
from pathlib import Path

import pytest

from md_studio import core

FORBIDDEN_PACKAGES = frozenset((
    "md_studio.cli",
    "md_studio.sinks",
    "md_studio.qa",
    "md_studio.extractors",
))
FORBIDDEN_ROOTS = frozenset(("typer", "rich"))
CORE_PACKAGE = "md_studio.core"


def _package_of(path: Path, core_dir: Path) -> str:
    """Return the dotted package that contains the module at *path*."""
    return ".".join((CORE_PACKAGE, *path.relative_to(core_dir).parent.parts))


def _absolute_base(node: ast.ImportFrom, package: str) -> str:
    """Resolve the module an ``ImportFrom`` names, making relative imports absolute."""
    if not node.level:
        return node.module or ""
    parts = package.split(".")
    anchor = parts[: len(parts) - node.level + 1]
    tail = [node.module] if node.module else []
    return ".".join([*anchor, *tail])


def _imported_modules(tree: ast.AST, package: str) -> list[str]:
    """List every module a tree imports, including ``from pkg import submodule`` targets."""
    modules: list[str] = []
    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            modules.extend(alias.name for alias in node.names)
        elif isinstance(node, ast.ImportFrom):
            base = _absolute_base(node, package)
            modules.append(base)
            modules.extend(f"{base}.{alias.name}" for alias in node.names)
    return modules


def _is_forbidden(module: str) -> bool:
    """Match a forbidden package or any submodule of it, on dotted boundaries."""
    parts = module.split(".")
    package = ".".join(parts[:2])
    return parts[0] in FORBIDDEN_ROOTS or package in FORBIDDEN_PACKAGES


def _violations(source: str, package: str = "md_studio.core.render") -> list[str]:
    """Return the forbidden modules imported by *source*."""
    return [
        module for module in _imported_modules(ast.parse(source), package) if _is_forbidden(module)
    ]


@pytest.mark.parametrize(
    "source",
    [
        "from md_studio import cli",
        "from md_studio import sinks, ir",
        "from ...sinks import file",
        "from ... import qa",
        "from md_studio.extractors.arxiv_latexml import LatexmlFix",
        "from md_studio import extractors",
        "import md_studio.cli.app",
        "from rich.console import Console",
        "import typer",
    ],
)
def test_boundary_helper_flags_forbidden_imports(source: str) -> None:
    assert _violations(source)


@pytest.mark.parametrize(
    "source",
    [
        "from md_studio.core import ir",
        "from md_studio import client",
        "import md_studio.client",
        "from md_studio.readers import epub",
        "from . import blocks",
        "from .blocks import render",
        "from ..ir import block",
        "import richness",
    ],
)
def test_boundary_helper_accepts_clean_imports(source: str) -> None:
    assert not _violations(source)


def test_core_imports_nothing_outside_core() -> None:
    core_dir = Path(core.__file__).parent
    offenders = [
        f"{path.relative_to(core_dir)}: {module}"
        for path in core_dir.rglob("*.py")
        for module in _imported_modules(
            ast.parse(path.read_text("utf-8")), _package_of(path, core_dir)
        )
        if _is_forbidden(module)
    ]
    assert not offenders
