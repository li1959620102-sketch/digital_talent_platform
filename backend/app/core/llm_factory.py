"""
统一 LLM 工厂
按策略返回对应 LLM，支持：
  - ollama: 本地 Ollama（向量模型不变，推理降级兜底）
  - silicon_flow: SiliconFlow（简历解析、NL2SQL 等高精度任务）

  # ali_bailian 分支已注释（2026-09-02）：实际未使用——Dify中台5大智能体全部用 workflow 模式，
  # Workflow 内部 LLM 在 Dify 控制台配置，不在本项目代码中调 LLM。保留旧代码备查，便于回滚。
  # - ali_bailian: 阿里百炼（Dify Chatflow 智能体用）

使用方式：
  from app.core.llm_factory import get_llm, get_llm_by_strategy

  # 按 config.LLM_STRATEGY 返回
  llm = get_llm()

  # 指定策略
  llm = get_llm_by_strategy("silicon_flow")
"""
import logging
from typing import Optional

from langchain_ollama import ChatOllama
from langchain_openai import ChatOpenAI

from app.core.config import settings

logger = logging.getLogger(__name__)


def _build_ollama_llm(
    model: Optional[str] = None,
    base_url: Optional[str] = None,
    temperature: float = 0.1,
    **kwargs
) -> ChatOllama:
    """构建 Ollama LLM

    本地 CPU 推理时 qwen3:1.7b 冷启动可达 ~100s，默认超时会让 Agent 恒定失败，
    因此显式注入 client_kwargs.timeout（由 OLLAMA_CHAT_TIMEOUT 控制）。

    同时必须限制**生成长度**（num_predict）：只设超时是不够的——实测模型会在
    一次调用里持续生成 3586 token 仍未结束（≈7.5 token/s），远超过 Nginx 的
    300s 读超时，导致请求被网关掐断、档案不落库。设上限后失控生成退化为
    「JSON 被截断 → 规则基线兜底」，是秒级失败而不是卡死。
    """
    params = dict(
        base_url=base_url or settings.OLLAMA_BASE_URL,
        model=model or settings.LLM_MODEL,
        temperature=temperature,
        num_predict=settings.OLLAMA_NUM_PREDICT,
    )
    params.update(kwargs)
    params.setdefault("client_kwargs", {"timeout": settings.OLLAMA_CHAT_TIMEOUT})
    try:
        return ChatOllama(**params)
    except TypeError:
        # 旧版 langchain-ollama 不认 client_kwargs，退回默认参数
        params.pop("client_kwargs", None)
        return ChatOllama(**params)


def _build_silicon_flow_llm(
    model: Optional[str] = None,
    temperature: float = 0.1,
    **kwargs
) -> ChatOpenAI:
    """构建 SiliconFlow LLM（DeepSeek-V4-Flash）"""
    key = settings.SILICON_FLOW_API_KEY
    if not key:
        raise ValueError("SILICON_FLOW_API_KEY 未配置，请在 .env 中设置")
    # max_tokens 与本地 Ollama 的 num_predict 同理：给生成设上限，
    # 避免模型在结构化抽取任务里无限输出。两者取值对齐，便于统一调参。
    kwargs.setdefault("max_tokens", settings.OLLAMA_NUM_PREDICT)
    return ChatOpenAI(
        api_key=key,
        base_url=settings.SILICON_FLOW_BASE_URL,
        model=model or settings.SILICON_FLOW_MODEL,
        temperature=temperature,
        **kwargs
    )


# 已注释（2026-09-02）：阿里百炼分支实际未使用——Dify中台5大智能体全部用 workflow 模式，
# Workflow 内部 LLM 在 Dify 控制台配置，不在本项目代码中调 LLM。保留旧代码备查，便于回滚：
# def _build_ali_bailian_llm(
#     model: Optional[str] = None,
#     temperature: float = 0.1,
#     **kwargs
# ) -> ChatOpenAI:
#     """构建阿里百炼 LLM（qwen3.8-max）"""
#     key = settings.ALI_BAILIAN_API_KEY
#     if not key:
#         raise ValueError("ALI_BAILIAN_API_KEY 未配置，请在 .env 中设置")
#     return ChatOpenAI(
#         api_key=key,
#         base_url=settings.ALI_BAILIAN_BASE_URL,
#         model=model or settings.ALI_BAILIAN_MODEL,
#         temperature=temperature,
#         **kwargs
#     )


