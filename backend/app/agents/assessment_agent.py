"""
测评分析Agent
基于LangGraph实现测评结果分析、雷达图生成、优劣分析、发展建议
"""
from typing import TypedDict, List, Dict, Any, Optional
from langgraph.graph import StateGraph, END
import logging
import json

from app.agents.graph_runtime import compile_graph, invoke_graph
from app.services.assessment_service import AssessmentService
from app.services.vector_search_service import VectorSearchService
from app.core.config import settings

logger = logging.getLogger(__name__)


def _simple_check_answer(user_answer, correct_answer, question_type: str) -> bool:
    """
    简化的答案比对（兼容历史脏数据：answers JSON 缺少 is_correct 字段）。
    覆盖四种基本题型：单选、多选、判断、填空。
    与 AssessmentService._check_answer 语义一致，但作为静态函数可独立调用。
    """
    try:
        # 兼容 enum 字符串（如 "QuestionType.SINGLE_CHOICE"）与纯字符串两种
        qt = str(question_type or "").lower()
        # 提取 enum 名（如 "QuestionType.SINGLE_CHOICE" → "single_choice"）
        if "questiontype" in qt:
            qt = qt.split(".")[-1]
        if "single" in qt:
            return str(user_answer).strip().upper() == str(correct_answer).strip().upper()
        if "multiple" in qt:
            def parse_set(val):
                if isinstance(val, list):
                    return set(str(v).strip().upper() for v in val)
                return set(str(val).replace("，", ",").replace("|", ",").split(","))
            return parse_set(user_answer) == parse_set(correct_answer)
        if "true" in qt or "false" in qt or "judge" in qt or "boolean" in qt:
            truthy = {"true", "t", "1", "正确", "对", "yes", "y"}
            falsey = {"false", "f", "0", "错误", "错", "no", "n"}
            ua, ca = str(user_answer).strip().lower(), str(correct_answer).strip().lower()
            if ca in truthy:
                return ua in truthy
            if ca in falsey:
                return ua in falsey
            return ua == ca
        # 填空题/简答题：宽松匹配（去除空格/标点）
        return str(user_answer).strip().replace(" ", "") == str(correct_answer).strip().replace(" ", "")
    except Exception as e:
        logger.warning(f"答案比对失败: {e}")
        return False


# ==================== 状态定义 ====================

class AssessmentAnalysisState(TypedDict):
    """测评分析状态"""
    result_id: int
    talent_id: int

    # 输入数据
    total_score: float
    correct_count: int
    total_count: int
    answer_details: List[Dict[str, Any]]

    # 分析结果
    category_scores: Dict[str, float]  # 分类得分
    strengths: List[str]  # 优势
    weaknesses: List[str]  # 劣势
    ability_level: str  # 能力评级
    radar_chart_data: List[Dict[str, Any]]  # 雷达图数据

    # 建议
    development_suggestions: List[str]  # 发展建议
    recommended_courses: List[Dict[str, Any]]  # 推荐课程

    # 错误信息
    errors: List[str]


# ==================== 节点函数 ====================

def load_result_data(state: AssessmentAnalysisState) -> AssessmentAnalysisState:
    """加载测评结果数据"""
    try:
        from app.core.database import get_mysql_session
        from app.models.assessment import AssessmentResult

        db = next(get_mysql_session())
        result = db.query(AssessmentResult).filter(AssessmentResult.id == state["result_id"]).first()

        if not result:
            state["errors"].append(f"测评结果不存在: {state['result_id']}")
            return state

        # 解析答题详情（实际字段为 answers，存储为JSON字符串）
        answer_details = json.loads(result.answers) if isinstance(result.answers, str) else result.answers
        total_count = result.correct_count + result.wrong_count + result.unanswered_count

        state.update({
            "talent_id": result.talent_id,
            "total_score": float(result.total_score),
            "correct_count": result.correct_count,
            "total_count": total_count,
            "answer_details": answer_details
        })

        logger.info(f"加载测评结果成功: result_id={state['result_id']}")
        return state

    except Exception as e:
        state["errors"].append(f"加载测评结果失败: {str(e)}")
        return state


