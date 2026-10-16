"""
岗位匹配 Agent（LangGraph 工作流版）
招标文件强制要求：LangGraph 有状态工作流，状态持久化，失败重试。
节点链路：load_candidates → filter_by_hard_conditions → vector_matching → llm_ranking → generate_match_results
Dify Chatflow 触发本模块 match_position endpoint。
"""
from typing import TypedDict, List, Dict, Any, Optional
from langgraph.graph import StateGraph, END
import logging

from app.agents.graph_runtime import compile_graph, invoke_graph
from app.core.database import get_mysql_session
from app.core.milvus_client import MilvusService
from app.core.config import settings
from app.core.llm_factory import get_agent_llm
from app.core.run_async import run_async
from app.models.talent import Talent
from app.models.position import JobPosition, PositionStatus
from app.utils.json_utils import extract_json

logger = logging.getLogger(__name__)


# ==================== 状态定义 ====================

class MatchingState(TypedDict):
    """LangGraph 匹配状态"""
    match_type: str
    talent_id: Optional[int]
    position_id: Optional[int]
    candidates: List[Dict[str, Any]]
    filtered_candidates: List[Dict[str, Any]]
    filter_reasons: Dict[int, List[str]]
    vector_scores: Dict[int, float]
    llm_scores: Dict[int, float]
    llm_reasons: Dict[int, str]
    match_results: List[Dict[str, Any]]
    errors: List[str]


# ==================== 学历映射 ====================

_EDU_MAP = {
    "高中": 1, "中专": 1,
    "大专": 2, "专科": 2,
    "本科": 3, "学士": 3,
    "硕士": 4, "研究生": 4,
    "博士": 5,
}


def _edu_index(edu) -> int:
    if edu is None:
        return 0
    val = edu.value if hasattr(edu, "value") else edu
    return _EDU_MAP.get(str(val).strip(), 0)


# ==================== LangGraph 节点（全部同步）====================

def _normalize_skill(s) -> str:
    """规范化单个技能条目：兼容字符串与 {name, level} 字典两种格式

    处理长字符串（如"湖仓架构与数据湖：熟悉 HDFS/OSS/MinIO..."），
    提取冒号前的核心短语（如"湖仓架构与数据湖"），用于粗粒度匹配。
    同时把 /、／ 等分隔符替换为空格，便于子串匹配。
    """
    if isinstance(s, dict):
        s = str(s.get("name") or s.get("skill") or "")
    s = str(s).strip()
    if not s:
        return ""
    # 截断到冒号前（LLM 输出格式通常是 "核心短语：详细描述"）
    if "：" in s:
        s = s.split("：")[0]
    if ":" in s:
        s = s.split(":")[0]
    # 统一替换分隔符为空格（让 "Python/Scala" 拆成两 token，下游做子串匹配）
    for sep in ["/", "／", "|", "｜", "、", "，", " ", "\t"]:
        s = s.replace(sep, " ")
    return s.lower().strip()


def _skill_tokens(items) -> List[str]:
    """把技能项切成 token 列表（支持 "Python/Scala" 这种"或"关系描述的拆分）"""
    if not items:
        return []
    result = []
    for s in items:
        n = _normalize_skill(s)
        if not n:
            continue
        # 拆分多 token（如 "python scala"），单独入库
        for tok in n.split():
            tok = tok.strip()
            if tok and len(tok) >= 2:  # 过滤掉单字符噪声
                result.append(tok)
    return result


def _skill_names(items) -> List[str]:
    """把 skill_requirements / skills_certificates 规范化为小写技能名列表"""
    if not items:
        return []
    result = []
    for s in items:
        n = _normalize_skill(s)
        if n:
            result.append(n)
    return result


# LLM 精排的候选上限：本地 CPU 模型单次推理可达数十秒，
# 只对粗排 TOP-N 做语义精排，其余沿用粗排分，避免整批候选串行推理超时。
LLM_RERANK_TOP_N = 10

_llm = None


def _get_llm():
    """惰性构建 Agent LLM：优先 SiliconFlow，未配密钥时自动回退本地 Ollama；均不可用返回 None"""
    global _llm
    if _llm is None:
        _llm = get_agent_llm(temperature=0.1)
    return _llm


