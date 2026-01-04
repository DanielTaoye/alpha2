-- 创建大盘指数日线数据表
CREATE TABLE IF NOT EXISTS market_index_daily (
    id INT AUTO_INCREMENT PRIMARY KEY COMMENT '主键ID',
    index_name VARCHAR(50) NOT NULL COMMENT '指数名称',
    index_code VARCHAR(20) DEFAULT NULL COMMENT '指数代码 (可选)',
    trade_date DATE NOT NULL COMMENT '交易日期',
    close_price DECIMAL(10, 2) NOT NULL DEFAULT 0.00 COMMENT '收盘价',
    updated_at DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP COMMENT '更新时间',
    UNIQUE KEY uk_index_date (index_name, trade_date) COMMENT '指数名称和日期的唯一索引',
    KEY idx_trade_date (trade_date) COMMENT '日期索引'
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COMMENT='大盘指数日线表';
