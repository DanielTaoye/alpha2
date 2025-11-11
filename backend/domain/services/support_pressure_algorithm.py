"""支撑压力线计算算法"""
from typing import List, Optional, Tuple, Dict
from dataclasses import dataclass, field
from domain.models.kline import KLineData
from infrastructure.logging.logger import get_logger

logger = get_logger(__name__)


@dataclass
class IndexedLine:
    """带索引的价格线"""
    index: int  # 在K线数组中的索引
    price: float  # 价格


@dataclass
class SupportLinesResult:
    """支撑压力线计算结果"""
    last_support: Optional[float]  # 上一支撑位
    support: Optional[float]  # 当前支撑位
    pressure: Optional[float]  # 当前压力位
    last_pressure: Optional[float]  # 上一压力位
    direction: int  # 趋势方向：-1=反转，0=震荡，1=反弹
    debug_info: Optional[Dict] = field(default=None)  # 调试信息（仅30分钟K线使用）


class ExtremeValueAlgorithm:
    """极值点计算算法"""
    
    @staticmethod
    def calculate_extreme_points(
        klines: List[KLineData],
        window_size: int,
        peak_enabled: bool = True,
        valley_enabled: bool = True,
        use_min_max: bool = False,
        side_ignored_count: int = 0
    ) -> List[IndexedLine]:
        """
        计算极值点（波峰和波谷）
        
        Args:
            klines: K线数据列表（按时间倒序，最新在前）
            window_size: 窗口大小
            peak_enabled: 是否查找波峰
            valley_enabled: 是否查找波谷
            use_min_max: 是否使用最高最低价，否则使用收盘价
            side_ignored_count: 忽略边缘数据数量
            
        Returns:
            极值点列表
        """
        if len(klines) < window_size:
            return []
        
        half_window = window_size // 2
        result = []
        
        # 提取价格数组
        high_values = [k.high for k in klines]
        low_values = [k.low for k in klines]
        close_values = [k.close for k in klines]
        
        # 查找波峰
        if peak_enabled:
            for i in range(half_window, len(klines) - half_window):
                if i < side_ignored_count:
                    continue
                
                # 获取当前点的价格
                current_price = high_values[i] if use_min_max else max(klines[i].open, klines[i].close)
                
                # 检查是否是波峰
                is_peak = True
                for j in range(max(0, i - half_window), min(len(klines), i + half_window + 1)):
                    if j == i:
                        continue
                    compare_price = high_values[j] if use_min_max else max(klines[j].open, klines[j].close)
                    if current_price < compare_price:
                        is_peak = False
                        break
                
                if is_peak:
                    result.append(IndexedLine(index=i, price=current_price))
        
        # 查找波谷
        if valley_enabled:
            for i in range(half_window, len(klines) - half_window):
                if i < side_ignored_count:
                    continue
                
                # 获取当前点的价格
                current_price = low_values[i] if use_min_max else min(klines[i].open, klines[i].close)
                
                # 检查是否是波谷
                is_valley = True
                for j in range(max(0, i - half_window), min(len(klines), i + half_window + 1)):
                    if j == i:
                        continue
                    compare_price = low_values[j] if use_min_max else min(klines[j].open, klines[j].close)
                    if current_price > compare_price:
                        is_valley = False
                        break
                
                if is_valley:
                    result.append(IndexedLine(index=i, price=current_price))
        
        # 按索引排序
        result.sort(key=lambda x: x.index)
        return result
    
    @staticmethod
    def calculate_extreme_points_asymmetric(
        klines: List[KLineData],
        left_window: int,
        right_window: int,
        peak_enabled: bool = True,
        valley_enabled: bool = True,
        use_min_max: bool = False,
        side_ignored_count: int = 0
    ) -> List[IndexedLine]:
        """
        使用不对称窗口计算极值点
        
        Args:
            klines: K线数据列表
            left_window: 左侧窗口大小
            right_window: 右侧窗口大小
            peak_enabled: 是否查找波峰
            valley_enabled: 是否查找波谷
            use_min_max: 是否使用最高最低价
            side_ignored_count: 忽略边缘数据数量
            
        Returns:
            极值点列表
        """
        if len(klines) < (left_window + right_window):
            return []
        
        result = []
        start_index = left_window // 2
        
        # 提取价格数组
        high_values = [k.high for k in klines]
        low_values = [k.low for k in klines]
        close_values = [k.close for k in klines]
        
        # 查找波峰
        if peak_enabled:
            for i in range(start_index, len(klines) - 2):
                if i < side_ignored_count:
                    continue
                
                # 使用最高价判断波峰（use_min_max=False时用max(open, close)）
                current_price = high_values[i] if use_min_max else max(klines[i].open, klines[i].close)
                
                is_peak = True
                # 窗口范围：从 i - right_window（未来，索引更小）到 i + left_window（历史，索引更大）
                # 注意：K线数据是倒序的（最新在前），所以 i 越小越新，i 越大越旧
                window_start = max(0, i - right_window)
                window_end = min(len(klines), i + left_window + 1)
                
                for j in range(window_start, window_end):
                    if j == i:
                        continue
                    compare_price = high_values[j] if use_min_max else max(klines[j].open, klines[j].close)
                    if current_price < compare_price:
                        is_peak = False
                        break
                
                if is_peak:
                    result.append(IndexedLine(index=i, price=current_price))
        
        # 查找波谷
        if valley_enabled:
            for i in range(start_index, len(klines) - 2):
                if i < side_ignored_count:
                    continue
                
                # 使用最低价判断波谷（use_min_max=False时用min(open, close)）
                current_price = low_values[i] if use_min_max else min(klines[i].open, klines[i].close)
                
                is_valley = True
                # 窗口范围：从 i - right_window（未来，索引更小）到 i + left_window（历史，索引更大）
                window_start = max(0, i - right_window)
                window_end = min(len(klines), i + left_window + 1)
                
                for j in range(window_start, window_end):
                    if j == i:
                        continue
                    compare_price = low_values[j] if use_min_max else min(klines[j].open, klines[j].close)
                    if current_price > compare_price:
                        is_valley = False
                        break
                
                if is_valley:
                    result.append(IndexedLine(index=i, price=current_price))
        
        # 按索引排序
        result.sort(key=lambda x: x.index)
        return result


