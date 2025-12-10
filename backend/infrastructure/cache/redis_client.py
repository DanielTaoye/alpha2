"""Redis 客户端封装"""
import json
import redis
from typing import Optional
from infrastructure.config.redis_config import REDIS_CONFIG, KEY_PREFIX
from infrastructure.logging.logger import get_logger

logger = get_logger(__name__)


class RedisClient:
    """简易Redis客户端（单例）"""

    _instance: Optional["RedisClient"] = None

    def __init__(self):
        self._client = redis.Redis(
            host=REDIS_CONFIG["host"],
            port=REDIS_CONFIG["port"],
            db=REDIS_CONFIG.get("db", 0),
            password=REDIS_CONFIG.get("password"),
            decode_responses=REDIS_CONFIG.get("decode_responses", True),
            socket_timeout=REDIS_CONFIG.get("socket_timeout", 5),
        )

    @classmethod
    def instance(cls) -> "RedisClient":
        if cls._instance is None:
            cls._instance = cls()
        return cls._instance

    @property
    def client(self) -> redis.Redis:
        return self._client

    @staticmethod
    def full_key(key: str) -> str:
        return f"{KEY_PREFIX}:{key}"

    def set_json(self, key: str, value, ex: int = None):
        """存储JSON序列化后的字符串"""
        return self._client.set(self.full_key(key), json.dumps(value, ensure_ascii=False), ex=ex)

    def get_json(self, key: str):
        val = self._client.get(self.full_key(key))
        if not val:
            return None
        try:
            return json.loads(val)
        except Exception:
            return None