def _rule_match_score(
    cand_edu,
    cand_exp,
    cand_skills,
    req_edu,
    req_exp,
    req_skills
) -> float:
    """规则匹配分（0~100）。

    权重与生产匹配接口 app/api/v1/matching.py::compute_match_score 保持一致：
    学历 30 + 经验 25 + 技能 45 + 经验加成 min(10, 年限×0.3)，学历不达标直接 0 分。

    用途：向量库无数据 / 检索未命中 / LLM 不可用时的**确定性兜底**。
    取代原先 "30 + 学历 + 经验 + id % 25" 的写法——那种分数与候选人能力无关，
    只是让分数看起来有区分度，属于伪区分度。
    """
    # 学历（不满足直接 0 分，与生产接口一致）
    if req_edu and _edu_index(cand_edu) < _edu_index(req_edu):
        return 0.0
    score = 30.0

    # 经验
    req_exp = req_exp or 0
    cand_exp = cand_exp or 0
    if req_exp > 0:
        if cand_exp >= req_exp:
            score += 25.0
        elif cand_exp > 0:
            score += round(25.0 * cand_exp / req_exp, 1)
    else:
        score += 25.0

    # 技能重叠（token 化，与节点2硬条件过滤同一套分词口径）
    req_tokens = set(_skill_tokens(req_skills))
    if req_tokens:
        cand_tokens = set(_skill_tokens(cand_skills))
        score += 45.0 * len(req_tokens & cand_tokens) / len(req_tokens)
    else:
        score += 45.0

    # 经验加成
    if cand_exp > 0 and score > 0:
        score += round(min(10.0, cand_exp * 0.3), 2)

    return round(min(100.0, score), 2)


def _fallback_rule_scores(state: MatchingState) -> Dict[int, float]:
    """向量不可用时，用规则分为全部候选生成兜底分（候选属性 vs 岗位/人才要求）"""
    result: Dict[int, float] = {}
    try:
        db = next(get_mysql_session())

        if state.get("match_type") == "talent_to_position":
            talent = db.query(Talent).filter(Talent.id == state.get("talent_id")).first()
            if not talent:
                return result
            talent_skills = (talent.skills_certificates or []) + (talent.tags or [])
            for cand in state.get("filtered_candidates") or []:
                result[cand["id"]] = _rule_match_score(
                    talent.education,
                    talent.experience_years,
                    talent_skills,
                    cand.get("education_requirement"),
                    cand.get("experience_requirement"),
                    cand.get("skill_requirements"),
                )

        elif state.get("match_type") == "position_to_talent":
            position = db.query(JobPosition).filter(
                JobPosition.id == state.get("position_id")
            ).first()
            if not position:
                return result
            for cand in state.get("filtered_candidates") or []:
                result[cand["id"]] = _rule_match_score(
                    cand.get("education"),
                    cand.get("experience_years"),
                    cand.get("skills_certificates") or [],
                    position.education_requirement,
                    position.experience_requirement,
                    position.skill_requirements,
                )

    except Exception as e:
        logger.warning(f"规则兜底评分失败: {e}")
    return result


def load_candidates(state: MatchingState) -> MatchingState:
    """节点1：从 MySQL 加载候选数据"""
    try:
        db = next(get_mysql_session())
        if state["match_type"] == "talent_to_position":
            positions = db.query(JobPosition).filter(
                JobPosition.status == PositionStatus.OPEN
            ).limit(50).all()
            state["candidates"] = [
                {
                    "id": p.id,
                    "position_name": p.position_name,
                    "education_requirement": p.education_requirement,
                    "experience_requirement": p.experience_requirement,
                    "skill_requirements": p.skill_requirements or [],
                    "salary_min": p.salary_min,
                    "salary_max": p.salary_max
                }
                for p in positions
            ]
            # 同时把目标人才的完整能力画像（skills_certificates + tags）传给后续过滤节点
            # 这样岗位的 skill_requirements（短词）能与人才的 tags（短词）匹配
            # （避免 LLM 输出的长技能名与岗位短词匹配失败）
            # 注意：存 list（不是 set），msgpack 才能序列化
            if state.get("talent_id"):
                t = db.query(Talent).filter(Talent.id == state["talent_id"]).first()
                if t:
                    state["talent_skills_pool"] = list(set(_skill_tokens(
                        (t.skills_certificates or []) + (t.tags or [])
                    )))
        elif state["match_type"] == "position_to_talent":
            talents = db.query(Talent).limit(50).all()
            state["candidates"] = [
                {
                    "id": t.id,
                    "name": t.name,
                    "education": t.education.value if t.education else None,
                    "experience_years": t.experience_years or 0,
                    "skills_certificates": t.skills_certificates or [],
                    "expected_salary_min": t.expected_salary_min,
                    "expected_salary_max": t.expected_salary_max
                }
                for t in talents
            ]
        logger.info(f"加载候选数据: {len(state['candidates'])}条")
    except Exception as e:
        state["errors"].append(f"加载候选数据失败: {e}")
    return state


