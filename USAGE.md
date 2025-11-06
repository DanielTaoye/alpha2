# 使用指南

## 快速开始

### 1. 环境准备

**系统要求：**
- Python 3.7+
- MySQL 5.7+
- 浏览器（推荐Chrome/Edge）

**检查Python版本：**
```bash
python --version
```

### 2. 安装步骤

**方法一：使用安装脚本（Windows）**
```bash
install.bat
```

**方法二：手动安装**
```bash
pip install -r requirements.txt
```

### 3. 数据库配置

编辑 `backend/app.py` 文件，修改数据库配置：

```python
DB_CONFIG = {
    'host': 'localhost',      # 数据库地址
    'user': 'root',           # 用户名
    'password': 'your_pass',  # 密码（修改这里）
    'database': 'stock_db',   # 数据库名（修改这里）
    'charset': 'utf8mb4'
}
```

### 4. 数据表检查

确保数据库中存在以下表：

**波段策略组：**
- `basic_data_sz300188` - 国投智能
- `basic_data_sh603556` - 海兴电力
- `basic_data_sz002130` - 沃尔核材
- `basic_data_sh600037` - 歌华有线
- `basic_data_sz301039` - 中集车辆

**短线策略组：**
- `basic_data_sh600004` - 白云机场
- `basic_data_sz300443` - 金雷股份
- `basic_data_sh600889` - 南京化纤
- `basic_data_sh688512` - 慧智微-U
- `basic_data_sh688693` - 锴威特

**中长线策略组：**
- `basic_data_sz002475` - 立讯精密
- `basic_data_sz300750` - 宁德时代
- `basic_data_sh601288` - 农业银行
- `basic_data_sh601857` - 中国石油
- `basic_data_sh601899` - 紫金矿业

### 5. 启动系统

**方法一：使用启动脚本（Windows）**
```bash
start.bat
```

**方法二：手动启动**
```bash
cd backend
python app.py
```

服务启动后会显示：
```
 * Running on http://0.0.0.0:5000
```

### 6. 访问系统

打开浏览器访问：http://localhost:5000

## 功能说明

### 页面布局

系统按策略类型分为三个区域：
1. **波段策略** - 5支股票
2. **短线策略** - 5支股票
3. **中长线策略** - 5支股票

### K线周期切换

每个股票卡片右上角有四个按钮：
- **30分钟** - 显示30分钟K线
- **日K线** - 显示日K线
- **周K线** - 显示周K线
- **月K线** - 显示月K线

点击按钮即可切换周期，默认显示30分钟K线。

### 分析指标说明

每个股票卡片底部显示5个关键指标：

| 指标 | 说明 | 来源 |
|------|------|------|
| **益损比** | 盈亏比率，用于评估风险收益 | 外部API |
| **支撑线** | 价格支撑位，绿色虚线 | 外部API |
| **压力线** | 价格压力位，红色虚线 | 外部API |
| **量比** | 当前成交量与历史平均成交量的比值 | 数据库 |
| **委比** | 买卖委托的比值，正值表示买盘强 | 数据库 |

### K线图操作

**缩放：**
- 鼠标滚轮：放大/缩小
- 拖动底部滑块：调整显示区间

**查看详情：**
- 鼠标悬停：显示当前K线的详细信息
  - 时间
  - 开盘价
  - 收盘价
  - 最高价
  - 最低价
  - 成交量

**图例控制：**
- 点击图例：显示/隐藏对应的线条
  - K线
  - 支撑线（绿色虚线）
  - 压力线（红色虚线）

## 常见问题

### Q1: 页面显示"数据加载失败"

**可能原因：**
1. 数据库连接失败
2. 表不存在或表名不匹配
3. 数据为空

**解决方法：**
1. 检查数据库配置是否正确
2. 确认MySQL服务是否启动
3. 查看后端控制台错误信息
4. 确认表名是否与代码中一致

### Q2: 支撑线/压力线不显示

**可能原因：**
1. 外部API调用失败
2. Token过期
3. 网络连接问题

**解决方法：**
1. 检查网络连接
2. 更新API Token
3. 查看浏览器控制台错误信息

### Q3: K线数据不完整

**可能原因：**
1. 数据库中数据不足3年
2. `peroid_type` 字段值不正确

**解决方法：**
1. 检查数据库中的数据量
2. 确认 `peroid_type` 字段：
   - 4 = 30分钟
   - 6 = 日K
   - 7 = 周K
   - 8 = 月K

### Q4: 端口被占用

**错误信息：**
```
Address already in use
```

**解决方法：**
1. 修改 `backend/app.py` 中的端口号：
```python
app.run(host='0.0.0.0', port=5001, debug=True)  # 改为5001或其他端口
```

2. 或者关闭占用5000端口的程序

### Q5: 跨域错误（CORS）

**错误信息（浏览器控制台）：**
```
Access to fetch at ... has been blocked by CORS policy
```

**解决方法：**
已通过Flask-CORS解决，如仍有问题：
1. 确认已安装 flask-cors：`pip install flask-cors`
2. 检查浏览器是否禁用了某些功能

## 性能优化建议

### 1. 数据加载优化

如果数据量很大，可以考虑：
- 添加数据分页
- 使用数据缓存
- 优化SQL查询索引

### 2. 图表渲染优化

- 减少单次加载的数据点数量
- 使用数据抽样（大周期可以减少数据点）
- 启用ECharts的性能模式

### 3. API调用优化

- 添加结果缓存（避免重复调用）
- 实现请求防抖
- 考虑批量获取数据

## 开发调试

### 启用详细日志

修改 `backend/app.py`：
```python
import logging
logging.basicConfig(level=logging.DEBUG)
```

### 浏览器调试

打开浏览器开发者工具（F12）：
- **Console** - 查看JavaScript错误
- **Network** - 查看API请求
- **Elements** - 检查页面结构

### 后端调试

查看后端控制台输出，了解：
- SQL查询语句
- API调用结果
- 错误堆栈信息

## 部署建议

### 生产环境配置

1. **关闭调试模式：**
```python
app.run(host='0.0.0.0', port=5000, debug=False)
```

2. **使用生产级服务器：**
```bash
pip install gunicorn
gunicorn -w 4 -b 0.0.0.0:5000 app:app
```

3. **配置反向代理（Nginx）：**
```nginx
server {
    listen 80;
    server_name your_domain.com;

    location / {
        proxy_pass http://localhost:5000;
        proxy_set_header Host $host;
        proxy_set_header X-Real-IP $remote_addr;
    }
}
```

### 安全建议

1. 不要将数据库密码提交到版本控制
2. 使用环境变量存储敏感信息
3. 启用HTTPS（生产环境必须）
4. 定期更新依赖包
5. 添加访问频率限制

## 技术支持

如遇到其他问题，请检查：
1. 后端控制台日志
2. 浏览器控制台（F12）
3. 数据库连接状态
4. 网络连接状态

或查看项目README.md了解更多信息。

