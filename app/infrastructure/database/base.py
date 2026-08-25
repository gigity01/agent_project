"""SQLAlchemy ORM 声明式模型基类定义模块。

职责说明：
- 导出全局唯一的 `Base` Declarative Base 对象，供各业务模块的所有 ORM 模型继承。
- 确保所有模型的表定义挂载在同一个 `Base.metadata` 命名空间中，便于统一迁移与建表。
"""

from sqlalchemy.ext.declarative import declarative_base

# 全局 SQLAlchemy ORM 模型声明式基类
Base = declarative_base()