class ClusterAlgorithm:
    """聚类算法用于筛选有效支撑压力位（基于最小间隔分割和欧氏距离）"""
    
    @staticmethod
    def _calculate_euclidean_distance(p1: IndexedLine, p2: IndexedLine) -> float:
        """计算两点之间的欧氏距离（考虑价格和索引）"""
        price_diff = abs(p1.price - p2.price)
        index_diff = abs(p1.index - p2.index)
        # 归一化索引差异（假设索引差异1对应价格差异的某个比例）
        # 这里简化处理，主要考虑价格差异
        return (price_diff ** 2 + (index_diff * 0.01) ** 2) ** 0.5
    
    @staticmethod
    def _find_min_gap(points: List[IndexedLine]) -> float:
        """找到点之间的最小间隔"""
        if len(points) < 2:
            return float('inf')
        
        # 按价格排序
        sorted_points = sorted(points, key=lambda x: x.price)
        gaps = []
        for i in range(len(sorted_points) - 1):
            gap = abs(sorted_points[i + 1].price - sorted_points[i].price)
            gaps.append(gap)
        
        return min(gaps) if gaps else float('inf')
    
    @staticmethod
    def _cluster_by_gap(points: List[IndexedLine], min_gap: float) -> List[List[IndexedLine]]:
        """
        按最小间隔分割成聚类
        
        Args:
            points: 极值点列表（已按价格排序）
            min_gap: 最小间隔阈值
            
        Returns:
            聚类列表，每个聚类是一个点列表
        """
        if not points:
            return []
        
        # 按价格排序
        sorted_points = sorted(points, key=lambda x: x.price)
        clusters = []
        current_cluster = [sorted_points[0]]
        
        for i in range(1, len(sorted_points)):
            gap = abs(sorted_points[i].price - sorted_points[i - 1].price)
            if gap <= min_gap * 1.5:  # 允许1.5倍的最小间隔作为同一聚类
                current_cluster.append(sorted_points[i])
            else:
                # 开始新的聚类
                clusters.append(current_cluster)
                current_cluster = [sorted_points[i]]
        
        if current_cluster:
            clusters.append(current_cluster)
        
        return clusters
    
    @staticmethod
    def _calculate_cluster_center(cluster: List[IndexedLine], current_price: float) -> float:
        """
        计算聚类的中心点（加权平均，距离当前价格越近权重越大）
        
        Args:
            cluster: 聚类点列表
            current_price: 当前价格
            
        Returns:
            聚类中心价格
        """
        if not cluster:
            return 0.0
        
        if len(cluster) == 1:
            return cluster[0].price
        
        # 计算权重：距离当前价格越近，权重越大
        weights = []
        prices = []
        for point in cluster:
            distance = abs(point.price - current_price)
            # 权重 = 1 / (1 + distance)，距离越近权重越大
            weight = 1.0 / (1.0 + distance * 0.1)
            weights.append(weight)
            prices.append(point.price)
        
        # 加权平均
        total_weight = sum(weights)
        if total_weight == 0:
            return sum(prices) / len(prices)  # 简单平均
        
        weighted_sum = sum(p * w for p, w in zip(prices, weights))
        return weighted_sum / total_weight
    
    @staticmethod
    def _select_lines_from_clusters(
        clusters: List[List[IndexedLine]],
        current_price: float,
        direction: int,
        is_support: bool
    ) -> List[float]:
        """
        从聚类中选择有效的支撑/压力位
        
        Args:
            clusters: 聚类列表
            current_price: 当前价格
            direction: 趋势方向：-1=反转，0=震荡，1=反弹
            is_support: 是否为支撑位（True=支撑，False=压力）
            
        Returns:
            选中的价格列表（按距离当前价格从近到远排序）
        """
        if not clusters:
            return []
        
        # 计算每个聚类的中心点
        cluster_centers = []
        for cluster in clusters:
            center = ClusterAlgorithm._calculate_cluster_center(cluster, current_price)
            cluster_centers.append({
                'center': center,
                'cluster': cluster,
                'size': len(cluster),
                'distance': abs(center - current_price)
            })
        
        # 根据趋势方向调整选择策略
        if is_support:
            # 支撑位：选择在当前价格下方的聚类
            valid_centers = [c for c in cluster_centers if c['center'] < current_price]
            # 按价格从高到低排序（最接近当前价格的在前）
            valid_centers.sort(key=lambda x: x['center'], reverse=True)
        else:
            # 压力位：选择在当前价格上方的聚类
            valid_centers = [c for c in cluster_centers if c['center'] > current_price]
            # 按价格从低到高排序（最接近当前价格的在前）
            valid_centers.sort(key=lambda x: x['center'])
        
        # 根据趋势方向调整优先级
        if direction == 1:  # 反弹趋势
            # 优先选择距离当前价格较近的聚类（已经按价格排序，最近的在前）
            pass
        elif direction == -1:  # 反转趋势
            # 优先选择距离当前价格较远的聚类（更强的支撑/压力）
            valid_centers.reverse()
        else:  # 震荡趋势（direction == 0）
            # 对于震荡趋势，优先选择距离当前价格较远的聚类（更稳定的支撑/压力）
            # 但也要考虑聚类的规模（点数多的聚类更可靠）
            # 按聚类规模和距离的综合评分排序
            for c in valid_centers:
                # 评分 = 聚类规模 * 距离，规模越大、距离越远，评分越高
                c['score'] = c['size'] * c['distance']
            valid_centers.sort(key=lambda x: x['score'], reverse=True)
        
        # 构建候选聚类信息字符串
        cluster_info = []
        for c in valid_centers[:5]:
            cluster_info.append(f"价格={c['center']:.2f}, 距离={c['distance']:.2f}, 规模={c['size']}")
        logger.info(f"【聚类选择】{'支撑' if is_support else '压力'}位候选聚类: {cluster_info}")
        
        # 返回聚类中心价格（最多返回2个）
        return [c['center'] for c in valid_centers[:2]]
    
    @staticmethod
    def pick_support_pressure_lines(
        extreme_points: List[IndexedLine],
        current_price: float,
        period_type: str = 'day',
        direction: int = 0
    ) -> Tuple[Optional[float], Optional[float], Optional[float], Optional[float]]:
        """
        从极值点中筛选出支撑压力位（使用聚类算法）
        
        算法流程：
        1. 分离支撑位和压力位候选点
        2. 计算最小间隔
        3. 按最小间隔分割成聚类
        4. 计算每个聚类的中心点
        5. 根据趋势方向选择最有效的支撑压力位
        
        Args:
            extreme_points: 极值点列表
            current_price: 当前价格
            period_type: 周期类型
            direction: 趋势方向：-1=反转，0=震荡，1=反弹
            
        Returns:
            (上一支撑位, 当前支撑位, 当前压力位, 上一压力位)
        """
        if not extreme_points:
            return (None, None, None, None)
        
        # 分离支撑位和压力位候选点
        support_points = [p for p in extreme_points if p.price < current_price]
        pressure_points = [p for p in extreme_points if p.price > current_price]
        
        # 如果候选点太少，使用简单方法
        if len(support_points) <= 2 and len(pressure_points) <= 2:
            # 简单排序选择
            support_points.sort(key=lambda x: x.price, reverse=True)
            pressure_points.sort(key=lambda x: x.price)
            
            support = support_points[0].price if len(support_points) >= 1 else None
            last_support = support_points[1].price if len(support_points) >= 2 else None
            pressure = pressure_points[0].price if len(pressure_points) >= 1 else None
            last_pressure = pressure_points[1].price if len(pressure_points) >= 2 else None
            
            return (last_support, support, pressure, last_pressure)
        
        # 使用聚类算法
        logger.info(f"【聚类算法】开始执行聚类筛选")
        logger.info(f"  支撑候选点数量: {len(support_points)}")
        logger.info(f"  压力候选点数量: {len(pressure_points)}")
        
        # 1. 计算最小间隔
        logger.info(f"【聚类算法】步骤1: 计算最小间隔")
        all_points = support_points + pressure_points
        min_gap = ClusterAlgorithm._find_min_gap(all_points)
        logger.info(f"  最小间隔: {min_gap:.4f}")
        
        # 如果最小间隔为0或无穷大，使用简单方法
        if min_gap == 0 or min_gap == float('inf'):
            logger.info(f"【聚类算法】最小间隔异常，使用简单排序方法")
            support_points.sort(key=lambda x: x.price, reverse=True)
            pressure_points.sort(key=lambda x: x.price)
            
            support = support_points[0].price if len(support_points) >= 1 else None
            last_support = support_points[1].price if len(support_points) >= 2 else None
            pressure = pressure_points[0].price if len(pressure_points) >= 1 else None
            last_pressure = pressure_points[1].price if len(pressure_points) >= 2 else None
            
            logger.info(f"【聚类算法】简单方法返回 - 支撑={support}, 上一支撑={last_support}, 压力={pressure}, 上一压力={last_pressure}")
            return (last_support, support, pressure, last_pressure)
        
        # 2. 按最小间隔分割成聚类
        logger.info(f"【聚类算法】步骤2: 按最小间隔分割成聚类")
        logger.info(f"  调用方法: ClusterAlgorithm._cluster_by_gap")
        support_clusters = ClusterAlgorithm._cluster_by_gap(support_points, min_gap)
        pressure_clusters = ClusterAlgorithm._cluster_by_gap(pressure_points, min_gap)
        
        logger.info(f"【聚类算法】聚类分割完成")
        logger.info(f"  最小间隔: {min_gap:.4f}")
        logger.info(f"  支撑聚类数: {len(support_clusters)}")
        logger.info(f"  压力聚类数: {len(pressure_clusters)}")
        for i, cluster in enumerate(support_clusters[:5]):
            logger.info(f"    支撑聚类{i+1}: {len(cluster)}个点, 价格范围: {min(p.price for p in cluster):.2f}~{max(p.price for p in cluster):.2f}")
        for i, cluster in enumerate(pressure_clusters[:5]):
            logger.info(f"    压力聚类{i+1}: {len(cluster)}个点, 价格范围: {min(p.price for p in cluster):.2f}~{max(p.price for p in cluster):.2f}")
        
        # 3. 从聚类中选择支撑压力位
        logger.info(f"【聚类算法】步骤3: 从聚类中选择支撑压力位")
        logger.info(f"  调用方法: ClusterAlgorithm._select_lines_from_clusters (支撑位)")
        support_lines = ClusterAlgorithm._select_lines_from_clusters(
            support_clusters, current_price, direction, is_support=True
        )
        logger.info(f"  调用方法: ClusterAlgorithm._select_lines_from_clusters (压力位)")
        pressure_lines = ClusterAlgorithm._select_lines_from_clusters(
            pressure_clusters, current_price, direction, is_support=False
        )
        
        logger.info(f"【聚类算法】筛选结果")
        logger.info(f"  支撑位列表: {support_lines}")
        logger.info(f"  压力位列表: {pressure_lines}")
        logger.info(f"  趋势方向: {direction}")
        
        # 4. 返回结果
        support = support_lines[0] if len(support_lines) >= 1 else None
        last_support = support_lines[1] if len(support_lines) >= 2 else None
        pressure = pressure_lines[0] if len(pressure_lines) >= 1 else None
        last_pressure = pressure_lines[1] if len(pressure_lines) >= 2 else None
        
        return (last_support, support, pressure, last_pressure)


