-- 添加成交量类型列到daily_chance表
-- 支持单个类型（如'A'）或多个类型用逗号连接（如'A,B'或'A,B,C,D,E,F,G,H,X,Y,Z'）
ALTER TABLE daily_chance 
ADD COLUMN volume_type VARCHAR(50) NULL COMMENT '成交量类型(A/B/C/D/E/F/G/H/X/Y/Z，多个类型用逗号连接)' AFTER pressure_price;

-- 添加索引以便查询
ALTER TABLE daily_chance 
ADD KEY idx_volume_type (volume_type) COMMENT '成交量类型索引';

