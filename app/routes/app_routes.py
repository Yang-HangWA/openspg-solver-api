from pathlib import Path
import os
import logging
import json
from typing import Dict, Any, List, Optional

from fastapi import FastAPI, Depends, Body, HTTPException
from fastapi.openapi.docs import get_swagger_ui_html
from starlette.responses import JSONResponse, RedirectResponse, HTMLResponse
from starlette.staticfiles import StaticFiles
from pydantic import BaseModel

from app.openspg.service.kag_service import get_kag_service

logger = logging.getLogger()


class ConfigValidationResponse(BaseModel):
    status: str
    message: str
    details: Optional[Dict[str, Any]] = None


class HealthResponse(BaseModel):
    status: str
    version: str
    projects: List[str]


def mount_routes(app: FastAPI, args):
    """
    mount global routes
    :param app:
    :param args:
    :return:
    """

    api_prefix = f"{args.servlet}"

    # static files
    app.mount(f"{api_prefix}/static", StaticFiles(directory=Path("static").as_posix()))

    # redirect to swagger
    @app.get("/", include_in_schema=False)
    async def redirect_swagger_document():
        return RedirectResponse(url=f"{api_prefix}/docs")

    # swagger documentation
    @app.get(f"{api_prefix}/docs", include_in_schema=False)
    async def swagger_ui_html() -> HTMLResponse:
        return get_swagger_ui_html(
            openapi_url=f"{app.openapi_url}",
            title=app.title + " - Swagger UI",
            oauth2_redirect_url=app.swagger_ui_oauth2_redirect_url,
            swagger_js_url=f"{api_prefix}/static/swagger-ui-bundle.js",
            swagger_css_url=f"{api_prefix}/static/swagger-ui.css",
            swagger_favicon_url=f"{api_prefix}/static/favicon.png",
        )

    @app.get(
        "/",
        summary="API Root",
    )
    def index():
        return {
            "title": args.desc,
            "docs_url": f"{args.servlet}/docs",
            "openapi_url": f"{args.servlet}/openapi.json",
        }

    @app.get(
        f"{args.servlet}/health",
        response_model=HealthResponse,
        summary="Health Check",
        description="Returns health status and basic information about the API",
    )
    def health_check():
        """健康检查API，返回基本信息和项目列表"""
        service = get_kag_service(args.openspg_service, args.openspg_modules)
        projects = service.get_projects()

        from importlib.metadata import version

        try:
            kag_version = version("openspg-kag")
        except:
            kag_version = "unknown"

        return HealthResponse(
            status="healthy", version=kag_version, projects=list(projects.keys())
        )

    @app.post(
        f"{args.servlet}/validate_config",
        response_model=ConfigValidationResponse,
        summary="Validate Project Configuration",
        description="Validates the LLM and solver configuration for a project",
    )
    def validate_config(project_name: str = Body(..., embed=True)):
        """验证项目配置是否正确，检查LLM和solver配置"""
        service = get_kag_service(args.openspg_service, args.openspg_modules)
        project_id = service.get_project_id_by_name(project_name)

        if not project_id:
            raise HTTPException(
                status_code=404, detail=f"Project '{project_name}' not found"
            )

        try:
            # 加载配置
            config = service.load_kag_config(service.service_url, project_id)

            # 检查solver_pipeline配置
            if "solver_pipeline" not in config:
                return ConfigValidationResponse(
                    status="error",
                    message="Missing solver_pipeline configuration",
                    details={"missing_key": "solver_pipeline"},
                )

            # 检查generator配置
            if "generator" not in config["solver_pipeline"]:
                return ConfigValidationResponse(
                    status="error",
                    message="Missing generator configuration in solver_pipeline",
                    details={"missing_key": "solver_pipeline.generator"},
                )

            # 检查llm_client配置
            if "llm_client" not in config["solver_pipeline"]["generator"]:
                return ConfigValidationResponse(
                    status="error",
                    message="Missing llm_client configuration in generator",
                    details={"missing_key": "solver_pipeline.generator.llm_client"},
                )

            # 获取LLM客户端配置
            llm_config = config["solver_pipeline"]["generator"]["llm_client"]

            if not isinstance(llm_config, dict):
                # 如果是引用，尝试从配置中找到实际配置
                found = False
                for key, value in config.items():
                    if (
                        isinstance(value, dict)
                        and value.get("type")
                        and "llm" in value.get("type", "")
                    ):
                        llm_config = value
                        found = True
                        break

                if not found:
                    return ConfigValidationResponse(
                        status="error",
                        message="Could not find LLM configuration",
                        details={"config": config["solver_pipeline"]["generator"]},
                    )

            # 检查LLM类型
            if "type" not in llm_config:
                return ConfigValidationResponse(
                    status="error",
                    message="Missing type in LLM configuration",
                    details={"llm_config": llm_config},
                )

            # 检查必要字段
            required_fields = []
            if "openai" in llm_config["type"]:
                required_fields = ["api_key", "base_url", "model"]
            elif "llamacpp" in llm_config["type"]:
                required_fields = ["model_path"]

            missing_fields = [
                field for field in required_fields if field not in llm_config
            ]
            if missing_fields:
                return ConfigValidationResponse(
                    status="error",
                    message=f"Missing required fields in LLM configuration: {', '.join(missing_fields)}",
                    details={
                        "missing_fields": missing_fields,
                        "llm_type": llm_config["type"],
                    },
                )

            # 配置有效
            return ConfigValidationResponse(
                status="success",
                message="Configuration is valid",
                details={
                    "llm_type": llm_config["type"],
                    "model": llm_config.get(
                        "model", llm_config.get("model_path", "unknown")
                    ),
                },
            )

        except Exception as e:
            logger.error(f"Error validating config: {str(e)}")
            return ConfigValidationResponse(
                status="error",
                message=f"Error validating configuration: {str(e)}",
                details={"exception": str(e)},
            )

    pass
