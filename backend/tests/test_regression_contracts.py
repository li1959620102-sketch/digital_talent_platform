"""后端安全与资源隔离回归契约测试。

这些用例只使用本地函数和 SQLite 测试会话，不连接线上服务。
"""
import os
from types import SimpleNamespace

import pytest
from fastapi import HTTPException

from app.api.v1.assessment import get_paper_questions, grade_real_answer
from app.api.v1.me import recommended_paper, submit_my_assessment
from app.models.assessment import Question, QuestionType, TestPaper
from app.models.talent import GenderEnum, Talent, TalentStatus
from app.utils.minio_client import BUCKET_IMPORTS, BUCKET_KNOWLEDGE, BUCKET_RESUMES
from app.utils.resume_parser import detect_resume_extension


@pytest.mark.parametrize(
    ("content", "filename", "expected"),
    [
        (b"%PDF-1.7\nresume", "resume.bin", ".pdf"),
        (b"PK\x03\x04" + b"docx", "resume.bin", ".docx"),
        (b"\xd0\xcf\x11\xe0" + b"doc", "resume.bin", ".doc"),
        (b"\x89PNG\r\n\x1a\n" + b"png", "resume.bin", ".png"),
        ("姓名：测试人员\nPython".encode("utf-8"), "resume.bin", ".txt"),
        (b"not a known binary", "resume.exe", None),
    ],
)
def test_detect_resume_extension_by_signature_and_rejects_unknown_suffix(
    content, filename, expected
):
    assert detect_resume_extension(content, filename) == expected


def test_detect_resume_extension_uses_supported_filename_fallback_only():
    assert detect_resume_extension(b"", "resume.PDF") == ".pdf"
    assert detect_resume_extension(b"", "resume.exe") is None


def test_test_resources_are_scoped_to_unique_run_id():
    run_id = os.environ.get("TEST_RUN_ID")
    assert run_id and len(run_id) == 12
    assert os.environ["MILVUS_COLLECTION_TALENT"] == f"talent_resume_test_{run_id}"
    assert os.environ["MILVUS_COLLECTION_JOB"] == f"job_position_test_{run_id}"
    assert os.environ["MILVUS_COLLECTION_KNOWLEDGE"] == f"knowledge_base_test_{run_id}"
    assert all(bucket.endswith(f"-test-{run_id}") for bucket in (
        BUCKET_RESUMES, BUCKET_KNOWLEDGE, BUCKET_IMPORTS
    ))
    assert all("_" not in bucket for bucket in (
        BUCKET_RESUMES, BUCKET_KNOWLEDGE, BUCKET_IMPORTS
    ))


def _manager():
    return SimpleNamespace(id=1, is_superuser=True)


def _paper(db, *, status="published", questions=None):
    paper = TestPaper(
        paper_code=f"P-{status}",
        paper_name=f"{status} paper",
        paper_type="综合测评",
        questions=questions or [],
        total_score=5,
        duration_minutes=30,
        status=status,
    )
    db.add(paper)
    db.commit()
    db.refresh(paper)
    return paper


def _question(db):
    question = Question(
        question_code="Q-REGRESSION",
        question_content="1+1等于？",
        question_type=QuestionType.SINGLE_CHOICE,
        question_category="综合",
        options=["A. 1", "B. 2"],
        correct_answer="B",
        answer_analysis="基础算术",
        score_value=5,
        difficulty=1,
        status="active",
    )
    db.add(question)
    db.commit()
    db.refresh(question)
    return question


@pytest.mark.parametrize("payload", [{}, {"talent_id": "abc"}, {"talent_id": None}])
@pytest.mark.asyncio
async def test_manager_grade_rejects_missing_or_invalid_talent_id(test_db, payload):
    paper = _paper(test_db)
    with pytest.raises(HTTPException) as exc_info:
        await grade_real_answer(paper.id, payload, test_db, _manager())
    assert 400 <= exc_info.value.status_code < 500


@pytest.mark.asyncio
async def test_manager_grade_rejects_nonexistent_talent_id(test_db):
    question = _question(test_db)
    paper = _paper(test_db, questions=[{"question_id": question.id, "score": 5}])
    with pytest.raises(HTTPException) as exc_info:
        await grade_real_answer(
            paper.id,
            {"talent_id": 999999, "answers": [{"question_id": question.id, "answer": "B"}]},
            test_db,
            _manager(),
        )
    assert exc_info.value.status_code == 404


@pytest.mark.asyncio
async def test_manager_question_view_does_not_leak_answers_by_default(test_db):
    question = _question(test_db)
    paper = _paper(test_db, questions=[{"question_id": question.id, "score": 5}])
    response = await get_paper_questions(paper.id, False, test_db, _manager())
    item = response.data["items"][0]
    assert "correct_answer" not in item
    assert "answer_analysis" not in item


@pytest.mark.asyncio
async def test_employee_recommended_paper_only_returns_published(test_db):
    _paper(test_db, status="draft")
    published = _paper(test_db, status="published")
    user = SimpleNamespace(id=7, username="employee", real_name="员工", phone="13800000000")
    response = await recommended_paper(test_db, user)
    assert response.data["paper"]["id"] == published.id


@pytest.mark.asyncio
async def test_employee_submission_rejects_draft_paper(test_db):
    draft = _paper(test_db, status="draft")
    user = SimpleNamespace(id=7, username="employee", real_name="员工", phone="13800000000")
    with pytest.raises(HTTPException) as exc_info:
        await submit_my_assessment(draft.id, {"answers": []}, test_db, user)
    assert 400 <= exc_info.value.status_code < 500


def test_test_talent_fixture_values_are_local_only(test_db):
    talent = Talent(
        talent_code="T-REGRESSION",
        name="本地测试人才",
        gender=GenderEnum.MALE,
        phone="13800000000",
        status=TalentStatus.RESERVE,
    )
    test_db.add(talent)
    test_db.commit()
    assert talent.id is not None
    assert test_db.query(Talent).count() == 1
