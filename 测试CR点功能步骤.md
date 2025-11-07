# 测试CR点功能步骤

## 前提条件

✅ 数据库已初始化（运行过 `python backend/scripts/init_cr_table.py`）
✅ 后端代码已更新并修复
✅ 前端代码已更新

## 应用更新

### 1. 如果服务器正在运行

**Windows PowerShell:**
```powershell
# 按 Ctrl+C 停止服务器，然后重新启动
python backend/app.py
```

或直接运行：
```bash
start.bat
```

### 2. 刷新浏览器

在浏览器中按 `Ctrl + F5` 强制刷新页面，清除缓存加载最新的 JavaScript 代码。

## 测试步骤

### 步骤 1: 访问系统
打开浏览器访问：`http://localhost:5000`

### 步骤 2: 选择股票
1. 选择策略类型（如"波段"）
2. 在下拉列表中选择一个股票（如"浦发银行 sh600000"）
3. 系统会自动加载K线图

### 步骤 3: 切换到日K线
点击"日K线"按钮（CR点分析目前只支持日K线）

### 步骤 4: 分析CR点
1. 点击右下角的 **"🎯 分析CR点"** 按钮
2. 等待分析完成（可能需要几秒钟）
3. 会弹出提示框显示：
   ```
   CR点分析完成！
   找到C点(买入点): X个
   找到R点(卖出点): Y个
   ```

### 步骤 5: 显示CR点
1. 点击 **"👁️ 显示CR点"** 按钮
2. K线图上会显示：
   - 🟢 **绿色圆圈 + C标记** = 买入点（位于K线下方）
   - 🔴 **红色圆圈 + R标记** = 卖出点（位于K线上方）
3. 右上角显示统计：`C点: X | R点: Y`

### 步骤 6: 切换显示
- 再次点击"显示CR点"按钮会隐藏标记
- 按钮文字会在"显示CR点"和"隐藏CR点"之间切换

## 预期结果

### 控制台输出（后端）

```
2025-11-07 xx:xx:xx - controllers.cr_point_controller - INFO - 开始分析CR点: sh600000 浦发银行 表:kline_sh600000 周期:day
2025-11-07 xx:xx:xx - application.services.cr_point_service - INFO - CR点分析完成: sh600000 - C点:3个, R点:2个
```

### 浏览器控制台（F12）

```javascript
开始分析CR点... {stockCode: "sh600000", stockName: "浦发银行", tableName: "kline_sh600000"}
CR点分析结果: {code: 200, data: {...}, message: "..."}
CR点数据: {code: 200, data: [...]}
```

### 数据库查询

打开数据库管理工具，执行：

```sql
-- 查看分析的CR点
SELECT * FROM cr_points 
WHERE stock_code = 'sh600000'
ORDER BY trigger_date DESC;

-- 应该能看到新插入的记录
```

## 常见问题排查

### 问题1: 点击"分析CR点"无反应

**检查：**
```javascript
// 浏览器控制台（F12）查看是否有错误
// 检查 currentTableName 是否有值
console.log(currentTableName);
```

**解决：** 重新选择股票

### 问题2: 提示"表名不能为空"

**原因：** 前端没有传递 `tableName`

**解决：**
1. 强制刷新浏览器（Ctrl + F5）
2. 确认前端代码已更新

### 问题3: 提示"K线数据为空"

**原因：** 
- 该股票在数据库中没有日K线数据
- 表名不正确

**解决：**
1. 尝试其他股票
2. 检查数据库中是否有该表

```sql
SHOW TABLES LIKE 'kline_%';
```

### 问题4: 找到0个CR点

**原因：** 
- 该股票最近的K线不符合策略条件
- 策略条件较为严格

**这是正常的！** 不是每个股票都会有CR点。

**建议：**
- 尝试分析多个不同的股票
- 查看策略定义，理解触发条件

## 验证成功标志

✅ 点击"分析CR点"后有弹窗提示
✅ 后端日志显示分析过程
✅ 点击"显示CR点"后图表上出现标记
✅ 右上角显示统计信息
✅ 数据库中有新记录

## 调整策略参数（可选）

如果想修改策略，编辑文件：
```
backend/domain/services/cr_strategy_service.py
```

修改这些条件：
```python
# C点策略1的条件
if not (0.9 <= a_c_ratio <= 1.1):  # 上下影线比例
    return False, 0, strategy_name

if b_low_ratio >= 0.01:  # 实体/最低价 < 1%
    return False, 0, strategy_name
```

修改后重启服务器即可生效。

## 下一步

尝试：
1. 分析不同的股票
2. 观察CR点的分布
3. 查看数据库中的详细数据
4. 根据需要调整策略参数

---

祝测试顺利！🎉

