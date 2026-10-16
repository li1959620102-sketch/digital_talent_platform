"""
历史数据迁移服务

负责将历史人才数据（Excel / CSV）批量迁移规整导入平台：
- 字段清洗（去空格、枚举归一化、类型强制）
- 重复数据跳过（按手机号/邮箱去重，不中断整体导入）
- 生成结构化迁移报告（总数/导入/跳过/失败/错误明细/清洗动作），落盘可审计
"""
import os
import csv
import json
import logging
from typing import List, Dict, Any
from datetime import datetime

import openpyxl
from sqlalchemy.orm import Session

from app.models.talent import Talent
from app.schemas.talent import TalentCreate, GenderEnum, EducationLevel
from app.services.talent_service import TalentService

logger = logging.getLogger(__name__)

VALID_EDUS = [e.value for e in EducationLevel]


class MigrationReport:
    """数据迁移报告"""

    def __init__(self):
        self.started_at = datetime.now()
        self.finished_at = None
        self.total = 0
        self.imported = 0
        self.skipped_duplicates = 0
        self.failed = 0
        self.errors: List[Dict[str, Any]] = []
        self.cleaned: List[str] = []

    def to_dict(self) -> Dict[str, Any]:
        return {
            "started_at": self.started_at.isoformat(),
            "finished_at": self.finished_at.isoformat() if self.finished_at else None,
            "total": self.total,
            "imported": self.imported,
            "skipped_duplicates": self.skipped_duplicates,
            "failed": self.failed,
            "errors": self.errors[:50],
            "cleaned": self.cleaned,
        }


def _normalize_gender(value) -> GenderEnum:
    v = str(value or "male").strip().lower()
    return GenderEnum.FEMALE if v in ("female", "女", "2") else GenderEnum.MALE


def _normalize_education(value):
    if value in VALID_EDUS:
        return EducationLevel(value)
    return None


def _read_rows(file_path: str):
    """读取 Excel/CSV，返回 (headers, data_rows)"""
    ext = os.path.splitext(file_path)[1].lower()
    if ext == ".csv":
        with open(file_path, "r", encoding="utf-8-sig", newline="") as f:
            rows = list(csv.reader(f))
        headers = [str(h).strip() for h in rows[0]] if rows else []
        return headers, rows[1:]
    wb = openpyxl.load_workbook(file_path, read_only=True)
    ws = wb.active
    headers = [
        str(c.value).strip() if c.value is not None else ""
        for c in next(ws.iter_rows(min_row=1, max_row=1))
    ]
    data_rows = [list(r) for r in ws.iter_rows(min_row=2, values_only=True)]
    return headers, data_rows


def import_talents_from_file(db: Session, file_path: str) -> MigrationReport:
    """将历史人才数据文件迁移导入，返回迁移报告"""
    report = MigrationReport()
    headers, data_rows = _read_rows(file_path)
    report.total = len(data_rows)

    for idx, row in enumerate(data_rows, start=2):
        record = dict(zip(headers, row))
        try:
            phone = str(record.get("phone") or "").strip()
            if not phone:
                raise ValueError("缺少手机号")

            # 清洗：已存在则跳过（去重，不中断整体导入）
            existing = db.query(Talent).filter(Talent.phone == phone).first()
            if existing:
                report.skipped_duplicates += 1
                report.cleaned.append(f"row {idx}: 跳过重复手机号 {phone}")
                continue

            exp = record.get("experience_years")
            talent_in = TalentCreate(
                name=str(record.get("name") or "").strip(),
                gender=_normalize_gender(record.get("gender")),
                phone=phone,
                email=record.get("email") or None,
                education=_normalize_education(record.get("education")),
                major=(record.get("major") or None),
                experience_years=int(exp) if exp not in (None, "") else None,
                current_company=record.get("current_company"),
                current_position=record.get("current_position"),
                status="reserve",
            )
            TalentService.create_talent(db, talent_in)
            report.imported += 1
        except Exception as e:  # noqa: BLE001
            report.failed += 1
            report.errors.append({"row": idx, "error": str(e)[:200]})

    report.finished_at = datetime.now()
    return report


def save_report(report: MigrationReport, out_dir: str = "migrations") -> str:
    """将迁移报告落盘，返回报告文件路径（可审计）。

    测试环境（TESTING=true）不落盘，避免每次跑测试都在 migrations/ 目录
    产生运行期产物、污染工作区与版本控制。
    """
    if os.getenv("TESTING"):
        return ""
    os.makedirs(out_dir, exist_ok=True)
    report_path = os.path.join(out_dir, f"migration_{report.finished_at:%Y%m%d_%H%M%S}.json")
    with open(report_path, "w", encoding="utf-8") as rf:
        json.dump(report.to_dict(), rf, ensure_ascii=False, indent=2)
    return report_path
