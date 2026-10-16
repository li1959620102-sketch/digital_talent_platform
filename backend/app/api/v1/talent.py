"""
人才管理API路由
"""
from fastapi import APIRouter, Depends, HTTPException, UploadFile, File, Query, Body
from sqlalchemy.orm import Session
from typing import List, Optional, Dict, Any
import logging
import os
import uuid

from app.core.config import settings
from app.core.database import get_mysql_session
from app.core.rbac import (
    PermCode,
    apply_field_masking,
    build_talent_scope_predicate,
    require_permission_or_403,
)
from app.models.permission import User
from app.models.talent import Talent as _Talent
from app.utils.minio_client import MinioClient, BUCKET_RESUMES, BUCKET_IMPORTS
from app.schemas.common import ResponseModel, PageModel
from app.core.exceptions import DuplicateKeyException
from app.schemas.talent import (
    TalentCreate, 
    TalentUpdate, 
    TalentResponse, 
    TalentListResponse,
    ResumeParseRequest,
    ResumeParseResponse,
    TalentSearchRequest,
    GenderEnum,
    EducationLevel,
)
from app.core.exceptions import NotFoundException, BadRequestException
from app.services.talent_service import TalentService
from app.agents.resume_parser_agent import resume_parser_agent

logger = logging.getLogger(__name__)

def _safe_remove(path: str) -> None:
    """
    安全删除本地临时文件（兼容外部 shim 的安全钩子）。
    任何异常（含 SystemExit）一律吞掉，不阻断主流程。
    MinIO 持久化副本不受影响。
    """
    try:
        os.remove(path)
    except BaseException:  # 兜底：包括 SystemExit 等
        pass

router = APIRouter()

# ── 权限依赖（P0 安全加固：全部人才档案端点禁止匿名访问）─────────────────
# 认证依赖 get_current_user 拦截匿名（401），权限码在已认证基础上做授权（403）。
AUTH_TALENT_VIEW = require_permission_or_403(PermCode.TALENT_VIEW)
AUTH_TALENT_CREATE = require_permission_or_403(PermCode.TALENT_CREATE)
AUTH_TALENT_UPDATE = require_permission_or_403(PermCode.TALENT_UPDATE)
AUTH_TALENT_DELETE = require_permission_or_403(PermCode.TALENT_DELETE)
AUTH_TALENT_IMPORT = require_permission_or_403(PermCode.TALENT_IMPORT)
AUTH_TALENT_TAG = require_permission_or_403(PermCode.TALENT_TAG)
AUTH_TALENT_PARSE = require_permission_or_403(PermCode.TALENT_PARSE_RESUME)


@router.post("", response_model=ResponseModel[TalentResponse], summary="创建人才档案")
async def create_talent(
    talent_data: TalentCreate,
    db: Session = Depends(get_mysql_session),
    current_user: User = Depends(AUTH_TALENT_CREATE)
):
    """创建人才档案"""
    talent = TalentService.create_talent(db, talent_data)
    
    return ResponseModel(
        code=201,
        message="创建成功",
        data=TalentResponse.model_validate({**talent.__dict__, 'department_name': talent.department.org_name if getattr(talent, 'department', None) else None})
    )


@router.get("/{talent_id}", response_model=ResponseModel[TalentResponse], summary="获取人才详情")
async def get_talent(
    talent_id: int,
    db: Session = Depends(get_mysql_session),
    current_user: User = Depends(AUTH_TALENT_VIEW)
):
    """获取人才详情（按字段级权限脱敏 + 行级数据范围隔离）"""
    talent = TalentService.get_talent_by_id(
        db, talent_id,
        scope_predicate=build_talent_scope_predicate(current_user, db)
    )
    
    return ResponseModel(
        code=200,
        message="获取成功",
        data=apply_field_masking(TalentResponse.model_validate(talent), current_user, db)
    )


