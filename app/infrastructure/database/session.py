"""SQLAlchemy 引擎、会话工厂与数据库会话依赖。"""

from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

from app.config.settings import SQLALCHEMY_DATABASE_URL
from app.infrastructure.database.base import Base

engine = create_engine(
    SQLALCHEMY_DATABASE_URL,
    pool_size=10,
    pool_pre_ping=True,
    pool_recycle=3600,
    echo=False,

)
session_local = sessionmaker(
    bind=engine,
    autocommit=False,
    autoflush=False,
    expire_on_commit=False,
)

def get_db():
    """按请求提供数据库会话，并在请求结束时确保关闭。"""
    db = session_local()
    try:
        yield db
    finally:
        db.close()
