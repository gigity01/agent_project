import json
from typing import Dict
from config.prompt import INTENT_PARSE_PROMPT
from core.logger import logger

# 可支持的合法意图列表
VALID_INTENTS = {
    "ingest",
    "delete",
    "restore",
    "replace",
    "list",
    "query"
}


class IntentParser:
    @staticmethod
    def parse(user_input: str, llm_func) -> Dict:
        """
        :param user_input: 管理员自然语言指令
        :param llm_func: 传入你的LLM调用函数
        :return: 结构化意图字典
        """
        # 填充Prompt模板
        prompt = INTENT_PARSE_PROMPT.replace("{{user_input}}", user_input)

        try:
            # 调用LLM
            resp = llm_func(prompt)
            # 清洗多余文本，只拿JSON部分
            json_str = IntentParser._extract_json(resp)
            data = json.loads(json_str)

            # 校验意图合法性
            intent = data.get("intent", "")
            if intent not in VALID_INTENTS:
                data["intent"] = ""

            # 兜底字段
            data.setdefault("target", "")
            data.setdefault("query", "")
            return data

        except Exception as e:
            logger.error(f"意图解析失败: {e}")
            return {
                "intent": "",
                "target": "",
                "query": ""
            }

    @staticmethod
    def _extract_json(text: str) -> str:
        """兜底：防止LLM前后加废话，只截取{}之间的JSON"""
        start = text.find("{")
        end = text.rfind("}")
        if start != -1 and end != -1:
            return text[start:end + 1]
        return text


# 全局单例
intent_parser = IntentParser()