import asyncio
import json
import logging
import traceback
from typing import Optional, AsyncGenerator, Any

from fastapi import APIRouter, Depends, HTTPException, Request
from fastapi.responses import Response
from pydantic import BaseModel, Field
from sse_starlette.sse import EventSourceResponse

from app.openspg.api.openai_api_types import (
    ChatCompletionRequest,
    ChatCompletion,
    ChatCompletionChunk,
)
from app.openspg.api.openai_api_types.chat_completion_response import (
    ChatMessage,
    ChatCompletionChoice,
)
from app.openspg.service.kag_service import get_kag_service
from app.utils import get_open_spg_address

router = APIRouter()
logger = logging.getLogger(__name__)


class ChatRequest(BaseModel):
    user_id: Optional[str] = Field(None, title="User ID")
    query: str = Field(..., title="User's query")
    project_id: str = Field(..., title="Target project ID")
    knowledge_id: Optional[str] = Field(None, title="Target knowledge ID")
    stream: Optional[bool] = Field(False, title="Stream response")


@router.post("/chat/completions", response_model=ChatCompletion)
async def create_chat_completion(
    request: Request,
    chat_request: ChatCompletionRequest,
    openspg_service: str = Depends(get_open_spg_address),
):
    """
    Provides a chat completion that's compatible with the OpenAI Chat API.
    """
    try:
        # Validate the request and extract the query
        if not chat_request.messages or len(chat_request.messages) == 0:
            raise HTTPException(status_code=400, detail="No messages provided")

        last_msg = chat_request.messages[-1]
        if last_msg.role != "user":
            raise HTTPException(
                status_code=400, detail="Last message must be from the user"
            )

        query = last_msg.content
        # 从model字段中提取项目名称，如 "openspg/CsQa" 提取为 "CsQa"
        if chat_request.model and "/" in chat_request.model:
            project_id = chat_request.model.split("/")[-1]
        else:
            project_id = chat_request.project_id or "0"

        stream = chat_request.stream or False

        logger.info(
            f"Chat completion request: {query[:100]}{'...' if len(query) > 100 else ''}, project: {project_id}"
        )

        # Get KAG service
        kag_service = get_kag_service(openspg_service)

        if stream:
            # 直接返回流式响应
            return EventSourceResponse(
                stream_generator(kag_service, query, project_id),
                media_type="text/event-stream",
            )
        else:
            # 处理非流式请求 - 收集所有结果然后返回完整响应
            full_response = ""
            async for chunk in kag_service.query(query, project_id):
                if isinstance(chunk, str):
                    if chunk.startswith("Error:"):
                        # 处理错误情况
                        raise HTTPException(status_code=500, detail=chunk)
                    else:
                        # 处理文本响应
                        full_response += chunk
                elif isinstance(chunk, dict):
                    if "event" in chunk and chunk["event"] == "changed":
                        # 处理中间事件，提取内容添加到响应
                        if "data" in chunk and "content" in chunk["data"]:
                            content = chunk["data"]["content"]
                            # 确保content是字符串
                            if isinstance(content, str):
                                full_response += content
                            elif content is not None:
                                # 如果不是字符串但有值，转换为字符串
                                full_response += str(content)
                    else:
                        # 处理其他字典格式响应
                        if isinstance(chunk.get("data", {}).get("content"), str):
                            full_response += chunk["data"]["content"]
                        else:
                            # 如果无法解析内容，转换为字符串
                            full_response += str(chunk)
                else:
                    # 处理其他类型的结果
                    full_response += str(chunk)

            # 构建并返回完整响应
            return ChatCompletion(
                id=f"chatcmpl-{project_id}",
                object="chat.completion",
                model=chat_request.model or f"kag-{project_id}",
                choices=[
                    ChatCompletionChoice(
                        index=0,
                        message=ChatMessage(role="assistant", content=full_response),
                        finish_reason="stop",
                    )
                ],
                usage={
                    "prompt_tokens": len(query),
                    "completion_tokens": len(full_response),
                    "total_tokens": len(query) + len(full_response),
                },
            )

    except Exception as e:
        logger.error(f"Error in create_chat_completion: {str(e)}")
        traceback.print_exc()
        raise HTTPException(status_code=500, detail=str(e))


