"""CR点控制器"""
from flask import request, jsonify
from typing import Dict, Any
from application.services.cr_point_service import CRPointService
from application.services.kline_service import KLineApplicationService
from infrastructure.persistence.kline_repository_impl import KLineRepositoryImpl
from interfaces.dto.response import ResponseBuilder
from infrastructure.logging.logger import get_logger

logger = get_logger(__name__)


class CRPointController:
    """CR点控制器"""
    
    def __init__(self):
        self.cr_service = CRPointService()
        kline_repository = KLineRepositoryImpl()
        self.kline_service = KLineApplicationService(kline_repository)
    
    def analyze_cr_points(self):
        """
        分析股票的CR点
        
        请求参数:
            stock_code: 股票代码
            stock_name: 股票名称
            table_name: K线数据表名
            period: 周期类型（day/week/month等）
        
        返回:
            CR点分析结果
        """
        try:
            data = request.get_json()
            stock_code = data.get('stockCode')
            stock_name = data.get('stockName', '')
            table_name = data.get('tableName')
            period = data.get('period', 'day')
            
            if not stock_code:
                return jsonify(ResponseBuilder.error('股票代码不能为空')), 400
            
            if not table_name:
                return jsonify(ResponseBuilder.error('表名不能为空')), 400
            
            logger.info(f"开始分析CR点: {stock_code} {stock_name} 表:{table_name} 周期:{period}")
            
            # 获取K线数据及技术指标
            result = self.kline_service.get_kline_data(table_name, period)
            kline_data_list = result.get('kline_data', [])
            macd_data = result.get('macd', {})
            ma_data = result.get('ma', {})
            
            if not kline_data_list:
                return jsonify(ResponseBuilder.error('K线数据为空')), 404
            
            # 转换为KLineData对象
            from domain.models.kline import KLineData
            from datetime import datetime
            
            kline_objects = []
            for kline in kline_data_list:
                kline_obj = KLineData(
                    time=datetime.strptime(kline['time'], '%Y-%m-%d %H:%M:%S'),
                    open=kline['open'],
                    high=kline['high'],
                    low=kline['low'],
                    close=kline['close'],
                    volume=kline['volume'],
                    liangbi=kline.get('liangbi', 0),
                    weibi=kline.get('weibi', 0)
                )
                kline_objects.append(kline_obj)
            
            # 实时分析CR点（不保存）
            cr_result = self.cr_service.analyze_cr_points(stock_code, stock_name, kline_objects)
            
            # 将MACD和MA数据添加到返回结果中
            cr_result['macd'] = macd_data
            cr_result['ma'] = ma_data
            
            return jsonify(ResponseBuilder.success(cr_result, f'CR点实时分析完成，发现C点{cr_result["c_points_count"]}个，R点{cr_result["r_points_count"]}个')), 200
            
        except Exception as e:
            logger.error(f"分析CR点失败: {e}", exc_info=True)
            return jsonify(ResponseBuilder.error(f'分析CR点失败: {str(e)}')), 500
    
    def get_cr_points(self):
        """
        获取股票的CR点列表（已弃用：C点改为实时计算，不再存储）
        
        说明：
            C点已改为实时计算模式，请使用 analyze_cr_points 接口实时计算
        """
        return jsonify(ResponseBuilder.error('C点已改为实时计算模式，请使用 analyze_cr_points 接口')), 410

