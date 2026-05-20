from typing import Dict
from core.metadata_manager import metadata_manager
from config.settings import KB_STATUS_ACTIVE

# 状态定义
STATE_NORMAL = "normal"
STATE_WAIT_CLARIFY = "wait_clarify"  # 等待用户澄清（文件不明确）
STATE_WAIT_CONFIRM = "wait_confirm"  # 等待用户确认（删除/覆盖）

class Validator:
    def __init__(self):
        # 内存状态机（生产可用Redis替换）
        self.user_state = {}  # {user_id: state}
        self.pending_task = {}  # 待执行任务缓存

    # ====================== 【主入口】统一校验 ======================
    def validate(self, user_id: str, intent_data: Dict) -> Dict:
        """
        输入：LLM解析后的意图
        输出：系统决策（直接执行 / 追问 / 确认）
        """
        intent = intent_data.get("intent")
        target = intent_data.get("target")

        # 1. 清单/查询/新增 无需校验
        if intent in ["list", "query", "ingest"]:
            return self._ok()

        # 2. 必须有目标文件
        if not target:
            return self._clarify("请告诉我你要操作的文件名")

        # 3. 模糊匹配，检查是否有多个文件
        matches = metadata_manager.fuzzy_match(target)
        if intent == "restore":
            active_matches = [f for f in matches if f["status"] != KB_STATUS_ACTIVE]
        else:
            active_matches = [f for f in matches if f["status"] == KB_STATUS_ACTIVE]

        # 4. 匹配到多个 → 必须追问澄清
        if len(active_matches) > 1:
            return self._multi_file_clarify(active_matches)

        # 5. 没匹配到 → 提示不存在
        if len(active_matches) == 0:
            return self._fail("未找到该文件，请确认文件名")

        # 6. 高风险操作：删除 / 覆盖 → 必须二次确认
        if intent in ["delete", "replace"]:
            file_name = active_matches[0]["file_name"]
            return self._need_confirm(intent_data, file_name)

        # 7. 安全操作（restore/ingest）→ 直接通过
        return self._ok()

    # ====================== 响应模板 ======================
    def _ok(self):
        return {"status": "ok", "state": STATE_NORMAL}

    def _clarify(self, msg):
        return {"status": "need_clarify", "message": msg, "state": STATE_WAIT_CLARIFY}

    def _fail(self, msg):
        return {"status": "failed", "message": msg}

    def _multi_file_clarify(self, files):
        options = "\n".join([f"{i+1}. {f['file_name']}" for i, f in enumerate(files)])
        msg = f"找到多个文件，请选择：\n{options}"
        return {"status": "need_clarify", "message": msg, "state": STATE_WAIT_CLARIFY}

    def _need_confirm(self, intent_data, file_name):
        intent_cn = {
            "delete": "删除",
            "replace": "覆盖更新"
        }.get(intent_data["intent"], "操作")
        msg = f"确认要{intent_cn}《{file_name}》吗？"
        return {
            "status": "need_confirm",
            "message": msg,
            "state": STATE_WAIT_CONFIRM,
            "pending_task": intent_data
        }

# 全局单例
validator = Validator()