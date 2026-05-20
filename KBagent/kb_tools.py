from core.metadata_manager import metadata_manager
from core.vector_store import vector_store
from facade.file_process_facade import file_facade
from config.settings import KB_STATUS_DELETED, KB_STATUS_ACTIVE, KB_STATUS_REPLACED
from core.logger import logger

# ==================== 【读工具】只查询，不修改数据 ====================
class ReadTools:
    @staticmethod
    def list_knowledge_files(only_active=True):
        """
        查看知识库文件清单
        :param only_active: True=只看正常文件 False=看全部
        """
        return metadata_manager.list_all(only_active=only_active)

    @staticmethod
    def query_knowledge(query: str, top_k: int = 5):
        """
        检索知识（给RAG用）
        """
        return vector_store.query(query, top_k=top_k)

    @staticmethod
    def fuzzy_match_files(keyword: str):
        """
        模糊匹配文件（安全校验追问用）
        """
        return metadata_manager.fuzzy_match(keyword)

# ==================== 【写工具】会修改知识库，必须严格管控 ====================
class WriteTools:
    @staticmethod
    def ingest_file(file_path: str):
        """
        新增文件入库（自动查重！）
        1. 查重
        2. 解析→分块→向量入库
        3. 写入台账
        返回：成功/失败
        """
        # 1. 查重（核心！重复直接拒绝）
        is_dup, exist_record = metadata_manager.is_file_duplicated(file_path)
        if is_dup:
            return {
                "success": False,
                "msg": f"文件已存在，禁止重复入库：{exist_record['file_name']}"
            }

        # 2. 执行全流程入库
        try:
            success = file_facade.process_and_store(file_path)
            if not success:
                return {"success": False, "msg": "文件处理入库失败"}
            doc_id = metadata_manager.add_file(file_path, [])
            return {
                "success": True,
                "msg": f"入库成功",
                "doc_id": doc_id
            }
        except Exception as e:
            logger.error(f"入库失败：{str(e)}")
            return {"success": False, "msg": f"入库异常：{str(e)}"}

    @staticmethod
    def soft_delete_file(file_identifier: str):
        """
        软删除文件
        1. 台账标记 deleted
        2. 向量库软删除
        """
        records = metadata_manager.fuzzy_match(file_identifier)
        if not records:
            return {"success": False, "msg": "未找到该文件"}
        file_path = records[0]["file_path"]
        # 向量软删除
        vector_store.soft_delete_by_file(file_path)
        # 台账状态修改
        metadata_manager.update_status(file_path, KB_STATUS_DELETED)
        return {"success": True, "msg": "已软删除，可恢复"}

    @staticmethod
    def restore_file(file_identifier: str):
        """
        恢复已删除文件
        """
        records = metadata_manager.fuzzy_match(file_identifier)
        if not records:
            return {"success": False, "msg": "未找到该文件"}
        file_path = records[0]["file_path"]
        vector_store.restore_by_file(file_path)
        metadata_manager.update_status(file_path, KB_STATUS_ACTIVE)
        return {"success": True, "msg": "文件已恢复正常"}

    @staticmethod
    def replace_file(file_path: str):
        """
        覆盖更新文件
        1. 旧版本标记 replaced + 向量软删除
        2. 新版本入库
        """
        # 查找旧文件
        is_dup, old_record = metadata_manager.is_file_duplicated(file_path)
        if not is_dup:
            return WriteTools.ingest_file(file_path)

        # 旧版本标记为已覆盖
        old_file_path = old_record["file_path"]
        metadata_manager.update_status(old_file_path, KB_STATUS_REPLACED)
        vector_store.soft_delete_by_file(old_file_path)

        # 新版本入库
        return WriteTools.ingest_file(file_path)

# ==================== 【安全工具】校验类 ====================
class SafetyTools:
    @staticmethod
    def check_duplicate(file_path: str):
        """仅查重，不入库"""
        return metadata_manager.is_file_duplicated(file_path)