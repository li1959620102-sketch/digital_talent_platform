# -*- coding: utf-8 -*-
"""
Dify 中台适配器（对齐参考 large_health_reference/app/adapter/dify_universal_client.py）。

关键改进（对比旧版）：
- DifyUniversalClient.call_application() 自动识别 chat/workflow 并路由
- _detect_app_type() 探测 app 类型，缓存避免重复探测
- run_workflow/run_chat 统一返回 {status, outputs/message}
- 400 not_workflow_app 自动降级 chat（参考实现）
- 保留 run_workflow() 别名，对五大 Agent 透明

Dify 定位：AI 应用中台（Prompt管理/模型路由/知识库），不承载复杂业务 Agent 编排。
DIFY_ENABLED=false / 缺 Key / 网络错误 → DifyUnavailable，上层回退本地链路。
"""
import json
import logging
import time
import urllib.request
import urllib.error
from typing import Optional, List, Dict, Any

from app.core.config import settings
from app.utils.string_utils import strip_think_markup

logger = logging.getLogger(__name__)


class DifyUnavailable(Exception):
    """Dify 不可用（未启用 / 缺 Key / 网络错误）——上层应回退本地链路"""
    pass


# ─────────────────────────────────────────────────────────────
# 通用客户端（对标参考 DifyUniversalClient）
# ─────────────────────────────────────────────────────────────

class DifyUniversalClient:
    """
    Dify 通用客户端（参考 DifyUniversalClient 模式）：
    - call_application() 自动识别 chat/workflow 并路由
    - _detect_app_type() 探测 app 类型，缓存避免重复探测
    - 400 not_workflow_app 自动降级 chat
    """

    def __init__(self, api_base: str, api_key: str):
        self.api_base = api_base.rstrip("/")
        self.api_key = api_key
        # 缓存：app_key → "chat" | "workflow"（避免每次探测）
        self._type_cache: Dict[str, str] = {}
        self._timeout_default = 60

    def _headers(self, api_key: Optional[str] = None) -> Dict[str, str]:
        return {
            "Authorization": f"Bearer {api_key or self.api_key}",
            "Content-Type": "application/json",
        }

    def _post(self, path: str, payload: Dict[str, Any],
              timeout: int = 60, api_key: Optional[str] = None) -> Dict[str, Any]:
        url = f"{self.api_base}{path}"
        data = json.dumps(payload, ensure_ascii=False).encode("utf-8")
        req = urllib.request.Request(url, data=data, headers=self._headers(api_key), method="POST")
        try:
            with urllib.request.urlopen(req, timeout=timeout) as resp:
                return json.loads(resp.read().decode("utf-8"))
        except urllib.error.HTTPError as e:
            body = e.read().decode("utf-8", errors="replace")
            raise DifyUnavailable(f"HTTP {e.code}: {body[:200]}")
        except Exception as e:
            raise DifyUnavailable(f"请求失败: {e}")

    def _detect_app_type(self, api_key: str) -> str:
        """
        探测 app 类型（chat vs workflow），结果缓存 5 分钟。
        策略：向 /workflows/run 发空 inputs 探测请求。
          - workflow 应用 → 因缺必填 input 回 400 invalid_param（这是预期信号，判 workflow）
          - chat/completion 应用 → 回 not_workflow_app 类错误（判 chat）
          - 网络/超时等真异常 → 保守假设 workflow
        探测请求被 400（缺参）是 workflow 的"反向确认"，属预期，不打 WARNING 噪音。
        """
        if api_key in self._type_cache:
            cached_type, cached_at = self._type_cache[api_key]
            if time.time() - cached_at < 300:  # 5 分钟缓存
                return cached_type

        # 探测请求（最小 payload，避免副作用）
        try:
            self._post("/workflows/run", {
                "inputs": {},
                "response_mode": "blocking",
                "user": "__type_probe__",
            }, timeout=10, api_key=api_key)
            app_type = "workflow"
        except DifyUnavailable as e:
            err_str = str(e).lower()
            if "not_workflow_app" in err_str or "not a workflow" in err_str:
                # 明确非工作流应用 → chat/completion 类
                app_type = "chat"
            elif "invalid_param" in err_str or "required" in err_str:
                # 缺必填 input 被 400 → workflow 应用的预期反向确认，静默判定
                app_type = "workflow"
            else:
                # 网络/超时/Dify 内部错误，保守假设 workflow（让上层决定）
                logger.warning(f"类型探测异常，假设 workflow: {e}")
                app_type = "workflow"

        self._type_cache[api_key] = (app_type, time.time())
        logger.info(f"Dify App 类型探测: {api_key[:12]}... → {app_type}")
        return app_type

    def call_application(
        self,
        api_key: str,
        inputs: Dict[str, Any],
        query: Optional[str] = None,
        user: str = "talent-platform",
        timeout: int = 120,
    ) -> Dict[str, Any]:
        """
        统一入口（对标参考 call_application）：
        自动探测 app 类型并路由到正确端点。
        返回统一格式：{status, outputs/message, data}
        """
        if not api_key:
            raise DifyUnavailable("API Key 未配置")

        app_type = self._detect_app_type(api_key)
        payload = {
            "inputs": inputs,
            "response_mode": "blocking",
            "user": user,
        }
        if query is not None:
            payload["query"] = query

        try:
            if app_type == "workflow":
                data = self._post("/workflows/run", payload, timeout=timeout, api_key=api_key)
                outputs = data.get("data", {}).get("outputs", {})
                return {"status": "success", "app_type": "workflow", "outputs": outputs, "raw": data}
            else:
                data = self._post("/chat-messages", payload, timeout=timeout, api_key=api_key)
                answer = data.get("answer", "") or data.get("data", {}).get("answer", "")
                return {"status": "success", "app_type": "chat", "message": answer, "raw": data}
        except DifyUnavailable as e:
            # 400 not_workflow_app：自动降级到 chat（参考实现降级逻辑）
            if "not_workflow_app" in str(e) or "not a workflow" in str(e):
                logger.info(f"App {api_key[:12]}... 非 workflow，降级为 chat 模式")
                # 清除缓存，下次重新探测
                self._type_cache.pop(api_key, None)
                try:
                    data = self._post("/chat-messages", payload, timeout=timeout, api_key=api_key)
                    answer = data.get("answer", "") or data.get("data", {}).get("answer", "")
                    return {"status": "success", "app_type": "chat", "message": answer,
                            "raw": data, "auto_downgrade": True}
                except DifyUnavailable:
                    raise
            raise


