"""测试后端是否能正常启动"""
import sys
import os

# 添加项目根目录到路径
backend_dir = os.path.join(os.path.dirname(os.path.abspath(__file__)), 'backend')
sys.path.insert(0, backend_dir)

print("=" * 60)
print("后端启动测试")
print("=" * 60)

# 测试1：导入基础模块
print("\n[1/6] 测试导入基础模块...")
try:
    from infrastructure.config.database_config import DATABASE_CONFIG
    from infrastructure.persistence.database import DatabaseConnection
    print("[OK] 基础模块导入成功")
except Exception as e:
    print(f"[FAIL] 基础模块导入失败: {e}")
    sys.exit(1)

# 测试2：导入领域模型
print("\n[2/6] 测试导入领域模型...")
try:
    from domain.models.cr_point import CRPoint, ABCComponents
    from domain.models.kline import KLineData
    print("[OK] 领域模型导入成功")
except Exception as e:
    print(f"[FAIL] 领域模型导入失败: {e}")
    sys.exit(1)

# 测试3：导入服务
print("\n[3/6] 测试导入服务...")
try:
    from domain.services.cr_strategy_service import CRStrategyService
    from application.services.cr_point_service import CRPointService
    print("[OK] 服务层导入成功")
except Exception as e:
    print(f"[FAIL] 服务层导入失败: {e}")
    sys.exit(1)

# 测试4：导入仓储
print("\n[4/6] 测试导入仓储...")
try:
    from infrastructure.persistence.cr_point_repository_impl import CRPointRepositoryImpl
    print("[OK] 仓储层导入成功")
except Exception as e:
    print(f"[FAIL] 仓储层导入失败: {e}")
    sys.exit(1)

# 测试5：导入控制器
print("\n[5/6] 测试导入控制器...")
try:
    from interfaces.controllers.cr_point_controller import CRPointController
    print("[OK] 控制器导入成功")
except Exception as e:
    print(f"[FAIL] 控制器导入失败: {e}")
    sys.exit(1)

# 测试6：创建控制器实例
print("\n[6/6] 测试创建控制器实例...")
try:
    controller = CRPointController()
    print("[OK] 控制器实例创建成功")
    print(f"  - CR服务: {type(controller.cr_service).__name__}")
    print(f"  - K线服务: {type(controller.kline_service).__name__}")
except Exception as e:
    print(f"[FAIL] 控制器实例创建失败: {e}")
    import traceback
    traceback.print_exc()
    sys.exit(1)

print("\n" + "=" * 60)
print("[SUCCESS] 所有测试通过！后端可以正常启动。")
print("=" * 60)
print("\n提示：现在可以运行 'start.bat' 或 'python backend/app.py' 来启动服务器")

