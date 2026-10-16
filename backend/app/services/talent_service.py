"""
人才管理服务
"""
from sqlalchemy.orm import Session, joinedload
from sqlalchemy import or_, and_, cast, String
from typing import List, Optional, Dict, Any
from datetime import datetime
import uuid
import json
import logging

from app.models.talent import Talent, Organization  # TalentTag 已移除（改用 talents.tags JSON）
from app.schemas.talent import TalentCreate, TalentUpdate, TalentSearchRequest
from app.core.exceptions import (
    NotFoundException,
    BadRequestException,
    DuplicateKeyException
)

logger = logging.getLogger(__name__)


class TalentService:
    """人才管理服务"""
    
    @staticmethod
    def generate_talent_code() -> str:
        """生成人才编号"""
        timestamp = datetime.now().strftime("%Y%m%d%H%M%S")
        random_str = uuid.uuid4().hex[:6].upper()
        return f"T{timestamp}{random_str}"
    
    @staticmethod
    def create_talent(
        db: Session,
        talent_data: TalentCreate
    ) -> Talent:
        """创建人才档案"""
        try:
            # 检查手机号是否已存在
            existing_talent = db.query(Talent).filter(
                Talent.phone == talent_data.phone
            ).first()
            
            if existing_talent:
                raise DuplicateKeyException(
                    message="该手机号已存在",
                    details={"phone": talent_data.phone}
                )
            
            # 检查邮箱是否已存在
            if talent_data.email:
                existing_email = db.query(Talent).filter(
                    Talent.email == talent_data.email
                ).first()
                
                if existing_email:
                    raise DuplicateKeyException(
                        message="该邮箱已存在",
                        details={"email": talent_data.email}
                    )
            
            # 创建人才档案
            talent = Talent(
                talent_code=TalentService.generate_talent_code(),
                name=talent_data.name,
                gender=talent_data.gender,
                birth_date=talent_data.birth_date,
                id_card=talent_data.id_card,
                phone=talent_data.phone,
                email=talent_data.email,
                address=talent_data.address,
                education=talent_data.education,
                major=talent_data.major,
                experience_years=talent_data.experience_years,
                current_company=talent_data.current_company,
                current_position=talent_data.current_position,
                expected_salary_min=talent_data.expected_salary_min,
                expected_salary_max=talent_data.expected_salary_max,
                expected_position=talent_data.expected_position,
                self_introduction=talent_data.self_introduction,
                status=talent_data.status,
                department_id=talent_data.department_id,
                education_records=[edu.model_dump() for edu in (talent_data.education_records or [])],
                work_experiences=[work.model_dump() for work in (talent_data.work_experiences or [])],
                skills_certificates=[skill.model_dump() for skill in (talent_data.skills_certificates or [])],
                tags=talent_data.tags or []
            )
            
            db.add(talent)
            db.commit()
            db.refresh(talent)
            
            logger.info(f"创建人才档案成功: {talent.talent_code} - {talent.name}")
            
            return talent
            
        except Exception as e:
            db.rollback()
            logger.error(f"创建人才档案失败: {str(e)}")
            raise
    
    @staticmethod
    def get_talent_by_id(
        db: Session,
        talent_id: int,
        scope_predicate=None
    ) -> Optional[Talent]:
        """根据ID获取人才

        Args:
            scope_predicate: 行级数据范围过滤条件（SQLAlchemy 表达式），
                由 app.core.rbac 按用户数据权限生成；None 表示不过滤。
        """
        query = db.query(Talent).options(joinedload(Talent.department)).filter(Talent.id == talent_id)
        if scope_predicate is not None:
            query = query.filter(scope_predicate)

        talent = query.first()

        if not talent:
            # 行级隔离下不可见时，统一按"不存在"返回，避免资源枚举探测
            raise NotFoundException(
                message="人才不存在",
                details={"talent_id": talent_id}
            )

        return talent
    
    @staticmethod
    def get_talent_by_code(
        db: Session,
        talent_code: str
    ) -> Optional[Talent]:
        """根据编号获取人才"""
        talent = db.query(Talent).filter(Talent.talent_code == talent_code).first()
        
        if not talent:
            raise NotFoundException(
                message="人才不存在",
                details={"talent_code": talent_code}
            )
        
        return talent
    
    @staticmethod
    def update_talent(
        db: Session,
        talent_id: int,
        talent_data: TalentUpdate
    ) -> Talent:
        """更新人才档案"""
        try:
            talent = TalentService.get_talent_by_id(db, talent_id)
            
            # 更新字段
            update_data = talent_data.model_dump(exclude_unset=True)
            
            for field, value in update_data.items():
                if field == "tags":
                    setattr(talent, field, value or [])
                else:
                    setattr(talent, field, value)
            
            talent.updated_at = datetime.now()
            
            db.commit()
            db.refresh(talent)
            
            logger.info(f"更新人才档案成功: {talent.talent_code}")
            
            return talent
            
        except Exception as e:
            db.rollback()
            logger.error(f"更新人才档案失败: {str(e)}")
            raise
    
    @staticmethod
    def delete_talent(
        db: Session,
        talent_id: int
    ) -> bool:
        """删除人才档案"""
        try:
            talent = TalentService.get_talent_by_id(db, talent_id)

            # 先清理关联子表记录，避免外键约束导致 500
            # （assessment_results / learning_records / match_records 默认 RESTRICT）
            for ar in list(talent.assessment_results):
                db.delete(ar)
            for lr in list(talent.learning_records):
                db.delete(lr)
            for mr in list(talent.match_records):
                db.delete(mr)
            db.flush()

            db.delete(talent)
            db.commit()

            logger.info(f"删除人才档案成功: {talent.talent_code}")

            return True

        except Exception as e:
            db.rollback()
            logger.error(f"删除人才档案失败: {str(e)}")
            raise

    @staticmethod
    def batch_delete_talents(db: Session, talent_ids: List[int]) -> Dict[str, Any]:
        """批量删除人才档案（整页删除）"""
        if not talent_ids:
            return {"deleted": 0, "failed": []}
        deleted = 0
        failed = []
        for tid in talent_ids:
            try:
                talent = TalentService.get_talent_by_id(db, tid)
                if not talent:
                    failed.append(tid)
                    continue
                # 清理关联子表，避免外键约束
                for ar in list(talent.assessment_results):
                    db.delete(ar)
                for lr in list(talent.learning_records):
                    db.delete(lr)
                for mr in list(talent.match_records):
                    db.delete(mr)
                db.flush()
                db.delete(talent)
                deleted += 1
            except Exception as e:
                db.rollback()
                logger.error(f"批量删除人才 {tid} 失败: {str(e)}")
                failed.append(tid)
        db.commit()
        logger.info(f"批量删除人才成功: {deleted}/{len(talent_ids)}, 失败: {failed}")
        return {"deleted": deleted, "failed": failed}
    
    @staticmethod
    def list_talents(
        db: Session,
        page: int = 1,
        page_size: int = 10,
        name: Optional[str] = None,
        phone: Optional[str] = None,
        status: Optional[str] = None,
        department_id: Optional[int] = None,
        keyword: Optional[str] = None,
        gender: Optional[str] = None,
        education: Optional[str] = None,
        scope_predicate=None
    ) -> tuple[List[Talent], int]:
        """获取人才列表

        Args:
            scope_predicate: 行级数据范围过滤条件（见 get_talent_by_id）
        """
        query = db.query(Talent)
        if scope_predicate is not None:
            query = query.filter(scope_predicate)

        # 过滤条件
        if name:
            query = query.filter(Talent.name.like(f"%{name}%"))

        if phone:
            query = query.filter(Talent.phone.like(f"%{phone}%"))

        if status:
            query = query.filter(Talent.status == status)

        if department_id:
            query = query.filter(Talent.department_id == department_id)

        # 关键词模糊搜索（姓名/手机号/邮箱 任一匹配）
        if keyword:
            kw = f"%{keyword}%"
            query = query.filter(
                or_(
                    Talent.name.like(kw),
                    Talent.phone.like(kw),
                    Talent.email.like(kw),
                )
            )

        # 性别过滤（前端传 male/female）
        if gender:
            query = query.filter(Talent.gender == gender)

        # 学历过滤（前端传 本科/硕士 等）
        if education:
            query = query.filter(Talent.education == education)
        
        # 统计总数
        total = query.count()
        
        # 分页
        offset = (page - 1) * page_size
        talents = query.order_by(Talent.created_at.desc()).offset(offset).limit(page_size).all()
        
        return talents, total
    
    @staticmethod
    def search_talents(
        db: Session,
        search_data: TalentSearchRequest,
        scope_predicate=None
    ) -> tuple[List[Talent], int]:
        """搜索人才（支持向量搜索）

        Args:
            scope_predicate: 行级数据范围过滤条件（见 get_talent_by_id）
        """
        query = db.query(Talent)
        if scope_predicate is not None:
            query = query.filter(scope_predicate)
        
        # 关键词搜索
        if search_data.query:
            query = query.filter(
                or_(
                    Talent.name.like(f"%{search_data.query}%"),
                    Talent.current_position.like(f"%{search_data.query}%"),
                    Talent.self_introduction.like(f"%{search_data.query}%")
                )
            )
        
        # 标签过滤（兼容 SQLite 测试库与 MySQL 生产库：对 JSON 文本做精确 token 匹配）
        if search_data.tags:
            for t in search_data.tags:
                query = query.filter(cast(Talent.tags, String).like(f'%{json.dumps(t)}%'))
        
        # 学历过滤
        if search_data.education:
            query = query.filter(Talent.education == search_data.education)
        
        # 工作年限过滤
        if search_data.min_experience is not None:
            query = query.filter(Talent.experience_years >= search_data.min_experience)
        
        if search_data.max_experience is not None:
            query = query.filter(Talent.experience_years <= search_data.max_experience)
        
        # 状态过滤
        if search_data.status:
            query = query.filter(Talent.status == search_data.status)
        
        # 部门过滤
        if search_data.department_id:
            query = query.filter(Talent.department_id == search_data.department_id)
        
        # 向量语义搜索：use_vector_search=True 且有查询文本时启用
        # 语义召回拿到的是一批 talent_id（Milvus），再与上面的硬条件（学历/年限/部门/
        # 数据范围）取交集，最后按语义相似度排序。向量库不可用或为空时自动回退关键词检索，
        # 保证「有 Milvus 走语义、没 Milvus 也能查」。
        vector_rank: Optional[Dict[int, float]] = None
        if search_data.use_vector_search and search_data.query:
            vector_rank = TalentService._vector_candidate_rank(search_data.query)
            if vector_rank:
                query = query.filter(Talent.id.in_(list(vector_rank.keys())))
            else:
                logger.info("向量检索无结果或不可用，本次回退关键词检索")

        # 统计总数
        total = query.count()
        
        # 分页
        offset = (search_data.page - 1) * search_data.page_size
        if vector_rank:
            # 语义排序无法在 SQL 侧表达（得分在向量库里），候选池已被 IN 限定为百级，内存排序可接受
            rows = query.all()
            rows.sort(key=lambda t: vector_rank.get(t.id, 0.0), reverse=True)
            talents = rows[offset: offset + search_data.page_size]
        else:
            talents = query.order_by(Talent.created_at.desc()).offset(offset).limit(search_data.page_size).all()
        
        return talents, total

    # 向量召回候选池上限：避免一次把过多 ID 塞进 IN 子句
    VECTOR_CANDIDATE_LIMIT = 200

    @staticmethod
    def _vector_candidate_rank(query_text: str) -> Optional[Dict[int, float]]:
        """语义召回人才，返回 {talent_id: 相似度}。

        向量服务未初始化、Milvus 无数据或调用异常时统一返回 None，
        由调用方回退关键词检索——不阻塞、不报错。
        """
        try:
            from app.services.vector_search_service import vector_search_service

            if vector_search_service is None:
                logger.info("向量检索服务未初始化，回退关键词检索")
                return None

            hits = vector_search_service.search_matching_talents(
                query_text=query_text,
                top_k=TalentService.VECTOR_CANDIDATE_LIMIT
            )

            rank: Dict[int, float] = {}
            for hit in hits or []:
                try:
                    tid = int(hit.get("id"))
                except (TypeError, ValueError):
                    continue
                score = float(hit.get("score") or 0.0)
                if score > rank.get(tid, float("-inf")):
                    rank[tid] = score

            return rank or None

        except Exception as e:
            logger.warning(f"向量检索失败（回退关键词检索）: {e}")
            return None
    
    @staticmethod
    def check_duplicate(
        db: Session,
        talent_id: int
    ) -> List[Dict[str, Any]]:
        """查重检测"""
        talent = TalentService.get_talent_by_id(db, talent_id)
        
        duplicates = []
        
        # 根据姓名+手机号查重
        if talent.name and talent.phone:
            similar_talents = db.query(Talent).filter(
                and_(
                    Talent.id != talent_id,
                    Talent.name == talent.name,
                    Talent.phone == talent.phone
                )
            ).all()
            
            for similar in similar_talents:
                duplicates.append({
                    "talent_id": similar.id,
                    "talent_code": similar.talent_code,
                    "name": similar.name,
                    "phone": similar.phone,
                    "match_type": "name_phone",
                    "similarity": 1.0
                })
        
        # 根据身份证号查重
        if talent.id_card:
            similar_talents = db.query(Talent).filter(
                and_(
                    Talent.id != talent_id,
                    Talent.id_card == talent.id_card
                )
            ).all()
            
            for similar in similar_talents:
                duplicates.append({
                    "talent_id": similar.id,
                    "talent_code": similar.talent_code,
                    "name": similar.name,
                    "phone": similar.phone,
                    "match_type": "id_card",
                    "similarity": 1.0
                })
        
        return duplicates
    
    @staticmethod
    def update_tags(
        db: Session,
        talent_id: int,
        tags: List[str]
    ) -> Talent:
        """更新人才标签"""
        try:
            talent = TalentService.get_talent_by_id(db, talent_id)
            
            talent.tags = tags
            talent.updated_at = datetime.now()
            
            db.commit()
            db.refresh(talent)
            
            logger.info(f"更新人才标签成功: {talent.talent_code}")
            
            return talent
            
        except Exception as e:
            db.rollback()
            logger.error(f"更新人才标签失败: {str(e)}")
            raise
