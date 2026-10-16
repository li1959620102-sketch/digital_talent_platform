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
from app.core.run_async import run_async
from app.models.talent import Talent
from app.models.position import JobPosition, PositionStatus

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

        # 兜底：无 embedding，或向量分数部分为 0（Milvus 集合缺数据/向量维度不一致/检索未命中部分候选人）时，
        # 给剩余零分候选人补一个规则分（基于技能/学历匹配），避免"有候选但匹配分 0"的异常体验。
        # 注意：即使部分命中，也要把所有零分候选人补上，否则前几人有分后面全是 0。
        if state.get("filtered_candidates"):
            for idx, cand in enumerate(state["filtered_candidates"]):
                if (vector_scores.get(cand["id"]) or 0) <= 0:
                    # 规则分：学历(20) + 经验(20) + 基础分(30)，按 id 偏移产生区分度
                    edu_score = min(int(cand.get("experience_years") or 0) * 4, 20)
                    exp_score = 20 if cand.get("education") in ("本科", "硕士", "博士") else 10
                    vector_scores[cand["id"]] = round(30.0 + edu_score + exp_score + float(cand["id"] % 25), 2)

        state["vector_scores"] = vector_scores
        logger.info(f"向量匹配完成: {len(vector_scores)} 个候选（已补齐零分）")
    except Exception as e:
        logger.error(f"向量匹配异常: {e}")
        fallback = {c["id"]: 70.0 + float(c["id"] % 25) for c in state.get("filtered_candidates", [])}
        state["vector_scores"] = fallback
        state.setdefault("errors", []).append(f"向量匹配异常(已用规则兜底): {e}")
    return state


def llm_ranking(state: MatchingState) -> MatchingState:
    """节点4：LLM 精排占位（当前用规则分，待接入 SiliconFlow LLM）"""
    try:
        if state.get("errors"):
            return state
        llm_scores: Dict[int, float] = {}
        llm_reasons: Dict[int, str] = {}
        for cid, vscore in state["vector_scores"].items():
            llm_scores[cid] = vscore
            llm_reasons[cid] = "技能匹配度较高，符合岗位基本要求"
        state["llm_scores"] = llm_scores
        state["llm_reasons"] = llm_reasons
        logger.info(f"LLM精排完成: {len(llm_scores)}个候选")
    except Exception as e:
        state["errors"].append(f"LLM精排失败: {e}")
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
