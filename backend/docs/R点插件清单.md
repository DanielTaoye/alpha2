## R点插件清单（R plugin）

本文档目标：把项目内**全部 R 点插件**按真实执行顺序完整列出，并说明每个插件的**触发条件/依赖数据/关键阈值**。

---

## 0. 总体说明（非常重要）

- **真实执行顺序**以 `backend/domain/services/r_point_plugin_service.py::RPointPluginService.check_r_point()` 为准：从上到下依次检查，**命中第一个插件就直接返回**（返回的 `plugins` 列表通常只包含 1 个插件结果）。
- **插件2「临近压力位滞涨」被刻意放在最后**（代码注释：避免缺 C 点影响其他插件）。
- 下面的“插件编号”按 `check_r_point()` 的顺序与项目常用叫法整理；注意：源码里部分 docstring 的“插件X”编号存在历史残留（不完全一致），本文以实际调用顺序为准。

---

## 1. 输入数据依赖（你排查漏触发时最常用）

R 插件会用到下列数据（不是每个插件都需要全部）：

- **daily（K线）**：开高低收、昨收等（来自 `daily_repo` / 缓存 `_daily_cache`）
- **daily_chance**：`volume_type`（量型）、`bearish_pattern`（空头组合）、`support_price`（支撑）、`pressure_price`（压力）、`day_win_ratio_score`（赔率/胜率相关分）、`stock_nature`（股性）等（来自 `daily_chance_repo` / 缓存 `_daily_chance_cache`）
- **MA 序列**：`ma5/ma10/ma20/ma30/ma60`（来自上层传入 `ma_data`）
- **MACD 序列**：`dif/dea/macd`（来自上层传入 `macd_data`；插件2可降级为“本地用收盘价计算MACD”）
- **kline_data 列表**：用于需要按 index 取过去一段K线的插件（箱体回踩、顶背离等）
- **最近C点日期**：`c_point_date`
- **最近有效点类型**：`last_valid_point_type`（插件2/5需要它来判断“上一个有效点必须是C”）

---

## 2. 可配置阈值（来自 `backend/config/strategy_config.json`）

- `r_point_plugins.pressure_stagnation.distance_threshold_pct`
  - 影响：插件2（也被插件5复用为“股价距压力线阈值”）
  - 当前配置：10.0（%）
- `r_point_plugins.high_position_r.gain_threshold_pct`
  - 影响：插件7（高位发R）“20日最低价到当前价涨幅阈值”
  - 当前配置：25.0（%）
- `r_point_plugins.high_stagnation_bearish.gain_threshold_pct`
  - 影响：插件10（高位滞涨+空头组合）“高位涨幅阈值”
  - 当前配置：25.0（%）

另外：市场类型 `market_type` 会影响插件5/插件2（熊市限定逻辑）。

---

## 3. 全部 R 插件列表（按真实执行顺序）

> 表格中阈值说明：很多阈值会区分主板/非主板（主板一般 6%/3%/9.9%，非主板一般 8%/5%/19.8%）。

