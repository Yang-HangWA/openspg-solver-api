# 可注册模块放置目录

将自定义的模块放在这个目录下，它们会被自动注册到KAG框架中。

# 流式生成器配置

## 基本配置
在项目配置中定义流式LLM客户端：

```yaml
# 定义stream-llm
generate_llm: &generate_llm
  # 必需参数
  api_key: your_api_key_here      # 您的API密钥
  base_url: https://api.example.com/v1  # API基础URL
  model: model_name_here          # 模型名称，例如gpt-3.5-turbo
  type: stream_openai_llm         # 使用流式OpenAI类型

  # 可选参数
  temperature: 0.7                # 温度参数，控制随机性

# 在solver_pipeline中引用LLM客户端
solver_pipeline:
  generator:
    type: default_generator
    llm_client: *generate_llm     # 引用上面定义的LLM客户端
```

## 支持的LLM类型
- `stream_openai_llm`: 支持OpenAI API格式的流式响应，适用于OpenAI和兼容服务
- `llamacpp_llm`: 用于本地部署的LLaMA模型
- `anthropic_llm`: 用于Anthropic的Claude模型

## 常见配置示例

### OpenAI GPT配置
```yaml
generate_llm:
  api_key: sk-...        # 您的OpenAI API密钥
  base_url: https://api.openai.com/v1
  model: gpt-3.5-turbo    # 或 gpt-4 等其他型号
  type: stream_openai_llm
  temperature: 0.7
```

### Azure OpenAI配置
```yaml
generate_llm:
  api_key: your_azure_api_key
  base_url: https://your-resource.openai.azure.com/openai/deployments/your-deployment-name
  model: gpt-35-turbo
  type: stream_openai_llm
  api_version: 2023-05-15  # Azure API版本
```

### 本地LLM配置
```yaml
generate_llm:
  model_path: /path/to/your/model.gguf
  type: llamacpp_llm
  context_length: 4096
  temperature: 0.7
```

## 常见问题排查

1. **序列化错误**：确保所有返回数据可以被序列化为JSON
2. **连接超时**：增加连接超时时间或减少请求批量
3. **API密钥错误**：检查API密钥是否有效，是否有足够的配额
4. **模型不可用**：确认模型名称是否正确，并确保您有权访问该模型

如需详细的错误日志，可设置环境变量：
```bash
export LOG_LEVEL=DEBUG
```
