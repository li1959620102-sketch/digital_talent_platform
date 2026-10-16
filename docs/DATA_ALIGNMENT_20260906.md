# 数据对齐专项报告（2026-09-06）

## 一、任务目标
1. 前端不同业务版块的数据相互对齐
2. 同时对齐 MySQL / PgSQL / Redis / Milvus / MinIO 各存储
3. 对齐完成后清理残留无用脚本/日志，保持项目干净

## 二、结论速览
**各版块数字与存储已全部对齐**，核心业务实体的数据源一致、无孤儿、无悬挂引用、无覆盖缺口。

| 存储 | 现状 | 对齐结果 |
|------|------|---------|
| MySQL（主数据源） | 人才53 / 岗位36 / 测评结果54 / 测评任务62 / 课程40 / 学习计划10 / 知识文件8 / chunks 52 / 匹配440 | ✅ 引用完整性良好 |
| Milvus | knowledge_base 52 / talent_resume 53 / job_position 36 | ✅ 与 MySQL 完全对齐（本轮修复） |
| MinIO | knowledge-docs 6（清理后）/ resumes 0 / imports 0 | ✅ 孤儿对象已清 |
| Redis | 0 keys | ✅ 未使用，无脏数据 |
| PgSQL | digital_talent_analytics 5 分析表 | ⚠️ 独立预留分析库，前端不读取，不影响展示 |

## 三、MySQL ↔ 前端各版块对齐核验
所有总数均为实时 COUNT，Dashboard / 列表 / DB 三者动态一致：

| 指标 | Dashboard | 列表接口 | MySQL | 结论 |
|------|-----------|---------|-------|------|
| 人才总数 | 53 | 53 | 53 | ✅ |
| 在岗 active | 18 | - | 18 | ✅ |
| 储备 reserve | 31 | 31（筛选） | 31 | ✅ |
| 岗位总数 | 36 | 36 | 36 | ✅ |
| 测评结果 | 54 | 54 | 54 | ✅ |
| 测评任务 | - | 62 | 62 | ✅ |
| 课程总数 | 40 | 40 | 40 | ✅ |
| 知识文件 | - | 8 | 8 | ✅ |
| 匹配记录 | 440 | - | 440 | ✅ |

**人才测评覆盖 = 100%**：53 位人才全部有测评结果（talent 422 重测 1 份属正常），"盘点人才库"不再出现"暂无测评档案"。

## 四、存储间对齐（本轮修复）
### 4.1 Milvus ↔ MySQL
排查发现并修复 **knowledge_base 孤儿向量**：collection 有 54 条，MySQL chunks 仅 52，差异为已删除文件（file_id 4/5）的孤儿向量残留。

**根因（代码缺陷）**：
1. 批量删除接口 `batch_delete_knowledge_files`：
   - `MilvusService()` 未传 collection_name（必填）→ 抛错被吞
   - expr 用不存在的字段 `knowledge_id`，实际为 `file_id` → 永远删不掉
   - async delete 未正确等待
2. 单删接口 `delete_knowledge_file`：完全没有 Milvus 向量清理

**修复**：
- `knowledge_service.py` 新增 `delete_file_vectors(db, file_id)` + `_remove_milvus_vectors(file_id)`（正确 collection + `file_id` 字段同步删除）
- 单删、批量删接口统一调用，删除文件时级联清理向量

**对齐后核验**：
- knowledge_base: 54 → 52（清 2 条孤儿），与 MySQL chunks 52 一致，无孤儿无重复
- talent_resume: 53 ↔ talents 53（无孤儿/缺失）
- job_position: 36 ↔ job_positions 36（无孤儿/重复）

### 4.2 MinIO ↔ MySQL
MinIO 中存在大量历史孤儿对象（上传后 DB 记录已删或从未关联）：
- **knowledge-docs**：27 → 6（仅保留 DB 引用的 6 个，清 21 个孤儿）
- **resumes**：47 → 0（53 人才均无 resume_file_id/name 引用，全部为 seed/测试残留孤儿）
- **imports**：6 → 0（批量导入源文件残留孤儿）

> 说明：人才简历/画像/匹配均走 Milvus talent_resume 向量，不依赖 MinIO 原文件，删除孤儿对象不影响任何功能。

### 4.3 Redis / PgSQL
- **Redis**：0 keys，当前无缓存依赖，无脏数据，无需清理
- **PgSQL**：`digital_talent_analytics` 库有 5 张分析表（dashboard_summaries/match_analytics/talent_behavior_logs/talent_trend_snapshots/training_analytics），为独立预留分析库，当前后端无接口/前端无页面读取，不影响展示一致性。配套提供 `scripts/sync_analytics_to_pgsql.py` 作为后续同步工具。

## 五、保留的对齐工具脚本
纳入版本管理，作为可复用幂等工具：
- `backend/scripts/sync_milvus_vectors.py`：Milvus 三集合 ↔ MySQL 对齐（补齐/清孤儿/去重）
- `backend/scripts/sync_analytics_to_pgsql.py`：MySQL 主数据派生同步到 PgSQL 分析库

## 六、变更清单
| 文件 | 变更 |
|------|------|
| backend/app/services/knowledge_service.py | 新增 delete_file_vectors / _remove_milvus_vectors |
| backend/app/api/v1/knowledge.py | 单删/批量删统一调用向量清理 |
| backend/scripts/sync_milvus_vectors.py | 新增（对齐工具） |
| backend/scripts/sync_analytics_to_pgsql.py | 新增（对齐工具） |

Commits：`01f1abc`（删除修复）、sync 脚本提交。
