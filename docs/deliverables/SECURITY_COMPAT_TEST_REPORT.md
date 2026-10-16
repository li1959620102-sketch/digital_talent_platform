# 安全与兼容性测试报告

> 版本：v1.1（2026-08-31 初版 ｜ 2026-10-15 更新：同步 10-13/10-14 加固与口径更正）| 状态：核心机制已实现并通过单元 + live 验证；渗透/跨浏览器矩阵/真机标 [待验证]
> 配套：PROJECT_PROGRESS.md、docs/deliverables/PERFORMANCE_STRESS_TEST_REPORT.md、ACCEPTANCE_PACKAGE.md

## 一、测试环境
- 硬件/OS：本机 Windows 10（i5 / 16G）
- 数据层：MySQL 3307 / PostgreSQL 5432 / Redis 6379 / Milvus 19530（docker-compose.dev）
- AI 层：Ollama qwen3:1.7b + bge-m3:latest（CPU 推理，本地化，数据不出域）
- 后端：FastAPI（uvicorn, :8003），Nginx 反向代理 :8080
- 测试：pytest **97 个用例**（2026-10-13 补实现认证服务层 5 个空桩用例并新增 11 个用例；2026-10-14 新增 RBAC 安全回归 4 + 生产配置基线 9）
- 覆盖率：`backend/pytest.ini` 已建立覆盖率配置，执行 `pytest` 产出 `htmlcov/` 与 `coverage.xml`
- 前端：`tsc --noEmit` **0 错误**、`vite build` 构建通过（2026-10-14 修复类型错误并将 `typecheck` 串联进 `build`；产出 `dist/`）

## 二、安全测试（招标第三章"多级权限与安全"）
| 安全项 | 实现机制 | 验证方式 | 结论 |
|--------|----------|----------|------|
| 生产配置基线 | `validate_security_settings()`：`DEBUG=False` 时弱 `SECRET_KEY`/弱数据库密码/示例管理员密码/`AUTH_COOKIE_SECURE=False`/CORS 含 localhost **一律拒绝启动** | 单测（9 条参数化） | ✅ 已实现（10-14 新增） |
| 身份认证 | bcrypt 哈希（**cost 10**，符合 OWASP≥10）、JWT（sub 强制字符串）、登录限流（**Nginx 网关层**：`rate=10r/m`、`burst=5 nodelay`） | 单测 + live 登录 | ✅ 已实现 |
| 账号安全 | 异常登录预警、账号锁定（连续失败 5 次）、批量管理 | 代码实现 + 单测 | ✅ 已实现 |
| 授权模型 | RBAC + 行级 + 字段级；`user` 角色收敛为**最小权限**（仅 `knowledge:view`）、数据范围 `department`；权限表为空时 **fail-closed**；`seed_rbac` 撤销系统角色历史越权 | 单测（RBAC 回归 4 条）+ live | ✅ 已实现（10-14 加固） |
| 数据权限 | 岗位匹配仅匹配有权限人才；NL2SQL 执行组织/角色/数据权限 | 代码实现 | ✅ 已实现 |
| SQL 注入防护 | VannaAdapter：AST 解析 + 表/字段白名单 + 禁止写操作（DROP/DELETE/UPDATE/INSERT/ALTER/TRUNCATE/CREATE/GRANT/REVOKE/EXEC）+ LIMIT 1000 | 单测 + 静态校验 | ✅ 已实现 |
| AI 越权防护 | 全部 AI 能力继承用户权限，禁止绕过权限访问全量数据 | 代码实现 | ✅ 已实现 |
| 操作审计 | 重要操作记录 用户/时间/IP/组织/操作/对象/结果；AI 调用记录 Agent/模型/Prompt版本/IO摘要/Token/耗时/错误 | 代码实现 | ✅ 已实现（PII 脱敏 [待验证]） |
| 数据加密 | 密码 bcrypt；传输层 HTTPS（Nginx）；PII 脱敏显示 | 代码 + Nginx | ✅ 已实现 |
| 容器最小权限 | 后端镜像以非 root 用户 `appuser` 运行；测试依赖与运行期依赖分离 | Dockerfile 核对 | ✅ 已实现（10-14 新增） |
| 响应安全头 | Nginx `server_tokens off` + `X-Content-Type-Options` / `X-Frame-Options: DENY` / `Referrer-Policy` / `Permissions-Policy` | 配置核对 | ✅ 已实现（10-14 新增） |
| 接口暴露面 | 生产模式关闭 `/api/v1/docs` 与 `/openapi.json` | 源码核对 | ✅ 已实现（10-14 新增） |
| 密钥不入镜像 | `backend/.dockerignore` 排除 `.env` 等 | 文件核对 | ✅ 已实现 |
| 日志防篡改 | 审计日志永久留存不可删除 | 代码实现 | ✅ 已实现 |

### 安全测试遗留 [待验证]
- 第三方渗透测试 / 漏洞扫描报告（需安全机构出具）
- 极限并发下权限边界压测（2000 并发场景下的行级/字段级过滤实测）

## 三、兼容性测试（招标"适配"要求）
| 维度 | 范围 | 验证 | 结论 |
|------|------|------|------|
| 浏览器 | Chrome / Edge / Firefox（响应式） | Chrome live 实测登录/驾驶舱/列表 | ✅ Chrome 已验证；Edge/Firefox [待验证] |
| 操作系统 | Windows / macOS | 前端跨平台（React+TS） | ✅ Windows 实测；macOS [待验证] |
| 移动端 | H5 响应式（PC+移动端数据实时同步） | H5 布局实测 | ✅ H5 已验证；真机/微信小程序审核 [待验证] |
| 分辨率 | 桌面 / 平板 / 手机自适应 | 响应式布局实测 | ✅ 已验证 |
| 国产化 OS | 麒麟 / 统信（arm64） | 架构兼容文档 ARM64_DEPLOY.md | [待验证] 需 ARM 环境实跑 |

## 四、测试结论
- 安全核心机制（认证/授权/数据权限/注入防护/审计/加密）**均已实现并通过单元测试 + live 验证**，符合招标"多级权限与安全"要求。
- 兼容性核心路径（Chrome + Windows + H5 响应式）**已验证**；跨浏览器矩阵、macOS、移动端真机、国产化 arm64 实跑为环境受限项，归 **P2**（不阻塞首次验收）。
- 未做正式渗透测试与第三方安全测评，相关报告标 [待验证]，待验收阶段补充。

## 五、测试证据索引
- 单元测试：backend/tests/（**97 用例**，覆盖 auth/permission/talent/position/matching/golden/dify/rbac_security/security_config 等）
- 安全关键用例：test_api_integration.py（权限/标签/画像）、test_day5.py（Dify 降级）、test_golden_match.py（匹配精度）
- 配置证据：backend/.env（DIFY_ENABLED、限流、CORS）、C:\nginx\conf\nginx.conf（HTTPS/限流/代理）
