# -*- coding: utf-8 -*-
"""
字符串工具（参考 large_health_reference/app/utils/string_utils.py）。
核心：extract_sql_after_escape_mark（LLM 输出 → 纯 SQL 后处理）。
"""
import re
import json
from datetime import datetime
from typing import Optional, Dict, Any


def extract_sql_after_escape_mark(text: str) -> str:
    """
    从 LLM 输出中提取纯 SQL（对标参考实现）。
    策略：
      1. 找 `</think>` 标记，取其后内容
      2. 匹配 DML 关键字（SELECT/SHOW/DESC/WITH）开头的 SQL 语句块
      3. 去除 markdown ```sql ... ``` 围栏
      4. 去除行注释（--）、块注释（/* */）
      5. 补末尾分号（若缺失）
    返回：纯 SELECT SQL 字符串（空字符串表示提取失败）
    """
    if not text:
        return ""

    # 1. 截取 </think> 之后（LLM 思考链在 </think> 之前）
    marker = "</think>"
    if marker in text:
        text = text.split(marker, 1)[1]

    # 2. 去除 markdown 围栏
    text = re.sub(r"```sql\s*", "", text, flags=re.IGNORECASE)
    text = re.sub(r"```\s*", "", text)

    # 3. 找第一个 DML 关键字开头
    match = re.search(
        r"\b(SELECT|SHOW|DESC|WITH)\b",
        text.strip(),
        re.IGNORECASE
    )
    if not match:
        return ""

    # 从匹配位置截取到文本末尾
    sql = text[match.start():].strip()

    # 4. 去除行注释
    sql = re.sub(r"--[^\n]*", " ", sql)
    # 去除块注释
    sql = re.sub(r"/\*.*?\*/", " ", sql, flags=re.DOTALL)

    # 5. 去除非 SQL 尾部（如"以上是查询结果"等自然语言）
    # 找第一个不在 () 内的分号作为语句分隔，取第一段
    depth = 0
    end_idx = len(sql)
    for i, ch in enumerate(sql):
        if ch == "(":
            depth += 1
        elif ch == ")":
            depth -= 1
        elif ch == ";" and depth == 0:
            end_idx = i + 1
            break

    # 5.1 兜底：截断"裸中文说明行"（qwen 等小模型常在 SQL 后追加
    #      "说明：\n- ..." 自然语言，且语句体无分号导致上一步把整段算进 SQL）
    #     仅在字符串字面量外的行首中文触发；引号内的中文值（'本科'/'成都'）不受影响。
    semi_end = end_idx
    nl_end = _cut_before_natural_language(sql)
    # 取两者更早的结束位置
    if nl_end is not None:
        end_idx = min(semi_end, nl_end)
    sql = sql[:end_idx].strip()

    # 6. 补末尾分号
    if sql and not sql.rstrip().endswith(";"):
        sql = sql.rstrip().rstrip(";") + ";"

    return sql


def _cut_before_natural_language(sql: str):
    """
    检测 SQL 中"裸中文说明行"起始位置（返回应截断的索引；无则 None）。
    qwen 等小模型常输出：`...SQL...\n说明：\n- 该查询...`，语句体本身无分号，
    导致 extract 上一步把自然语言也算进 SQL，执行时 MySQL 报 1064。
    判定：字符串字面量（单引号内）之外，某行行首出现中文说明词（中文/中文标点）
    即视为 SQL 已结束。引号内的中文值（education='本科'、work_location='成都'）
    因处于引号内被跳过，不会误伤。
    """
    if not sql:
        return None
    in_squote = False
    i = 0
    n = len(sql)
    # 用 last_line_start 记录最近一次行首（跳过空白）的索引；行内遇普通字符则置 None，
    # 换行则重置为新行首候选。这样可容忍"说明：\n- 该查询"里以列表符开头的说明行。
    while i < n:
        ch = sql[i]
        # 处理转义 / 连续引号（MySQL '' 表示单个 '）
        if ch == "\\" and in_squote:
            i += 2
            continue
        if ch == "'":
            if in_squote and i + 1 < n and sql[i + 1] == "'":
                i += 2
                continue
            in_squote = not in_squote
            i += 1
            continue
        if not in_squote:
            if ch == "\n":
                # 新行：探测紧随其后、跳过空白后的首字符
                j = i + 1
                while j < n and sql[j] in " \t\r":
                    j += 1
                # 行首是中文 / 中文标点 / 列表符（- • *）即视为自然语言说明行起点；
                # 合法 SQL 续行不会以这些字符作行首（负数/减号不会单独起行），故直接截断。
                if j < n and _is_nl_line_start(sql[j]):
                    return j
                i += 1
                continue
            # 行内其它字符：保持扫描
            i += 1
        else:
            i += 1
    return None


