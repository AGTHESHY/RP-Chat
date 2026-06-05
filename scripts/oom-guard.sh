#!/usr/bin/env bash
# 监控 OOM / 极低可用内存，自动停止 RP-Chat Docker 栈并重启 SSH，防止整机卡死。
set -euo pipefail

# shellcheck disable=SC1091
source "$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)/lib/compose.sh"

LOG_FILE="${LOG_FILE:-/var/log/rp-chat-oom-guard.log}"
STATE_DIR="${STATE_DIR:-/var/run/rp-chat-oom-guard}"
COOLDOWN_FILE="$STATE_DIR/last_action"
CHECK_INTERVAL="${CHECK_INTERVAL:-10}"
COOLDOWN_SECONDS="${COOLDOWN_SECONDS:-300}"
MIN_MEM_KB="${MIN_MEM_KB:-32768}"
ENABLE_MEM_PRESSURE="${ENABLE_MEM_PRESSURE:-0}"

RP_CONTAINERS=(rp-chat-frontend rp-chat-backend rp-chat-redis rp-chat-mysql)

mkdir -p "$STATE_DIR"
touch "$LOG_FILE"

log() {
  echo "$(date -Is) $*" | tee -a "$LOG_FILE"
}

in_cooldown() {
  [[ ! -f "$COOLDOWN_FILE" ]] && return 1
  local last now
  last="$(cat "$COOLDOWN_FILE")"
  now="$(date +%s)"
  (( now - last < COOLDOWN_SECONDS ))
}

mark_action() {
  date +%s > "$COOLDOWN_FILE"
}

restart_ssh() {
  if systemctl restart ssh 2>/dev/null; then
    log "已重启 ssh 服务"
    return 0
  fi
  if systemctl restart sshd 2>/dev/null; then
    log "已重启 sshd 服务"
    return 0
  fi
  log "警告: 无法重启 SSH（请检查 systemd 单元名）"
  return 1
}

stop_rp_chat_stack() {
  log "正在停止 RP-Chat Docker 服务 ..."
  "${COMPOSE[@]}" stop frontend backend redis mysql 2>>"$LOG_FILE" || true
  log "RP-Chat Docker 服务已停止"
}

handle_emergency() {
  local reason="$1"
  if in_cooldown; then
    log "冷却中，跳过: $reason"
    return 0
  fi
  log "触发保护: $reason"
  mark_action
  stop_rp_chat_stack
  restart_ssh || true
}

check_kernel_oom() {
  if journalctl -k --since "${CHECK_INTERVAL} seconds ago" --no-pager 2>/dev/null \
    | grep -qiE 'out of memory|oom-kill|invoked oom-killer|Killed process'; then
    return 0
  fi
  if dmesg -T 2>/dev/null | tail -30 | grep -qiE 'out of memory|oom-kill|invoked oom-killer'; then
    return 0
  fi
  return 1
}

check_mem_pressure() {
  local avail
  avail="$(awk '/^MemAvailable:/ {print $2}' /proc/meminfo)"
  [[ -n "$avail" && "$avail" -lt "$MIN_MEM_KB" ]]
}

check_container_oom() {
  local container oom id handled_file
  for container in "${RP_CONTAINERS[@]}"; do
    if ! docker inspect "$container" >/dev/null 2>&1; then
      continue
    fi
    oom="$(docker inspect -f '{{.State.OOMKilled}}' "$container" 2>/dev/null || echo false)"
    [[ "$oom" != "true" ]] && continue
    id="$(docker inspect -f '{{.Id}}' "$container")"
    handled_file="$STATE_DIR/handled-oom-${container}"
    if [[ -f "$handled_file" ]] && [[ "$(cat "$handled_file")" == "$id" ]]; then
      continue
    fi
    echo "$id" > "$handled_file"
    return 0
  done
  return 1
}

log "OOM Guard 启动 (interval=${CHECK_INTERVAL}s, mem_pressure=${ENABLE_MEM_PRESSURE}, min_mem=${MIN_MEM_KB}KB, cooldown=${COOLDOWN_SECONDS}s)"

while true; do
  if check_kernel_oom; then
    handle_emergency "检测到内核 OOM 日志"
  elif check_container_oom; then
    handle_emergency "检测到 RP-Chat 容器被 OOM Kill"
  elif [[ "$ENABLE_MEM_PRESSURE" == "1" ]] && check_mem_pressure; then
    handle_emergency "可用内存低于 ${MIN_MEM_KB}KB"
  fi
  sleep "$CHECK_INTERVAL"
done