@router.put("/{talent_id}", response_model=ResponseModel[TalentResponse], summary="更新人才档案")
async def update_talent(
    talent_id: int,
    talent_data: TalentUpdate,
    db: Session = Depends(get_mysql_session),
    current_user: User = Depends(AUTH_TALENT_UPDATE)
):
    """更新人才档案"""
    talent = TalentService.update_talent(db, talent_id, talent_data)
    
    return ResponseModel(
        code=200,
        message="更新成功",
        data=TalentResponse.model_validate({**talent.__dict__, 'department_name': talent.department.org_name if getattr(talent, 'department', None) else None})
    )


@router.delete("/{talent_id}", response_model=ResponseModel, summary="删除人才档案")
async def delete_talent(
    talent_id: int,
    db: Session = Depends(get_mysql_session),
    current_user: User = Depends(AUTH_TALENT_DELETE)
):
    """删除人才档案"""
    TalentService.delete_talent(db, talent_id)
    
    return ResponseModel(
        code=200,
        message="删除成功"
    )


@router.post("/batch-delete", response_model=ResponseModel, summary="批量删除人才档案")
async def batch_delete_talents(
    payload: Dict[str, Any],
    db: Session = Depends(get_mysql_session),
    current_user: User = Depends(AUTH_TALENT_DELETE)
):
    """批量删除人才档案（整页删除）"""
    talent_ids = payload.get("ids") or payload.get("talent_ids") or []
    if not talent_ids:
        raise HTTPException(status_code=400, detail="ids 必填")
    try:
        result = TalentService.batch_delete_talents(db, [int(i) for i in talent_ids])
        return ResponseModel(
            code=200,
            message=f"批量删除完成：成功 {result['deleted']} 条",
            data=result
        )
    except Exception as e:
        logger.error(f"批量删除人才失败(user={current_user.username}): {e}")
        raise HTTPException(status_code=500, detail="批量删除失败")


@router.get("", response_model=ResponseModel[TalentListResponse], summary="人才列表")
async def list_talents(
    page: int = Query(1, ge=1),
    page_size: int = Query(10, ge=1, le=100),
    name: Optional[str] = None,
    phone: Optional[str] = None,
    status: Optional[str] = None,
    keyword: Optional[str] = Query(None, description="关键词(姓名/手机号/邮箱)"),
    gender: Optional[str] = Query(None, description="性别: male/female"),
    education: Optional[str] = Query(None, description="学历: 高中/大专/本科/硕士/博士"),
    db: Session = Depends(get_mysql_session),
    current_user: User = Depends(AUTH_TALENT_VIEW)
):
    """获取人才列表（按字段级权限脱敏 + 行级数据范围隔离）"""
    talents, total = TalentService.list_talents(
        db=db,
        page=page,
        page_size=page_size,
        name=name,
        phone=phone,
        status=status,
        keyword=keyword,
        gender=gender,
        education=education,
        scope_predicate=build_talent_scope_predicate(current_user, db)
    )
    
    # 计算总页数
    total_pages = (total + page_size - 1) // page_size
    
    return ResponseModel(
        code=200,
        message="获取成功",
        data=TalentListResponse(
            items=[apply_field_masking(
                TalentResponse.model_validate({
                    **t.__dict__,
                    'department_name': t.department.org_name if t.department else None,
                }),
                current_user, db,
            ) for t in talents],
            total=total,
            page=page,
            page_size=page_size,
            total_pages=total_pages
        )
    )


@router.post("/search", response_model=ResponseModel[TalentListResponse], summary="人才搜索")
async def search_talents(
    search_data: TalentSearchRequest,
    db: Session = Depends(get_mysql_session),
    current_user: User = Depends(AUTH_TALENT_VIEW)
):
    """人才搜索（支持向量搜索；结果按字段级权限脱敏）"""
    talents, total = TalentService.search_talents(
        db, search_data,
        scope_predicate=build_talent_scope_predicate(current_user, db)
    )
    
    # 计算总页数
    total_pages = (total + search_data.page_size - 1) // search_data.page_size
    
    return ResponseModel(
        code=200,
        message="搜索成功",
        data=TalentListResponse(
            items=[apply_field_masking(TalentResponse.model_validate(t), current_user, db) for t in talents],
            total=total,
            page=search_data.page,
            page_size=search_data.page_size,
            total_pages=total_pages
        )
    )


