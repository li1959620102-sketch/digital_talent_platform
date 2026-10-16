#!/bin/bash
# =============================================================================
# 备份恢复演练 —— 验证「备份是真的能还原的」
#
# 背景：没验证过的备份等于没有备份。本脚本起一个**临时独立 MySQL 容器**，
#       把最近一份备份原样灌进去，逐表核对行数与线上是否一致，最后销毁临时容器。
#       全程不碰线上容器、线上库、线上卷。
#
# 安全性：
#   · 临时容器名 restore_drill_mysql、临时卷 restore_drill_data，与业务完全隔离
#   · 只读线上备份文件，线上数据零风险
#   · 演练结束（含中途失败）自动清理临时容器与卷
#   · 磁盘占用：约 300MB，演练结束立即释放
#
# 用法：/opt/restore_drill.sh
# 退出码：0=行数全部一致；1=存在差异；2=演练无法执行
# =============================================================================
set -uo pipefail

BACKUP_DIR=/opt/backups
DRILL_CTN=restore_drill_mysql
DRILL_VOL=restore_drill_data
DRILL_PW=drill_only_not_prod
LOG=/var/log/backup.log

log() { echo "[$(date '+%F %T')] [演练] $*" | tee -a "$LOG"; }

cleanup() {
    docker rm -f "$DRILL_CTN" >/dev/null 2>&1
    docker volume rm "$DRILL_VOL" >/dev/null 2>&1
    log "临时容器与卷已清理"
}
trap cleanup EXIT

# --- 1. 找最新一份 MySQL 备份 ---------------------------------------------
BAK=$(ls -t "$BACKUP_DIR"/mysql_*.sql.gz 2>/dev/null | head -1)
if [ -z "$BAK" ]; then
    log "找不到备份文件，无法演练"; exit 2
fi
log "使用备份：$(basename "$BAK")（$(du -h "$BAK" | cut -f1)）"

# --- 2. 起临时 MySQL --------------------------------------------------------
cleanup
docker run -d --name "$DRILL_CTN" \
    -e MYSQL_ROOT_PASSWORD="$DRILL_PW" \
    -v "$DRILL_VOL":/var/lib/mysql \
    mysql:8.0 >/dev/null || { log "临时容器启动失败"; exit 2; }

log "等待临时 MySQL 就绪…"
# 注意：不能用 `mysqladmin ping` 判就绪 —— 它在「服务器已应答但鉴权失败」时也返回 0
# （MySQL 客户端的已知行为），而官方镜像初始化期间正好处于这个状态，会导致刚启动就去连、
# 拿到 Access denied。这里必须用真正带鉴权的查询来判定。
ready=0
for i in $(seq 1 90); do
    if docker exec "$DRILL_CTN" mysql -uroot -p"$DRILL_PW" -N -B \
            -e "SELECT 1;" >/dev/null 2>&1; then
        log "临时 MySQL 就绪并鉴权成功（${i}s）"; ready=1; break
    fi
    sleep 1
done
if [ "$ready" -ne 1 ]; then log "等待就绪超时（90s）"; exit 2; fi

# --- 3. 灌入备份（原样，不改库名）------------------------------------------
log "开始恢复…"
if ! gunzip -c "$BAK" | docker exec -i "$DRILL_CTN" \
        mysql -uroot -p"$DRILL_PW" --default-character-set=utf8mb4 2>/dev/null; then
    log "恢复失败：dump 执行报错"
    # 复现一次并保留报错原文，便于定位
    gunzip -c "$BAK" | docker exec -i "$DRILL_CTN" \
        mysql -uroot -p"$DRILL_PW" --default-character-set=utf8mb4 2>&1 \
        | grep -v 'password on the command line' | head -5 | tee -a "$LOG"
    exit 2
fi
log "恢复完成"

# --- 4. 逐表核对行数 -------------------------------------------------------
dump_q() { # $1=容器 $2=sql
    docker exec "$1" mysql -uroot -p"$DRILL_PW" -N -B -e "$2" 2>/dev/null
}

TABLES=$(dump_q "$DRILL_CTN" \
    "SELECT table_name FROM information_schema.tables
     WHERE table_schema='digital_talent' AND table_name<>'alembic_version' ORDER BY table_name;")
TBL_COUNT=$(echo "$TABLES" | grep -c .)
log "演练库建出业务表 ${TBL_COUNT} 张，开始逐表比对…"

diff_cnt=0
skip_cnt=0
# audit_logs 是只追加的审计表：备份是某一时刻的快照，之后每有一次登录/写操作
# 线上就会多几行，因此「演练库 ≤ 线上」属正常，不算不一致。
# 其余业务表是严格状态，行数必须完全相等，少一行都说明丢数据。
# 注意：必须用 case 做匹配 —— `[ "$A" = *" $t "* ]` 里的 test 命令只做
#       纯字符串比较、不识别通配符，会永远判为「未命中」。
APPEND_ONLY=" audit_logs "

printf '%-28s %-10s %-10s %s\n' "表名" "线上" "演练库" "结果"
printf '%.0s-' {1..62}; echo

for t in $TABLES; do
    drill=$(dump_q "$DRILL_CTN" "SELECT COUNT(*) FROM digital_talent.\`$t\`;")
    # 直接连线上容器数可能因密码转义失败，失败时标为 NA 而非误判差异
    prod=$(docker exec digital_talent_mysql sh -c \
           "exec mysql -uroot -p\"\$MYSQL_ROOT_PASSWORD\" -N -B \
            -e 'SELECT COUNT(*) FROM digital_talent.\`$t\`;'" 2>/dev/null)
    is_append=0
    case "$APPEND_ONLY" in
        *" $t "*) is_append=1 ;;
    esac

    if [ -z "$prod" ]; then
        result="SKIP(线上读取失败)"; skip_cnt=$((skip_cnt+1))
    elif [ "$prod" = "$drill" ]; then
        result="一致"
    elif [ "$is_append" -eq 1 ] && [ "$drill" -le "$prod" ]; then
        result="一致(线上新增 $((prod - drill)) 行，属只追加表的正常增长)"
    else
        result="** 不一致 **"; diff_cnt=$((diff_cnt+1))
    fi
    printf '%-28s %-10s %-10s %s\n' "$t" "${prod:-NA}" "$drill" "$result"
done

echo
if [ "$diff_cnt" -eq 0 ] && [ "$skip_cnt" -eq 0 ]; then
    log "演练通过：${TBL_COUNT} 张表行数与线上逐项一致，备份可信"
    exit 0
elif [ "$diff_cnt" -eq 0 ]; then
    log "演练基本通过：0 处不一致，但有 ${skip_cnt} 张表未能读取线上行数（需人工确认）"
    exit 1
else
    log "演练失败：${diff_cnt} 张表行数不一致，备份不可信！"
    exit 1
fi