"""Context 完成 HTTP 接口（Complete Turn）请求体映射与 Attribution 契约测试。

核心业务不变量：
1. 请求参数到领域 Command 映射：
   - 将 CompleteContextTurnRequest 中的显式 attribution（已有链 ID 列表、新建链标志、新建链 ID）与 chain_updates 映射为 CompleteTurnCommand。
2. 缺省安全策略：
   - 当请求体未指定 attribution 时，默认将 existing_chain_ids 置空，create_new_chain 置 False，由 Service 内部策略决定是否自动创建新链。
"""

import unittest

from app.modules.context.presentation.router import (
    _to_complete_turn_command,
)
from app.modules.context.presentation.schemas import (
    CompleteContextTurnRequest,
)


class ContextCompletionApiContractTest(unittest.TestCase):
    """验证 Context CompleteTurn HTTP 请求模型与应用层 CompleteTurnCommand 之间的映射契约。"""

    def test_request_maps_explicit_attribution_and_new_chain_update(self) -> None:
        """验证携带显式 attribution 与新链 updates 的请求能够完整、准确地转换为领域 Command。"""
        request = CompleteContextTurnRequest.model_validate(
            {
                "assistant_content": "完成",
                "task_ids": ["task-1"],
                "attribution": {
                    "existing_chain_ids": ["chain-a"],
                    "create_new_chain": True,
                    "new_chain_id": "chain-new",
                },
                "chain_updates": [
                    {
                        "chain_id": "chain-new",
                        "related_task_ids": ["task-1"],
                    }
                ],
            }
        )

        command = _to_complete_turn_command(request)

        self.assertEqual(
            command.attribution.existing_chain_ids,
            ["chain-a"],
        )
        self.assertTrue(command.attribution.create_new_chain)
        self.assertEqual(command.attribution.new_chain_id, "chain-new")
        self.assertEqual(command.chain_updates[0].chain_id, "chain-new")

    def test_default_attribution_leaves_auto_new_chain_to_service(self) -> None:
        """验证空请求体时构造默认的 Attribution 对象，将新链判断权保留给 Service 层。"""
        command = _to_complete_turn_command(CompleteContextTurnRequest())

        self.assertEqual(command.attribution.existing_chain_ids, [])
        self.assertFalse(command.attribution.create_new_chain)
        self.assertIsNone(command.attribution.new_chain_id)


if __name__ == "__main__":
    unittest.main()
