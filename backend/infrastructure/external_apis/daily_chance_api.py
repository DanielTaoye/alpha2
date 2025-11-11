"""每日机会外部API客户端"""
import requests
from typing import List, Dict, Any
from infrastructure.logging.logger import get_external_api_logger
import re

logger = get_external_api_logger()


class DailyChanceApiClient:
    """每日机会API客户端"""
    
    def __init__(self):
        self.api_url = 'http://121.5.174.81:8005/stock/getDailyChanceWithBeauty'
        self.timeout = 30
    
    def get_daily_chance(self, stock_code: str) -> List[Dict[str, Any]]:
        """
        获取股票每日机会数据
        
        Args:
            stock_code: 股票代码，如SZ300188
            
        Returns:
            每日机会数据列表
        """
        try:
            logger.info(f"调用每日机会API: 股票代码={stock_code}")
            
            # 接口需要POST请求，请求体是股票代码字符串
            response = requests.post(
                self.api_url,
                data=stock_code,
                headers={'Content-Type': 'application/json'},
                timeout=self.timeout
            )
            
            if response.status_code == 200:
                data = response.json()
                logger.info(f"成功获取每日机会数据: 股票={stock_code}, 记录数={len(data) if isinstance(data, list) else 0}")
                return data if isinstance(data, list) else []
            else:
                logger.warning(f"每日机会API请求失败: 股票={stock_code}, status={response.status_code}")
                return []
                
        except requests.Timeout:
            logger.warning(f"每日机会API超时: 股票={stock_code}, 超时时间={self.timeout}秒")
            return []
        except requests.RequestException as e:
            logger.error(f"每日机会API请求异常: 股票={stock_code}, 错误={str(e)}")
            return []
        except Exception as e:
            logger.error(f"每日机会API处理异常: 股票={stock_code}, 错误={str(e)}", exc_info=True)
            return []
    
    @staticmethod
    def parse_win_ratio_description(description: str) -> tuple:
        """
        解析赔率描述字符串，提取日线、周线、总分
        
        Args:
            description: 赔率描述字符串，如"根据为赔率算法计算：日线赔率得分：6.70，周线赔率得分：7.75，赔率总分：14.46"
            
        Returns:
            (日线赔率得分, 周线赔率得分, 赔率总分)
        """
        if not description:
            return (0.0, 0.0, 0.0)
        
        try:
            # 使用正则表达式提取数字
            day_match = re.search(r'日线赔率得分[：:]\s*([\d.]+)', description)
            week_match = re.search(r'周线赔率得分[：:]\s*([\d.]+)', description)
            total_match = re.search(r'赔率总分[：:]\s*([\d.]+)', description)
            
            day_score = float(day_match.group(1)) if day_match else 0.0
            week_score = float(week_match.group(1)) if week_match else 0.0
            total_score = float(total_match.group(1)) if total_match else 0.0
            
            return (day_score, week_score, total_score)
        except Exception as e:
            logger.warning(f"解析赔率描述失败: {description}, 错误={str(e)}")
            return (0.0, 0.0, 0.0)