def filter_by_hard_conditions(state: MatchingState) -> MatchingState:
    """节点2：硬条件过滤（学历/年限/技能），学历比较方向已修正（≥）"""
    try:
        if state.get("errors"):
            return state
        db = next(get_mysql_session())
        filtered = []
        filter_reasons: Dict[int, List[str]] = {}

        if state["match_type"] == "talent_to_position":
            talent = db.query(Talent).filter(Talent.id == state["talent_id"]).first()
            if not talent:
                state["errors"].append("人才不存在")
                return state
            for cand in state["candidates"]:
                reasons = []
                # 学历：人才学历未知(None，如简历解析遗漏)时不剔除，放行交给向量/LLM 精排
                #      语义判断；仅已知学历才做严格 >= 比较。
                talent_edu = talent.education
                if cand.get("education_requirement") and talent_edu is not None:
                    # 学历需不低于要求 → 用 >= 比较
                    if _edu_index(talent_edu) < _edu_index(cand["education_requirement"]):
                        reasons.append(
                            f"学历不足: 要求{cand['education_requirement']}，"
                            f"实际{talent_edu.value if hasattr(talent_edu, 'value') else talent_edu}"
                        )
                elif cand.get("education_requirement") and talent_edu is None:
                    # 未知学历：不过滤，让 LLM 精排结合岗位做语义判断
                    filter_reasons.setdefault(cand["id"], []).append(
                        f"学历未知，交由精排判断（岗位要求{cand['education_requirement']}）"
                    )
                if cand.get("experience_requirement"):
                    if (talent.experience_years or 0) < cand["experience_requirement"]:
                        reasons.append(
                            f"年限不足: 要求{cand['experience_requirement']}年，"
                            f"实际{talent.experience_years}年"
                        )
                if cand.get("skill_requirements"):
                    # 优先用预聚合的 talent_skills_pool（含 skills_certificates + tags 短词，已拆分 token）
                    talent_tokens = set(state.get("talent_skills_pool") or [])
                    if not talent_tokens:
                        # fallback：从 ORM 重新聚合（兼容 state 被序列化后丢失的场景）
                        talent_tokens = set(_skill_tokens(
                            (talent.skills_certificates or []) + (talent.tags or [])
                        ))
                    req_tokens = _skill_tokens(cand["skill_requirements"])
                    if req_tokens:
                        # 双向子串匹配：人才 token 是岗位 token 子串 或 反之（兼容 Python/scala vs python）
                        def _hit(req, pool):
                            if req in pool:
                                return True
                            for p in pool:
                                if len(p) >= 3 and (req in p or p in req):
                                    return True
                            return False
                        missing = [s for s in req_tokens if not _hit(s, talent_tokens)]
                        hit_count = len(req_tokens) - len(missing)
                        # 宽松策略：
                        # - 完全 0 命中 → 剔除（避免完全无关岗位进入LLM精排浪费token）
                        # - 部分命中（≥1）→ 通过硬条件过滤，让 LLM 精排阶段做语义评分
                        # - 全命中 → 通过
                        if hit_count == 0:
                            reasons.append(f"缺少任一技能: {', '.join(req_tokens)}")
                        elif hit_count < len(req_tokens):
                            # 部分匹配，记录但通过
                            filter_reasons.setdefault(cand["id"], []).append(
                                f"部分匹配技能 {hit_count}/{len(req_tokens)}: 缺{', '.join(missing)}"
                            )
                if not reasons:
                    filtered.append(cand)
                else:
                    filter_reasons[cand["id"]] = reasons

        elif state["match_type"] == "position_to_talent":
            position = db.query(JobPosition).filter(JobPosition.id == state["position_id"]).first()
            if not position:
                state["errors"].append("岗位不存在")
                return state
            for cand in state["candidates"]:
                reasons = []
                # 学历：人才学历未知(None)时不剔除，放行交精排语义判断；仅已知才严格比较。
                cand_edu = cand.get("education")
                if position.education_requirement and cand_edu is not None:
                    if _edu_index(cand_edu) < _edu_index(position.education_requirement):
                        reasons.append(
                            f"学历不足: 要求{position.education_requirement}，"
                            f"实际{cand.get('education')}"
                        )
                elif position.education_requirement and cand_edu is None:
                    filter_reasons.setdefault(cand["id"], []).append(
                        f"学历未知，交由精排判断（岗位要求{position.education_requirement}）"
                    )
                if position.experience_requirement:
                    if (cand.get("experience_years") or 0) < position.experience_requirement:
                        reasons.append(
                            f"年限不足: 要求{position.experience_requirement}年，"
                            f"实际{cand.get('experience_years')}"
                        )
                if position.skill_requirements:
                    # 修正：与 talent_to_position 方向对齐，改用 token 化 + 双向子串的宽松策略，
                    # 完全 0 命中才剔除，部分命中通过（交向量/LLM 精排做语义评分）。
                    # 原实现用 _skill_names 严格相等匹配，岗位要求"分布式"这类泛技能时，
                    # 人才技能标"分布式系统/hadoop/spark"都算缺失，导致 45 人全被过滤（空结果）。
                    cand_tokens = set(_skill_tokens(cand.get("skills_certificates") or []))
                    req_tokens = _skill_tokens(position.skill_requirements)
                    if req_tokens:
                        def _hit(req, pool):
                            if req in pool:
                                return True
                            for p in pool:
                                if len(p) >= 3 and (req in p or p in req):
                                    return True
                            return False
                        missing = [s for s in req_tokens if not _hit(s, cand_tokens)]
                        hit_count = len(req_tokens) - len(missing)
                        if hit_count == 0:
                            reasons.append(f"缺少技能: {', '.join(req_tokens)}")
                        elif hit_count < len(req_tokens):
                            filter_reasons.setdefault(cand["id"], []).append(
                                f"部分匹配技能 {hit_count}/{len(req_tokens)}: 缺{', '.join(missing)}"
                            )
                if not reasons:
                    filtered.append(cand)
                else:
                    filter_reasons[cand["id"]] = reasons

        state["filtered_candidates"] = filtered
        state["filter_reasons"] = filter_reasons
        logger.info(f"硬条件过滤: {len(state['candidates'])}→{len(filtered)}条")
    except Exception as e:
        state["errors"].append(f"硬条件过滤失败: {e}")
    return state


