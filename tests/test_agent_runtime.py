"""DeepSeek Agent 配置与运行时的离线单元测试。"""

from __future__ import annotations

import importlib.util
import sys
import types
import unittest
from pathlib import Path
from unittest import mock

from agents import Agent, OpenAIChatCompletionsModel, Runner
from openai import AsyncOpenAI
from openai.types.chat import ChatCompletion


ROOT_DIR = Path(__file__).resolve().parents[1]
SETTINGS_PATH = ROOT_DIR / "app" / "app_config" / "settings.py"
RUNTIME_PATH = ROOT_DIR / "app" / "agents" / "runtime.py"


def _load_settings_module(*, missing_deepseek_key: bool = False):
    environment_module = types.ModuleType("main_config.environment")
    main_config_module = types.ModuleType("main_config")

    def get_required_env(name: str) -> str:
        if missing_deepseek_key and name == "DEEPSEEK_API_KEY":
            raise RuntimeError(f"缺少必填环境变量: {name}")
        return f"{name.lower()}-test-placeholder"

    environment_module.load_local_env_file = lambda project_root: None
    environment_module.get_required_env = get_required_env
    environment_module.get_env = lambda name, default: default
    environment_module.get_int_env = lambda name, default: default
    main_config_module.environment = environment_module

    replacements = {
        "main_config": main_config_module,
        "main_config.environment": environment_module,
    }
    originals = {name: sys.modules.get(name) for name in replacements}
    module_name = "agent_settings_under_test"

    try:
        sys.modules.update(replacements)
        spec = importlib.util.spec_from_file_location(module_name, SETTINGS_PATH)
        if spec is None or spec.loader is None:
            raise RuntimeError("无法加载待测试的应用配置")
        module = importlib.util.module_from_spec(spec)
        sys.modules[module_name] = module
        spec.loader.exec_module(module)
        return module
    finally:
        sys.modules.pop(module_name, None)
        for name, original in originals.items():
            if original is None:
                sys.modules.pop(name, None)
            else:
                sys.modules[name] = original


def _load_runtime_module():
    settings_module = types.ModuleType("app.app_config.settings")
    settings_module.DEEPSEEK_API_KEY = "deepseek-test-placeholder"
    settings_module.DEEPSEEK_BASE_URL = "https://api.deepseek.com"
    settings_module.DEEPSEEK_MODEL_NAME = "deepseek-v4-flash"
    settings_module.DEEPSEEK_TIMEOUT_SECONDS = 60
    settings_module.DEEPSEEK_MAX_RETRIES = 2

    replacements = {"app.app_config.settings": settings_module}
    originals = {name: sys.modules.get(name) for name in replacements}
    module_name = "agent_runtime_under_test"

    try:
        sys.modules.update(replacements)
        spec = importlib.util.spec_from_file_location(module_name, RUNTIME_PATH)
        if spec is None or spec.loader is None:
            raise RuntimeError("无法加载待测试的 AgentRuntime")
        module = importlib.util.module_from_spec(spec)
        sys.modules[module_name] = module
        spec.loader.exec_module(module)
        return module
    finally:
        sys.modules.pop(module_name, None)
        for name, original in originals.items():
            if original is None:
                sys.modules.pop(name, None)
            else:
                sys.modules[name] = original


class AgentSettingsTest(unittest.TestCase):
    def test_missing_deepseek_api_key_fails_configuration(self) -> None:
        with self.assertRaisesRegex(RuntimeError, "DEEPSEEK_API_KEY"):
            _load_settings_module(missing_deepseek_key=True)

    def test_deepseek_defaults_are_stable(self) -> None:
        settings = _load_settings_module()

        self.assertEqual(settings.DEEPSEEK_BASE_URL, "https://api.deepseek.com")
        self.assertEqual(settings.DEEPSEEK_MODEL_NAME, "deepseek-v4-flash")
        self.assertEqual(settings.DEEPSEEK_TIMEOUT_SECONDS, 60)
        self.assertEqual(settings.DEEPSEEK_MAX_RETRIES, 2)


class AgentRuntimeTest(unittest.IsolatedAsyncioTestCase):
    async def test_create_configures_chat_completions_runtime(self) -> None:
        runtime_module = _load_runtime_module()

        with mock.patch.object(
            runtime_module,
            "set_tracing_disabled",
        ) as set_tracing_disabled:
            runtime = runtime_module.AgentRuntime.create()

        try:
            set_tracing_disabled.assert_called_once_with(True)
            self.assertIsInstance(runtime.client, AsyncOpenAI)
            self.assertIsInstance(runtime.model, OpenAIChatCompletionsModel)
            self.assertEqual(runtime.model.model, "deepseek-v4-flash")
            self.assertIs(runtime.model._client, runtime.client)
            self.assertTrue(runtime.model._strict_feature_validation)
            self.assertTrue(runtime.model._buffer_streamed_tool_calls)
            self.assertEqual(
                str(runtime.client.base_url).rstrip("/"),
                "https://api.deepseek.com",
            )
            self.assertEqual(runtime.client.max_retries, 2)
            self.assertEqual(runtime.client.timeout, 60)
            self.assertEqual(runtime.default_model_settings.max_tokens, 512)
            self.assertFalse(
                runtime.default_model_settings.parallel_tool_calls
            )
            self.assertEqual(
                runtime.default_model_settings.extra_body,
                {"thinking": {"type": "disabled"}},
            )
        finally:
            await runtime.aclose()

    async def test_aclose_closes_async_client(self) -> None:
        runtime_module = _load_runtime_module()
        runtime = runtime_module.AgentRuntime.create()

        with mock.patch.object(
            runtime.client,
            "close",
            new=mock.AsyncMock(),
        ) as close:
            await runtime.aclose()

        close.assert_awaited_once_with()
        await runtime.client.close()

    async def test_runner_uses_chat_completions_with_provider_settings(
        self,
    ) -> None:
        runtime_module = _load_runtime_module()
        runtime = runtime_module.AgentRuntime.create()
        completion = ChatCompletion.model_validate(
            {
                "id": "chatcmpl-deepseek-test",
                "object": "chat.completion",
                "created": 0,
                "model": "deepseek-v4-flash",
                "choices": [
                    {
                        "index": 0,
                        "message": {
                            "role": "assistant",
                            "content": "SDK_OK",
                        },
                        "finish_reason": "stop",
                    }
                ],
                "usage": {
                    "prompt_tokens": 1,
                    "completion_tokens": 1,
                    "total_tokens": 2,
                },
            }
        )
        create = mock.AsyncMock(return_value=completion)
        agent = Agent(
            name="SDK Offline Agent",
            instructions="只回复 SDK_OK。",
            model=runtime.model,
            model_settings=runtime.default_model_settings,
        )

        try:
            with mock.patch.object(
                runtime.client.chat.completions,
                "create",
                new=create,
            ):
                result = await Runner.run(
                    agent,
                    input="执行离线连通性检查。",
                    max_turns=1,
                )

            self.assertEqual(result.final_output, "SDK_OK")
            request = create.await_args.kwargs
            self.assertEqual(request["model"], "deepseek-v4-flash")
            self.assertEqual(request["max_tokens"], 512)
            self.assertFalse(request["parallel_tool_calls"])
            self.assertEqual(
                request["extra_body"],
                {"thinking": {"type": "disabled"}},
            )
            self.assertNotIsInstance(request["response_format"], dict)
        finally:
            await runtime.aclose()


if __name__ == "__main__":
    unittest.main()