@router.post("/parse-resume", response_model=ResponseModel[ResumeParseResponse], summary="解析简历")
async def parse_resume(
    file: UploadFile = File(...),
    db: Session = Depends(get_mysql_session),
    current_user: User = Depends(AUTH_TALENT_PARSE)
):
    """解析简历（PDF/Word/图片），提取字段、生成标签与画像，并自动落库人才档案"""
    ext = os.path.splitext(file.filename or "resume.pdf")[1].lower()
    file_content = await file.read()

    # 通过 magic bytes 嗅探真实文件类型，纠正错误的扩展名
    # （如 .pdf 扩展但内容是 txt；或反之）。覆盖常见四种二进制/文本场景。
    def _detect_ext(content: bytes) -> str:
        head = content[:8]
        if head.startswith(b'%PDF-'):
            return '.pdf'
        if head.startswith(b'PK\x03\x04'):
            return '.docx'
        if head.startswith(b'\xd0\xcf\x11\xe0'):
            return '.doc'
        if head.startswith(b'\xff\xd8\xff') or head.startswith(b'\x89PNG'):
            return '.png'
        # 二进制嗅探失败时，改用"可打印字符占比"判定文本类（txt/md/csv）
        sample = content[:4096]
        printable = sum(1 for b in sample if 9 <= b <= 13 or 32 <= b < 127 or b >= 0x80)
        if sample and printable / len(sample) > 0.85:
            return '.txt'
        return ''
    real_ext = _detect_ext(file_content)
    if real_ext and real_ext != ext:
        logger.info(f"扩展名 {ext} 与内容不符，按真实类型纠正为 {real_ext}")
        ext = real_ext

    # 显式大小校验（应用层兜底，避免依赖 Nginx 的 client_max_body_size）
    max_size = getattr(settings, "MAX_UPLOAD_SIZE", 52428800)  # 默认 50MB
    if len(file_content) > max_size:
        raise HTTPException(
            status_code=413,
            detail=f"文件过大（{len(file_content) / 1024 / 1024:.1f}MB），超过上限 {max_size / 1024 / 1024:.0f}MB"
        )

    # 上传到MinIO持久化存储
    minio_client = MinioClient(BUCKET_RESUMES)
    minio_object_name = f"resume_{uuid.uuid4().hex}{ext}"
    try:
        minio_client.upload_file_for_bucket(
            file_object=file_content,
            original_name=file.filename or "resume.pdf",
            bucket_name=BUCKET_RESUMES,
            minio_object_name=minio_object_name
        )
    except Exception as e:
        logger.warning(f"MinIO上传失败，降级到本地存储: {e}")

    # 写入本地临时文件供解析用（解析完成后删除）
    # upload_dir = getattr(settings, "UPLOAD_DIR", "./uploads") or "./uploads"
    # os.makedirs(upload_dir, exist_ok=True)
    # ext = os.path.splitext(file.filename or "resume.pdf")[1].lower()
    # save_path = os.path.join(upload_dir, f"resume_{uuid.uuid4().hex}{ext}")
    # with open(save_path, "wb") as f:
    #     f.write(await file.read())
    upload_dir = getattr(settings, "UPLOAD_DIR", "./uploads") or "./uploads"
    os.makedirs(upload_dir, exist_ok=True)
    save_path = os.path.join(upload_dir, f"resume_{uuid.uuid4().hex}{ext}")
    with open(save_path, "wb") as f:
        f.write(file_content)

    result = await resume_parser_agent.parse_resume(save_path, file.filename or "resume")

    # 解析完成后删除本地临时文件（MinIO已有持久化副本）
    _safe_remove(save_path)

    created_talent_id = None
    merged_existing_flag = False
    merged_message: Optional[str] = None
    td = result.get("talent_data") or {}
    # 核心字段（姓名+手机号）抽取成功即建档；标签/画像等AI增强失败仅降级，不阻断建档（符合降级原则）
    if td.get("name") and td.get("phone"):
        try:
            gender = GenderEnum.MALE
            if str(td.get("gender") or "").strip().lower() in ("female", "女", "2"):
                gender = GenderEnum.FEMALE
            education = None
            if td.get("education") in [e.value for e in EducationLevel]:
                education = EducationLevel(td["education"])

            # 把 LLM 提取的 skills 拆成技能证书结构化列表
            # （匹配 Agent 的硬条件过滤依赖 skills_certificates，不传会导致所有岗位都被过滤掉）
            raw_skills_val = td.get("skills")
            if isinstance(raw_skills_val, list):
                # LLM 直接返回 list（如 ["Python", "分布式"]）
                skill_items = [{"name": str(s).strip(), "level": "熟悉"}
                              for s in raw_skills_val if s and str(s).strip()]
            elif isinstance(raw_skills_val, str):
                # LLM 返回字符串（如 "Python、Java、分布式系统"）
                import re
                parts = re.split(r"[、，,;/｜\|\s]+", raw_skills_val)
                skill_items = [{"name": p.strip(), "level": "熟悉"}
                               for p in parts if p and p.strip() and len(p.strip()) <= 50]
            else:
                skill_items = []

            talent_in = TalentCreate(
                name=str(td["name"]),
                gender=gender,
                phone=str(td["phone"]),
                email=td.get("email"),
                education=education,
                major=td.get("major"),
                experience_years=int(td["experience_years"]) if td.get("experience_years") is not None else None,
                current_company=td.get("current_company"),
                current_position=td.get("current_position"),
                self_introduction=td.get("self_introduction"),
                status="reserve",
                skills_certificates=skill_items,
                tags=result.get("tags") or [],
            )
            try:
                talent = TalentService.create_talent(db, talent_in)
            except DuplicateKeyException:
                # 手机号/邮箱已存在 → 复用现有档案并刷新画像/标签
                existing = db.query(_Talent).filter(_Talent.phone == talent_in.phone).first()
                if not existing and talent_in.email:
                    existing = db.query(_Talent).filter(_Talent.email == talent_in.email).first()
                if existing:
                    if result.get("portrait"):
                        existing.portrait = result["portrait"]
                    if result.get("tags"):
                        existing.tags = result["tags"]
                    if skill_items:
                        merged = list(existing.skills_certificates or [])
                        for si in skill_items:
                            if si not in merged:
                                merged.append(si)
                        existing.skills_certificates = merged
                    db.commit()
                    db.refresh(existing)
                    logger.info(f"手机号冲突，复用现有档案 id={existing.id}")
                    created_talent_id = existing.id
                    merged_existing_flag = True
                    merged_message = f"手机号 {talent_in.phone} 已存在，已并入现有档案 (id={existing.id})"
                else:
                    raise
            else:
                created_talent_id = talent.id
                if result.get("portrait"):
                    talent.portrait = result["portrait"]
                    db.commit()
        except Exception as e:
            logger.warning(f"简历解析落库失败（仍返回解析结果）: {type(e).__name__}: {e}")

    return ResponseModel(
        code=200,
        message="简历解析完成" if result.get("success") else "简历解析部分完成",
        data={
            "success": result.get("success"),
            "talent_data": result.get("talent_data"),
            "tags": result.get("tags"),
            "portrait": result.get("portrait"),
            "confidence": result.get("confidence"),
            "created_talent_id": created_talent_id,
            "merged_existing": merged_existing_flag,
            "merge_message": merged_message,
            "warnings": result.get("warnings"),
        }
    )


