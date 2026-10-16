#!/bin/bash
# =============================================================================
# 备份异地同步 —— 把本机备份推送到阿里云 OSS（走 ECS RAM 角色，不用静态密钥）
#
# 为什么需要：本机 /opt/backups 只能防「磁盘坏 / 误删容器」，
#             整机被释放、被入侵、机房故障时备份会跟着一起没，必须异地留存。
#
# 凭据方式：mode=EcsRamRole —— ossutil 自动向实例元数据服务
#           http://100.100.100.200/latest/meta-data/ram/security-credentials/
#           取实例绑定的 RAM 角色临时凭证，**密钥不落盘**，比 AK/SK 安全。
#
# 需要你在阿里云控制台完成两件事（脚本无法代劳）：
#   1) 创建一个 Bucket（建议与本机同地域，减少流量费与延迟）
#   2) 创建一个只授予该 Bucket 读写权限的 RAM 角色，并绑定到这台 ECS
#
# 你只需在这台服务器上填一行目标地址：
#   echo 'OSS_TARGET=oss://你的bucket名/backups/' > /root/backup_oss.env
#
# 安全性与幂等：
#   · 只读 /opt/backups，只写 OSS，不触碰线上容器与数据库
#   · --update：同名文件跳过，重复执行不重复消耗流量与存储
#   · 未配置目标时自动跳过并退出 0，不会让备份任务报错
# =============================================================================
set -uo pipefail

BACKUP_DIR=/opt/backups
OSSUTIL=/usr/local/bin/ossutil64
OSS_CONF=/root/.ossutilconfig
TARGET_FILE=/root/backup_oss.env
LOG=/var/log/backup.log
META=http://100.100.100.200/latest/meta-data

log() { echo "[$(date '+%F %T')] [异地同步] $*" | tee -a "$LOG"; }

# --- 0. 未配置目标 → 安静跳过（不影响本机备份与业务）----------------------
if [ ! -f "$TARGET_FILE" ]; then
    log "未配置 $TARGET_FILE，本次跳过（不影响本机备份）。"
    log "  启用方法：echo 'OSS_TARGET=oss://你的bucket名/backups/' > $TARGET_FILE"
    exit 0
fi
# shellcheck disable=SC1090
. "$TARGET_FILE"
OSS_TARGET="${OSS_TARGET:-}"

if [ ! -x "$OSSUTIL" ]; then
    log "未找到 $OSSUTIL，异地同步跳过（不影响本机备份）"; exit 0
fi
if [ -z "$OSS_TARGET" ]; then
    log "$TARGET_FILE 中 OSS_TARGET 为空，跳过"; exit 0
fi
if [ ! -d "$BACKUP_DIR" ]; then
    log "备份目录不存在：$BACKUP_DIR"; exit 1
fi

# --- 1. 检查实例是否已绑定 RAM 角色 ----------------------------------------
ROLE=$(curl -s --max-time 5 "$META/ram/security-credentials/" 2>/dev/null | tr -d '\r\n' | head -c 200)
if [ -z "$ROLE" ] || [ "$ROLE" = "<html>" ]; then
    log "实例未绑定 RAM 角色（元数据服务无凭据返回），异地同步跳过。"
    log "  请在控制台：ECS 实例详情 → 绑定与安全 → RAM角色 → 绑定后重试。"
    exit 0
fi
log "检测到实例 RAM 角色：${ROLE:0:80}"

# --- 2. 生成/校验 ossutil 配置（EcsRamRole 模式，不含静态密钥）--------------
if [ ! -f "$OSS_CONF" ]; then
    cat > "$OSS_CONF" <<'EOF'
[Credentials]
language=CH
endpoint=oss-cn-hangzhou.aliyuncs.com
mode=EcsRamRole
EOF
    chmod 600 "$OSS_CONF"
    log "已生成 ossutil 配置（EcsRamRole 模式）：$OSS_CONF"
fi

# --- 3. 连通性自检（角色没绑权限 / 桶不存在 / 网络不通都在这里暴露）--------
if ! "$OSSUTIL" ls "$OSS_TARGET" --config-file "$OSS_CONF" >/dev/null 2>&1; then
    log "无法访问 $OSS_TARGET。请检查：① RAM 角色是否已给该 Bucket 的读写权限 ② Bucket 名与地域是否正确（当前 endpoint=$(grep '^endpoint=' "$OSS_CONF" | cut -d= -f2)）"
    exit 1
fi

# --- 4. 执行同步 -----------------------------------------------------------
# 备份总量约 11MB/天，整目录推送的数据量很小，无需复杂的增量筛选。
if "$OSSUTIL" cp -rf "$BACKUP_DIR" "$OSS_TARGET" \
        --config-file "$OSS_CONF" --update -f -s >>"$LOG" 2>&1; then
    n=$(find "$BACKUP_DIR" -type f | wc -l)
    sz=$(du -sh "$BACKUP_DIR" | cut -f1)
    log "同步完成：本地 ${n} 个文件 / ${sz} → $OSS_TARGET"
    exit 0
else
    log "同步失败，详见 $LOG 末尾（不影响本机备份与业务）"
    exit 1
fi