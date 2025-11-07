# CR点功能快速启动指南

## 第一步：初始化数据库表

打开终端，运行：

```bash
cd backend
python scripts/init_cr_table.py
```

看到"初始化完成！"表示成功。

## 第二步：启动后端服务

运行：

```bash
start.bat
```

或者：

```bash
python backend/app.py
```

看到"Running on http://127.0.0.1:5000"表示后端启动成功。

## 第三步：打开前端页面

浏览器访问：

```
http://localhost:5000
```

## 第四步：使用CR点分析

1. **选择策略类型**：波段/短线/中长线
2. **选择股票**：从下拉列表中选择一个股票
3. **切换到日K线**：点击"日K线"按钮
4. **分析CR点**：点击右下角"🎯 分析CR点"按钮
   - 系统会分析该股票的所有日K线数据
   - 弹窗显示找到多少个C点和R点
5. **显示CR点**：点击"👁️ 显示CR点"按钮
   - 绿色C点标记买入点
   - 红色R点标记卖出点
6. **查看统计**：右上角显示C点和R点数量

## CR点策略说明

### 当前实现的策略

**策略1：上下影线均衡小实体**

这是一个寻找底部十字星形态的策略：

- 上影线和下影线长度接近（a/c = 0.9~1.1）
- 实体很小（b/最低价 < 1%）
- 上下影线都存在（a≠0 且 c≠0）

### K线ABC定义

```
        最高价
          |
          |--- a (上引线)
        -----
        |   |
        | b | (实体)
        |   |
        -----
          |--- c (下引线)
          |
        最低价
```

- **a (上引线)** = 最高价 - max(开盘价, 收盘价)
- **b (实体)** = max(开盘价, 收盘价) - min(开盘价, 收盘价)
- **c (下引线)** = min(开盘价, 收盘价) - 最低价

## 测试示例

可以选择以下股票进行测试：
- 浦发银行 (sh600000)
- 中国银行 (sh600015)
- 工商银行 (sh601398)

## 常见问题

### Q: 点击"分析CR点"没有反应？
A: 检查：
1. 是否选择了日K线周期（目前只支持日K）
2. 浏览器控制台是否有错误信息
3. 后端服务是否正常运行

### Q: 为什么有的股票找不到CR点？
A: 可能原因：
1. 该股票最近没有符合策略的K线形态
2. 策略条件较为严格
3. 可以尝试其他股票

### Q: 如何修改策略参数？
A: 编辑 `backend/domain/services/cr_strategy_service.py` 文件，修改策略条件。

### Q: 如何添加新的策略？
A: 参考《CR点分析系统使用说明.md》中的"扩展开发"章节。

## 数据库查询

查看已识别的CR点：

```sql
-- 查看所有CR点
SELECT * FROM cr_points ORDER BY trigger_date DESC;

-- 查看某个股票的C点
SELECT * FROM cr_points 
WHERE stock_code = 'sh600000' AND point_type = 'C'
ORDER BY trigger_date DESC;

-- 统计每个股票的CR点数量
SELECT stock_code, stock_name, point_type, COUNT(*) as count
FROM cr_points
GROUP BY stock_code, stock_name, point_type
ORDER BY count DESC;
```

## API测试

使用Postman或curl测试API：

### 分析CR点

```bash
curl -X POST http://localhost:5000/api/cr_points/analyze \
  -H "Content-Type: application/json" \
  -d '{
    "stockCode": "sh600000",
    "stockName": "浦发银行",
    "period": "day"
  }'
```

### 获取CR点列表

```bash
curl -X POST http://localhost:5000/api/cr_points \
  -H "Content-Type: application/json" \
  -d '{
    "stockCode": "sh600000"
  }'
```

## 系统架构

```
frontend/
  ├── js/app.js          # 前端主逻辑（包含CR点功能）
  └── css/styles.css     # 样式（包含CR点按钮样式）

backend/
  ├── domain/
  │   ├── models/cr_point.py           # CR点实体模型
  │   ├── repositories/                # 仓储接口
  │   └── services/cr_strategy_service.py  # 策略领域服务
  ├── application/
  │   └── services/cr_point_service.py # CR点应用服务
  ├── infrastructure/
  │   └── persistence/
  │       └── cr_point_repository_impl.py  # 仓储实现
  └── interfaces/
      └── controllers/cr_point_controller.py  # 控制器

sql/
  └── create_cr_points_table.sql       # 数据库表结构

scripts/
  └── init_cr_table.py                 # 初始化脚本
```

## 下一步

- 可以尝试分析不同的股票
- 查看数据库中保存的CR点数据
- 根据需要调整策略参数
- 添加新的识别策略

祝使用愉快！