@router.post("/batch-import", response_model=ResponseModel, summary="批量导入/数据迁移")
async def batch_import_talents(
    file: UploadFile = File(...),
    db: Session = Depends(get_mysql_session),
    current_user: User = Depends(AUTH_TALENT_IMPORT)
):
    """历史数据批量迁移导入（Excel/CSV），含清洗与去重，返回迁移报告"""
    from app.services.migration_service import import_talents_from_file, save_report
    ext = os.path.splitext(file.filename or "import.xlsx")[1].lower()
    file_content = await file.read()

    # 上传到MinIO持久化存储
    minio_client = MinioClient(BUCKET_IMPORTS)
    minio_object_name = f"import_{uuid.uuid4().hex}{ext}"
    try:
        minio_client.upload_file_for_bucket(
            file_object=file_content,
            original_name=file.filename or "import.xlsx",
            bucket_name=BUCKET_IMPORTS,
            minio_object_name=minio_object_name
        )
    except Exception as e:
        logger.warning(f"MinIO上传失败，降级到本地存储: {e}")

    # 写入本地临时文件供解析用（导入完成后删除）
    # upload_dir = getattr(settings, "UPLOAD_DIR", "./uploads") or "./uploads"
    # os.makedirs(upload_dir, exist_ok=True)
    # ext = os.path.splitext(file.filename or "import.xlsx")[1].lower()
    # save_path = os.path.join(upload_dir, f"import_{uuid.uuid4().hex}{ext}")
    # with open(save_path, "wb") as f:
    #     f.write(await file.read())
    upload_dir = getattr(settings, "UPLOAD_DIR", "./uploads") or "./uploads"
    os.makedirs(upload_dir, exist_ok=True)
    save_path = os.path.join(upload_dir, f"import_{uuid.uuid4().hex}{ext}")
    with open(save_path, "wb") as f:
        f.write(file_content)

    report = import_talents_from_file(db, save_path)

    # 导入完成后删除本地临时文件（MinIO已有持久化副本）
    _safe_remove(save_path)
    report_file = save_report(report)
    data = report.to_dict()
    data["report_file"] = report_file
    return ResponseModel(code=200, message="数据迁移完成", data=data)


