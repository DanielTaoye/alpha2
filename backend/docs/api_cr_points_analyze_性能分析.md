# /api/cr_points/analyze 接口性能分析（调用顺序 + 数据流）

> 目标：解释为什么 `api/cr_points/analyze` 可能“很慢”，并把**调用顺序**、**涉及的数据（DB/内存结构）**、**主要耗时点**梳理清楚，方便你后续做 profiling 与优化。

## 1. 接口概览

- **路由**：`POST /api/cr_points/analyze`（同逻辑也被 `/api/cr_analysis` 复用）
- **入口文件**：`backend/app.py`
- **Controller**：`backend/interfaces/controllers/cr_point_controller.py -> CRPointController.analyze_cr_points`
- **核心服务**：
  - `backend/application/services/kline_service.py -> KLineApplicationService.get_kline_data`
  - `backend/application/services/cr_point_service.py -> CRPointService.analyze_cr_points`

## 2. 请求/响应数据（前端视角）

### 2.1 请求 JSON
`cr_point_controller.py` 读取的字段：

- `stockCode`（必填）
- `stockName`（可选）
- `tableName`（必填：K线数据表名，例如 `basic_data_XXXXXX`）
- `period`（可选：默认 `day`，支持 `day/week/month/30min`）
- `stockNature`（可选：短线/波段/中长线；也兼容 `stock_nature`）

### 2.2 响应结构（核心字段）
Controller 会把结果包一层 `ResponseBuilder.success(data, message)`，其中 `data` 主要包含：

- `c_points_count` / `r_points_count`
- `c_points` / `r_points`
- `rejected_c_points`（包含 `C_REJECTED`、`R_REJECTED` 等）
- `strategy1_scores` / `strategy2_scores`（**按日期**记录的评分明细，数据量≈K线根数）
- `macd` / `ma`
- `stock_nature`

> 注意：`strategy1_scores`/`strategy2_scores` 会随K线根数线性增长，是返回体的“大头”之一。

---

## 3. 调用顺序（从路由到 DB/算法）

下面按真实执行顺序（同步）梳理，括号里标注关键 I/O、循环规模与数据形态。

### 3.1 路由入口
1. `backend/app.py`
   - `@app.route('/api/cr_points/analyze', methods=['POST'])`
   - 调用：`cr_point_controller.analyze_cr_points()`

### 3.2 Controller：解析请求 + 准备输入数据
2. `CRPointController.analyze_cr_points()`
   1) `request.get_json(force=True)`（JSON解析）
   2) 调用 `KLineApplicationService.get_kline_data(table_name, period, exclude_today=True)`
      - **DB**：读取K线（最多 `LIMIT 2000`，但受时间范围配置影响，日K默认最近730天）
      - **CPU**：计算 `MACD`、`MA`
      - 返回：`kline_data`（list[dict]）、`macd`（dict）、`ma`（dict）
   3) Controller 将 `kline_data` 再次转换为 `domain.models.kline.KLineData`（逐根解析日期字符串、构造对象）
   4) 额外加载策略2需要的数据（**DB：daily_chance 批量查询**）
      - `DailyChanceRepositoryImpl.find_by_stock_code(stock_code, start_date, end_date)`
      - 在内存里构建：
        - `volume_types: { 'YYYY-MM-DD': volume_type }`
        - `bullish_patterns: { 'YYYY-MM-DD': bullish_pattern }`
   5) 调用核心分析：`CRPointService.analyze_cr_points(...)`

### 3.3 CRPointService：初始化缓存 + 循环跑策略
3. `CRPointService.analyze_cr_points(stock_code, kline_objects, ...)`
   1) **初始化缓存（批量预加载）**
      - `CRStrategyService.init_cache(stock_code, start_date, end_date)`
        - **DB：daily_chance** 再查一遍区间数据（`b_daily_chance`）
        - 同时 `CPointPluginService.init_cache(...)`
          - **DB：daily**（每股一张 `basic_data_xxx` 表，`peroid_type='1day'`）
          - **DB：daily_chance**（`b_daily_chance`）
      - `RPointPluginService.init_cache(stock_code, start_date, end_date)`
        - **DB：daily**（同上）
        - **DB：daily_chance**（同上）

      > 结论：单次请求里，`daily_chance` 至少会被批量查询 **3次**（Controller 1次 + CRStrategy 1次 + C点插件 1次 + R点插件 1次；其中 CRStrategy 又会触发 C点插件 init），`daily` 至少会批量查询 **2次**（C点插件 + R点插件）。

   2) 主循环：对每根K线（N≈730 for day）执行：
      - **先判 R 点**：`r_point_service.check_r_point(...)`
        - 内部包含多个插件（乖离率、强转弱、压力位滞涨、跌破支撑、高位发R、箱体回踩…）
        - 大部分使用缓存；但遇到“缓存不足/缺前收价/缺交易日”会触发额外 DB 查询（见 5.3）
      - **再判 C 点策略1**：`CRStrategyService.check_c_point_strategy_1(...)`
        - 基础分=赔率分（`total_win_ratio_score`）+胜率分（由 `volume_type` 派生）
        - 再跑 `CPointPluginService.apply_plugins(...)`（阴线/风险K线/不追涨/急跌抢反弹/牛市插件等）
      - **再跑 策略2**：`Strategy2Service.check_strategy2(...)`
        - 依赖 `ma/macd`（数组按 index 对齐）+ `volume_types/bullish_patterns` + `daily_data_30`
      - **CR关系校验**：同日C/R冲突、C间隔≥2交易日、RR不连续等

   3) 清理：`clear_cache()`（释放内存）