async def stream_generator(
    kag_service, query: str, project_id: str
) -> AsyncGenerator[str, None]:
    """
    生成流式响应的异步生成器
    """
    try:
        event_id = 0
        # 发送开始事件
        yield json.dumps(
            {
                "id": f"chatcmpl-{event_id}",
                "object": "chat.completion.chunk",
                "created": int(asyncio.get_event_loop().time()),
                "model": "kag",
                "choices": [
                    {"index": 0, "delta": {"role": "assistant"}, "finish_reason": None}
                ],
            }
        )
        event_id += 1

        # 直接使用kag_service的异步生成器
        current_content = ""
        async for chunk in kag_service.query(query, project_id):
            # 解析结果
            if isinstance(chunk, str) and chunk.startswith("Error:"):
                # 发送错误消息
                yield json.dumps(
                    {
                        "id": f"chatcmpl-{event_id}",
                        "object": "chat.completion.chunk",
                        "created": int(asyncio.get_event_loop().time()),
                        "model": "kag",
                        "choices": [
                            {
                                "index": 0,
                                "delta": {"content": f"Error: {chunk}"},
                                "finish_reason": "error",
                            }
                        ],
                    }
                )
                break

            elif (
                isinstance(chunk, dict)
                and "event" in chunk
                and chunk["event"] == "changed"
            ):
                # 处理中间事件，提取内容
                if "data" in chunk and "content" in chunk["data"]:
                    content = chunk["data"]["content"]
                    if content and content != current_content:
                        # 只发送增量内容
                        delta = content[len(current_content) :]
                        current_content = content

                        yield json.dumps(
                            {
                                "id": f"chatcmpl-{event_id}",
                                "object": "chat.completion.chunk",
                                "created": int(asyncio.get_event_loop().time()),
                                "model": "kag",
                                "choices": [
                                    {
                                        "index": 0,
                                        "delta": {"content": delta},
                                        "finish_reason": None,
                                    }
                                ],
                            }
                        )
                        event_id += 1
            else:
                # 处理最终结果
                final_content = str(chunk)
                if final_content and final_content != current_content:
                    delta = final_content[len(current_content) :]
                    yield json.dumps(
                        {
                            "id": f"chatcmpl-{event_id}",
                            "object": "chat.completion.chunk",
                            "created": int(asyncio.get_event_loop().time()),
                            "model": "kag",
                            "choices": [
                                {
                                    "index": 0,
                                    "delta": {"content": delta},
                                    "finish_reason": None,
                                }
                            ],
                        }
                    )
                    event_id += 1

        # 发送结束事件
        yield json.dumps(
            {
                "id": f"chatcmpl-{event_id}",
                "object": "chat.completion.chunk",
                "created": int(asyncio.get_event_loop().time()),
                "model": "kag",
                "choices": [{"index": 0, "delta": {}, "finish_reason": "stop"}],
            }
        )

    except Exception as e:
        logger.error(f"Error in stream_generator: {str(e)}")
        traceback.print_exc()
        # 发送错误消息
        yield json.dumps(
            {
                "id": f"chatcmpl-error",
                "object": "chat.completion.chunk",
                "created": int(asyncio.get_event_loop().time()),
                "model": "kag",
                "choices": [
                    {
                        "index": 0,
                        "delta": {"content": f"\nError: {str(e)}"},
                        "finish_reason": "error",
                    }
                ],
            }
        )


def mount_routes(app, args):
    """
    挂载OpenAI API兼容的路由

    Args:
        app: FastAPI应用实例
        args: 命令行参数
    """
    prefix = args.servlet
    openai_api_prefix = f"{prefix}/openspg/v1"

    # 注册路由
    app.include_router(router, prefix=openai_api_prefix)

    # 添加模型信息端点
    @app.get(f"{openai_api_prefix}/models", tags=["OpenAI API"])
    async def list_models():
        """
        列出可用模型，兼容OpenAI API
        """
        try:
            kag_service = get_kag_service(args.openspg_service)
            projects = kag_service.get_projects()

            logger.info(f"Available models: {list(projects.keys())}")

            return {
                "object": "list",
                "data": [
                    {
                        "id": f"openspg/{name}",
                        "object": "model",
                        "created": int(asyncio.get_event_loop().time()),
                        "owned_by": "openspg",
                    }
                    for name in projects.keys()
                ],
            }
        except Exception as e:
            logger.error(f"Error listing models: {str(e)}")
            traceback.print_exc()
            # 返回至少一些默认模型
            return {
                "object": "list",
                "data": [
                    {
                        "id": "openspg/default",
                        "object": "model",
                        "created": int(asyncio.get_event_loop().time()),
                        "owned_by": "openspg",
                    }
                ],
            }
