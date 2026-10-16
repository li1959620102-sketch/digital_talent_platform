"""
岗位管理服务
"""
from sqlalchemy.orm import Session
from sqlalchemy import and_, or_
from typing import List, Optional, Dict, Any
from datetime import datetime
import logging

from app.models.position import JobPosition, MatchRecord, PositionStatus
from app.models.talent import Talent
from app.schemas.common import ResponseModel, PageModel
from app.services.vector_search_service import VectorSearchService

logger = logging.getLogger(__name__)


class PositionService:
    """岗位管理服务"""

    def __init__(self, db: Session):
        self.db = db
        self._vector_service = None

    @property
    def vector_service(self):
        """延迟初始化向量检索服务（避免在测试/无Ollama环境下初始化失败）"""
        if self._vector_service is None:
            try:
                self._vector_service = VectorSearchService()
            except Exception as e:
                logger.warning(f"向量检索服务初始化失败，将跳过向量化: {str(e)}")
                self._vector_service = False
        return self._vector_service or None

    def create_position(self, position_data: Dict[str, Any], user_id: int) -> JobPosition:
        """创建岗位"""
        try:
            # 生成岗位编号
            position_code = self._generate_position_code()

            # 创建岗位
            position = JobPosition(
                position_code=position_code,
                position_name=position_data.get("position_name"),
                department_id=position_data.get("department_id"),
                position_category=position_data.get("position_category"),
                position_level=position_data.get("position_level"),
                position_type=position_data.get("position_type"),
                headcount=position_data.get("headcount", 1),
                salary_min=position_data.get("salary_min"),
                salary_max=position_data.get("salary_max"),
                work_location=position_data.get("work_location"),
                education_requirement=position_data.get("education_requirement"),
                experience_requirement=position_data.get("experience_requirement"),
                skill_requirements=position_data.get("skill_requirements", []),
                capability_requirements=position_data.get("capability_requirements", []),
                job_description=position_data.get("job_description"),
                job_responsibilities=position_data.get("job_responsibilities"),
                tags=position_data.get("tags", []),
                status=PositionStatus.OPEN,
                publish_date=datetime.now()
            )

            self.db.add(position)
            self.db.commit()
            self.db.refresh(position)

            # 创建岗位需求向量
            self._create_position_vector(position)

            logger.info(f"创建岗位成功: {position.position_code}")
            return position

        except Exception as e:
            self.db.rollback()
            logger.error(f"创建岗位失败: {str(e)}")
            raise

    def get_position(self, position_id: int) -> Optional[JobPosition]:
        """获取岗位详情"""
        return self.db.query(JobPosition).filter(JobPosition.id == position_id).first()

    def get_position_by_code(self, position_code: str) -> Optional[JobPosition]:
        """根据编号获取岗位"""
        return self.db.query(JobPosition).filter(JobPosition.position_code == position_code).first()

    def update_position(self, position_id: int, position_data: Dict[str, Any], user_id: int) -> Optional[JobPosition]:
        """更新岗位信息"""
        try:
            position = self.get_position(position_id)
            if not position:
                return None

            # 更新字段
            for key, value in position_data.items():
                if hasattr(position, key) and key not in ["id", "position_code", "created_at"]:
                    setattr(position, key, value)

            if hasattr(position, "updated_by"):
                position.updated_by = user_id
            self.db.commit()
            self.db.refresh(position)

            # 更新向量
            if position_data.get("job_description") or position_data.get("skill_requirements"):
                self._update_position_vector(position)

            logger.info(f"更新岗位成功: {position.position_code}")
            return position

        except Exception as e:
            self.db.rollback()
            logger.error(f"更新岗位失败: {str(e)}")
            raise

    def delete_position(self, position_id: int) -> bool:
        """删除岗位"""
        try:
            position = self.get_position(position_id)
            if not position:
                return False

            self.db.delete(position)
            self.db.commit()

            logger.info(f"删除岗位成功: {position.position_code}")
            return True

        except Exception as e:
            self.db.rollback()
            logger.error(f"删除岗位失败: {str(e)}")
            raise

    def batch_delete_positions(self, position_ids: List[int]) -> Dict[str, Any]:
        """批量删除岗位（整页删除）"""
        if not position_ids:
            return {"deleted": 0, "failed": []}
        deleted = 0
        failed = []
        for pid in position_ids:
            try:
                position = self.get_position(pid)
                if not position:
                    failed.append(pid)
                    continue
                self.db.delete(position)
                deleted += 1
            except Exception as e:
                self.db.rollback()
                logger.error(f"批量删除岗位 {pid} 失败: {str(e)}")
                failed.append(pid)
        self.db.commit()
        logger.info(f"批量删除岗位成功: {deleted}/{len(position_ids)}, 失败: {failed}")
        return {"deleted": deleted, "failed": failed}

    def get_positions(
        self,
        page: int = 1,
        page_size: int = 20,
        department_id: Optional[int] = None,
        status: Optional[PositionStatus] = None,
        keyword: Optional[str] = None,
        position_level: Optional[Any] = None
    ) -> Dict[str, Any]:
        """获取岗位列表（分页）"""
        query = self.db.query(JobPosition)

        # 过滤条件
        if department_id:
            query = query.filter(JobPosition.department_id == department_id)
        if status:
            query = query.filter(JobPosition.status == status)
        if position_level:
            query = query.filter(JobPosition.position_level == position_level)
        if keyword:
            query = query.filter(
                or_(
                    JobPosition.position_name.ilike(f"%{keyword}%"),
                    JobPosition.position_code.ilike(f"%{keyword}%")
                )
            )

        # 总数
        total = query.count()

        # 分页
        positions = query.offset((page - 1) * page_size).limit(page_size).all()

        return {
            "items": positions,
            "total": total,
            "page": page,
            "page_size": page_size
        }

    def search_positions(
        self,
        query_text: str,
        filters: Optional[Dict[str, Any]] = None,
        top_k: int = 10
    ) -> List[Dict[str, Any]]:
        """搜索岗位（向量搜索）"""
        try:
            # 向量搜索
            results = self.vector_service.search_job_positions(
                query_text=query_text,
                filters=filters,
                top_k=top_k
            )

            # 补充岗位详情
            position_ids = [r["id"] for r in results]
            positions = self.db.query(JobPosition).filter(JobPosition.id.in_(position_ids)).all()
            position_map = {p.id: p for p in positions}

            enriched_results = []
            for result in results:
                position = position_map.get(result["id"])
                if position:
                    enriched_results.append({
                        **result,
                        "position_name": position.position_name,
                        "position_code": position.position_code,
                        "department_id": position.department_id,
                        "status": position.status.value if position.status else None
                    })

            return enriched_results

        except Exception as e:
            logger.error(f"岗位搜索失败: {str(e)}")
            raise

    def _generate_position_code(self) -> str:
        """生成岗位编号"""
        count = self.db.query(JobPosition).count()
        return f"POS{datetime.now().strftime('%Y%m%d')}{str(count + 1).zfill(4)}"

    def _create_position_vector(self, position: JobPosition):
        """创建岗位需求向量"""
        try:
            # 构建向量化文本
            text = self._build_vector_text(position)

            # 调用向量服务
            vector_id = self.vector_service.create_job_position_vector(
                position_id=position.id,
                text=text,
                metadata={
                    "position_code": position.position_code,
                    "position_name": position.position_name,
                    "department_id": position.department_id,
                    "education_requirement": position.education_requirement,
                    "experience_requirement": position.experience_requirement
                }
            )

            # 保存向量ID
            position.vector_id = vector_id
            self.db.commit()

        except Exception as e:
            logger.warning(f"创建岗位向量失败: {str(e)}")

    def _update_position_vector(self, position: JobPosition):
        """更新岗位需求向量"""
        try:
            text = self._build_vector_text(position)
            self.vector_service.update_job_position_vector(
                position_id=position.id,
                text=text
            )
        except Exception as e:
            logger.warning(f"更新岗位向量失败: {str(e)}")

    def _build_vector_text(self, position: JobPosition) -> str:
        """构建向量化文本"""
        parts = []

        if position.position_name:
            parts.append(f"岗位名称: {position.position_name}")

        if position.job_description:
            parts.append(f"岗位描述: {position.job_description}")

        if position.job_responsibilities:
            parts.append(f"岗位职责: {position.job_responsibilities}")

        if position.skill_requirements:
            parts.append(f"技能要求: {', '.join(position.skill_requirements)}")

        if position.capability_requirements:
            parts.append(f"能力要求: {', '.join(position.capability_requirements)}")

        if position.education_requirement:
            parts.append(f"学历要求: {position.education_requirement}")

        if position.experience_requirement:
            parts.append(f"经验要求: {position.experience_requirement}年")

        return "\n".join(parts)
