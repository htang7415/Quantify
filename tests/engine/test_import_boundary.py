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
    "pathlib",
    "shutil",
}
FORBIDDEN_CALLS = {
    ("datetime", "now"),
    ("datetime", "utcnow"),
    ("date", "today"),
    ("Path", "open"),
}


def test_engine_has_no_harness_or_nondeterministic_imports() -> None:
    assert _violations(ENGINE_ROOT) == []


def test_boundary_checker_rejects_clock_and_filesystem_calls(tmp_path: Path) -> None:
    (tmp_path / "invalid.py").write_text(
        "from datetime import datetime\n"
        "from pathlib import Path\n"
        "datetime.now()\n"
        "Path('snapshot.json').open()\n",
        encoding="utf-8",
    )

    violations = _violations(tmp_path)

    assert "invalid.py: pathlib" in violations
    assert "invalid.py: datetime.now" in violations
    assert "invalid.py: Path.open" in violations


def _violations(root: Path) -> list[str]:
    violations: list[str] = []

    for path in root.glob("*.py"):
        if path.name.startswith("._"):
            continue
        tree = ast.parse(path.read_text(encoding="utf-8"), filename=str(path))
        for node in ast.walk(tree):
            if isinstance(node, ast.Import):
                imported = {alias.name.split(".", 1)[0] for alias in node.names}
            elif isinstance(node, ast.ImportFrom):
                imported = {node.module.split(".", 1)[0]} if node.module else set()
            else:
                imported = set()
            forbidden = imported.intersection(FORBIDDEN_ROOT_MODULES)
            if forbidden:
                violations.append(f"{path.name}: {', '.join(sorted(forbidden))}")
            if isinstance(node, ast.Call) and isinstance(node.func, ast.Attribute):
                owner = node.func.value
                owner_name = (
                    owner.id
                    if isinstance(owner, ast.Name)
                    else owner.func.id
                    if isinstance(owner, ast.Call) and isinstance(owner.func, ast.Name)
                    else None
                )
                if owner_name and (owner_name, node.func.attr) in FORBIDDEN_CALLS:
                    violations.append(f"{path.name}: {owner_name}.{node.func.attr}")

    return violations