class SupportPressureAlgorithm:
    """支撑压力线计算主算法"""
    
    def __init__(self):
        self.extreme_algorithm = ExtremeValueAlgorithm()
        self.cluster_algorithm = ClusterAlgorithm()
    
    def calculate_support_pressure_lines(
        self,
        klines: List[KLineData],
        period_type: str = 'day'
    ) -> SupportLinesResult:
        """
        计算支撑压力线
        
        Args:
            klines: K线数据列表（按时间倒序，最新在前）
            period_type: 周期类型
            
        Returns:
            支撑压力线计算结果
        """
        logger.info(f"═══════════════════════════════════════════════════════════")
        logger.info(f"【日线计算入口】calculate_support_pressure_lines")
        logger.info(f"  周期类型: {period_type}")
        logger.info(f"  K线数量: {len(klines)}")
        if klines:
            logger.info(f"  最新K线时间: {klines[0].time if hasattr(klines[0], 'time') else 'N/A'}")
            logger.info(f"  最新收盘价: {klines[0].close}")
            logger.info(f"  最旧K线时间: {klines[-1].time if hasattr(klines[-1], 'time') else 'N/A'}")
            logger.info(f"  最旧收盘价: {klines[-1].close}")
        
        if not klines or len(klines) < 20:
            logger.warning(f"【日线计算】K线数据不足，返回空结果")
            return SupportLinesResult(
                last_support=None,
                support=None,
                pressure=None,
                last_pressure=None,
                direction=0
            )
        
        # 30分钟K线特殊处理
        if period_type == '30min':
            logger.info(f"【日线计算】30分钟K线，使用30分钟算法")
            return self._calculate_for_30min(klines)
        
        current_price = klines[0].close
        
        # 判断市场状态
        logger.info(f"【日线计算】判断市场状态（检查近300日）...")
        is_new_top = self._is_new_top(klines, 300)
        is_new_bottom = self._is_new_bottom(klines, 300)
        
        logger.info(f"【日线算法选择】周期={period_type}, 创新高={is_new_top}, 创新低={is_new_bottom}, 当前价格={current_price}")
        
        if is_new_top:
            logger.info(f"【日线算法】使用创新高算法")
            return self._calculate_for_new_top(klines, period_type)
        elif is_new_bottom:
            logger.info(f"【日线算法】使用创新低算法")
            return self._calculate_for_new_bottom(klines, period_type)
        else:
            logger.info(f"【日线算法】使用常规震荡算法（聚类算法）")
            return self._calculate_for_normal(klines, period_type)
    
    def _is_new_top(self, klines: List[KLineData], period: int) -> bool:
        """
        判断是否创新高（突破近period日新高）
        
        逻辑：判断最新一天的最高价是否大于等于近period日（不包括最新一天）的最高价
        """
        if len(klines) < period + 1:
            return False
        
        # 近period日的最高价（不包括最新一天，从索引1开始）
        period_high = max(k.high for k in klines[1:period+1])
        # 最新一天的最高价
        latest_high = klines[0].high
        
        return latest_high >= period_high
    
    def _is_new_bottom(self, klines: List[KLineData], period: int) -> bool:
        """
        判断是否创新低（跌破近period日新低）
        
        逻辑：判断最新一天的最低价是否小于等于近period日（不包括最新一天）的最低价
        """
        if len(klines) < period + 1:
            return False
        
        # 近period日的最低价（不包括最新一天，从索引1开始）
        period_low = min(k.low for k in klines[1:period+1])
        # 最新一天的最低价
        latest_low = klines[0].low
        
        return latest_low <= period_low
    
    def _calculate_for_new_top(
        self,
        klines: List[KLineData],
        period_type: str
    ) -> SupportLinesResult:
        """创新高算法：只计算支撑位"""
        current_price = klines[0].close
        
        # 判断是否创新高
        is_new_top = self._is_new_top(klines, 300)
        recent_300_max = max(k.high for k in klines[:300]) if len(klines) >= 300 else max(k.high for k in klines)
        latest_high = klines[0].high
        
        extreme_points = self.extreme_algorithm.calculate_extreme_points_asymmetric(
            klines,
            left_window=12,
            right_window=4,
            peak_enabled=False,  # 不找波峰
            valley_enabled=True,  # 只找波谷
            use_min_max=False,
            side_ignored_count=0
        )
        
        # 获取所有极值点价格
        extreme_values = [p.price for p in extreme_points]
        extreme_points_detail = [{'index': p.index, 'price': p.price} for p in extreme_points]
        
        last_support, support, _, _ = self.cluster_algorithm.pick_support_pressure_lines(
            extreme_points, current_price, period_type, 0
        )
        
        # 调试信息
        debug_info = {
            'algorithm': '创新高算法',
            'is_new_top': is_new_top,
            'recent_300_max': recent_300_max,
            'latest_high': latest_high,
            'window_left': 12,
            'window_right': 4,
            'current_price': current_price,
            'kline_count': len(klines),
            'extreme_points_count': len(extreme_points),
            'extreme_values': extreme_values[:10],  # 只显示前10个
            'extreme_points': extreme_points_detail[:10],
            'support_candidates': [p.price for p in extreme_points if p.price < current_price][:5]
        }
        
        return SupportLinesResult(
            last_support=last_support,
            support=support,
            pressure=None,
            last_pressure=None,
            direction=0,
            debug_info=debug_info
        )
    
    def _calculate_for_new_bottom(
        self,
        klines: List[KLineData],
        period_type: str
    ) -> SupportLinesResult:
        """创新低算法：只计算压力位"""
        current_price = klines[0].close
        
        # 判断是否创新低
        is_new_bottom = self._is_new_bottom(klines, 300)
        recent_300_min = min(k.low for k in klines[:300]) if len(klines) >= 300 else min(k.low for k in klines)
        latest_low = klines[0].low
        
        extreme_points = self.extreme_algorithm.calculate_extreme_points_asymmetric(
            klines,
            left_window=4,
            right_window=12,
            peak_enabled=True,  # 只找波峰
            valley_enabled=False,  # 不找波谷
            use_min_max=False,
            side_ignored_count=0
        )
        
        # 获取所有极值点价格
        extreme_values = [p.price for p in extreme_points]
        extreme_points_detail = [{'index': p.index, 'price': p.price} for p in extreme_points]
        
        _, _, pressure, last_pressure = self.cluster_algorithm.pick_support_pressure_lines(
            extreme_points, current_price, period_type, 0
        )
        
        # 调试信息
        debug_info = {
            'algorithm': '创新低算法',
            'is_new_bottom': is_new_bottom,
            'recent_300_min': recent_300_min,
            'latest_low': latest_low,
            'window_left': 4,
            'window_right': 12,
            'current_price': current_price,
            'kline_count': len(klines),
            'extreme_points_count': len(extreme_points),
            'extreme_values': extreme_values[:10],  # 只显示前10个
            'extreme_points': extreme_points_detail[:10],
            'pressure_candidates': [p.price for p in extreme_points if p.price > current_price][:5]
        }
        
        return SupportLinesResult(
            last_support=None,
            support=None,
            pressure=pressure,
            last_pressure=last_pressure,
            direction=0,
            debug_info=debug_info
        )
    
    def _calculate_for_30min(
        self,
        klines: List[KLineData]
    ) -> SupportLinesResult:
        """30分钟K线计算：根据趋势方向选择不同算法"""
        # 判断大趋势方向
        direction = self._get_big_trend_direction(klines)
        
        # 收集中间变量（包含趋势判断的详细信息）
        # 只检查最近30个周期，与趋势判断保持一致
        check_periods = min(30, len(klines) - 10) if len(klines) >= 10 else 0
        trending_up_count = self._get_trending_up_count_for_ma(klines, 10, check_periods)
        trending_down_count = self._get_trending_down_count_for_ma(klines, 10, check_periods)
        peak_prices = self._get_peak_prices(klines, 6, strict=True)
        valley_prices = self._get_valley_prices(klines, 6, strict=True)
        
        debug_info = {
            'trend_direction': direction,
            'trend_direction_text': {1: '上涨', -1: '下跌', 0: '震荡'}.get(direction, '未知'),
            'current_price': klines[0].close,
            'kline_count': len(klines),
            'ma_trending_up_count': trending_up_count,
            'ma_trending_down_count': trending_down_count,
            'peak_prices_count': len(peak_prices),
            'valley_prices_count': len(valley_prices),
            'peak_prices_sample': peak_prices[:5] if len(peak_prices) > 0 else [],
            'valley_prices_sample': valley_prices[:5] if len(valley_prices) > 0 else []
        }
        
        if direction == 1:
            # 明显上涨趋势：使用趋势算法（只找压力位）
            result = self._calculate_for_30min_trend(klines, is_trending_up=True, is_trending_down=False, base_debug_info=debug_info)
            return result
        elif direction == -1:
            # 明显下跌趋势：使用趋势算法（只找支撑位）
            result = self._calculate_for_30min_trend(klines, is_trending_up=False, is_trending_down=True, base_debug_info=debug_info)
            return result
        else:
            # 震荡状态：使用双近算法
            result = self._calculate_for_30min_double_near(klines, base_debug_info=debug_info)
            return result
    
    def _get_big_trend_direction(self, klines: List[KLineData]) -> int:
        """
        判断大趋势方向（30分钟K线专用）
        返回：1=上涨，-1=下跌，0=震荡
        """
        if len(klines) < 30:
            return 0
        
        # 1. 检查10均线上涨/下跌周期数（只看最近30个周期）
        # 只检查最近30个周期的均线趋势，而不是所有周期
        check_periods = min(30, len(klines) - 10)  # 最多检查30个周期
        trending_up_count = self._get_trending_up_count_for_ma(klines, 10, check_periods)
        trending_down_count = self._get_trending_down_count_for_ma(klines, 10, check_periods)
        
        logger.debug(f"30分钟趋势判断 - 检查最近{check_periods}个周期，均线上涨周期数: {trending_up_count}, "
                    f"下跌周期数: {trending_down_count}")
        
        # 检查是否明显上涨或下跌（最近30个周期中，均线周期数>20）
        if trending_up_count > 20:
            logger.debug(f"判断为上涨趋势（最近{check_periods}个周期中，均线上涨周期>{trending_up_count}>20）")
            return 1
        if trending_down_count > 20:
            logger.debug(f"判断为下跌趋势（最近{check_periods}个周期中，均线下跌周期>{trending_down_count}>20）")
            return -1
        
        # 2. 检查连续波峰递减（下跌趋势）
        # 注意：peak_prices是按时间倒序的（最新的在前），所以peak_prices[0]是最新的波峰
        # 如果最新的波峰 < 第二新的波峰 < 第三新的波峰，说明波峰在递减（价格在下跌）
        peak_prices = self._get_peak_prices(klines, 6, strict=True)
        logger.debug(f"波峰价格（最新的在前）: {peak_prices[:5] if len(peak_prices) > 0 else '无'}")
        if len(peak_prices) > 3:
            if peak_prices[0] < peak_prices[1] and peak_prices[1] < peak_prices[2]:
                logger.debug(f"判断为下跌趋势（连续波峰递减）: {peak_prices[:3]}")
                return -1
        
        # 3. 检查连续波谷递增（上涨趋势）
        # 注意：valley_prices是按时间倒序的（最新的在前），所以valley_prices[0]是最新的波谷
        # 如果最新的波谷 > 第二新的波谷 > 第三新的波谷，说明波谷在递增（价格在上涨）
        valley_prices = self._get_valley_prices(klines, 6, strict=True)
        logger.debug(f"波谷价格（最新的在前）: {valley_prices[:5] if len(valley_prices) > 0 else '无'}")
        if len(valley_prices) > 3:
            if valley_prices[0] > valley_prices[1] and valley_prices[1] > valley_prices[2]:
                logger.debug(f"判断为上涨趋势（连续波谷递增）: {valley_prices[:3]}")
                return 1
        
        logger.debug("判断为震荡趋势")
        return 0
    
    def _get_trending_up_count_for_ma(self, klines: List[KLineData], ma_period: int, max_periods: int = None) -> int:
        """
        计算均线上涨周期数
        K线数据是倒序的（最新在前），所以：
        - klines[0] 是最新的
        - klines[i] 比 klines[i+1] 更新
        - 比较 ma[i] 和 ma[i+1]，如果 ma[i] > ma[i+1]，说明均线上涨
        
        Args:
            klines: K线数据列表（倒序，最新在前）
            ma_period: 均线周期
            max_periods: 最多检查的周期数（默认检查所有周期）
        """
        if len(klines) < ma_period + 1:
            return 0
        
        # 只检查最近max_periods个周期
        total_periods = len(klines) - ma_period
        if max_periods is not None:
            check_count = min(max_periods, total_periods)
        else:
            check_count = total_periods
        
        count = 0
        ma_details = []  # 记录详细的均线计算过程
        
        # 从最新到最旧遍历，只检查最近check_count个周期
        for i in range(check_count):
            # 计算当前均线（从索引i开始的ma_period个K线，包含更新的K线）
            ma_current = sum(k.close for k in klines[i:i+ma_period]) / ma_period
            # 计算前一个均线（从索引i+1开始的ma_period个K线，包含更旧的K线）
            ma_prev = sum(k.close for k in klines[i+1:i+ma_period+1]) / ma_period
            
            # 如果当前均线（更新）大于前一个均线（更旧），说明均线上涨
            is_up = ma_current > ma_prev
            if is_up:
                count += 1
                # 记录前20个上涨周期的详细信息
                if len(ma_details) < 20:
                    ma_details.append({
                        'index': i,
                        'ma_current': ma_current,
                        'ma_prev': ma_prev,
                        'diff': ma_current - ma_prev,
                        'current_close': klines[i].close,
                        'prev_close': klines[i+1].close if i+1 < len(klines) else None
                    })
        
        # 如果上涨周期数>20，打印详细信息
        if count > 20:
            logger.info(f"【10均线上涨周期数检查】检查最近{check_count}个周期，上涨周期数={count} > 20，判断为上涨趋势")
            logger.info(f"【均线计算详情】前20个上涨周期的均线值：")
            for detail in ma_details:
                prev_close_str = f"{detail['prev_close']:.2f}" if detail['prev_close'] is not None else 'N/A'
                logger.info(f"  索引{detail['index']}: MA当前={detail['ma_current']:.2f}, MA前一个={detail['ma_prev']:.2f}, "
                          f"差值={detail['diff']:.2f}, 当前收盘={detail['current_close']:.2f}, "
                          f"前一个收盘={prev_close_str}")
            # 打印前几个和后几个K线的收盘价，帮助理解数据顺序
            logger.info(f"【K线数据顺序验证】前5个K线收盘价（最新在前）: "
                       f"{[k.close for k in klines[:5]]}")
            logger.info(f"【K线数据顺序验证】后5个K线收盘价（最旧在后）: "
                       f"{[k.close for k in klines[-5:]]}")
        
        return count
    
    def _get_trending_down_count_for_ma(self, klines: List[KLineData], ma_period: int, max_periods: int = None) -> int:
        """
        计算均线下跌周期数
        K线数据是倒序的（最新在前），所以：
        - klines[0] 是最新的
        - klines[i] 比 klines[i+1] 更新
        - 比较 ma[i] 和 ma[i+1]，如果 ma[i] < ma[i+1]，说明均线下跌
        
        Args:
            klines: K线数据列表（倒序，最新在前）
            ma_period: 均线周期
            max_periods: 最多检查的周期数（默认检查所有周期）
        """
        if len(klines) < ma_period + 1:
            return 0
        
        # 只检查最近max_periods个周期
        total_periods = len(klines) - ma_period
        if max_periods is not None:
            check_count = min(max_periods, total_periods)
        else:
            check_count = total_periods
        
        count = 0
        ma_details = []  # 记录详细的均线计算过程
        
        # 从最新到最旧遍历，只检查最近check_count个周期
        for i in range(check_count):
            # 计算当前均线（从索引i开始的ma_period个K线，包含更新的K线）
            ma_current = sum(k.close for k in klines[i:i+ma_period]) / ma_period
            # 计算前一个均线（从索引i+1开始的ma_period个K线，包含更旧的K线）
            ma_prev = sum(k.close for k in klines[i+1:i+ma_period+1]) / ma_period
            
            # 如果当前均线（更新）小于前一个均线（更旧），说明均线下跌
            is_down = ma_current < ma_prev
            if is_down:
                count += 1
                # 记录前20个下跌周期的详细信息
                if len(ma_details) < 20:
                    ma_details.append({
                        'index': i,
                        'ma_current': ma_current,
                        'ma_prev': ma_prev,
                        'diff': ma_current - ma_prev,
                        'current_close': klines[i].close,
                        'prev_close': klines[i+1].close if i+1 < len(klines) else None
                    })
        
        # 如果下跌周期数>20，打印详细信息
        if count > 20:
            logger.info(f"【10均线下跌周期数检查】检查最近{check_count}个周期，下跌周期数={count} > 20，判断为下跌趋势")
            logger.info(f"【均线计算详情】前20个下跌周期的均线值：")
            for detail in ma_details:
                prev_close_str = f"{detail['prev_close']:.2f}" if detail['prev_close'] is not None else 'N/A'
                logger.info(f"  索引{detail['index']}: MA当前={detail['ma_current']:.2f}, MA前一个={detail['ma_prev']:.2f}, "
                          f"差值={detail['diff']:.2f}, 当前收盘={detail['current_close']:.2f}, "
                          f"前一个收盘={prev_close_str}")
        
        return count
    
    def _get_peak_prices(self, klines: List[KLineData], half_window: int, strict: bool = True) -> List[float]:
        """
        获取波峰价格列表（按时间倒序，最新的在前）
        使用最高价（high）判断波峰
        """
        if len(klines) < half_window * 2:
            return []
        
        peak_prices = []
        high_values = [k.high for k in klines]
        
        # 从前往后遍历（i越小越新），确保最新的在前
        for i in range(half_window, len(klines) - half_window):
            if strict and i < 10:  # 忽略边缘
                continue
            
            current_price = high_values[i]
            is_peak = True
            
            # 在窗口范围内检查是否是最高点
            for j in range(max(0, i - half_window), min(len(klines), i + half_window + 1)):
                if j == i:
                    continue
                if current_price < high_values[j]:
                    is_peak = False
                    break
            
            if is_peak:
                peak_prices.append(current_price)  # 按时间顺序添加（最新的先添加）
        
        return peak_prices  # 返回时已经是时间倒序（最新的在前）
    
    def _get_valley_prices(self, klines: List[KLineData], half_window: int, strict: bool = True) -> List[float]:
        """
        获取波谷价格列表（按时间倒序，最新的在前）
        使用最低价（low）判断波谷
        """
        if len(klines) < half_window * 2:
            return []
        
        valley_prices = []
        low_values = [k.low for k in klines]
        
        # 从前往后遍历（i越小越新），确保最新的在前
        for i in range(half_window, len(klines) - half_window):
            if strict and i < 10:  # 忽略边缘
                continue
            
            current_price = low_values[i]
            is_valley = True
            
            # 在窗口范围内检查是否是最低点
            for j in range(max(0, i - half_window), min(len(klines), i + half_window + 1)):
                if j == i:
                    continue
                if current_price > low_values[j]:
                    is_valley = False
                    break
            
            if is_valley:
                valley_prices.append(current_price)  # 按时间顺序添加（最新的先添加）
        
        return valley_prices  # 返回时已经是时间倒序（最新的在前）
    
    def _calculate_for_30min_trend(
        self,
        klines: List[KLineData],
        is_trending_up: bool,
        is_trending_down: bool,
        base_debug_info: Optional[Dict] = None
    ) -> SupportLinesResult:
        """30分钟趋势算法（上涨或下跌趋势）"""
        current_price = klines[0].close
        
        if is_trending_up:
            # 上涨趋势：使用不对称窗口（左12右6），只找波峰（压力位）
            # 注意：在Java代码中，pastWindowSize=12, futureWindowSize=6
            # pastWindowSize是历史窗口（向前看，索引更大），futureWindowSize是未来窗口（向后看，索引更小）
            extreme_points = self.extreme_algorithm.calculate_extreme_points_asymmetric(
                klines,
                left_window=12,  # pastWindowSize（历史窗口）
                right_window=6,  # futureWindowSize（未来窗口）
                peak_enabled=True,   # 只找波峰
                valley_enabled=False,  # 不找波谷
                use_min_max=False,
                side_ignored_count=10
            )
        elif is_trending_down:
            # 下跌趋势：使用不对称窗口（左6右12），只找波谷（支撑位）
            extreme_points = self.extreme_algorithm.calculate_extreme_points_asymmetric(
                klines,
                left_window=6,   # pastWindowSize（历史窗口）
                right_window=12,  # futureWindowSize（未来窗口）
                peak_enabled=False,  # 不找波峰
                valley_enabled=True,  # 只找波谷
                use_min_max=False,
                side_ignored_count=10
            )
        else:
            return SupportLinesResult(None, None, None, None, 0)
        
        # 获取极值点价格（按索引排序，索引越小越新）
        extreme_values = [p.price for p in sorted(extreme_points, key=lambda x: x.index)]
        extreme_points_detail = [{'index': p.index, 'price': p.price} for p in sorted(extreme_points, key=lambda x: x.index)]
        
        logger.debug(f"30分钟趋势算法 - 当前价格: {current_price}, 极值点数量: {len(extreme_values)}, "
                    f"极值点: {extreme_values[:5] if len(extreme_values) > 5 else extreme_values}")
        
        # 筛选候选支撑位和压力位（各取前2个）
        candidate_support_lines = []
        candidate_pressure_lines = []
        
        for price in extreme_values:
            if price < current_price and len(candidate_support_lines) < 2:
                candidate_support_lines.append(price)
            if price > current_price and len(candidate_pressure_lines) < 2:
                candidate_pressure_lines.append(price)
        
        logger.debug(f"候选支撑位: {candidate_support_lines}, 候选压力位: {candidate_pressure_lines}")
        
        # 获取支撑位和压力位
        support = None
        pressure = None
        
        if candidate_support_lines:
            # 取最大的（最接近当前价格）
            support = max(candidate_support_lines)
        
        if candidate_pressure_lines:
            # 取最小的（最接近当前价格）
            pressure = min(candidate_pressure_lines)
        
        logger.debug(f"最终结果 - 支撑位: {support}, 压力位: {pressure}")
        
        # 更新调试信息
        debug_info = {
            'algorithm': '趋势算法',
            'trend_type': '上涨' if is_trending_up else '下跌',
            'window_left': 12 if is_trending_up else 6,
            'window_right': 6 if is_trending_up else 12,
            'side_ignored_count': 10,
            'extreme_points_count': len(extreme_points),
            'extreme_points': extreme_points_detail[:10],  # 只显示前10个
            'extreme_values': extreme_values[:10],  # 只显示前10个
            'candidate_support_lines': candidate_support_lines,
            'candidate_pressure_lines': candidate_pressure_lines,
            'current_price': current_price
        }
        
        # 合并基础调试信息
        if base_debug_info:
            debug_info.update(base_debug_info)
        
        result = SupportLinesResult(
            last_support=None,
            support=support,
            pressure=pressure,
            last_pressure=None,
            direction=1 if is_trending_up else -1,
            debug_info=debug_info
        )
            
        return result
    
    def _calculate_for_30min_double_near(
        self,
        klines: List[KLineData],
        base_debug_info: Optional[Dict] = None
    ) -> SupportLinesResult:
        """30分钟双近算法（震荡状态）"""
        current_price = klines[0].close
        
        # 第一窗口（半径15）计算波峰波谷
        peeks_first = self._get_peak_prices(klines, 15, strict=True)
        valleys_first = self._get_valley_prices(klines, 15, strict=True)
        
        # 第二窗口（半径13）计算波峰波谷
        peeks_second = self._get_peak_prices(klines, 13, strict=True)
        valleys_second = self._get_valley_prices(klines, 13, strict=True)
        
        # 过滤：只保留当前价格上方的波峰和下方的波谷
        peeks_first = [p for p in peeks_first if p > current_price]
        valleys_first = [p for p in valleys_first if p < current_price]
        peeks_second = [p for p in peeks_second if p > current_price]
        valleys_second = [p for p in valleys_second if p < current_price]
        
        # 获取第一窗口的支撑压力位
        last_support_price = valleys_first[1] if len(valleys_first) >= 2 else None
        support_price = valleys_first[0] if len(valleys_first) >= 1 else None
        pressure_price = peeks_first[0] if len(peeks_first) >= 1 else None
        last_pressure_price = peeks_first[1] if len(peeks_first) >= 2 else None
        
        # 获取第二窗口的支撑压力位
        last_support_price2 = valleys_second[1] if len(valleys_second) >= 2 else None
        support_price2 = valleys_second[0] if len(valleys_second) >= 1 else None
        pressure_price2 = peeks_second[0] if len(peeks_second) >= 1 else None
        last_pressure_price2 = peeks_second[1] if len(peeks_second) >= 2 else None
        
        # 合并所有支撑位和压力位（去重）
        support_prices_set = set()
        if support_price is not None:
            support_prices_set.add(support_price)
        if last_support_price is not None:
            support_prices_set.add(last_support_price)
        if support_price2 is not None:
            support_prices_set.add(support_price2)
        if last_support_price2 is not None:
            support_prices_set.add(last_support_price2)
        support_prices = list(support_prices_set)
        
        pressure_prices_set = set()
        if pressure_price is not None:
            pressure_prices_set.add(pressure_price)
        if last_pressure_price is not None:
            pressure_prices_set.add(last_pressure_price)
        if pressure_price2 is not None:
            pressure_prices_set.add(pressure_price2)
        if last_pressure_price2 is not None:
            pressure_prices_set.add(last_pressure_price2)
        pressure_prices = list(pressure_prices_set)
        
        # 排序并选择（支撑位从高到低，压力位从低到高）
        support_prices.sort(reverse=True)  # 从高到低（最接近当前价格的在前）
        pressure_prices.sort()  # 从低到高（最接近当前价格的在前）
        
        # 调试信息
        debug_info = {
            'algorithm': '双近算法',
            'window1_radius': 15,
            'window2_radius': 13,
            'peeks_first': peeks_first[:5],
            'valleys_first': valleys_first[:5],
            'peeks_second': peeks_second[:5],
            'valleys_second': valleys_second[:5],
            'support_prices_all': list(support_prices_set),
            'pressure_prices_all': list(pressure_prices_set),
            'current_price': current_price
        }
        
        # 合并基础调试信息
        if base_debug_info:
            debug_info.update(base_debug_info)
        
        # 返回结果
        return SupportLinesResult(
            last_support=support_prices[1] if len(support_prices) >= 2 else None,
            support=support_prices[0] if len(support_prices) >= 1 else None,
            pressure=pressure_prices[0] if len(pressure_prices) >= 1 else None,
            last_pressure=pressure_prices[1] if len(pressure_prices) >= 2 else None,
            direction=0,
            debug_info=debug_info
        )
    
    def _calculate_for_normal(
        self,
        klines: List[KLineData],
        period_type: str
    ) -> SupportLinesResult:
        """常规震荡算法：同时计算支撑位和压力位"""
        logger.info(f"【日线常规震荡算法】开始计算，周期类型={period_type}, K线数量={len(klines)}")
        current_price = klines[0].close
        
        # 判断趋势方向（收集详细信息）
        direction = self._get_trend_direction(klines)
        is_releasing = self._is_releasing(klines, 0, 3, 1.5)
        change_ratio = (klines[0].close - klines[1].close) / klines[1].close if klines[1].close > 0 else 0
        pop_back_to_up = self._pop_back_to_up(klines)
        pop_back_to_down = self._pop_back_to_down(klines)
        
        # 计算窗口大小
        window_size = 20 if period_type == 'day' else 10
        side_ignored = window_size // 4  # 日线忽略5日，其他忽略2-3日
        
        # 计算极值点
        logger.info(f"【日线常规震荡算法】开始计算极值点...")
        logger.info(f"  调用方法: ExtremeValueAlgorithm.calculate_extreme_points")
        logger.info(f"  参数: window_size={window_size}, peak_enabled=True, valley_enabled=True, use_min_max=False, side_ignored_count={side_ignored}")
        
        extreme_points = self.extreme_algorithm.calculate_extreme_points(
            klines,
            window_size=window_size,
            peak_enabled=True,
            valley_enabled=True,
            use_min_max=False,
            side_ignored_count=side_ignored
        )
        
        logger.info(f"【日线常规震荡算法】极值点计算完成")
        logger.info(f"  极值点数量: {len(extreme_points)}")
        logger.info(f"  窗口大小: {window_size}")
        logger.info(f"  忽略边缘: {side_ignored}根K线")
        if extreme_points:
            logger.info(f"  极值点价格范围: {min(p.price for p in extreme_points):.2f} ~ {max(p.price for p in extreme_points):.2f}")
            logger.info(f"  前10个极值点: {[(p.index, p.price) for p in extreme_points[:10]]}")
        
        # 分离支撑位和压力位候选
        support_candidates = [p for p in extreme_points if p.price < current_price]
        pressure_candidates = [p for p in extreme_points if p.price > current_price]
        
        # 获取所有极值点价格
        extreme_values = [p.price for p in extreme_points]
        extreme_points_detail = [{'index': p.index, 'price': p.price} for p in extreme_points]
        
        logger.info(f"【日线常规震荡算法】准备调用聚类算法")
        logger.info(f"  支撑候选数量: {len(support_candidates)}")
        logger.info(f"  压力候选数量: {len(pressure_candidates)}")
        logger.info(f"  趋势方向: {direction} ({'反弹' if direction == 1 else '反转' if direction == -1 else '震荡'})")
        if support_candidates:
            logger.info(f"  支撑候选价格: {[p.price for p in support_candidates[:10]]}")
        if pressure_candidates:
            logger.info(f"  压力候选价格: {[p.price for p in pressure_candidates[:10]]}")
        
        logger.info(f"【日线常规震荡算法】调用聚类算法: ClusterAlgorithm.pick_support_pressure_lines")
        last_support, support, pressure, last_pressure = self.cluster_algorithm.pick_support_pressure_lines(
            extreme_points, current_price, period_type, direction
        )
        
        logger.info(f"【日线常规震荡算法】聚类算法返回结果")
        logger.info(f"  当前支撑位: {support}")
        logger.info(f"  上一支撑位: {last_support}")
        logger.info(f"  当前压力位: {pressure}")
        logger.info(f"  上一压力位: {last_pressure}")
        
        # 计算益损比（用于验证）
        if support and pressure:
            win_space = pressure - current_price
            lose_space = current_price - support
            win_lose_ratio = win_space / lose_space if lose_space > 0 else 0
            logger.info(f"  益损比: {win_lose_ratio:.2f} (上升空间={win_space:.2f}, 下行空间={lose_space:.2f})")
        
        logger.info(f"═══════════════════════════════════════════════════════════")
        
        # 调试信息
        debug_info = {
            'algorithm': '常规震荡算法',
            'trend_direction': direction,
            'trend_direction_text': {1: '反弹', -1: '反转', 0: '震荡'}.get(direction, '未知'),
            'current_price': current_price,
            'kline_count': len(klines),
            'window_size': window_size,
            'side_ignored_count': side_ignored,
            'is_releasing': is_releasing,
            'change_ratio': round(change_ratio * 100, 2),  # 转换为百分比
            'pop_back_to_up': pop_back_to_up,
            'pop_back_to_down': pop_back_to_down,
            'extreme_points_count': len(extreme_points),
            'support_candidates_count': len(support_candidates),
            'pressure_candidates_count': len(pressure_candidates),
            'extreme_values': extreme_values[:10],  # 只显示前10个
            'extreme_points': extreme_points_detail[:10],
            'support_candidates': [p.price for p in support_candidates[:5]],
            'pressure_candidates': [p.price for p in pressure_candidates[:5]]
        }
        
        return SupportLinesResult(
            last_support=last_support,
            support=support,
            pressure=pressure,
            last_pressure=last_pressure,
            direction=direction,
            debug_info=debug_info
        )
    
    def _get_trend_direction(self, klines: List[KLineData]) -> int:
        """
        判断趋势方向
        返回：-1=反转，0=震荡，1=反弹
        """
        if len(klines) < 3:
            return 0
        
        # 判断是否最近3日放量
        is_releasing = self._is_releasing(klines, 0, 3, 1.5)
        
        # 计算涨跌幅
        change_ratio = (klines[0].close - klines[1].close) / klines[1].close if klines[1].close > 0 else 0
        
        # 判断反弹：放量上涨或从低点反弹
        if is_releasing and klines[0].volume > klines[1].volume and change_ratio > 0.03:
            return 1
        
        if self._pop_back_to_up(klines):
            return 1
        
        # 判断反转：放量下跌或从高点回落
        if is_releasing and change_ratio < -0.03:
            return -1
        
        if self._pop_back_to_down(klines):
            return -1
        
        return 0
    
    def _is_releasing(self, klines: List[KLineData], start: int, count: int, ratio: float) -> bool:
        """判断是否放量"""
        if len(klines) < start + count:
            return False
        
        volumes = [k.volume for k in klines[start:start+count]]
        if len(volumes) < 2:
            return False
        
        avg_volume = sum(volumes) / len(volumes)
        latest_volume = volumes[0]
        
        return latest_volume >= avg_volume * ratio
    
    def _pop_back_to_up(self, klines: List[KLineData]) -> bool:
        """判断是否从低点反弹"""
        if len(klines) < 10:
            return False
        
        # 获取最近10日的最低点
        recent_lows = [k.low for k in klines[:10]]
        min_low = min(recent_lows)
        
        change_ratio = (klines[0].close - klines[1].close) / klines[1].close if klines[1].close > 0 else 0
        
        return min_low < klines[0].close and change_ratio > 0.03
    
    def _pop_back_to_down(self, klines: List[KLineData]) -> bool:
        """判断是否从高点回落"""
        if len(klines) < 10:
            return False
        
        # 获取最近10日的最高点
        recent_highs = [k.high for k in klines[:10]]
        max_high = max(recent_highs)
        
        change_ratio = (klines[0].close - klines[1].close) / klines[1].close if klines[1].close > 0 else 0
        
        return max_high > klines[0].close and change_ratio < -0.03
    
    def calculate_win_lose_ratio(
        self,
        support: Optional[float],
        pressure: Optional[float],
        current_price: float
    ) -> float:
        """
        计算益损比
        
        Args:
            support: 支撑位
            pressure: 压力位
            current_price: 当前价格
            
        Returns:
            益损比
        """
        # 无效值处理
        if support is None and pressure is None:
            return 0.0
        
        if support is None:
            # 只有压力位，无支撑位（创新低场景）
            return 0.0
        
        if pressure is None:
            # 只有支撑位，无压力位（创新高场景）
            return 0.0
        
        # 计算上升空间和下行空间
        win_space = pressure - current_price
        lose_space = current_price - support
        
        if lose_space <= 0:
            return 0.0
        
        # 计算益损比
        win_lose_ratio = win_space / lose_space
        
        # 边界处理：限制在 [0.01, 99.99] 范围内
        if win_lose_ratio < 0.01:
            return 0.0
        elif win_lose_ratio > 99.99:
            return 100.0
        else:
            return round(win_lose_ratio, 2)

