import os
from dotenv import load_dotenv
from psycopg_pool import AsyncConnectionPool

load_dotenv()


class Config:
    # 鉴权
    AUTH_KEY = os.getenv("AUTH_KEY", "").strip()

    # LLM
    MODEL = os.getenv("MODEL")
    API_KEY = os.getenv("API_KEY", "")
    BASE_URL = os.getenv("BASE_URL")
    SYSTEM_PROMPT = os.getenv("SYSTEM_PROMPT", "你是一个有用的助手")
    MAX_INPUT_LENGTH = int(os.getenv("MAX_INPUT_LENGTH", "2000"))

    # 数据库
    DB_HOST = os.getenv("DB_HOST", "localhost")
    DB_PORT = int(os.getenv("DB_PORT", "5432"))
    DB_DATABASE = os.getenv("DB_DATABASE", "postgres")
    DB_USER = os.getenv("DB_USER", "postgres")
    DB_PASSWORD = os.getenv("DB_PASSWORD", "")

    # Embedding
    EMBEDDING_API_KEY = os.getenv("EMBEDDING_API_KEY", "")
    EMBEDDING_BASE_URL = os.getenv("EMBEDDING_BASE_URL", "")
    EMBEDDING_MODEL = os.getenv("EMBEDDING_MODEL", "")

    # RedFox
    REDFOX_API_KEY = os.getenv("REDFOX_API_KEY", "")
    SHOWAPI_APPKEY = os.getenv("SHOWAPI_APPKEY", "")

config = Config()


# 连接池的 conninfo 字符串
_pool_conninfo = (
    f"host={config.DB_HOST} "
    f"port={config.DB_PORT} "
    f"dbname={config.DB_DATABASE} "
    f"user={config.DB_USER} "
    f"password={config.DB_PASSWORD}"
)

# 全局连接池（还没打开，交给 main.py 启动时打开）
pool = AsyncConnectionPool(
    conninfo=_pool_conninfo,
    min_size=2,
    max_size=10,
    open=False
)