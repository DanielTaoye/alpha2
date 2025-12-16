# /api/latest_cr_points 接口调用逻辑（详细版）

## 1. 接口概览

- **路由**：`POST /api/latest_cr_points`
- **入口**：`backend/app.py -> get_latest_cr_points()`
- **Controller**：`backend/interfaces/controllers/latest_cr_point_controller.py -> LatestCRPointController.get_latest_cr_points`
- **核心 Service**：`backend/application/services/latest_cr_point_service.py -> LatestCRPointService.calculate_latest_cr_points`

此接口的目标不是“算全历史”，而是返回**最新一天**的：
- **策略1评分**（是否触发C点、分数、插件）
- **策略2评分**（是否触发C点、分数、原因）
- **R点**（是否触发、触发的风险插件）
- 并附带 **最新一天K线**、预测成交量、成交量类型、前一交易日赔率分等信息，供前端 tooltip/展示使用。

---

## 2. 请求/响应数据

### 2.1 请求 JSON
`LatestCRPointController.get_latest_cr_points` 解析字段：

- `stockCode`（必填）
- `tableName`（必填：如 `basic_data_sz300188`）
- `stockNature` / `stock_nature`（可选：短线/波段/中长线）
- `predictedVolume`（可选：如果前端已算好预测成交量，可传入避免后端再算）
- `volumeType`（可选：如果前端已算好成交量类型，可传入避免后端再算）

### 2.2 响应结构（关键字段）
Controller 外层使用 `ResponseBuilder.success(result, "计算成功")` 包装。

其中 `result`（由 `LatestCRPointService.calculate_latest_cr_points` 返回）结构大致为：

- `success`: bool
- `date`: 最新一天日期（字符串，通常 `YYYY-MM-DD`）
- `stock_code`: 请求入参 stock_code（未必带 SZ/SH）
- `stock_nature`: 最终股性（入参优先，否则尝试从 daily_chance 推断，默认“波段”）
- `kline`: `{open, close, high, low, volume}`
- `predicted_volume`: 预测成交量（可能为空）
- `volume_type`: 最新一天成交量类型（可能为空）
- `realtime_volume_type`: 同 `volume_type`（前端兼容字段）
- `volume_type_source`: `"predicted"` 或 `"historical"`
- `previous_day_scores`: `{day, week, total, has_historical_data}`
- `strategy1`: `{is_c_point, is_rejected, score, base_score, plugins, threshold}`
- `strategy2`: `{is_c_point, score, reason, threshold}`
- `r_point`: `{is_r_point, plugins: [{plugin_name, reason}] }`

---

## 3. 实际调用顺序（从入口到最底层）

### 3.1 路由入口
1. `backend/app.py`
   - `@app.route('/api/latest_cr_points', methods=['POST'])`
   - 调用：`latest_cr_point_controller.get_latest_cr_points()`

### 3.2 Controller：解析参数并委派给 Service
2. `LatestCRPointController.get_latest_cr_points()`
   - 读取 `stockCode/tableName/stockNature/predictedVolume/volumeType`
   - 调用：
     - `LatestCRPointService.calculate_latest_cr_points(stock_code, table_name, predicted_volume, volume_type, stock_nature)`

### 3.3 Service：LatestCRPointService.calculate_latest_cr_points（核心）
下面按代码执行顺序梳理：

#### Step A：补全带市场前缀的 stock_code（用于 b_daily_chance）
- 代码会把 `stock_code` 补成 `full_stock_code`：
  - 若入参不带 `SZ/SH`，则从 `table_name` 判断 `_sz/_sh` 补前缀
- 目的：后续查 `b_daily_chance` 时使用 `full_stock_code`

#### Step B：获取最新一天日K（从 1min 聚合）
- 调用：`kline_service.get_latest_day_kline(table_name)`
  - 底层：`KLineRepositoryImpl.get_latest_day_1min_data` 读当日 1min（9:31~15:00）
  - 在应用层聚合成当天日K：open/high/low/close/volume（volume 汇总）
- 返回：`latest_kline_result['kline_data']`（dict）

#### Step C：获取历史日K（排除今天），并带上 MA/MACD
- 调用：`kline_service.get_kline_data(table_name, 'day', exclude_today=True)`
  - DB：`KLineRepositoryImpl.get_kline_data`（limit=2000，日K默认时间范围 730 天）
  - CPU：`MAService` + `MACDService`
- 得到：`kline_data_result['kline_data']`（list[dict]） + `kline_data_result['ma']` + `kline_data_result['macd']`

#### Step D：为了“插件判断”，先算一遍历史 CR 点（已优化为仅最近90个交易日）
这是 `latest_cr_points` 里**最重的一段**（通常 4~6 秒级别），逻辑是：

1) 把历史 `kline_data` 转成 `List[KLineData]`
2) 查一次 `b_daily_chance` 区间数据，构建：
   - `volume_types_hist: {date_str: volume_type}`
   - `bullish_patterns_hist: {date_str: bullish_pattern}`
3) 调用 `CRPointService.analyze_cr_points(...)` **计算最近90个交易日的 C/R 点**  
   - 这一步内部会跑 R点插件 + 策略1插件 + 策略2（逐根K线）
