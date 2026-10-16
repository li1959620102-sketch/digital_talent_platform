"""
为 Milvus 的 talent_resume / job_position 两个集合灌入向量（幂等、可重复执行）。

背景：平台的 4 大 Milvus 集合里，knowledge_base（RAG 知识库）已有数据，但
talent_resume / job_position 长期为 0 —— 导致：
  · 人才检索的「向量搜索」开关无结果（app/services/talent_service.py）
  · 匹配 Agent 的向量召回阶段全部走规则兜底（app/agents/matching_agent.py）
本脚本按当前库内的人才/岗位生成文本描述，用 bge-m3 生成 1024 维向量写入 Milvus。

幂等策略：按批「先按主键删除旧向量，再插入新向量」，因此可安全重跑；
不会出现重复向量（与 knowledge_service.vectorize_file 同样的处理思路）。

用法（容器内）：
    python scripts/seed_vector_index.py                    # 两个集合全量
    python scripts/seed_vector_index.py --only talent      # 只灌人才
    python scripts/seed_vector_index.py --limit 50         # 先小批量试跑
"""
import argparse
import sys
import time
from typing import Any, Dict, List

from app.core.config import settings
from app.core.database import get_mysql_session
from app.core.milvus_client import MilvusService
from app.core.run_async import run_async
from app.models.position import JobPosition
from app.models.talent import Talent

BATCH_SIZE = 32
MAX_TEXT_LEN = 65535


def _join(values) -> str:
    """把 list / JSON 字段拼成可读文本"""
    if not values:
        return ""
    if isinstance(values, str):
        return values
    out = []
    for v in values:
        if isinstance(v, dict):
            out.append(str(v.get("name") or v.get("skill") or v))
        else:
            out.append(str(v))
    return "、".join(x for x in out if x)


def build_talent_text(t: Talent) -> str:
    """人才档案 → 用于语义检索的自述文本"""
    edu = t.education.value if hasattr(t.education, "value") else (t.education or "")
    parts = [
        f"姓名：{t.name or ''}",
        f"性别：{t.gender.value if hasattr(t.gender, 'value') else (t.gender or '')}",
        f"学历：{edu}",
        f"专业：{t.major or ''}",
        f"工作年限：{t.experience_years or 0}年",
        f"当前职位：{t.current_position or ''}",
        f"当前公司：{t.current_company or ''}",
        f"技能与证书：{_join(t.skills_certificates)}",
        f"标签：{_join(t.tags)}",
        f"自我评价：{t.self_introduction or ''}",
    ]
    return "；".join(p for p in parts if p.split("：", 1)[-1].strip())[:MAX_TEXT_LEN]


def build_position_text(p: JobPosition) -> str:
    """岗位 → 用于语义检索的岗位描述文本"""
    level = p.position_level.value if hasattr(p.position_level, "value") else (p.position_level or "")
    parts = [
        f"岗位名称：{p.position_name or ''}",
        f"岗位类别：{p.position_category or ''}",
        f"岗位级别：{level}",
        f"学历要求：{p.education_requirement or '不限'}",
        f"经验要求：{p.experience_requirement or 0}年",
        f"技能要求：{_join(p.skill_requirements)}",
        f"能力要求：{_join(p.capability_requirements)}",
        f"岗位描述：{p.job_description or ''}",
        f"岗位职责：{p.job_responsibilities or ''}",
    ]
    return "；".join(x for x in parts if x.split("：", 1)[-1].strip())[:MAX_TEXT_LEN]


def embed_texts(texts: List[str]) -> List[List[float]]:
    """调用 Ollama 原生 /api/embed 做**整批**向量化。

    为什么不用 langchain 的 OllamaEmbeddings：其 embed_documents 在当前版本里是
    **逐条发请求**的，实测单条冷启动可达 1m45s，1201 条要跑半小时以上。
    原生接口支持 input 传数组，一次请求批量返回，吞吐提升一个数量级。
    """
    import json
    import urllib.request

    payload = json.dumps({
        "model": settings.EMBEDDING_MODEL,
        "input": texts,
    }).encode("utf-8")
    req = urllib.request.Request(
        f"{settings.OLLAMA_BASE_URL}/api/embed",
        data=payload,
        headers={"Content-Type": "application/json"},
        method="POST",
    )
    timeout = max(int(getattr(settings, "OLLAMA_CHAT_TIMEOUT", 300)), 300)
    with urllib.request.urlopen(req, timeout=timeout) as resp:
        data = json.loads(resp.read().decode("utf-8"))

    vectors = data.get("embeddings") or []
    if len(vectors) != len(texts):
        raise RuntimeError(f"embedding 数量不匹配：期望 {len(texts)}，实际 {len(vectors)}")
    return vectors


