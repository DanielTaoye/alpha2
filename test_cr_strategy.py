"""测试CR点策略"""
import sys
import os

# 添加项目根目录到路径
backend_dir = os.path.join(os.path.dirname(os.path.abspath(__file__)), 'backend')
sys.path.insert(0, backend_dir)

from domain.services.cr_strategy_service import CRStrategyService

# 测试用例
def test_abc_calculation():
    """测试ABC计算"""
    print("\n=== 测试ABC计算 ===")
    
    # 测试用例1：标准K线
    service = CRStrategyService()
    abc = service.calculate_abc(
        open_price=10.0,
        high_price=11.0,
        low_price=9.5,
        close_price=10.5
    )
    
    print(f"测试用例1 - 开盘:10.0, 最高:11.0, 最低:9.5, 收盘:10.5")
    print(f"计算结果: a={abc.a}, b={abc.b}, c={abc.c}")
    print(f"预期: a=0.5 (11-10.5), b=0.5 (10.5-10), c=0.5 (10-9.5)")
    
    # 测试用例2：下跌K线
    abc2 = service.calculate_abc(
        open_price=11.0,
        high_price=11.5,
        low_price=10.0,
        close_price=10.2
    )
    
    print(f"\n测试用例2 - 开盘:11.0, 最高:11.5, 最低:10.0, 收盘:10.2")
    print(f"计算结果: a={abc2.a}, b={abc2.b}, c={abc2.c}")
    print(f"预期: a=0.5 (11.5-11), b=0.8 (11-10.2), c=0.2 (10.2-10)")


def test_c_point_strategy():
    """测试C点策略1"""
    print("\n\n=== 测试C点策略1 ===")
    
    service = CRStrategyService()
    
    # 测试用例1：符合条件的C点
    print("\n测试用例1 - 符合条件的C点")
    abc = service.calculate_abc(
        open_price=10.0,
        high_price=10.05,
        low_price=9.95,
        close_price=10.0
    )
    is_c, score, strategy = service.check_c_point_strategy_1(abc, 9.95)
    print(f"ABC值: a={abc.a:.4f}, b={abc.b:.4f}, c={abc.c:.4f}")
    print(f"a/c比例: {abc.a/abc.c:.4f}")
    print(f"b/最低价: {abc.b/9.95:.4f} ({abc.b/9.95*100:.2f}%)")
    print(f"是否C点: {is_c}, 得分: {score:.4f}")
    
    # 测试用例2：a/c不在范围内
    print("\n测试用例2 - a/c不在范围内")
    abc2 = service.calculate_abc(
        open_price=10.0,
        high_price=10.5,
        low_price=9.8,
        close_price=10.0
    )
    is_c2, score2, strategy2 = service.check_c_point_strategy_1(abc2, 9.8)
    print(f"ABC值: a={abc2.a:.4f}, b={abc2.b:.4f}, c={abc2.c:.4f}")
    print(f"a/c比例: {abc2.a/abc2.c:.4f}")
    print(f"是否C点: {is_c2}, 得分: {score2:.4f}")
    
    # 测试用例3：b/最低价超过1%
    print("\n测试用例3 - b/最低价超过1%")
    abc3 = service.calculate_abc(
        open_price=10.0,
        high_price=10.2,
        low_price=9.8,
        close_price=10.12
    )
    is_c3, score3, strategy3 = service.check_c_point_strategy_1(abc3, 9.8)
    print(f"ABC值: a={abc3.a:.4f}, b={abc3.b:.4f}, c={abc3.c:.4f}")
    print(f"a/c比例: {abc3.a/abc3.c:.4f}")
    print(f"b/最低价: {abc3.b/9.8:.4f} ({abc3.b/9.8*100:.2f}%)")
    print(f"是否C点: {is_c3}, 得分: {score3:.4f}")


if __name__ == '__main__':
    print("=" * 50)
    print("CR点策略测试程序")
    print("=" * 50)
    
    test_abc_calculation()
    test_c_point_strategy()
    
    print("\n" + "=" * 50)
    print("测试完成！")
    print("=" * 50)

