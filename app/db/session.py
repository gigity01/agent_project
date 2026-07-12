"""SQLAlchemy 引擎、会话工厂与 FastAPI 依赖注入。"""

from sqlalchemy import create_engine
from sqlalchemy.ext.declarative import declarative_base
from sqlalchemy.orm import sessionmaker

from app.app_config.settings import SQLALCHEMY_DATABASE_URL

engine = create_engine(
    SQLALCHEMY_DATABASE_URL,
    pool_size=10,
    pool_pre_ping=True,
    pool_recycle=3600,
    echo=False,

)
session_local = sessionmaker(autocommit=False, autoflush=False, bind=engine)

Base = declarative_base()


def get_db():
    """按请求提供数据库会话，并在请求结束时确保关闭。"""
    db = session_local()
    try:
        yield db
    finally:
        db.close()
