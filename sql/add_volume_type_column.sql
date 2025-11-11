-- 添加成交量类型列到daily_chance表
ALTER TABLE daily_chance 
ADD COLUMN volume_type VARCHAR(10) NULL COMMENT '成交量类型(A/B/C/D)' AFTER pressure_price;

-- 添加索引以便查询
ALTER TABLE daily_chance 
ADD KEY idx_volume_type (volume_type) COMMENT '成交量类型索引';

