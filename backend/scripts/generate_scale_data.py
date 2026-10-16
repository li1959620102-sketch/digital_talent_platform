"""生成可重复的中型生产规模累计档案数据。

默认只生成人才档案；这是累计档案规模压测，不代表每日简历导入量。其它业务表可以在真实业务导入或专门压测脚本中生成。
脚本采用分批 bulk_insert_mappings，避免一次性把上万条 ORM 对象保留在内存。

示例：
    python -m scripts.generate_scale_data --talents 10000
    python -m scripts.generate_scale_data --talents 50000 --batch-size 1000

该脚本不会删除已有数据，使用稳定的 talent_code 做幂等去重。
"""
from __future__ import annotations

import argparse
import random
from datetime import date, timedelta

from sqlalchemy import select

from app.core.database import get_mysql_session_factory
from app.models.talent import EducationLevel, GenderEnum, Talent, TalentStatus


NAMES = ("张伟", "李娜", "王强", "刘洋", "陈静", "赵磊", "杨帆", "黄敏", "周凯", "吴婷")
EDUCATIONS = tuple(item.value for item in EducationLevel)
GENDERS = tuple(item.value for item in GenderEnum)
STATUSES = tuple(item.value for item in TalentStatus)


def build_row(index: int, organization_id: int | None) -> dict:
    random.seed(index)
    return {
        "talent_code": f"T-SCALE-{index:08d}",
        "name": f"{NAMES[index % len(NAMES)]}{index:05d}",
        "gender": GENDERS[index % len(GENDERS)],
        "birth_date": date(1975, 1, 1) + timedelta(days=random.randrange(15000)),
        "phone": f"1{30 + index % 70:02d}{index:08d}",
        "email": f"talent{index}@scale.example.com",
        "education": EDUCATIONS[index % len(EDUCATIONS)],
        "major": ("计算机科学", "人力资源管理", "工商管理", "数据科学")[index % 4],
        "experience_years": index % 16,
        "current_company": f"示例企业{index % 50 + 1:02d}",
        "current_position": ("软件工程师", "产品经理", "数据分析师", "HRBP")[index % 4],
        "status": STATUSES[index % len(STATUSES)],
        "department_id": organization_id,
        "tags": [{"name": ("Python", "项目管理", "数据分析", "招聘管理")[index % 4]}],
        "skills_certificates": [{"name": ("Python", "项目管理", "数据分析", "招聘管理")[index % 4]}],
        "is_parsed": True,
    }


def run(target: int, batch_size: int) -> int:
    factory = get_mysql_session_factory()
    if factory is None:
        raise RuntimeError("MySQL 未初始化，请先配置运行环境")
    db = factory()
    try:
        organization_id = db.execute(select(Talent.department_id).where(Talent.department_id.is_not(None)).limit(1)).scalar()
        existing = {code for (code,) in db.query(Talent.talent_code).filter(Talent.talent_code.like("T-SCALE-%")).all()}
        created = 0
        pending: list[dict] = []
        for index in range(1, target + 1):
            code = f"T-SCALE-{index:08d}"
            if code in existing:
                continue
            pending.append(build_row(index, organization_id))
            if len(pending) >= batch_size:
                db.bulk_insert_mappings(Talent, pending)
                db.commit()
                created += len(pending)
                pending.clear()
        if pending:
            db.bulk_insert_mappings(Talent, pending)
            db.commit()
            created += len(pending)
        print(f"规模数据生成完成：目标 {target} 条，新增 {created} 条，已有 {target - created} 条")
        return created
    finally:
        db.close()


def main() -> None:
    parser = argparse.ArgumentParser(description="生成上万级累计人才档案压测数据")
    parser.add_argument("--talents", type=int, default=10000)
    parser.add_argument("--batch-size", type=int, default=1000)
    args = parser.parse_args()
    if not 1 <= args.talents <= 1_000_000:
        parser.error("--talents 必须在 1 到 1000000 之间")
    if not 1 <= args.batch_size <= 10_000:
        parser.error("--batch-size 必须在 1 到 10000 之间")
    run(args.talents, args.batch_size)


if __name__ == "__main__":
    main()
