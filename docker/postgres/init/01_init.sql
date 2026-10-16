-- PostgreSQL初始化脚本
-- 创建时间: 2026-08-31
-- 数据库: digital_talent_analytics

-- 创建数据库
CREATE DATABASE digital_talent_analytics;

\c digital_talent_analytics;

-- 创建schema
CREATE SCHEMA IF NOT EXISTS analytics;

-- 设置默认schema
SET search_path TO analytics;

-- 人才年度台账表
CREATE TABLE IF NOT EXISTS talent_yearly_stats (
    id SERIAL PRIMARY KEY,
    talent_id INT NOT NULL,
    year INT NOT NULL,
    total_assessments INT DEFAULT 0,
    avg_assessment_score DECIMAL(5,2) DEFAULT 0,
    total_training_hours INT DEFAULT 0,
    training_completion_rate DECIMAL(5,2) DEFAULT 0,
    position_match_count INT DEFAULT 0,
    promotion_count INT DEFAULT 0,
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    UNIQUE(talent_id, year)
);

-- 测评历史记录表
CREATE TABLE IF NOT EXISTS assessment_history (
    id SERIAL PRIMARY KEY,
    talent_id INT NOT NULL,
    assessment_id INT NOT NULL,
    assessment_date DATE NOT NULL,
    score DECIMAL(5,2) NOT NULL,
    capability_dimensions JSONB DEFAULT '{}',
    radar_chart_data JSONB DEFAULT '{}',
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);

-- 培训轨迹表
CREATE TABLE IF NOT EXISTS training_trajectory (
    id SERIAL PRIMARY KEY,
    talent_id INT NOT NULL,
    course_id INT NOT NULL,
    start_time TIMESTAMP,
    end_time TIMESTAMP,
    duration_minutes INT DEFAULT 0,
    completion_rate DECIMAL(5,2) DEFAULT 0,
    examination_score DECIMAL(5,2),
    passed BOOLEAN DEFAULT FALSE,
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);

-- 行为时序数据表
CREATE TABLE IF NOT EXISTS behavior_timeline (
    id SERIAL PRIMARY KEY,
    talent_id INT NOT NULL,
    behavior_type VARCHAR(50) NOT NULL,
    behavior_data JSONB DEFAULT '{}',
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);

-- 创建索引
CREATE INDEX idx_talent_yearly_stats_talent_id ON talent_yearly_stats(talent_id);
CREATE INDEX idx_assessment_history_talent_id ON assessment_history(talent_id);
CREATE INDEX idx_training_trajectory_talent_id ON training_trajectory(talent_id);
CREATE INDEX idx_behavior_timeline_talent_id ON behavior_timeline(talent_id);

-- 插入示例数据
INSERT INTO talent_yearly_stats (talent_id, year, total_assessments, avg_assessment_score, total_training_hours)
VALUES (1, 2026, 5, 85.5, 120);