@router.get("/{talent_id}/portrait", response_model=ResponseModel, summary="获取人才画像")
async def get_talent_portrait(
    talent_id: int,
    db: Session = Depends(get_mysql_session),
    current_user: User = Depends(AUTH_TALENT_VIEW)
):
    """获取人才画像（智能画像，未生成时基于档案生成摘要）"""
    talent = TalentService.get_talent_by_id(
        db, talent_id,
        scope_predicate=build_talent_scope_predicate(current_user, db)
    )
    portrait = talent.portrait or {}
    if not portrait:
        portrait = {
            "summary": f"{talent.name}，{talent.education.value if talent.education else ''}学历，{talent.experience_years or 0}年经验",
            "education": talent.education.value if talent.education else None,
            "experience_years": talent.experience_years,
            "skills": [s.get("name") for s in (talent.skills_certificates or []) if isinstance(s, dict)],
            "tags": talent.tags or [],
        }
    return ResponseModel(
        code=200,
        message="获取成功",
        data={"talent_id": talent.id, "portrait": portrait, "capability_rating": talent.capability_rating}
    )


@router.post("/{talent_id}/tags", response_model=ResponseModel, summary="更新人才标签")
async def update_talent_tags(
    talent_id: int,
    tags: List[str] = Body(..., embed=True),
    db: Session = Depends(get_mysql_session),
    current_user: User = Depends(AUTH_TALENT_TAG)
):
    """更新人才标签（200+多维标签）"""
    talent = TalentService.update_tags(db, talent_id, tags)
    return ResponseModel(code=200, message="标签更新成功", data={"talent_id": talent.id, "tags": talent.tags})


@router.get("/{talent_id}/check-duplicate", response_model=ResponseModel, summary="查重检测")
async def check_duplicate_talent(
    talent_id: int,
    db: Session = Depends(get_mysql_session),
    current_user: User = Depends(AUTH_TALENT_VIEW)
):
    """人才查重检测"""
    duplicates = TalentService.check_duplicate(db, talent_id)
    
    return ResponseModel(
        code=200,
        message="查重完成",
        data={
            "has_duplicate": len(duplicates) > 0,
            "duplicates": duplicates
        }
    )
