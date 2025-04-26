"""
Toolkit
"""

from enum import Enum
import os


def remove_empty_fields(obj):
    """
    递归地移除字典或列表中的空字段和None值
    同时处理不可序列化的对象，将其转换为字符串表示
    """
    if obj is None:
        return None

    # 处理字典
    if isinstance(obj, dict):
        result = {}
        for key, value in obj.items():
            processed_value = remove_empty_fields(value)
            if (
                processed_value is not None
                and processed_value != {}
                and processed_value != []
            ):
                result[key] = processed_value
        return result

    # 处理列表
    elif isinstance(obj, list):
        result = []
        for item in obj:
            processed_item = remove_empty_fields(item)
            if (
                processed_item is not None
                and processed_item != {}
                and processed_item != []
            ):
                result.append(processed_item)
        return result

    # 基本数据类型直接返回
    elif isinstance(obj, (str, int, float, bool)):
        return obj

    # 处理复杂对象
    else:
        try:
            # 尝试将对象转换为字典
            if hasattr(obj, "to_dict") and callable(getattr(obj, "to_dict")):
                return remove_empty_fields(obj.to_dict())
            elif hasattr(obj, "__dict__"):
                return remove_empty_fields(
                    {k: v for k, v in obj.__dict__.items() if not k.startswith("_")}
                )
            else:
                # 无法处理的对象转换为字符串
                return str(obj)
        except Exception:
            # 完全无法处理的情况下，转换为字符串
            return str(obj)


def write_fake_config(filename: str, service_url: str, debug_level="INFO"):
    """
    create a fake config file before KAG loaded
    this function should be called before **import kag**
    @:param service_url: the service url
    @:param debug_level: the debug level
    """

    content = f"""
# keep this fake config to cheat openspg-kag
# warning: 
#     KAG load this file as global config in 'kag.common.conf.KAGConfigMgr'. so we lost all default configs in kag.
#     if you want to use default configs, update this file.
project:
  host_addr: {service_url}

log:
  level: {debug_level}

vectorize_model:
  type: openai
    """
    with open(filename, "w") as f:
        f.write(content)
    pass


def get_open_spg_address():
    """
    获取OpenSPG服务地址

    Returns:
        str: OpenSPG服务地址
    """
    return os.environ.get("KAG_PROJECT_HOST_ADDR", "http://127.0.0.1:8887")
