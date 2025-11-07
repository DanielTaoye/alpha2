"""股票分析外部API客户端"""
import requests
from typing import Dict, Any
from infrastructure.config.api_config import EXTERNAL_API_CONFIG


class StockAnalysisApiClient:
    """股票分析API客户端"""
    
    def __init__(self):
        self.api_url = EXTERNAL_API_CONFIG['url']
        self.token = EXTERNAL_API_CONFIG['token']
        self.timeout = EXTERNAL_API_CONFIG['timeout']
    
    def get_stock_analysis(self, stock_code: str) -> Dict[str, Any]:
        """
        获取股票分析数据
        
        Args:
            stock_code: 股票代码
            
        Returns:
            分析数据字典，包含各周期的益损比、压力线、支撑线
        """
        # 默认空数据结构
        result = {
            '30min': {},
            'day': {},
            'week': {},
            'month': {}
        }
        
        try:
            api_data = {
                "appId": "string",
                "circleId": "string",
                "parameter": {
                    "stockCode": stock_code
                },
                "requestId": "string",
                "token": self.token,
                "traceId": "string"
            }
            
            response = requests.post(self.api_url, json=api_data, timeout=self.timeout)
            response_data = response.json()
            
            print(f"[分析接口] 股票 {stock_code} 响应: success={response_data.get('success')}")
            
            if response.status_code == 200 and response_data.get('success') == True:
                api_result = response_data.get('result', {})
                
                # 提取不同周期的数据
                period_mapping = {
                    '30min': 'minLineAnalysis',
                    'day': 'dayLineAnalysis',
                    'week': 'weekLineAnalysis',
                    'month': 'monthLineAnalysis'
                }
                
                for frontend_period, api_field in period_mapping.items():
                    period_data = api_result.get(api_field, {})
                    if period_data:
                        result[frontend_period] = {
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
            print(f"分析接口超时: {stock_code}")
        except requests.RequestException as e:
            print(f"分析接口请求失败: {stock_code}, 错误: {e}")
        except Exception as e:
            print(f"分析接口异常: {stock_code}, 错误: {e}")
        
        return result

