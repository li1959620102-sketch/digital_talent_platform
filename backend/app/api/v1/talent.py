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
from app.utils.resume_parser import (
    normalize_phone,
    normalize_education,
    normalize_experience_years,
    extract_phone_from_text,
)
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


# ==================== 简历向量同步 ====================
# 为什么必须有这一步：talent_resume 集合历史上只由离线脚本
# scripts/seed_vector_index.py 灌库，在线「上传简历 → 解析 → 建档」链路里
# 完全没有写向量。结果是新上传的简历在语义检索里永远搜不到，
# AI 简历筛选会直接漏掉这些人，且 MySQL 与 Milvus 两侧数据量对不上
# （实测建档 15 条后：MySQL 1216 / Milvus 仍 1201）。

_vector_service_singleton = None


def _get_vector_service():
    """进程内单例：避免每次解析都重建 embedding 客户端。"""
    global _vector_service_singleton
    if _vector_service_singleton is None:
        from app.services.vector_search_service import VectorSearchService
        _vector_service_singleton = VectorSearchService()
    return _vector_service_singleton


def _sync_talent_vector(
    talent_id: Optional[int],
    text: str,
    file_id: str = "",
    file_name: str = "",
) -> Optional[int]:
    """建档成功后把简历写入 Milvus，失败只告警不阻断建档（遵循项目降级原则）。

    先删旧向量再插新的：重复上传同一份简历时，否则向量会一条条堆积，
    同一份简历被检索命中多次。过滤式删除要求集合处于 loaded 状态，
    所以先 load 再 delete。
    """
    if not talent_id or not text or not text.strip():
        return None
    try:
        svc = _get_vector_service()
        try:
            from app.core.milvus_client import MilvusService
            col = MilvusService(settings.MILVUS_COLLECTION_TALENT)
            svc._run(col.load())
            removed = svc._run(col.delete(f'talent_id == "{talent_id}"'))
            if removed:
                logger.info(f"清理人才 {talent_id} 的旧简历向量 {removed} 条")
        except Exception as e:  # noqa: BLE001
            # 删不掉不阻断：可能是首次入库（本来就没有旧向量）
            logger.debug(f"清理旧简历向量跳过: {e}")

        return svc.create_talent_resume_vector(
            talent_id=talent_id,
            text=text[:8000],
            metadata={
                "file_id": file_id or "",
                "file_name": (file_name or "")[:512],
                "chunk_id": f"t{talent_id}",
            },
        )
    except Exception as e:  # noqa: BLE001
        logger.warning(f"简历向量写入失败（不影响建档）: {type(e).__name__}: {e}")
        return None


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
    minio_uploaded = True
    try:
        minio_client.upload_file_for_bucket(
            file_object=file_content,
            original_name=file.filename or "resume.pdf",
            bucket_name=BUCKET_RESUMES,
            minio_object_name=minio_object_name
        )
    except Exception as e:
        # 上传失败时不要把对象名写回档案：本地临时文件在解析后会被删除，
        # 写回引用会指向一个根本不存在的对象（悬空引用）。
        minio_uploaded = False
        logger.warning(f"MinIO上传失败，本次不建立简历文件引用: {e}")

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
    # Agent 返回的原文键名是 raw_text（见 resume_parser_agent.parse_resume 的返回值），
    # 不是 text。取错键会让下面所有「原文兜底」静默失效——这正是之前手机号和
    # 工作年限拿不到兜底值的原因。兼容两个键名以防 Agent 返回结构变化。
    resume_text = result.get("raw_text") or result.get("text") or ""

    # ── LLM 输出规范化（不可信，必须收敛后再入库）────────────────────────
    # 实测踩到的坑：LLM 会把规则层已抽对的手机号覆盖成带横线的原串、
    # 把学历返回成"本科/硕士"这种非枚举值、把"五年经验"漏掉不做数值化。
    phone_norm = normalize_phone(td.get("phone"))
    if not phone_norm:
        # LLM 漏给或给错 → 从简历原文捞（容忍 "138-0013-8001" 这类带分隔符写法）。
        # 走到这里仍为空则确实无法建档：phone 是必填且唯一的建档主键。
        phone_norm = extract_phone_from_text(resume_text)

    edu_norm = normalize_education(td.get("education")) or normalize_education(resume_text)
    exp_norm = normalize_experience_years(td.get("experience_years"), fallback_text=resume_text)

    parse_warnings = list(result.get("warnings") or [])
    if phone_norm:
        # Agent 是在 LLM 原始输出上做的格式校验（如带横线的 "138-0013-8001"），
        # 规范化已经把它修好了，这条告警此时已不适用，必须剔除，
        # 否则会出现「phone 已正确却仍报格式错误」的自相矛盾输出。
        parse_warnings = [w for w in parse_warnings if "手机号格式" not in str(w)]
    elif td.get("phone"):
        parse_warnings.append("手机号格式无法识别")
    if not minio_uploaded:
        parse_warnings.append("对象存储上传失败，简历文件未建立引用")

    # 核心字段（姓名+手机号）抽取成功即建档；标签/画像等AI增强失败仅降级，不阻断建档（符合降级原则）
    if td.get("name") and phone_norm:
        try:
            gender = GenderEnum.MALE
            if str(td.get("gender") or "").strip().lower() in ("female", "女", "2"):
                gender = GenderEnum.FEMALE
            education = None
            if edu_norm in [e.value for e in EducationLevel]:
                education = EducationLevel(edu_norm)

            # 把 LLM 提取的 skills 拆成技能证书结构化列表
            # （匹配 Agent 的硬条件过滤依赖 skills_certificates，不传会导致所有岗位都被过滤掉）
            raw_skills_val = td.get("skills")
            if isinstance(raw_skills_val, list):
                # LLM 直接返回 list（如 ["Python", "分布式"])。
                # 必须保序去重：实测 1.7B 模型会输出重复项（Python/FastAPI/MySQL
                # 各出现两次），重复技能会污染岗位匹配的硬条件过滤。
                seen_skills = set()
                skill_items = []
                for s in raw_skills_val:
                    name = str(s).strip()
                    key = name.lower()
                    if not name or key in seen_skills or len(name) > 50:
                        continue
                    seen_skills.add(key)
                    skill_items.append({"name": name, "level": "熟悉"})
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
                phone=phone_norm,
                email=td.get("email"),
                education=education,
                major=td.get("major"),
                experience_years=exp_norm,
                current_company=td.get("current_company"),
                current_position=td.get("current_position"),
                self_introduction=td.get("self_introduction"),
                status="reserve",
                skills_certificates=skill_items,
                tags=result.get("tags") or [],
                # 关键回填：把刚上传成功的对象名与解析标记写回档案，
                # 否则 MinIO 里有文件、档案里 is_parsed=0 / resume_file_id=NULL，
                # 文件与档案之间没有任何关联，属于真实的链路断裂。
                resume_file_id=minio_object_name if minio_uploaded else None,
                resume_file_name=file.filename,
                is_parsed=True,
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
                        # 必须按 **name** 去重，不能用 `si not in merged` 整字典比较。
                        # 实测踩坑：库里已有项由 SkillCertificateBase.model_dump() 生成，
                        # 带 expiry_date/obtained_date/issuing_authority 等字段，
                        # 而这里新构造的只有 {name, level}，整字典比较恒为"不相等"，
                        # 于是每次重复上传都会把同名技能再追加一遍（实测堆到 28 项、
                        # 其中 12 项完全重复）。顺带把历史遗留的重复项一并压掉。
                        deduped, seen_names = [], set()
                        for x in list(existing.skills_certificates or []) + skill_items:
                            if not isinstance(x, dict):
                                continue
                            nm = str(x.get("name", "")).strip()
                            key = nm.lower()
                            if not nm or key in seen_names:
                                continue
                            seen_names.add(key)
                            deduped.append(x)
                        existing.skills_certificates = deduped
                    # 复用已有档案时同样要回填简历引用与解析标记，
                    # 否则重复上传同一份简历仍然拿不到文件关联。
                    if minio_uploaded and not existing.resume_file_id:
                        existing.resume_file_id = minio_object_name
                    if file.filename:
                        existing.resume_file_name = file.filename
                    existing.is_parsed = True
                    # 学历与年限用本次解析结果覆盖：重复上传时这就是同一份简历的
                    # 最新解析结论，是权威来源。若只填空，被 LLM 误判的旧值
                    # （如 experience_years=3，而原文写的是"五年"）永远修不回来。
                    if education is not None:
                        existing.education = education
                    if exp_norm is not None:
                        existing.experience_years = exp_norm
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

    # ── 建档/合并成功后同步向量库 ──
    # 放在落库 try 之外单独 try：向量化依赖 Ollama bge-m3 + Milvus，任一不可用
    # 都只降级告警，绝不能反过来影响已经建好的档案（降级不阻断原则）。
    resume_vector_id = None
    if created_talent_id:
        resume_vector_id = _sync_talent_vector(
            talent_id=created_talent_id,
            text=resume_text,
            file_id=minio_object_name if minio_uploaded else "",
            file_name=file.filename or "",
        )

    return ResponseModel(
        code=200,
        message="简历解析完成" if result.get("success") else "简历解析部分完成",
        data={
            "success": result.get("success"),
            "talent_data": {
                **td,
                # 回传规范化后的值，让调用方看到的与实际入库的一致
                "phone": phone_norm or td.get("phone"),
                "education": edu_norm or td.get("education"),
                "experience_years": exp_norm if exp_norm is not None
                else td.get("experience_years"),
            },
            "tags": result.get("tags"),
            "portrait": result.get("portrait"),
            "confidence": result.get("confidence"),
            "created_talent_id": created_talent_id,
            "merged_existing": merged_existing_flag,
            "merge_message": merged_message,
            "resume_file_id": minio_object_name if minio_uploaded else None,
            "resume_vector_id": resume_vector_id,
            "warnings": parse_warnings,
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
