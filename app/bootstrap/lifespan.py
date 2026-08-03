"""FastAPI 应用生命周期与对象装配。"""

from __future__ import annotations

from contextlib import asynccontextmanager

from fastapi import FastAPI
from qdrant_client.models import PointStruct
from sqlalchemy.exc import IntegrityError

from app.config.settings import (
    CONTEXT_RESOURCE_QUEUE_MAX_SIZE,
    CONTEXT_ROUTE_LOCK_BLOCKING_TIMEOUT_SECONDS,
    CONTEXT_ROUTE_LOCK_TIMEOUT_SECONDS,
    CLEANED_STORAGE_DIR,
    DEFAULT_CREATED_BY_ACTOR_CODE,
    DEFAULT_DOCUMENT_STATUS,
    DEFAULT_DOCUMENT_VERSION,
    DEEPSEEK_API_KEY,
    DOCUMENT_CODE_PREFIX,
    DOCUMENT_CODE_RANDOM_LENGTH,
    EMBEDDING_BATCH_SIZE,
    EMBEDDING_MODEL_NAME,
    EMBEDDING_VECTOR_SIZE,
    MAX_UPLOAD_FILE_SIZE,
    RAW_EXTERNAL_STORAGE_DIR,
    RAW_LOCAL_STORAGE_DIR,
    REDIS_SOCKET_CONNECT_TIMEOUT_SECONDS,
    REDIS_SOCKET_TIMEOUT_SECONDS,
    REDIS_URL,
    SECONDARY_TEXT_STORAGE_DIR,
)
from app.bootstrap.container import AppContainer
from app.infrastructure.database.uow import SQLAlchemyUnitOfWork
from app.infrastructure.llm.deepseek.provider import DeepSeekModelProvider
from app.infrastructure.redis.client import (
    close_redis_client,
    create_redis_client,
    ping_redis_client,
)
from app.modules.context.infrastructure.cache.redis_resource_queue import (
    ContextResourceQueueRepository,
)
from app.modules.context.infrastructure.llm.deepseek_router import (
    DeepSeekContextRouter,
)
from app.modules.context.infrastructure.locking.redis_conversation_lock import (
    ConversationRouteLockManager,
)
from app.modules.context.infrastructure.persistence.mapper import (
    SQLAlchemyContextRecordFactory,
    build_context_chain,
)
from app.modules.context.application.context_service import ContextService
from app.modules.context.application.resource_service import (
    ContextResourceService,
)
from app.modules.document.application.ports import (
    DocumentApplicationPorts,
)
from app.modules.document.application.settings import (
    DocumentIndexingSettings,
    DocumentProcessingSettings,
    DocumentUploadSettings,
)
from app.modules.document.application.use_cases.build_chunks import (
    BuildChunksUseCase,
)
from app.modules.document.application.use_cases.index_vectors import (
    IndexVectorsUseCase,
)
from app.modules.document.application.use_cases.get_document import (
    GetDocumentUseCase,
)
from app.modules.document.application.use_cases.get_chunk_statistics import (
    GetDocumentChunkStatisticsUseCase,
)
from app.modules.document.application.use_cases.get_knowledge_base_statistics import (
    GetKnowledgeBaseStatisticsUseCase,
)
from app.modules.document.application.use_cases.get_pipeline_state import (
    GetDocumentPipelineStateUseCase,
)
from app.modules.document.application.use_cases.list_artifacts import (
    ListDocumentArtifactsUseCase,
)
from app.modules.document.application.use_cases.list_child_chunks import (
    ListChildChunksUseCase,
)
from app.modules.document.application.use_cases.list_documents import (
    ListDocumentsUseCase,
)
from app.modules.document.application.use_cases.list_parent_blocks import (
    ListParentBlocksUseCase,
)
from app.modules.document.application.use_cases.process_document import (
    ProcessDocumentUseCase,
)
from app.modules.document.application.use_cases.search_artifacts import (
    SearchDocumentArtifactsUseCase,
)
from app.modules.document.application.use_cases.search_documents import (
    SearchDocumentsUseCase,
)
from app.modules.document.application.use_cases.upload_document import (
    UploadDocumentUseCase,
)
from app.modules.document.infrastructure.chunking.factory import get_chunker
from app.modules.document.infrastructure.embedding.dashscope import (
    EmbeddingService,
)
from app.modules.document.infrastructure.parsing.docling_client import (
    DoclingClient,
)
from app.modules.document.infrastructure.parsing.factory import get_processor
from app.modules.document.infrastructure.persistence.models.child_chunk import (
    ChildChunk,
)
from app.modules.document.infrastructure.persistence.models.document import (
    Document,
)
from app.modules.document.infrastructure.persistence.models.parent_block import (
    ParentBlock,
)
from app.modules.document.infrastructure.storage.local import (
    calculate_file_hash,
    cleanup_file,
    get_safe_extension,
    validate_content_type,
)
from app.modules.document.infrastructure.vector_store.qdrant import (
    QdrantVectorStore,
)


