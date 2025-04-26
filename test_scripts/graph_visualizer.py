#!/usr/bin/env python
"""
知识图谱可视化工具

用于获取知识图谱数据并进行本地可视化显示
"""

import argparse
import json
import sys
import requests
import networkx as nx
import matplotlib.pyplot as plt
from typing import Dict, List, Any


class GraphVisualizer:
    """知识图谱可视化工具"""

    def __init__(self, base_url: str):
        """
        初始化可视化工具

        Args:
            base_url: API服务基础URL，如 http://localhost:8000/api/v1/graph
        """
        self.base_url = base_url
        self.session = requests.Session()

    def get_available_graphs(self) -> List[Dict[str, Any]]:
        """获取所有可用的知识图谱"""
        response = self.session.get(f"{self.base_url}/graphs")
        response.raise_for_status()
        return response.json()

    def get_entity_types(self, graph_id: str) -> List[str]:
        """获取图谱中的实体类型"""
        response = self.session.get(f"{self.base_url}/graphs/{graph_id}/entity-types")
        response.raise_for_status()
        return response.json()

    def get_entities(
        self, graph_id: str, entity_type: str, limit: int = 100
    ) -> List[Dict[str, Any]]:
        """获取特定类型的实体"""
        response = self.session.get(
            f"{self.base_url}/graphs/{graph_id}/entities",
            params={"entity_type": entity_type, "limit": limit, "offset": 0},
        )
        response.raise_for_status()
        return response.json().get("entities", [])

    def get_entity_relations(
        self, graph_id: str, entity_id: str
    ) -> List[Dict[str, Any]]:
        """获取实体的关系"""
        response = self.session.get(
            f"{self.base_url}/graphs/{graph_id}/entities/{entity_id}/relations",
            params={"direction": "BOTH"},
        )
        response.raise_for_status()
        return response.json().get("relations", [])

    def execute_query(self, graph_id: str, query: str) -> Dict[str, Any]:
        """执行SPG DSL查询"""
        response = self.session.post(
            f"{self.base_url}/graphs/{graph_id}/query", json={"query": query}
        )
        response.raise_for_status()
        return response.json()

    def visualize_entity_network(
        self, graph_id: str, entity_type: str, limit: int = 20, depth: int = 1
    ):
        """
        可视化实体网络

        Args:
            graph_id: 知识图谱ID
            entity_type: 实体类型
            limit: 最大实体数量
            depth: 探索深度
        """
        # 获取实体
        print(f"获取{entity_type}类型的实体...")
        entities = self.get_entities(graph_id, entity_type, limit)

        if not entities:
            print(f"未找到{entity_type}类型的实体")
            return

        print(f"找到{len(entities)}个实体")

        # 创建NetworkX图
        G = nx.Graph()

        # 已处理的实体ID
        processed_ids = set()

        # 递归获取实体及其关系
        self._add_entities_with_relations(G, graph_id, entities, processed_ids, depth)

        # 可视化图形
        self._draw_graph(G, f"{entity_type}实体关系网络")

    def _add_entities_with_relations(
        self, G, graph_id, entities, processed_ids, depth, current_depth=0
    ):
        """递归添加实体及其关系到图中"""
        if current_depth >= depth:
            return

        for entity in entities:
            entity_id = entity.get("id")
            if not entity_id or entity_id in processed_ids:
                continue

            # 添加实体节点
            name = entity.get("name", entity_id)
            entity_type = entity.get("type", "Unknown")
            G.add_node(entity_id, name=name, type=entity_type)
            processed_ids.add(entity_id)

            # 获取关系
            relations = self.get_entity_relations(graph_id, entity_id)
            print(f"实体 {name} 有 {len(relations)} 个关系")

            related_entities = []
            for relation in relations:
                rel = relation.get("relation", {})
                source = relation.get("source", {})
                target = relation.get("target", {})

                source_id = source.get("id")
                target_id = target.get("id")

                if not source_id or not target_id:
                    continue

                # 添加关系边
                if source_id == entity_id:
                    other_entity = target
                    G.add_node(
                        target_id,
                        name=target.get("name", target_id),
                        type=target.get("type", "Unknown"),
                    )
                    G.add_edge(source_id, target_id, type=rel.get("type", "Unknown"))
                    related_entities.append(target)
                else:
                    other_entity = source
                    G.add_node(
                        source_id,
                        name=source.get("name", source_id),
                        type=source.get("type", "Unknown"),
                    )
                    G.add_edge(source_id, target_id, type=rel.get("type", "Unknown"))
                    related_entities.append(source)

            # 递归处理相关实体
            if related_entities and current_depth + 1 < depth:
                self._add_entities_with_relations(
                    G,
                    graph_id,
                    related_entities,
                    processed_ids,
                    depth,
                    current_depth + 1,
                )

    def _draw_graph(self, G, title):
        """绘制图形"""
        # 检查图的大小
        num_nodes = G.number_of_nodes()
        num_edges = G.number_of_edges()
        print(f"绘制图形，包含 {num_nodes} 个节点和 {num_edges} 条边")

        if num_nodes == 0:
            print("图中没有节点，无法绘制")
            return

        # 设置图形大小
        plt.figure(figsize=(12, 10))

        # 根据节点数量选择不同的布局算法
        if num_nodes <= 50:
            pos = nx.spring_layout(G, seed=42)  # 小图使用弹簧布局
        else:
            pos = nx.kamada_kawai_layout(G)  # 大图使用Kamada-Kawai布局

        # 获取节点类型
        node_types = {
            node: data.get("type", "Unknown") for node, data in G.nodes(data=True)
        }
        unique_types = set(node_types.values())

        # 为每种类型分配不同的颜色
        color_map = {}
        colors = plt.cm.tab10.colors
        for i, t in enumerate(unique_types):
            color_map[t] = colors[i % len(colors)]

        # 绘制节点
        for node_type in unique_types:
            nodes = [
                node
                for node, data in G.nodes(data=True)
                if data.get("type") == node_type
            ]
            nx.draw_networkx_nodes(
                G,
                pos,
                nodelist=nodes,
                node_color=[color_map[node_type]] * len(nodes),
                node_size=300,
                alpha=0.8,
                label=node_type,
            )

        # 绘制边
        nx.draw_networkx_edges(G, pos, alpha=0.5)

        # 绘制标签
        labels = {node: data.get("name", node) for node, data in G.nodes(data=True)}
        nx.draw_networkx_labels(G, pos, labels, font_size=8, font_family="sans-serif")

        plt.title(title)
        plt.legend()
        plt.axis("off")
        plt.tight_layout()

        # 保存图形
        output_file = f"{title.replace(' ', '_')}.png"
        plt.savefig(output_file, dpi=300)
        print(f"图形已保存至 {output_file}")

        # 显示图形
        plt.show()

    def visualize_custom_query(
        self, graph_id: str, query: str, title: str = "自定义查询结果"
    ):
        """
        通过自定义查询可视化图形

        Args:
            graph_id: 知识图谱ID
            query: SPG DSL查询语句
            title: 图形标题
        """
        # 执行查询
        print("执行查询...")
        result = self.execute_query(graph_id, query)

        records = result.get("records", [])
        if not records:
            print("查询没有返回结果")
            return

        print(f"查询返回了 {len(records)} 条记录")

        # 创建NetworkX图
        G = nx.Graph()

        # 处理查询结果
        for record in records:
            # 查找记录中的实体和关系
            entities = {}
            relation = None

            for key, value in record.items():
                if isinstance(value, dict) and "id" in value:
                    # 这是一个实体
                    entities[key] = value
                elif (
                    isinstance(value, dict)
                    and "type" in value
                    and "properties" in value
                ):
                    # 这可能是一个关系
                    relation = value

            # 添加实体节点
            for key, entity in entities.items():
                entity_id = entity.get("id")
                name = entity.get("name", entity_id)
                entity_type = entity.get("type", "Unknown")
                G.add_node(entity_id, name=name, type=entity_type)

            # 如果有关系，添加边
            if relation and len(entities) >= 2:
                # 找出源和目标
                entity_ids = [entity.get("id") for entity in entities.values()]
                if len(entity_ids) >= 2:
                    G.add_edge(
                        entity_ids[0],
                        entity_ids[1],
                        type=relation.get("type", "Unknown"),
                    )

        # 可视化图形
        self._draw_graph(G, title)


