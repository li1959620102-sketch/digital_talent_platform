"""
Golden Test Set - 岗位匹配精度回归测试
加载 tests/golden_dataset.json 标注数据，对真实 compute_match_score 评分，
断言整体准确率 >= 85%（验收底线）/ 工程目标 >= 90%。
"""
import json
import os
import pytest

from app.models.talent import Talent, EducationLevel
from app.models.position import JobPosition
from app.api.v1.matching import compute_match_score

HERE = os.path.dirname(os.path.abspath(__file__))


def _build_talent(d):
    t = Talent()
    t.education = EducationLevel(d["education"])
    t.experience_years = d.get("experience_years", 0)
    t.skills_certificates = [{"name": s} for s in d.get("skills", [])]
    return t


def _build_position(d):
    p = JobPosition()
    p.education_requirement = d.get("education_requirement")
    p.experience_requirement = d.get("experience_requirement", 0)
    p.skill_requirements = d.get("skill_requirements", [])
    return p


def _load_cases():
    with open(os.path.join(HERE, "golden_dataset.json"), encoding="utf-8") as f:
        data = json.load(f)
    return data["threshold"], data["cases"]


def test_golden_match_accuracy():
    threshold, cases = _load_cases()
    tp = fp = tn = fn = 0
    for c in cases:
        res = compute_match_score(_build_talent(c["talent"]), _build_position(c["position"]))
        pred = 1 if res["score"] >= threshold else 0
        label = c["expected_relevant"]
        if pred == 1 and label == 1:
            tp += 1
        elif pred == 1 and label == 0:
            fp += 1
        elif pred == 0 and label == 0:
            tn += 1
        else:
            fn += 1
    total = len(cases)
    accuracy = (tp + tn) / total
    # 验收底线 >= 85%
    assert accuracy >= 0.85, f"岗位匹配准确率 {accuracy*100:.1f}% 低于验收底线85%"
    # 工程目标 >= 90%
    assert accuracy >= 0.90, f"岗位匹配准确率 {accuracy*100:.1f}% 低于工程目标90%"
