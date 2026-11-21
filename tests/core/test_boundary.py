"""Core must stay free of CLI, sink, QA, and terminal-UI dependencies."""

import ast
from pathlib import Path

from md_studio import core

FORBIDDEN_PREFIXES = ("md_studio.cli", "md_studio.sinks", "md_studio.qa")
FORBIDDEN_ROOTS = frozenset(("typer", "rich"))


def _imported_modules(tree: ast.AST) -> list[str]:
    modules: list[str] = []
    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            modules.extend(alias.name for alias in node.names)
        elif isinstance(node, ast.ImportFrom) and node.module and not node.level:
            modules.append(node.module)
    return modules


def _is_forbidden(module: str) -> bool:
    return module.split(".")[0] in FORBIDDEN_ROOTS or module.startswith(FORBIDDEN_PREFIXES)


def test_core_imports_nothing_outside_core() -> None:
    core_dir = Path(core.__file__).parent
    offenders = [
        f"{path.relative_to(core_dir)}: {module}"
        for path in core_dir.rglob("*.py")
        for module in _imported_modules(ast.parse(path.read_text("utf-8")))
        if _is_forbidden(module)
    ]
    assert not offenders
