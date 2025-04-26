from fastapi import FastAPI, Request
from fastapi.responses import JSONResponse
import traceback
import logging

from app.routes.app_routes import mount_routes as mount_app_routes
from app.openspg.api.openai_api import mount_routes as mount_openai_routes
from app.graphapi.graph_api import mount_routes as mount_graph_routes

logger = logging.getLogger()


async def global_exception_handler(request: Request, exc: Exception):
    """全局异常处理器，确保API错误被正确处理和记录"""
    error_msg = f"Global exception: {str(exc)}"
    logger.error(error_msg)
    logger.error(traceback.format_exc())

    # 返回结构化的错误响应
    return JSONResponse(
        status_code=500,
        content={
            "error": {
                "message": str(exc),
                "type": exc.__class__.__name__,
                "param": None,
                "code": "server_error",
            }
        },
    )


def mount_all_routes(app: FastAPI, args):
    """
    Mount all routes in this package to the provided application.
    """
    # 设置全局异常处理器
    app.add_exception_handler(Exception, global_exception_handler)

    mount_app_routes(app, args)
    mount_openai_routes(app, args)
    mount_graph_routes(app, args)

    return app
