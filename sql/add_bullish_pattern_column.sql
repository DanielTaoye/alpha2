-- 添加多头组合列到daily_chance表
-- 支持单个组合或多个组合用逗号连接（如"十字星+中阳线,阳包阴"）
ALTER TABLE daily_chance 
ADD COLUMN bullish_pattern VARCHAR(100) NULL COMMENT '多头组合(多个组合用逗号连接)' AFTER volume_type;

-- 添加索引以便查询
ALTER TABLE daily_chance 
ADD KEY idx_bullish_pattern (bullish_pattern) COMMENT '多头组合索引';

