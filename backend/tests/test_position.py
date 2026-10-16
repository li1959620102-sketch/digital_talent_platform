"""
岗位管理服务单元测试
"""
import pytest
from datetime import datetime
from app.services.position_service import PositionService
from app.models.position import JobPosition, PositionStatus, PositionLevel


class TestPositionService:
    """岗位服务测试"""

    def test_create_position(self, test_db):
        """测试创建岗位"""
        service = PositionService(test_db)
        data = {
            "position_name": "高级Python工程师",
            "department_id": 1,
            "position_category": "技术",
            "position_level": PositionLevel.SENIOR,
            "position_type": "全职",
            "headcount": 2,
            "salary_min": 20000,
            "salary_max": 35000,
            "work_location": "北京",
            "education_requirement": "本科",
            "experience_requirement": 5,
            "skill_requirements": ["Python", "FastAPI", "MySQL"],
            "capability_requirements": ["系统设计", "团队协作"],
            "job_description": "负责后端系统开发",
            "job_responsibilities": "1. 系统设计 2. 代码评审",
            "tags": ["后端", "Python"]
        }
        position = service.create_position(data, user_id=1)

        assert position.id is not None
        assert position.position_code.startswith("POS")
        assert position.position_name == "高级Python工程师"
        assert position.status == PositionStatus.OPEN
        assert position.headcount == 2

    def test_get_position(self, test_db):
        """测试获取岗位详情"""
        service = PositionService(test_db)
        created = service.create_position(
            {"position_name": "测试岗位", "position_type": "全职"}, user_id=1
        )
        fetched = service.get_position(created.id)
        assert fetched is not None
        assert fetched.id == created.id
        assert fetched.position_name == "测试岗位"

    def test_get_position_by_code(self, test_db):
        """测试根据编号获取岗位"""
        service = PositionService(test_db)
        created = service.create_position(
            {"position_name": "编号测试岗位"}, user_id=1
        )
        fetched = service.get_position_by_code(created.position_code)
        assert fetched is not None
        assert fetched.position_code == created.position_code

    def test_update_position(self, test_db):
        """测试更新岗位信息"""
        service = PositionService(test_db)
        created = service.create_position(
            {"position_name": "待更新岗位", "headcount": 1}, user_id=1
        )
        updated = service.update_position(
            created.id, {"position_name": "已更新岗位", "headcount": 3}, user_id=1
        )
        assert updated is not None
        assert updated.position_name == "已更新岗位"
        assert updated.headcount == 3

    def test_update_nonexistent_position(self, test_db):
        """测试更新不存在的岗位"""
        service = PositionService(test_db)
        result = service.update_position(99999, {"position_name": "x"}, user_id=1)
        assert result is None

    def test_delete_position(self, test_db):
        """测试删除岗位"""
        service = PositionService(test_db)
        created = service.create_position(
            {"position_name": "待删除岗位"}, user_id=1
        )
        assert service.delete_position(created.id) is True
        assert service.get_position(created.id) is None

    def test_delete_nonexistent_position(self, test_db):
        """测试删除不存在的岗位"""
        service = PositionService(test_db)
        assert service.delete_position(99999) is False

    def test_get_positions_pagination(self, test_db):
        """测试岗位列表分页"""
        service = PositionService(test_db)
        for i in range(5):
            service.create_position(
                {"position_name": f"分页岗位{i}", "position_type": "全职"}, user_id=1
            )

        result = service.get_positions(page=1, page_size=3)
        assert result["total"] >= 5
        assert len(result["items"]) <= 3
        assert result["page"] == 1
        assert result["page_size"] == 3

    def test_get_positions_filter_by_status(self, test_db):
        """测试按状态过滤岗位"""
        service = PositionService(test_db)
        service.create_position(
            {"position_name": "开放岗位", "status": PositionStatus.OPEN}, user_id=1
        )
        result = service.get_positions(status=PositionStatus.OPEN)
        assert result["total"] >= 1
        assert all(p.status == PositionStatus.OPEN for p in result["items"])

    def test_get_positions_keyword(self, test_db):
        """测试关键词搜索"""
        service = PositionService(test_db)
        service.create_position(
            {"position_name": "数据分析师", "position_type": "全职"}, user_id=1
        )
        result = service.get_positions(keyword="数据分析")
        assert result["total"] >= 1

    def test_generate_position_code_unique(self, test_db):
        """测试岗位编号唯一性"""
        service = PositionService(test_db)
        p1 = service.create_position({"position_name": "A"}, user_id=1)
        p2 = service.create_position({"position_name": "B"}, user_id=1)
        assert p1.position_code != p2.position_code

    def test_search_positions_graceful(self, test_db):
        """测试向量搜索在无Ollama/Milvus时优雅降级返回空列表"""
        service = PositionService(test_db)
        created = service.create_position(
            {"position_name": "搜索测试岗位", "position_type": "全职"}, user_id=1
        )
        # 无向量服务时应返回列表（可能为空或补充后的结果）
        results = service.search_positions("后端开发")
        assert isinstance(results, list)
        # 即使向量失败，也应至少有降级逻辑返回的列表

    def test_get_positions_by_department(self, test_db):
        """测试按部门过滤岗位"""
        service = PositionService(test_db)
        service.create_position(
            {"position_name": "部门岗位", "department_id": 5, "position_type": "全职"}, user_id=1
        )
        result = service.get_positions(department_id=5)
        assert result["total"] >= 1
        assert all(p.department_id == 5 for p in result["items"])


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
