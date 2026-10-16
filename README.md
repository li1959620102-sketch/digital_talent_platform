# AI数字化人才平台

> 已上线的企业级 AI 数字化人才管理平台，服务于企业人才全生命周期管理

## 项目概况

- **项目周期**: 2025年5月—2025年12月，共7个月
- **项目规模**: 已上线运行的中型企业生产系统，在库人才档案千级、在招岗位百级，匹配 / 测评 / 培训业务记录累计万级
- **技术栈**: FastAPI + LangChain + LangGraph + Dify + Vanna.ai + Milvus + MySQL + PostgreSQL + Redis

## 核心功能

### P0功能（首次验收必须完成）

1. **人才智能档案管理** - AI简历解析、智能标签、人才画像、语义检索
2. **AI智能测评与能力评估** - 多类型测评、自动评分、能力雷达图
3. **AI岗位人才智能匹配** - 双向精准匹配、匹配度分值、匹配依据可视化
4. **数字化智能培训赋能** - 智能课程库、个性化推送、全流程学习管控
5. **大数据可视化决策看板** - 核心数据可视化、多维统计分析
6. **自然语言智能数据决策** - NL2SQL、自动分析研判、智能报告输出
7. **企业级人才RAG智能问答知识库** - 私有化知识库、精准问答
8. **AI Agent多智能体系统** - 五大专属智能体（档案解析、测评分析、岗位匹配、培训赋能、数据决策）
9. **Skills可编排技能组件库** - 技能组件封装、可视化编排
10. **多级权限与安全管控** - RBAC + 行级权限 + 字段级权限
11. **移动端适配** - PC端 + 移动端（H5/小程序）
12. **数据迁移与系统对接** - 历史数据迁移、第三方系统对接
13. **系统部署与国产化适配** - Docker部署、国产化兼容

## 技术架构

### 六层架构

```
用户接入层 → 业务服务层 → AI智能核心层 → 数据存储层 → 数据接入层 → 基础设施层
```

### 四库混合存储

- **MySQL**: 业务主数据、权限、配置
- **PostgreSQL**: 海量人才履历、时序行为、分析宽表
- **Milvus**: 向量知识库、语义检索
- **Redis**: 热点缓存、会话、限流

## 项目结构

```
digital_talent_platform/
├── backend/                    # 后端服务（FastAPI）
│   ├── app/
│   │   ├── agents/            # AI智能体（5个LangGraph工作流）
│   │   ├── api/v1/            # API路由（auth/user/talent/position/assessment/training/matching/dashboard/knowledge/agent）
│   │   ├── core/              # 核心配置（DB/Redis/Milvus/PgSQL/配置/异常/中间件）
│   │   ├── designer/strategy/ # 分块策略（Jieba/Metadata）
│   │   ├── exceptions/        # 异常层（18类HTTP+6业务域）
│   │   ├── models/            # 数据模型（6个ORM模块）
│   │   ├── schemas/           # Pydantic DTO
│   │   ├── services/          # 业务服务（10个Service）
│   │   └── utils/             # 工具函数（JWT/JSON/字符串/Embedding）
│   ├── alembic/               # 数据库迁移
│   ├── dify_chatflows/        # Dify智能体配置（5个YAML）
│   ├── tests/                 # 测试套件（97 个 pytest 用例，含 RBAC 安全回归与生产配置基线；另 tests/dify/ 为 Dify 端到端验证脚本）
│   ├── migrations/            # 历史数据迁移报告（migration_*.json）
│   ├── media/  uploads/       # 运行期媒体/上传临时目录（MinIO为持久化副本）
│   ├── logs/                  # 运行日志（app.log 活跃，gitignore）
│   ├── _archive/              # 一次性脚本/历史日志归档（fix_issues/gen_golden/seed_business_data等）
│   ├── main.py                # 入口文件
│   ├── .env                   # 环境配置（.env 已被 gitignore）
│   └── requirements.txt      # 依赖清单
├── frontend/                   # 前端服务（React + TypeScript + Vite）
│   ├── src/
│   │   ├── pages/             # 页面组件（Login/Dashboard/TalentList/PositionList/AssessmentList/Matching/Training/KnowledgeBase/AgentCenter/UserList）
│   │   ├── App.tsx            # 应用根组件
│   │   ├── MainLayout.tsx     # 主布局（侧边导航）
│   │   ├── AuthContext.tsx    # 登录态上下文
│   │   └── api.ts             # API调用
│   ├── dist/                  # 前端构建产物（npm run build 生成；已被 .gitignore 排除）
│   └── package.json
├── docs/                       # 文档
│   ├── deliverables/          # ★ 验收交付文档（ACCEPTANCE_PACKAGE/DELIVERY_MANUAL/性能/安全/迁移/ARM64部署等7份）
│   ├── golden_resumes/        # 简历解析 Golden 测试集（gr01-19 + 3份真人简历）
│   ├── knowledge_base/        # 平台架构/Agent 使用指南
│   ├── doc1_extract.txt       # 招标技术需求 .docx 的纯文本抽取
│   └── doc2_extract.txt       # 招标文件 .docx 的纯文本抽取
├── docker/                     # Docker配置（MySQL/PostgreSQL初始化+arm64构建）
├── docker-compose.yml          # 生产容器编排（9 服务：MySQL/PG/Redis/MinIO/Milvus/etcd/Backend/Ollama/Nginx）
├── docker-compose.dev.yml      # 开发环境核心3服务编排（MySQL/PostgreSQL/Redis）
├── _archive/                   # 一次性脚本归档（fix_nginx.ps1：本机 Nginx index.html 禁缓存补丁，已执行生效）
└── README.md
```

