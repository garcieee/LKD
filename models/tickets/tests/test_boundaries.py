"""Keeps the layout honest, so the ticketing logic stays in one place.

The rule folders are pure (numbers in, numbers out), and only engine.py reaches storage/.
"""
import ast
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
RULES = ["matching", "ranking", "classification"]
NO_IO = {"sqlite3", "os", "sys", "pathlib", "json", "shutil", "subprocess", "socket", "urllib", "http",
         "requests", "fastapi", "storage", "engine", "resources"}


def imported(path: Path) -> set[str]:
    names: set[str] = set()
    for node in ast.walk(ast.parse(path.read_text())):
        if isinstance(node, ast.Import):
            for alias in node.names:
                names.update(alias.name.split("."))
        elif isinstance(node, ast.ImportFrom):
            if node.module:
                names.update(node.module.split("."))
            names.update(alias.name for alias in node.names)
    return names


def test_rule_folders_do_no_io_and_never_reach_storage_or_engine():
    for folder in RULES:
        for path in (ROOT / folder).glob("*.py"):
            bad = imported(path) & NO_IO
            assert not bad, f"{path.relative_to(ROOT)} imports {sorted(bad)}: rules must stay pure"


def test_storage_knows_nothing_about_the_rules_or_the_engine():
    for path in (ROOT / "storage").glob("*.py"):
        bad = imported(path) & {*RULES, "engine"}
        assert not bad, f"{path.relative_to(ROOT)} imports {sorted(bad)}: storage only stores"
