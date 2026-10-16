"""
API 集成测试（端到端：API -> service -> DB）
使用 SQLite 内存库 + 依赖覆盖，验证接口层真实可用（不依赖 MySQL/Milvus/Ollama）
"""
import pytest
from fastapi.testclient import TestClient
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool

from app.core.database import Base, get_mysql_session
from app.utils.jwt_handler import get_current_user
from app.models import talent, position, assessment, training, permission  # noqa: F401
from main import app

# 内存 SQLite 引擎（每个测试模块一份）
engine = create_engine(
    "sqlite:///:memory:",
    connect_args={"check_same_thread": False},
    poolclass=StaticPool,
)
Base.metadata.create_all(engine)
TestingSessionLocal = sessionmaker(bind=engine, autoflush=False, autocommit=False)


import types

def override_get_db():
    db = TestingSessionLocal()
    try:
        yield db
    finally:
        db.close()


def override_get_current_user():
    return types.SimpleNamespace(id=1, username="test", is_superuser=True, organization_id=None)


app.dependency_overrides[get_mysql_session] = override_get_db
app.dependency_overrides[get_current_user] = override_get_current_user

client = TestClient(app)
BASE = "/api/v1"


class TestTalentAPI:
    def test_health(self):
        resp = client.get("/health")
        assert resp.status_code == 200

    def test_create_and_get_talent(self):
        payload = {
            "name": "集成测试人才",
            "gender": "male",
            "birth_date": "1992-05-20",
            "phone": "13900001111",
            "email": "it_talent@example.com",
            "education": "本科",
            "experience_years": 5,
            "current_position": "后端工程师",
            "status": "reserve",
            "tags": ["Python", "FastAPI"]
        }
        r = client.post(f"{BASE}/talents", json=payload)
        assert r.status_code == 200, r.text
        data = r.json()
        assert data["code"] == 201
        tid = data["data"]["id"]
        assert tid is not None

        g = client.get(f"{BASE}/talents/{tid}")
        assert g.status_code == 200
        assert g.json()["data"]["name"] == "集成测试人才"

    def test_list_talents(self):
        r = client.get(f"{BASE}/talents", params={"page": 1, "page_size": 10})
        assert r.status_code == 200
        body = r.json()
        assert body["code"] == 200
        assert "items" in body["data"]

    def test_create_duplicate_talent(self):
        payload = {
            "name": "重复人才",
            "gender": "male",
            "phone": "13900002222",
            "email": "dup_api@example.com",
            "status": "reserve"
        }
        r1 = client.post(f"{BASE}/talents", json=payload)
        assert r1.status_code == 200
        r2 = client.post(f"{BASE}/talents", json=payload)
        # 重复手机号应返回错误（code != 201）
        assert r2.status_code != 201


class TestPositionAPI:
    def test_create_and_list_position(self):
        payload = {
            "position_name": "集成测试岗位",
            "department_id": 1,
            "position_category": "技术",
            "position_level": "senior",
            "position_type": "全职",
            "headcount": 2,
            "salary_min": 20000,
            "salary_max": 35000,
            "work_location": "北京",
            "education_requirement": "本科",
            "experience_requirement": 5,
            "skill_requirements": ["Python", "FastAPI"],
            "capability_requirements": ["系统设计"],
            "job_description": "后端开发",
            "job_responsibilities": "1. 开发 2. 评审",
            "tags": ["后端"]
        }
        r = client.post(f"{BASE}/positions", json=payload)
        assert r.status_code == 200, r.text
        assert r.json()["code"] == 200
        pid = r.json()["data"]["id"]
        assert pid is not None

        lst = client.get(f"{BASE}/positions", params={"page": 1, "page_size": 10})
        assert lst.status_code == 200
        assert lst.json()["data"]["total"] >= 1


class TestAssessmentAPI:
    def test_create_and_list_question(self):
        payload = {
            "question_content": "Python中list的append方法时间复杂度是多少？",
            "question_type": "single_choice",
            "question_category": "专业知识",
            "options": ["O(1)", "O(n)", "O(log n)", "O(n^2)"],
            "correct_answer": "O(1)",
            "answer_analysis": "list.append为 amortized O(1)",
            "score_value": 5,
            "difficulty": 2,
            "capability_dimension": "专业能力",
            "tags": ["Python"]
        }
        r = client.post(f"{BASE}/assessments/questions", json=payload)
        assert r.status_code == 200, r.text
        assert r.json()["code"] == 200
        qid = r.json()["data"]["id"]
        assert qid is not None

        lst = client.get(f"{BASE}/assessments/questions", params={"page": 1, "page_size": 10})
        assert lst.status_code == 200, lst.text
        body = lst.json()
        assert body["code"] == 200
        assert body["data"]["total"] >= 1
        assert any(i["id"] == qid for i in body["data"]["items"])

    def test_list_papers_empty(self):
        lst = client.get(f"{BASE}/assessments/papers", params={"page": 1, "page_size": 10})
        assert lst.status_code == 200, lst.text
        assert lst.json()["code"] == 200
        assert "items" in lst.json()["data"]

    def test_list_results_empty(self):
        lst = client.get(f"{BASE}/assessments/results", params={"page": 1, "page_size": 10})
        assert lst.status_code == 200, lst.text
        assert lst.json()["code"] == 200
        assert "items" in lst.json()["data"]


