"""查看Redis中的高分排行榜数据"""
import json
import sys
from pathlib import Path

# 添加backend目录到路径
backend_dir = Path(__file__).parent.parent
sys.path.insert(0, str(backend_dir))

from infrastructure.cache.redis_client import RedisClient

def main():
    r = RedisClient.instance().client
    zkey = RedisClient.full_key('high_score:zset')
    mkey = RedisClient.full_key('high_score:meta')
    
    print("=" * 60)
    print("Redis高分排行榜数据")
    print("=" * 60)
    
    # 查看zset
    count = r.zcard(zkey)
    print(f"\n📊 ZSET总数: {count}")
    
    if count > 0:
        print("\n🏆 排行榜（按总分降序）:")
        print("-" * 60)
        top_list = r.zrevrange(zkey, 0, -1, withscores=True)
        for idx, (member, score) in enumerate(top_list, 1):
            try:
                item = json.loads(member)
                print(f"{idx}. {item.get('stock_code')} {item.get('stock_name')}")
                print(f"   策略1: {item.get('strategy1_score')}, 策略2: {item.get('strategy2_score')}, 总分: {item.get('total_score')}")
                print(f"   是否高分: {'是' if item.get('is_high_score') else '否'}, 日期: {item.get('date')}")
                print()
            except Exception as e:
                print(f"{idx}. {member} (score: {score})")
    else:
        print("\n⚠️  ZSET为空")
    
    # 查看元信息
    meta_str = r.get(mkey)
    if meta_str:
        print("\n📋 元信息:")
        print("-" * 60)
        meta = json.loads(meta_str)
        for k, v in meta.items():
            print(f"   {k}: {v}")
    else:
        print("\n⚠️  元信息为空")
    
    print("\n" + "=" * 60)

if __name__ == '__main__':
    main()

