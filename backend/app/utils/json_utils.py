"""
健壮 JSON 提取工具
兼容 LLM 返回的常见"脏格式"：
- Markdown 代码围栏 ```json ... ```
- 前后多余说明文本
- 混合 ``` 与裸 JSON
"""
import json
import re
from typing import Any, Optional


def extract_json(text: str, default: Any = None) -> Any:
    """
    从可能含围栏/噪声的文本中提取首个合法 JSON 对象或数组。
    失败返回 default（若提供），否则抛 ValueError。
    """
    if text is None:
        if default is not None:
            return default
        raise ValueError("输入文本为 None")
    text = text.strip()

    # 1) 剥离 ```json ... ``` 或 ``` ... ``` 围栏
    fence = re.search(r"```(?:json)?\s*(.*?)```", text, re.DOTALL)
    if fence:
        text = fence.group(1).strip()

    # 2) 直接解析
    try:
        return json.loads(text)
    except (json.JSONDecodeError, ValueError):
        pass

    # 3) 提取首个平衡 {..} 或 [..]
    for opener, closer in (("{", "}"), ("[", "]")):
        start = text.find(opener)
        if start == -1:
            continue
        depth = 0
        for i in range(start, len(text)):
            if text[i] == opener:
                depth += 1
            elif text[i] == closer:
                depth -= 1
                if depth == 0:
                    candidate = text[start:i + 1]
                    try:
                        return json.loads(candidate)
                    except (json.JSONDecodeError, ValueError):
                        break

    if default is not None:
        return default
    raise ValueError(f"无法从文本中提取 JSON: {text[:200]}")
