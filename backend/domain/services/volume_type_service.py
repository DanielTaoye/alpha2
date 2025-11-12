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
            成交量类型: 'A', 'B', 'C', 'D', 'E', 'F', 'G', 'H', 'X', 'Y', 'Z' 或多个类型用逗号连接（如 'A,B' 或 'A,B,C,D,E,F,G,H,X,Y,Z'），如果没有匹配则返回 None
        """
        try:
            # 获取日线数据（需要足够的历史数据来计算）
            # 需要至少15天的数据：Z类型需要前10天，加上前5天用于其他类型计算
            start_date = target_date - timedelta(days=15)
            
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
            
            # 收集所有匹配的类型
            matched_types = []
            
            # 计算类型A: 当日为前1日成交均量的2倍-3倍
            if target_idx >= 1:
                prev_volume = daily_data[target_idx - 1]['volume']
                if prev_volume > 0:
                    ratio = target_volume / prev_volume
                    if 2.0 <= ratio <= 3.0:
                        matched_types.append('A')
            
            # 计算类型B: 当日为前3日成交均量的2倍及以上
            if target_idx >= 3:
                prev_3_volumes = [daily_data[i]['volume'] for i in range(target_idx - 3, target_idx)]
                avg_volume = sum(prev_3_volumes) / len(prev_3_volumes)
                if avg_volume > 0:
                    ratio = target_volume / avg_volume
                    if ratio >= 2.0:
                        matched_types.append('B')
            
            # 计算类型C: 当日为前5日成交均量的2倍及以上
            if target_idx >= 5:
                prev_5_volumes = [daily_data[i]['volume'] for i in range(target_idx - 5, target_idx)]
                avg_volume = sum(prev_5_volumes) / len(prev_5_volumes)
                if avg_volume > 0:
                    ratio = target_volume / avg_volume
                    if ratio >= 2.0:
                        matched_types.append('C')
            
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
                        matched_types.append('D')
            
            # 计算类型E: 当日为前1日以及前五日均值的4倍以上（前五日未出现ABCD任何一种放量）
            if target_idx >= 5:
                # 检查前5天是否有ABCD任意一种放量
                has_abcd_in_prev_5 = False
                for i in range(max(0, target_idx - 5), target_idx):
                    check_types = VolumeTypeService._check_all_volume_types(daily_data, i)
                    if check_types and any(t in check_types for t in ['A', 'B', 'C', 'D']):
                        has_abcd_in_prev_5 = True
                        break
                
                if not has_abcd_in_prev_5:
                    # 前1日成交量
                    prev_volume = daily_data[target_idx - 1]['volume'] if target_idx >= 1 else 0
                    # 前5日均值
                    prev_5_volumes = [daily_data[i]['volume'] for i in range(target_idx - 5, target_idx)]
                    avg_5_volume = sum(prev_5_volumes) / len(prev_5_volumes)
                    
                    if prev_volume > 0 and avg_5_volume > 0:
                        ratio_to_prev = target_volume / prev_volume
                        ratio_to_avg5 = target_volume / avg_5_volume
                        if ratio_to_prev >= 4.0 and ratio_to_avg5 >= 4.0:
                            matched_types.append('E')
            
            # 计算类型F: 前五日出现过ABCD任意一种放量，标记为X日，今日成交量为X日的3倍以上，或今日成交量为前5日成交量均值的3倍以上
            if target_idx >= 5:
                # 检查前5天是否有ABCD任意一种放量
                x_day_volume = None
                for i in range(max(0, target_idx - 5), target_idx):
                    check_types = VolumeTypeService._check_all_volume_types(daily_data, i)
                    if check_types and any(t in check_types for t in ['A', 'B', 'C', 'D']):
                        x_day_volume = daily_data[i]['volume']
                        break
                
                prev_5_volumes = [daily_data[i]['volume'] for i in range(target_idx - 5, target_idx)]
                avg_5_volume = sum(prev_5_volumes) / len(prev_5_volumes)
                
                # 条件1: 今日成交量为X日的3倍以上
                condition1 = False
                if x_day_volume and x_day_volume > 0:
                    ratio = target_volume / x_day_volume
                    if ratio >= 3.0:
                        condition1 = True
                
                # 条件2: 今日成交量为前5日成交量均值的3倍以上
                condition2 = False
                if avg_5_volume > 0:
                    ratio = target_volume / avg_5_volume
                    if ratio >= 3.0:
                        condition2 = True
                
                if condition1 or condition2:
                    matched_types.append('F')
            
            # 计算类型G: 前五日中某日（设X日）出现任意一种放量（ABCD)放量，今日的量能为X日的0.7倍及以上
            if target_idx >= 5:
                for i in range(max(0, target_idx - 5), target_idx):
                    check_types = VolumeTypeService._check_all_volume_types(daily_data, i)
                    if check_types and any(t in check_types for t in ['A', 'B', 'C', 'D']):
                        x_day_volume = daily_data[i]['volume']
                        if x_day_volume > 0:
                            ratio = target_volume / x_day_volume
                            if ratio >= 0.7:
                                matched_types.append('G')
                                break
            
            # 计算类型H: 前五日中某日（设X日）出现任意一种放量（ABCD)放量，今日的量能大于X日
            if target_idx >= 5:
                for i in range(max(0, target_idx - 5), target_idx):
                    check_types = VolumeTypeService._check_all_volume_types(daily_data, i)
                    if check_types and any(t in check_types for t in ['A', 'B', 'C', 'D']):
                        x_day_volume = daily_data[i]['volume']
                        if target_volume > x_day_volume:
                            matched_types.append('H')
                            break
            
            # 计算类型X: 当日为前3日成交均量的1.5倍及以上
            if target_idx >= 3:
                prev_3_volumes = [daily_data[i]['volume'] for i in range(target_idx - 3, target_idx)]
                avg_volume = sum(prev_3_volumes) / len(prev_3_volumes)
                if avg_volume > 0:
                    ratio = target_volume / avg_volume
                    if ratio >= 1.5:
                        matched_types.append('X')
            
            # 计算类型Y: 当日为前5日成交均量的1.5倍及以上
            if target_idx >= 5:
                prev_5_volumes = [daily_data[i]['volume'] for i in range(target_idx - 5, target_idx)]
                avg_volume = sum(prev_5_volumes) / len(prev_5_volumes)
                if avg_volume > 0:
                    ratio = target_volume / avg_volume
                    if ratio >= 1.5:
                        matched_types.append('Y')
            
            # 计算类型Z: 前10日出现出现过（ABC）任何一种放量，且昨日量能相较于前三日均量出现1.3倍以上的放量，今日的量相较于昨日能量能的1.08倍以上
            if target_idx >= 10:
                # 检查前10天是否有ABC任意一种放量
                has_abc_in_prev_10 = False
                for i in range(max(0, target_idx - 10), target_idx):
                    check_types = VolumeTypeService._check_abc_volume_type(daily_data, i)
                    if check_types in ['A', 'B', 'C']:
                        has_abc_in_prev_10 = True
                        break
                
                if has_abc_in_prev_10 and target_idx >= 4:
                    # 昨日量能
                    yesterday_volume = daily_data[target_idx - 1]['volume']
                    # 前3日均量（不包括昨日）
                    prev_3_volumes = [daily_data[i]['volume'] for i in range(target_idx - 4, target_idx - 1)]
                    avg_3_volume = sum(prev_3_volumes) / len(prev_3_volumes)
                    
                    # 条件1: 昨日量能相较于前三日均量出现1.3倍以上的放量
                    condition1 = False
                    if avg_3_volume > 0:
                        ratio = yesterday_volume / avg_3_volume
                        if ratio >= 1.3:
                            condition1 = True
                    
                    # 条件2: 今日的量相较于昨日能量能的1.08倍以上
                    condition2 = False
                    if yesterday_volume > 0:
                        ratio = target_volume / yesterday_volume
                        if ratio >= 1.08:
                            condition2 = True
                    
                    if condition1 and condition2:
                        matched_types.append('Z')
            
            # 返回所有匹配的类型，用逗号连接（按A、B、C、D、E、F、G、H、X、Y、Z的顺序）
            if matched_types:
                # 去重并保持顺序
                seen = set()
                unique_types = []
                for t in ['A', 'B', 'C', 'D', 'E', 'F', 'G', 'H', 'X', 'Y', 'Z']:
                    if t in matched_types and t not in seen:
                        unique_types.append(t)
                        seen.add(t)
                return ','.join(unique_types)
            
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
    def _check_all_volume_types(daily_data: List[Dict], idx: int) -> Optional[str]:
        """
        检查指定索引位置的成交量是否为A/B/C/D类型（返回所有匹配的类型）
        
        Args:
            daily_data: 日线数据列表
            idx: 索引位置
            
        Returns:
            匹配的类型字符串，多个类型用逗号连接，如 'A,B' 或 None
        """
        if idx < 1:
            return None
        
        target_volume = daily_data[idx]['volume']
        matched_types = []
        
        # 检查类型A
        if idx >= 1:
            prev_volume = daily_data[idx - 1]['volume']
            if prev_volume > 0:
                ratio = target_volume / prev_volume
                if 2.0 <= ratio <= 3.0:
                    matched_types.append('A')
        
        # 检查类型B
        if idx >= 3:
            prev_3_volumes = [daily_data[i]['volume'] for i in range(idx - 3, idx)]
            avg_volume = sum(prev_3_volumes) / len(prev_3_volumes)
            if avg_volume > 0:
                ratio = target_volume / avg_volume
                if ratio >= 2.0:
                    matched_types.append('B')
        
        # 检查类型C
        if idx >= 5:
            prev_5_volumes = [daily_data[i]['volume'] for i in range(idx - 5, idx)]
            avg_volume = sum(prev_5_volumes) / len(prev_5_volumes)
            if avg_volume > 0:
                ratio = target_volume / avg_volume
                if ratio >= 2.0:
                    matched_types.append('C')
        
        # 检查类型D（需要检查前5天是否有ABC放量）
        if idx >= 5:
            x_day_volume = None
            for i in range(max(0, idx - 5), idx):
                check_volume_type = VolumeTypeService._check_abc_volume_type(daily_data, i)
                if check_volume_type in ['A', 'B', 'C']:
                    x_day_volume = daily_data[i]['volume']
                    break
            
            if x_day_volume and x_day_volume > 0:
                ratio = target_volume / x_day_volume
                if ratio >= 1.2:
                    matched_types.append('D')
        
        if matched_types:
            # 去重并保持顺序
            seen = set()
            unique_types = []
            for t in ['A', 'B', 'C', 'D']:
                if t in matched_types and t not in seen:
                    unique_types.append(t)
                    seen.add(t)
            return ','.join(unique_types)
        
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
                
                # 获取足够的历史数据（需要前10天的数据，因为Z类型需要前10天）
                data_start_date = all_dates[0] - timedelta(days=15)
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
                    matched_types = []
                    
                    # 计算类型A: 当日为前1日成交均量的2倍-3倍
                    if target_idx >= 1:
                        prev_volume = daily_data[target_idx - 1]['volume']
                        if prev_volume > 0:
                            ratio = target_volume / prev_volume
                            if 2.0 <= ratio <= 3.0:
                                matched_types.append('A')
                    
                    # 计算类型B: 当日为前3日成交均量的2倍及以上
                    if target_idx >= 3:
                        prev_3_volumes = [daily_data[i]['volume'] for i in range(target_idx - 3, target_idx)]
                        avg_volume = sum(prev_3_volumes) / len(prev_3_volumes)
                        if avg_volume > 0:
                            ratio = target_volume / avg_volume
                            if ratio >= 2.0:
                                matched_types.append('B')
                    
                    # 计算类型C: 当日为前5日成交均量的2倍及以上
                    if target_idx >= 5:
                        prev_5_volumes = [daily_data[i]['volume'] for i in range(target_idx - 5, target_idx)]
                        avg_volume = sum(prev_5_volumes) / len(prev_5_volumes)
                        if avg_volume > 0:
                            ratio = target_volume / avg_volume
                            if ratio >= 2.0:
                                matched_types.append('C')
                    
                    # 计算类型D: 前五日出现过ABC任意一种放量，标记为X日，今日的成交量为X日的1.2倍以上
                    if target_idx >= 5:
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
                                matched_types.append('D')
                    
                    # 计算类型E: 当日为前1日以及前五日均值的4倍以上（前五日未出现ABCD任何一种放量）
                    if target_idx >= 5:
                        # 检查前5天是否有ABCD任意一种放量
                        has_abcd_in_prev_5 = False
                        for i in range(max(0, target_idx - 5), target_idx):
                            check_types = VolumeTypeService._check_all_volume_types(daily_data, i)
                            if check_types and any(t in check_types for t in ['A', 'B', 'C', 'D']):
                                has_abcd_in_prev_5 = True
                                break
                        
                        if not has_abcd_in_prev_5:
                            # 前1日成交量
                            prev_volume = daily_data[target_idx - 1]['volume'] if target_idx >= 1 else 0
                            # 前5日均值
                            prev_5_volumes = [daily_data[i]['volume'] for i in range(target_idx - 5, target_idx)]
                            avg_5_volume = sum(prev_5_volumes) / len(prev_5_volumes)
                            
                            if prev_volume > 0 and avg_5_volume > 0:
                                ratio_to_prev = target_volume / prev_volume
                                ratio_to_avg5 = target_volume / avg_5_volume
                                if ratio_to_prev >= 4.0 and ratio_to_avg5 >= 4.0:
                                    matched_types.append('E')
                    
                    # 计算类型F: 前五日出现过ABCD任意一种放量，标记为X日，今日成交量为X日的3倍以上，或今日成交量为前5日成交量均值的3倍以上
                    if target_idx >= 5:
                        # 检查前5天是否有ABCD任意一种放量
                        x_day_volume = None
                        for i in range(max(0, target_idx - 5), target_idx):
                            check_types = VolumeTypeService._check_all_volume_types(daily_data, i)
                            if check_types and any(t in check_types for t in ['A', 'B', 'C', 'D']):
                                x_day_volume = daily_data[i]['volume']
                                break
                        
                        prev_5_volumes = [daily_data[i]['volume'] for i in range(target_idx - 5, target_idx)]
                        avg_5_volume = sum(prev_5_volumes) / len(prev_5_volumes)
                        
                        # 条件1: 今日成交量为X日的3倍以上
                        condition1 = False
                        if x_day_volume and x_day_volume > 0:
                            ratio = target_volume / x_day_volume
                            if ratio >= 3.0:
                                condition1 = True
                        
                        # 条件2: 今日成交量为前5日成交量均值的3倍以上
                        condition2 = False
                        if avg_5_volume > 0:
                            ratio = target_volume / avg_5_volume
                            if ratio >= 3.0:
                                condition2 = True
                        
                        if condition1 or condition2:
                            matched_types.append('F')
                    
                    # 计算类型G: 前五日中某日（设X日）出现任意一种放量（ABCD)放量，今日的量能为X日的0.7倍及以上
                    if target_idx >= 5:
                        for i in range(max(0, target_idx - 5), target_idx):
                            check_types = VolumeTypeService._check_all_volume_types(daily_data, i)
                            if check_types and any(t in check_types for t in ['A', 'B', 'C', 'D']):
                                x_day_volume = daily_data[i]['volume']
                                if x_day_volume > 0:
                                    ratio = target_volume / x_day_volume
                                    if ratio >= 0.7:
                                        matched_types.append('G')
                                        break
                    
                    # 计算类型H: 前五日中某日（设X日）出现任意一种放量（ABCD)放量，今日的量能大于X日
                    if target_idx >= 5:
                        for i in range(max(0, target_idx - 5), target_idx):
                            check_types = VolumeTypeService._check_all_volume_types(daily_data, i)
                            if check_types and any(t in check_types for t in ['A', 'B', 'C', 'D']):
                                x_day_volume = daily_data[i]['volume']
                                if target_volume > x_day_volume:
                                    matched_types.append('H')
                                    break
                    
                    # 计算类型X: 当日为前3日成交均量的1.5倍及以上
                    if target_idx >= 3:
                        prev_3_volumes = [daily_data[i]['volume'] for i in range(target_idx - 3, target_idx)]
                        avg_volume = sum(prev_3_volumes) / len(prev_3_volumes)
                        if avg_volume > 0:
                            ratio = target_volume / avg_volume
                            if ratio >= 1.5:
                                matched_types.append('X')
                    
                    # 计算类型Y: 当日为前5日成交均量的1.5倍及以上
                    if target_idx >= 5:
                        prev_5_volumes = [daily_data[i]['volume'] for i in range(target_idx - 5, target_idx)]
                        avg_volume = sum(prev_5_volumes) / len(prev_5_volumes)
                        if avg_volume > 0:
                            ratio = target_volume / avg_volume
                            if ratio >= 1.5:
                                matched_types.append('Y')
                    
                    # 计算类型Z: 前10日出现出现过（ABC）任何一种放量，且昨日量能相较于前三日均量出现1.3倍以上的放量，今日的量相较于昨日能量能的1.08倍以上
                    if target_idx >= 10:
                        # 检查前10天是否有ABC任意一种放量
                        has_abc_in_prev_10 = False
                        for i in range(max(0, target_idx - 10), target_idx):
                            check_types = VolumeTypeService._check_abc_volume_type(daily_data, i)
                            if check_types in ['A', 'B', 'C']:
                                has_abc_in_prev_10 = True
                                break
                        
                        if has_abc_in_prev_10 and target_idx >= 4:
                            # 昨日量能
                            yesterday_volume = daily_data[target_idx - 1]['volume']
                            # 前3日均量（不包括昨日）
                            prev_3_volumes = [daily_data[i]['volume'] for i in range(target_idx - 4, target_idx - 1)]
                            avg_3_volume = sum(prev_3_volumes) / len(prev_3_volumes)
                            
                            # 条件1: 昨日量能相较于前三日均量出现1.3倍以上的放量
                            condition1 = False
                            if avg_3_volume > 0:
                                ratio = yesterday_volume / avg_3_volume
                                if ratio >= 1.3:
                                    condition1 = True
                            
                            # 条件2: 今日的量相较于昨日能量能的1.08倍以上
                            condition2 = False
                            if yesterday_volume > 0:
                                ratio = target_volume / yesterday_volume
                                if ratio >= 1.08:
                                    condition2 = True
                            
                            if condition1 and condition2:
                                matched_types.append('Z')
                    
                    # 返回所有匹配的类型，用逗号连接（按A、B、C、D、E、F、G、H、X、Y、Z的顺序）
                    if matched_types:
                        # 去重并保持顺序
                        seen = set()
                        unique_types = []
                        for t in ['A', 'B', 'C', 'D', 'E', 'F', 'G', 'H', 'X', 'Y', 'Z']:
                            if t in matched_types and t not in seen:
                                unique_types.append(t)
                                seen.add(t)
                        volume_type = ','.join(unique_types)
                        result[target_date_obj] = volume_type
                
                return result
                
        except Exception as e:
            logger.error(f"批量计算成交量类型失败: {table_name}: {e}", exc_info=True)
            return {}

