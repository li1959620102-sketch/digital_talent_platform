#!/usr/bin/env bash
# =====================================================================
# AI 数字化人才平台 —— 全栈上云部署脚本
#
# 在【服务器】上、项目根目录同级执行：
#   cp .env.example .env      # 先填好真实值
#   chmod +x deploy/deploy.sh
#   ./deploy/deploy.sh
#
# 脚本只负责：校验配置 → 构建镜像 → 启动 9 个服务 → 拉取本地大模型。
# 不自动灌业务数据/向量（避免误覆盖），灌数据命令在最后打印出来，
# 由你确认后手动执行。
# =====================================================================
set -euo pipefail

cd "$(dirname "$0")/.."
ROOT="$(pwd)"
COMPOSE="docker compose -f docker-compose.yml -f docker-compose.prod.yml"

echo "== AI 数字化人才平台 部署 =="
echo "项目目录：$ROOT"

echo "[1/6] 检查 docker 与 .env"
command -v docker >/dev/null 2>&1 || { echo "未安装 docker，请先安装 Docker 与 compose 插件"; exit 1; }
docker compose version >/dev/null 2>&1 || { echo "缺少 docker compose 插件（v2）"; exit 1; }
if [ ! -f .env ]; then
  echo "缺少 .env：请先执行 cp .env.example .env 并填入真实值"; exit 1
fi
if grep -q "CHANGE_ME" .env; then
  echo ".env 中仍存在 CHANGE_ME 占位值，请先全部替换成真实值"; exit 1
fi
echo "  OK"

echo "[2/6] 校验 compose 配置"
$COMPOSE config -q
echo "  OK"

echo "[3/6] 构建镜像（后端 Python 依赖 + 前端 npm 依赖，首次较慢）"
$COMPOSE build

echo "[4/6] 启动全部服务"
$COMPOSE up -d

echo "[5/6] 等待后端就绪（最多 5 分钟）"
for i in $(seq 1 60); do
  if docker exec digital_talent_backend python -c \
      "import urllib.request;urllib.request.urlopen('http://localhost:8000/health/ready',timeout=3)" \
      >/dev/null 2>&1; then
    echo "  后端已就绪"; break
  fi
  if [ "$i" -eq 60 ]; then
    echo "  后端未就绪。排查：docker logs digital_talent_backend"; exit 1
  fi
  sleep 5
done

echo "[6/6] 拉取本地大模型（qwen3:1.7b 对话 + bge-m3 向量，首次约数 GB）"
docker exec digital_talent_ollama ollama pull qwen3:1.7b
docker exec digital_talent_ollama ollama pull bge-m3

echo
echo "部署完成。"
echo "  访问入口： http://<服务器公网IP>/"
echo "  容器状态： docker ps --filter name=digital_talent"
echo
echo "还需要手动执行的两步（详见 docs/06_部署与集成/生产部署操作手册.md）："
echo "  ① 启用 HTTPS：放置证书 → 启用 docker/nginx/conf.d/https.conf.example"
echo "  ② 灌业务数据与向量："
echo "     docker exec -e PYTHONPATH=/app -w /app digital_talent_backend python -m scripts.seed_midscale_real_data"
echo "     docker exec -e PYTHONPATH=/app -w /app digital_talent_backend python -u scripts/seed_vector_index.py --only both --batch 100"
