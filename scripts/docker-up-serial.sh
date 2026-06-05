#!/usr/bin/env bash
# 低内存环境串行构建并启动全栈：MySQL → Redis → Backend → Frontend
set -euo pipefail

# shellcheck disable=SC1091
source "$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)/lib/compose.sh"

BUILD="${BUILD:-1}"

wait_healthy() {
  local container="$1"
  local timeout="${2:-180}"
  local elapsed=0

  echo "等待 ${container} 就绪..."
  while (( elapsed < timeout )); do
    local status
    status="$(docker inspect -f '{{if .State.Health}}{{.State.Health.Status}}{{else}}none{{end}}' "$container" 2>/dev/null || echo missing)"
    if [[ "$status" == "healthy" ]]; then
      echo "${container} 已就绪"
      return 0
    fi
    if [[ "$status" == "unhealthy" ]]; then
      echo "错误: ${container} 健康检查失败" >&2
      docker logs --tail 50 "$container" >&2 || true
      return 1
    fi
    sleep 2
    elapsed=$((elapsed + 2))
  done

  echo "错误: 等待 ${container} 超时（${timeout}s）" >&2
  return 1
}

if [[ "$BUILD" == "1" ]]; then
  echo "==> 构建 backend 镜像"
  "${COMPOSE[@]}" build backend
  echo "==> 构建 frontend 镜像"
  "${COMPOSE[@]}" build frontend
fi

echo "==> 1/4 启动 MySQL"
"${COMPOSE[@]}" up -d mysql
wait_healthy rp-chat-mysql 240

echo "==> 2/4 启动 Redis"
"${COMPOSE[@]}" up -d redis
wait_healthy rp-chat-redis 60

echo "==> 3/4 启动 Backend"
"${COMPOSE[@]}" up -d backend
wait_healthy rp-chat-backend 180

echo "==> 4/4 启动 Frontend"
"${COMPOSE[@]}" up -d frontend
wait_healthy rp-chat-frontend 60

echo ""
echo "全部服务已串行启动完成。"
echo "访问: http://<服务器IP>:8080"
"${COMPOSE[@]}" ps
