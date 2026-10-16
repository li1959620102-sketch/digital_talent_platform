"""
知识库 RAG API 路由（P1：RAG 知识库）
实现：知识文档上传、向量化、语义检索、RAG 问答。
遵循项目规则：检索前执行权限过滤，禁止 AI 越权访问；Milvus/LLM 不可用时优雅降级。
"""
import os
from fastapi import APIRouter, Depends, HTTPException, UploadFile, File, Form, Query
from sqlalchemy.orm import Session
from typing import Optional, Dict, Any

from app.core.database import get_mysql_session
from app.schemas.common import ResponseModel
from app.core.rbac import PermCode, require_permission_or_403, user_has_permission
from app.services.knowledge_service import KnowledgeService
from app.core.config import settings
from app.utils.minio_client import MinioClient, BUCKET_KNOWLEDGE

router = APIRouter()
_knowledge_service = KnowledgeService()
AUTH_KNOWLEDGE_VIEW = require_permission_or_403(PermCode.KNOWLEDGE_VIEW)
AUTH_KNOWLEDGE_MANAGE = require_permission_or_403(PermCode.KNOWLEDGE_MANAGE)

ALLOWED_EXT = {".txt", ".md", ".csv", ".json", ".py", ".pdf", ".docx", ".doc"}


def _ensure_dir(path: str):
    os.makedirs(path, exist_ok=True)


@router.post("/upload", response_model=ResponseModel, summary="上传知识文档")
async def upload_knowledge(
    file: UploadFile = File(...),
    knowledge_type: str = Form("other"),
    permission_level: int = Form(0),
    db: Session = Depends(get_mysql_session),
    current_user: dict = Depends(AUTH_KNOWLEDGE_MANAGE)
):
    """上传知识文档（简历/岗位说明/人才制度/培训课件/测评标准/历史案例/培养方案等）"""
    ext = os.path.splitext(file.filename or "")[1].lower()
    if ext not in ALLOWED_EXT:
        raise HTTPException(status_code=400, detail=f"不支持的文件类型: {ext}")

    content = await file.read(settings.MAX_UPLOAD_SIZE + 1)
    if len(content) > settings.MAX_UPLOAD_SIZE:
        raise HTTPException(
            status_code=413,
            detail=f"文件大小不能超过 {settings.MAX_UPLOAD_SIZE // 1024 // 1024}MB",
        )
    if permission_level < 0 or permission_level > 999:
        raise HTTPException(status_code=400, detail="permission_level 必须在 0 到 999 之间")

    # 上传到MinIO持久化存储
    import uuid as _uuid
    import time as _time
    stored_name = f"{int(_time.time()*1000)}{_uuid.uuid4().hex[:6]}{ext}"
    minio_client = MinioClient(BUCKET_KNOWLEDGE)
    try:
        minio_client.upload_file_for_bucket(
            file_object=content,
            original_name=file.filename or "document",
            bucket_name=BUCKET_KNOWLEDGE,
            minio_object_name=stored_name
        )
    except Exception as e:
        import logging
        logging.getLogger(__name__).warning(f"MinIO上传失败，降级到本地存储: {e}")

    # 同时写入本地文件（供向量化读取）
    # _ensure_dir(settings.MEDIA_ROOT)
    # knowledge_dir = os.path.join(settings.MEDIA_ROOT, "knowledge")
    # _ensure_dir(knowledge_dir)
    # stored_name = f"{int(_time.time()*1000)}{_uuid.uuid4().hex[:6]}{ext}"
    # file_path = os.path.join(knowledge_dir, stored_name)
    # content = await file.read()
    _ensure_dir(settings.MEDIA_ROOT)
    knowledge_dir = os.path.join(settings.MEDIA_ROOT, "knowledge")
    _ensure_dir(knowledge_dir)
    file_path = os.path.join(knowledge_dir, stored_name)
    with open(file_path, "wb") as f:
        f.write(content)

    record = _knowledge_service.save_file_metadata(
        db,
        file_name=file.filename,
        file_type=ext.lstrip("."),
        file_size=len(content),
        file_path=file_path,
        knowledge_type=knowledge_type,
        permission_level=permission_level,
        uploader_id=current_user.id
    )
    return ResponseModel(code=200, message="上传成功", data={
        "id": record.id, "file_code": record.file_code, "file_name": record.file_name,
        "status": record.status, "knowledge_type": record.knowledge_type
    })


@router.post("/vectorize", response_model=ResponseModel, summary="向量化处理")
async def vectorize_knowledge(
    payload: Dict[str, Any],
    db: Session = Depends(get_mysql_session),
    current_user: dict = Depends(AUTH_KNOWLEDGE_MANAGE)
):
    """对指定知识文件进行切片、Embedding 并写入 Milvus 向量库"""
    file_id = payload.get("file_id")
    if not file_id:
        raise HTTPException(status_code=400, detail="file_id 必填")
    result = _knowledge_service.vectorize_file(db, file_id)
    if not result.get("success"):
        return ResponseModel(code=500, message=result.get("message", "向量化失败"), data=result)
    return ResponseModel(code=200, message="向量化完成", data=result)


