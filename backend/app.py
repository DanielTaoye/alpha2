"""应用入口文件 - DDD架构"""
from flask import Flask, send_from_directory
from flask_cors import CORS
import sys
import os

# 添加项目根目录到路径
backend_dir = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, backend_dir)

# 导入控制器
from interfaces.controllers.stock_controller import StockController
from interfaces.controllers.kline_controller import KLineController
from interfaces.controllers.analysis_controller import AnalysisController
from infrastructure.config.app_config import SERVER_CONFIG

# 创建Flask应用
app = Flask(__name__, static_folder='../frontend', static_url_path='')
CORS(app)

# 实例化控制器
stock_controller = StockController()
kline_controller = KLineController()
analysis_controller = AnalysisController()


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


if __name__ == '__main__':
    app.run(
        host=SERVER_CONFIG['host'],
        port=SERVER_CONFIG['port'],
        debug=SERVER_CONFIG['debug']
    )

