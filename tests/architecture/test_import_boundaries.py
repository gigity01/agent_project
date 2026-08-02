"""使用 AST 防止模块化单体的依赖方向回退。"""

from __future__ import annotations

import ast
import unittest
from pathlib import Path


ROOT_DIR = Path(__file__).resolve().parents[2]
MODULES_DIR = ROOT_DIR / "app" / "modules"


def _imports(path: Path) -> list[str]:
    tree = ast.parse(path.read_text(encoding="utf-8"), filename=str(path))
    names: list[str] = []
    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            names.extend(alias.name for alias in node.names)
        elif isinstance(node, ast.ImportFrom) and node.module:
            names.append(node.module)
    return names


class ImportBoundariesTest(unittest.TestCase):
    def test_module_layer_import_boundaries(self) -> None:
        violations: list[str] = []
        for path in sorted(MODULES_DIR.rglob("*.py")):
            relative = path.relative_to(MODULES_DIR)
            if len(relative.parts) < 3:
                continue

            module_name, layer = relative.parts[:2]
            for imported in _imports(path):
                if layer == "domain":
                    forbidden = (
                        "fastapi",
                        "sqlalchemy",
                        "redis",
                        "openai",
                        "agents",
                        "app.infrastructure",
                    )
                    if imported.startswith(forbidden) or (
                        imported.startswith("app.modules.")
                        and ".infrastructure" in imported
                    ):
                        violations.append(f"{relative}: {imported}")

                if layer == "application":
                    if (
                        imported == "fastapi"
                        or imported.startswith("fastapi.")
                        or imported.startswith(
                            f"app.modules.{module_name}.presentation"
                        )
                        or imported.startswith(
                            f"app.modules.{module_name}.infrastructure"
                        )
                        or imported == "app.config"
                        or imported.startswith("app.config.")
                    ):
                        violations.append(f"{relative}: {imported}")

                if layer == "presentation":
                    if (
                        imported.startswith(("sqlalchemy", "redis", "openai"))
                        or ".infrastructure" in imported
                        or "repository" in imported.lower()
                    ):
                        violations.append(f"{relative}: {imported}")

                if layer == "agent_tools":
                    forbidden = (
                        "fastapi",
                        "sqlalchemy",
                        "redis",
                        "app.bootstrap",
                    )
                    if (
                        imported.startswith(forbidden)
                        or ".infrastructure" in imported
                        or ".presentation" in imported
                        or ".domain" in imported
                        or "repository" in imported.lower()
                        or ".models" in imported
                    ):
                        violations.append(f"{relative}: {imported}")

                prefix = "app.modules."
                if imported.startswith(prefix) and ".infrastructure" in imported:
                    imported_module = imported[len(prefix):].split(".", 1)[0]
                    if imported_module != module_name:
                        violations.append(
                            f"{relative}: cross-module {imported}"
                        )

        self.assertEqual([], violations, "\n".join(violations))

    def test_application_has_no_global_port_configurator(self) -> None:
        violations: list[str] = []
        for path in sorted(MODULES_DIR.glob("*/application/**/*.py")):
            relative = path.relative_to(MODULES_DIR)
            tree = ast.parse(path.read_text(encoding="utf-8"))
            for node in ast.walk(tree):
                if isinstance(
                    node,
                    (ast.FunctionDef, ast.AsyncFunctionDef),
                ) and node.name.startswith("configure_"):
                    violations.append(f"{relative}: {node.name}")
                if isinstance(node, ast.Global):
                    violations.append(
                        f"{relative}: global {', '.join(node.names)}"
                    )

        self.assertEqual([], violations, "\n".join(violations))


if __name__ == "__main__":
    unittest.main()
