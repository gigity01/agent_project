from typing import Dict
from KBagent.intent_parser import intent_parser
from KBagent.validator import validator, STATE_WAIT_CLARIFY, STATE_WAIT_CONFIRM
from KBagent.kb_tools import ReadTools, WriteTools
from core.logger import logger

class KnowledgeBaseAgent:
    def __init__(self):
        # 简易内存会话存储，后续可无缝换成 Redis
        self.session = {}

    def run(self, user_id: str, user_input: str, llm_func) -> Dict:
        """
        总入口：接收用户指令，全流程调度
        :param user_id: 区分不同用户/会话
        :param user_input: 管理员输入
        :param llm_func: LLM调用函数
        :return: 响应结果
        """
        # 1. 优先处理上一轮待澄清/待确认的会话
        if user_id in self.session:
            return self._handle_pending_session(user_id, user_input)

        # 2. 全新指令：LLM解析结构化意图
        intent_data = intent_parser.parse(user_input, llm_func)
        intent = intent_data.get("intent")
        if not intent:
            return {"reply": "无法识别当前操作指令，请重新输入"}

        # 3. 安全规则校验（参数/歧义/高危确认）
        validate_res = validator.validate(user_id, intent_data)

        # 3.1 直接正常执行
        if validate_res["status"] == "ok":
            return self._dispatch_tool(intent_data)

        # 3.2 需要用户补充澄清
        if validate_res["status"] == "need_clarify":
            self.session[user_id] = {
                "state": STATE_WAIT_CLARIFY,
                "pending_intent": intent_data
            }
            return {"reply": validate_res["message"]}

        # 3.3 需要高危操作确认
        if validate_res["status"] == "need_confirm":
            self.session[user_id] = {
                "state": STATE_WAIT_CONFIRM,
                "pending_intent": validate_res["pending_task"]
            }
            return {"reply": validate_res["message"]}

        # 3.4 校验失败
        return {"reply": validate_res.get("message", "操作校验失败")}

    def _handle_pending_session(self, user_id: str, user_input: str) -> Dict:
        """处理待澄清、待确认的后续用户回复"""
        session_data = self.session[user_id]
        state = session_data["state"]
        pending_intent = session_data["pending_intent"]

        # 情况1：等待澄清 → 用户给出文件名/选择
        if state == STATE_WAIT_CLARIFY:
            # 把用户补充的内容覆盖到target
            pending_intent["target"] = user_input
            # 清除会话状态
            del self.session[user_id]
            # 重新走工具调度执行
            return self._dispatch_tool(pending_intent)

        # 情况2：等待确认 → 用户回复 确认/取消
        if state == STATE_WAIT_CONFIRM:
            del self.session[user_id]
            if user_input in ["确认", "是的", "ok", "确定"]:
                return self._dispatch_tool(pending_intent)
            else:
                return {"reply": "已取消本次操作"}

        return {"reply": "会话异常，请重新发起指令"}

    def _dispatch_tool(self, intent_data: Dict) -> Dict:
        """根据意图，确定性调度原子工具，LLM不参与"""
        intent = intent_data["intent"]
        target = intent_data["target"]
        query = intent_data["query"]

        # 读工具
        if intent == "list":
            res = ReadTools.list_knowledge_files()
            return {"reply": f"知识库文件列表：共{len(res)}个", "data": res}

        if intent == "query":
            res = ReadTools.query_knowledge(query)
            return {"reply": "知识检索完成", "data": res}

        # 写工具
        if intent == "ingest":
            res = WriteTools.ingest_file(target)
            return {"reply": res["msg"]}

        if intent == "delete":
            res = WriteTools.soft_delete_file(target)
            return {"reply": res["msg"]}

        if intent == "restore":
            res = WriteTools.restore_file(target)
            return {"reply": res["msg"]}

        if intent == "replace":
            res = WriteTools.replace_file(target)
            return {"reply": res["msg"]}

        return {"reply": "未知操作类型"}

# 全局单例
kb_agent = KnowledgeBaseAgent()