4) 从返回里提取：
   - `historical_c_points = c_points + strategy2_c_points`
   - `historical_r_points = r_points`

> 说明：这一步的目的，是为了在最新一天的策略1/插件里用到“历史C/R点序列”（例如 R 后回支撑发C、阳包阴等插件）。

#### Step E：把“最新一天日K”追加进历史 kline_data，并重新计算 MA/MACD（含最新一天）
- 因为最新一天日K来自 1min 聚合，未必已写回日K表，所以要手动 append
- 若 `predicted_volume` 存在，会用预测成交量替换当天 volume
- 然后对 closes 重新算 MA5/10/20 与 MACD，并写回 `kline_data_result['ma']`、`kline_data_result['macd']`

#### Step F：获取“前一交易日”的 daily_chance（赔率分等）
- 调用：`_get_previous_daily_chance(full_stock_code, latest_kline)`
  - 实际：`daily_chance_service.get_daily_chance_by_stock(full_stock_code)` 拉取该股所有 daily_chance（按日期降序）
  - 找到第一个 `< latest_date` 的记录作为前一交易日
- 得到：`day/week/total_win_ratio_score`，并可用于推断 `stock_nature`

#### Step G：预测成交量与成交量类型（可由前端传入）
- 若 `predicted_volume` 缺失：
  - 调 `kline_service.predict_today_volume(table_name)`（基于近 5 天 1min）
- 若 `volume_type` 缺失且有 `predicted_volume`：
  - 调 `VolumeTypeService.calculate_volume_type_with_predicted(table_name, predicted_volume)`（需要查询历史日成交量）

#### Step H：拿“CR策略服务实例”（理论上有缓存，但当前实现禁用缓存）
- 调：`get_cr_cache_manager().get_cr_service(stock_code)`
- 注意：`CRCacheManager.get_cr_service` 当前实现是 **禁用缓存**，每次返回 `CRStrategyService()` 新实例（会打印“🚫 禁用缓存...”）

#### Step I：策略1（最新一天）
- 调：`_check_strategy1_c_point(...)`
  - 内部把日期转 `datetime`
  - 调 `CRStrategyService.check_c_point_strategy_1(...)`
  - 传入：`volume_type` + `total_win_ratio_score` + `historical_c_points` + `historical_r_points` + `stock_nature`
  - 返回：`is_c_point / is_rejected / score / base_score / plugins / threshold`

#### Step J：多头组合（用于策略2的K线组合加分）
- 调：`BullishPatternService.identify_bullish_patterns(full_stock_code, table_name, target_date)`
  - DB：查询目标日期附近日K数据
  - 输出：组合列表，拼成逗号字符串 `bullish_pattern`

#### Step K：策略2（最新一天）
- 调：`_check_strategy2_c_point(...)`
  - `current_index = len(kline_data)-1`
  - `daily_data_30 = kline_data[-30:]`
  - 调 `Strategy2Service.check_strategy2(...)` 返回是否触发、分数、原因

#### Step L：R点（最新一天）
- 先从历史C点里取“最近C点日期”作为 `c_point_date`
- 调：`_check_r_point(...)`
  - **重要修复**：会把 `kline_data`（list[dict]）转换为 `List[KLineData]` 再传入 `RPointPluginService.check_r_point`，避免插件内部直接访问 `kline.high/low` 时报错
  - 返回：是否触发R点 + 触发插件列表

#### Step M：组装返回结果
组合 kline、预测成交量/类型、前一日赔率分、strategy1/2/r_point 等信息返回。

---

## 4. 涉及的数据源与表

### 4.1 每股K线表（`table_name`）
典型字段：
- `shi_jian`（时间）
- `kai_pan_jia / zui_gao_jia / zui_di_jia / shou_pan_jia`
- `cheng_jiao_liang`
- `liang_bi / wei_bi`
- `peroid_type`：`1min`、`1day`

用途：
- 1min：聚合当日日K、预测成交量
- 1day：历史日K、MA/MACD、策略2窗口

### 4.2 `b_daily_chance`
用途：
- 前一交易日赔率分：`day_win_ratio_score/week_win_ratio_score/total_win_ratio_score`
- 成交量类型：`volume_type`
- 多头/空头组合：`bullish_pattern/bearish_pattern`
- 支撑/压力：`support_price/pressure_price`
- 股性：`stock_nature`

> 注意：该表 stock_code 通常带 `SZ/SH` 前缀，本接口用 `full_stock_code` 查询。

---

## 5. 性能特征（为什么 latest 也不“轻”）

`latest_cr_points` 最耗时的点通常是 **Step D：为了插件判断重新计算历史CR点**：
- 之前会调用一次 `CRPointService.analyze_cr_points`（对 400~700 根K线做全套插件/策略循环）
- 现在已在 `latest_cr_points` 内优化为：**仅对最近90个交易日**进行该步骤（其他接口不受影响）
- 所以 latest 接口天然会是“秒级”而不是“毫秒级”

如果后续想进一步提速，方向一般是：
- 只维护历史C/R点的增量缓存（而不是每次都重算历史）
- 或者 latest 只算“最新一天评分”，历史点由单独缓存/任务维护


