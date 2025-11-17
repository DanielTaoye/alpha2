"""应用入口文件 - DDD架构"""
from flask import Flask, send_from_directory
from flask_cors import CORS
import sys
import os

# 添加项目根目录到路径
backend_dir = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, backend_dir)

# 导入日志
from infrastructure.logging.logger import get_app_logger

# 导入控制器
from interfaces.controllers.stock_controller import StockController
from interfaces.controllers.kline_controller import KLineController
from interfaces.controllers.analysis_controller import AnalysisController
from interfaces.controllers.cr_point_controller import CRPointController
from interfaces.controllers.daily_chance_controller import DailyChanceController
from interfaces.controllers.config_controller import ConfigController
from infrastructure.config.app_config import SERVER_CONFIG

# 初始化日志
logger = get_app_logger()

# 创建Flask应用
app = Flask(__name__, static_folder='../frontend', static_url_path='')
CORS(app)

# 实例化控制器
stock_controller = StockController()
kline_controller = KLineController()
analysis_controller = AnalysisController()
cr_point_controller = CRPointController()
daily_chance_controller = DailyChanceController()
config_controller = ConfigController()


# ============ 路由定义 ============

@app.route('/')
def index():
    """返回首页"""
    return send_from_directory(app.static_folder, 'index.html')


@app.route('/api/stock_groups', methods=['GET'])
def get_stock_groups():
    """获取股票分组信息"""
    return stock_controller.get_stock_groups()


@app.route('/api/available_periods', methods=['POST'])
def get_available_periods():
    """获取股票可用的周期类型"""
    return kline_controller.get_available_periods()


@app.route('/api/kline_data', methods=['POST'])
def get_kline_data():
    """获取K线数据"""
    return kline_controller.get_kline_data()


@app.route('/api/stock_analysis', methods=['POST'])
def get_stock_analysis():
    """获取股票分析数据（益损比、压力线、支撑线）"""
    return analysis_controller.get_stock_analysis()


@app.route('/api/cr_points/analyze', methods=['POST'])
def analyze_cr_points():
    """分析股票CR点（买入卖出点）"""
    return cr_point_controller.analyze_cr_points()


@app.route('/api/cr_points', methods=['POST'])
def get_cr_points():
    """获取股票CR点列表（已弃用：改为实时计算）"""
    return cr_point_controller.get_cr_points()


@app.route('/api/daily_chance/sync_all', methods=['POST'])
def sync_all_daily_chance():
    """同步所有股票的每日机会数据"""
    return daily_chance_controller.sync_all_stocks()


@app.route('/api/daily_chance/sync', methods=['POST'])
def sync_daily_chance():
    """同步单个股票的每日机会数据"""
    return daily_chance_controller.sync_stock()


@app.route('/api/daily_chance', methods=['POST'])
def get_daily_chance():
    """获取每日机会数据"""
    return daily_chance_controller.get_daily_chance()


@app.route('/api/config', methods=['GET'])
def get_config():
    """获取策略配置"""
    return config_controller.get_config()


@app.route('/api/config', methods=['POST'])
def update_config():
    """更新策略配置"""
    return config_controller.update_config()


@app.route('/api/config/reload', methods=['POST'])
def reload_config():
    """重新加载配置"""
    return config_controller.reload_config()


if __name__ == '__main__':
    logger.info("=" * 50)
    logger.info("阿尔法策略2.0系统启动")
    logger.info(f"服务器地址: {SERVER_CONFIG['host']}:{SERVER_CONFIG['port']}")
    logger.info(f"调试模式: {SERVER_CONFIG['debug']}")
    logger.info("=" * 50)
    
    try:
        app.run(
            host=SERVER_CONFIG['host'],
            port=SERVER_CONFIG['port'],
            debug=SERVER_CONFIG['debug']
        )
    except Exception as e:
        logger.error(f"应用启动失败: {str(e)}", exc_info=True)
        raise

