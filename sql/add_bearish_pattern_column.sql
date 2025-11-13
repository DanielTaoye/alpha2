-- 添加空头组合列到daily_chance表
ALTER TABLE daily_chance 
ADD COLUMN bearish_pattern VARCHAR(255) NULL COMMENT '空头组合（多个组合用逗号连接）' AFTER bullish_pattern;

-- 添加索引以便查询
ALTER TABLE daily_chance 
ADD KEY idx_bearish_pattern (bearish_pattern) COMMENT '空头组合索引';

