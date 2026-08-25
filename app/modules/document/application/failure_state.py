"""描述文档处理或索引失败登记后的真实数据库状态快照。

用于跨进程/跨组件传递条件更新执行结果，辅助 Runtime 决策与日志审计。
"""

from dataclasses import dataclass


@dataclass(frozen=True)
class FailureStateResult:
    """通用失败状态登记结果。

    记录条件更新（CAS）是否真正修改了数据库记录，以及更新前后的文档状态。

    Attributes:
        state_updated: 数据库状态字段是否被实际修改为 failed。
        status_before: 更新前文档所处的原始状态（若未命中更新条件则可能为 None）。
        status_after: 更新后文档的新状态。
    """

    state_updated: bool
    status_before: str | None
    status_after: str | None


@dataclass(frozen=True)
class IndexFailureStateResult:
    """向量索引阶段失败状态登记结果。

    分别记录 Document 实体和其关联的 ChildChunk 实体在失败时的实际更新情况。

    Attributes:
        document_state_updated: Document 记录的状态是否被更新为 failed。
        chunk_state_updated_count: 实际被批量置为 failed 状态的 ChildChunk 数量。
        status_before: 更新前文档所处的原始状态。
        status_after: 更新后文档的新状态。
    """

    document_state_updated: bool
    chunk_state_updated_count: int
    status_before: str | None
    status_after: str | None


# 预定义的无状态变更常量对象，用于快速返回未发生状态改变的情形
NO_FAILURE_STATE_CHANGE = FailureStateResult(
    state_updated=False,
    status_before=None,
    status_after=None,
)

NO_INDEX_FAILURE_STATE_CHANGE = IndexFailureStateResult(
    document_state_updated=False,
    chunk_state_updated_count=0,
    status_before=None,
    status_after=None,
)