def vector_matching(state: MatchingState) -> MatchingState:
    """
    节点3：向量匹配（真实 Milvus 检索，同步驱动）
    talent_to_position: 人才 embedding → job_position 集合检索
    position_to_talent: 岗位 embedding → talent_resume 集合检索
    """
    try:
        if state.get("errors"):
            return state

        ms_talent = MilvusService(settings.MILVUS_COLLECTION_TALENT)
        ms_job = MilvusService(settings.MILVUS_COLLECTION_JOB)
        vector_scores: Dict[int, float] = {}

        if state["match_type"] == "talent_to_position":
            tid = state["talent_id"]
            try:
                # 查人才 embedding（async → run_async 同步驱动）
                emb_results = run_async(ms_talent.query(
                    expr=f'talent_id == "{tid}"',
                    output_fields=["talent_id", "embedding"],
                    limit=1,
                ))
            except Exception as ex:
                logger.warning(f"Milvus 查 talent embedding 失败: {ex}")
                emb_results = []

            if emb_results:
                emb = emb_results[0].get("embedding")
                if emb:
                    try:
                        pos_results = run_async(ms_job.search(
                            query_embedding=emb,
                            top_k=20,
                            output_fields=["position_id", "position_name"],
                        ))
                    except Exception as ex:
                        logger.warning(f"Milvus job_position 检索失败: {ex}")
                        pos_results = []

                    pos_score_map: Dict[int, float] = {}
                    for hit in pos_results:
                        # hit 是 Dict，hit["score"] 为余弦相似度（0~1）
                        raw = float(hit.get("score", 0))
                        pos_score_map[int(hit["position_id"])] = round(min(raw * 100, 100), 2)

                    for cand in state["filtered_candidates"]:
                        vector_scores[cand["id"]] = pos_score_map.get(cand["id"], 0.0)
                    logger.info(f"向量匹配: 人才 {tid} 命中 {len(pos_score_map)} 个岗位")

        elif state["match_type"] == "position_to_talent":
            pid = state["position_id"]
            try:
                emb_results = run_async(ms_job.query(
                    expr=f'position_id == "{pid}"',
                    output_fields=["position_id", "embedding"],
                    limit=1,
                ))
            except Exception as ex:
                logger.warning(f"Milvus 查 position embedding 失败: {ex}")
                emb_results = []

            if emb_results:
                emb = emb_results[0].get("embedding")
                if emb:
                    try:
                        talent_results = run_async(ms_talent.search(
                            query_embedding=emb,
                            top_k=20,
                            output_fields=["talent_id", "resume_text"],
                        ))
                    except Exception as ex:
                        logger.warning(f"Milvus talent_resume 检索失败: {ex}")
                        talent_results = []

                    talent_score_map: Dict[int, float] = {}
                    for hit in talent_results:
                        raw = float(hit.get("score", 0))
                        talent_score_map[int(hit["talent_id"])] = round(min(raw * 100, 100), 2)

                    for cand in state["filtered_candidates"]:
                        vector_scores[cand["id"]] = talent_score_map.get(cand["id"], 0.0)
                    logger.info(f"向量匹配: 岗位 {pid} 命中 {len(talent_score_map)} 个人才")

        # 兜底：Milvus 集合无数据 / 向量维度不一致 / 检索未命中时，用与生产匹配接口
        # 一致的规则分为候选补齐，保证"有候选就有可解释的分数"。
        # 原实现用 "30 + 学历 + 经验 + id % 25" 补齐，分数与候选人能力无关，已移除。
        if state.get("filtered_candidates"):
            fallback_scores = _fallback_rule_scores(state)
            filled = 0
            for cand in state["filtered_candidates"]:
                if (vector_scores.get(cand["id"]) or 0) <= 0:
                    vector_scores[cand["id"]] = fallback_scores.get(cand["id"], 0.0)
                    filled += 1
            if filled:
                logger.info(f"向量未命中，已用规则分补齐 {filled} 个候选")

        state["vector_scores"] = vector_scores
        logger.info(f"向量匹配完成: {len(vector_scores)} 个候选")
    except Exception as e:
        # 向量环节异常不应让整条匹配链路失败：退化为纯规则分继续往下走。
        # （原实现把异常写进 state["errors"]，而下游节点见到 errors 会直接返回，
        #   结果是 Milvus 一抖就"候选全在、结果为空"。）
        logger.error(f"向量匹配异常，退化为规则评分: {e}")
        state["vector_scores"] = _fallback_rule_scores(state)
    return state


