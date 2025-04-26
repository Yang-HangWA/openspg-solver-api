"""
知识图谱API接口
提供REST API来访问知识图谱数据
"""

import logging
from typing import Dict, List, Any, Optional

from fastapi import APIRouter, Depends, Query, Path, HTTPException
from pydantic import BaseModel, Field

from app.graphapi.graph_service import get_graph_service
from app.utils import get_open_spg_address

router = APIRouter()
logger = logging.getLogger(__name__)


class GraphInfo(BaseModel):
    """知识图谱基本信息"""

    name: str
    id: str
    description: Optional[str] = None


class GraphSchema(BaseModel):
    """知识图谱Schema信息"""

    types: List[Dict[str, Any]] = Field(default_factory=list)
    properties: List[Dict[str, Any]] = Field(default_factory=list)


class EntityListResponse(BaseModel):
    """实体列表响应"""

    entities: List[Dict[str, Any]] = Field(default_factory=list)
    total: int = 0
    page: int = 1
    page_size: int = 100


class RelationListResponse(BaseModel):
    """关系列表响应"""

    relations: List[Dict[str, Any]] = Field(default_factory=list)
    total: int = 0


class SearchResponse(BaseModel):
    """搜索响应"""

    results: List[Dict[str, Any]] = Field(default_factory=list)
    total: int = 0


class QueryRequest(BaseModel):
    """SPG DSL查询请求"""

    query: str = Field(..., description="SPG DSL查询语句")


class QueryResponse(BaseModel):
    """查询响应"""

    records: List[Dict[str, Any]] = Field(default_factory=list)
    columns: List[str] = Field(default_factory=list)


@router.get("/graphs", response_model=List[GraphInfo], tags=["Knowledge Graph"])
async def list_graphs(
    openspg_service: str = Depends(get_open_spg_address),
):
    """
    获取所有可用的知识图谱列表
    """
    graph_service = get_graph_service(openspg_service)
    projects = graph_service.get_projects()

    result = []
    for name, id in projects.items():
        result.append(GraphInfo(name=name, id=id))

    return result


@router.get(
    "/graphs/{graph_id}/schema", response_model=GraphSchema, tags=["Knowledge Graph"]
)
async def get_graph_schema(
    graph_id: str = Path(..., description="知识图谱ID或名称"),
    openspg_service: str = Depends(get_open_spg_address),
):
    """
    获取指定知识图谱的Schema信息
    """
    graph_service = get_graph_service(openspg_service)
    schema = graph_service.get_schema(graph_id)

    if not schema:
        raise HTTPException(
            status_code=404, detail=f"Graph {graph_id} not found or has no schema"
        )

    return GraphSchema(**schema)


@router.get(
    "/graphs/{graph_id}/entity-types",
    response_model=List[str],
    tags=["Knowledge Graph"],
)
async def get_entity_types(
    graph_id: str = Path(..., description="知识图谱ID或名称"),
    openspg_service: str = Depends(get_open_spg_address),
):
    """
    获取指定知识图谱的所有实体类型
    """
    graph_service = get_graph_service(openspg_service)
    types = graph_service.get_entity_types(graph_id)

    return types


@router.get(
    "/graphs/{graph_id}/concept-types",
    response_model=List[str],
    tags=["Knowledge Graph"],
)
async def get_concept_types(
    graph_id: str = Path(..., description="知识图谱ID或名称"),
    openspg_service: str = Depends(get_open_spg_address),
):
    """
    获取指定知识图谱的所有概念类型
    """
    graph_service = get_graph_service(openspg_service)
    types = graph_service.get_concept_types(graph_id)

    return types


@router.get(
    "/graphs/{graph_id}/relation-types",
    response_model=List[str],
    tags=["Knowledge Graph"],
)
async def get_relation_types(
    graph_id: str = Path(..., description="知识图谱ID或名称"),
    openspg_service: str = Depends(get_open_spg_address),
):
    """
    获取指定知识图谱的所有关系类型
    """
    graph_service = get_graph_service(openspg_service)
    types = graph_service.get_relation_types(graph_id)

    return types


@router.get(
    "/graphs/{graph_id}/entities",
    response_model=EntityListResponse,
    tags=["Knowledge Graph"],
)
async def get_entities(
    graph_id: str = Path(..., description="知识图谱ID或名称"),
    entity_type: str = Query(..., description="实体类型"),
    limit: int = Query(100, description="最大返回数量"),
    offset: int = Query(0, description="偏移量"),
    openspg_service: str = Depends(get_open_spg_address),
):
    """
    获取指定类型的实体列表
    """
    graph_service = get_graph_service(openspg_service)
    entities = graph_service.get_entities(graph_id, entity_type, limit, offset)

    return EntityListResponse(
        entities=entities,
        total=len(entities),  # 实际场景中应该返回总数
        page=(offset // limit) + 1,
        page_size=limit,
    )


@router.get(
    "/graphs/{graph_id}/search", response_model=SearchResponse, tags=["Knowledge Graph"]
)
async def search_entities(
    graph_id: str = Path(..., description="知识图谱ID或名称"),
    keyword: str = Query(..., description="搜索关键词"),
    limit: int = Query(100, description="最大返回数量"),
    openspg_service: str = Depends(get_open_spg_address),
):
    """
    搜索实体
    """
    graph_service = get_graph_service(openspg_service)
    results = graph_service.search_entities(graph_id, keyword, limit)

    return SearchResponse(results=results, total=len(results))


@router.get(
    "/graphs/{graph_id}/entities/{entity_id}/relations",
    response_model=RelationListResponse,
    tags=["Knowledge Graph"],
)
async def get_entity_relations(
    graph_id: str = Path(..., description="知识图谱ID或名称"),
    entity_id: str = Path(..., description="实体ID"),
    direction: str = Query(
        "BOTH", description="关系方向，可选值为OUTGOING/INCOMING/BOTH"
    ),
    openspg_service: str = Depends(get_open_spg_address),
):
    """
    获取实体的关系
    """
    graph_service = get_graph_service(openspg_service)
    relations = graph_service.get_entity_relations(graph_id, entity_id, direction)

    return RelationListResponse(relations=relations, total=len(relations))


@router.post(
    "/graphs/{graph_id}/query", response_model=QueryResponse, tags=["Knowledge Graph"]
)
async def execute_query(
    graph_id: str = Path(..., description="知识图谱ID或名称"),
    openspg_service: str = Depends(get_open_spg_address),
    query_request: QueryRequest = None,
):
    """
    执行自定义SPG DSL查询
    """
    graph_service = get_graph_service(openspg_service)
    result = graph_service.execute_query(graph_id, query_request.query)

    if "error" in result:
        raise HTTPException(status_code=400, detail=result["error"])

    return QueryResponse(
        records=result.get("records", []), columns=result.get("columns", [])
    )


def mount_routes(app, args):
    """
    挂载知识图谱API路由

    Args:
        app: FastAPI应用实例
        args: 命令行参数
    """
    prefix = f"{args.servlet}/graph"

    # 注册路由
    app.include_router(router, prefix=prefix)

    logger.info(f"Mounted graph API routes at {prefix}")
    return app
