-- 上万级数据索引补充（MySQL 8）。
-- 首次部署执行一次；重复执行前请检查 SHOW INDEX，避免同名索引。
-- ORM 模型也同步声明了这些索引，供新环境自动建表使用。
ALTER TABLE assessment_tasks ADD INDEX idx_assessment_task_status_time (status, start_time, end_time);
ALTER TABLE assessment_results ADD INDEX idx_result_task_submit (task_id, submit_time);
ALTER TABLE assessment_results ADD INDEX idx_result_score (total_score);
ALTER TABLE learning_records ADD INDEX idx_learning_status_updated (status, updated_at);
ALTER TABLE learning_records ADD INDEX idx_learning_plan_status (plan_id, status);
ALTER TABLE examination_records ADD INDEX idx_examination_passed_submit (passed, submit_time);
ALTER TABLE examination_records ADD INDEX idx_examination_plan_submit (plan_id, submit_time);
