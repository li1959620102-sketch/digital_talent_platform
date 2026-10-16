"""幂等导入项目知识库文档并完成向量化。

用法（容器内）：
    python -m scripts.import_knowledge_base \
      --source /workspace/docs/knowledge_base \
      --source /workspace/backend/media/knowledge

脚本按文件 SHA-256 去重；已登记且状态为 vectorized 的文件不会重复切片或写入 Milvus。
"""
from __future__ import annotations

import argparse
import asyncio
import hashlib
import shutil
from pathlib import Path

from sqlalchemy import or_

from app.core.database import get_mysql_session_factory
from app.core.milvus_client import init_milvus
from app.models.knowledge import KnowledgeFile
from app.services.knowledge_service import KnowledgeService
from app.services.rag_search_service import refresh_bm25_index


def knowledge_type(path: Path) -> str:
    name = path.name.lower()
    if name.startswith(("01_", "02_", "04_", "05_")):
        return "平台技术"
    if name.startswith("03_"):
        return "标准"
    try:
        text = path.read_text(encoding="utf-8", errors="ignore")[:5000].lower()
    except OSError:
        text = ""
    corpus = name + " " + text
    if any(k in corpus for k in ("岗位", "匹配", "算法", "任职资格", "胜任力")):
        return "标准"
    if any(k in corpus for k in ("权限", "制度", "操作", "手册", "审批", "管理办法")):
        return "制度"
    if any(k in corpus for k in ("agent", "workflow", "rag", "dify", "智能体", "向量检索")):
        return "平台技术"
    if any(k in corpus for k in ("培训", "课程", "培养", "学习路径")):
        return "课件"
    return "其他"


def digest(path: Path) -> str:
    hasher = hashlib.sha256()
    with path.open("rb") as handle:
        for block in iter(lambda: handle.read(1024 * 1024), b""):
            hasher.update(block)
    return hasher.hexdigest()


def run(sources: list[Path], destination: Path) -> None:
    files: list[Path] = []
    for source in sources:
        if source.is_file() and source.suffix.lower() in {".md", ".txt", ".csv"}:
            files.append(source)
        elif source.is_dir():
            files.extend(p for p in source.rglob("*") if p.is_file() and p.suffix.lower() in {".md", ".txt", ".csv"})
    files = sorted({p.resolve() for p in files})
    if not files:
        raise RuntimeError("没有找到可导入的 md/txt/csv 文档")

    factory = get_mysql_session_factory()
    if factory is None:
        raise RuntimeError("MySQL 未初始化")
    destination.mkdir(parents=True, exist_ok=True)
    service = KnowledgeService()
    db = factory()
    stats = {"found": len(files), "registered": 0, "vectorized": 0, "skipped": 0, "failed": 0, "chunks": 0}
    try:
        for source in files:
            file_hash = digest(source)
            existing = db.query(KnowledgeFile).filter(
                or_(KnowledgeFile.file_path.like(f"%/{file_hash}.%"), KnowledgeFile.file_path.like(f"%\\{file_hash}.%"))
            ).first()
            if existing and existing.status == "vectorized":
                # 即使向量已经存在，也刷新来源文件名和业务分类，便于知识库运营检索。
                changed = False
                # 目标目录中的 SHA-256 副本仅用于持久化，不覆盖原始来源文件名。
                is_hash_copy = len(source.stem) == 64 and all(c in "0123456789abcdef" for c in source.stem.lower())
                if not is_hash_copy and existing.file_name != source.name:
                    existing.file_name = source.name
                    changed = True
                category = knowledge_type(source) if not is_hash_copy else existing.knowledge_type
                if existing.knowledge_type != category:
                    existing.knowledge_type = category
                    changed = True
                if changed:
                    db.commit()
                stats["skipped"] += 1
                stats["chunks"] += existing.chunk_count or 0
                continue

            target = destination / f"{file_hash}{source.suffix.lower()}"
            if source.resolve() != target.resolve():
                shutil.copyfile(source, target)
            if existing:
                file_record = existing
                file_record.file_path = str(target)
                file_record.file_size = target.stat().st_size
                file_record.file_name = source.name
                file_record.knowledge_type = knowledge_type(source)
                db.commit()
            else:
                file_record = service.save_file_metadata(
                    db,
                    file_name=source.name,
                    file_type=source.suffix.lower().lstrip("."),
                    file_size=target.stat().st_size,
                    file_path=str(target),
                    knowledge_type=knowledge_type(source),
                    permission_level=0,
                )
                stats["registered"] += 1
            result = service.vectorize_file(db, file_record.id)
            if result.get("success"):
                stats["vectorized"] += 1
                stats["chunks"] += int(result.get("chunk_count") or file_record.chunk_count or 0)
            else:
                stats["failed"] += 1
                print(f"导入失败: {source.name}: {result.get('message')}")
        # 进程启动时 BM25 是惰性的；即使本轮全部幂等跳过，也要从 MySQL 重建关键词索引。
        chunks = db.query(__import__('app.models.knowledge', fromlist=['KnowledgeChunk']).KnowledgeChunk).all()
        refresh_bm25_index([
            {"id": str(chunk.id), "text": chunk.content or "", "metadata": {"file_id": str(chunk.file_id)}}
            for chunk in chunks if chunk.content
        ])
        print(f"知识库导入完成: {stats}")
    finally:
        db.close()


def main() -> None:
    parser = argparse.ArgumentParser(description="幂等导入知识库并完成 Milvus 向量化")
    parser.add_argument("--source", action="append", required=True, type=Path)
    parser.add_argument("--destination", type=Path, default=Path("media/knowledge"))
    args = parser.parse_args()
    asyncio.run(init_milvus())
    run(args.source, args.destination)


if __name__ == "__main__":
    main()
