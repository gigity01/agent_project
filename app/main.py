"""FastAPI 应用入口。"""

from app.bootstrap.app_factory import create_app


app = create_app()
