"""
PostgreSQL 分析库初始化与管理
遵循招标文件强制要求：PgSQL 用于海量分析数据和时序数据。

用法：
    from app.core.postgresql import init_pgsql_tables, migrate_to_pgsql, sync_behavior_log

    # 启动时创建表
    init_pgsql_tables()

    # 迁移 MySQL 存量数据到 PgSQL（一次性）
    migrate_to_pgsql()

    # 实时同步行为日志到 PgSQL（每次事件触发）
    sync_behavior_log(talent_id=10, event_type="resume_view", event_data={"position_id": 3})
"""
import logging
from typing import Any, Dict, Optional

from app.core.postgresql.client import get_pgsql_session, get_pgsql_engine, init_pgsql_check
from app.core.postgresql.models import (
    Base,
    TalentBehaviorLog,
    TalentTrendSnapshot,
    TrainingAnalytics,
    MatchAnalytics,
    DashboardSummary,
)

logger = logging.getLogger(__name__)


def init_pgsql_tables() -> bool:
    """
    应用启动时调用：在 PgSQL 创建分析专属表。
    幂等操作（IF NOT EXISTS），重复执行安全。
    """
    try:
        engine = get_pgsql_engine()
        Base.metadata.create_all(engine)
        logger.info("✅ PgSQL 分析表创建/验证完成")
        return True
    except Exception as e:
        logger.error(f"❌ PgSQL 表初始化失败: {e}")
        return False


def sync_behavior_log(
    talent_id: int,
    event_type: str,
    event_data: Optional[Dict[str, Any]] = None,
    organization_id: Optional[int] = None,
    user_id: Optional[int] = None,
) -> bool:
    """
    将行为事件实时写入 PgSQL（时序日志）。
    失败时降级日志（不阻断主流程）。
    """
    try:
        with get_pgsql_session() as db:
            log = TalentBehaviorLog(
                talent_id=talent_id,
                event_type=event_type,
                event_data=event_data or {},
                organization_id=organization_id,
                user_id=user_id,
            )
            db.add(log)
        logger.debug(f"行为日志写入PgSQL: talent={talent_id}, event={event_type}")
        return True
    except Exception as e:
        logger.warning(f"⚠️ 行为日志PgSQL写入失败（已降级）: {e}")
        return False


def sync_trend_snapshot(
    talent_id: int,
    assessment_result_id: int,
    capability_dimensions: Dict[str, float],
    total_score: float,
    ability_level: str,
) -> bool:
    """同步测评结果快照到 PgSQL（用于趋势分析）"""
    try:
        with get_pgsql_session() as db:
            snapshot = TalentTrendSnapshot(
                talent_id=talent_id,
                assessment_result_id=assessment_result_id,
                capability_dimensions=capability_dimensions,
                total_score=total_score,
                ability_level=ability_level,
            )
            db.add(snapshot)
        logger.debug(f"趋势快照写入PgSQL: talent={talent_id}, result={assessment_result_id}")
        return True
    except Exception as e:
        logger.warning(f"⚠️ 趋势快照写入失败: {e}")
        return False


def sync_training_analytics(
    talent_id: int,
    learning_record_id: int,
    course_id: Optional[int] = None,
    study_duration_minutes: float = 0,
    completion_rate: float = 0,
    exam_score: Optional[float] = None,
    passed: Optional[bool] = None,
    learning_path_step: Optional[int] = None,
) -> bool:
    """同步培训学习数据到 PgSQL"""
    try:
        with get_pgsql_session() as db:
            record = TrainingAnalytics(
                talent_id=talent_id,
                learning_record_id=learning_record_id,
                course_id=course_id,
                study_duration_minutes=study_duration_minutes,
                completion_rate=completion_rate,
                exam_score=exam_score,
                passed=passed,
                learning_path_step=learning_path_step,
            )
            db.add(record)
        return True
    except Exception as e:
        logger.warning(f"⚠️ 培训分析数据写入失败: {e}")
        return False


def sync_match_analytics(
    request_id: str,
    match_type: str,
    talent_id: Optional[int] = None,
    position_id: Optional[int] = None,
    filter_count: int = 0,
    match_count: int = 0,
    top1_score: Optional[float] = None,
    top1_candidate_id: Optional[int] = None,
    duration_ms: Optional[float] = None,
    llm_ranking_used: bool = False,
) -> bool:
    """同步匹配请求分析数据到 PgSQL"""
    try:
        with get_pgsql_session() as db:
            record = MatchAnalytics(
                request_id=request_id,
                talent_id=talent_id,
                position_id=position_id,
                match_type=match_type,
                filter_count=filter_count,
                match_count=match_count,
                top1_score=top1_score,
                top1_candidate_id=top1_candidate_id,
                duration_ms=duration_ms,
                llm_ranking_used=llm_ranking_used,
            )
            db.add(record)
        return True
    except Exception as e:
        logger.warning(f"⚠️ 匹配分析数据写入失败: {e}")
        return False


# ── 从 MySQL 迁移存量数据到 PgSQL（一次性）───────────────────────

def migrate_to_pgsql() -> Dict[str, Any]:
    """
    将 MySQL 存量数据迁移到 PgSQL。
    包括：测评结果快照（历史评估数据）→ 趋势快照。
    幂等：已迁移的 assessment_result_id 不重复写入。
    """
    from datetime import datetime
    from app.core.database import get_mysql_session
    from app.models.assessment import AssessmentResult

    results = {"migrated": 0, "skipped": 0, "failed": 0}

    try:
        mysql_db = next(get_mysql_session())

        # 找出所有已有快照的评估结果（避免重复迁移）
        try:
            with get_pgsql_session() as pgsql:
                existing_ids = set(
                    r[0] for r in pgsql.query(TalentTrendSnapshot.assessment_result_id).all()
                )
        except Exception:
            existing_ids = set()

        all_results = mysql_db.query(AssessmentResult).all()
        for ar in all_results:
            if ar.id in existing_ids:
                results["skipped"] += 1
                continue
            try:
                dims = ar.capability_dimensions if isinstance(ar.capability_dimensions, dict) else {}
                with get_pgsql_session() as pgsql:
                    snapshot = TalentTrendSnapshot(
                        talent_id=ar.talent_id,
                        assessment_result_id=ar.id,
                        capability_dimensions=dims,
                        total_score=float(ar.total_score or 0),
                        ability_level=getattr(ar, "ability_level", None),
                    )
                    pgsql.add(snapshot)
                results["migrated"] += 1
            except Exception as e:
                logger.warning(f"迁移评估结果 {ar.id} 失败: {e}")
                results["failed"] += 1

        logger.info(f"PgSQL 迁移完成: {results}")
        return results
    except Exception as e:
        logger.error(f"PgSQL 迁移异常: {e}")
        return results


__all__ = [
    "init_pgsql_tables",
    "init_pgsql_check",
    "get_pgsql_session",
    "sync_behavior_log",
    "sync_trend_snapshot",
    "sync_training_analytics",
    "sync_match_analytics",
    "migrate_to_pgsql",
]
