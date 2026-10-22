"""The command modules: each one is its arguments and main(), and shares what it shares through chessllm.cli.common,
never by importing another command or the app's __main__."""

import ast
import tomllib
from pathlib import Path

ROOT = Path(__file__).parents[2]


def command_modules() -> list[str]:
    scripts = tomllib.loads((ROOT / "pyproject.toml").read_text(encoding="utf-8"))["project"]["scripts"]
    return sorted({entry.partition(":")[0] for entry in scripts.values()})


def imported_modules(module: str) -> set[str]:
    tree = ast.parse((ROOT / Path(*module.split("."))).with_suffix(".py").read_text(encoding="utf-8"))
    imported = set()
    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            imported.update(alias.name for alias in node.names)
        elif isinstance(node, ast.ImportFrom) and node.module is not None:
            imported.add(node.module)
            imported.update(f"{node.module}.{alias.name}" for alias in node.names)
    return imported


def test_no_command_module_imports_another_command_module_or_the_apps_main():
    commands = command_modules()
    assert "chessllm.cli.anchor_match" in commands and "chessllm.__main__" in commands

    for command in commands:
        others = set(commands) - {command}
        assert not imported_modules(command) & others, command
