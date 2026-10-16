"""
人才管理服务单元测试
"""
import pytest
from datetime import date

from app.services.talent_service import TalentService
from app.schemas.talent import (
    TalentCreate, TalentUpdate, TalentSearchRequest, GenderEnum, EducationLevel, TalentStatus
)
from app.core.exceptions import DuplicateKeyException, NotFoundException

_counter = {"n": 0}


def _make_talent_data(**overrides):
    _counter["n"] += 1
    n = _counter["n"]
    data = {
        "name": "张三",
        "gender": GenderEnum.MALE,
        "birth_date": date(1990, 1, 1),
        "education": EducationLevel.BACHELOR,
        "phone": f"138{n:08d}",
        "email": f"user{n}@example.com",
        "status": TalentStatus.RESERVE,
        "tags": ["后端", "Python"]
    }
    data.update(overrides)
    return TalentCreate(**data)


class TestTalentService:
    """人才服务测试"""

    def test_create_talent(self, test_db):
        """测试创建人才档案"""
        talent_data = _make_talent_data()
        result = TalentService.create_talent(test_db, talent_data)

        assert result.id is not None
        assert result.name == "张三"
        assert result.talent_code.startswith("T")
        assert result.gender == GenderEnum.MALE
        assert result.status == TalentStatus.RESERVE

    def test_create_talent_auto_number(self, test_db):
        """测试自动生成人才编号唯一性"""
        t1 = TalentService.create_talent(test_db, _make_talent_data(phone="13800000001"))
        t2 = TalentService.create_talent(test_db, _make_talent_data(phone="13800000002"))
        assert t1.talent_code != t2.talent_code
        assert t1.talent_code.startswith("T")
        assert t2.talent_code.startswith("T")

    def test_create_talent_duplicate_phone(self, test_db):
        """测试手机号查重"""
        TalentService.create_talent(test_db, _make_talent_data(phone="13900000001"))
        with pytest.raises(DuplicateKeyException):
            TalentService.create_talent(test_db, _make_talent_data(phone="13900000001"))

    def test_get_talent_by_id(self, test_db):
        """测试根据ID获取人才"""
        created = TalentService.create_talent(test_db, _make_talent_data())
        fetched = TalentService.get_talent_by_id(test_db, created.id)
        assert fetched.id == created.id
        assert fetched.name == "张三"

    def test_get_talent_by_id_not_found(self, test_db):
        """测试获取不存在的人才抛出异常"""
        with pytest.raises(NotFoundException):
            TalentService.get_talent_by_id(test_db, 999999)

    def test_get_talent_by_code(self, test_db):
        """测试根据编号获取人才"""
        created = TalentService.create_talent(test_db, _make_talent_data())
        fetched = TalentService.get_talent_by_code(test_db, created.talent_code)
        assert fetched.talent_code == created.talent_code

    def test_update_talent(self, test_db):
        """测试更新人才档案"""
        created = TalentService.create_talent(test_db, _make_talent_data())
        update_data = TalentUpdate(name="李四", tags=["前端", "React"])
        updated = TalentService.update_talent(test_db, created.id, update_data)
        assert updated.name == "李四"
        assert updated.tags == ["前端", "React"]

    def test_delete_talent(self, test_db):
        """测试删除人才档案"""
        created = TalentService.create_talent(test_db, _make_talent_data())
        assert TalentService.delete_talent(test_db, created.id) is True
        with pytest.raises(NotFoundException):
            TalentService.get_talent_by_id(test_db, created.id)

    def test_list_talents_pagination(self, test_db):
        """测试人才列表分页"""
        for i in range(15):
            TalentService.create_talent(test_db, _make_talent_data(
                name=f"人才{i}", phone=f"137000000{i:02d}"
            ))
        items, total = TalentService.list_talents(test_db, page=1, page_size=10)
        assert total >= 15
        assert len(items) == 10

    def test_search_talents(self, test_db):
        """测试人才搜索"""
        TalentService.create_talent(test_db, _make_talent_data(
            name="王五", phone="13611112222"
        ))
        search = TalentSearchRequest(query="王五")
        items, total = TalentService.search_talents(test_db, search)
        assert total >= 1
        assert any(t.name == "王五" for t in items)

    def test_update_talent_tags(self, test_db):
        """测试更新人才标签"""
        created = TalentService.create_talent(test_db, _make_talent_data(tags=["初始"]))
        update_data = TalentUpdate(tags=["新标签A", "新标签B"])
        updated = TalentService.update_talent(test_db, created.id, update_data)
        assert updated.tags == ["新标签A", "新标签B"]

    def test_check_duplicate_found(self, test_db):
        """测试查重：同名同手机号应被识别为重复（绕过API唯一性约束直接入库）"""
        from app.models.talent import Talent
        from app.schemas.talent import GenderEnum, EducationLevel, TalentStatus
        t1 = TalentService.create_talent(test_db, _make_talent_data(
            name="查重测试", phone="13512345678", email="dup1@example.com"
        ))
        # 直接插入一条同名同手机号的重复记录（模拟Excel批量导入未做校验）
        dup = Talent(
            talent_code="TDUP0001",
            name="查重测试",
            gender=GenderEnum.MALE,
            phone="13512345678",
            education=EducationLevel.BACHELOR,
            status=TalentStatus.RESERVE
        )
        test_db.add(dup)
        test_db.commit()
        duplicates = TalentService.check_duplicate(test_db, t1.id)
        assert isinstance(duplicates, list)
        assert len(duplicates) >= 1

    def test_check_duplicate_not_found(self, test_db):
        """测试查重：不存在的人才应抛出异常"""
        with pytest.raises(NotFoundException):
            TalentService.check_duplicate(test_db, 999999)


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
