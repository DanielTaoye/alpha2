"""成交量类型计算服务"""
from typing import Optional, List, Dict
from datetime import datetime, timedelta
import pymysql.cursors
from infrastructure.persistence.database import DatabaseConnection
from infrastructure.logging.logger import get_logger
from domain.services.period_service import PeriodService

logger = get_logger(__name__)


class VolumeTypeService:
    """成交量类型计算服务"""
    
    @staticmethod
    def calculate_volume_type(table_name: str, target_date: datetime) -> Optional[str]:
        """
        计算指定日期的成交量类型
        
        Args:
            table_name: 股票表名
            target_date: 目标日期
            
        Returns:
            成交量类型: 'A', 'B', 'C', 'D' 或 None
        """
        try:
            # 获取日线数据（需要足够的历史数据来计算）
            # 需要至少6天的数据：前5天用于计算，当天用于判断
            start_date = target_date - timedelta(days=10)
            
            daily_data = VolumeTypeService._get_daily_volumes(
                table_name, start_date, target_date
            )
            
            if not daily_data or len(daily_data) < 2:
                return None
            
            # 按日期排序（从旧到新）
            daily_data.sort(key=lambda x: x['date'])
            
            # 找到目标日期的索引
            target_idx = None
            for i, data in enumerate(daily_data):
                if data['date'].date() == target_date.date():
                    target_idx = i
                    break
            
            if target_idx is None or target_idx < 1:
                return None
            
            target_volume = daily_data[target_idx]['volume']
            
            # 计算类型A: 当日为前1日成交均量的2倍-3倍
            if target_idx >= 1:
                prev_volume = daily_data[target_idx - 1]['volume']
                if prev_volume > 0:
                    ratio = target_volume / prev_volume
                    if 2.0 <= ratio <= 3.0:
                        return 'A'
            
            # 计算类型B: 当日为前3日成交均量的2倍及以上
            if target_idx >= 3:
                prev_3_volumes = [daily_data[i]['volume'] for i in range(target_idx - 3, target_idx)]
                avg_volume = sum(prev_3_volumes) / len(prev_3_volumes)
                if avg_volume > 0:
                    ratio = target_volume / avg_volume
                    if ratio >= 2.0:
                        return 'B'
            
            # 计算类型C: 当日为前5日成交均量的2倍及以上
            if target_idx >= 5:
                prev_5_volumes = [daily_data[i]['volume'] for i in range(target_idx - 5, target_idx)]
                avg_volume = sum(prev_5_volumes) / len(prev_5_volumes)
                if avg_volume > 0:
                    ratio = target_volume / avg_volume
                    if ratio >= 2.0:
                        return 'C'
            
            # 计算类型D: 前五日出现过ABC任意一种放量，标记为X日，今日的成交量为X日的1.2倍以上
            if target_idx >= 5:
                # 检查前5天是否有A/B/C类型的放量
                x_day_volume = None
                for i in range(max(0, target_idx - 5), target_idx):
                    check_date = daily_data[i]['date']
                    check_volume_type = VolumeTypeService._check_abc_volume_type(
                        daily_data, i
                    )
                    if check_volume_type in ['A', 'B', 'C']:
                        x_day_volume = daily_data[i]['volume']
                        break
                
                if x_day_volume and x_day_volume > 0:
                    ratio = target_volume / x_day_volume
                    if ratio >= 1.2:
                        return 'D'
            
            return None
            
        except Exception as e:
            logger.error(f"计算成交量类型失败: {table_name} {target_date}: {e}", exc_info=True)
            return None
    
    @staticmethod
    def _check_abc_volume_type(daily_data: List[Dict], idx: int) -> Optional[str]:
        """
        检查指定索引位置的成交量是否为A/B/C类型
        
        Args:
            daily_data: 日线数据列表
            idx: 索引位置
            
        Returns:
            'A', 'B', 'C' 或 None
        """
        if idx < 1:
            return None
        
        target_volume = daily_data[idx]['volume']
        
        # 检查类型A
        if idx >= 1:
            prev_volume = daily_data[idx - 1]['volume']
            if prev_volume > 0:
                ratio = target_volume / prev_volume
                if 2.0 <= ratio <= 3.0:
                    return 'A'
        
        # 检查类型B
        if idx >= 3:
            prev_3_volumes = [daily_data[i]['volume'] for i in range(idx - 3, idx)]
            avg_volume = sum(prev_3_volumes) / len(prev_3_volumes)
            if avg_volume > 0:
                ratio = target_volume / avg_volume
                if ratio >= 2.0:
                    return 'B'
        
        # 检查类型C
        if idx >= 5:
            prev_5_volumes = [daily_data[i]['volume'] for i in range(idx - 5, idx)]
            avg_volume = sum(prev_5_volumes) / len(prev_5_volumes)
            if avg_volume > 0:
                ratio = target_volume / avg_volume
                if ratio >= 2.0:
                    return 'C'
        
        return None
    
    @staticmethod
    def _get_daily_volumes(table_name: str, start_date: datetime, end_date: datetime) -> List[Dict]:
        """
        获取指定日期范围内的日线成交量数据
        
        Args:
            table_name: 股票表名
            start_date: 开始日期
            end_date: 结束日期
            
        Returns:
            日线数据列表，包含date和volume字段
        """
        try:
            period_code = PeriodService.get_period_code('day')
            
            with DatabaseConnection.get_connection_context() as conn:
                cursor = conn.cursor(pymysql.cursors.DictCursor)
                
                query = f"""
                    SELECT shi_jian as date, cheng_jiao_liang as volume
                    FROM {table_name}
                    WHERE peroid_type = %s 
                      AND shi_jian >= %s 
                      AND shi_jian <= %s
                    ORDER BY shi_jian ASC
                """
                
                cursor.execute(query, (period_code, start_date, end_date))
                results = cursor.fetchall()
                
                return [
                    {
                        'date': row['date'],
                        'volume': int(row['volume']) if row['volume'] else 0
                    }
                    for row in results
                ]
                
        except Exception as e:
            logger.error(f"获取日线成交量数据失败: {table_name}: {e}", exc_info=True)
            return []
    
    @staticmethod
    def batch_calculate_volume_types(
        table_name: str, 
        stock_code: str,
        start_date: Optional[datetime] = None,
        end_date: Optional[datetime] = None
    ) -> Dict[datetime, str]:
        """
        批量计算指定日期范围内的成交量类型
        
        Args:
            table_name: 股票表名
            stock_code: 股票代码
            start_date: 开始日期（如果为None，则从最早的数据开始）
            end_date: 结束日期（如果为None，则到最新的数据）
            
        Returns:
            日期到成交量类型的字典
        """
        try:
            period_code = PeriodService.get_period_code('day')
            
            with DatabaseConnection.get_connection_context() as conn:
                cursor = conn.cursor(pymysql.cursors.DictCursor)
                
                # 构建查询条件
                where_clauses = [f"peroid_type = %s"]
                params = [period_code]
                
                if start_date:
                    where_clauses.append("shi_jian >= %s")
                    params.append(start_date)
                
                if end_date:
                    where_clauses.append("shi_jian <= %s")
                    params.append(end_date)
                
                query = f"""
                    SELECT DISTINCT shi_jian as date
                    FROM {table_name}
                    WHERE {' AND '.join(where_clauses)}
                    ORDER BY shi_jian ASC
                """
                
                cursor.execute(query, params)
                date_rows = cursor.fetchall()
                
                # 获取所有日期的成交量数据
                all_dates = [row['date'] for row in date_rows]
                if not all_dates:
                    return {}
                
                # 获取足够的历史数据（需要前5天的数据）
                data_start_date = all_dates[0] - timedelta(days=10)
                daily_data = VolumeTypeService._get_daily_volumes(
                    table_name, data_start_date, all_dates[-1]
                )
                
                if not daily_data:
                    return {}
                
                # 按日期排序
                daily_data.sort(key=lambda x: x['date'])
                
                # 为每个日期计算成交量类型
                result = {}
                
                for target_date in all_dates:
                    # 转换为datetime对象
                    if isinstance(target_date, datetime):
                        target_date_obj = target_date
                    else:
                        target_date_obj = datetime.combine(target_date, datetime.min.time())
                    
                    # 在daily_data中找到目标日期的索引
                    target_idx = None
                    for i, data in enumerate(daily_data):
                        data_date = data['date']
                        if isinstance(data_date, datetime):
                            if data_date.date() == target_date_obj.date():
                                target_idx = i
                                break
                        else:
                            if data_date == target_date_obj.date():
                                target_idx = i
                                break
                    
                    if target_idx is None or target_idx < 1:
                        continue
                    
                    # 使用已获取的数据计算成交量类型
                    target_volume = daily_data[target_idx]['volume']
                    volume_type = None
                    
                    # 计算类型A: 当日为前1日成交均量的2倍-3倍
                    if target_idx >= 1:
                        prev_volume = daily_data[target_idx - 1]['volume']
                        if prev_volume > 0:
                            ratio = target_volume / prev_volume
                            if 2.0 <= ratio <= 3.0:
                                volume_type = 'A'
                    
                    # 计算类型B: 当日为前3日成交均量的2倍及以上
                    if volume_type is None and target_idx >= 3:
                        prev_3_volumes = [daily_data[i]['volume'] for i in range(target_idx - 3, target_idx)]
                        avg_volume = sum(prev_3_volumes) / len(prev_3_volumes)
                        if avg_volume > 0:
                            ratio = target_volume / avg_volume
                            if ratio >= 2.0:
                                volume_type = 'B'
                    
                    # 计算类型C: 当日为前5日成交均量的2倍及以上
                    if volume_type is None and target_idx >= 5:
                        prev_5_volumes = [daily_data[i]['volume'] for i in range(target_idx - 5, target_idx)]
                        avg_volume = sum(prev_5_volumes) / len(prev_5_volumes)
                        if avg_volume > 0:
                            ratio = target_volume / avg_volume
                            if ratio >= 2.0:
                                volume_type = 'C'
                    
                    # 计算类型D: 前五日出现过ABC任意一种放量，标记为X日，今日的成交量为X日的1.2倍以上
                    if volume_type is None and target_idx >= 5:
                        # 检查前5天是否有A/B/C类型的放量
                        x_day_volume = None
                        for i in range(max(0, target_idx - 5), target_idx):
                            check_volume_type = VolumeTypeService._check_abc_volume_type(
                                daily_data, i
                            )
                            if check_volume_type in ['A', 'B', 'C']:
                                x_day_volume = daily_data[i]['volume']
                                break
                        
                        if x_day_volume and x_day_volume > 0:
                            ratio = target_volume / x_day_volume
                            if ratio >= 1.2:
                                volume_type = 'D'
                    
                    if volume_type:
                        result[target_date_obj] = volume_type
                
                return result
                
        except Exception as e:
            logger.error(f"批量计算成交量类型失败: {table_name}: {e}", exc_info=True)
            return {}

