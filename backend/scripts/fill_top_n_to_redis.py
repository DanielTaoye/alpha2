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
import os
from pathlib import Path
from datetime import datetime
from concurrent.futures import ThreadPoolExecutor, as_completed

from application.services.high_score_cache_service import HighScoreCacheService
from infrastructure.cache.redis_client import RedisClient
def load_stocks_from_config():
    """
    优先从配置文件加载 59 支股票列表（避免数据库只有少量记录导致榜单空）。
    文件：backend/infrastructure/config/stock_config.json
    """
    # 允许通过环境变量覆盖路径
    env_path = os.getenv("STOCK_CONFIG_PATH")
    if env_path:
        config_path = Path(env_path).expanduser().resolve()
    else:
        config_path = Path(__file__).resolve().parent.parent / "infrastructure" / "config" / "stock_config.json"

    if not config_path.exists():
        print(f"⚠️ 未找到配置文件: {config_path}")
        return []

    try:
        with config_path.open("r", encoding="utf-8") as f:
            data = json.load(f)
    except Exception:
        print(f"⚠️ 读取配置文件失败: {config_path}")
        return []

    stocks = []
    for nature, stock_list in data.items():
        for stock in stock_list:
            code = stock.get("code")
            name = stock.get("name", "")
            table = stock.get("table")
            table_name = table or f"basic_data_{code.lower()}" if code else ""
            if not code or not table_name:
                continue
            stocks.append({
                "code": code,
                "name": name,
                "nature": nature,
                "table_name": table_name,
            })
    return stocks



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

    # 先用配置文件的59支列表，避免数据库只有少量记录
    stocks = load_stocks_from_config()
    if stocks:
        print(f"✅ 从配置文件加载到 {len(stocks)} 只股票")
    else:
        print("⚠️ 配置文件未加载到股票，改用数据库 all_stock")
        stocks = svc._get_all_active_stocks()

    if not stocks:
        print("⚠️ 无股票数据")
        return

    # 按 top_n 截取
    stocks = stocks[:top_n]
    print(f"🚀 开始计算前 {len(stocks)} 只股票，线程 {max_workers}")

    s1 = svc.config_service.get_strategy1_threshold()
    s2 = svc.config_service.get_strategy2_threshold()

    results = []
    high = []

    # 流式写入：先清空，随后每完成一只就写入Redis
    zkey = RedisClient.full_key("high_score:zset")
    mkey = RedisClient.full_key("high_score:meta")
    rds = RedisClient.instance().client
    rds.delete(zkey)
    rds.delete(mkey)

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
                    # 每算完一只立即写入
                    member = json.dumps(r, ensure_ascii=False)
                    rds.zadd(zkey, {member: r.get("total_score", 0)})
            except Exception as e:
                print(f"❌ {st['code']} 计算失败: {e}")

    # 写入meta
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



