"""Wiring tests: every registered command module imports and exposes main()."""

from __future__ import annotations

import importlib

import pytest

from scripts.harness.commands import COMMAND_MODULES

# Registered modules that are shared helpers rather than CLI entry points.
HELPER_MODULES = {"report_snapshot"}


@pytest.mark.parametrize("name", sorted(COMMAND_MODULES))
def test_command_module_imports_and_has_main(name):
    module = importlib.import_module(COMMAND_MODULES[name])
    if name in HELPER_MODULES:
        return
    assert callable(getattr(module, "main", None)), f"{name} must expose main()"


def test_every_cli_module_on_disk_is_registered():
    """Reverse wiring: any command module defining main() must be registered.

    Catches silent registry drift where a new CLI lands under scripts/commands/
    without a COMMAND_MODULES entry. Uses AST instead of imports so helper
    modules with heavy optional dependencies are never imported here.
    """
    import ast
    from pathlib import Path

    def defines_main(node) -> bool:
        if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)):
            return node.name == "main"
        if isinstance(node, ast.Assign):
            return any(isinstance(t, ast.Name) and t.id == "main" for t in node.targets)
        if isinstance(node, ast.AnnAssign):
            return isinstance(node.target, ast.Name) and node.target.id == "main"
        return False

    commands_dir = Path(__file__).resolve().parents[1] / "commands"
    registered = set(COMMAND_MODULES.values())
    missing = []
    for path in sorted(commands_dir.rglob("*.py")):
        if path.name == "__init__.py" or path.name.startswith("test_"):
            continue
        tree = ast.parse(path.read_text(encoding="utf-8"))
        if not any(defines_main(node) for node in tree.body):
            continue
        parts = path.relative_to(commands_dir).with_suffix("").parts
        module = "scripts.commands." + ".".join(parts)
        if module not in registered:
            missing.append(module)
    assert missing == [], f"CLI modules missing from COMMAND_MODULES: {missing}"


def test_harness_layer_does_not_import_command_modules():
    """The harness foundation must never depend on command modules."""
    import ast
    from pathlib import Path

    harness_dir = Path(__file__).resolve().parents[1] / "harness"
    offenders = []
    for path in sorted(harness_dir.glob("*.py")):
        tree = ast.parse(path.read_text(encoding="utf-8"))
        for node in ast.walk(tree):
            if isinstance(node, ast.ImportFrom) and (node.module or "").startswith("scripts.commands"):
                offenders.append(f"{path.name}: from {node.module}")
            if isinstance(node, ast.Import):
                for alias in node.names:
                    if alias.name.startswith("scripts.commands"):
                        offenders.append(f"{path.name}: import {alias.name}")
    assert offenders == [], f"harness must not import scripts.commands: {offenders}"