def _build_rerank_prompt(state: MatchingState, ranked: List[tuple]) -> str:
    """构造 LLM 精排提示词：目标画像 + 候选清单，要求返回 JSON 数组

    ranked 元素为 (候选id, 候选dict, 粗排分)
    """
    header = [
        "你是资深招聘顾问，请结合【目标画像】评估【候选清单】中每一项的匹配度。",
        "评分范围 0~100，必须体现真实契合度差异，不要给所有项相同或接近的高分。",
    ]
    body: List[str] = []

    if state.get("match_type") == "talent_to_position":
        pool = state.get("talent_skills_pool") or []
        body.append("【目标画像】人才技能：" + ("、".join(pool)[:600] or "未知"))
        body.append("【候选清单】岗位（评价该人才与每个岗位的匹配度）")
        for cid, cand, coarse in ranked:
            req_skills = "、".join(_skill_names(cand.get("skill_requirements") or []))[:200] or "不限"
            body.append(
                f"- id={cid}｜{cand.get('position_name') or '未知岗位'}"
                f"｜学历要求:{cand.get('education_requirement') or '不限'}"
                f"｜经验要求:{cand.get('experience_requirement') or '不限'}年"
                f"｜技能要求:{req_skills}"
                f"｜粗排分:{coarse}"
            )
    else:
        position = None
        try:
            db = next(get_mysql_session())
            position = db.query(JobPosition).filter(
                JobPosition.id == state.get("position_id")
            ).first()
        except Exception as e:
            logger.warning(f"精排提示词加载岗位失败: {e}")

        if position:
            req_skills = "、".join(_skill_names(position.skill_requirements or []))[:300] or "不限"
            body.append(
                "【目标画像】岗位："
                f"{position.position_name}"
                f"｜学历要求:{position.education_requirement or '不限'}"
                f"｜经验要求:{position.experience_requirement or '不限'}年"
                f"｜技能要求:{req_skills}"
                f"｜岗位描述:{str(position.job_description or '')[:200]}"
            )
        else:
            body.append("【目标画像】岗位要求未获取到，请按候选人之间的相对水平评分")

        body.append("【候选清单】人才")
        for cid, cand, coarse in ranked:
            skills = "、".join(_skill_names(cand.get("skills_certificates") or []))[:200] or "未知"
            body.append(
                f"- id={cid}｜{cand.get('name') or '匿名'}"
                f"｜学历:{cand.get('education') or '未知'}"
                f"｜经验:{cand.get('experience_years') or 0}年"
                f"｜技能:{skills}"
                f"｜粗排分:{coarse}"
            )

    footer = [
        "",
        "只返回 JSON 数组，不要任何多余文字，格式：",
        '[{"id": <候选id>, "score": <0-100的整数>, "reason": "<20字以内推荐理由>"}]',
    ]
    return "\n".join(header + body + footer)


