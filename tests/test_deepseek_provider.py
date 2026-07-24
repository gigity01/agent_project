"""DeepSeek Agent 配置与模型 Provider 的离线单元测试。"""

from __future__ import annotations

import importlib.util
import os
import subprocess
import sys
import types
import unittest
from pathlib import Path
from unittest import mock

from agents import Agent, OpenAIChatCompletionsModel, Runner
from openai import AsyncOpenAI
from openai.types.chat import ChatCompletion

from main_config import environment


ROOT_DIR = Path(__file__).resolve().parents[1]
SETTINGS_PATH = ROOT_DIR / "app" / "app_config" / "settings.py"
PROVIDER_PATH = ROOT_DIR / "app" / "agents" / "deepseek_provider.py"


def _load_settings_module(*, missing_deepseek_key: bool = False):
    environment_module = types.ModuleType("main_config.environment")
    main_config_module = types.ModuleType("main_config")

    environment_module.load_local_env_file = lambda project_root: None
    environment_module.get_required_env = (
        lambda name: f"{name.lower()}-test-placeholder"
    )
    environment_module.get_optional_env = (
        lambda name: None
        if missing_deepseek_key
        else f"{name.lower()}-test-placeholder"
    )
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


def _load_provider_module(*, api_key: str | None = "deepseek-test-placeholder"):
    settings_module = types.ModuleType("app.app_config.settings")
    settings_module.DEEPSEEK_API_KEY = api_key
    settings_module.DEEPSEEK_BASE_URL = "https://api.deepseek.com"
    settings_module.DEEPSEEK_MODEL_NAME = "deepseek-v4-flash"
    settings_module.DEEPSEEK_TIMEOUT_SECONDS = 60
    settings_module.DEEPSEEK_MAX_RETRIES = 2

    replacements = {"app.app_config.settings": settings_module}
    originals = {name: sys.modules.get(name) for name in replacements}
    module_name = "deepseek_provider_under_test"

    try:
        sys.modules.update(replacements)
        spec = importlib.util.spec_from_file_location(module_name, PROVIDER_PATH)
        if spec is None or spec.loader is None:
            raise RuntimeError("无法加载待测试的 DeepSeekModelProvider")
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


class OptionalEnvironmentTest(unittest.TestCase):
    def test_optional_env_treats_missing_and_placeholder_as_unconfigured(
        self,
    ) -> None:
        with mock.patch.dict(os.environ, {}, clear=True):
            self.assertIsNone(environment.get_optional_env("OPTIONAL_TEST_KEY"))

        with mock.patch.dict(
            os.environ,
            {"OPTIONAL_TEST_KEY": "replace-with-test-key"},
            clear=True,
        ):
            self.assertIsNone(environment.get_optional_env("OPTIONAL_TEST_KEY"))

    def test_optional_env_returns_configured_value(self) -> None:
        with mock.patch.dict(
            os.environ,
            {"OPTIONAL_TEST_KEY": "configured-test-value"},
            clear=True,
        ):
            self.assertEqual(
                environment.get_optional_env("OPTIONAL_TEST_KEY"),
                "configured-test-value",
            )


