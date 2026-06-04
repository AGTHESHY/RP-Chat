#!/usr/bin/env bash
# 导出 rp_chat 数据库到 deploy/backup/rp_chat_dump.sql
set -euo pipefail

ROOT="$(cd "$(dirname "$0")/../.." && pwd)"
OUT_DIR="$ROOT/deploy/backup"
OUT_FILE="$OUT_DIR/rp_chat_dump.sql"

MYSQL_HOST="${MYSQL_HOST:-127.0.0.1}"
MYSQL_PORT="${MYSQL_PORT:-3306}"
MYSQL_USER="${MYSQL_USER:-root}"
MYSQL_PASSWORD="${MYSQL_PASSWORD:-root123}"
MYSQL_DATABASE="${MYSQL_DATABASE:-rp_chat}"

mkdir -p "$OUT_DIR"
STAMP="$(date +%Y%m%d_%H%M%S)"
STAMPED="$OUT_DIR/rp_chat_dump_${STAMP}.sql"

dump_via_client() {
  mysqldump -h"$MYSQL_HOST" -P"$MYSQL_PORT" -u"$MYSQL_USER" -p"$MYSQL_PASSWORD" \
    --single-transaction --routines --triggers --set-gtid-purged=OFF \
    --default-character-set=utf8mb4 \
    "$MYSQL_DATABASE" >"$1"
}

dump_via_docker() {
  local container="${MYSQL_DOCKER_CONTAINER:-mysql8}"
  docker exec "$container" mysqldump -u"$MYSQL_USER" -p"$MYSQL_PASSWORD" \
    --single-transaction --routines --triggers --set-gtid-purged=OFF \
    --default-character-set=utf8mb4 \
    "$MYSQL_DATABASE" >"$1"
}

if command -v mysqldump >/dev/null 2>&1; then
  dump_via_client "$OUT_FILE"
elif docker ps --format '{{.Names}}' | grep -q '^mysql8$'; then
  dump_via_docker "$OUT_FILE"
elif docker ps --format '{{.Names}}' | grep -q '^rp-chat-mysql$'; then
  MYSQL_DOCKER_CONTAINER=rp-chat-mysql dump_via_docker "$OUT_FILE"
else
  echo "未找到 mysqldump 或运行中的 MySQL 容器（mysql8 / rp-chat-mysql）" >&2
  exit 1
fi

cp "$OUT_FILE" "$STAMPED"
echo "已导出: $OUT_FILE"
echo "备份副本: $STAMPED"
wc -c "$OUT_FILE"
