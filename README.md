# RP Chat 提示词管理与测试

Vue 3 + FastAPI 全栈应用，用于浏览 v1/v2 提示词、查看版本文档，并在线测试 Segment 压缩 / History 合并 API。

## 目录

- `server/` — FastAPI 后端（提示词、测试用例存储在 MySQL）
- `frontend/` — Vue 3 前端
- `docker-compose.yml` — MySQL 8.0（端口 3306）、Redis 7（端口 6380）
- `docker-compose.lowmem.yml` — 2GB 内存环境的资源限制与精简配置
- `scripts/docker-up-serial.sh` — 低内存环境串行启动脚本

## 数据库

提示词、版本文档、对话问答与 Prompt 示例均存储在 MySQL 中。首次启动且对应表为空时，会从 `server/seed_data/` 自动导入初始数据。

每条提示词拆为：

- `content_sfw`：主体内容，在原先 NSFW 规则位置保留 `{{NSFW}}` 占位符
- `content_nsfw`：NSFW 段落（多条以 `---NSFW_PART---` 分隔），拼接时按占位符顺序插入

最终 System Prompt = SFW + NSFW 拼接；测试页可开关 NSFW 段落。


| 配置       | 默认值         |
| -------- | ----------- |
| Host     | `127.0.0.1` |
| Port     | `3306`      |
| User     | （自己设置）      |
| Password | （自己设置）      |
| Database | `rp_chat`   |


可通过环境变量覆盖：`MYSQL_HOST`、`MYSQL_PORT`、`MYSQL_USER`、`MYSQL_PASSWORD`、`MYSQL_DATABASE`。

### 启动 MySQL + Redis（Docker）

**常规环境**（内存充足，可并行启动）：

```bash
docker compose up -d
```

**低内存环境**（如 2GB Ubuntu，建议串行启动，避免同时拉镜像/初始化导致 OOM）：

```bash
chmod +x scripts/docker-up-serial.sh
bash scripts/docker-up-serial.sh
```

脚本会按顺序执行：先启动并等待 MySQL 就绪，再启动 Redis；并自动加载 `docker-compose.lowmem.yml` 中的内存限制与精简参数。

若需手动分步：

```bash
docker compose -f docker-compose.yml -f docker-compose.lowmem.yml up -d mysql
# 等待 MySQL 健康后再执行
docker compose -f docker-compose.yml -f docker-compose.lowmem.yml up -d redis
```

后端启动时会自动建表（若不存在）。

## 启动

### 1. 后端

先确保 MySQL 已运行，再启动 API：

**注意：** 依赖文件在 `server/requirements.txt`，不在项目根目录。

```bash
cd server
pip install -r requirements.txt
python -m uvicorn main:app --reload --port 8000
```

或在**项目根目录**直接运行：

```bash
python run_server.py
```

若 `pip` 找不到，任选其一：

```bash
# 方式 A：用 python -m pip（推荐）
python -m pip install -r requirements.txt

# 方式 B：先回到 base 环境（已有 Python/pip）
conda activate base
cd server && pip install -r requirements.txt
```

若你刚用 `conda create -n RP` 创建了空环境，里面**还没有 Python 和 pip**，需先安装：

```bash
conda activate RP
conda install -y python=3.11 pip -c defaults --override-channels
cd server
pip install -r requirements.txt
python -m uvicorn main:app --reload --port 8000
```

若 `conda install` 因清华镜像 403 失败，务必加上 `-c defaults --override-channels` 改用官方源。

### 2. 前端

需要先安装 Node.js（含 npm）。若终端里 `npm` 找不到，可在 `RP` 环境里安装：

```bash
conda activate RP
conda install -y nodejs -c defaults --override-channels
```

然后：

```bash
cd frontend
npm install
npm run dev
```

浏览器打开 [http://localhost:5173](http://localhost:5173)

- **提示词管理**：切换 v1/v2，查看 MD 文档与 SP 正文
- **测试用例**：「对话问答」选会话作为测试输入；「Prompt 用例」查看已保存的期望输出
- **测试**：配置 API 参数，在对话问答选中会话后运行 Segment 压缩 / History 合并
- **智脑**：基于 RP 测评历史与被测 SP 版本，分析建议小版本（同基线 fork）或大版本（切换 v1/v2 基线）更迭；**智脑历史**保存在 Redis（默认 **3 天**过期，可用环境变量 `REDIS_BRAIN_TTL_SECONDS` 覆盖），测评记录仍在 MySQL、可在「测评历史」Tab 删除

API 配置保存在浏览器 `localStorage`，不会写入仓库。

## API 端点


| 方法   | 路径                                              | 说明                    |
| ---- | ----------------------------------------------- | --------------------- |
| GET  | `/api/versions/{version}/prompts/{type}/{lang}` | 获取版本提示词（MySQL）        |
| GET  | `/api/versions/{version}/docs`                  | 获取版本 MD 文档            |
| PUT  | `/api/versions/{version}/docs`                  | 更新版本文档（草稿，写入 MySQL）   |
| GET  | `/api/prompt-test-results`                      | 列出已保存的 Prompt 期望结果    |
| GET  | `/api/prompt-test-results/{id}`                 | 获取期望结果详情              |
| POST | `/api/prompt-test-results`                      | 保存测试期望结果              |
| POST | `/api/chat/completions`                         | 代理 OpenAI 兼容 Chat API |


