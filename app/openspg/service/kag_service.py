import asyncio
import concurrent.futures
import json
import logging
import multiprocessing
import os.path
import threading
import traceback
from abc import ABC
from multiprocessing import Process
from typing import Generator, AsyncGenerator, Optional, Any, Union

from jedi.inference.gradual.typing import Callable
from kag.common.conf import KAGConstants, KAG_CONFIG, KAG_PROJECT_CONF
from kag.common.registry import import_modules_from_path
from kag.interface import SolverPipelineABC
from kag.solver.executor.retriever.local_knowledge_base.kag_retriever.kag_hybrid_executor import (
    KAGRetrievedResponse,
)
from kag.solver.reporter.open_spg_reporter import OpenSPGReporter
from kag.solver.reporter.trace_log_reporter import TraceLog
from knext.project.client import ProjectClient
from knext.reasoner.rest.models.report_pipeline_request import ReportPipelineRequest

from app.utils import remove_empty_fields

logger = logging.getLogger()


class EventQueue(Generator, ABC):
    """
    A queue that can be used to send events to a generator.
    Stop iteration while got a 'None' event
    """

    def __init__(self):
        self.events = []
        self.lock = threading.Lock()
        self.closed = False
        self.event_available = threading.Event()

    def __next__(self):
        if self.closed and len(self.events) == 0:
            raise StopIteration

        # 等待事件可用或队列关闭
        while len(self.events) == 0 and not self.closed:
            # 设置超时防止无限等待
            self.event_available.wait(timeout=0.1)

        with self.lock:
            if len(self.events) == 0:
                if self.closed:
                    raise StopIteration
                return None

            event = self.events.pop(0)

        if event is None:
            self.close()
            raise StopIteration
        return event

    def send(self, event: any):
        with self.lock:
            if self.closed:
                logger.warning("Attempting to send event to closed queue")
                return

            self.events.append(event)
            self.event_available.set()  # 通知有新事件

        # 重置事件，以便下次等待
        if event is not None:
            self.event_available.clear()

    def close(self):
        """关闭队列，不再接受新事件"""
        with self.lock:
            self.closed = True
            self.event_available.set()  # 确保等待的线程能继续

    def throw(self, typ, val=None, tb=None):
        """处理异常，清理资源"""
        logger.error(f"Exception in event queue: {typ} {val}")
        self.close()
        pass


class EventReporter(OpenSPGReporter):
    """事件报告器，将OpenSPG的报告转换为事件流"""

    def __init__(self, callback=None, **kwargs):
        super().__init__(0, **kwargs)
        self.callback = callback
        self.events = []

    def add_report_line(self, segment, tag_name, content, status, **kwargs):
        super().add_report_line(segment, tag_name, content, status, **kwargs)

        report_data = self.report_stream_data[tag_name]

        # 创建安全的事件数据
        safe_data = remove_empty_fields({"event": "changed", "data": report_data})

        # 存储事件
        self.events.append(safe_data)

        # 如果有回调，则调用
        if self.callback:
            try:
                self.callback(safe_data)
            except Exception as e:
                logger.error(f"Error in report_line callback: {str(e)}")


def load_kag_config(host_addr, project_id):
    """
    copy those codes from kag.common.conf.load_config
    """
    project_client = ProjectClient(host_addr=host_addr, project_id=project_id)
    project = project_client.get_by_id(project_id)
    if not project:
        return {}
    config = json.loads(project.config)
    if "project" not in config:
        config["project"] = {
            KAGConstants.KAG_PROJECT_ID_KEY: project_id,
            KAGConstants.KAG_PROJECT_HOST_ADDR_KEY: host_addr,
            KAGConstants.KAG_NAMESPACE_KEY: project.namespace,
        }
        prompt_config = config.pop("prompt", {})
        for key in [KAGConstants.KAG_LANGUAGE_KEY, KAGConstants.KAG_BIZ_SCENE_KEY]:
            if key in prompt_config:
                config["project"][key] = prompt_config[key]
    if "vectorizer" in config and "vectorize_model" not in config:
        config["vectorize_model"] = config["vectorizer"]
    return config