---

## 4. 涉及的数据（DB 表/字段 + 内存结构）

### 4.1 K线表（每股一张）
来源：请求里的 `tableName`（直接拼到 SQL）

1) `KLineRepositoryImpl.get_kline_data`
- SQL（简化）：
  - `SELECT shi_jian, kai_pan_jia, zui_gao_jia, zui_di_jia, shou_pan_jia, cheng_jiao_liang, liang_bi, wei_bi`
  - `WHERE peroid_type = ? AND shi_jian >= ?`
  - `ORDER BY shi_jian DESC LIMIT 2000`
- 输出：`List[KLineData]` -> 在应用层转成 `list[dict]`

2) `DailyRepositoryImpl.find_by_date_range`（用于插件缓存）
- SQL：`WHERE DATE(shi_jian) BETWEEN start_date AND end_date AND peroid_type='1day' ORDER BY shi_jian ASC`
- 同时额外查一次：`start_date` 之前一条收盘价，用作第一根 `pre_close`

### 4.2 `b_daily_chance`（每日机会表）
来源：`DailyChanceRepositoryImpl`

- 常用字段（本接口实际用到）：
  - `stock_code, date`
  - `total_win_ratio_score`（策略1赔率分）
  - `day_win_ratio_score`（R点插件部分逻辑使用）
  - `volume_type`（策略1/2、C点插件、R点插件都用）
  - `bullish_pattern`（策略2、部分C点插件）
  - `bearish_pattern`（R点插件）
  - `support_price, pressure_price`（R点插件；注意代码里通常要 `/100.0`）
  - `stock_nature`（股性阈值）

### 4.3 内存结构（返回体/中间态）

- `kline_objects: List[KLineData]`（长度 N）
- `ma_data/macd_data: Dict[str, List[Optional[float]]]`（长度 N）
- `volume_types/bullish_patterns: Dict[str, str]`（按日期键）
- `strategy1_scores/strategy2_scores: Dict[str, {...}]`（按日期键，数量≈N，返回给前端）
- `c_points/r_points/rejected_*: List[CRPoint]`（返回给前端）

---

## 5. 主要“慢点”定位（按优先级）

### 5.1 最高优先：重复 DB 批量查询（daily/daily_chance 多套缓存）
**现状：**
- Controller 为策略2查一次 `b_daily_chance`（volume_type/bullish_pattern）
- `CRStrategyService.init_cache` 再查一次 `b_daily_chance`
- `CPointPluginService.init_cache` 再查一次 `daily` + `b_daily_chance`
- `RPointPluginService.init_cache` 再查一次 `daily` + `b_daily_chance`

**影响：**
- 同一股票、同一日期区间，重复 I/O 与对象构建（MySQL + Python 映射）；
- 在并发下会放大数据库压力与锁/连接开销。

### 5.2 高优先：大量 `INFO` 日志在主循环内输出
`CRStrategyService.check_c_point_strategy_1` 每次调用都会打印多条 `logger.info`；主循环 N≈730（day）时，单请求就可能写入几千行日志。

**影响：**
- 日志落盘是 I/O；在 Windows 下尤为明显；
- 多线程/多进程时日志锁竞争也会放大。

### 5.3 高优先：插件在“缓存不足/缺前收/缺交易日”时的 DB 回退查询可能发生在循环内
典型触发点（只要缓存内日期不够或字段缺失，就可能查询）：

- `RPointPluginService._get_previous_trading_dates_from_cache(...)`
  - 若缓存里 `<25` 个交易日，会对 `basic_data_{stock_code}` 额外查 `LIMIT 25` 的交易日列表
