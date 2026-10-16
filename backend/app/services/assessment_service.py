"""
测评管理服务
基于真实数据模型实现：Question / TestPaper / AssessmentTask / AssessmentResult
"""
from sqlalchemy.orm import Session
from sqlalchemy import or_
from typing import List, Optional, Dict, Any
from datetime import datetime
import json
import uuid
import logging

from app.models.assessment import (
    Question, TestPaper, AssessmentTask, AssessmentResult,
    QuestionType, AssessmentStatus, CapabilityLevel
)
from app.models.talent import Talent

logger = logging.getLogger(__name__)


class AssessmentService:
    """测评管理服务"""

    def __init__(self, db: Session):
        self.db = db

    # ==================== 题库管理 ====================

    def create_question(self, question_data: Dict[str, Any], user_id: int = None) -> Question:
        """创建题目"""
        try:
            question = Question(
                question_code=f"Q{int(datetime.now().timestamp()*1000)}{uuid.uuid4().hex[:6].upper()}",
                question_content=question_data.get("question_content") or question_data.get("question_text"),
                question_type=QuestionType(question_data.get("question_type")),
                question_category=question_data.get("question_category") or question_data.get("category"),
                options=question_data.get("options"),
                correct_answer=str(question_data.get("correct_answer")),
                answer_analysis=question_data.get("answer_analysis") or question_data.get("explanation"),
                score_value=float(question_data.get("score_value", question_data.get("score", 1))),
                difficulty=int(question_data.get("difficulty", 3)),
                capability_dimension=question_data.get("capability_dimension"),
                tags=question_data.get("tags", []),
                status=question_data.get("status", "active")
            )

            self.db.add(question)
            self.db.commit()
            self.db.refresh(question)

            logger.info(f"创建题目成功: ID={question.id}")
            return question

        except Exception as e:
            self.db.rollback()
            logger.error(f"创建题目失败: {str(e)}")
            raise

    def get_question(self, question_id: int) -> Optional[Question]:
        """获取题目详情"""
        return self.db.query(Question).filter(Question.id == question_id).first()

    def get_questions(
        self,
        page: int = 1,
        page_size: int = 20,
        question_type: Optional[str] = None,
        category: Optional[str] = None,
        difficulty: Optional[int] = None
    ) -> Dict[str, Any]:
        """获取题目列表"""
        query = self.db.query(Question)

        if question_type:
            query = query.filter(Question.question_type == QuestionType(question_type))
        if category:
            query = query.filter(Question.question_category == category)
        if difficulty is not None:
            query = query.filter(Question.difficulty == difficulty)

        total = query.count()
        questions = query.offset((page - 1) * page_size).limit(page_size).all()

        return {
            "items": questions,
            "total": total,
            "page": page,
            "page_size": page_size
        }

    # ==================== 试卷管理 ====================

    def create_paper(self, paper_data: Dict[str, Any], user_id: int = None) -> TestPaper:
        """创建试卷"""
        try:
            paper_code = self._generate_paper_code()

            paper = TestPaper(
                paper_code=paper_code,
                paper_name=paper_data.get("paper_name"),
                paper_type=paper_data.get("paper_type"),
                paper_description=paper_data.get("paper_description"),
                questions=paper_data.get("questions", []),
                total_score=float(paper_data.get("total_score", 100)),
                duration_minutes=int(paper_data.get("duration_minutes", paper_data.get("duration", 60))),
                capability_dimensions=paper_data.get("capability_dimensions", []),
                status="draft"
            )

            self.db.add(paper)
            self.db.commit()
            self.db.refresh(paper)

            logger.info(f"创建试卷成功: {paper.paper_code}")
            return paper

        except Exception as e:
            self.db.rollback()
            logger.error(f"创建试卷失败: {str(e)}")
            raise

    def publish_paper(self, paper_id: int, user_id: int = None) -> Optional[TestPaper]:
        """发布试卷"""
        try:
            paper = self.db.query(TestPaper).filter(TestPaper.id == paper_id).first()
            if not paper:
                return None

            paper.status = "published"
            self.db.commit()
            self.db.refresh(paper)

            logger.info(f"发布试卷成功: {paper.paper_code}")
            return paper

        except Exception as e:
            self.db.rollback()
            logger.error(f"发布试卷失败: {str(e)}")
            raise

    def get_paper(self, paper_id: int) -> Optional[TestPaper]:
        """获取试卷详情"""
        return self.db.query(TestPaper).filter(TestPaper.id == paper_id).first()

    def get_papers(
        self,
        page: int = 1,
        page_size: int = 20,
        paper_type: Optional[str] = None,
        status: Optional[str] = None
    ) -> Dict[str, Any]:
        """获取试卷列表"""
        query = self.db.query(TestPaper)

        if paper_type:
            query = query.filter(TestPaper.paper_type == paper_type)
        if status:
            query = query.filter(TestPaper.status == status)

        total = query.count()
        papers = query.offset((page - 1) * page_size).limit(page_size).all()

        return {
            "items": papers,
            "total": total,
            "page": page,
            "page_size": page_size
        }

    def auto_generate_paper(self, paper_data: Dict[str, Any], user_id: int = None) -> TestPaper:
        """自动组卷：根据题型/难度/数量要求，从题库随机抽题拼装成完整试卷。

        paper_data 结构：
          paper_name: str
          paper_type: str（综合测评/专业技能/...）
          paper_description: str（可选）
          duration_minutes: int（可选，默认 60）
          strategy: {
            "single_choice": 10,   # 题型 -> 抽题数量
            "multiple_choice": 5,
            "true_false": 5,
            ...
          }
          或按难度/分类过滤：
          category: str（可选，按分类抽题）
          difficulty: int（可选，按难度抽题）
        """
        import random
        try:
            strategy = paper_data.get("strategy") or {}
            category = paper_data.get("category")
            difficulty = paper_data.get("difficulty")

            # 归一化策略：题型 -> 数量
            if not strategy:
                strategy = {
                    "single_choice": 10,
                    "multiple_choice": 5,
                    "true_false": 5,
                }

            selected_questions = []
            for qtype, count in strategy.items():
                if not count or int(count) <= 0:
                    continue
                query = self.db.query(Question).filter(
                    Question.question_type == QuestionType(qtype),
                    Question.status == "active"
                )
                if category:
                    query = query.filter(Question.question_category == category)
                if difficulty:
                    query = query.filter(Question.difficulty == int(difficulty))

                candidates = query.all()
                if not candidates:
                    logger.warning(f"题型 {qtype} 无可用题目，跳过")
                    continue
                # 随机抽样（不足则全取）
                sampled = random.sample(candidates, min(int(count), len(candidates)))
                selected_questions.extend(sampled)

            if not selected_questions:
                raise ValueError("题库中没有可用的题目，请先新增题目")

            # 组装试卷题目配置：[{question_id, score}]
            paper_questions = [
                {"question_id": q.id, "score": float(q.score_value or 1)}
                for q in selected_questions
            ]
            total_score = round(sum(q["score"] for q in paper_questions), 2)
            # 能力维度汇总
            dims = list({q.capability_dimension for q in selected_questions if q.capability_dimension})

            paper = TestPaper(
                paper_code=self._generate_paper_code(),
                paper_name=paper_data.get("paper_name", "自动组卷"),
                paper_type=paper_data.get("paper_type", "综合测评"),
                paper_description=paper_data.get("paper_description", "系统自动组卷"),
                questions=paper_questions,
                total_score=total_score,
                duration_minutes=int(paper_data.get("duration_minutes", 60)),
                difficulty_distribution=paper_data.get("difficulty_distribution"),
                capability_dimensions=dims,
                status="draft"
            )
            self.db.add(paper)
            self.db.commit()
            self.db.refresh(paper)

            logger.info(f"自动组卷成功: {paper.paper_code}, 题数={len(paper_questions)}, 总分={total_score}")
            return paper
        except Exception as e:
            self.db.rollback()
            logger.error(f"自动组卷失败: {str(e)}")
            raise

    def simulate_answer(self, paper_id: int, talent_id: int, correct_rate: float = 0.8) -> Dict[str, Any]:
        """模拟答题：对指定试卷按正确率自动生成答案并评分，返回测评结果摘要。

        用于功能演示/联调验证，不产生真实人才数据依赖（talent_id 需已存在）。
        """
        import random
        try:
            paper = self.db.query(TestPaper).filter(TestPaper.id == paper_id).first()
            if not paper:
                raise ValueError("试卷不存在")

            paper_questions = paper.questions or []
            if not paper_questions:
                raise ValueError("试卷无题目")

            question_ids = [q["question_id"] for q in paper_questions]
            questions = self.db.query(Question).filter(Question.id.in_(question_ids)).all()
            question_map = {q.id: q for q in questions}

            # 生成模拟答案
            answers = []
            for qc in paper_questions:
                q = question_map.get(qc["question_id"])
                if not q:
                    continue
                # 按正确率决定答对/答错
                if random.random() < correct_rate:
                    answer = self._mock_correct_answer(q)
                else:
                    answer = self._mock_wrong_answer(q)
                answers.append({"question_id": q.id, "answer": answer})

            # 复用现有评分逻辑
            correct = 0
            wrong = 0
            unanswered = 0
            total = 0.0
            detail = []
            for qc in paper_questions:
                q = question_map.get(qc["question_id"])
                if not q:
                    continue
                ans = next((a for a in answers if a["question_id"] == q.id), None)
                user_answer = ans["answer"] if ans else None
                if user_answer is None:
                    unanswered += 1
                    is_correct = False
                else:
                    is_correct = self._check_answer(user_answer, q.correct_answer, q.question_type)
                score = float(qc.get("score", q.score_value or 1))
                if is_correct:
                    correct += 1
                    total += score
                else:
                    wrong += 1
                detail.append({
                    "question_id": q.id,
                    "question_content": q.question_content[:50],
                    "user_answer": user_answer,
                    "correct_answer": q.correct_answer,
                    "is_correct": is_correct,
                })

            total = round(total, 2)
            total_count = correct + wrong + unanswered
            real_correct_rate = round((correct / total_count * 100) if total_count else 0, 2)

            return {
                "paper_id": paper_id,
                "paper_name": paper.paper_name,
                "talent_id": talent_id,
                "total_score": total,
                "correct_count": correct,
                "wrong_count": wrong,
                "unanswered_count": unanswered,
                "correct_rate": real_correct_rate,
                "detail": detail,
            }
        except Exception as e:
            logger.error(f"模拟答题失败: {str(e)}")
            raise

    def _mock_correct_answer(self, q: Question) -> Any:
        """生成正确的模拟答案"""
        if q.question_type in (QuestionType.SINGLE_CHOICE, QuestionType.TRUE_FALSE, QuestionType.FILL_BLANK):
            return q.correct_answer
        if q.question_type == QuestionType.MULTIPLE_CHOICE:
            return q.correct_answer
        return q.correct_answer

    def _mock_wrong_answer(self, q: Question) -> Any:
        """生成错误的模拟答案（从选项中挑一个非正确答案）"""
        import random
        if q.question_type in (QuestionType.SINGLE_CHOICE, QuestionType.MULTIPLE_CHOICE):
            options = q.options or []
            if options:
                # options 可能是 ["A. xx", ...] 或 [{"key":"A","text":"xx"}, ...]
                keys = []
                for o in options:
                    if isinstance(o, str):
                        keys.append(o[0] if o and o[0].isalpha() else o)
                    elif isinstance(o, dict):
                        keys.append(o.get("key") or o.get("label") or o.get("text"))
                correct_keys = self._parse_answer_keys(q.correct_answer)
                wrong_keys = [k for k in keys if k and str(k).strip().upper() not in correct_keys]
                if wrong_keys:
                    return random.choice(wrong_keys)
            return "Z"
        if q.question_type == QuestionType.TRUE_FALSE:
            return "错误" if str(q.correct_answer).strip().lower() in ("true", "t", "1", "正确", "对") else "正确"
        if q.question_type == QuestionType.FILL_BLANK:
            return "模拟错误答案"
        return "模拟错误答案"

    def _parse_answer_keys(self, correct_answer: Any) -> set:
        if isinstance(correct_answer, list):
            return {str(v).strip().upper() for v in correct_answer}
        return {str(v).strip().upper() for v in str(correct_answer).replace("，", ",").split(",")}

    # ==================== 测评任务 ====================

    def create_task(self, task_data: Dict[str, Any], user_id: int = None) -> AssessmentTask:
        """创建测评任务"""
        try:
            task_code = self._generate_task_code()

            task = AssessmentTask(
                task_code=task_code,
                task_name=task_data.get("task_name"),
                target_type=task_data.get("target_type", "batch"),
                target_talents=task_data.get("target_talents", task_data.get("talent_ids", [])),
                paper_id=task_data.get("paper_id"),
                start_time=task_data.get("start_time"),
                end_time=task_data.get("end_time"),
                allow_retake=task_data.get("allow_retake", False),
                max_attempts=task_data.get("max_attempts", 1),
                show_answer=task_data.get("show_answer", False),
                anti_cheating=task_data.get("anti_cheating", True),
                status=AssessmentStatus.DRAFT
            )

            self.db.add(task)
            self.db.commit()
            self.db.refresh(task)

            logger.info(f"创建测评任务成功: ID={task.id}")
            return task

        except Exception as e:
            self.db.rollback()
            logger.error(f"创建测评任务失败: {str(e)}")
            raise

    def submit_assessment(
        self,
        task_id: int,
        talent_id: int,
        answers: List[Dict[str, Any]],
        duration_seconds: int = 0
    ) -> AssessmentResult:
        """提交测评并自动评分"""
        try:
            task = self.db.query(AssessmentTask).filter(AssessmentTask.id == task_id).first()
            if not task:
                raise ValueError("测评任务不存在")

            paper = self.db.query(TestPaper).filter(TestPaper.id == task.paper_id).first()
            if not paper:
                raise ValueError("试卷不存在")

            # 试卷题目配置: [{"question_id": 1, "score": 2}, ...]
            paper_questions = paper.questions or []
            question_score_map = {q["question_id"]: float(q.get("score", 1)) for q in paper_questions if "question_id" in q}

            question_ids = list(question_score_map.keys())
            questions = self.db.query(Question).filter(Question.id.in_(question_ids)).all()
            question_map = {q.id: q for q in questions}

            total_score = 0.0
            correct_count = 0
            wrong_count = 0
            unanswered_count = 0
            capability_scores: Dict[str, Dict[str, float]] = {}

            answer_details = []
            for answer in answers:
                question_id = answer.get("question_id")
                user_answer = answer.get("answer")

                question = question_map.get(question_id)
                if not question:
                    continue

                if user_answer is None or user_answer == "":
                    unanswered_count += 1
                    is_correct = False
                else:
                    is_correct = self._check_answer(
                        user_answer,
                        question.correct_answer,
                        question.question_type
                    )

                q_score = question_score_map.get(question_id, float(question.score_value or 1))
                if is_correct:
                    total_score += q_score
                    correct_count += 1
                else:
                    wrong_count += 1

                # 能力维度统计
                dim = question.capability_dimension or "通用"
                if dim not in capability_scores:
                    capability_scores[dim] = {"score": 0.0, "max": 0.0}
                capability_scores[dim]["max"] += q_score
                if is_correct:
                    capability_scores[dim]["score"] += q_score

                answer_details.append({
                    "question_id": question_id,
                    "user_answer": user_answer,
                    "correct_answer": question.correct_answer,
                    "is_correct": is_correct,
                    "score": q_score if is_correct else 0.0
                })

            # 计算能力维度得分率
            capability_dimensions = {}
            for dim, vals in capability_scores.items():
                capability_dimensions[dim] = round(
                    (vals["score"] / vals["max"] * 100) if vals["max"] > 0 else 0, 2
                )

            # 总分四舍五入
            total_score = round(total_score, 2)

            # 能力等级评定
            correct_rate = (correct_count / len(answer_details) * 100) if answer_details else 0
            capability_level = self._calc_capability_level(correct_rate)

            result = AssessmentResult(
                result_code=self._generate_result_code(),
                talent_id=talent_id,
                task_id=task_id,
                paper_id=paper.id,
                answers=json.dumps(answers, ensure_ascii=False),
                total_score=total_score,
                correct_count=correct_count,
                wrong_count=wrong_count,
                unanswered_count=unanswered_count,
                capability_dimensions=capability_dimensions,
                capability_level=capability_level,
                submit_time=datetime.now(),
                duration_seconds=duration_seconds,
                status="completed"
            )

            self.db.add(result)
            self.db.commit()
            self.db.refresh(result)

            logger.info(f"提交测评成功: talent_id={talent_id}, score={total_score}")
            return result

        except Exception as e:
            self.db.rollback()
            logger.error(f"提交测评失败: {str(e)}")
            raise

    def get_results(
        self,
        talent_id: Optional[int] = None,
        task_id: Optional[int] = None,
        page: int = 1,
        page_size: int = 20
    ) -> Dict[str, Any]:
        """获取测评结果"""
        query = self.db.query(AssessmentResult)

        if talent_id:
            query = query.filter(AssessmentResult.talent_id == talent_id)
        if task_id:
            query = query.filter(AssessmentResult.task_id == task_id)

        total = query.count()
        results = query.offset((page - 1) * page_size).limit(page_size).all()

        return {
            "items": results,
            "total": total,
            "page": page,
            "page_size": page_size
        }

    # ==================== 雷达图 / 报告 ====================

    def generate_radar_chart(self, result_id: int) -> Dict[str, Any]:
        """生成能力雷达图数据"""
        try:
            result = self.db.query(AssessmentResult).filter(AssessmentResult.id == result_id).first()
            if not result:
                raise ValueError("测评结果不存在")

            # 优先使用已计算的 capability_dimensions
            capability_dimensions = result.capability_dimensions or {}

            radar_data = [
                {"category": category, "score": score, "max_score": 100}
                for category, score in capability_dimensions.items()
            ]

            return {
                "result_id": result_id,
                "total_score": float(result.total_score),
                "correct_count": result.correct_count,
                "wrong_count": result.wrong_count,
                "unanswered_count": result.unanswered_count,
                "capability_level": result.capability_level.value if result.capability_level else None,
                "radar_data": radar_data
            }

        except Exception as e:
            logger.error(f"生成雷达图失败: {str(e)}")
            raise

    # ==================== 辅助方法 ====================

    def _generate_paper_code(self) -> str:
        count = self.db.query(TestPaper).count()
        return f"PAPER{datetime.now().strftime('%Y%m%d')}{str(count + 1).zfill(4)}"

    def _generate_task_code(self) -> str:
        count = self.db.query(AssessmentTask).count()
        return f"TASK{datetime.now().strftime('%Y%m%d')}{str(count + 1).zfill(4)}"

    def _generate_result_code(self) -> str:
        count = self.db.query(AssessmentResult).count()
        return f"RES{datetime.now().strftime('%Y%m%d')}{str(count + 1).zfill(4)}"

    def _check_answer(self, user_answer: Any, correct_answer: Any, question_type: QuestionType) -> bool:
        """检查答案是否正确"""
        try:
            if question_type == QuestionType.SINGLE_CHOICE:
                return str(user_answer).strip().upper() == str(correct_answer).strip().upper()

            elif question_type == QuestionType.MULTIPLE_CHOICE:
                def parse_set(val):
                    if isinstance(val, list):
                        return set(str(v).strip().upper() for v in val)
                    return set(str(val).replace("，", ",").replace("|", ",").split(","))

                return parse_set(user_answer) == parse_set(correct_answer)

            elif question_type == QuestionType.TRUE_FALSE:
                def norm(v):
                    return str(v).strip().lower()
                truthy = {"true", "t", "1", "正确", "对", "yes", "y"}
                falsey = {"false", "f", "0", "错误", "错", "no", "n"}
                ua, ca = norm(user_answer), norm(correct_answer)
                if ca in truthy:
                    return ua in truthy
                if ca in falsey:
                    return ua in falsey
                return ua == ca

            elif question_type == QuestionType.FILL_BLANK:
                if isinstance(correct_answer, list):
                    return str(user_answer).strip() in [str(a).strip() for a in correct_answer]
                return str(user_answer).strip() == str(correct_answer).strip()

            # 简答题/论述题需人工或AI评分，自动评分为0
            return False

        except Exception as e:
            logger.error(f"检查答案失败: {str(e)}")
            return False

    def _calc_capability_level(self, correct_rate: float) -> CapabilityLevel:
        """根据正确率计算能力等级"""
        if correct_rate >= 90:
            return CapabilityLevel.CORE
        elif correct_rate >= 80:
            return CapabilityLevel.BACKBONE
        elif correct_rate >= 70:
            return CapabilityLevel.SENIOR
        elif correct_rate >= 60:
            return CapabilityLevel.INTERMEDIATE
        elif correct_rate >= 40:
            return CapabilityLevel.JUNIOR
        else:
            return CapabilityLevel.ENTRY
