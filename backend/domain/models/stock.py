"""股票领域模型"""
from dataclasses import dataclass
from typing import List, Dict


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
    
    def __init__(self):
        self._groups = {
            '波段': [
                Stock('国投智能', 'SZ300188', 'basic_data_sz300188'),
                Stock('海兴电力', 'SH603556', 'basic_data_sh603556'),
                Stock('沃尔核材', 'SZ002130', 'basic_data_sz002130'),
                Stock('歌华有线', 'SH600037', 'basic_data_sh600037'),
                Stock('中集车辆', 'SZ301039', 'basic_data_sz301039'),
                Stock('蓝色光标', 'SZ300058', 'basic_data_sz300058'),
                Stock('迪普科技', 'SZ300768', 'basic_data_sz300768'),
                Stock('思瑞浦', 'SH688536', 'basic_data_sh688536'),
                Stock('时代新材', 'SH600458', 'basic_data_sh600458'),
                Stock('东华软件', 'SZ002065', 'basic_data_sz002065'),
                Stock('福蓉科技', 'SH603327', 'basic_data_sh603327'),
                Stock('筑博设计', 'SZ300564', 'basic_data_sz300564'),
                Stock('杭叉集团', 'SH603298', 'basic_data_sh603298'),
                Stock('维信诺', 'SZ002387', 'basic_data_sz002387'),
                Stock('康美药业', 'SH600518', 'basic_data_sh600518'),
                Stock('广汇能源', 'SH600256', 'basic_data_sh600256'),
                Stock('科沃斯', 'SH603486', 'basic_data_sh603486'),
                Stock('高能环境', 'SH603588', 'basic_data_sh603588'),
                Stock('北新建材', 'SZ000786', 'basic_data_sz000786'),
                Stock('安通控股', 'SH600179', 'basic_data_sh600179')
            ],
            '短线': [
                Stock('白云机场', 'SH600004', 'basic_data_sh600004'),
                Stock('金雷股份', 'SZ300443', 'basic_data_sz300443'),
                Stock('南京化纤', 'SH600889', 'basic_data_sh600889'),
                Stock('慧智微-U', 'SH688512', 'basic_data_sh688512'),
                Stock('锴威特', 'SH688693', 'basic_data_sh688693'),
                Stock('新疆天业', 'SH600075', 'basic_data_sh600075'),
                Stock('物产金轮', 'SZ002722', 'basic_data_sz002722'),
                Stock('中巨芯-U', 'SH688549', 'basic_data_sh688549'),
                Stock('美湖股份', 'SH603319', 'basic_data_sh603319'),
                Stock('依米康', 'SZ300249', 'basic_data_sz300249'),
                Stock('中化装备', 'SH600579', 'basic_data_sh600579'),
                Stock('科锐国际', 'SZ300662', 'basic_data_sz300662'),
                Stock('三晖电气', 'SZ002857', 'basic_data_sz002857'),
                Stock('易尚退', 'SZ002751', 'basic_data_sz002751'),
                Stock('长青科技', 'SZ001324', 'basic_data_sz001324'),
                Stock('菲菱科思', 'SZ301191', 'basic_data_sz301191'),
                Stock('运达股份', 'SZ300772', 'basic_data_sz300772'),
                Stock('上纬新材', 'SH688585', 'basic_data_sh688585'),
                Stock('开创电气', 'SZ301448', 'basic_data_sz301448'),
                Stock('康希通信', 'SH688653', 'basic_data_sh688653')
            ],
            '中长线': [
                Stock('立讯精密', 'SZ002475', 'basic_data_sz002475'),
                Stock('宁德时代', 'SZ300750', 'basic_data_sz300750'),
                Stock('农业银行', 'SH601288', 'basic_data_sh601288'),
                Stock('中国石油', 'SH601857', 'basic_data_sh601857'),
                Stock('紫金矿业', 'SH601899', 'basic_data_sh601899'),
                Stock('传音控股', 'SH688036', 'basic_data_sh688036'),
                Stock('常熟银行', 'SH601128', 'basic_data_sh601128'),
                Stock('潍柴动力', 'SZ000338', 'basic_data_sz000338'),
                Stock('海螺水泥', 'SH600585', 'basic_data_sh600585'),
                Stock('民生银行', 'SH600016', 'basic_data_sh600016'),
                Stock('华域汽车', 'SH600741', 'basic_data_sh600741'),
                Stock('申万宏源', 'SZ000166', 'basic_data_sz000166'),
                Stock('陕西煤业', 'SH601225', 'basic_data_sh601225'),
                Stock('泸州老窖', 'SZ000568', 'basic_data_sz000568'),
                Stock('江阴银行', 'SZ002807', 'basic_data_sz002807'),
                Stock('中微公司', 'SH688012', 'basic_data_sh688012'),
                Stock('春秋航空', 'SH601021', 'basic_data_sh601021'),
                Stock('光启技术', 'SZ002625', 'basic_data_sz002625'),
                Stock('宇通客车', 'SH600066', 'basic_data_sh600066'),
                Stock('中远海控', 'SH601919', 'basic_data_sh601919')
            ]
        }
    
    def get_all_groups(self) -> Dict[str, List[Stock]]:
        """获取所有股票分组"""
        return self._groups
    
    def get_group(self, group_name: str) -> List[Stock]:
        """根据名称获取股票分组"""
        return self._groups.get(group_name, [])