async def build_container() -> AppContainer:
    """创建外部客户端并装配应用级共享对象。"""
    redis_client = create_redis_client(
        REDIS_URL,
        socket_connect_timeout_seconds=(
            REDIS_SOCKET_CONNECT_TIMEOUT_SECONDS
        ),
        socket_timeout_seconds=REDIS_SOCKET_TIMEOUT_SECONDS,
    )
    deepseek_provider = None

    try:
        if not await ping_redis_client(redis_client):
            raise RuntimeError("Redis PING 未返回成功")

        route_lock_manager = ConversationRouteLockManager(
            redis_client,
            lock_timeout_seconds=CONTEXT_ROUTE_LOCK_TIMEOUT_SECONDS,
            blocking_timeout_seconds=(
                CONTEXT_ROUTE_LOCK_BLOCKING_TIMEOUT_SECONDS
            ),
        )
        queue_repository = ContextResourceQueueRepository(
            redis_client,
            capacity=CONTEXT_RESOURCE_QUEUE_MAX_SIZE,
        )
        record_factory = SQLAlchemyContextRecordFactory()
        resource_service = ContextResourceService(
            queue_repository=queue_repository,
            uow_factory=SQLAlchemyUnitOfWork,
            record_factory=record_factory,
        )
        deepseek_provider = (
            DeepSeekModelProvider.create()
            if DEEPSEEK_API_KEY is not None
            else None
        )
        agent_router = (
            DeepSeekContextRouter(deepseek_provider)
            if deepseek_provider is not None
            else None
        )
        context_service = ContextService(
            agent_router=agent_router,
            route_lock_manager=route_lock_manager,
            resource_service=resource_service,
            uow_factory=SQLAlchemyUnitOfWork,
            record_factory=record_factory,
            chain_mapper=build_context_chain,
        )
        document_ports = DocumentApplicationPorts(
            uow_factory=SQLAlchemyUnitOfWork,
            document_factory=Document,
            parent_block_factory=ParentBlock,
            child_chunk_factory=ChildChunk,
            processor_factory=get_processor,
            chunker_factory=get_chunker,
            embedding_factory=EmbeddingService,
            vector_store_factory=QdrantVectorStore,
            docling_factory=DoclingClient,
            point_factory=PointStruct,
            validate_content_type=validate_content_type,
            get_safe_extension=get_safe_extension,
            calculate_file_hash=calculate_file_hash,
            cleanup_file=cleanup_file,
            integrity_error_type=IntegrityError,
        )
        upload_document = UploadDocumentUseCase(
            ports=document_ports,
            settings=DocumentUploadSettings(
                raw_local_storage_dir=RAW_LOCAL_STORAGE_DIR,
                raw_external_storage_dir=RAW_EXTERNAL_STORAGE_DIR,
                max_upload_file_size=MAX_UPLOAD_FILE_SIZE,
                default_document_status=DEFAULT_DOCUMENT_STATUS,
                default_document_version=DEFAULT_DOCUMENT_VERSION,
                default_created_by_actor_code=(
                    DEFAULT_CREATED_BY_ACTOR_CODE
                ),
                document_code_prefix=DOCUMENT_CODE_PREFIX,
                document_code_random_length=(
                    DOCUMENT_CODE_RANDOM_LENGTH
                ),
            ),
        )
        process_document = ProcessDocumentUseCase(
            ports=document_ports,
            settings=DocumentProcessingSettings(
                cleaned_storage_dir=CLEANED_STORAGE_DIR,
                secondary_text_storage_dir=(
                    SECONDARY_TEXT_STORAGE_DIR
                ),
            ),
        )
        build_chunks = BuildChunksUseCase(ports=document_ports)
        get_document = GetDocumentUseCase(
            uow_factory=SQLAlchemyUnitOfWork
        )
        list_documents = ListDocumentsUseCase(
            uow_factory=SQLAlchemyUnitOfWork
        )
        search_documents = SearchDocumentsUseCase(
            uow_factory=SQLAlchemyUnitOfWork
        )
        get_document_pipeline_state = GetDocumentPipelineStateUseCase(
            uow_factory=SQLAlchemyUnitOfWork
        )
        list_document_artifacts = ListDocumentArtifactsUseCase(
            uow_factory=SQLAlchemyUnitOfWork
        )
        search_document_artifacts = SearchDocumentArtifactsUseCase(
            uow_factory=SQLAlchemyUnitOfWork
        )
        list_parent_blocks = ListParentBlocksUseCase(
            uow_factory=SQLAlchemyUnitOfWork
        )
        list_child_chunks = ListChildChunksUseCase(
            uow_factory=SQLAlchemyUnitOfWork
        )
        get_document_chunk_statistics = (
            GetDocumentChunkStatisticsUseCase(
                uow_factory=SQLAlchemyUnitOfWork
            )
        )
        get_knowledge_base_statistics = (
            GetKnowledgeBaseStatisticsUseCase(
                uow_factory=SQLAlchemyUnitOfWork
            )
        )
        index_vectors = IndexVectorsUseCase(
            ports=document_ports,
            settings=DocumentIndexingSettings(
                embedding_batch_size=EMBEDDING_BATCH_SIZE,
                embedding_model_name=EMBEDDING_MODEL_NAME,
                embedding_vector_size=EMBEDDING_VECTOR_SIZE,
            ),
        )
        return AppContainer(
            redis_client=redis_client,
            deepseek_provider=deepseek_provider,
            context_agent_router=agent_router,
            context_route_lock_manager=route_lock_manager,
            context_resource_service=resource_service,
            context_service=context_service,
            upload_document=upload_document,
            get_document=get_document,
            list_documents=list_documents,
            search_documents=search_documents,
            get_document_pipeline_state=get_document_pipeline_state,
            list_document_artifacts=list_document_artifacts,
            search_document_artifacts=search_document_artifacts,
            list_parent_blocks=list_parent_blocks,
            list_child_chunks=list_child_chunks,
            get_document_chunk_statistics=get_document_chunk_statistics,
            get_knowledge_base_statistics=get_knowledge_base_statistics,
            process_document=process_document,
            build_chunks=build_chunks,
            index_vectors=index_vectors,
        )
    except Exception:
        try:
            if deepseek_provider is not None:
                await deepseek_provider.aclose()
        finally:
            await close_redis_client(redis_client)
        raise


@asynccontextmanager
async def lifespan(app: FastAPI):
    """创建统一容器，并在应用退出时释放其中的外部客户端。"""
    container = await build_container()
    app.state.container = container

    try:
        yield
    finally:
        await container.aclose()
