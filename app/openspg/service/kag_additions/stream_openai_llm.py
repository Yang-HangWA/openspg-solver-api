import logging
import time
from typing import Generator, Optional, Dict, Any, List, Union

from kag.common.llm import OpenAIClient
from kag.interface import LLMClient

logger = logging.getLogger()


@LLMClient.register("stream_openai_llm")
class StreamOpenAIClient(OpenAIClient):
    """
    增强版OpenAI客户端，支持流式响应并具备更好的错误处理
    """

    def __init__(
        self,
        api_key: str,
        base_url: str,
        model: str,
        temperature: float = 0.7,
        api_version: Optional[str] = None,
        timeout: int = 60,
        max_retries: int = 3,
        retry_interval: int = 2,
        system_prompt: str = "you are a helpful assistant",
    ):
        """
        初始化流式OpenAI客户端

        Args:
            api_key: API密钥
            base_url: API基础URL
            model: 模型名称
            temperature: 温度参数
            api_version: API版本，用于Azure等服务
            timeout: 请求超时时间(秒)
            max_retries: 最大重试次数
            retry_interval: 重试间隔(秒)
            system_prompt: 系统提示词
        """
        super().__init__(
            api_key=api_key,
            base_url=base_url,
            model=model,
            stream=True,
            temperature=temperature,
        )

        self.timeout = timeout
        self.max_retries = max_retries
        self.retry_interval = retry_interval
        self.system_prompt = system_prompt
        self.api_version = api_version

        # 如果使用Azure，修改URL格式
        if api_version:
            self.client.base_url = f"{base_url}"
            self.is_azure = True
            logger.info(f"Using Azure OpenAI with API version: {api_version}")
        else:
            self.is_azure = False

        logger.info(
            f"Initialized StreamOpenAIClient with model: {model}, base_url: {base_url}"
        )

    def __call__(
        self, prompt: str = "", image_url: str = None, **kwargs
    ) -> Generator[str, None, None]:
        """
        调用LLM模型，处理流式响应

        Args:
            prompt: 用户输入文本
            image_url: 图片URL (如果支持多模态)
            **kwargs: 其他参数

        Returns:
            生成器，产生模型输出的文本块
        """
        message = [
            {"role": "system", "content": self.system_prompt},
            {"role": "user", "content": prompt},
        ]

        # 添加图片内容（如果提供）
        if image_url:
            logger.info(f"Adding image URL to message: {image_url}")
            if isinstance(message[-1]["content"], str):
                message[-1]["content"] = [
                    {"type": "text", "text": message[-1]["content"]},
                    {"type": "image_url", "image_url": {"url": image_url}},
                ]

        # 记录请求开始
        request_id = f"req_{int(time.time())}"
        logger.debug(
            f"[{request_id}] Starting LLM request with prompt: {prompt[:100]}..."
        )

        for attempt in range(self.max_retries):
            try:
                # 准备请求参数
                request_params = {
                    "model": self.model,
                    "messages": message,
                    "stream": self.stream,
                    "temperature": self.temperature,
                    "timeout": self.timeout,
                }

                # 为Azure添加API版本
                if self.is_azure and self.api_version:
                    request_params["api_version"] = self.api_version

                # 发送请求
                response = self.client.chat.completions.create(**request_params)

                # 处理流式响应
                response_text = ""
                for chunk in response:
                    # 抽取文本内容
                    content = chunk.choices[0].delta.content
                    if content:
                        response_text += content
                        yield content

                logger.debug(
                    f"[{request_id}] Completed LLM request, total tokens: ~{len(response_text) // 4}"
                )
                return

            except Exception as e:
                logger.error(
                    f"Error in LLM request (attempt {attempt+1}/{self.max_retries}): {str(e)}"
                )
                if attempt < self.max_retries - 1:
                    logger.info(f"Retrying in {self.retry_interval} seconds...")
                    time.sleep(self.retry_interval)
                else:
                    logger.error(f"Max retries exceeded for LLM request")
                    # 返回错误信息
                    error_message = f"Error calling language model: {str(e)}"
                    yield error_message
                    return
        pass
