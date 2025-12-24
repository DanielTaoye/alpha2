"""应用入口文件 - DDD架构"""
from flask import Flask, send_from_directory, request, jsonify
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
from interfaces.controllers.backtest_controller import BacktestController
from interfaces.controllers.batch_backtest_controller import BatchBacktestController
from interfaces.controllers.latest_cr_point_controller import LatestCRPointController
from interfaces.controllers.cache_controller import CacheController
from interfaces.controllers.high_score_controller import HighScoreController
from infrastructure.config.app_config import SERVER_CONFIG
from schedulers.high_score_scheduler import get_high_score_scheduler

# 初始化日志
logger = get_app_logger()

# 创建Flask应用
app = Flask(__name__, static_folder='../frontend', static_url_path='')
CORS(app, resources={r"/api/*": {"origins": "*", "methods": ["GET", "POST", "OPTIONS"], "allow_headers": "*"}})

# 实例化控制器
stock_controller = StockController()
kline_controller = KLineController()
analysis_controller = AnalysisController()
cr_point_controller = CRPointController()
daily_chance_controller = DailyChanceController()
config_controller = ConfigController()
backtest_controller = BacktestController()
batch_backtest_controller = BatchBacktestController()
latest_cr_point_controller = LatestCRPointController()
cache_controller = CacheController()
high_score_controller = HighScoreController()


# ============ 路由定义 ============

@app.route('/')
def index():
    """返回首页"""
    return send_from_directory(app.static_folder, 'index.html')


@app.route('/batch_backtest.html')
def batch_backtest():
    """返回批量回测页面"""
    return send_from_directory(app.static_folder, 'batch_backtest.html')


@app.route('/high_score.html')
def high_score():
    """返回高分推荐页面"""
    return send_from_directory(app.static_folder, 'high_score.html')


@app.route('/api/debug/routes')
def debug_routes():
    """调试：显示所有注册的路由"""
    routes = []
    for rule in app.url_map.iter_rules():
        routes.append({
            'endpoint': rule.endpoint,
            'methods': list(rule.methods),
            'path': str(rule)
        })
    return jsonify({'routes': routes}), 200


@app.route('/api/stock_groups', methods=['GET'])
def get_stock_groups():
    """获取股票分组信息（59支代表性股票）"""
    return stock_controller.get_stock_groups()


@app.route('/api/stocks/search', methods=['GET'])
def search_stocks():
    """搜索全部股票（从 all_stock 表）"""
    return stock_controller.search_stocks()


@app.route('/api/available_periods', methods=['POST'])
def get_available_periods():
    """获取股票可用的周期类型"""
    return kline_controller.get_available_periods()


@app.route('/api/kline_data', methods=['POST'])
def get_kline_data():
    """获取K线数据"""
    return kline_controller.get_kline_data()


@app.route('/api/latest_day_kline', methods=['POST'])
def get_latest_day_kline():
    """获取最新一天的K线数据（从1分钟数据聚合）"""
    return kline_controller.get_latest_day_kline()


@app.route('/api/predict_volume', methods=['POST'])
def predict_volume():
    """预测当天的成交量"""
    return kline_controller.predict_volume()


@app.route('/api/predict_volume_type', methods=['POST'])
def predict_volume_type():
    """基于预测成交量计算成交量类型"""
    return kline_controller.predict_volume_type()


@app.route('/api/trading_status', methods=['GET'])
def get_trading_status():
    """获取当前交易状态（是否应该使用预测成交量）"""
    from domain.services.trading_calendar_service import TradingCalendarService
    from datetime import datetime
    
    calendar_service = TradingCalendarService()
    now = datetime.now()
    
    return jsonify({
        'code': 0,
        'data': {
            'is_trading_day': calendar_service.is_trading_day(now.date()),
            'is_trading_time': calendar_service.is_in_trading_time(now),
            'should_use_predicted': calendar_service.should_use_predicted_volume(now),
            'current_time': now.strftime('%Y-%m-%d %H:%M:%S'),
            'today_date': now.strftime('%Y-%m-%d')
        }
    })


@app.route('/api/stock_analysis', methods=['POST'])
def get_stock_analysis():
    """获取股票分析数据（益损比、压力线、支撑线）"""
    return analysis_controller.get_stock_analysis()


@app.route('/api/cr_points/analyze', methods=['POST'])
def analyze_cr_points():
    """分析股票CR点（买入卖出点）"""
    return cr_point_controller.analyze_cr_points()


@app.route('/api/cr_analysis', methods=['POST', 'OPTIONS'])
def cr_analysis():
    """CR点分析（批量回测使用）"""
    if request.method == 'OPTIONS':
        return '', 204
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


@app.route('/api/latest_cr_points', methods=['POST'])
def get_latest_cr_points():
    """获取最新一天的CR点"""
    return latest_cr_point_controller.get_latest_cr_points()