def llm_ranking(state: MatchingState) -> MatchingState:
    """
    节点4：LLM 精排

    在粗排（向量/规则）基础上，让 LLM 结合岗位要求与候选人画像做语义精排，
    输出 0~100 的精排分与推荐理由。

    - 仅对粗排 TOP LLM_RERANK_TOP_N 名做精排：本地 CPU 模型单次推理可达数十秒，
      全量精排必然超时；其余候选沿用粗排分。
    - LLM 不可用 / 返回不可解析 / 调用异常 → 一律沿用粗排分，理由标注规则口径，
      不写 state["errors"]（否则下游节点见到 errors 会直接返回空结果）。
    """
    candidates = state.get("filtered_candidates") or []
    coarse = state.get("vector_scores") or {}

    # 默认结果 = 粗排分，保证任何异常路径下都有可解释的分数
    llm_scores: Dict[int, float] = {c["id"]: coarse.get(c["id"], 0.0) for c in candidates}
    llm_reasons: Dict[int, str] = {c["id"]: "规则评分" for c in candidates}

    try:
        if state.get("errors") or not candidates:
            state["llm_scores"] = llm_scores
            state["llm_reasons"] = llm_reasons
            return state

        llm = _get_llm()
        if llm is None:
            logger.info("LLM 不可用，精排沿用粗排分")
            state["llm_scores"] = llm_scores
            state["llm_reasons"] = llm_reasons
            return state

        top = sorted(candidates, key=lambda c: coarse.get(c["id"], 0.0), reverse=True)[:LLM_RERANK_TOP_N]
        prompt = _build_rerank_prompt(
            state, [(c["id"], c, coarse.get(c["id"], 0.0)) for c in top]
        )
        resp = llm.invoke(prompt)
        content = resp.content if hasattr(resp, "content") else str(resp)
        parsed = extract_json(content, default=[]) or []
        if not isinstance(parsed, list):
            parsed = [parsed]

        applied = 0
        for item in parsed:
            if not isinstance(item, dict):
                continue
            try:
                cid = int(item.get("id"))
                score = float(item.get("score"))
            except (TypeError, ValueError):
                continue
            if cid not in llm_scores:
                continue
            llm_scores[cid] = round(max(0.0, min(100.0, score)), 2)
            reason = str(item.get("reason") or "").strip()
            if reason:
                llm_reasons[cid] = reason[:200]
            applied += 1

        state["llm_scores"] = llm_scores
        state["llm_reasons"] = llm_reasons
        logger.info(f"LLM精排完成: 候选 {len(candidates)} 个，实际精排 {applied}/{len(top)} 个")

    except Exception as e:
        logger.warning(f"LLM精排失败（沿用粗排分）: {e}")
        state["llm_scores"] = llm_scores
        state["llm_reasons"] = llm_reasons
    return state


