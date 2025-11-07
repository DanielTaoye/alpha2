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
        {'name': '中集车辆', 'code': 'SZ301039', 'table': 'basic_data_sz301039'},
        {'name': '蓝色光标', 'code': 'SZ300058', 'table': 'basic_data_sz300058'},
        {'name': '迪普科技', 'code': 'SZ300768', 'table': 'basic_data_sz300768'},
        {'name': '思瑞浦', 'code': 'SH688536', 'table': 'basic_data_sh688536'},
        {'name': '时代新材', 'code': 'SH600458', 'table': 'basic_data_sh600458'},
        {'name': '东华软件', 'code': 'SZ002065', 'table': 'basic_data_sz002065'},
        {'name': '福蓉科技', 'code': 'SH603327', 'table': 'basic_data_sh603327'},
        {'name': '筑博设计', 'code': 'SZ300564', 'table': 'basic_data_sz300564'},
        {'name': '杭叉集团', 'code': 'SH603298', 'table': 'basic_data_sh603298'},
        {'name': '维信诺', 'code': 'SZ002387', 'table': 'basic_data_sz002387'},
        {'name': '康美药业', 'code': 'SH600518', 'table': 'basic_data_sh600518'},
        {'name': '广汇能源', 'code': 'SH600256', 'table': 'basic_data_sh600256'},
        {'name': '科沃斯', 'code': 'SH603486', 'table': 'basic_data_sh603486'},
        {'name': '高能环境', 'code': 'SH603588', 'table': 'basic_data_sh603588'},
        {'name': '北新建材', 'code': 'SZ000786', 'table': 'basic_data_sz000786'},
        {'name': '安通控股', 'code': 'SH600179', 'table': 'basic_data_sh600179'}
    ],
    '短线': [
        {'name': '白云机场', 'code': 'SH600004', 'table': 'basic_data_sh600004'},
        {'name': '金雷股份', 'code': 'SZ300443', 'table': 'basic_data_sz300443'},
        {'name': '南京化纤', 'code': 'SH600889', 'table': 'basic_data_sh600889'},
        {'name': '慧智微-U', 'code': 'SH688512', 'table': 'basic_data_sh688512'},
        {'name': '锴威特', 'code': 'SH688693', 'table': 'basic_data_sh688693'},
        {'name': '新疆天业', 'code': 'SH600075', 'table': 'basic_data_sh600075'},
        {'name': '物产金轮', 'code': 'SZ002722', 'table': 'basic_data_sz002722'},
        {'name': '中巨芯-U', 'code': 'SH688549', 'table': 'basic_data_sh688549'},
        {'name': '美湖股份', 'code': 'SH603319', 'table': 'basic_data_sh603319'},
        {'name': '依米康', 'code': 'SZ300249', 'table': 'basic_data_sz300249'},
        {'name': '中化装备', 'code': 'SH600579', 'table': 'basic_data_sh600579'},
        {'name': '科锐国际', 'code': 'SZ300662', 'table': 'basic_data_sz300662'},
        {'name': '三晖电气', 'code': 'SZ002857', 'table': 'basic_data_sz002857'},
        {'name': '易尚退', 'code': 'SZ002751', 'table': 'basic_data_sz002751'},
        {'name': '长青科技', 'code': 'SZ001324', 'table': 'basic_data_sz001324'},
        {'name': '菲菱科思', 'code': 'SZ301191', 'table': 'basic_data_sz301191'},
        {'name': '运达股份', 'code': 'SZ300772', 'table': 'basic_data_sz300772'},
        {'name': '上纬新材', 'code': 'SH688585', 'table': 'basic_data_sh688585'},
        {'name': '开创电气', 'code': 'SZ301448', 'table': 'basic_data_sz301448'},
        {'name': '康希通信', 'code': 'SH688653', 'table': 'basic_data_sh688653'}
    ],
    '中长线': [
        {'name': '立讯精密', 'code': 'SZ002475', 'table': 'basic_data_sz002475'},
        {'name': '宁德时代', 'code': 'SZ300750', 'table': 'basic_data_sz300750'},
        {'name': '农业银行', 'code': 'SH601288', 'table': 'basic_data_sh601288'},
        {'name': '中国石油', 'code': 'SH601857', 'table': 'basic_data_sh601857'},
        {'name': '紫金矿业', 'code': 'SH601899', 'table': 'basic_data_sh601899'},
        {'name': '传音控股', 'code': 'SH688036', 'table': 'basic_data_sh688036'},
        {'name': '常熟银行', 'code': 'SH601128', 'table': 'basic_data_sh601128'},
        {'name': '潍柴动力', 'code': 'SZ000338', 'table': 'basic_data_sz000338'},
        {'name': '海螺水泥', 'code': 'SH600585', 'table': 'basic_data_sh600585'},
        {'name': '民生银行', 'code': 'SH600016', 'table': 'basic_data_sh600016'},
        {'name': '华域汽车', 'code': 'SH600741', 'table': 'basic_data_sh600741'},
        {'name': '申万宏源', 'code': 'SZ000166', 'table': 'basic_data_sz000166'},
        {'name': '陕西煤业', 'code': 'SH601225', 'table': 'basic_data_sh601225'},
        {'name': '泸州老窖', 'code': 'SZ000568', 'table': 'basic_data_sz000568'},
        {'name': '江阴银行', 'code': 'SZ002807', 'table': 'basic_data_sz002807'},
        {'name': '中微公司', 'code': 'SH688012', 'table': 'basic_data_sh688012'},
        {'name': '春秋航空', 'code': 'SH601021', 'table': 'basic_data_sh601021'},
        {'name': '光启技术', 'code': 'SZ002625', 'table': 'basic_data_sz002625'},
        {'name': '宇通客车', 'code': 'SH600066', 'table': 'basic_data_sh600066'},
        {'name': '中远海控', 'code': 'SH601919', 'table': 'basic_data_sh601919'}
    ]
}







