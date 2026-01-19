
import os

file_path = r'c:\Users\lenovo\Desktop\alpha_strategy_v2\frontend\js\app.js'

with open(file_path, 'r', encoding='utf-8') as f:
    lines = f.readlines()

start_marker = "// 🟢 计算真实支撑（动态支撑）：Max(前一日支撑, 最近一个C日支撑)"
# Note: The end marker needs to be matched carefully. 
# It looks like: result += `<span style="color: #26a69a; font-weight: bold;">真实支撑${labelSuffix}: ${supportDisplay}${realSupportNote}</span><br/>`;
# We can look for the line containing "真实支撑${labelSuffix}"
end_marker_part = "真实支撑${labelSuffix}"

start_idx = -1
end_idx = -1

for i, line in enumerate(lines):
    if start_marker in line:
        start_idx = i
    if end_marker_part in line and start_idx != -1 and i > start_idx:
        end_idx = i
        break

if start_idx != -1 and end_idx != -1:
    print(f"Found block from line {start_idx+1} to {end_idx+1}")
    
    # New content
    new_content = """                                    // 🟢 计算真实支撑（动态支撑）- 新逻辑
                                    // 规则：
                                    // 1. 找到当前日期之前的最后一个信号（C点或R点）。
                                    // 2. 如果上个信号是R点 -> 真实支撑 = 前一日支撑 (重置)。
                                    // 3. 如果上个信号是C点 -> 真实支撑 = MAX(前一日支撑, 该C点当日支撑)。
                                    // 4. 如果没有前置信号 -> 真实支撑 = 前一日支撑。

                                    // 1. 获取前一日支撑
                                    let prevSupportVal = 0;
                                    const currIndex = params[0].dataIndex;
                                    if (currIndex > 0 && dates[currIndex - 1]) {
                                        const prevDateRow = dates[currIndex - 1].split(' ')[0];
                                        if (supportPriceMap[prevDateRow]) {
                                            prevSupportVal = supportPriceMap[prevDateRow] / 100.0;
                                        }
                                    }

                                    // 2. 寻找最近的信号（C或R）
                                    let lastSignalType = 'NONE'; // 'C' or 'R' or 'NONE'
                                    let lastCDateStr = '';
                                    let cSupportVal = 0;

                                    // 合并所有信号
                                    const allSignals = [];
                                    
                                    // 添加策略1 C点
                                    if (crPointsData.c_points) {
                                        crPointsData.c_points.forEach(p => allSignals.push({ type: 'C', date: p.triggerDate }));
                                    }
                                    // 添加策略2 C点
                                    if (crPointsData.strategy2_c_points) {
                                        crPointsData.strategy2_c_points.forEach(p => allSignals.push({ type: 'C', date: p.triggerDate }));
                                    }
                                    // 添加R点 (R点通常有 date 字段)
                                    if (crPointsData.r_points) {
                                        crPointsData.r_points.forEach(p => {
                                            // 兼容不同的日期字段名
                                            const d = p.date || p.triggerDate; 
                                            // 只有效保存日期的R点才算
                                            if (d) allSignals.push({ type: 'R', date: d });
                                        });
                                    }

                                    if (allSignals.length > 0) {
                                        // 找到日期 < 当前日期的最近一个信号
                                        // 过滤并排序
                                        const validSignals = allSignals.filter(p => p.date < dateOnly);
                                        
                                        if (validSignals.length > 0) {
                                            // 按日期升序排序
                                            validSignals.sort((a,b) => new Date(a.date) - new Date(b.date));
                                            
                                            // 获取最后一个信号
                                            const lastSignal = validSignals[validSignals.length - 1];
                                            
                                            if (lastSignal.type === 'R') {
                                                lastSignalType = 'R';
                                                // R点之后，重置，不参考C点支撑
                                            } else {
                                                lastSignalType = 'C';
                                                lastCDateStr = lastSignal.date;
                                                // 获取该C点的支撑位
                                                if (supportPriceMap[lastCDateStr]) {
                                                    cSupportVal = supportPriceMap[lastCDateStr] / 100.0;
                                                }
                                            }
                                        }
                                    }

                                    // 3. 计算最终真实支撑
                                    let realSupportPrice = prevSupportVal; // 默认（R点后或无信号）
                                    let realSupportNote = "";

                                    if (lastSignalType === 'C') {
                                        // 如果是C点后，取MAX(前日, C日)
                                        realSupportPrice = Math.max(prevSupportVal, cSupportVal);
                                        
                                        if (realSupportPrice > 0) {
                                            if (cSupportVal > prevSupportVal) {
                                                realSupportNote = ` (C日${lastCDateStr})`;
                                            } else {
                                                // realSupportNote = ` (前日)`;
                                            }
                                        }
                                    } else if (lastSignalType === 'R') {
                                        // R点后，只看前日支撑
                                        realSupportNote = ""; // 可选提示 `(R后重置)`
                                    }

                                    // 显示逻辑
                                    let supportDisplay = actualSupportPrice.toFixed(2);
                                    if (realSupportPrice > 0) {
                                        supportDisplay = realSupportPrice.toFixed(2);
                                    }

                                    result += `<span style="color: #26a69a; font-weight: bold;">真实支撑${labelSuffix}: ${supportDisplay}${realSupportNote}</span><br/>`;
"""
    # Replace the lines
    # lines[start_idx:end_idx+1] = [new_content + "\n"]
    # The new_content is a string, needs to be one entry in list or split
    
    # Just write the whole file
    with open(file_path, 'w', encoding='utf-8') as f:
        for i in range(start_idx):
            f.write(lines[i])
        
        f.write(new_content)
        f.write("\n")
        
        for i in range(end_idx + 1, len(lines)):
            f.write(lines[i])
            
    print("Successfully replaced content.")

else:
    print("Could not find start or end marker.")
    exit(1)
