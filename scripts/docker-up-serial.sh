#!/usr/bin/env bash
# 低内存环境（如 2GB Ubuntu）串行启动 Docker 服务，避免 mysql + redis 同时拉起导致 OOM。
set -euo pipefail

ROOT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
cd "$ROOT_DIR"

COMPOSE=(docker compose -f docker-compose.yml)
if [[ -f docker-compose.lowmem.yml ]]; then
  COMPOSE+=(-f docker-compose.lowmem.yml)
fi

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

echo "==> 1/2 启动 MySQL"
"${COMPOSE[@]}" up -d mysql
wait_healthy rp-chat-mysql 240

echo "==> 2/2 启动 Redis"
"${COMPOSE[@]}" up -d redis
wait_healthy rp-chat-redis 60

echo ""
echo "全部服务已串行启动完成："
"${COMPOSE[@]}" ps
