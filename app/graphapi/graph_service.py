"""
知识图谱服务类，提供对OpenSPG知识图谱的直接访问
"""

import json
import logging
from typing import Dict, List, Any, Optional, Tuple

from knext.client.graph_client import GraphClient
from knext.project.client import ProjectClient
from kag.common.conf import KAGConstants

logger = logging.getLogger(__name__)


class GraphService:
    """
    知识图谱服务类
    提供对OpenSPG知识图谱的直接访问功能
    """

    def __init__(self, service_url: str):
        """
        初始化知识图谱服务

        Args:
            service_url: OpenSPG服务地址
        """
        self.service_url = service_url
        self.project_client = ProjectClient(host_addr=service_url, project_id=-1)

        # 加载所有项目
        logger.info("Loading projects from OpenSPG service")
        self.project_list = self.project_client.get_all()
        logger.info(f"Loaded {len(self.project_list)} projects")
        for project_name, project_id in self.project_list.items():
            logger.info(f"  - {project_name}: {project_id}")

        # 项目ID到GraphClient的映射
        self.graph_clients: Dict[str, GraphClient] = {}

    def get_projects(self) -> Dict[str, str]:
        """
        获取所有可用的项目

        Returns:
            Dict[str, str]: 项目名称到项目ID的映射
        """
        return self.project_list

    def get_graph_client(self, project_name_or_id: str) -> Optional[GraphClient]:
        """
        获取指定项目的图客户端

        Args:
            project_name_or_id: 项目名称或ID

        Returns:
            Optional[GraphClient]: 图客户端实例，如果项目不存在则返回None
        """
        # 先检查是否已缓存
        if project_name_or_id in self.graph_clients:
            return self.graph_clients[project_name_or_id]

        # 如果是项目名，则转换为项目ID
        project_id = project_name_or_id
        if project_name_or_id in self.project_list:
            project_id = self.project_list[project_name_or_id]

        # 获取项目配置
        project = self.project_client.get_by_id(project_id)
        if not project:
            logger.warning(f"Project {project_name_or_id} not found")
            return None

        # 创建图客户端
        try:
            client = GraphClient(host_addr=self.service_url, project_id=project_id)
            self.graph_clients[project_name_or_id] = client
            return client
        except Exception as e:
            logger.error(
                f"Error creating GraphClient for project {project_name_or_id}: {e}"
            )
            return None

    def get_schema(self, project_name_or_id: str) -> Dict[str, Any]:
        """
        获取知识图谱的Schema

        Args:
            project_name_or_id: 项目名称或ID

        Returns:
            Dict[str, Any]: Schema定义，如果项目不存在则返回空字典
        """
        client = self.get_graph_client(project_name_or_id)
        if not client:
            return {}

        try:
            schema = client.get_schema()
            return schema or {}
        except Exception as e:
            logger.error(f"Error getting schema for project {project_name_or_id}: {e}")
            return {}

    def get_entity_types(self, project_name_or_id: str) -> List[str]:
        """
        获取所有实体类型

        Args:
            project_name_or_id: 项目名称或ID

        Returns:
            List[str]: 实体类型列表
        """
        schema = self.get_schema(project_name_or_id)
        if not schema:
            return []

        entity_types = []
        for type_def in schema.get("types", []):
            if type_def.get("category") == "ENTITY_TYPE":
                entity_types.append(type_def.get("name"))

        return entity_types

    def get_concept_types(self, project_name_or_id: str) -> List[str]:
        """
        获取所有概念类型

        Args:
            project_name_or_id: 项目名称或ID

        Returns:
            List[str]: 概念类型列表
        """
        schema = self.get_schema(project_name_or_id)
        if not schema:
            return []

        concept_types = []
        for type_def in schema.get("types", []):
            if type_def.get("category") == "CONCEPT_TYPE":
                concept_types.append(type_def.get("name"))

        return concept_types

    def get_relation_types(self, project_name_or_id: str) -> List[str]:
        """
        获取所有关系类型

        Args:
            project_name_or_id: 项目名称或ID

        Returns:
            List[str]: 关系类型列表
        """
        schema = self.get_schema(project_name_or_id)
        if not schema:
            return []

        relation_types = []
        for type_def in schema.get("types", []):
            if type_def.get("category") == "RELATION_TYPE":
                relation_types.append(type_def.get("name"))

        return relation_types

    def get_entities(
        self,
        project_name_or_id: str,
        entity_type: str,
        limit: int = 100,
        offset: int = 0,
    ) -> List[Dict[str, Any]]:
        """
        获取指定类型的实体

        Args:
            project_name_or_id: 项目名称或ID
            entity_type: 实体类型
            limit: 最大返回数量
            offset: 偏移量

        Returns:
            List[Dict[str, Any]]: 实体列表
        """
        client = self.get_graph_client(project_name_or_id)
        if not client:
            return []

        try:
            # 构建SPG DSL查询
            query = f"""
            MATCH (e:{entity_type})
            RETURN e
            LIMIT {limit}
            OFFSET {offset}
            """

            # 执行查询
            result = client.execute_spg_dsl(query)

            # 解析结果
            entities = []
            for record in result.get("records", []):
                if "e" in record:
                    entities.append(record["e"])

            return entities
        except Exception as e:
            logger.error(
                f"Error getting entities for project {project_name_or_id}, type {entity_type}: {e}"
            )
            return []

    def search_entities(
        self, project_name_or_id: str, keyword: str, limit: int = 100
    ) -> List[Dict[str, Any]]:
        """
        搜索实体

        Args:
            project_name_or_id: 项目名称或ID
            keyword: 搜索关键词
            limit: 最大返回数量

        Returns:
            List[Dict[str, Any]]: 符合搜索条件的实体列表
        """
        client = self.get_graph_client(project_name_or_id)
        if not client:
            return []

        try:
            # 使用通用搜索接口
            result = client.search(keyword, limit=limit)
            return result or []
        except Exception as e:
            logger.error(
                f"Error searching entities for project {project_name_or_id}, keyword {keyword}: {e}"
            )
            return []

    def get_entity_relations(
        self, project_name_or_id: str, entity_id: str, direction: str = "BOTH"
    ) -> List[Dict[str, Any]]:
        """
        获取实体的关系

        Args:
            project_name_or_id: 项目名称或ID
            entity_id: 实体ID
            direction: 关系方向，可选值为"OUTGOING", "INCOMING", "BOTH"

        Returns:
            List[Dict[str, Any]]: 关系列表
        """
        client = self.get_graph_client(project_name_or_id)
        if not client:
            return []

        try:
            # 构建查询
            if direction == "OUTGOING":
                query = f"""
                MATCH (s)-[r]->(o)
                WHERE id(s) = "{entity_id}"
                RETURN s, r, o
                """
            elif direction == "INCOMING":
                query = f"""
                MATCH (s)-[r]->(o)
                WHERE id(o) = "{entity_id}"
                RETURN s, r, o
                """
            else:  # BOTH
                query = f"""
                MATCH (s)-[r]->(o)
                WHERE id(s) = "{entity_id}" OR id(o) = "{entity_id}"
                RETURN s, r, o
                """

            # 执行查询
            result = client.execute_spg_dsl(query)

            # 解析结果
            relations = []
            for record in result.get("records", []):
                if "r" in record:
                    relation = {
                        "relation": record["r"],
                        "source": record.get("s", {}),
                        "target": record.get("o", {}),
                    }
                    relations.append(relation)

            return relations
        except Exception as e:
            logger.error(
                f"Error getting relations for entity {entity_id} in project {project_name_or_id}: {e}"
            )
            return []

    def execute_query(self, project_name_or_id: str, query: str) -> Dict[str, Any]:
        """
        执行自定义SPG DSL查询

        Args:
            project_name_or_id: 项目名称或ID
            query: SPG DSL查询语句

        Returns:
            Dict[str, Any]: 查询结果
        """
        client = self.get_graph_client(project_name_or_id)
        if not client:
            return {"error": f"Project {project_name_or_id} not found"}

        try:
            result = client.execute_spg_dsl(query)
            return result or {}
        except Exception as e:
            logger.error(f"Error executing query for project {project_name_or_id}: {e}")
            return {"error": str(e)}


# 全局服务实例
graph_service = None


def get_graph_service(service_url: str) -> GraphService:
    """
    获取或创建全局图服务实例

    Args:
        service_url: OpenSPG服务地址

    Returns:
        GraphService: 图服务实例
    """
    global graph_service
    if graph_service is None:
        graph_service = GraphService(service_url=service_url)
    return graph_service
