-- ======================================
-- 全A股每日机会数据 - 常用查询SQL
-- ======================================

-- 1. 查看已同步的股票统计
SELECT 
    stock_code, 
    stock_name, 
    stock_nature,
    COUNT(*) as record_count,
    MIN(date) as earliest_date,
    MAX(date) as latest_date
FROM b_daily_chance 
GROUP BY stock_code, stock_name, stock_nature
ORDER BY stock_code;

-- 2. 按股性统计股票数量
SELECT 
    stock_nature,
    COUNT(DISTINCT stock_code) as stock_count,
    COUNT(*) as total_records
FROM b_daily_chance
GROUP BY stock_nature
ORDER BY stock_count DESC;

-- 3. 查看指定股票的最新数据
SELECT * 
FROM b_daily_chance 
WHERE stock_code = 'SH600000' 
ORDER BY date DESC 
LIMIT 10;

-- 4. 查看今日所有股票的机会数据
SELECT 
    stock_code,
    stock_name,
    stock_nature,
    chance,
    day_win_ratio_score,
    week_win_ratio_score,
    total_win_ratio_score,
    support_price,
    pressure_price
FROM b_daily_chance 
WHERE date = CURDATE()
ORDER BY total_win_ratio_score DESC;

-- 5. 查找高赔率机会（总分 > 30）
SELECT 
    stock_code,
    stock_name,
    stock_nature,
    date,
    chance,
    total_win_ratio_score,
    support_price,
    pressure_price
FROM b_daily_chance 
WHERE total_win_ratio_score > 30
ORDER BY date DESC, total_win_ratio_score DESC
LIMIT 50;

-- 6. 按股性查看平均赔率得分
SELECT 
    stock_nature,
    COUNT(DISTINCT stock_code) as stock_count,
    AVG(day_win_ratio_score) as avg_day_score,
    AVG(week_win_ratio_score) as avg_week_score,
    AVG(total_win_ratio_score) as avg_total_score,
    MAX(total_win_ratio_score) as max_total_score
FROM b_daily_chance
WHERE total_win_ratio_score > 0
GROUP BY stock_nature
ORDER BY avg_total_score DESC;

-- 7. 查看某个时间段内的高机会股票
SELECT 
    stock_code,
    stock_name,
    stock_nature,
    date,
    chance,
    total_win_ratio_score
FROM b_daily_chance 
WHERE date BETWEEN '2025-11-01' AND '2025-11-30'
  AND chance > 10
ORDER BY date DESC, chance DESC
LIMIT 50;

-- 8. 统计数据完整性（有赔率得分的比例）
SELECT 
    COUNT(*) as total_records,
    SUM(CASE WHEN day_win_ratio_score > 0 THEN 1 ELSE 0 END) as has_day_score,
    SUM(CASE WHEN week_win_ratio_score > 0 THEN 1 ELSE 0 END) as has_week_score,
    SUM(CASE WHEN total_win_ratio_score > 0 THEN 1 ELSE 0 END) as has_total_score,
    ROUND(SUM(CASE WHEN day_win_ratio_score > 0 THEN 1 ELSE 0 END) * 100.0 / COUNT(*), 2) as day_score_pct,
    ROUND(SUM(CASE WHEN week_win_ratio_score > 0 THEN 1 ELSE 0 END) * 100.0 / COUNT(*), 2) as week_score_pct,
    ROUND(SUM(CASE WHEN total_win_ratio_score > 0 THEN 1 ELSE 0 END) * 100.0 / COUNT(*), 2) as total_score_pct
FROM b_daily_chance;

-- 9. 查看各股票的最新机会值排名（TOP 20）
SELECT 
    a.stock_code,
    a.stock_name,
    a.stock_nature,
    a.date,
    a.chance,
    a.total_win_ratio_score
FROM b_daily_chance a
INNER JOIN (
    SELECT stock_code, MAX(date) as max_date
    FROM b_daily_chance
    GROUP BY stock_code
) b ON a.stock_code = b.stock_code AND a.date = b.max_date
ORDER BY a.chance DESC
LIMIT 20;

-- 10. 查看指定日期范围内，波段股票的高机会日
SELECT 
    stock_code,
    stock_name,
    date,
    chance,
    day_win_ratio_score,
    week_win_ratio_score,
    total_win_ratio_score
FROM b_daily_chance
WHERE stock_nature = '波段'
  AND date >= DATE_SUB(CURDATE(), INTERVAL 30 DAY)
  AND total_win_ratio_score > 25
ORDER BY total_win_ratio_score DESC, date DESC
LIMIT 50;

-- 11. 统计每只股票的高机会天数（机会值 > 10）
SELECT 
    stock_code,
    stock_name,
    stock_nature,
    COUNT(*) as high_chance_days,
    AVG(chance) as avg_chance,
    MAX(chance) as max_chance,
    MAX(total_win_ratio_score) as max_total_score
FROM b_daily_chance
WHERE chance > 10
GROUP BY stock_code, stock_name, stock_nature
ORDER BY high_chance_days DESC
LIMIT 30;

-- 12. 查看all_stock表中未退市的股票总数
SELECT COUNT(*) as active_stock_count
FROM all_stock
WHERE `是否退市` != 1 OR `是否退市` IS NULL;

-- 13. 对比all_stock和b_daily_chance，找出还未同步的股票
SELECT a.code, a.name, a.nature
FROM all_stock a
LEFT JOIN (
    SELECT DISTINCT stock_code 
    FROM b_daily_chance
) b ON a.code = b.stock_code
WHERE (a.`是否退市` != 1 OR a.`是否退市` IS NULL)
  AND b.stock_code IS NULL
ORDER BY a.code;

-- 14. 查看最近一周的机会趋势（某只股票）
SELECT 
    date,
    chance,
    day_win_ratio_score,
    week_win_ratio_score,
    total_win_ratio_score,
    support_price,
    pressure_price
FROM b_daily_chance
WHERE stock_code = 'SH600000'
  AND date >= DATE_SUB(CURDATE(), INTERVAL 7 DAY)
ORDER BY date DESC;