| 插件名称 | 插件描述 | 插件判断逻辑 |
|---|---|---|
| 插件1：乖离率偏离 | 识别**短期涨幅过大**后出现的风险信号（放量 + 空头K线/空头组合）。 | **前置依赖**：需要当日 `daily` + `daily_chance`（无则跳过）。部分子条件需要 `ma_data` + `current_index`（用于 MA10 乖离）。<br><br>**公共判定要素**：<br>- 放量判断：`volume_type` 包含 `X/Y/H`（XYH）或 `X/Y/Z/H`（XYZH）<br>- 空头K线：由 `_check_bearish_kline_patterns()` 命中（包含冲高回落/高开低走/高振幅十字星/阴线大跌等）<br>- 空头组合：`daily_chance.bearish_pattern` 非空<br><br>**子条件（任一触发即触发插件）**：<br>- 条件1：连续 ≥2 个涨停（主板≥9.9%，非主板≥19.8%） + 放量XYH +（空头分歧K线(需振幅门槛) 或 阴线跌幅>3%/5%）<br>- 条件2：前3日累计涨幅 >15%（非主板20%） + 放量XYH +（空头分歧K线 或 阴线跌幅>3%/5%）<br>- 条件3：前5日累计涨幅 >20%（非主板25%） + 放量XYH +（空头分歧K线 或 阴线跌幅>3%/5%）<br>- 条件4：5连阳 + 5日涨幅 >20%（非主板25%） + 放量XYH +（空头分歧K线 或 阴线跌幅>3%/5%）<br>- 条件5：前15日涨幅 >50% + 放量XYZH +（空头分歧K线 或 空头组合）<br>- 条件6：前20日涨幅 >50% + 放量XYZH +（空头分歧K线 或 空头组合）<br>- 条件7：当日收盘相对 MA10 乖离 >15% + 放量XYH + 空头分歧K线（需振幅门槛） |
| 插件3：强转弱未反转 | 针对“强转弱”空头形态的次日确认：昨日出现强转弱，今日未修复且出现G量型。 | **条件**：<br>- 前一日 `bearish_pattern` 包含“强转弱”<br>- 今日未修复：`close < (昨日close + 昨日open)/2`<br>- 今日 `volume_type` 包含 `G` |
| 插件4：基本面突发利空 | 识别“一字跌停 / T字跌停”这类突发利空形态。 | **条件**：<br>- 当日跌幅达到跌停阈值（主板 ≤ -9.9%，非主板 ≤ -19.8%）<br>- 且满足其一：<br>  - 一字跌停：`open==high==low==close`<br>  - T字跌停：`open==low==close` 且 `high>close` |
| 插件5：上冲乏力（熊市特定） | 熊市里识别“从C点上冲后，临近压力位、强势后转弱”的卖出风险。 | **前置**：仅熊市；且 `last_valid_point_type=='C'`，并传入 `c_point_date`。<br><br>**条件（全部同时满足）**：<br>- 从 **C日最低价** 到今日收盘累计涨幅 >15%<br>- 使用“**今日前一交易日**”的 `daily_chance`：要求 `pressure_price` 存在，且 `day_win_ratio_score` 满足：\(0 < score < 阈值\)。阈值按股性：短线15、波段12、中长线10。<br>- 今日股价距压力线：\(0\% < (pressure-close)/close < 距离阈值\)（与插件2同一配置项）<br>- 前一日涨幅：主板 ≥6%，非主板 ≥8%<br>- 今日放量：`volume_type` 含 `A/X/Y/Z/H` 任一<br>- 今日命中任意空头K线形态（复用 `_check_bearish_kline_patterns()`） |
| 插件6：跌破支撑位 | 最基础的“跌破支撑 + 放量”风险卖点。 | **条件（同时满足）**：<br>- 今日收盘 **跌破前一交易日支撑位**（支撑位来自前一日 `daily_chance.support_price`，数据库为100倍价）<br>- 今日放量：`volume_type` 含 `X/Y/Z`（XYZ） |
| 插件14：横盘震荡+风险信号 | 识别“上个R之后多次C点支撑/开盘/MA20接近”的横盘区间，并在横盘阶段内给出风险R信号。 | **前置依赖**：需要 `historical_c_points/historical_r_points`（C点不落库，只能由 `CRPointService.analyze_cr_points()` 循环传入），并需要 `ma_data.ma20` + `current_index` + `kline_data`（用于按“C点日期”取MA20）。<br><br>**横盘阶段判定（同时满足）**：<br>- 今日之前“最后一个有效信号”为C；并回溯得到“上个R之后的连续C序列”，至少2个C。记最早C为 firstC（离上个R最近），最新C为 lastC（离今天最近）。<br>- 支撑接近：\(|support(lastC)-support(firstC)|/support(firstC) < 6\%\)（支撑来自各C日 `daily_chance.support_price`）<br>- 开盘接近：\(|open(lastC)-open(firstC)|/open(firstC) < 2\%\)（开盘来自C点自身或当日K线）<br>- 对该连续C序列内每个C日：\(|open(C)-MA20(C)|/open(C) < 6\%\)<br><br>**横盘阶段内风险触发（任一触发即出R）**：<br>1) 跌破或已跌破 MA20 + `DEA>DIF`（死叉状态）<br>2) 跌破或已跌破 最近C日支撑位 + `DEA>DIF`<br>3) 当日有任意量型（`volume_type`非空） + 跌破或已跌破 最近C日支撑位<br>4) 当日有任意量型 + 跌破或已跌破 MA20 |
| 插件13：阶段涨幅过大 | 阶段涨幅过大后转弱：满足“阶段涨幅 + 量型 + 跌破MA20 + MACD死叉状态”同日共振出R。 | **前置依赖**：需要 `ma_data` + `macd_data` + `current_index`，以及当日 `daily/daily_chance` 可用。<br><br>**条件（全部同时满足）**：<br>- 30交易日累计涨幅 ≥ 30%：用 **t-30 收盘 → 今日收盘**（即“今天往前的31个交易日”起点收盘价到今天收盘价）<br>- 今日出现任意成交量类型：`daily_chance.volume_type` 非空<br>- 跌破MA20：昨日 `close > MA20` 且 今日 `close < MA20`<br>- MACD死叉状态：今日 `DIF < DEA` |
| 插件7：高位发R | 多头趋势高位出现转弱：均线多头排列背景下，高位涨幅够大、跌破支撑且MACD死叉。 | **前置依赖**：需要 `ma_data` + `macd_data` + `current_index`。<br><br>**条件（全部同时满足）**：<br>- 均线多头排列：在“今日或近3日”出现过 `MA5>MA10>MA20>MA30>MA60`<br>- 20日最低价到当前价涨幅 > 阈值（配置项 `high_position_r.gain_threshold_pct`，当前 25%）<br>- 当前价 > MA10（确认处于短期高位）<br>- 当前价跌破前一日支撑位（前一日 `support_price`）<br>- MACD死叉：当天或近5日内出现 DIF 从上穿下 DEA；若死叉发生在过去几天，要求今天仍处于 `DIF<DEA` |
| 插件8：箱体回踩被跌破 | 识别箱体结构回落：高位回撤足够大、箱体幅度足够大，且跌破支撑并出现MACD死叉。 | **前置依赖**：需要 `macd_data` + `current_index` + `kline_data`，且 `current_index>=42`（至少 20+22 个交易日）。<br><br>**步骤/条件（全部同时满足）**：<br>- 近20日（含当日）最高价日为 X；且 X日最高价相对当前价回撤 >20%<br>- 从 X 向前22日：若存在比 X 更高的高点则为 Y；同时找这22日内最低价日 Z<br>- 箱体成立：若有 Y，则 \(Y高 - Z低\)/\(Z低\) >20%；否则 \(X高 - Z低\)/\(Z低\) >20%<br>- 当前价跌破前一日支撑位<br>- 近5日内出现 MACD 死叉“转换点”（前一日 DIF>DEA 且当日 DIF<DEA） |
| 插件9：趋势向下 + 跌破支撑 + MACD死叉 | 识别“低位C之后的下行趋势确认”：低位C + 跌破支撑 + 死叉（含近几日）。 | **前置依赖**：需要 `ma_data` + `macd_data` + `current_index` + `kline_data` + `c_point_date`。<br><br>**条件（全部同时满足）**：<br>- 低位C判定：上个C日（传入 `c_point_date`）收盘 < 上个C日 MA60<br>- 跌破支撑满足其一：<br>  - 今日或近3个交易日中，存在“收盘跌破前一交易日支撑位”（复用统一函数 `_is_close_break_prev_support()`）<br>  - 或 今日收盘跌破“上个低位C当日”的支撑位（`support_price`）<br>- MACD满足其一：<br>  - 今日处于死叉状态（`DIF<DEA`）<br>  - 或近3个交易日内出现死叉转换点（前一日 DIF>DEA，当日 DIF<DEA） |
| 插件11：MACD中长线死叉 + 跌破支撑 | 仅用于“中长线股性”的风险卖点：MACD红柱转蓝柱 + 跌破支撑。 | **前置依赖**：需要 `macd_data` + `current_index`。<br><br>**条件（全部同时满足）**：<br>- `stock_nature == '中长线'`<br>- 当日 `volume_type` 非空（任意量型即可）<br>- 近3日内出现死叉（更严格的定义：前一日 `MACD>0`，当日 `MACD<0` 且当日 `DIF<DEA`）<br>- 今日收盘跌破前一日支撑位 |
| 插件12：中长线顶背离 | 中长线专用顶背离：价格创新高但DIF走弱，且当日需有空头氛围（空头组合或三连阴）。 | **前置依赖**：需要 `macd_data` + `current_index` + `kline_data`，且 `stock_nature=='中长线'`。<br><br>**触发前置**（满足其一）：<br>- 当日空头组合非空；或<br>- 三连阴（前天/昨天/今天均 `close<open`）<br><br>**回溯逻辑（核心）**：<br>- Step1：从今天往前最多10个交易日，找最近一次“金叉G1”（以 `MACD` 从负变正为金叉信号）；未找到则失败<br>- Step2：找 G1 之前最近一次“死叉S1”（满足 DIF从上穿下DEA + 红柱转蓝柱）<br>- Step3：在 S1 之前找 DIF 局部高点 H1（形态规则：当日DIF与前一日DIF均大于再往前8日DIF）并取 H1 的最高价 Price_H1<br>- Step4：在 G1 之后、今天之前，找 DIF 最大的日期 H2 并取最高价 Price_H2<br>- Step5：若 `Price_H2 > Price_H1` 且 `DIF_H2 < DIF_H1`，判定顶背离，触发 R |
| 插件10：高位滞涨 + 空头组合 | 识别“高位滞涨后转弱”：先证明处于高位区间，再要求跌破支撑，最后由“空头组合 或 MACD死叉”触发。 | **前置依赖**：需要 `macd_data` + `current_index`；并要求缓存 `_daily_cache/_daily_chance_cache` 充分（该插件默认用缓存，数据不足会直接不触发）。<br><br>**步骤/条件（全部同时满足）**：<br>- 当日往前不含当日共5个交易日找最高价日 X（取 X日最高价）<br>- 从 X 往前20日找最低价日 Y（取 Y日最低价）<br>- 高位成立：\((X高 - Y低)/Y低\) > 阈值（配置项 `high_stagnation_bearish.gain_threshold_pct`，当前 25%）<br>- 今日收盘跌破前一日支撑位（统一函数 `_is_close_break_prev_support()`）<br>- 最终触发满足其一：<br>  - A：当日空头组合非空（`bearish_pattern` 非空）<br>  - B：当日或近5日内出现 MACD 死叉（含“已处于 DIF<DEA”也算） |
| 插件2：临近压力位滞涨（最后检查） | 在临近压力线附近出现“滞涨/转弱”形态，偏向“压力位附近的风险卖点”。该插件依赖最近C点，且有多情形。 | **前置依赖**：需要当日/前一日 `daily + daily_chance`；并要求上层传入 `c_point_date` 且 `last_valid_point_type=='C'`（插件本身不回溯重算C点）。<br><br>**公共前置（必须全部满足）**：<br>- 使用“今日前一交易日”的压力线 `prev_pressure`（来自 `prev_chance.pressure_price`，100倍价）<br>- 发C日压力线 `c_pressure`（来自 `c_chance.pressure_price`）：若 `c_pressure > prev_pressure` 则直接不触发<br>- 若 `c_pressure==0`：用“发C日前一日收盘 → 今日收盘”的累计涨幅兜底，要求 >15%<br>- 前一日赔率 `day_win_ratio_score > 0`<br>- 距离压力线：\(0\% < (prev_pressure-close)/close < 距离阈值\)（配置项 `pressure_stagnation.distance_threshold_pct`，当前 10%）<br><br>**情形1（当日放量）**：<br>- 当日放量：`volume_type` 含 `X/Y/Z/H`（XYZH）<br>- 且当日“风险K线”成立：<br>  - 形态属于：冲高回落阳/阴线、冲高回落阳/阴十字星、高开低走，且振幅 >6%/8%；或<br>  - 阴线且相对开盘跌幅 ≥3%/5%<br><br>**情形2（当日未放量，但前两日有放量）**：<br>- 当日不放量（无XYZH）但当日风险形态成立（冲高回落阴线/阳线/高开低走，或空头组合含“乌云盖顶”）<br>- 且再往前2个交易日“都满足距离压力线仍在阈值内”<br>- 且前两日任意一天出现过放量（XYZH）<br><br>**情形3（仅熊市）**：<br>- 熊市 + 近3个交易日都没有 A/X/Y/Z 放量 + 当日空头组合非空（不要求当日放量）<br><br>**情形4（空头组合 + MACD死叉）**：<br>- 当日空头组合非空<br>- 且当日满足 `DIF<DEA` 且 `MACD<0`，并在近5日内出现过死叉转换点（前一日 `MACD>0` 且 `DIF>DEA`，当日 `MACD<0` 且 `DIF<DEA`）<br>- MACD优先用外部传入 `macd_data`；若未传入，会用近120日收盘价本地计算 MACD 再判断 |

---

## 4. 排查建议（快速定位“为什么没触发/为什么触发”）

- 最直接：用 `backend/scripts/diagnose_r_plugins.py` 跑指定股票/日期，它会按**真实插件顺序**输出每个插件的逐条条件。
- 常见“没触发”的根因：
  - 缺 `daily_chance`（很多插件直接返回 False）
  - 上层没有传 `ma_data/macd_data/current_index/kline_data`（插件7/8/9/11/12 直接跳过）
  - 上层没有传 `c_point_date` 或 `last_valid_point_type!='C'`（插件2/5 直接不触发）
  - 缓存区间太短导致“历史天数不足”（如插件8需要至少42根K线、插件10需要足够多交易日缓存）


