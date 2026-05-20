from typing import List, Dict

from langchain_chroma import Chroma
from langchain_community.embeddings import DashScopeEmbeddings

from config.settings import DASHSCOPE_API_KEY, EMBEDDING_MODEL_NAME, VECTOR_DB_PATH
from core.logger import logger


# ==================== 向量库管理类（LangChain + 通义千问向量模型） ====================
class VectorStore:
    _instance = None

    def __new__(cls, *args, **kwargs):
        if cls._instance is None:
            cls._instance = super().__new__(cls)
            cls._instance._init_vector_db()
        return cls._instance

    def _init_vector_db(self):
        """初始化LangChain Chroma向量库，使用通义千问在线向量模型"""
        # 通义千问向量嵌入
        self.embedding = DashScopeEmbeddings(
            model=EMBEDDING_MODEL_NAME,  # 通义千问官方向量模型
            dashscope_api_key=DASHSCOPE_API_KEY

        )

        # 初始化Chroma持久化存储（和你截图里的写法完全一致）
        self.vector_store = Chroma(
            collection_name="kb_documents",
            embedding_function=self.embedding,
            persist_directory=VECTOR_DB_PATH
        )

        logger.info("✅ LangChain + 通义千问向量库初始化完成，无本地模型下载")

    # ==================== 入库：添加分块向量（接口完全兼容旧版） ====================
    def add_chunks(self, chunks: List[Dict], file_path: str) -> List[str]:
        """
        把分块文本加入向量库，保持和旧版接口一致
        :param chunks: 包含chunk_id、content、metadata的分块列表
        :param file_path: 所属文件路径（用于后续按文件操作）
        :return: 新增的向量ID列表
        """
        texts = []
        metadatas = []
        ids = []

        for chunk in chunks:
            chunk_id = chunk.get("chunk_id")
            content = chunk.get("content", "")
            meta = chunk.get("metadata", {})

            # 关键：绑定文件路径 + 软删除标记
            meta["file_path"] = file_path
            meta["is_deleted"] = False

            texts.append(content)
            metadatas.append(meta)
            ids.append(chunk_id)

        # LangChain 批量入库
        self.vector_store.add_texts(
            texts=texts,
            metadatas=metadatas,
            ids=ids
        )

        logger.info(f"📦 向量入库完成：{len(ids)} 个分块 | 文件：{file_path}")
        return ids

    # ==================== 按文件路径：软删除向量 ====================
    def soft_delete_by_file(self, file_path: str) -> bool:
        """软删除：仅标记is_deleted=True，不删除数据"""
        # 找到该文件的所有向量ID
        results = self.vector_store.get(where={"file_path": file_path})
        if not results["ids"]:
            logger.warning(f"⚠️ 未找到向量：{file_path}")
            return False

        # 更新metadata，标记为已删除
        self.vector_store._collection.update(
            ids=results["ids"],
            metadatas=[{"is_deleted": True} for _ in results["ids"]]
        )

        logger.info(f"🗑️ 软删除完成：{file_path} | 共 {len(results['ids'])} 个分块")
        return True

    # ==================== 按文件路径：恢复向量 ====================
    def restore_by_file(self, file_path: str) -> bool:
        """恢复软删除的文件向量：取消is_deleted标记"""
        results = self.vector_store.get(where={"file_path": file_path})
        if not results["ids"]:
            return False

        self.vector_store._collection.update(
            ids=results["ids"],
            metadatas=[{"is_deleted": False} for _ in results["ids"]]
        )

        logger.info(f"✅ 恢复向量：{file_path}")
        return True

    # ==================== 核心检索：自动过滤已删除内容 ====================
    def query(self, query_text: str, top_k: int = 5) -> List[Dict]:
        """检索知识，只返回未被软删除的向量"""
        # LangChain 相似度检索 + 过滤条件
        results = self.vector_store.similarity_search_with_score(
            query=query_text,
            k=top_k,
            filter={"is_deleted": False}  # 关键：过滤已删除内容
        )

        # 格式化结果，和旧版接口完全一致
        formatted = []
        for doc, score in results:
            formatted.append({
                "chunk_id": doc.id,
                "content": doc.page_content,
                "metadata": doc.metadata,
                "score": float(score)
            })
        return formatted

    def add_hierarchical_chunks(self, file_path: str, hierarchical_blocks: List[Dict]) -> List[str]:
        flattened = []
        for block in hierarchical_blocks:
            parent_id = block.get("id", str(hash(block["parent"])))
            block_type = block.get("type", "section")
            section_path = block.get("section_path", [])
            flattened.append({
                "chunk_id": f"{parent_id}_parent",
                "content": block["parent"],
                "metadata": {
                    "chunk_role": "parent",
                    "block_type": block_type,
                    "section_path": section_path,
                    "has_children": True,
                }
            })
            for i, child_text in enumerate(block.get("children", [])):
                flattened.append({
                    "chunk_id": f"{parent_id}_child_{i}",
                    "content": child_text,
                    "metadata": {
                        "chunk_role": "child",
                        "parent_id": parent_id,
                        "block_type": block_type,
                        "section_path": section_path,
                    }
                })
        return self.add_chunks(flattened, file_path)

    def hybrid_search(self, question: str, top_k: int = 5) -> List[Dict]:
        return self.query(question, top_k=top_k)

    # ==================== 获取某个文件的所有向量ID（给台账用） ====================
    def get_chunk_ids_by_file(self, file_path: str) -> List[str]:
        results = self.vector_store.get(where={"file_path": file_path})
        return results["ids"]


# 全局单例（和旧版完全一致，不影响其他代码）
vector_store = VectorStore()
