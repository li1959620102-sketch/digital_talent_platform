"""Day5 新增能力测试：JSON 提取健壮性、Dify 适配器优雅降级

2026-10-13 补充：LLM 思考段（think 标记）剥离、Dify 输入有效性门禁。
背景：qwen3 等推理模型会把思考过程包裹在 <think>...</think> 中一并输出；
      且实测发现 Dify 工作流在输入记录不存在时仍会生成「看似完整」的报告。
"""
import sys
import os
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from app.utils.json_utils import extract_json
from app.utils.string_utils import strip_think_markup
from app.services.dify_adapter import dify_adapter, DifyUnavailable


def test_extract_json_plain():
    assert extract_json('{"a": 1}') == {"a": 1}


def test_extract_json_fence():
    text = '```json\n{"name": "张三", "age": 30}\n```'
    assert extract_json(text) == {"name": "张三", "age": 30}


def test_extract_json_array():
    assert extract_json('```json\n["标签A", "标签B"]\n```') == ["标签A", "标签B"]


def test_extract_json_with_surrounding_text():
    text = '以下是结果：\n{"ok": true}\n以上为输出'
    assert extract_json(text) == {"ok": True}


def test_extract_json_default_on_garbage():
    assert extract_json("完全不是json", default={"fallback": 1}) == {"fallback": 1}


def test_dify_adapter_respects_env():
    # DIFY_ENABLED=true（已配置 Dify 内部 LLM 阿里百炼）
    # 验证适配器 enabled 状态与 .env 一致
    from app.core.config import settings
    assert dify_adapter.enabled is settings.DIFY_ENABLED


def test_dify_completion_raises_when_disabled(monkeypatch):
    import pytest
    # 无 Key / 未启用时，适配器应优雅降级为 DifyUnavailable，上层回退本地链路
    monkeypatch.setattr(dify_adapter, "enabled", False)
    with pytest.raises(DifyUnavailable):
        dify_adapter.completion("hello")


def test_dify_retrieve_raises_when_disabled():
    import pytest
    with pytest.raises(DifyUnavailable):
        dify_adapter.retrieve("query")


# =====================================================================
# LLM 思考段（think 标记）剥离
# =====================================================================

def test_strip_think_markup_paired_block():
    """成对 <think>...</think> 块应被移除，只保留正式回答"""
    assert strip_think_markup("<think>用户希望我作为分析师...</think>## 报告\n内容") == "## 报告\n内容"


def test_strip_think_markup_multiple_blocks():
    """多组成对块全部移除"""
    assert strip_think_markup("<think>a</think>P1<think>b</think>P2") == "P1P2"


def test_strip_think_markup_unclosed_returns_empty():
    """未闭合的 <think>（被截断）视为无正式内容"""
    assert strip_think_markup("<think>用户希望基于提供的后端解析结果") == ""


def test_strip_think_markup_close_only():
    """仅有闭合标记（起始标记在 prompt 模板中）：取闭合标记之后的内容"""
    assert strip_think_markup("思考过程...</think>正式回答") == "正式回答"


def test_strip_think_markup_plain_text_unchanged():
    """无标记文本原样返回（仅去首尾空白）"""
    assert strip_think_markup("  没有标记的普通文本  ") == "没有标记的普通文本"


def test_strip_think_markup_empty_input():
    """空输入返回空串，不抛异常"""
    assert strip_think_markup("") == ""
    assert strip_think_markup(None) == ""


# =====================================================================
# Dify 输入有效性门禁
# =====================================================================

def test_dify_input_gate_helper():
    """门禁判定：显式假值 → 不通过；未声明 → 通过"""
    assert dify_adapter._input_gate_passed({}) is True
    assert dify_adapter._input_gate_passed({"data_valid": True}) is True
    assert dify_adapter._input_gate_passed({"data_valid": False}) is False
    assert dify_adapter._input_gate_passed({"input_valid": "false"}) is False
    assert dify_adapter._input_gate_passed({"data_valid": "0"}) is False


def test_dify_report_blocked_on_invalid_input(monkeypatch):
    """输入数据无效时必须拒绝生成报告——避免「空数据产出看似完整的报告」"""
    monkeypatch.setattr(dify_adapter, "enabled", True)
    out = dify_adapter.run_report(
        "assessment", {"data_valid": False, "assessment_result_id": 999}
    )
    assert out["success"] is False
    assert out.get("gate") == "input_validation_failed"
    assert "report" not in out
