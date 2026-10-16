#!/bin/bash
# =============================================================================
# AI 数字化人才平台 —— 生产数据备份
#
# 备份分级（依据「丢了能不能重建」）：
#   必备份（唯一真相源）：MySQL 业务库、PostgreSQL 分析库、MinIO 原始文档、知识库文档目录
#   建议备份（可重建但重建耗时）：Milvus 向量数据 —— 每周一次
#   不备份（可重新拉取）：Ollama 模型目录（2.4G，pull 即可恢复）
#
# 保留策略：每日备份留7 份，每周 Milvus 备份留 3 份。
# 执行方式：由 cron 每日 03:17 调用，也可手动执行 /opt/backup.sh。
# 可逆性：只往 /opt/backups 写文件，不触碰容器与业务数据；删除该目录即彻底撤销。
# =============================================================================
set -uo pipefail

APP_DIR=/opt/digital_talent_platform
BACKUP_DIR=/opt/backups
LOG=/var/log/backup.log
KEEP_DAILY=7
KEEP_MILVUS=3
STAMP=$(date +%Y%m%d_%H%M%S)
DOW=$(date +%u)   # 1=周一 … 7=周日

# 读取生产密钥（POSTGRES_PASSWORD 等）。MySQL 走容器内环境变量，无需在此读取。
set -a
# shellcheck disable=SC1091
[ -f "$APP_DIR/.env" ] && . "$APP_DIR/.env"
set +a

mkdir -p "$BACKUP_DIR"

log() { echo "[$(date '+%F %T')] $*" | tee -a "$LOG"; }

fail=0

# --- 1. MySQL 业务库（唯一真相源，必须成功）----------------------------------
log "开始备份 → $BACKUP_DIR"
if docker exec digital_talent_mysql sh -c \
    'exec mysqldump -uroot -p"$MYSQL_ROOT_PASSWORD" --single-transaction \
     --default-character-set=utf8mb4 --databases digital_talent' \
    2>/dev/null | gzip > "$BACKUP_DIR/mysql_${STAMP}.sql.gz"; then
    size=$(du -h "$BACKUP_DIR/mysql_${STAMP}.sql.gz" | cut -f1)
    log "  MySQL      OK  mysql_${STAMP}.sql.gz ($size)"
else
    log "  MySQL      FAIL"
    fail=1
fi

# --- 2. PostgreSQL 分析库 ----------------------------------------------------
if docker exec -e PGPASSWORD="$POSTGRES_PASSWORD" digital_talent_postgres \
    pg_dump -U postgres digital_talent_analytics 2>/dev/null \
    | gzip > "$BACKUP_DIR/postgres_${STAMP}.sql.gz"; then
    size=$(du -h "$BACKUP_DIR/postgres_${STAMP}.sql.gz" | cut -f1)
    log "  PostgreSQL OK  postgres_${STAMP}.sql.gz ($size)"
else
    log "  PostgreSQL FAIL"
    fail=1
fi

# --- 3. MinIO 原始文档（简历/上传文件）---------------------------------------
MINIO_VOL=digital_talent_platform_minio_data
if [ -d "/var/lib/docker/volumes/$MINIO_VOL" ]; then
    tar -C "/var/lib/docker/volumes/$MINIO_VOL" -czf "$BACKUP_DIR/minio_${STAMP}.tar.gz" . 2>/dev/null \
        && log "  MinIO      OK  minio_${STAMP}.tar.gz ($(du -h "$BACKUP_DIR/minio_${STAMP}.tar.gz" | cut -f1))" \
        || { log "  MinIO      FAIL"; fail=1; }
fi

# --- 4. 知识库文档目录 ------------------------------------------------------
MEDIA_VOL=digital_talent_platform_backend_media
if [ -d "/var/lib/docker/volumes/$MEDIA_VOL" ]; then
    tar -C "/var/lib/docker/volumes/$MEDIA_VOL" -czf "$BACKUP_DIR/knowledge_${STAMP}.tar.gz" . 2>/dev/null \
        && log "  知识库文档 OK  knowledge_${STAMP}.tar.gz ($(du -h "$BACKUP_DIR/knowledge_${STAMP}.tar.gz" | cut -f1))" \
        || { log "  知识库文档 FAIL"; fail=1; }
fi

# --- 5. Milvus 向量数据（每周日一次）----------------------------------------
if [ "$DOW" = "7" ]; then
    MILVUS_VOL=digital_talent_platform_milvus_data
    if [ -d "/var/lib/docker/volumes/$MILVUS_VOL" ]; then
        tar -C "/var/lib/docker/volumes/$MILVUS_VOL" -czf "$BACKUP_DIR/milvus_${STAMP}.tar.gz" . 2>/dev/null \
            && log "  Milvus(周) OK  milvus_${STAMP}.tar.gz ($(du -h "$BACKUP_DIR/milvus_${STAMP}.tar.gz" | cut -f1))" \
            || { log "  Milvus(周) FAIL（向量可由灌库脚本重建，不影响可用性）"; }
    fi
fi

# --- 6. 清理过期备份 --------------------------------------------------------
del() { find "$BACKUP_DIR" -name "$1" -type f -printf '%T@ %p\n' 2>/dev/null \
        | sort -rn | tail -n +$2 | cut -d' ' -f2- | while read -r f; do
              rm -f "$f" && log "  清理过期 $(basename "$f")"
          done; }
del "mysql_*.sql.gz"      "$((KEEP_DAILY + 1))"
del "postgres_*.sql.gz"   "$((KEEP_DAILY + 1))"
del "minio_*.tar.gz"      "$((KEEP_DAILY + 1))"
del "knowledge_*.tar.gz"  "$((KEEP_DAILY + 1))"
del "milvus_*.tar.gz"     "$((KEEP_MILVUS + 1))"

used=$(du -sh "$BACKUP_DIR" | cut -f1)
log "备份完成，占用 ${used}（失败标记=$fail）"
exit $fail