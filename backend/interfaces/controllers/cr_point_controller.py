"""CR点控制器"""
from flask import request, jsonify
from typing import Dict, Any
from time import perf_counter
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
            t0 = perf_counter()
            # 添加详细日志
            logger.info(f"收到CR点分析请求")
            logger.info(f"请求内容类型: {request.content_type}")
            logger.info(f"请求体长度: {request.content_length}")
            
            # 使用force=True来避免JSON解析错误
            try:
                data = request.get_json(force=True)
                logger.info(f"成功解析JSON: {data}")
            except Exception as json_error:
                logger.error(f"JSON解析失败: {json_error}")
                logger.error(f"原始请求体: {request.get_data(as_text=True)}")
                raise
            stock_code = data.get('stockCode')
            stock_name = data.get('stockName', '')
            table_name = data.get('tableName')
            period = data.get('period', 'day')
            stock_nature = data.get('stockNature') or data.get('stock_nature')
            
            if not stock_code:
                return jsonify(ResponseBuilder.error('股票代码不能为空')), 400
            
            if not table_name:
                return jsonify(ResponseBuilder.error('表名不能为空')), 400
            
            logger.info(f"开始分析CR点: {stock_code} {stock_name} 表:{table_name} 周期:{period}")
            
            # 🔥 获取K线数据及技术指标（排除今天的数据，只计算历史）
            t_kline_0 = perf_counter()
            result = self.kline_service.get_kline_data(table_name, period, exclude_today=True)
            t_kline_1 = perf_counter()
            kline_data_list = result.get('kline_data', [])
            macd_data = result.get('macd', {})
            ma_data = result.get('ma', {})
            
            if not kline_data_list:
                return jsonify(ResponseBuilder.error('K线数据为空')), 404
            
            # 转换为KLineData对象
            from domain.models.kline import KLineData
            from datetime import datetime
            
            t_convert_0 = perf_counter()
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
            t_convert_1 = perf_counter()
            
            # 实时分析CR点（不保存）
            t_analyze_0 = perf_counter()
            cr_result = self.cr_service.analyze_cr_points(
                stock_code, 
                stock_name, 
                kline_objects,
                ma_data=ma_data,
                macd_data=macd_data,
                # 性能优化：策略2所需的 volume_types / bullish_patterns 由 service 内部从已预加载的 daily_chance 缓存派生
                volume_types=None,
                bullish_patterns=None,
                stock_nature=stock_nature
            )
            t_analyze_1 = perf_counter()
            
            # 将MACD和MA数据添加到返回结果中
            cr_result['macd'] = macd_data
            cr_result['ma'] = ma_data

            t_resp_0 = perf_counter()
            resp = jsonify(ResponseBuilder.success(cr_result, f'CR点实时分析完成，发现C点{cr_result["c_points_count"]}个，R点{cr_result["r_points_count"]}个'))
            t_resp_1 = perf_counter()

            logger.info(
                "CR点分析耗时(ms): total=%.1f, kline+指标=%.1f, kline转换=%.1f, 核心分析=%.1f, jsonify=%.1f, k线数=%d",
                (t_resp_1 - t0) * 1000,
                (t_kline_1 - t_kline_0) * 1000,
                (t_convert_1 - t_convert_0) * 1000,
                (t_analyze_1 - t_analyze_0) * 1000,
                (t_resp_1 - t_resp_0) * 1000,
                len(kline_objects),
            )
            
            return resp, 200
            
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