class KagService:

    def __init__(self, service_url: str, addition_modules: list[str] = None):
        self.service_url = service_url

        import_modules_from_path(
            os.path.join(os.path.dirname(__file__), "kag_additions")
        )
        for module in addition_modules or []:
            import_modules_from_path(module)

        self.project_client = ProjectClient(host_addr=self.service_url, project_id=-1)
        logger.info("loading projects")
        self.project_list = self.project_client.get_all()
        logger.info(f"loaded {len(self.project_list)} projects")
        for project_name, project_key in self.project_list.items():
            logger.info(f"  - {project_name}: {project_key}")
        pass

    def get_projects(self):
        return self.project_list

    def get_project_id_by_name(self, project_name: str):
        return self.project_list.get(project_name)

    def load_kag_config(self, service_url: str, project_id: str):
        """加载KAG配置"""
        return load_kag_config(service_url, project_id)

    async def query(
        self, query: str, project_id: str, printer=None
    ) -> AsyncGenerator[Any, None]:
        """
        查询知识图谱，返回异步生成器

        Args:
            query: 用户查询文本
            project_id: 项目ID
            printer: 兼容旧接口的回调函数，已弃用

        Returns:
            异步生成器，产生查询结果
        """
        try:
            # 创建事件报告器，将结果保存到事件列表
            reporter = EventReporter(callback=printer)

            # 检查项目ID是否有效,如果不是数字ID尝试获取对应的项目ID
            if not project_id.isdigit() and project_id in self.project_list:
                numeric_id = self.project_list.get(project_id)
                logger.info(f"Converting project name {project_id} to ID {numeric_id}")
                project_id = numeric_id

            global_config = load_kag_config(self.service_url, project_id)

            KAG_CONFIG.update_conf(global_config)
            KAG_PROJECT_CONF.project_id = project_id

            solver_config = global_config.get("solver_pipeline")
            if not solver_config:
                # 如果没有找到配置，返回默认响应而不是错误
                logger.warning(
                    f"No solver_pipeline configuration found for project {project_id}, using default response"
                )
                response = f"我是一个知识库助手，但我无法找到项目 {project_id} 的配置。请尝试其他问题或联系管理员配置此项目。"
                # 创建一个模拟事件
                mock_event = {
                    "event": "changed",
                    "data": {
                        "content": response,
                        "segment": "answer",
                        "tag_name": "mock_answer",
                    },
                }
                yield mock_event
                return

            try:
                # 创建求解器管道
                solver = SolverPipelineABC.from_config(solver_config)

                # 调用求解器，获取结果
                result = await solver.ainvoke(query, reporter=reporter)

                # 先返回所有报告事件
                for event in reporter.events:
                    yield event

                # 然后返回最终结果
                if result:
                    yield result

            except Exception as solver_error:
                # 处理求解器错误，但返回友好响应
                error_message = (
                    f"Error initializing solver pipeline: {str(solver_error)}"
                )
                logger.error(error_message)
                traceback.print_exc()

                response = "很抱歉，处理您的请求时遇到了问题。请稍后再试或联系管理员。"
                mock_event = {
                    "event": "changed",
                    "data": {
                        "content": response,
                        "segment": "answer",
                        "tag_name": "error_answer",
                    },
                }
                yield mock_event

        except Exception as e:
            # 处理一般错误，但返回友好响应
            error_message = f"Error in query execution: {str(e)}"
            logger.error(error_message)
            traceback.print_exc()

            response = "很抱歉，处理您的请求时遇到了问题。请稍后再试或联系管理员。"
            mock_event = {
                "event": "changed",
                "data": {
                    "content": response,
                    "segment": "answer",
                    "tag_name": "error_answer",
                },
            }
            yield mock_event


kag_service = None


def get_kag_service(service_url: str, addition_modules: list[str] = None) -> KagService:
    global kag_service
    if kag_service is None:
        kag_service = KagService(
            service_url=service_url, addition_modules=addition_modules
        )
    return kag_service


print(__file__)
