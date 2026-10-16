# 国产化部署（方案 A·轻量）— arm64 构建与验收清单

> 决策来源：用户拍板「国产化选 A（轻）」——国产 OS + 国产 CPU 上可运行即可，数据库保持开源兼容（MySQL / PostgreSQL / Redis / Milvus），达梦/金仓等全量国产库替换列入 P2 / 二期。

## 1. 目标环境

| 层级 | 选型 | 说明 |
|------|------|------|
| 操作系统 | 麒麟软件 V10 / 统信 UOS（arm64） | 提供 arm64 容器运行时 |
| CPU | 鲲鹏 920 / 飞腾 FT-2000+（arm64，AArch64） | 与 x64 指令集不同，须构建 arm64 镜像 |
| 数据库 | MySQL 8.0 / PostgreSQL 15 / Redis 7 / Milvus 2.4（arm64 镜像） | 均为开源、官方提供 arm64 镜像，数据零改造 |
| 推理 | Ollama（arm64 构建，已含 qwen3:1.7b / bge-m3:latest arm64） | 本地推理，数据不出域，合《个保法》 |
| 中台 | Dify（arm64 支持） | AI 应用中台，不承载核心业务编排 |

## 2. 构建脚本

`docker/build_arm64.ps1`（已就绪）使用 `docker buildx` 多架构构建器产出 arm64 后端镜像：

```powershell
# 1) 启用 buildx 多架构构建器
docker buildx create --name multiarch --use
docker buildx inspect multiarch --bootstrap

# 2) 构建并载入 arm64 镜像（单平台用 --load；多平台分发用 --push 到镜像仓库）
docker buildx build --platform linux/arm64 -f backend/Dockerfile -t digital-talent-backend:arm64 . --load
```

`python:3.11-slim` 为多架构基础镜像，无需改动 `backend/Dockerfile` 即可构建 arm64。

> 依赖服务镜像同样需指定 `platform: linux/arm64`（在 docker-compose 中各服务加 `platform: linux/arm64`），包括 mysql/postgres/redis/milvus。

## 3. ARM 环境实测清单（在真实国产服务器执行，**本开发机为 x64，以下均 [待验证]**）

- [ ] 在 麒麟/统信 arm64 主机安装 Docker + buildx，执行 `build_arm64.ps1` 成功产出 `digital-talent-backend:arm64`
- [ ] `docker compose` 拉起 MySQL/PostgreSQL/Redis/Milvus 的 arm64 镜像，全部 `healthy`
- [ ] 后端容器启动：MySQL/Redis/Milvus 初始化成功，三集合（talent_resume / job_position / knowledge_base）创建成功
- [ ] Ollama arm64 启动，加载 `qwen3:1.7b` 与 `bge-m3:latest`，embedding dim=1024 校验通过
- [ ] 登录（admin/admin123）、人才 CRUD、简历解析建档、岗位匹配、知识库问答（Dify/本地 LLM）全链路 200
- [ ] 单元/集成测试 97 用例在 arm64 环境复跑通过
- [ ] 性能：普通接口 ≤1s、向量检索（Milvus 本机） ≤500ms 在国产 CPU 上实测（GPU 加速时 [待验证]）
- [ ] 数据迁移脚本（Excel/CSV 批量导入 + 迁移报告）在国产库运行通过

## 4. 已知约束与降级

- **全量国产库替换（达梦/金仓）未做**：当前用开源库保证兼容性，属方案 A 范围；列入 P2 / 二期。
- **Ollama 推理性能**：国产 CPU 单核性能弱于开发机 x64，LLM 生成延迟可能更高；架构已支持独立推理 tier + 水平扩展。
- **本机无法验证 arm64 运行时**：以上清单需在真实国产服务器执行后方可标注「已验证」。
