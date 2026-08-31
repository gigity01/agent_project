"""FastAPI 应用入口模块。"""

import uvicorn

from app.bootstrap.app_factory import create_app

app = create_app()


def main() -> None:
    """从项目根目录启动本地 Uvicorn 开发服务器。"""
    uvicorn.run(
        "app.main:app",
        host="127.0.0.1",
        port=8000,
        reload=True,
    )


if __name__ == "__main__":
    main()
