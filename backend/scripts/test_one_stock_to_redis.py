"""
测试：取1只股票，通过本地接口 /api/latest_cr_points 获取分数并写入 Redis。
运行方式：
    cd backend
    python scripts/test_one_stock_to_redis.py
"""

import json
import sys
from datetime import datetime

import requests

from application.services.high_score_cache_service import HighScoreCacheService
from infrastructure.cache.redis_client import RedisClient


def main():
    # 选第一只股票
    svc = HighScoreCacheService(max_workers=1)
    stocks = svc._get_all_active_stocks()
    if not stocks:
        print("no stocks")
        return

    stock = stocks[0]
    print("use stock:", stock)

    # 调接口获取最新分数
    payload = {"stockCode": stock["code"], "tableName": stock["table_name"]}
    try:
        resp = requests.post(
            "http://localhost:5000/api/latest_cr_points",
            json=payload,
            timeout=60,
        )
        print("http status:", resp.status_code)
        data = resp.json()
    except Exception as e:
        print("http error:", e)
        return

    print("resp keys:", list(data.keys()) if isinstance(data, dict) else type(data))

    if not (isinstance(data, dict) and data.get("code") == 200 and data.get("data", {}).get("success")):
        print("calc failed:", data)
        return

    res = data["data"]
    s1_score = res.get("strategy1", {}).get("score", 0) or 0
    s2_score = res.get("strategy2", {}).get("score", 0) or 0
    date_str = res.get("date") or datetime.now().strftime("%Y-%m-%d")
    s1 = svc.config_service.get_strategy1_threshold()
    s2 = svc.config_service.get_strategy2_threshold()
    is_high = 1 if (s1_score >= s1 and s2_score >= s2) else 0
    total = max(s1_score, s2_score)

    item = {
        "stock_code": stock["code"],
        "stock_name": stock.get("name", ""),
        "nature": stock.get("nature", "波段"),
        "strategy1_score": round(s1_score, 2),
        "strategy2_score": round(s2_score, 2),
        "total_score": round(total, 2),
        "is_high_score": is_high,
        "date": date_str,
    }

    # 写入 Redis
    zkey = RedisClient.full_key("high_score:zset")
    mkey = RedisClient.full_key("high_score:meta")
    r = RedisClient.instance().client
    r.delete(zkey)
    r.delete(mkey)
    r.zadd(zkey, {json.dumps(item, ensure_ascii=False): item["total_score"]})
    meta = {
        "total_stocks": 1,
        "calculated": 1,
        "high_score_count": 1 if is_high else 0,
        "refreshed_at": datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
        "strategy1_threshold": s1,
        "strategy2_threshold": s2,
    }
    r.set(mkey, json.dumps(meta, ensure_ascii=False))

    print("write redis done")
    print("zcard:", r.zcard(zkey))
    print("top:", r.zrevrange(zkey, 0, 2, withscores=True))
    print("meta:", r.get(mkey))
    print("item:", item)


if __name__ == "__main__":
    sys.exit(main())