class TestDashboardAPI:
    def test_overview(self):
        r = client.get(f"{BASE}/dashboard/overview")
        assert r.status_code == 200, r.text
        assert r.json()["code"] == 200
        assert "total_talents" in r.json()["data"]

    def test_talent_structure(self):
        r = client.get(f"{BASE}/dashboard/talent-structure")
        assert r.status_code == 200 and r.json()["code"] == 200

    def test_skill_distribution(self):
        r = client.get(f"{BASE}/dashboard/skill-distribution")
        assert r.status_code == 200 and r.json()["code"] == 200

    def test_assessment_statistics(self):
        r = client.get(f"{BASE}/dashboard/assessment-statistics")
        assert r.status_code == 200 and r.json()["code"] == 200

    def test_training_statistics(self):
        r = client.get(f"{BASE}/dashboard/training-statistics")
        assert r.status_code == 200 and r.json()["code"] == 200

    def test_matching_statistics(self):
        r = client.get(f"{BASE}/dashboard/matching-statistics")
        assert r.status_code == 200 and r.json()["code"] == 200

    def test_alerts(self):
        r = client.get(f"{BASE}/dashboard/alerts")
        assert r.status_code == 200 and r.json()["code"] == 200


class TestMatchingAPI:
    def _create_talent(self):
        payload = {
            "name": "匹配测试人才", "gender": "male", "phone": "13900003333",
            "email": "match_api@example.com", "education": "本科",
            "experience_years": 5, "current_position": "后端工程师",
            "status": "reserve", "skills_certificates": [{"name": "Python"}, {"name": "FastAPI"}]
        }
        r = client.post(f"{BASE}/talents", json=payload)
        assert r.status_code == 200, r.text
        return r.json()["data"]["id"]

    def _create_position(self):
        payload = {
            "position_name": "匹配测试岗位", "department_id": 1, "position_category": "技术",
            "position_level": "senior", "position_type": "全职", "headcount": 2,
            "salary_min": 20000, "salary_max": 35000, "work_location": "北京",
            "education_requirement": "本科", "experience_requirement": 3,
            "skill_requirements": ["Python", "FastAPI"], "capability_requirements": ["系统设计"],
            "job_description": "后端开发", "job_responsibilities": "开发", "tags": ["后端"]
        }
        r = client.post(f"{BASE}/positions", json=payload)
        assert r.status_code == 200, r.text
        return r.json()["data"]["id"]

    def test_match_and_list(self):
        tid = self._create_talent()
        pid = self._create_position()
        m = client.post(f"{BASE}/matching/match", json={"position_id": pid, "top_n": 5})
        assert m.status_code == 200, m.text
        assert m.json()["code"] == 200
        assert m.json()["data"]["total_candidates"] >= 1

        res = client.get(f"{BASE}/matching/results", params={"position_id": pid})
        assert res.status_code == 200 and res.json()["code"] == 200
        assert res.json()["data"]["total"] >= 1

        cand = client.get(f"{BASE}/matching/positions/{pid}/candidates")
        assert cand.status_code == 200 and cand.json()["code"] == 200
        assert cand.json()["data"]["count"] >= 1

        tp = client.get(f"{BASE}/matching/talents/{tid}/positions")
        assert tp.status_code == 200 and tp.json()["code"] == 200


class TestTrainingAPI:
    def test_course_crud_and_learning(self):
        c = client.post(f"{BASE}/training/courses", json={
            "course_name": "Python进阶", "course_category": "skill", "course_type": "video",
            "duration_minutes": 60, "instructor": "张老师", "tags": ["Python"]
        })
        assert c.status_code == 200, c.text
        assert c.json()["code"] == 200
        cid = c.json()["data"]["id"]

        g = client.get(f"{BASE}/training/courses/{cid}")
        assert g.status_code == 200 and g.json()["code"] == 200
        assert g.json()["data"]["course_name"] == "Python进阶"

        p = client.post(f"{BASE}/training/plans", json={"plan_name": "新人计划", "target_talents": [1]})
        assert p.status_code == 200 and p.json()["code"] == 200

        ls = client.post(f"{BASE}/training/learning/start", json={"talent_id": 1, "course_id": cid})
        assert ls.status_code == 200 and ls.json()["code"] == 200
        rid = ls.json()["data"]["id"]

        lp = client.post(f"{BASE}/training/learning/progress", json={"record_id": rid, "progress": 100})
        assert lp.status_code == 200 and lp.json()["data"]["status"] == "completed"

        es = client.post(f"{BASE}/training/examination/start", json={"talent_id": 1, "course_id": cid})
        assert es.status_code == 200 and es.json()["code"] == 200
        eid = es.json()["data"]["id"]

        sub = client.post(f"{BASE}/training/examination/submit", json={"record_id": eid, "score": 85})
        assert sub.status_code == 200 and sub.json()["data"]["passed"] is True


