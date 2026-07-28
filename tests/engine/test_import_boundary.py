from __future__ import annotations

import ast
from pathlib import Path


ENGINE_ROOT = Path(__file__).parents[2] / "quantify" / "engine"
FORBIDDEN_ROOT_MODULES = {
    "anthropic",
    "httpx",
    "openai",
    "os",
    "random",
    "requests",
}


def test_engine_has_no_harness_or_nondeterministic_imports() -> None:
    violations: list[str] = []

    for path in ENGINE_ROOT.glob("*.py"):
        if path.name.startswith("._"):
            continue
        tree = ast.parse(path.read_text(encoding="utf-8"), filename=str(path))
        for node in ast.walk(tree):
            if isinstance(node, ast.Import):
                imported = {alias.name.split(".", 1)[0] for alias in node.names}
            elif isinstance(node, ast.ImportFrom):
                imported = {node.module.split(".", 1)[0]} if node.module else set()
            else:
                continue
            forbidden = imported.intersection(FORBIDDEN_ROOT_MODULES)
            if forbidden:
                violations.append(f"{path.name}: {', '.join(sorted(forbidden))}")

    assert violations == []