- `RPointPluginService._check_bearish_kline_patterns(...)`
  - 若 `pre_close` 缺失，会再查一次“前一交易日收盘价”
- 若这些发生在循环里（尤其对起始区间的前几十天），会出现“每根K线多一次SQL”的放大效应。

### 5.4 中优先：数据转换与重复构建对象
当前链路里有明显的重复转换：
- `KLineRepositoryImpl` 读出 `KLineData` 对象
- `KLineApplicationService` 又转 `to_dict()`
- `CRPointController` 又把 `kline_data_list`（dict）重新转回 `KLineData`（还要 `strptime`）

**影响：**
- CPU + GC 压力；在 N≈730 时还好，但配合其它慢点会叠加。

### 5.5 中优先：策略2 `daily_data_30` 在循环内每次构建 30 日窗口
`CRPointService.analyze_cr_points` 对每个 index 都用 for 循环组一个长度 30 的 list（O(30*N)）。

**影响：**
- 纯 CPU，常数不大，但在插件+日志很重时会变得明显。

### 5.6 基础设施：SQL 索引缺失会直接把接口拖垮
强烈建议确认这些索引是否存在（尤其数据量大时）：

- K线表（每股一张）：至少需要 `(peroid_type, shi_jian)` 复合索引
- `b_daily_chance`：至少需要 `(stock_code, date)` 复合索引

如果没有索引，即使 `LIMIT 2000` 也可能触发全表扫描或文件排序。

---

## 6. 建议你怎么“量化”慢在哪里（最小侵入）

### 6.1 在关键阶段打点（建议加到日志里）
建议在这些边界打印耗时（ms）：

- `kline_repository.get_kline_data`（SQL耗时）
- `macd_service.calculate_*`（CPU）
- `ma_service.calculate_*`（CPU）
- `daily_chance_repo.find_by_stock_code`（SQL耗时：Controller & 各 cache init）
- `daily_repo.find_by_date_range`（SQL耗时：插件 cache init）
- 主循环：统计
  - 总K线根数 N
  - R点插件触发次数/调用耗时
  - C点策略1耗时（含插件）
  - 策略2耗时

### 6.2 开 MySQL 慢查询日志
如果你是本地/自建 MySQL：
- 开启 slow query log（阈值比如 0.2s）
- 观察是否出现：
  - `b_daily_chance WHERE stock_code=? AND date BETWEEN ? AND ?`
  - `basic_data_xxx WHERE DATE(shi_jian) BETWEEN ...`
  - `SELECT DISTINCT DATE(shi_jian)`（交易日回退查询）

---

## 7. 可落地的优化建议（从“收益最大”到“改动最小”）

### 7.1 先做“减 IO”
- **合并缓存初始化**：把 `daily` + `daily_chance` 的区间查询做成“单处加载、多人复用”，避免 2~4 次重复批量查询。
- **避免 Controller 额外查 daily_chance**：策略2需要的 `volume_type/bullish_pattern` 可以直接从已缓存的 `daily_chance` 提取（或把 map 预构建一次并传下去）。

### 7.2 再做“减日志”
- 将主循环内的 `info` 日志改为 `debug`，或加采样（例如每50根打一条）。

### 7.3 避免循环内 DB 回退
- cache 初始化时把 `start_date` 往前多取（例如多取 60 个交易日），确保插件需要的“前N日”都能在缓存命中，减少 `_get_previous_trading_dates_from_cache` 的数据库回退。

### 7.4 减少对象转换
- `KLineApplicationService` 可直接返回 `List[KLineData]`（或 Controller 直接用 repository 的对象），减少 dict<->object 往返。

### 7.5 安全/稳定性（顺带一提）
- `tableName` 被直接拼进 SQL（f-string），理论上存在 SQL 注入风险；至少要做白名单校验（只能是 `basic_data_` 前缀 + `[0-9a-zA-Z_]`）。

---

## 8. 文件与关键代码位置索引

- 路由：`backend/app.py`
- Controller：`backend/interfaces/controllers/cr_point_controller.py`
- K线应用服务：`backend/application/services/kline_service.py`
- K线仓储：`backend/infrastructure/persistence/kline_repository_impl.py`
- CR点应用服务：`backend/application/services/cr_point_service.py`
- 策略1：`backend/domain/services/cr_strategy_service.py`
- C点插件：`backend/domain/services/c_point_plugin_service.py`
- R点插件：`backend/domain/services/r_point_plugin_service.py`
- 策略2：`backend/domain/services/strategy2_service.py`
- daily_chance 仓储：`backend/infrastructure/persistence/daily_chance_repository_impl.py`
- daily 仓储：`backend/infrastructure/persistence/daily_repository_impl.py`


