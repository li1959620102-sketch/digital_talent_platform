# RBAC 权限与用户配置管理手册

> 版本：v1.0 · 更新日期：2026-09 · 适用角色：super_admin / 运维

## 一、角色体系

平台采用 **四角色 RBAC 模型**（基于 JWT + 前端路由守卫 + 后端依赖注入校验），所有角色定义在 `app/models/permission.py`，启动时由 `app/core/seed.py` 初始化，无需手动插入。

### 1.1 角色矩阵（R = 读 / W = 写 / D = 删 / A = 管理员操作）

| 功能模块 | super_admin | admin | hr | user |
|---------|:-----------:|:-----:|:--:|:----:|
| 数据总表 Dashboard    | R | R | R | R |
| 人才档案 Talent       | RWD | RWD | RWD | R |
| 岗位管理 Position     | RWD | RWD | RWD | R |
| 测评管理 Assessment   | RWD | RWD | RWD | R |
| 岗位匹配 Matching     | RWA | RWA | RWA | R |
| 培训赋能 Training     | RWD | RWD | R | R |
| 知识库 Knowledge      | RWDA | RWDA | RWD | R |
| AI 智能体中心 Agent   | RWDA | RWD | R | R |
| 用户管理 User         | RWDA | ❌  | ❌ | ❌ |
| 系统配置 Config       | A   | ❌  | ❌ | ❌ |

### 1.2 角色枚举值
```python
# app/models/permission.py 定义
class RoleEnum(str, Enum):
    SUPER_ADMIN = "super_admin"   # 超管：唯一能进 /users 页面
    ADMIN       = "admin"         # 管理员：所有业务模块
    HR          = "hr"            # 人力资源：人才/岗位/测评/匹配读写
    USER        = "user"          # 普通用户：公开注册默认角色，只读
```

### 1.3 账号生命周期（自动流程）
```
用户访问 /register
    ↓
POST /api/v1/auth/register → 默认 role = user，返回 token
    ↓  （用户立即登录，可访问只读页面）
super_admin 登录 /users
    ↓
PUT /api/v1/users/{id}/role → 修改为 admin/hr/super_admin
    ↓
用户下次登录时 JWT 包含新 role，前端菜单与后端接口同步生效
```

## 二、JWT 认证机制

### 2.1 Token 结构
- **Access Token**：`HS256` 签名，有效期 30 分钟
- **Refresh Token**：有效期 7 天（当前前端未启用刷新逻辑，统一重新登录）
- Payload 字段：
  ```json
  {
    "sub": "user_id_数字",
    "username": "admin",
    "role": "super_admin",
    "exp": 175xxxxxxx
  }
  ```

### 2.2 后端接口权限校验方式
```python
# 所有受保护接口通过 Depends(get_current_user) 注入当前用户
# 再按 role 进行分支判断
@router.get("/users")
def list_users(db=..., current_user=Depends(require_role(RoleEnum.SUPER_ADMIN))):
    ...  # 只有 super_admin 能调用

@router.delete("/talents/{tid}")
def delete_talent(tid: int, current_user=Depends(require_role([RoleEnum.SUPER_ADMIN, RoleEnum.ADMIN, RoleEnum.HR]))):
    ...  # 三种角色均可删除
```
> 后端双层校验：即使前端路由守卫被绕过，接口返回 403 Forbidden，确保安全。

### 2.3 前端路由守卫（App.tsx）
```tsx
// 未登录：跳 /login
if (!token && !publicRoutes.includes(path)) return <Navigate to="/login" replace />;

// super_admin 专属页：/users
if (path.startsWith('/users') && role !== 'super_admin')
  return <Navigate to="/403" replace />;

// 业务页：hr/admin/super_admin 可写，user 仅访问不触发写操作
```
> 前端主菜单 MainLayout.tsx 也按 role 过滤菜单项，user 看不到"用户管理"入口。

## 三、默认账号与初始化

### 3.1 seed.py 内置默认账号
| 用户名 | 密码 | 角色 | 用途 |
|--------|------|------|------|
| admin  | admin123 | super_admin | 平台超级管理员，上线后务必修改密码 |
| hr01   | hr123456 | hr | 示例 HR 账号（如 seed 开启 SAMPLE_USERS） |

### 3.2 seed.py 何时执行
- `main.py` 启动时调用 `await seed_data()`
- 幂等：已存在的角色/用户 **不覆盖**，只补缺失项
- 重置方式：清空 users / roles 表后重启后端，或手动调用 `python -m app.core.seed`

## 四、权限变更操作指引（super_admin）

### 4.1 提升新注册用户为 HR
1. 用 `admin` 登录，进入「用户管理」
2. 搜索目标用户名 → 点击 **编辑角色**
3. 下拉选 `hr` → **保存**
4. 告知该用户 **重新登录** 让新权限生效

### 4.2 禁用账号
1. 用户管理 → 搜索账号 → 切换 **状态开关**（active → disabled）
2. 被禁用账号 JWT 下一次请求接口时会返回 401，强制退出

### 4.3 重置密码
1. 用户管理 → 点击 **重置密码** → 输入新密码（≥6位）
2. 建议使用一次性密码并要求用户首次登录后自行修改（版本 v1.1 将加入强制修改）

## 五、安全加固建议（生产环境）

| 措施 | 说明 | 当前状态 |
|------|------|---------|
| 修改默认 admin 密码 | 必须第一项执行 | ⚠️ 默认 admin123 |
| 变更 JWT SECRET_KEY | `.env` 中 SECRET_KEY 改强随机串 | ⚠️ 使用默认值 |
| 开启 HTTPS | Nginx 配置 SSL 证书，Cookies 加 Secure+HttpOnly | ⚠️ 待配置 |
| 登录失败锁定 | 连续 5 次失败 → 锁定账号 15 分钟 | 🔜 v1.2 |
| 操作审计日志 | 所有写操作记录（who/when/what/IP） | 🔜 v1.2 |
| Token 自动刷新 | 基于 refresh token 无感续期 | 🔜 v1.2 |
| 最小权限原则 | 业务账号一律给 `hr` 或 `user`，不共享 `admin` | ⚠️ 请遵守 |

## 六、常见问题

**Q：修改用户角色后，用户不生效？**
A：JWT 是离线签名，角色被编码进 token。必须要求用户**重新登录**获取新 token。

**Q：super_admin 误删自己怎么办？**
A：进入 MySQL 直接执行：
```sql
INSERT INTO users (username, password_hash, role, is_active)
VALUES ('admin', '<bcrypt_hash_of_new_password>', 'super_admin', 1)
ON DUPLICATE KEY UPDATE role='super_admin', is_active=1;
```

**Q：公开注册担心被刷，能关闭吗？**
A：在 `.env` 中设置 `PUBLIC_REGISTER_ENABLED=false`，`auth.py` 注册接口会返回 403。

---

*配套：`app/core/seed.py`（初始化脚本）、`app/services/auth_service.py`（JWT 签发与校验）、`frontend/src/AuthContext.tsx`（前端登录态管理）。*
