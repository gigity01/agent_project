"""Context 完成接口的 Turn Attribution 契约测试。"""

import unittest

from app.modules.context.presentation.router import (
    _to_complete_turn_command,
)
from app.modules.context.presentation.schemas import (
    CompleteContextTurnRequest,
)


class ContextCompletionApiContractTest(unittest.TestCase):
    def test_request_maps_explicit_attribution_and_new_chain_update(self) -> None:
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
        command = _to_complete_turn_command(CompleteContextTurnRequest())

        self.assertEqual(command.attribution.existing_chain_ids, [])
        self.assertFalse(command.attribution.create_new_chain)
        self.assertIsNone(command.attribution.new_chain_id)


if __name__ == "__main__":
    unittest.main()