def analyze_category_scores(state: AssessmentAnalysisState) -> AssessmentAnalysisState:
    """分析分类得分（同时回填真实正确数 / 总分，避免综合分/分维度矛盾）"""
    try:
        from app.core.database import get_mysql_session
        from app.models.assessment import Question

        if state.get("errors"):
            return state

        db = next(get_mysql_session())

        # 获取题目信息
        question_ids = [a["question_id"] for a in state["answer_details"]]
        questions = db.query(Question).filter(Question.id.in_(question_ids)).all()
        question_map = {q.id: q for q in questions}

        # 按分类统计；同时累计"当场比对"得到的真实正确数与得分
        category_stats = {}
        real_correct = 0
        max_total_score = 0.0  # 卷面满分（所有题目分值之和）
        gained_total_score = 0.0  # 实际得分（答对的题分之和）
        for answer in state["answer_details"]:
            question = question_map.get(answer["question_id"])
            if not question:
                continue

            category = question.question_category or "未分类"
            if category not in category_stats:
                category_stats[category] = {"correct": 0, "total": 0, "score": 0, "max_score": 0}

            category_stats[category]["total"] += 1
            q_score = float(question.score_value or 0)
            category_stats[category]["max_score"] += q_score
            max_total_score += q_score

            # 优先使用答案里的 is_correct（新版数据）；缺字段则当场比对正确答案回填
            is_correct = answer.get("is_correct")
            if is_correct is None:
                is_correct = answer.get("correct", False)
            # 老数据：answer/correct 字段均不存在时，按题目正确答案比对
            if not is_correct:
                user_ans = answer.get("user_answer") or answer.get("answer")
                if user_ans is not None and user_ans != "" and question.correct_answer:
                    is_correct = _simple_check_answer(
                        user_ans, question.correct_answer, str(question.question_type or "")
                    )
            if is_correct:
                category_stats[category]["correct"] += 1
                category_stats[category]["score"] += q_score
                real_correct += 1
                gained_total_score += q_score

        # 计算得分率
        category_scores = {}
        for category, stats in category_stats.items():
            score_rate = (stats["score"] / stats["max_score"] * 100) if stats["max_score"] > 0 else 0
            category_scores[category] = round(score_rate, 1)

        # 关键：把"当场比对"的真实正确数和得分回填到 state，
        # 让后续 calculate_ability_level / 雷达图与分维度数据一致（不再 100% 维度 + 80% 综合分）
        state["correct_count"] = real_correct
        state["total_count"] = max(state.get("total_count") or 0, len(question_ids))
        # 综合得分统一为「相对率」（0-100），与分维度得分数值口径一致，避免用户迷惑
        state["total_score"] = round(gained_total_score / max_total_score * 100, 1) if max_total_score > 0 else 0
        state["max_total_score"] = max_total_score  # 卷面满分（保留绝对值，前端用不到）
        state["category_scores"] = category_scores
        logger.info(f"分类得分分析完成: {category_scores} | 真实得分 {gained_total_score}/{max_total_score} ({real_correct}/{len(question_ids)} 答对)")
        return state

    except Exception as e:
        state["errors"].append(f"分析分类得分失败: {str(e)}")
        return state


def identify_strengths_weaknesses(state: AssessmentAnalysisState) -> AssessmentAnalysisState:
    """识别优势和劣势"""
    try:
        if state.get("errors"):
            return state

        category_scores = state.get("category_scores", {})

        strengths = []
        weaknesses = []

        for category, score in category_scores.items():
            if score >= 80:
                strengths.append(f"{category}: {score:.1f}分")
            elif score < 60:
                weaknesses.append(f"{category}: {score:.1f}分")

        state["strengths"] = strengths
        state["weaknesses"] = weaknesses

        logger.info(f"优势: {strengths}, 劣势: {weaknesses}")
        return state

    except Exception as e:
        state["errors"].append(f"识别优劣势失败: {str(e)}")
        return state


