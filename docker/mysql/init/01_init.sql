-- MySQL 初始化脚本
-- 创建时间: 2026-08-31
-- 更新: 2026-09-18 —— 只保留建库，表结构统一交给后端 ORM 创建
--
-- 【为什么这里不再手写 CREATE TABLE】
-- 原先本文件手写了 7 张表，与 app/models 下的 ORM 模型（21 张表）严重漂移：
--   1) 缺 audit_logs / data_permissions / job_positions / match_records /
--      questions / test_papers / assessment_* / courses / training_plans /
--      learning_records / examination_records / knowledge_* 等表；
--   2) 已有的 talents 表缺 user_id 列；
--   3) users 表插入的 admin 密码哈希是不可解析的占位串，
--      导致 login 恒定失败（该哈希并非有效的 bcrypt 值）。
-- 上述问题会造成运行期 500（如 "Table 'digital_talent.audit_logs' doesn't exist"）。
--
-- 现由后端启动时统一按 ORM 元数据建表（app/core/database.py::init_mysql_tables），
-- 并由 app/core/seed.py 幂等创建默认组织、4 个角色及环境变量指定的初始超管账号
-- 以及 RBAC 权限体系。ORM 模型即 schema 唯一事实源。

SET NAMES utf8mb4;

-- 创建数据库（表结构由后端 ORM 在建连后创建）
CREATE DATABASE IF NOT EXISTS `digital_talent`
DEFAULT CHARACTER SET utf8mb4
COLLATE utf8mb4_unicode_ci;

USE `digital_talent`;
