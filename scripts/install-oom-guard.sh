#!/usr/bin/env bash
# 安装 OOM 守护 systemd 服务（需 root）。
set -euo pipefail

if [[ "${EUID:-$(id -u)}" -ne 0 ]]; then
  echo "请使用 root 运行: sudo bash scripts/install-oom-guard.sh" >&2
  exit 1
fi

ROOT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
UNIT_SRC="$ROOT_DIR/deploy/systemd/rp-chat-oom-guard.service"
UNIT_DST="/etc/systemd/system/rp-chat-oom-guard.service"

chmod +x "$ROOT_DIR/scripts/oom-guard.sh"
chmod +x "$ROOT_DIR/scripts/docker-up-serial.sh"
chmod +x "$ROOT_DIR/scripts/docker-down-serial.sh"

sed "s|@PROJECT_ROOT@|$ROOT_DIR|g" "$UNIT_SRC" > "$UNIT_DST"

systemctl daemon-reload
systemctl enable rp-chat-oom-guard.service
systemctl restart rp-chat-oom-guard.service

echo "已安装并启动 rp-chat-oom-guard.service"
systemctl status rp-chat-oom-guard.service --no-pager || true
