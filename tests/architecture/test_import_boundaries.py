"""基于 AST 语法树的模块化单体架构导入边界与依赖方向静态检查。

核心架构不变量（遵循 AGENTS.md 分层规范）：
1. 分层依赖方向约束：
   - 固定依赖方向为 Presentation -> Application -> Domain。
   - Infrastructure 实现 Application 声明的 Port 接口，并可依赖 Domain；Bootstrap 负责最终装配。
2. 各层导入边界硬隔离：
   - Domain 层：纯净领域模型，严禁导入 FastAPI、SQLAlchemy、Redis、OpenAI / Agents SDK 或任何 Infrastructure 代码。
   - Application 层：用例与编排，严禁直接依赖 Presentation、本模块或跨模块 Infrastructure、全局 app.config 或 FastAPI。
   - Presentation 层：协议适配与 HTTP Router，只能调用 Application UseCase/Service，严禁直连 Infrastructure、SQLAlchemy、Redis 或 Repository。
   - Agent Tools 层：仅暴露受控只读/操作能力，严禁直连底层数据库模型、Repository 或 Infrastructure。
   - 禁止跨模块 Infrastructure 越权依赖。
3. Application 无全局可变状态：
   - 严禁在 Application 层使用 `global` 关键字或 `configure_*` 全局配置变异器，所有依赖必须通过构造器显式注入。
"""

from __future__ import annotations

import ast
import unittest
from pathlib import Path


ROOT_DIR = Path(__file__).resolve().parents[2]
MODULES_DIR = ROOT_DIR / "app" / "modules"


def _imports(path: Path) -> list[str]:
    """解析指定 Python 源文件的 AST 语法树，提取所有 import 与 import from 模块名。"""
    tree = ast.parse(path.read_text(encoding="utf-8"), filename=str(path))
    names: list[str] = []
    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            names.extend(alias.name for alias in node.names)
        elif isinstance(node, ast.ImportFrom) and node.module:
            names.append(node.module)
    return names


class ImportBoundariesTest(unittest.TestCase):
    """验证 app/modules 目录下各领域模块的分层导入边界与依赖倒置规则。"""

    def test_module_layer_import_boundaries(self) -> None:
        """遍历 app/modules 下所有子模块文件，使用 AST 检查各层导入是否违反架构防腐与单向依赖规则。"""
        violations: list[str] = []
        for path in sorted(MODULES_DIR.rglob("*.py")):
            relative = path.relative_to(MODULES_DIR)
            if len(relative.parts) < 3:
                continue

            module_name, layer = relative.parts[:2]
            for imported in _imports(path):
                # 1. 检查 domain 层：严禁导入外部框架、基础设施及任何基础设施实现
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

                # 2. 检查 application 层：严禁反向依赖 presentation 或本模块 infrastructure，禁止直接依赖 app.config
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

                # 3. 检查 presentation 层：严禁直接导入 infrastructure 实现、ORM 或 Repository
                if layer == "presentation":
                    if (
                        imported.startswith(("sqlalchemy", "redis", "openai"))
                        or ".infrastructure" in imported
                        or "repository" in imported.lower()
                    ):
                        violations.append(f"{relative}: {imported}")

                # 4. 检查 agent_tools 层：严禁依赖底层 infrastructure、presentation、domain 内部模型或 repository
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

                # 5. 跨模块基础设施检查：严禁跨模块直接导入其他模块的 .infrastructure 私有实现
                prefix = "app.modules."
                if imported.startswith(prefix) and ".infrastructure" in imported:
                    imported_module = imported[len(prefix):].split(".", 1)[0]
                    if imported_module != module_name:
                        violations.append(
                            f"{relative}: cross-module {imported}"
                        )

        self.assertEqual([], violations, "\n".join(violations))

    def test_application_has_no_global_port_configurator(self) -> None:
        """检查 application 层禁止包含 configure_* 全局配置器或 global 全局变量，防止单例可变状态污染。"""
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
