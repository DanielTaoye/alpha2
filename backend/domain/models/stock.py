"""股票领域模型"""
from dataclasses import dataclass
from typing import List, Dict
import json
from pathlib import Path


@dataclass
class Stock:
    """股票实体"""
    name: str
    code: str
    table_name: str
    

@dataclass
class StockGroup:
    """股票分组聚合根"""
    name: str
    stocks: List[Stock]


class StockGroups:
    """股票分组值对象"""
    
    def __init__(self, config_path: str = None):
        """
        初始化股票分组
        
        Args:
            config_path: 配置文件路径，如果为None则使用默认路径
        """
        if config_path is None:
            # 获取当前文件的目录，然后找到配置文件
            current_dir = Path(__file__).parent.parent.parent
            config_path = current_dir / 'infrastructure' / 'config' / 'stock_config.json'
        
        self._groups = self._load_from_config(config_path)
    
    def _load_from_config(self, config_path: str) -> Dict[str, List[Stock]]:
        """
        从JSON配置文件加载股票分组
        
        Args:
            config_path: 配置文件路径
            
        Returns:
            股票分组字典
        """
        try:
            config_file = Path(config_path)
            if not config_file.exists():
                raise FileNotFoundError(f"股票配置文件不存在: {config_path}")
            
            with open(config_file, 'r', encoding='utf-8') as f:
                config_data = json.load(f)
            
            groups = {}
            for group_name, stocks_data in config_data.items():
                stocks = []
                for stock_data in stocks_data:
                    stock = Stock(
                        name=stock_data['name'],
                        code=stock_data['code'],
                        table_name=stock_data['table']
                    )
                    stocks.append(stock)
                groups[group_name] = stocks
            
            return groups
        except json.JSONDecodeError as e:
            raise ValueError(f"股票配置文件JSON格式错误: {str(e)}")
        except KeyError as e:
            raise ValueError(f"股票配置文件缺少必要字段: {str(e)}")
        except Exception as e:
            raise RuntimeError(f"加载股票配置文件失败: {str(e)}")
    
    def get_all_groups(self) -> Dict[str, List[Stock]]:
        """获取所有股票分组"""
        return self._groups
    
    def get_group(self, group_name: str) -> List[Stock]:
        """根据名称获取股票分组"""
        return self._groups.get(group_name, [])