class AgentSettingsTest(unittest.TestCase):
    def test_missing_deepseek_api_key_does_not_fail_configuration(self) -> None:
        settings = _load_settings_module(missing_deepseek_key=True)

        self.assertIsNone(settings.DEEPSEEK_API_KEY)

    def test_deepseek_defaults_are_stable(self) -> None:
        settings = _load_settings_module()

        self.assertEqual(settings.DEEPSEEK_BASE_URL, "https://api.deepseek.com")
        self.assertEqual(settings.DEEPSEEK_MODEL_NAME, "deepseek-v4-flash")
        self.assertEqual(settings.DEEPSEEK_TIMEOUT_SECONDS, 60)
        self.assertEqual(settings.DEEPSEEK_MAX_RETRIES, 2)

    def test_fastapi_lifespan_starts_without_deepseek_api_key(self) -> None:
        code = """
import asyncio
import os

os.environ.pop("DEEPSEEK_API_KEY", None)

from main_config import environment
environment.load_local_env_file = lambda project_root: None

from app import main as app_main

async def check() -> None:
    async with app_main.lifespan(app_main.app):
        assert app_main.app.state.deepseek_provider is None

asyncio.run(check())
print("FastAPI lifespan without DeepSeek key: OK")
"""
        child_environment = os.environ.copy()
        child_environment["SQLALCHEMY_DATABASE_URL"] = (
            "sqlite+pysqlite:///:memory:"
        )
        child_environment["DASHSCOPE_API_KEY"] = "lifespan-test-placeholder"
        child_environment.pop("DEEPSEEK_API_KEY", None)

        result = subprocess.run(
            [sys.executable, "-c", code],
            cwd=ROOT_DIR,
            env=child_environment,
            capture_output=True,
            text=True,
            timeout=60,
        )

        self.assertEqual(result.returncode, 0, msg=result.stderr)
        self.assertIn(
            "FastAPI lifespan without DeepSeek key: OK",
            result.stdout,
        )


class DeepSeekModelProviderTest(unittest.IsolatedAsyncioTestCase):
    async def test_create_configures_chat_completions_provider(self) -> None:
        provider_module = _load_provider_module()
        provider = provider_module.DeepSeekModelProvider.create()

        try:
            self.assertIsInstance(provider.client, AsyncOpenAI)
            self.assertIsInstance(provider.model, OpenAIChatCompletionsModel)
            self.assertEqual(provider.model.model, "deepseek-v4-flash")
            self.assertIs(provider.model._client, provider.client)
            self.assertTrue(provider.model._strict_feature_validation)
            self.assertTrue(provider.model._buffer_streamed_tool_calls)
            self.assertEqual(
                str(provider.client.base_url).rstrip("/"),
                "https://api.deepseek.com",
            )
            self.assertEqual(provider.client.max_retries, 2)
            self.assertEqual(provider.client.timeout, 60)
            self.assertEqual(provider.model_settings.max_tokens, 512)
            self.assertFalse(provider.model_settings.parallel_tool_calls)
            self.assertEqual(
                provider.model_settings.extra_body,
                {"thinking": {"type": "disabled"}},
            )
        finally:
            await provider.aclose()

    async def test_create_requires_deepseek_api_key(self) -> None:
        provider_module = _load_provider_module(api_key=None)

        with self.assertRaisesRegex(
            RuntimeError,
            "Agent 功能未配置 DEEPSEEK_API_KEY",
        ):
            provider_module.DeepSeekModelProvider.create()

    async def test_aclose_closes_async_client(self) -> None:
        provider_module = _load_provider_module()
        provider = provider_module.DeepSeekModelProvider.create()

        with mock.patch.object(
            provider.client,
            "close",
            new=mock.AsyncMock(),
        ) as close:
            await provider.aclose()

        close.assert_awaited_once_with()
        await provider.client.close()

    async def test_build_run_config_injects_provider_resources(self) -> None:
        provider_module = _load_provider_module()
        provider = provider_module.DeepSeekModelProvider.create()

        try:
            run_config = provider_module.build_deepseek_run_config(provider)

            self.assertIs(run_config.model, provider.model)
            self.assertIs(run_config.model_settings, provider.model_settings)
            self.assertTrue(run_config.tracing_disabled)
        finally:
            await provider.aclose()

    async def test_runner_uses_chat_completions_with_provider_settings(
        self,
    ) -> None:
        provider_module = _load_provider_module()
        provider = provider_module.DeepSeekModelProvider.create()
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
        )
        run_config = provider_module.build_deepseek_run_config(provider)

        try:
            with mock.patch.object(
                provider.client.chat.completions,
                "create",
                new=create,
            ):
                result = await Runner.run(
                    agent,
                    input="执行离线连通性检查。",
                    max_turns=1,
                    run_config=run_config,
                )

            self.assertEqual(result.final_output, "SDK_OK")
            self.assertIsNone(agent.model)
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
            await provider.aclose()


if __name__ == "__main__":
    unittest.main()