@app.route('/api/streaming/high_score', methods=['POST'])
def streaming_high_score():
    """从Redis获取高分排行榜"""
    return high_score_controller.get_high_score()


@app.route('/api/streaming/high_score/refresh', methods=['POST'])
def refresh_streaming_high_score():
    """手动刷新高分排行榜（立即重算）"""
    return high_score_controller.refresh_high_score()


# ============= 缓存管理接口 =============
@app.route('/api/cache/info', methods=['GET', 'POST'])
def get_cache_info():
    """获取缓存信息"""
    return cache_controller.get_cache_info()


@app.route('/api/cache/update', methods=['POST'])
def update_cache():
    """手动更新缓存"""
    return cache_controller.update_cache()


@app.route('/api/cache/init', methods=['POST'])
def init_cache():
    """初始化缓存"""
    return cache_controller.init_cache()


@app.route('/api/cache/clear', methods=['POST'])
def clear_cache():
    """清空所有缓存"""
    return cache_controller.clear_cache()


@app.route('/api/config', methods=['POST'])
def update_config():
    """更新策略配置"""
    return config_controller.update_config()


@app.route('/api/config/reload', methods=['POST'])
def reload_config():
    """重新加载配置"""
    return config_controller.reload_config()


@app.route('/api/backtest', methods=['POST', 'OPTIONS'])
def run_backtest():
    """执行回测"""
    if request.method == 'OPTIONS':
        return '', 204
    return backtest_controller.run_backtest()


@app.route('/api/batch_backtest/start', methods=['POST', 'OPTIONS'])
def batch_backtest_start():
    """启动批量回测（后端后台任务）"""
    if request.method == 'OPTIONS':
        return '', 204
    return batch_backtest_controller.start()


@app.route('/api/batch_backtest/status/<job_id>', methods=['GET'])
def batch_backtest_status(job_id: str):
    """查询批量回测任务状态"""
    return batch_backtest_controller.status(job_id)


@app.route('/api/batch_backtest/cancel/<job_id>', methods=['POST', 'OPTIONS'])
def batch_backtest_cancel(job_id: str):
    """取消批量回测任务"""
    if request.method == 'OPTIONS':
        return '', 204
    return batch_backtest_controller.cancel(job_id)


if __name__ == '__main__':
    logger.info("=" * 50)
    logger.info("阿尔法策略2.0系统启动")
    logger.info(f"服务器地址: {SERVER_CONFIG['host']}:{SERVER_CONFIG['port']}")
    logger.info(f"调试模式: {SERVER_CONFIG['debug']}")
    logger.info("=" * 50)
    
    # 初始化全局CR缓存（后台线程异步初始化，不阻塞启动）
    try:
        import threading
        import json
        import os
        from application.services.cr_cache_manager import get_cr_cache_manager
        
        def init_cache_async():
            """异步初始化缓存"""
            try:
                logger.info("🚀 开始异步初始化CR全局缓存...")
                
                # 加载股票配置
                config_path = os.path.join(os.path.dirname(__file__), 'infrastructure/config/stock_config.json')
                with open(config_path, 'r', encoding='utf-8') as f:
                    config = json.load(f)
                
                # 收集所有股票代码
                stock_codes = []
                for nature, stock_list in config.items():
                    for stock in stock_list:
                        stock_codes.append(stock['code'])
                
                # 初始化缓存
                cache_manager = get_cr_cache_manager()
                cache_manager.init_all_stocks(stock_codes, days=30)
                
                logger.info("✅ CR全局缓存初始化完成")
                
            except Exception as e:
                logger.error(f"❌ CR全局缓存初始化失败: {e}", exc_info=True)
        
        # 启动后台线程初始化缓存（已禁用，按需使用）
        # cache_thread = threading.Thread(target=init_cache_async, daemon=True)
        # cache_thread.start()
        # logger.info("📌 CR缓存初始化线程已启动（后台运行）")
        logger.info("⏸️  CR缓存自动初始化已禁用（按需加载）")
        
    except Exception as e:
        logger.error(f"❌ 启动CR缓存初始化失败: {e}", exc_info=True)
    
    try:
        # 启动高分定时任务（避免debug模式重复启动）
        # 临时关闭：如需恢复，将下方注释去掉
        # try:
        #     if os.environ.get("WERKZEUG_RUN_MAIN") == "true" or not SERVER_CONFIG.get('debug', False):
        #         scheduler = get_high_score_scheduler()
        #         scheduler.start()
        # except Exception as e:
        #     logger.error(f"❌ 启动高分定时任务失败: {e}", exc_info=True)

        app.run(
            host=SERVER_CONFIG['host'],
            port=SERVER_CONFIG['port'],
            debug=SERVER_CONFIG['debug'],
            threaded=True
        )
    except Exception as e:
        logger.error(f"应用启动失败: {str(e)}", exc_info=True)
        raise

