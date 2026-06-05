# RP Chat 提示词管理与测试

Vue 3 + FastAPI 全栈应用，用于浏览 v1/v2 提示词、查看版本文档，并在线测试 Segment 压缩 / History 合并 API。

## 目录

- `server/` — FastAPI 后端
- `frontend/` — Vue 3 前端
- `docker-compose.yml` — 全栈 Docker（MySQL、Redis、Backend、Frontend）
- `docker-compose.lowmem.yml` — 2GB 内存环境的资源限制
- `scripts/docker-up-serial.sh` — **推荐**：串行构建并启动
- `scripts/docker-down-serial.sh` — 串行停止
- `scripts/oom-guard.sh` — OOM 监控，自动停服并重启 SSH
- `scripts/install-oom-guard.sh` — 安装 OOM 守护为 systemd 服务

## Docker 全栈部署（推荐）

适用于 Linux 服务器（含 2GB 内存 Ubuntu）。**无需在宿主机安装 Python / Node / Conda**。

### 1. 串行启动（低内存必用）

```bash
cd /opt/RP-Chat
chmod +x scripts/docker-up-serial.sh scripts/docker-down-serial.sh
bash scripts/docker-up-serial.sh
```

按顺序执行：**构建 backend → 构建 frontend → MySQL → Redis → Backend → Frontend**，并自动加载 `docker-compose.lowmem.yml`。

浏览器访问：**http://\<服务器IP\>:8080**

跳过重新构建（镜像已存在时）：

```bash
BUILD=0 bash scripts/docker-up-serial.sh
```

### 2. 停止服务

```bash
bash scripts/docker-down-serial.sh
```

### 3. OOM 保护（2GB 服务器强烈建议）

当检测到 **内核 OOM** 或 **RP-Chat 容器被 OOM Kill** 时，自动：

1. 停止 RP-Chat 全部 Docker 服务（**不影响**其他项目的容器）
2. 重启 SSH，避免 OOM 后无法远程登录

可选：设置 `ENABLE_MEM_PRESSURE=1` 时，可用内存低于 `MIN_MEM_KB`（默认 32MB）也会 preemptive 停服。

```bash
sudo bash scripts/install-oom-guard.sh
```

查看日志：

```bash
tail -f /var/log/rp-chat-oom-guard.log
systemctl status rp-chat-oom-guard
```

可调环境变量（写入 systemd unit 或 export 后重启服务）：

| 变量 | 默认 | 说明 |
|------|------|------|
| `ENABLE_MEM_PRESSURE` | `0` | 设为 `1` 启用可用内存过低 preemptive 停服 |
| `MIN_MEM_KB` | `32768` | 启用 mem pressure 时的阈值（KB） |
| `CHECK_INTERVAL` | `10` | 检测间隔（秒） |
| `COOLDOWN_SECONDS` | `300` | 触发后冷却时间（秒） |

### 4. 内存预算（lowmem 模式）

| 服务 | 上限 |
|------|------|
| MySQL | 384MB |
| Redis | 128MB |
| Backend | 320MB |
| Frontend (nginx) | 48MB |

建议额外配置 **1GB swap**，首次 `docker-up-serial.sh` 构建 frontend 时更稳。

### 5. 常规并行启动（内存充足）

```bash
docker compose up -d --build
```

## 本地开发（非 Docker）

### 数据库

提示词、版本文档、对话问答与 Prompt 示例均存储在 MySQL 中。首次启动且对应表为空时，会从 `server/seed_data/` 自动导入初始数据。

| 配置 | Docker 默认值 |
|------|---------------|
| MySQL Host | `127.0.0.1:3306` |
| Redis Host | `127.0.0.1:6380` |
| User / Password | `root` / `root123` |
| Database | `rp_chat` |

本地开发可复制 `server/.env`，连接 Docker 中的 MySQL/Redis：

```env
MYSQL_HOST=127.0.0.1
MYSQL_PORT=3306
MYSQL_USER=root
MYSQL_PASSWORD=root123
MYSQL_DATABASE=rp_chat
REDIS_HOST=127.0.0.1
REDIS_PORT=6380
REDIS_PASSWORD=
```

### 后端

```bash
cd server
pip install -r requirements.txt
python -m uvicorn main:app --reload --port 8000
```

### 前端

```bash
cd frontend
npm install
npm run dev
```

浏览器打开 [http://localhost:5173](http://localhost:5173)

## 功能概览

- **提示词管理**：切换 v1/v2，查看 MD 文档与 SP 正文
- **测试用例**：「对话问答」选会话作为测试输入；「Prompt 用例」查看已保存的期望输出
- **测试**：配置 API 参数，运行 Segment 压缩 / History 合并
- **智脑**：智脑历史保存在 Redis（默认 3 天过期）；测评记录在 MySQL

API 配置保存在浏览器 `localStorage`，不会写入仓库。

## API 端点

| 方法 | 路径 | 说明 |
|------|------|------|
| GET | `/api/versions/{version}/prompts/{type}/{lang}` | 获取版本提示词 |
| GET | `/api/versions/{version}/docs` | 获取版本 MD 文档 |
| PUT | `/api/versions/{version}/docs` | 更新版本文档 |
| GET | `/api/prompt-test-results` | 列出 Prompt 期望结果 |
| POST | `/api/prompt-test-results` | 保存测试期望结果 |
| POST | `/api/chat/completions` | 代理 OpenAI 兼容 Chat API |