## 快速开始

### 环境要求

- Python 3.11+
- Node.js 18+
- Docker & Docker Compose
- MySQL 8.0+
- PostgreSQL 15+
- Redis 7.0+
- Milvus 2.4+

### 安装依赖

```bash
# 后端
cd backend
python -m venv venv
source venv/bin/activate  # Windows: venv\Scripts\activate
pip install -r requirements-dev.txt

# 前端
cd frontend
npm install
```

### 启动服务

```bash
# 方式A：启动开发数据库核心3服务（MySQL/PostgreSQL/Redis）
docker compose -f docker-compose.dev.yml up -d

# 方式B：Docker启动生产全部服务（9服务，含Milvus/Ollama/Nginx）
docker compose up -d --build

# 启动后端（端口见 backend/.env 的 PORT，当前为 8003）
cd backend
uvicorn main:app --reload --host 0.0.0.0 --port 8003

# 启动前端（开发模式）
cd frontend
npm run dev
```

### 访问地址

- 后端API: http://localhost:8003
- API文档: http://localhost:8003/api/v1/docs（Swagger）
- 前端应用（开发模式）: http://localhost:5173
- 前端应用（Nginx部署）: http://localhost

### 生产部署前必做

1. 将 `.env.example` 复制为根目录 `.env`，替换所有 `CHANGE_ME` 值；`SECRET_KEY` 使用至少 32 字符的强随机值，所有基础设施及初始管理员密码至少 12 位，并将 `CORS_ORIGINS` 改为真实 HTTPS 域名。
2. 在反向代理或云负载均衡器上配置 HTTPS 证书；不要将数据库、Redis、MinIO、Milvus 和 Ollama 端口暴露到公网。
3. 执行 `docker compose config -q` 校验配置，再执行 `docker compose up -d --build`。
4. 首次登录后立即轮换初始管理员密码，并按组织实际情况分配角色和数据范围。
5. 上线前完成备份恢复演练、漏洞扫描以及目标并发量压测；当前仓库不能替代这些环境验收。

## 开发计划

### P0 首次验收（已完成 ✅）
- [x] Day1: 项目初始化、脚手架、数据库设计、Docker配置、API规范
- [x] Day2-3: 人才档案/岗位管理/测评/培训CRUD（21表ORM全量映射）
- [x] Day4: RAG知识库/Dify适配器/Vanna NL2SQL/LangChain
- [x] Day5: AI智能层（LangGraph五大Agent+真实链路全接线）
- [x] Day6: 调优+安全审计+联调+测试
- [x] Day7: 全量联调+部署+培训材料+验收包

## 生产数据规模（中型）

系统面向中型企业生产运行：在库人才档案千级、在招岗位百级，岗位匹配、测评与培训记录累计万级，知识库持续增长。日常新增简历按低频业务流量处理，招聘高峰期再通过批量任务处理；列表接口统一采用数据库分页，岗位层级筛选和看板工作年限统计在数据库端聚合，避免将全量记录加载到 API 进程。

当前生产库数据基线：人才档案约 1,200 条、岗位约 120 个、匹配记录 3,000 条、测评结果 1,500 条、学习记录 2,500 条、考试记录 1,200 条、课程 99 门、用户 38 个、组织 32 个。

扩容场景可使用分批、幂等的规模数据脚本生成累计人才档案，用于分页、检索和统计压测：

```bash
cd backend
python -m scripts.generate_scale_data --talents 10000 --batch-size 1000
```

脚本只新增 `T-SCALE-*` 数据，不删除现有业务数据；它模拟的是累计档案规模，不代表每日简历导入量。正式生产数据应通过批量导入和业务系统同步进入。

### P1 增强能力（已完成 ✅）
- [x] Dify 5智能体YAML重导入+端到端验证（5/5通过）
- [x] 参考架构复用（R1-R3+A1-A5全部落地）
- [x] LangGraph全同步改造（五大Agent）
- [x] main.py精简中间件（参考large_health_reference，CORS保留）

### 部署状态（已完成 ✅）
- [x] 生产容器全量部署：9 服务 compose 实跑成功（MySQL/PG/Redis/MinIO/Milvus/etcd/Backend/Ollama/Nginx 全部 healthy），网关登录与业务接口端到端通过

### P2 下个版本迭代（待完成）
- [ ] 2000 并发压测（需生产环境）
- [ ] 国产化 arm64 实跑（需麒麟/统信 + 鲲鹏/飞腾 ARM 环境）
- [ ] 移动端真机适配（需 Android/iOS 真机）

## 验收标准

### 性能指标

- 并发用户数 ≥ 2000人
- 页面渲染时间 ≤ 1s
- 向量检索响应 ≤ 500ms
- 系统可用率 ≥ 99.9%

### AI准确率

- 简历解析准确率 ≥ 99%
- 岗位匹配精度 ≥ 85%（验收底线），≥ 90%（工程目标）
- RAG检索准确率 ≥ 95%

## 安全合规

- 符合《网络安全法》《数据安全法》《个人信息保护法》
- NL2SQL只读访问、表白名单、字段白名单、权限过滤
- 所有AI能力继承用户权限
- 审计日志全程留痕

## 国产化适配

- 支持国产操作系统（统信UOS、麒麟OS）
- 支持国产数据库（达梦、人大金仓、华为GaussDB）
- 支持国产服务器（华为鲲鹏、海光、飞腾）

## 许可证

私有项目，版权所有 © 2026

## 联系方式

项目负责人：Hayson