def silicon_flow_available() -> bool:
    """SiliconFlow 是否可用（已配置密钥）"""
    return bool(settings.SILICON_FLOW_API_KEY)


def get_llm_by_strategy(
    strategy: Optional[str] = None,
    model: Optional[str] = None,
    temperature: float = 0.1,
    **kwargs
):
    """
    按策略获取 LLM

    Args:
        strategy: ollama | silicon_flow  （ali_bailian 已注释 2026-09-02：实际未使用）
                  传入 None 则使用 settings.LLM_STRATEGY
        model: 覆盖默认模型
        temperature: 温度参数
        **kwargs: 透传给 LLM 构造器

    注意：请求 silicon_flow 但未配置密钥时，**自动回退本地 Ollama**（不再抛异常），
          避免上层 Agent 因缺密钥整体降级为规则模式。回退前的策略仍可通过
          `silicon_flow_available()` 单独判断。
    """
    strategy = strategy or settings.LLM_STRATEGY or "ollama"

    if strategy == "silicon_flow":
        if not silicon_flow_available():
            logger.warning(
                "[LLM] 请求 silicon_flow 策略但 SILICON_FLOW_API_KEY 未配置，"
                "自动回退本地 Ollama（model=%s）", settings.LLM_MODEL
            )
            return _build_ollama_llm(model=None, temperature=temperature, **kwargs)
        llm = _build_silicon_flow_llm(model=model, temperature=temperature, **kwargs)
        logger.info(f"[LLM] SiliconFlow initialized: {model or settings.SILICON_FLOW_MODEL}")
        return llm

    # 已注释（2026-09-02）：ali_bailian 分支实际未使用（Dify中台用 workflow，不在本项目调 LLM）
    # if strategy == "ali_bailian":
    #     llm = _build_ali_bailian_llm(model=model, temperature=temperature, **kwargs)
    #     logger.info(f"[LLM] AliBailian initialized: {model or settings.ALI_BAILIAN_MODEL}")
    #     return llm

    # 默认 ollama
    llm = _build_ollama_llm(model=model, temperature=temperature, **kwargs)
    logger.info(f"[LLM] Ollama initialized: {model or settings.LLM_MODEL}")
    return llm


def get_agent_llm(temperature: float = 0.1, model: Optional[str] = None, **kwargs):
    """
    Agent 场景统一入口：优先 SiliconFlow（高精度），不可用时自动回退本地 Ollama。
    永不抛异常——全部不可用时返回 None，调用方按既定策略走规则降级。
    """
    try:
        return get_llm_by_strategy("silicon_flow", model=model, temperature=temperature, **kwargs)
    except Exception as e:
        logger.warning(f"[LLM] Agent LLM 构建失败（{e}），Agent 将使用规则降级")
        return None


def get_llm(
    strategy: Optional[str] = None,
    model: Optional[str] = None,
    temperature: float = 0.1,
    **kwargs
):
    """
    按 config.LLM_STRATEGY 返回主 LLM。
    便捷别名，内部调用 get_llm_by_strategy。
    """
    return get_llm_by_strategy(strategy=strategy, model=model, temperature=temperature, **kwargs)


# ── 专用获取器（用于特定场景）──────────────────────────────────────

def get_silicon_flow_llm(temperature: float = 0.1, model: Optional[str] = None, **kwargs) -> ChatOpenAI:
    """SiliconFlow LLM（简历解析 / NL2SQL 专用）"""
    return _build_silicon_flow_llm(model=model, temperature=temperature, **kwargs)


# 已注释（2026-09-02）：阿里百炼获取器实际未使用，保留旧代码备查：
# def get_ali_bailian_llm(temperature: float = 0.1, model: Optional[str] = None, **kwargs) -> ChatOpenAI:
#     """阿里百炼 LLM（Dify Chatflow 智能体用）"""
#     return _build_ali_bailian_llm(model=model, temperature=temperature, **kwargs)


def get_ollama_llm(temperature: float = 0.1, model: Optional[str] = None, base_url: Optional[str] = None, **kwargs) -> ChatOllama:
    """Ollama LLM（降级兜底 / 本地开发）"""
    return _build_ollama_llm(model=model, base_url=base_url, temperature=temperature, **kwargs)