# 周期类型映射（根据数据库实际字段值）
# 数据库中使用字符串存储周期类型
PERIOD_TYPE_MAP = {
    '30min': '30min',
    'day': '1day',      # 注意：数据库中是 '1day' 不是 'day'
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


@app.route('/api/available_periods', methods=['POST'])
def get_available_periods():
    """获取股票可用的周期类型"""
    try:
        data = request.json
        table_name = data.get('table_name')
        
        conn = get_db_connection()
        cursor = conn.cursor()
        
        # 查询该表中有哪些周期类型的数据
        query = f"""
            SELECT DISTINCT peroid_type, COUNT(*) as count
            FROM {table_name}
            GROUP BY peroid_type
        """
        
        cursor.execute(query)
        results = cursor.fetchall()
        
        cursor.close()
        conn.close()
        
        # 构建可用周期列表
        available_periods = {}
        period_map_reverse = {v: k for k, v in PERIOD_TYPE_MAP.items()}
        
        for row in results:
            db_period = row[0]
            count = row[1]
            
            # 反向映射，找到前端使用的周期名称
            frontend_period = period_map_reverse.get(db_period)
            if frontend_period and count > 0:
                available_periods[frontend_period] = count
        
        return jsonify({
            'code': 200,
            'data': available_periods,
            'message': 'success'
        })
    
    except Exception as e:
        return jsonify({
            'code': 500,
            'data': {},
            'message': str(e)
        }), 500


@app.route('/api/kline_data', methods=['POST'])
def get_kline_data():
    """获取K线数据"""
    try:
        data = request.json
        table_name = data.get('table_name')
        period_type = data.get('period_type', 'day')
        
        # 根据周期类型设置合理的时间范围，减少数据量
        time_ranges = {
            '30min': 90,    # 30分钟K线：最近3个月
            'day': 730,     # 日K线：最近2年
            'week': 1095,   # 周K线：最近3年
            'month': 1825   # 月K线：最近5年
        }
        days = time_ranges.get(period_type, 730)
        start_date = datetime.now() - timedelta(days=days)
        
        # 获取周期类型代码
        period_code = PERIOD_TYPE_MAP.get(period_type, '1day')
        
        conn = get_db_connection()
        cursor = conn.cursor(pymysql.cursors.DictCursor)
        
        # 优化查询：只查询必要字段，添加限制
        query = f"""
            SELECT shi_jian, kai_pan_jia, zui_gao_jia, zui_di_jia, shou_pan_jia, 
                   cheng_jiao_liang, liang_bi, wei_bi
            FROM {table_name}
            WHERE peroid_type = %s AND shi_jian >= %s
            ORDER BY shi_jian DESC
            LIMIT 2000
        """
        
        cursor.execute(query, (period_code, start_date))
        results = cursor.fetchall()
        
        # 反转顺序，从旧到新
        results.reverse()
        
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
        
        # 默认空数据结构
        analysis_data = {
            '30min': {},
            'day': {},
            'week': {},
            'month': {}
        }
        
        try:
            # 调用外部API（设置短超时，避免阻塞）
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
            
            # 超时设置：15秒，给足够的响应时间
            response = requests.post(api_url, json=api_data, timeout=15)
            response_data = response.json()
            
            print(f"[分析接口] 股票 {stock_code} 响应: success={response_data.get('success')}")
            
            # 解析响应数据（注意：接口返回的是 success 和 result，不是 code 和 data）
            if response.status_code == 200 and response_data.get('success') == True:
                result = response_data.get('result', {})
                
                # 提取不同周期的数据
                # 30分钟: minLineAnalysis
                # 日K: dayLineAnalysis
                # 周K: weekLineAnalysis
                # 月K: monthLineAnalysis
                period_mapping = {
                    '30min': 'minLineAnalysis',
                    'day': 'dayLineAnalysis',
                    'week': 'weekLineAnalysis',
                    'month': 'monthLineAnalysis'
                }
                
                for frontend_period, api_field in period_mapping.items():
                    period_data = result.get(api_field, {})
                    if period_data:
                        analysis_data[frontend_period] = {
                            'winLoseRatio': period_data.get('winLoseRatio', 0),
                            'supportPrice': period_data.get('supportPrice', 0),
                            'pressurePrice': period_data.get('pressurePrice', 0)
                        }
                        print(f"[分析接口] {frontend_period} 数据: 益损比={period_data.get('winLoseRatio')}, "
                              f"支撑线={period_data.get('supportPrice')}, 压力线={period_data.get('pressurePrice')}")
                    else:
                        print(f"[分析接口] {frontend_period} 无数据")
            else:
                print(f"[分析接口] 请求失败: status={response.status_code}, success={response_data.get('success')}")
        except requests.Timeout:
            # 超时不影响返回，返回空数据
            print(f"分析接口超时: {stock_code}")
        except requests.RequestException as e:
            # 网络错误不影响返回
            print(f"分析接口请求失败: {stock_code}, 错误: {e}")
        except Exception as e:
            # 其他错误也不影响返回
            print(f"分析接口异常: {stock_code}, 错误: {e}")
        
        # 总是返回成功，即使分析数据为空
        return jsonify({
            'code': 200,
            'data': analysis_data,
            'message': 'success'
        })
    
    except Exception as e:
        # 最外层异常，返回空数据而不是500错误
        return jsonify({
            'code': 200,
            'data': {
                '30min': {},
                'day': {},
                'week': {},
                'month': {}
            },
            'message': f'Analysis failed: {str(e)}'
        })


if __name__ == '__main__':
    app.run(host='0.0.0.0', port=5000, debug=True)