def main():
    """主函数"""
    parser = argparse.ArgumentParser(description="知识图谱可视化工具")
    parser.add_argument(
        "--url",
        type=str,
        required=True,
        help="API服务基础URL，例如：http://localhost:8000/api/v1/graph",
    )
    parser.add_argument("--graph-id", type=str, required=True, help="知识图谱ID或名称")
    parser.add_argument(
        "--mode",
        type=str,
        choices=["entity", "query"],
        default="entity",
        help="可视化模式：entity或query",
    )
    parser.add_argument(
        "--entity-type", type=str, help="实体类型（当mode=entity时必须）"
    )
    parser.add_argument(
        "--query", type=str, help="SPG DSL查询语句（当mode=query时必须）"
    )
    parser.add_argument(
        "--limit", type=int, default=20, help="实体数量限制（仅对entity模式有效）"
    )
    parser.add_argument(
        "--depth", type=int, default=1, help="关系探索深度（仅对entity模式有效）"
    )
    parser.add_argument(
        "--list-graphs", action="store_true", help="列出所有可用的知识图谱"
    )
    parser.add_argument(
        "--list-types", action="store_true", help="列出指定图谱中的实体类型"
    )

    args = parser.parse_args()

    visualizer = GraphVisualizer(args.url)

    try:
        if args.list_graphs:
            graphs = visualizer.get_available_graphs()
            print("可用的知识图谱:")
            for graph in graphs:
                print(f"  名称: {graph['name']}, ID: {graph['id']}")
            return

        if args.list_types and args.graph_id:
            types = visualizer.get_entity_types(args.graph_id)
            print(f"知识图谱 {args.graph_id} 中的实体类型:")
            for t in types:
                print(f"  {t}")
            return

        if args.mode == "entity":
            if not args.entity_type:
                print("错误：entity模式下必须指定--entity-type参数")
                return
            visualizer.visualize_entity_network(
                args.graph_id, args.entity_type, args.limit, args.depth
            )
        elif args.mode == "query":
            if not args.query:
                print("错误：query模式下必须指定--query参数")
                return
            visualizer.visualize_custom_query(args.graph_id, args.query)

    except requests.RequestException as e:
        print(f"API请求错误: {e}")
    except Exception as e:
        print(f"错误: {e}")


if __name__ == "__main__":
    main()
