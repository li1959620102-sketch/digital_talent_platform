"""
Vanna NL2SQL 训练数据共享知识库
- DDL 必须与 ORM 模型 / 真实表结构一致（这是 LLM 生成可执行 SQL 的关键）
- examples 是经过验证的 few-shot 范本，覆盖常见业务问句
- vanna_adapter 与 Ollama fallback 共用本模块，避免两套语义漂移
"""

# 表结构 DDL（与 MySQL 实际 schema 对齐 — 2026-09-05 实测）
DEFAULT_DDL = [
    """CREATE TABLE talents (
  id INT PRIMARY KEY AUTO_INCREMENT,
  talent_code VARCHAR(64),
  name VARCHAR(64),
  gender VARCHAR(16),           -- 'male' / 'female'
  phone VARCHAR(32) UNIQUE,
  email VARCHAR(128),
  education VARCHAR(32),         -- '高中' / '大专' / '本科' / '硕士' / '博士'
  experience_years INT,
  current_company VARCHAR(128),
  current_position VARCHAR(128),
  status VARCHAR(32) DEFAULT 'reserve',  -- 'active' / 'reserve' / 'left'
  tags TEXT,
  capability_rating VARCHAR(32),
  created_at DATETIME DEFAULT CURRENT_TIMESTAMP,
  updated_at DATETIME DEFAULT CURRENT_TIMESTAMP
);""",
    """CREATE TABLE job_positions (
  id INT PRIMARY KEY AUTO_INCREMENT,
  position_code VARCHAR(50),
  position_name VARCHAR(100),
  department_id INT,
  position_category VARCHAR(50),
  position_level VARCHAR(50),    -- enum: entry/junior/intermediate/senior/expert/manager/director
  position_type VARCHAR(50),
  headcount INT,
  filled_count INT,
  salary_min INT,
  salary_max INT,
  work_location VARCHAR(200),
  education_requirement VARCHAR(50),  -- 注意：不是 education_required
  experience_requirement INT,         -- 注意：不是 min_experience_years
  skill_requirements JSON,
  status VARCHAR(50) DEFAULT 'open',
  created_at DATETIME DEFAULT CURRENT_TIMESTAMP
);""",
    """CREATE TABLE match_records (
  id INT PRIMARY KEY AUTO_INCREMENT,
  talent_id INT,
  position_id INT,
  match_score DECIMAL(5,2),      -- 注意：是 match_score 不是 final_score
  match_dimensions JSON,
  match_basis TEXT,
  strengths TEXT,
  weaknesses TEXT,
  suggestions TEXT,
  status VARCHAR(50),
  feedback TEXT,
  created_at DATETIME DEFAULT CURRENT_TIMESTAMP,
  updated_at DATETIME DEFAULT CURRENT_TIMESTAMP
);""",
    """CREATE TABLE assessment_results (
  id INT PRIMARY KEY AUTO_INCREMENT,
  talent_id INT,
  task_id INT,
  paper_id INT,
  answers JSON,
  total_score DECIMAL(5,2),
  correct_count INT,
  wrong_count INT,
  unanswered_count INT,
  capability_dimensions JSON,
  radar_chart_data JSON,
  capability_level VARCHAR(32),  -- ENUM: entry/junior/intermediate/senior/expert/backbone/core
  start_time DATETIME,
  submit_time DATETIME,
  duration_seconds INT,
  status VARCHAR(20),
  created_at DATETIME DEFAULT CURRENT_TIMESTAMP
);""",
    """CREATE TABLE courses (
  id INT PRIMARY KEY AUTO_INCREMENT,
  course_name VARCHAR(128),
  course_category VARCHAR(32),
  duration_hours INT,
  status VARCHAR(32)
);""",
    """CREATE TABLE examination_records (
  id INT PRIMARY KEY AUTO_INCREMENT,
  talent_id INT,
  course_id INT,
  score DECIMAL(5,2),
  passed TINYINT,
  created_at DATETIME DEFAULT CURRENT_TIMESTAMP
);""",
]

# Few-shot examples（与真实 DDL 配套，覆盖典型业务问句）
DEFAULT_EXAMPLES = [
    {"question": "有多少人才？", "sql": "SELECT COUNT(*) AS total FROM talents"},
    {"question": "人才总数", "sql": "SELECT COUNT(*) AS total FROM talents"},
    {"question": "本科学历的人才有哪些？", "sql": "SELECT id, name, education FROM talents WHERE education = '本科' LIMIT 100"},
    {"question": "本月新进了多少人才？", "sql": "SELECT COUNT(*) AS total FROM talents WHERE created_at >= DATE_FORMAT(CURDATE(), '%Y-%m-01') AND created_at <= CURDATE()"},
    {"question": "各岗位平均匹配分是多少", "sql": "SELECT jp.position_name, ROUND(AVG(mr.match_score), 1) AS avg_score, COUNT(*) AS cnt FROM match_records mr JOIN job_positions jp ON mr.position_id = jp.id GROUP BY jp.id, jp.position_name ORDER BY avg_score DESC"},
    {"question": "哪些人才测评合格", "sql": "SELECT t.id, t.name, ar.total_score, ar.capability_level FROM talents t JOIN assessment_results ar ON t.id = ar.talent_id WHERE ar.capability_level IN ('backbone', 'core', 'senior', 'expert') ORDER BY ar.total_score DESC"},
]