@router.post("/search", response_model=ResponseModel, summary="知识检索")
async def search_knowledge(
    payload: Dict[str, Any],
    db: Session = Depends(get_mysql_session),
    current_user: dict = Depends(AUTH_KNOWLEDGE_VIEW)
):
    """语义检索知识库（带权限过滤）"""
    query = payload.get("query") or payload.get("question")
    if not query:
        raise HTTPException(status_code=400, detail="query 必填")
    top_k = payload.get("top_k", 5)
    _knowledge_service._ensure_bm25_index(db)
    # 权限：用户权限级别越低可访问范围越小（permission_level <= 用户级别）
    permission_level = 999 if user_has_permission(current_user, PermCode.KNOWLEDGE_MANAGE, db) else 0
    _knowledge_service._ensure_bm25_index(db)
    results = _knowledge_service.search(query, top_k=top_k, permission_level=permission_level, db=db)
    return ResponseModel(code=200, message="检索完成", data={"results": results, "count": len(results)})


@router.post("/qa", response_model=ResponseModel, summary="知识问答")
async def knowledge_qa(
    payload: Dict[str, Any],
    db: Session = Depends(get_mysql_session),
    current_user: dict = Depends(AUTH_KNOWLEDGE_VIEW)
):
    """基于知识库的 RAG 问答（检索→LLM→带来源追溯）"""
    query = payload.get("query") or payload.get("question")
    if not query:
        raise HTTPException(status_code=400, detail="query 必填")
    permission_level = 999 if user_has_permission(current_user, PermCode.KNOWLEDGE_MANAGE, db) else 0
    result = _knowledge_service.qa(query, permission_level=permission_level, top_k=payload.get("top_k", 5), db=db)
    return ResponseModel(code=200, message="问答完成", data=result)


@router.get("/files", response_model=ResponseModel, summary="知识文件列表")
async def list_knowledge_files(
    page: int = Query(1, ge=1),
    page_size: int = Query(20, ge=1, le=100),
    knowledge_type: Optional[str] = None,
    db: Session = Depends(get_mysql_session),
    current_user: dict = Depends(AUTH_KNOWLEDGE_VIEW)
):
    """知识文件列表"""
    max_permission_level = 999 if user_has_permission(current_user, PermCode.KNOWLEDGE_MANAGE, db) else 0
    items, total = _knowledge_service.list_files(
        db,
        page=page,
        page_size=page_size,
        knowledge_type=knowledge_type,
        max_permission_level=max_permission_level,
    )
    data = [{
        "id": f.id, "file_code": f.file_code, "file_name": f.file_name,
        "knowledge_type": f.knowledge_type, "status": f.status,
        "chunk_count": f.chunk_count, "permission_level": f.permission_level
    } for f in items]
    total_pages = (total + page_size - 1) // page_size
    return ResponseModel(code=200, message="获取成功", data={
        "items": data, "total": total, "page": page, "page_size": page_size, "total_pages": total_pages
    })


@router.delete("/files/{file_id}", response_model=ResponseModel, summary="删除知识文件")
async def delete_knowledge_file(
    file_id: int,
    db: Session = Depends(get_mysql_session),
    current_user: dict = Depends(AUTH_KNOWLEDGE_MANAGE)
):
    """删除知识文件（数据库记录 + 关联向量，保证 MySQL 与 Milvus 对齐）"""
    try:
        from app.models.knowledge import KnowledgeFile
        kf = db.query(KnowledgeFile).filter(KnowledgeFile.id == file_id).first()
        if not kf:
            raise HTTPException(status_code=404, detail="文件不存在")
        db.delete(kf)
        db.commit()
        # 级联清理 DB chunk + Milvus 向量（复用 service，避免孤儿向量）
        try:
            _knowledge_service.delete_file_vectors(db, file_id)
        except Exception:
            pass
        return ResponseModel(code=200, message="删除成功", data={"file_id": file_id})
    except HTTPException:
        raise
    except Exception as e:
        db.rollback()
        raise HTTPException(status_code=500, detail=f"删除失败: {str(e)}")


@router.post("/files/batch-delete", response_model=ResponseModel, summary="批量删除知识文件")
async def batch_delete_knowledge_files(
    payload: Dict[str, Any],
    db: Session = Depends(get_mysql_session),
    current_user: dict = Depends(AUTH_KNOWLEDGE_MANAGE)
):
    """批量删除知识文件（数据库记录 + Milvus 向量数据）"""
    ids = payload.get("ids") or payload.get("file_ids") or []
    if not ids:
        raise HTTPException(status_code=400, detail="ids 必填")
    try:
        from app.models.knowledge import KnowledgeFile
        # 一次性查出记录，便于级联清理 Milvus 向量
        records = db.query(KnowledgeFile).filter(KnowledgeFile.id.in_([int(i) for i in ids])).all()
        deleted_ids = [r.id for r in records]
        deleted_count = db.query(KnowledgeFile).filter(KnowledgeFile.id.in_(deleted_ids)).delete(synchronize_session=False)
        db.commit()
        # 清理 DB chunk + Milvus 向量（同步可靠，字段为 file_id，杜绝孤儿向量）
        for deleted_id in deleted_ids:
            try:
                _knowledge_service.delete_file_vectors(db, deleted_id)
            except Exception:
                pass
        return ResponseModel(code=200, message=f"批量删除成功：共删除 {deleted_count} 条", data={"deleted": deleted_count})
    except HTTPException:
        raise
    except Exception as e:
        db.rollback()
        raise HTTPException(status_code=500, detail=f"批量删除失败: {str(e)}")
