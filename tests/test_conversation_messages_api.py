"""Conversation 用户消息 API 测试。"""

from __future__ import annotations

import unittest
from unittest import mock

import httpx
from fastapi import FastAPI

from app.api.conversations import router
from app.api.dependencies import (
    get_context_routing_service,
)
from app.schemas.context import (
    ContextRouteDecision,
    ContextRouteMode,
    ContextRouteRequest,
    RoutedContextPackage,
)


class ConversationMessagesApiTest(unittest.IsolatedAsyncioTestCase):
    def setUp(self) -> None:
        self.app = FastAPI()
        self.app.include_router(router, prefix="/api")
        self.context_service = mock.Mock()
        self.context_service.route_context = mock.AsyncMock()

        async def get_service():
            return self.context_service

        self.app.dependency_overrides[get_context_routing_service] = (
            get_service
        )

    async def _post(self, path: str, *, json: dict[str, str]):
        transport = httpx.ASGITransport(app=self.app)
        async with httpx.AsyncClient(
            transport=transport,
            base_url="http://testserver",
        ) as client:
            return await client.post(path, json=json)

    async def test_message_is_adapted_to_context_route_request(self) -> None:
        routed_package = RoutedContextPackage(
            current_turn_id="turn-1",
            current_user_input="继续完善之前的文档处理日志方案",
            selected_chains=[],
            new_chain_id="chain-1",
            route_decision=ContextRouteDecision(
                selected_chain_ids=[],
                create_new_chain=True,
                route_mode=ContextRouteMode.NEW_CHAIN,
                reason_summary="当前会话没有可关联的已有上下文链。",
            ),
        )

        self.context_service.route_context.return_value = routed_package

        response = await self._post(
            "/api/conversations/conv_test_001/messages",
            json={
                "message": "继续完善之前的文档处理日志方案",
            },
        )

        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.json(), routed_package.model_dump(mode="json"))
        self.context_service.route_context.assert_awaited_once_with(
            ContextRouteRequest(
                conversation_id="conv_test_001",
                user_input="继续完善之前的文档处理日志方案",
            )
        )

    async def test_message_is_required_and_must_not_be_empty(self) -> None:
        missing_response = await self._post(
            "/api/conversations/conv_test_001/messages",
            json={},
        )
        empty_response = await self._post(
            "/api/conversations/conv_test_001/messages",
            json={"message": ""},
        )

        self.assertEqual(missing_response.status_code, 422)
        self.assertEqual(empty_response.status_code, 422)

    async def test_conversation_id_must_not_exceed_service_limit(self) -> None:
        response = await self._post(
            f"/api/conversations/{'c' * 101}/messages",
            json={"message": "继续之前的方案"},
        )

        self.assertEqual(response.status_code, 422)

    async def test_request_schema_exposes_only_message(self) -> None:
        schema = self.app.openapi()
        request_schema = schema["components"]["schemas"][
            "SendConversationMessageRequest"
        ]

        self.assertEqual(
            set(request_schema["properties"]),
            {"message"},
        )
        self.assertEqual(request_schema["required"], ["message"])


if __name__ == "__main__":
    unittest.main()
