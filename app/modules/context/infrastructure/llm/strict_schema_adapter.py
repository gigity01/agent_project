"""DeepSeek strict Tool JSON Schema 兼容转换。"""

from __future__ import annotations

from copy import deepcopy
from typing import Any

from app.modules.context.domain.models import ContextRouteDecision


class ContextAgentOutputError(RuntimeError):
    """DeepSeek 未按约定提交唯一且合法的 Context 路由结果。"""


def resolve_local_schema_refs(
    value: Any,
    definitions: dict[str, Any],
) -> Any:
    """展开 Pydantic 生成的本地 ``$defs`` 引用。"""
    if isinstance(value, list):
        return [
            resolve_local_schema_refs(item, definitions)
            for item in value
        ]
    if not isinstance(value, dict):
        return value

    reference = value.get("$ref")
    if isinstance(reference, str) and reference.startswith("#/$defs/"):
        definition_name = reference.removeprefix("#/$defs/")
        definition = definitions.get(definition_name)
        if definition is None:
            raise ContextAgentOutputError(
                f"Context 路由 Schema 引用了未知定义: {definition_name}"
            )
        merged = deepcopy(definition)
        merged.update(
            {
                key: item
                for key, item in value.items()
                if key != "$ref"
            }
        )
        return resolve_local_schema_refs(merged, definitions)

    return {
        key: resolve_local_schema_refs(item, definitions)
        for key, item in value.items()
        if key != "$defs"
    }


def normalize_strict_tool_schema(value: Any) -> Any:
    """转换为 DeepSeek strict tool 当前支持的 JSON Schema 子集。"""
    if isinstance(value, list):
        return [normalize_strict_tool_schema(item) for item in value]
    if not isinstance(value, dict):
        return value

    unsupported_or_display_only = {
        "title",
        "default",
        "minLength",
        "maxLength",
        "minItems",
        "maxItems",
    }
    normalized = {
        key: normalize_strict_tool_schema(item)
        for key, item in value.items()
        if key not in unsupported_or_display_only
    }
    if normalized.get("type") == "object":
        properties = normalized.get("properties", {})
        if isinstance(properties, dict):
            normalized["required"] = list(properties)
        normalized["additionalProperties"] = False
    return normalized


def build_context_route_tool_schema() -> dict[str, Any]:
    """从 Pydantic 契约生成 DeepSeek strict tool 参数 Schema。"""
    raw_schema = ContextRouteDecision.model_json_schema()
    definitions = raw_schema.get("$defs", {})
    resolved = resolve_local_schema_refs(raw_schema, definitions)
    normalized = normalize_strict_tool_schema(resolved)
    if not isinstance(normalized, dict):
        raise ContextAgentOutputError("Context 路由 Schema 不是 JSON 对象")
    return normalized
