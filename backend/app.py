from flask import Flask, jsonify, request, send_from_directory
from flask_cors import CORS
import pymysql
import requests
from datetime import datetime, timedelta
from decimal import Decimal
import json
import sys
import os

# 添加项目根目录到路径
sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
from config import DATABASE_CONFIG

app = Flask(__name__, static_folder='../frontend', static_url_path='')
CORS(app)

# 使用配置文件中的数据库配置
DB_CONFIG = DATABASE_CONFIG

# 股票分组配置
STOCK_GROUPS = {
    '波段': [
        {'name': '国投智能', 'code': 'SZ300188', 'table': 'basic_data_sz300188'},
        {'name': '海兴电力', 'code': 'SH603556', 'table': 'basic_data_sh603556'},
        {'name': '沃尔核材', 'code': 'SZ002130', 'table': 'basic_data_sz002130'},
        {'name': '歌华有线', 'code': 'SH600037', 'table': 'basic_data_sh600037'},
        {'name': '中集车辆', 'code': 'SZ301039', 'table': 'basic_data_sz301039'}
    ],
    '短线': [
        {'name': '白云机场', 'code': 'SH600004', 'table': 'basic_data_sh600004'},
        {'name': '金雷股份', 'code': 'SZ300443', 'table': 'basic_data_sz300443'},
        {'name': '南京化纤', 'code': 'SH600889', 'table': 'basic_data_sh600889'},
        {'name': '慧智微-U', 'code': 'SH688512', 'table': 'basic_data_sh688512'},
        {'name': '锴威特', 'code': 'SH688693', 'table': 'basic_data_sh688693'}
    ],
    '中长线': [
        {'name': '立讯精密', 'code': 'SZ002475', 'table': 'basic_data_sz002475'},
        {'name': '宁德时代', 'code': 'SZ300750', 'table': 'basic_data_sz300750'},
        {'name': '农业银行', 'code': 'SH601288', 'table': 'basic_data_sh601288'},
        {'name': '中国石油', 'code': 'SH601857', 'table': 'basic_data_sh601857'},
        {'name': '紫金矿业', 'code': 'SH601899', 'table': 'basic_data_sh601899'}
    ]
}

# 周期类型映射（根据数据库实际字段值）
PERIOD_TYPE_MAP = {
    '30min': '30min',
    'day': '1day',
    'week': 'week',
    'month': 'month'
}


def get_db_connection():
    """获取数据库连接"""
    return pymysql.connect(**DB_CONFIG)


def decimal_to_float(obj):
    """将Decimal类型转换为float"""
    if isinstance(obj, Decimal):
        return float(obj)
    raise TypeError


@app.route('/')
def index():
    """返回首页"""
    return send_from_directory(app.static_folder, 'index.html')


@app.route('/api/stock_groups', methods=['GET'])
def get_stock_groups():
    """获取股票分组信息"""
    return jsonify({
        'code': 200,
        'data': STOCK_GROUPS,
        'message': 'success'
    })


@app.route('/api/kline_data', methods=['POST'])
def get_kline_data():
    """获取K线数据"""
    try:
        data = request.json
        table_name = data.get('table_name')
        period_type = data.get('period_type', 'day')
        
        # 获取3年前的日期
        three_years_ago = datetime.now() - timedelta(days=365*3)
        
        # 获取周期类型代码
        period_code = PERIOD_TYPE_MAP.get(period_type, '6')
        
        conn = get_db_connection()
        cursor = conn.cursor(pymysql.cursors.DictCursor)
        
        query = f"""
            SELECT shi_jian, kai_pan_jia, zui_gao_jia, zui_di_jia, shou_pan_jia, 
                   cheng_jiao_liang, liang_bi, wei_bi
            FROM {table_name}
            WHERE peroid_type = %s AND shi_jian >= %s
            ORDER BY shi_jian ASC
        """
        
        cursor.execute(query, (period_code, three_years_ago))
        results = cursor.fetchall()
        
        cursor.close()
        conn.close()
        
        # 格式化数据
        kline_data = []
        for row in results:
            kline_data.append({
                'time': row['shi_jian'].strftime('%Y-%m-%d %H:%M:%S'),
                'open': float(row['kai_pan_jia']) if row['kai_pan_jia'] else 0,
                'high': float(row['zui_gao_jia']) if row['zui_gao_jia'] else 0,
                'low': float(row['zui_di_jia']) if row['zui_di_jia'] else 0,
                'close': float(row['shou_pan_jia']) if row['shou_pan_jia'] else 0,
                'volume': int(row['cheng_jiao_liang']) if row['cheng_jiao_liang'] else 0,
                'liangbi': float(row['liang_bi']) if row['liang_bi'] else 0,
                'weibi': float(row['wei_bi']) if row['wei_bi'] else 0
            })
        
        return jsonify({
            'code': 200,
            'data': kline_data,
            'message': 'success'
        })
    
    except Exception as e:
        return jsonify({
            'code': 500,
            'data': None,
            'message': str(e)
        }), 500


@app.route('/api/stock_analysis', methods=['POST'])
def get_stock_analysis():
    """获取股票分析数据（益损比、压力线、支撑线）"""
    try:
        data = request.json
        stock_code = data.get('stock_code')
        
        # 调用外部API
        api_url = 'https://apiprod.mtygs.cn/api/stock/getStockAnalysis'
        api_data = {
            "appId": "string",
            "circleId": "string",
            "parameter": {
                "stockCode": stock_code
            },
            "requestId": "string",
            "token": "2025102013283854160ae6136c47da8d6c065f7919e66a_17721044150",
            "traceId": "string"
        }
        
        response = requests.post(api_url, json=api_data, timeout=10)
        response_data = response.json()
        
        # 解析响应数据
        analysis_data = {
            '30min': {},
            'day': {},
            'week': {},
            'month': {}
        }
        
        if response.status_code == 200 and response_data.get('code') == 200:
            result = response_data.get('data', {})
            
            # 提取不同周期的数据
            for period in ['30min', 'day', 'week', 'month']:
                period_data = result.get(f'minLineAnalysis_{period}', {})
                analysis_data[period] = {
                    'winLoseRatio': period_data.get('winLoseRatio', 0),
                    'supportPrice': period_data.get('supportPrice', 0),
                    'pressurePrice': period_data.get('pressurePrice', 0)
                }
        
        return jsonify({
            'code': 200,
            'data': analysis_data,
            'message': 'success'
        })
    
    except Exception as e:
        return jsonify({
            'code': 500,
            'data': None,
            'message': str(e)
        }), 500


if __name__ == '__main__':
    app.run(host='0.0.0.0', port=5000, debug=True)

