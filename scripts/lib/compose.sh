# shellcheck shell=bash
# 被其他脚本 source，设置 COMPOSE 数组与 RP_CHAT_ROOT。
RP_CHAT_ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/../.." && pwd)"
cd "$RP_CHAT_ROOT"

COMPOSE=(docker compose -f docker-compose.yml)
if [[ -f docker-compose.lowmem.yml ]]; then
  COMPOSE+=(-f docker-compose.lowmem.yml)
fi