def seed_collection(
    label: str,
    collection_name: str,
    key_field: str,
    records: List[Dict[str, Any]],
    batch_size: int = BATCH_SIZE,
) -> Dict[str, int]:
    """通用灌库流程：按批 embedding → 删旧 → 插新"""
    stats = {"total": len(records), "ok": 0, "failed": 0}
    if not records:
        print(f"[{label}] 无数据，跳过")
        return stats

    collection = MilvusService(collection_name)

    # 集合只需加载一次：过滤式删除与插入都要求集合处于 load 状态，
    # 放在循环外避免每批重复加载（实测可显著缩短总耗时）。
    try:
        run_async(collection.load())
    except Exception as e:
        print(f"[{label}] 集合加载失败（继续尝试）: {e}")

    for start in range(0, len(records), batch_size):
        batch = records[start:start + batch_size]
        texts = [r["text"] for r in batch]

        try:
            vectors = embed_texts(texts)
        except Exception as e:
            stats["failed"] += len(batch)
            print(f"[{label}] {start}-{start+len(batch)} embedding 失败: {e}")
            continue

        rows = [r["row"] for r in batch]

        # 幂等：先按主键删除该批旧向量，避免重复。
        # 注意：Milvus 的「过滤式删除」要求集合处于 load 状态，否则删除不生效
        # （实测不 load 时 delete 不报错但也没删掉，重跑会累积重复向量）。
        try:
            keys = [str(r["row"][key_field]) for r in batch]
            expr = f'{key_field} in [{", ".join(chr(34) + k + chr(34) for k in keys)}]'
            deleted = run_async(collection.delete(expr))
            if deleted:
                print(f"[{label}] 清理旧向量 {deleted} 条")
        except Exception as e:
            print(f"[{label}] {start} 清理旧向量失败: {e}")

        try:
            run_async(collection.insert(vectors, rows))
            stats["ok"] += len(batch)
        except Exception as e:
            stats["failed"] += len(batch)
            print(f"[{label}] {start}-{start+len(batch)} 插入失败: {e}")

        print(f"[{label}] 进度 {min(start + batch_size, len(records))}/{len(records)}（成功 {stats['ok']}）")

    return stats


def main() -> int:
    parser = argparse.ArgumentParser(description="为 Milvus 人才/岗位集合灌入向量")
    parser.add_argument("--only", choices=["talent", "job", "both"], default="both")
    parser.add_argument("--limit", type=int, default=0, help="每类最多处理条数（0=全部）")
    parser.add_argument("--batch", type=int, default=BATCH_SIZE)
    args = parser.parse_args()

    print(f"Milvus: {settings.MILVUS_HOST}:{settings.MILVUS_PORT}｜"
          f"embedding={settings.EMBEDDING_MODEL}｜base={settings.OLLAMA_BASE_URL}")
    t0 = time.time()
    db = next(get_mysql_session())
    summary: Dict[str, Dict[str, int]] = {}

    if args.only in ("talent", "both"):
        q = db.query(Talent)
        if args.limit:
            q = q.limit(args.limit)
        talents = q.all()
        print(f"\n读取人才 {len(talents)} 条，构建向量文本…")
        ts = int(time.time())
        records = [
            {
                "text": build_talent_text(t),
                "row": {
                    "talent_id": str(t.id),
                    "resume_text": build_talent_text(t),
                    "chunk_id": f"t{t.id}",
                    "file_id": "",
                    "file_name": "",
                    "business_scene": "talent_resume",
                    "created_at": ts,
                },
            }
            for t in talents
        ]
        summary["talent_resume"] = seed_collection(
            "talent_resume", settings.MILVUS_COLLECTION_TALENT, "talent_id",
            records, batch_size=args.batch
        )

    if args.only in ("job", "both"):
        q = db.query(JobPosition)
        if args.limit:
            q = q.limit(args.limit)
        positions = q.all()
        print(f"\n读取岗位 {len(positions)} 条，构建向量文本…")
        ts = int(time.time())
        records = [
            {
                "text": build_position_text(p),
                "row": {
                    "position_id": str(p.id),
                    "position_text": build_position_text(p),
                    "position_name": str(p.position_name or "")[:256],
                    "department": str(p.department_id or "")[:256],
                    "business_scene": "job_position",
                    "created_at": ts,
                },
            }
            for p in positions
        ]
        summary[settings.MILVUS_COLLECTION_JOB] = seed_collection(
            "job_position", settings.MILVUS_COLLECTION_JOB, "position_id",
            records, batch_size=args.batch
        )

    print("\n================ 汇总 ================")
    for name, s in summary.items():
        print(f"  {name:16s} 总 {s['total']:5d}｜成功 {s['ok']:5d}｜失败 {s['failed']:5d}")
    print(f"耗时 {round(time.time() - t0, 1)}s")
    return 0 if all(s["failed"] == 0 for s in summary.values()) else 1


if __name__ == "__main__":
    sys.exit(main())
