#!/usr/bin/env bash
# 按相反顺序停止 RP-Chat 全栈，释放内存。
set -euo pipefail

# shellcheck disable=SC1091
source "$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)/lib/compose.sh"

echo "停止 Frontend → Backend → Redis → MySQL ..."
"${COMPOSE[@]}" stop frontend backend redis mysql 2>/dev/null || true

echo "RP-Chat 服务已停止。"
"${COMPOSE[@]}" ps -a 2>/dev/null || true
