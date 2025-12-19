# R插件「临近压力位滞涨」：上个C点怎么取（调用关系说明）

本文回答两个问题：

- **R插件里“上个C点”到底是谁算出来的？**（当日现算还是外部传入 CR 序列）
- **“临近压力位滞涨”具体用哪个日期的压力位？**（上个C日/上个交易日/今日哪个）

结论先说：

- **插件本身不回溯计算上个C点**。`RPointPluginService._check_pressure_stagnation()` 只“消费”上层传入的 `c_point_date`（最近C点日期）和 `last_valid_point_type`（最近有效点类型），不负责从历史里再找C点。
- **上个C点的计算发生在 CR 序列生成的主循环里**：`application/services/cr_point_service.py::CRPointService.analyze_cr_points()` 在遍历K线时维护 `last_c_point_date` 和 `last_valid_point_type`，每个交易日先把它们传入 R 插件。
- **最新一天接口（`LatestCRPointService`）也会“现算”出历史CR点**（默认只算最近90个交易日），然后把最后一个C点日期传给 R 插件；但它不维护 `last_valid_point_type`，因此 **插件2「临近压力位滞涨」在 latest 接口里默认不会触发**。

---

## 1. 总体调用链（两条入口）

### 1.1 历史分析入口（全量/多日：会维护 CR 序列）

HTTP → Controller → Service → R插件：

- `interfaces/controllers/cr_point_controller.py::CRPointController.analyze_cr_points()`
  - 获取历史K线（`exclude_today=True`）
  - 调用 `CRPointService.analyze_cr_points(...)`
- `application/services/cr_point_service.py::CRPointService.analyze_cr_points()`
  - 遍历 `kline_data`（按时间顺序）
  - 在循环内维护：
    - `last_c_point_date`：最近一个**已被接受**的C点日期
    - `last_valid_point_type`：最近一个**已被接受**的有效点类型（`'C'` 或 `'R'`）
  - 每个交易日 **优先检查 R 点**，调用：
    - `domain/services/r_point_plugin_service.py::RPointPluginService.check_r_point(..., c_point_date=last_c_point_date, last_valid_point_type=last_valid_point_type)`

这条入口下，**“上个C点在哪里”是当次 analyze 循环里现算/现维护出来的**，不是外部传入一整条CR序列。

### 1.2 最新一天入口（单日：会先计算“近90日历史CR”，再算今日）

HTTP → Controller → Service →（先算历史CR）→ 再算今日：

- `interfaces/controllers/latest_cr_point_controller.py::LatestCRPointController.get_latest_cr_points()`
  - 调用 `LatestCRPointService.calculate_latest_cr_points(...)`
- `application/services/latest_cr_point_service.py::LatestCRPointService.calculate_latest_cr_points()`
  - 先取历史K线（不含今天），再**用 `CRPointService.analyze_cr_points()` 计算最近90个交易日的历史CR点**
  - 从 `historical_c_points[-1]` 取最后一个C点的 `trigger_date` 作为 `last_c_point_date`
  - 再调用 `_check_r_point(..., c_point_date=last_c_point_date)`
    - 内部调用 `RPointPluginService.check_r_point(..., last_valid_point_type=None)`

因此这条入口下：

- **“上个C点”是从“现算出来的历史CR点列表”取的最后一个C**（不是从数据库直接读 CR 序列，因为项目里 C 点不落库）。
- 但 `last_valid_point_type` 被显式置为 `None`，所以 **插件2「临近压力位滞涨」要求 `last_valid_point_type=='C'`，在 latest 接口默认不会触发**。

---

## 2. 插件2「临近压力位滞涨」：它到底如何“取上个C点”

位置：

- `domain/services/r_point_plugin_service.py::RPointPluginService._check_pressure_stagnation()`

关键逻辑是这句“门槛”：

- **只有上层传入了 `c_point_date` 且 `last_valid_point_type == 'C'` 才继续**  
  否则插件直接返回不触发。

这意味着：

- 插件不做“从历史回溯找最近C点”的计算。
- 插件认为 `c_point_date` 已经是“最近的C点”（并且最近有效点类型必须是C，避免“刚出现R点”仍用旧C点误判）。

---

## 3. 这个插件用到的“压力位”到底是哪一天的？

插件涉及三个日期概念：

- **今日**：`date`（正在检查R点的交易日）
- **今日前一交易日**：`prev_date_str`（用于“压力线/赔率”）
- **发C日**：`c_date_str`（由上层传入的 `c_point_date`）
- **发C日前一交易日**：`c_prev_date[0]`（仅在“发C日压力线为空/0”时，取它的收盘价来算涨幅）

### 3.1 今日参考的压力位：用的是“今日前一交易日”的压力线

插件把“压力线距离”计算为：

- `prev_pressure = prev_chance.pressure_price / 100.0`
- `distance_pct = (prev_pressure - current_close) / current_close * 100`

注意：这里用的是 **前一交易日** 的 `daily_chance.pressure_price`，不是今日的。

### 3.2 发C日压力位：取 `c_point_date` 当天的 `daily_chance.pressure_price`

- `c_chance = daily_chance_repo.find_by_stock_and_date(stock_code, c_date_str)`
- `c_pressure = c_chance.pressure_price / 100.0 (若为空则记为0)`

### 3.3 发C日压力位与今日前一日压力位的比较规则

插件要求：

- 如果 `c_pressure > prev_pressure` → **不触发**

业务含义（按注释）：  
“发C日压力线”如果比“今日前一日压力线”更高，认为压力线出现抬升/不匹配，直接跳过。

### 3.4 发C日压力线为空/0 的兜底

如果 `c_pressure == 0`，插件用 **发C日前一日收盘价** 到 **今日收盘价** 的累计涨幅做兜底约束：

- `c_prev_date = previous_trading_day(c_date_str)`
- `c_prev_close = close(c_prev_date)`
- `gain_from_c = (today_close - c_prev_close) / c_prev_close * 100`
- 要求 `gain_from_c > 15`，否则不触发

---

## 4. “前一交易日/发C日前一交易日”是怎么取的（是否每次查库）

R插件统一用 `RPointPluginService._get_previous_trading_dates_from_cache()` 来取“前N个交易日日期”。

### 4.1 正常路径：用进程内缓存（不查库）

在 `RPointPluginService.init_cache()` 里，会预加载 `daily_list` 并生成 `_sorted_dates`（按日期倒序），之后取前序交易日时只在内存里筛选：

- 先拿 `all_dates = self._sorted_dates`  
- 然后取所有 `< current_date_str` 的日期放入列表

**在 analyze_cr_points 历史分析场景下**，`CRPointService.analyze_cr_points()` 会统一预加载 `daily_list` + `daily_chance_list`，并注入到 R 插件缓存中，所以这里基本不回退查库。

### 4.2 兜底路径：缓存为空时才回退查库

如果 `_daily_cache` 为空且 result 不足，并且传入了 `stock_code`，函数才会去查询 `basic_data_{stock_code}` 取前25个交易日。

---

## 5. 回答你的原问题（用一句话对齐）

- **历史分析（`/analyze_cr_points`）**：上个C点是 `CRPointService.analyze_cr_points()` 在遍历K线时“当次现算/现维护”的 `last_c_point_date`，然后传给R插件；插件2不在内部回溯找C点。
- **最新一天（`/get_latest_cr_points`）**：先用 `CRPointService.analyze_cr_points()` 现算近90日的历史CR点列表，再取最后一个C点日期传给R插件；但 `last_valid_point_type` 未维护，插件2默认不会触发（它要求最近有效点类型为C）。