def calculate_ability_level(state: AssessmentAnalysisState) -> AssessmentAnalysisState:
    """计算能力评级"""
    try:
        if state.get("errors"):
            return state

        # 计算总体正确率
        correct_rate = (state["correct_count"] / state["total_count"] * 100) if state["total_count"] > 0 else 0

        # 评级标准
        if correct_rate >= 90:
            ability_level = "核心人才"
        elif correct_rate >= 80:
            ability_level = "骨干"
        elif correct_rate >= 70:
            ability_level = "高级"
        elif correct_rate >= 60:
            ability_level = "中级"
        else:
            ability_level = "初级"

        state["ability_level"] = ability_level
        logger.info(f"能力评级: {ability_level} (正确率: {correct_rate:.1f}%)")
        return state

    except Exception as e:
        state["errors"].append(f"计算能力评级失败: {str(e)}")
        return state


def generate_radar_chart(state: AssessmentAnalysisState) -> AssessmentAnalysisState:
    """生成雷达图数据"""
    try:
        if state.get("errors"):
            return state

        category_scores = state.get("category_scores", {})

        radar_data = [
            {
                "category": category,
                "score": score,
                "max_score": 100
            }
            for category, score in category_scores.items()
        ]

        state["radar_chart_data"] = radar_data
        logger.info(f"雷达图数据生成完成: {len(radar_data)}个维度")
        return state

    except Exception as e:
        state["errors"].append(f"生成雷达图失败: {str(e)}")
        return state


def generate_development_suggestions(state: AssessmentAnalysisState) -> AssessmentAnalysisState:
    """生成发展建议"""
    try:
        if state.get("errors"):
            return state

        suggestions = []
        weaknesses = state.get("weaknesses", [])

        # 基于劣势生成建议
        for weakness in weaknesses:
            category = weakness.split(":")[0]
            suggestions.append(f"建议加强{category}能力的学习和训练")

        # 通用建议
        if state.get("ability_level") == "初级":
            suggestions.append("建议参加基础能力培训课程")
        elif state.get("ability_level") == "中级":
            suggestions.append("建议参与项目实践，提升综合能力")

        state["development_suggestions"] = suggestions
        logger.info(f"发展建议生成完成: {suggestions}")
        return state

    except Exception as e:
        state["errors"].append(f"生成发展建议失败: {str(e)}")
        return state


def recommend_courses(state: AssessmentAnalysisState) -> AssessmentAnalysisState:
    """推荐课程：基于短板分类匹配真实课程库（与培训赋能 Agent 同源，口径一致）"""
    try:
        if state.get("errors"):
            return state

        from app.core.database import get_mysql_session
        from app.models.training import Course

        db = next(get_mysql_session())
        weaknesses = state.get("weaknesses", [])

        # 测评短板分类 → 课程类别映射
        _CATEGORY_MAP = {
            "专业": {"skill"},          # 专业技能短板 → 技能类课程
            "综合": {"profession"},     # 综合素质短板 → 职业素养课程
            "岗位": {"position"},       # 岗位能力短板 → 岗位类课程
            "性格": {"level"},          # 性格短板 → 通用/软技能课程
            "抗压": {"level"},
            "团队": {"level"},
        }
        weak_categories = [w.split(":")[0] for w in weaknesses]
        target_cats = set()
        for wc in weak_categories:
            target_cats |= _CATEGORY_MAP.get(wc, {"skill"})

        # 查询真实课程库
        try:
            courses = db.query(Course).filter(
                Course.status.in_(["published", "active", "PUBLISHED", "ACTIVE"])
            ).all()
        except Exception:
            courses = db.query(Course).all()

        recommended = []
        for c in courses:
            cat = getattr(c, "course_category", None)
            cat_val = cat.value if hasattr(cat, "value") else str(cat or "")
            if cat_val in target_cats:
                recommended.append({
                    "course_id": c.id,
                    "course_name": c.course_name,
                    "course_type": cat_val,
                    "difficulty": "中级",
                    "duration": "按课程",
                    "tags": c.tags if isinstance(c.tags, list) else [],
                })

        # 兜底：短板分类无匹配课程时，退化为推荐技能类课程
        if not recommended:
            for c in courses:
                cat = getattr(c, "course_category", None)
                cat_val = cat.value if hasattr(cat, "value") else str(cat or "")
                if cat_val == "skill":
                    recommended.append({
                        "course_id": c.id,
                        "course_name": c.course_name,
                        "course_type": "skill",
                        "difficulty": "中级",
                        "duration": "按课程",
                        "tags": c.tags if isinstance(c.tags, list) else [],
                    })
                if len(recommended) >= 3:
                    break

        state["recommended_courses"] = recommended[:3]
        logger.info(f"推荐课程: {[c['course_name'] for c in recommended]}")
        return state

    except Exception as e:
        state["errors"].append(f"推荐课程失败: {str(e)}")
        state["recommended_courses"] = []
        return state


