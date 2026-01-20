
    # =========================
    # 插件15：趋势走弱
    # =========================
    def _check_trend_weakening(
        self,
        stock_code: str,
        date: datetime,
        ma_data: dict,
        macd_data: dict,
        current_index: int,
        kline_data: list
    ) -> RPointPluginResult:
        """
        插件15: 趋势走弱 (仅针对中长线和波段股性)
        
        触发条件（必须全部满足）：
        1. 股性为“中长线”或“波段”。
        2. 放量：volume_type 包含 ['A', 'B', 'C', 'D', 'E', 'F', 'G', 'H', 'Z', 'Y', 'S'] 中任意一个。
        3. MACD死叉：DIF < DEA。
        4. 跌破均线：收盘价 <= MA20。
        5. 风险信号（满足其一）：
           - 出现空头组合 (bearish_pattern 非空)。
           - 分歧K线：["冲高回落阳线", "冲高回落阴线", "冲高回落阳十字星", "冲高回落阴十字星", "高开低走"] 中任意一个。
           - 大阴线：跌幅 (PrevClose - Close)/PrevClose > 3% 且 实体跌幅 (Open - Close)/PrevClose > 3%。
        """
        plugin_name = "趋势走弱"
        
        # 0. 准备数据
        date_str = date.strftime('%Y-%m-%d') if isinstance(date, datetime) else date
        daily_chance = self._daily_chance_cache.get(date_str)
        
        # 1. 股性检查：仅中长线和波段
        stock_nature = "波段" # 默认为波段
        if daily_chance and getattr(daily_chance, "stock_nature", None):
            stock_nature = daily_chance.stock_nature
            
        if stock_nature not in ["中长线", "波段"]:
             return RPointPluginResult(plugin_name, False, "")

        # 2. 放量检查
        volume_type = getattr(daily_chance, "volume_type", None)
        if not volume_type:
             return RPointPluginResult(plugin_name, False, "")
             
        valid_volume_types = {'A', 'B', 'C', 'D', 'E', 'F', 'G', 'H', 'Z', 'Y', 'S'}
        # volume_type 可能包含多个类型，如 "A,H"
        current_types = set(t.strip() for t in volume_type.split(','))
        if not current_types.intersection(valid_volume_types):
             return RPointPluginResult(plugin_name, False, "")

        # 3. MACD死叉检查 (DIF < DEA)
        if not macd_data or not macd_data.get('dif') or not macd_data.get('dea'):
             return RPointPluginResult(plugin_name, False, "")
             
        dif_list = macd_data['dif']
        dea_list = macd_data['dea']
        
        if current_index >= len(dif_list) or current_index >= len(dea_list):
             return RPointPluginResult(plugin_name, False, "")
             
        dif = dif_list[current_index]
        dea = dea_list[current_index]
        
        if dif is None or dea is None or dif >= dea:
             return RPointPluginResult(plugin_name, False, "")

        # 4. 跌破均线检查 (Close <= MA20)
        current_kline = kline_data[current_index]
        close_price = current_kline.close
        
        ma20_list = ma_data.get('ma20', [])
        if current_index >= len(ma20_list):
             return RPointPluginResult(plugin_name, False, "")
             
        ma20 = ma20_list[current_index]
        if ma20 is None or close_price > ma20:
             return RPointPluginResult(plugin_name, False, "")

        # 5. 风险信号检查 (满足其一)
        risk_signal_found = False
        risk_reason = ""

        # 5.1 空头组合
        bearish_pattern = getattr(daily_chance, "bearish_pattern", None)
        if bearish_pattern:
            risk_signal_found = True
            risk_reason = f"空头组合: {bearish_pattern}"

        # 5.2 分歧K线
        if not risk_signal_found:
            divergence_patterns = {
                "冲高回落阳线", "冲高回落阴线", "冲高回落阳十字星", 
                "冲高回落阴十字星", "高开低走"
            }
            # K线形态通常也在 bearish_pattern 或 bullish_pattern 中体现，或者需要单独计算
            # 这里假设如果 bearish_pattern 中包含了这些描述，或者我们需要额外检查形态
            # 由于 daily_chance.bearish_pattern 已经包含了识别出的空头形态，
            # 如果这里的“分歧K线”是 daily_chance 里的标准形态，那上一条已经覆盖。
            # 这里为了保险，检查 bearish_pattern 是否包含这些特定字符串
            if bearish_pattern and any(p in bearish_pattern for p in divergence_patterns):
                 risk_signal_found = True
                 risk_reason = f"分歧K线: {bearish_pattern}"

        # 5.3 大阴线 (跌幅 > 3% 且 实体跌幅 > 3%)
        if not risk_signal_found:
            prev_close = 0
            if current_index > 0:
                prev_close = kline_data[current_index - 1].close
            elif 'prev_close' in kline_data[current_index].__dict__: # 尝试从对象属性获取
                 prev_close = kline_data[current_index].prev_close
            
            if prev_close > 0:
                drop_pct = (prev_close - close_price) / prev_close
                open_price = current_kline.open
                # 实体跌幅: (Open - Close) / PrevClose (严格来说应该是实体长度相对于昨收)
                # 用户描述: "跌幅（相对于昨收）大于3%的阴线（且B＞3%）"
                # B通常指实体 (Body)。在这里理解为实体长度 > 3% 昨收。
                # 且必须是阴线 (Open > Close)
                if open_price > close_price:
                    body_pct = (open_price - close_price) / prev_close
                    if drop_pct > 0.03 and body_pct > 0.03:
                        risk_signal_found = True
                        risk_reason = f"大阴线(跌幅{drop_pct*100:.1f}%, 实体{body_pct*100:.1f}%)"

        if risk_signal_found:
            return RPointPluginResult(
                plugin_name, 
                True, 
                f"放量+MACD死叉+跌破MA20+风险信号({risk_reason})"
            )
            
        return RPointPluginResult(plugin_name, False, "")