# ─────────────────────────────────────────────────────────────
# 业务层适配（保留原有 Agent 视角接口，对五大 Agent 透明）
# ─────────────────────────────────────────────────────────────

class DifyAdapter:
    """
    Dify 中台客户端（同步实现，Agent 视角封装）。
    内部使用 DifyUniversalClient，自动处理 chat/workflow 路由。

    AGENT_APP_KEY_MAP: 五大 Agent → .env 配置项映射
    """

    # 五大 Agent → 对应 Dify App Key 配置项映射
    AGENT_APP_KEY_MAP = {
        "resume": "DIFY_APP_KEY_RESUME",
        "assessment": "DIFY_APP_KEY_ASSESSMENT",
        "matching": "DIFY_APP_KEY_MATCHING",
        "training": "DIFY_APP_KEY_TRAINING",
        "data_decision": "DIFY_APP_KEY_DATA_DECISION",
    }

    def __init__(self):
        self.enabled = bool(settings.DIFY_ENABLED)
        self.api_base = (settings.DIFY_API_BASE or "").rstrip("/")
        self.api_key = settings.DIFY_API_KEY or ""
        self.mode = settings.DIFY_APP_MODE or "workflow"
        self.backend_token = settings.DIFY_BACKEND_TOKEN or ""

        # 初始化通用客户端（用于需要自动探测的场景）
        self._universal: Optional[DifyUniversalClient] = None
        if self.enabled and self.api_key:
            self._universal = DifyUniversalClient(self.api_base, self.api_key)

        # 五大 Agent 各自独立的 Dify App Key
        self.app_keys: Dict[str, str] = {
            agent: getattr(settings, cfg_key, "")
            for agent, cfg_key in self.AGENT_APP_KEY_MAP.items()
        }

        if self.enabled:
            configured = [a for a, k in self.app_keys.items() if k]
            logger.info(f"Dify 中台已启用: {self.api_base}，已配置 {len(configured)}/{len(self.app_keys)} 个 Agent App Key")
        else:
            logger.info("Dify 中台未启用（DIFY_ENABLED=false），走本地模型链路")

    # ─── 通用探测 ────────────────────────────────────────────

    def get_app_key(self, agent: str) -> str:
        """按 Agent 类型取 Dify App Key"""
        return self.app_keys.get(agent, "")

    # ─── 统一入口（推荐使用）─────────────────────────────────

    def call_application(
        self,
        agent: str,
        inputs: Dict[str, Any],
        query: Optional[str] = None,
        user: str = "talent-platform",
        timeout: int = 120,
    ) -> Dict[str, Any]:
        """
        统一调用入口（对标参考 call_application）。
        自动探测 app 类型并路由到正确端点，返回统一格式。
        推荐五大 Agent 使用此接口。
        """
        if not self.enabled:
            raise DifyUnavailable("Dify 未启用")
        api_key = self.get_app_key(agent)
        if not api_key:
            raise DifyUnavailable(f"Dify App Key 未配置: {agent}")
        if self._universal is None:
            self._universal = DifyUniversalClient(self.api_base, self.api_key)
        return self._universal.call_application(api_key, inputs, query, user, timeout)

    # ─── 独立接口（向后兼容 + 显式语义）─────────────────────

    def completion(self, prompt: str, user: str = "talent-platform") -> str:
        """
        Completion 模式（生成一段回答文本）。
        对 DIFY_API_KEY 指向的应用做自适应路由（实时探测类型，不受全局 DIFY_APP_MODE
        开关误导）：
          - chat 应用 → /chat-messages（text-gen 应用走 /completion-messages）
          - workflow 应用 → 无法直接文本生成，抛错由上层回退本地 LLM
        修复：此前 completion 用 DIFY_APP_MODE=workflow 分支打 /completion-messages，
        而实际全局 key 是 chat 应用，导致 knowledge/qa 每次 400 后静默回退本地。
        """
        if not self.enabled:
            raise DifyUnavailable("Dify 未启用")
        if self._universal is None:
            self._universal = DifyUniversalClient(self.api_base, self.api_key)
        payload = {
            "inputs": {},
            "query": prompt,
            "response_mode": "blocking",
            "user": user,
        }
        try:
            # 实时探测：chat 走 chat-messages，completion 走 completion-messages
            app_type = self._universal._detect_app_type(self.api_key)
            if app_type == "workflow":
                raise DifyUnavailable(
                    "DIFY_API_KEY 指向 workflow 应用，不支持文本生成式问答，请为知识问答配置 chat/completion 应用"
                )
            if app_type == "chat":
                data = self._post("/chat-messages", payload)
            else:  # completion
                data = self._post("/completion-messages", payload)
            return data.get("answer", "") or data.get("data", {}).get("answer", "")
        except DifyUnavailable:
            raise

    def chat(self, message: str, user: str = "talent-platform",
             conversation_id: str = "", inputs: Optional[dict] = None) -> Dict[str, Any]:
        """Chat 模式：返回完整响应（含 conversation_id）"""
        if not self.enabled:
            raise DifyUnavailable("Dify 未启用")
        payload = {
            "inputs": inputs or {},
            "query": message,
            "response_mode": "blocking",
            "conversation_id": conversation_id,
            "user": user,
        }
        return self._post("/chat-messages", payload)

    def run_workflow(self, agent: str, inputs: Dict[str, Any],
                     user: str = "talent-platform", timeout: int = 120) -> Dict[str, Any]:
        """
        调用 Dify Workflow（向后兼容别名，内部路由到 call_application）。
        agent: resume | assessment | matching | training | data_decision
        """
        if not self.enabled:
            raise DifyUnavailable("Dify 未启用")
        api_key = self.get_app_key(agent)
        if not api_key:
            raise DifyUnavailable(f"Dify App Key 未配置: {agent}")
        if self._universal is None:
            self._universal = DifyUniversalClient(self.api_base, self.api_key)
        result = self._universal.call_application(api_key, inputs, query=None, user=user, timeout=timeout)
        return result.get("outputs", {})

    # 各 Agent 工作流输出的报告字段名（供 run_report 通用提取）
    REPORT_OUTPUT_KEYS: Dict[str, List[str]] = {
        "resume": ["resume_report"],
        "assessment": ["assessment_report"],
        "matching": ["match_report"],
        "training": ["training_report"],
        "data_decision": ["nl2sql_result", "data_analysis_report", "report"],
    }

    # 输入有效性门禁字段：调用方在 inputs 中显式标记数据无效（False）时，
    # 拒绝调用 Dify 工作流，避免「空数据 / 不存在的记录」仍产出看似完整的报告。
    INPUT_GATE_FIELDS = ("data_valid", "input_valid")

    def _input_gate_passed(self, inputs: Dict[str, Any]) -> bool:
        """输入有效性门禁：任一 gate 字段显式为假值 → 判定输入无效。"""
        for field in self.INPUT_GATE_FIELDS:
            if field not in inputs:
                continue
            val = inputs[field]
            if val is False:
                return False
            if isinstance(val, str) and val.strip().lower() in ("false", "0", "no", "none", ""):
                return False
        return True

    def run_report(self, agent: str, inputs: Dict[str, Any], user: str = "talent-platform",
                   timeout: int = 120) -> Dict[str, Any]:
        """
        调用对应 Dify 工作流生成文字报告，返回统一结构。
        - 成功: {"success": True, "report": "<markdown>", "raw_outputs": {...}}
        - 失败/未启用/无key/输入无效: {"success": False, "message": "<原因>"}（调用方降级本地，不抛异常）

        安全设计（2026-10-13）：
        1. 输入有效性门禁——inputs 携带 data_valid=false 时直接拒绝，不调用工作流；
        2. 输出剥离 think 标记——避免 qwen3 等模型的思考过程混入正式报告。
        """
        if not self.enabled:
            return {"success": False, "message": "Dify 未启用（DIFY_ENABLED=false），跳过深度报告"}

        # ── 门禁：输入有效性（先于 enabled 判断的语义等价位置——
        #    此处位于 enabled 检查之后仅为保持分支简单；无论 Dify 是否启用，
        #    输入无效都不应产出报告，故调用方亦须自行校验 data_valid）──
        if not self._input_gate_passed(inputs):
            logger.warning(f"[Dify 输入门禁] 输入数据无效，拒绝生成报告: agent={agent}, inputs={inputs}")
            return {
                "success": False,
                "gate": "input_validation_failed",
                "message": "输入数据无效（data_valid=false），已阻止生成报告，请先确认目标记录是否存在",
            }

        try:
            api_key = self.get_app_key(agent)
            if not api_key:
                return {"success": False, "message": f"Dify App Key 未配置: {agent}"}
            if self._universal is None:
                self._universal = DifyUniversalClient(self.api_base, self.api_key)
            result = self._universal.call_application(api_key, inputs, query=None, user=user, timeout=timeout)
            if result.get("status") != "success":
                return {"success": False, "message": str(result.get("outputs") or result.get("error") or "Dify 执行未成功")}
            outputs = result.get("outputs") or {}
            report = self._extract_report_text(agent, outputs)
            if not report:
                return {"success": False, "message": f"Dify 工作流未返回报告文本（outputs keys={list(outputs.keys())}）"}
            return {"success": True, "report": report, "raw_outputs": outputs}
        except Exception as e:
            logger.warning(f"Dify 深度报告生成失败(agent={agent}): {e}")
            return {"success": False, "message": str(e)}

    @staticmethod
    def _extract_report_text(agent: str, outputs: Dict[str, Any]) -> str:
        """按 agent 的输出 key 取报告文本；未知结构则取第一个字符串值。
        所有返回路径均剥离 LLM 思考段标记（think），保证透出的是正式内容。
        """
        def _clean(value: str) -> str:
            return strip_think_markup(value.strip())

        keys = DifyAdapter.REPORT_OUTPUT_KEYS.get(agent, [])
        for k in keys:
            v = outputs.get(k)
            if v and isinstance(v, str) and _clean(v):
                return _clean(v)
        # 兜底：取第一个清洗后非空字符串值
        for v in outputs.values():
            if isinstance(v, str) and _clean(v):
                return _clean(v)
        # 兜底：结构化值 JSON 序列化（Dify 可能返回 dict/list）
        for v in outputs.values():
            if v:
                try:
                    return json.dumps(v, ensure_ascii=False)
                except Exception:
                    continue
        return ""

    def retrieve(self, query: str, dataset_ids: Optional[List[str]] = None,
                 top_k: int = 5) -> List[Dict[str, Any]]:
        """知识库检索（Dify 知识库运营能力）"""
        if not self.enabled:
            raise DifyUnavailable("Dify 未启用")
        payload: Dict[str, Any] = {
            "query": query,
            "retrieval_model": {"top_k": top_k, "score_threshold": 0.5},
        }
        if dataset_ids:
            payload["dataset_ids"] = dataset_ids
        data = self._post("/datasets/retrieve", payload)
        return data.get("records", [])

    # ─── 内部 ────────────────────────────────────────────────

    def _post(self, path: str, payload: Dict[str, Any],
              timeout: int = 60, api_key: Optional[str] = None) -> Dict[str, Any]:
        """内部 POST 工具（向后兼容）"""
        if not self.enabled:
            raise DifyUnavailable("Dify 未启用")
        url = f"{self.api_base}{path}"
        data = json.dumps(payload, ensure_ascii=False).encode("utf-8")
        req = urllib.request.Request(
            url, data=data,
            headers={"Authorization": f"Bearer {api_key or self.api_key}",
                     "Content-Type": "application/json"},
            method="POST"
        )
        try:
            with urllib.request.urlopen(req, timeout=timeout) as resp:
                return json.loads(resp.read().decode("utf-8"))
        except urllib.error.HTTPError as e:
            raise DifyUnavailable(f"HTTP {e.code}: {e.reason}")
        except Exception as e:
            raise DifyUnavailable(f"Dify 调用失败: {e}")


# 全局实例
dify_adapter = DifyAdapter()