# ==================== 工作流构建 ====================

def build_assessment_agent():
    """构建测评分析Agent"""
    workflow = StateGraph(AssessmentAnalysisState)

    # 添加节点
    workflow.add_node("load_result", load_result_data)
    workflow.add_node("analyze_categories", analyze_category_scores)
    workflow.add_node("identify_strengths", identify_strengths_weaknesses)
    workflow.add_node("calculate_level", calculate_ability_level)
    workflow.add_node("generate_radar", generate_radar_chart)
    workflow.add_node("generate_suggestions", generate_development_suggestions)
    workflow.add_node("recommend_courses", recommend_courses)

    # 设置入口
    workflow.set_entry_point("load_result")

    # 添加边
    workflow.add_edge("load_result", "analyze_categories")
    workflow.add_edge("analyze_categories", "identify_strengths")
    workflow.add_edge("identify_strengths", "calculate_level")
    workflow.add_edge("calculate_level", "generate_radar")
    workflow.add_edge("generate_radar", "generate_suggestions")
    workflow.add_edge("generate_suggestions", "recommend_courses")
    workflow.add_edge("recommend_courses", END)

    return compile_graph(workflow)  # 注入 checkpointer 状态持久化


# ==================== Agent接口 ====================

class AssessmentAnalysisAgent:
    """测评分析Agent"""

    def __init__(self):
        self.agent = build_assessment_agent()

    def analyze(self, result_id: int) -> Dict[str, Any]:
        """执行测评分析"""
        try:
            # 初始化状态
            initial_state = {
                "result_id": result_id,
                "talent_id": 0,
                "total_score": 0,
                "correct_count": 0,
                "total_count": 0,
                "answer_details": [],
                "category_scores": {},
                "strengths": [],
                "weaknesses": [],
                "ability_level": "",
                "radar_chart_data": [],
                "development_suggestions": [],
                "recommended_courses": [],
                "errors": []
            }

            # 执行工作流
            final_state = invoke_graph(self.agent, initial_state)

            # 检查错误
            if final_state.get("errors"):
                logger.error(f"测评分析出错: {final_state['errors']}")
                return {
                    "success": False,
                    "errors": final_state["errors"]
                }

            # 返回结果
            return {
                "success": True,
                "result_id": result_id,
                "talent_id": final_state["talent_id"],
                "total_score": final_state["total_score"],
                "correct_rate": (final_state["correct_count"] / final_state["total_count"] * 100) if final_state["total_count"] > 0 else 0,
                "category_scores": final_state["category_scores"],
                "strengths": final_state["strengths"],
                "weaknesses": final_state["weaknesses"],
                "ability_level": final_state["ability_level"],
                "radar_chart_data": final_state["radar_chart_data"],
                "development_suggestions": final_state["development_suggestions"],
                "recommended_courses": final_state["recommended_courses"]
            }

        except Exception as e:
            logger.error(f"测评分析失败: {str(e)}")
            return {
                "success": False,
                "errors": [str(e)]
            }


# 全局实例
assessment_agent = AssessmentAnalysisAgent()
