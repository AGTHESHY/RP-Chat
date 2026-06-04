# 服务器部署 — MySQL 数据迁移

## 已导出的数据

| 文件 | 说明 |
|------|------|
| [`backup/rp_chat_dump.sql`](backup/rp_chat_dump.sql) | 完整库 `rp_chat`（表结构 + 数据） |
| [`backup/MANIFEST.json`](backup/MANIFEST.json) | 各表行数摘要 |

导出环境：本机 `mysql8` 容器，`127.0.0.1:3306`，库名 `rp_chat`。

### 数据概览（导出时）

| 表 | 行数 |
|----|------|
| prompt_versions | 2 |
| prompts | 8 |
| version_docs | 2 |
| jailbreak_prompts | 1 |
| prompt_test_results | 4 |
| rp_eval_results | 1 |
| chat_qa_cases | 119 |
| prompt_examples | 见 SQL |

---

## 重新导出（本地）

```bash
chmod +x deploy/scripts/export_mysql.sh
./deploy/scripts/export_mysql.sh
```

可通过环境变量覆盖连接：`MYSQL_HOST`、`MYSQL_PORT`、`MYSQL_USER`、`MYSQL_PASSWORD`、`MYSQL_DATABASE`。  
若本机无 `mysqldump`，脚本会尝试 `docker exec mysql8 mysqldump`（可设 `MYSQL_DOCKER_CONTAINER`）。

---

## 在服务器上恢复

### 1. 启动 MySQL

```bash
docker compose up -d mysql
# 或复用已有 MySQL 8.0
```

### 2. 创建库并导入

```bash
# 将 rp_chat_dump.sql 上传到服务器后：
mysql -h127.0.0.1 -P3306 -uroot -p -e "CREATE DATABASE IF NOT EXISTS rp_chat CHARACTER SET utf8mb4 COLLATE utf8mb4_unicode_ci;"
mysql -h127.0.0.1 -P3306 -uroot -p rp_chat < deploy/backup/rp_chat_dump.sql
```

Docker 示例：

```bash
docker exec -i rp-chat-mysql mysql -uroot -proot123 -e "CREATE DATABASE IF NOT EXISTS rp_chat CHARACTER SET utf8mb4 COLLATE utf8mb4_unicode_ci;"
docker exec -i rp-chat-mysql mysql -uroot -proot123 rp_chat < deploy/backup/rp_chat_dump.sql
```

### 3. 配置后端环境变量

与 [`server/config.py`](../server/config.py) 一致，例如：

```bash
export MYSQL_HOST=127.0.0.1
export MYSQL_PORT=3306
export MYSQL_USER=root
export MYSQL_PASSWORD=你的密码
export MYSQL_DATABASE=rp_chat
```

### 4. 构建前端（本地或 CI）

```bash
cd frontend && npm ci && npm run build
```

将 `frontend/dist/` 上传到服务器（例如 `/var/www/rp-chat/dist`）。

### 5. Nginx 静态托管 + API 反代

复制 [`nginx/rp-chat.conf`](nginx/rp-chat.conf)，修改 `root` 路径后：

```bash
sudo cp deploy/nginx/rp-chat.conf /etc/nginx/sites-available/rp-chat.conf
sudo ln -sf /etc/nginx/sites-available/rp-chat.conf /etc/nginx/sites-enabled/
sudo nginx -t && sudo systemctl reload nginx
```

生产环境**不需要**在服务器上运行 Node 或 `vite preview`；仅 Nginx 提供静态文件。

### 6. 启动 API（单进程，省内存）

```bash
cd server && pip install -r requirements-prod.txt
python -m uvicorn main:app --host 127.0.0.1 --port 8000
```

或使用 systemd 守护。勿默认多 worker，以免内存成倍增加。

后端启动时会执行 schema 迁移（`migrate_schema.py`），在**已有完整 dump** 的前提下通常无需再跑 seed；若表为空才会从 `seed_data/` 导入。

### 内存占用建议

| 组件 | 说明 |
|------|------|
| Nginx | 静态 `dist`，内存占用很低 |
| uvicorn | 单进程即可，推荐 `requirements-prod.txt` |
| MySQL / Redis | 独立服务，按数据量配置 |

---

## 注意

- **不要**把生产密码提交进 Git；`rp_chat_dump.sql` 仅含业务数据，不含连接密钥。
- 若服务器库中已有同名表，导入前请先备份或清空目标库，避免主键冲突。
- 前端构建产物在 `frontend/dist/`，部署时需单独 `npm run build` 并由 Nginx 或静态服务托管。
