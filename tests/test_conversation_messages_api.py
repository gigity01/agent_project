"""Conversation 用户消息 API 测试。"""

from __future__ import annotations

import unittest
from unittest import mock

import httpx
from fastapi import FastAPI
from types import SimpleNamespace

from app.bootstrap.dependencies import get_container
from app.modules.context.presentation.router import router
from app.modules.context.presentation.dependencies import (
    get_context_routing_service,
)
from app.modules.context.application.dto import (
    RouteContextResult,
    SendMessageCommand,
)
from app.modules.context.application.errors import ContextRoutingError
from app.modules.context.domain.models import (
    ContextRouteDecision,
)
from app.modules.context.domain.enums import ContextRouteMode


class ConversationMessagesApiTest(unittest.IsolatedAsyncioTestCase):
    def setUp(self) -> None:
        self.app = FastAPI()
        self.app.include_router(router, prefix="/api")
        self.context_service = mock.Mock()
        self.context_service.send_message = mock.AsyncMock()

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

    async def test_message_is_adapted_to_application_command(self) -> None:
        result = RouteContextResult(
            conversation_id="conv_test_001",
            turn_id="turn-1",
            message="继续完善之前的文档处理日志方案",
            selected_chains=[],
            new_chain_id="chain-1",
            decision=ContextRouteDecision(
                selected_chain_ids=[],
                create_new_chain=True,
                route_mode=ContextRouteMode.NEW_CHAIN,
                reason_summary="当前会话没有可关联的已有上下文链。",
            ),
        )

        self.context_service.send_message.return_value = result

        response = await self._post(
            "/api/conversations/conv_test_001/messages",
            json={
                "message": "继续完善之前的文档处理日志方案",
            },
        )

        self.assertEqual(response.status_code, 200)
        self.assertEqual(
            response.json(),
            {
                "conversation_id": "conv_test_001",
                "turn_id": "turn-1",
                "status": "routed",
                "routing": {
                    "route_mode": "new_chain",
                    "selected_chain_ids": [],
                    "new_chain_id": "chain-1",
                    "reason_summary": (
                        "当前会话没有可关联的已有上下文链。"
                    ),
                },
            },
        )
        self.assertNotIn("selected_chains", response.json())
        self.assertNotIn("resource_queue", response.text)
        self.context_service.send_message.assert_awaited_once_with(
            SendMessageCommand(
                conversation_id="conv_test_001",
                message="继续完善之前的文档处理日志方案",
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

    async def test_routing_error_is_mapped_to_bad_gateway(self) -> None:
        self.context_service.send_message.side_effect = ContextRoutingError(
            "Context Agent 路由失败"
        )

        response = await self._post(
            "/api/conversations/conv_test_001/messages",
            json={"message": "继续之前的方案"},
        )

        self.assertEqual(response.status_code, 502)
        self.assertEqual(
            response.json(),
            {"detail": "Context Agent 路由失败"},
        )

    async def test_unconfigured_agent_is_service_unavailable(self) -> None:
        async def get_unconfigured_container():
            return SimpleNamespace(
                context_agent_router=None,
                context_service=self.context_service,
            )

        self.app.dependency_overrides.pop(
            get_context_routing_service,
            None,
        )
        self.app.dependency_overrides[get_container] = (
            get_unconfigured_container
        )

        response = await self._post(
            "/api/conversations/conv_test_001/messages",
            json={"message": "继续之前的方案"},
        )

        self.assertEqual(response.status_code, 503)
        self.assertEqual(
            response.json(),
            {"detail": "Context Agent 服务未配置"},
        )

    async def test_conversation_id_must_not_exceed_service_limit(self) -> None:
        response = await self._post(
            f"/api/conversations/{'c' * 101}/messages",
            json={"message": "继续之前的方案"},
        )

        self.assertEqual(response.status_code, 422)

    async def test_request_schema_exposes_only_message(self) -> None:
        schema = self.app.openapi()
        request_schema = schema["components"]["schemas"][
            "SendMessageRequest"
        ]

        self.assertEqual(
            set(request_schema["properties"]),
            {"message"},
        )
        self.assertEqual(request_schema["required"], ["message"])


if __name__ == "__main__":
    unittest.main()
