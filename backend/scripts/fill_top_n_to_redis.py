"""
批量计算前N只股票分数并写入Redis排行榜。

用法：
    cd backend
    # 默认计算前30只，线程20
    PYTHONPATH=. python scripts/fill_top_n_to_redis.py

    # 指定数量和线程
    PYTHONPATH=. python scripts/fill_top_n_to_redis.py 50 30
"""

import json
import sys
from datetime import datetime
from concurrent.futures import ThreadPoolExecutor, as_completed

from application.services.high_score_cache_service import HighScoreCacheService
from infrastructure.cache.redis_client import RedisClient


def main():
    # 命令行参数：数量、线程数
    try:
        top_n = int(sys.argv[1]) if len(sys.argv) > 1 else 59  # 默认刷新59只已配置股票
    except ValueError:
        top_n = 59
    try:
        max_workers = int(sys.argv[2]) if len(sys.argv) > 2 else 20
    except ValueError:
        max_workers = 20

    svc = HighScoreCacheService(max_workers=max_workers)
    stocks = svc._get_all_active_stocks()
    if not stocks:
        print("⚠️ 无股票数据")
        return

    stocks = stocks[:top_n]
    print(f"🚀 开始计算前 {top_n} 只股票，线程 {max_workers}")

    s1 = svc.config_service.get_strategy1_threshold()
    s2 = svc.config_service.get_strategy2_threshold()

    results = []
    high = []

    with ThreadPoolExecutor(max_workers=max_workers) as executor:
        future_map = {
            executor.submit(svc._calc_score_safe, st, s1, s2): st for st in stocks
        }
        for fut in as_completed(future_map):
            st = future_map[fut]
            try:
                r = fut.result()
                if r:
                    results.append(r)
                    if r.get("is_high_score"):
                        high.append(r)
            except Exception as e:
                print(f"❌ {st['code']} 计算失败: {e}")

    # 流式写入Redis：算完一条写一条（先清空旧榜）
    zkey = RedisClient.full_key("high_score:zset")
    mkey = RedisClient.full_key("high_score:meta")
    rds = RedisClient.instance().client
    rds.delete(zkey)
    rds.delete(mkey)

    for item in results:
        member = json.dumps(item, ensure_ascii=False)
        rds.zadd(zkey, {member: item.get("total_score", 0)})

    meta = {
        "total_stocks": len(stocks),
        "calculated": len(results),
        "high_score_count": len([x for x in results if x.get("is_high_score")]),
        "refreshed_at": datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
        "strategy1_threshold": s1,
        "strategy2_threshold": s2,
    }
    rds.set(mkey, json.dumps(meta, ensure_ascii=False))

    print("✅ 写入完成")
    print(f"📊 总计算 {len(results)} 条，高分 {meta['high_score_count']} 条")
    print(f"🏆 ZSET 总数: {rds.zcard(zkey)}")
    top = rds.zrevrange(zkey, 0, 9, withscores=True)
    if top:
        print("前10示例:")
        for i, (member, score) in enumerate(top, 1):
            try:
                item = json.loads(member)
                print(f"{i}. {item.get('stock_code')} {item.get('stock_name')} 分:{score}")
            except Exception:
                print(f"{i}. {member} 分:{score}")


if __name__ == "__main__":
    main()