def generate_match_results(state: MatchingState) -> MatchingState:
    """节点5：加权求和 → 排序 → 取 TOP10，生成 MatchRecord"""
    try:
        if state.get("errors"):
            return state
        results = []
        for cand in state["filtered_candidates"]:
            cid = cand["id"]
            vscore = state["vector_scores"].get(cid, 0)
            lscore = state["llm_scores"].get(cid, 0)
            final = round(vscore * 0.4 + lscore * 0.6, 2)
            # 同时输出 position_id 和 id（前端根据字段名取值，兼容老字段）
            row = {
                **cand,
                "id": cid,
                "position_id": cid,  # 兼容前端用 position_id 取值
                "vector_score": round(vscore, 2),
                "llm_score": round(lscore, 2),
                "final_score": final,
                "match_reason": state["llm_reasons"].get(cid, "")
            }
            results.append(row)
        results.sort(key=lambda x: x["final_score"], reverse=True)
        state["match_results"] = results[:10]
        logger.info(f"生成匹配结果: {len(state['match_results'])}条")
    except Exception as e:
        state["errors"].append(f"生成匹配结果失败: {e}")
    return state


# ==================== 工作流构建 ====================

_workflow = None


def _get_workflow():
    global _workflow
    if _workflow is None:
        wf = StateGraph(MatchingState)
        wf.add_node("load_candidates", load_candidates)
        wf.add_node("filter", filter_by_hard_conditions)
        wf.add_node("vector_match", vector_matching)
        wf.add_node("llm_rank", llm_ranking)
        wf.add_node("generate_results", generate_match_results)
        wf.set_entry_point("load_candidates")
        wf.add_edge("load_candidates", "filter")
        wf.add_edge("filter", "vector_match")
        wf.add_edge("vector_match", "llm_rank")
        wf.add_edge("llm_rank", "generate_results")
        wf.add_edge("generate_results", END)
        _workflow = compile_graph(wf)  # 注入 checkpointer 状态持久化
    return _workflow


# ==================== 公开接口 ====================

class MatchingAgent:
    def __init__(self):
        self._graph = _get_workflow()

    def _run(self, state: MatchingState) -> Dict[str, Any]:
        final = invoke_graph(self._graph, state)
        if final.get("errors"):
            return {"success": False, "errors": final["errors"]}
        return {
            "success": True,
            "talent_id": state.get("talent_id"),
            "position_id": state.get("position_id"),
            "match_type": state["match_type"],
            "total_candidates": len(final["candidates"]),
            "filtered_candidates": len(final["filtered_candidates"]),
            "match_results": final["match_results"]
        }

    def match_talent_to_positions(self, talent_id: int) -> Dict[str, Any]:
        return self._run({
            "match_type": "talent_to_position",
            "talent_id": talent_id,
            "position_id": None,
            "candidates": [], "filtered_candidates": [], "filter_reasons": {},
            "vector_scores": {}, "llm_scores": {}, "llm_reasons": {},
            "match_results": [], "errors": []
        })

    def match_position_to_talents(self, position_id: int) -> Dict[str, Any]:
        return self._run({
            "match_type": "position_to_talent",
            "talent_id": None,
            "position_id": position_id,
            "candidates": [], "filtered_candidates": [], "filter_reasons": {},
            "vector_scores": {}, "llm_scores": {}, "llm_reasons": {},
            "match_results": [], "errors": []
        })


matching_agent = MatchingAgent()
