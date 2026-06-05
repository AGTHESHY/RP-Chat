import os
from dotenv import load_dotenv

load_dotenv()

MYSQL_HOST = os.getenv("MYSQL_HOST", "127.0.0.1")
MYSQL_PORT = int(os.getenv("MYSQL_PORT", "3306"))
MYSQL_USER = os.getenv("MYSQL_USER", "root")
MYSQL_PASSWORD = os.getenv("MYSQL_PASSWORD", "root123")
MYSQL_DATABASE = os.getenv("MYSQL_DATABASE", "rp_chat")

REDIS_HOST = os.getenv("REDIS_HOST", "127.0.0.1")
REDIS_PORT = int(os.getenv("REDIS_PORT", "6380"))
REDIS_DB = int(os.getenv("REDIS_DB", "0"))
REDIS_PASSWORD = os.getenv("REDIS_PASSWORD") or None
REDIS_DRAFT_TTL_SECONDS = int(os.getenv("REDIS_DRAFT_TTL_SECONDS", str(7 * 24 * 3600)))

BASELINE_VERSIONS = frozenset({"v1", "v2"})
DRAFT_KEY_PREFIX = "rpchat:draft:"
BRAIN_KEY_PREFIX = "rpchat:brain:"
# 智脑历史默认 3 天过期；设为 0 则永不过期
REDIS_BRAIN_TTL_SECONDS = int(os.getenv("REDIS_BRAIN_TTL_SECONDS", str(3 * 24 * 3600)))
# 流式会话暂存默认 1 小时；设为 0 则永不过期
REDIS_STREAM_TTL_SECONDS = int(os.getenv("REDIS_STREAM_TTL_SECONDS", str(3600)))
STREAM_KEY_PREFIX = "rpchat:stream:"
STREAM_ACTIVE_PREFIX = "rpchat:stream:active:"