def _is_nl_line_start(c: str) -> bool:
    """判断字符是否可能是自然语言说明行的引导（中文 / 中文标点 / 列表符）。"""
    if "\u4e00" <= c <= "\u9fff":
        return True
    if c in "，。：、；！？…—“”‘’":
        return True
    # ASCII 列表符或说明引导（如 '-'、'•'、'*' 后通常接文字）
    if c in "-•*·":
        return True
    return False


def format_json(data: Any) -> str:
    """
    JSON 序列化（带 datetime 支持）。
    对标参考 string_utils.format_json。
    """
    class _DateTimeEncoder(json.JSONEncoder):
        def default(self, obj):
            if isinstance(obj, datetime):
                return obj.isoformat()
            return super().default(obj)

    return json.dumps(data, ensure_ascii=False, indent=2, cls=_DateTimeEncoder)


def sanitize_filename(filename: str) -> str:
    """
    净化文件名（防路径穿越 / 非法字符）。
    对标参考 file_handler 逻辑。
    """
    import re
    # 去掉路径分隔符和上级目录引用
    filename = re.sub(r"[\\/]+", "_", filename)
    filename = re.sub(r"\.\.+", "_", filename)
    # 去掉 Windows/NTFS 非法字符
    filename = re.sub(r'[<>:"|?*\x00-\x1f]', "_", filename)
    return filename.strip() or "unnamed"


def normalize_whitespace(text: str) -> str:
    """合并多余空白（保留换行分段信息）"""
    # 合并连续空格，但保留换行
    lines = [re.sub(r"[ \t]+", " ", line).strip() for line in text.splitlines()]
    return "\n".join(line for line in lines if line)


# =====================================================================
# LLM 思考段（think 标记）剥离
# =====================================================================
# 背景：qwen3 等推理模型会把思考过程包裹在 <think>...</think> 中一并输出。
# 若直接透传给前端/报告，用户会看到一大段自述式思考文字，严重影响专业性与可读性。
# 本函数统一剥离，供 Dify 报告、知识库问答、Agent 输出等所有 LLM 文本出口调用。
_RE_THINK_BLOCK = re.compile(r"<think\b[^>]*>.*?</think\s*>", re.IGNORECASE | re.DOTALL)
_RE_THINK_OPEN = re.compile(r"<think\b[^>]*>", re.IGNORECASE)
_RE_THINK_CLOSE = re.compile(r"</think\s*>", re.IGNORECASE)


def strip_think_markup(text: Optional[str]) -> str:
    """
    剥离 LLM 输出中的思考段标记，只保留正式回答。

    处理四种形态：
      1. 成对块     `<think>思考...</think>正文` → 移除思考段，保留正文
      2. 仅闭合标记 `思考...</think>正文`        → 起始标记在 prompt 模板中，
                                                取闭合标记之后的内容为正文
      3. 未闭合     `<think>思考...(被截断)`      → 思考未结束，其前内容不可用
      4. 无标记     `普通文本`                    → 原样返回

    Args:
        text: LLM 原始输出

    Returns:
        剥离后的文本（已 strip）；输入为空时返回空串
    """
    if not text:
        return ""

    # 1) 先移除所有完整成对块
    cleaned = _RE_THINK_BLOCK.sub("", text)

    # 2) 残留闭合标记：闭合标记之前的内容属思考过程，只保留其后内容
    #    （需先于开启标记处理：当两种标记同时残留时，闭合标记标识了思考段的结束位置）
    m_close = _RE_THINK_CLOSE.search(cleaned)
    if m_close:
        cleaned = cleaned[m_close.end():]

    # 3) 残留未闭合开启标记：思考未结束，其后的内容不可用
    if _RE_THINK_OPEN.search(cleaned):
        cleaned = _RE_THINK_OPEN.split(cleaned, maxsplit=1)[0]

    # 4) 清理残余标记
    cleaned = _RE_THINK_CLOSE.sub("", cleaned)
    cleaned = _RE_THINK_OPEN.sub("", cleaned)

    return cleaned.strip()