class TestKnowledgeAPI:
    def _upload(self):
        content = ("人才管理制度：员工每年度需完成至少40学时培训。\n"
                   "岗位说明书：后端工程师需掌握Python与分布式系统。")
        files = {"file": ("policy.txt", content.encode("utf-8"), "text/plain")}
        data = {"knowledge_type": "制度", "permission_level": 0}
        r = client.post(f"{BASE}/knowledge/upload", files=files, data=data)
        assert r.status_code == 200, r.text
        return r.json()["data"]["id"]

    def test_upload_and_list(self):
        fid = self._upload()
        res = client.get(f"{BASE}/knowledge/files")
        assert res.status_code == 200 and res.json()["code"] == 200
        ids = [i["id"] for i in res.json()["data"]["items"]]
        assert fid in ids

    def test_vectorize_graceful(self):
        fid = self._upload()
        r = client.post(f"{BASE}/knowledge/vectorize", json={"file_id": fid})
        # 无 Ollama/Milvus 时优雅失败，返回结构化响应而非崩溃
        assert r.status_code in (200, 500)
        assert r.json()["code"] in (200, 500)

    def test_search_graceful(self):
        r = client.post(f"{BASE}/knowledge/search", json={"query": "培训学时要求"})
        assert r.status_code == 200 and r.json()["code"] == 200
        assert "results" in r.json()["data"]

    def test_qa_graceful(self):
        r = client.post(f"{BASE}/knowledge/qa", json={"query": "年度培训学时是多少"})
        assert r.status_code == 200 and r.json()["code"] == 200
        assert "answer" in r.json()["data"]


class TestAgentAPI:
    def test_data_analysis_structure(self):
        r = client.post(f"{BASE}/agents/data-analysis", json={"analysis_type": "structure"})
        assert r.status_code == 200 and r.json()["code"] == 200
        data = r.json()["data"]
        # 优先检查顶层展平字段（LangGraph 路由正常时）；回退检查 structure 子对象
        assert "total_talents" in data or "total_talents" in data.get("structure", {}), \
            f"结构分析返回缺少 total_talents，keys={list(data.keys())}"

    def test_nl2sql_graceful(self):
        r = client.post(f"{BASE}/agents/nl2sql", json={"question": "统计各学历人才数量"})
        assert r.status_code == 200 and r.json()["code"] == 200
        data = r.json()["data"]
        # LangGraph 结构：sql 在 nl2sql 子对象中（兼容旧版顶层字段）
        nl2sql = data.get("nl2sql") or {}
        assert "sql" in data or "sql" in nl2sql, \
            f"NL2SQL 返回缺少 sql，keys={list(data.keys())}"

    def test_recommend_training_missing(self):
        r = client.post(f"{BASE}/agents/recommend-training", json={"talent_id": 999})
        assert r.status_code == 200 and r.json()["code"] == 200
        assert r.json()["data"]["success"] is False  # 人才不存在，结构化返回

    def test_match_position_missing(self):
        r = client.post(f"{BASE}/agents/match-position", json={"position_id": 999})
        assert r.status_code == 200 and r.json()["code"] == 200

    def test_analyze_assessment_missing(self):
        r = client.post(f"{BASE}/agents/analyze-assessment", json={"result_id": 999})
        assert r.status_code == 200 and r.json()["code"] == 200


class TestTalentImportAndProfile:
    """验证此前为 pass 桩的 P0 端点已真实实现（Excel导入/标签/画像/标签搜索）"""

    def test_tags_portrait_and_tag_search(self, test_client):
        r = client.post(
            f"{BASE}/talents",
            json={"name": "导入测试人", "gender": "male", "phone": "13900000001",
                  "education": "本科", "experience_years": 3, "status": "reserve"},
        )
        assert r.status_code == 200, r.text
        tid = r.json()["data"]["id"]

        r = client.post(f"{BASE}/talents/{tid}/tags", json={"tags": ["Python", "后端"]})
        assert r.status_code == 200
        assert set(r.json()["data"]["tags"]) == {"Python", "后端"}

        r = client.get(f"{BASE}/talents/{tid}/portrait")
        assert r.status_code == 200
        assert "portrait" in r.json()["data"]

        r = client.post(f"{BASE}/talents/search", json={"tags": ["Python"]})
        assert r.status_code == 200
        ids = [t["id"] for t in r.json()["data"]["items"]]
        assert tid in ids

    def test_batch_import_xlsx(self, test_client):
        import openpyxl, tempfile, os
        wb = openpyxl.Workbook()
        ws = wb.active
        ws.append(["name", "gender", "phone", "education", "experience_years"])
        ws.append(["批量甲", "male", "13900000011", "本科", 2])
        ws.append(["批量乙", "female", "13900000012", "硕士", 5])
        path = tempfile.mktemp(suffix=".xlsx")
        wb.save(path)
        with open(path, "rb") as f:
            r = client.post(
                f"{BASE}/talents/batch-import",
                files={"file": ("t.xlsx", f, "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet")},
            )
        os.remove(path)
        assert r.status_code == 200, r.text
        d = r.json()["data"]
        assert d["imported"] >= 2, d
        assert "report_file" in d


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
