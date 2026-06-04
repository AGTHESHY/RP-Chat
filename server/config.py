import os

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
