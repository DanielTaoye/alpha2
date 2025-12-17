import argparse
import logging
import os
from datetime import datetime
from typing import Dict, List, Set

import pymysql

from dzh_refresh.dzh_client import DzhRestClient, build_default_client
from dzh_refresh.db import get_connection

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s %(levelname)s %(message)s",
)
logger = logging.getLogger(__name__)

def _parse_date(s: str) -> datetime:
    return datetime.strptime(s, "%Y-%m-%d")


def _env_or_default() -> Dict[str, any]:
    obj = os.getenv("DZH_OBJ", "SH601128")
    start = os.getenv("DZH_START", "2024-01-01")
    end = os.getenv("DZH_END", "2024-02-01")
    return {
        "obj": obj,
        "table": os.getenv("DZH_TABLE", f"basic_data_{obj.lower()}"),
        "period": os.getenv("DZH_PERIOD", "1day"),
        "start": _parse_date(start),
        "end": _parse_date(end),
        "count": int(os.getenv("DZH_COUNT", "600")),
    }


def _ensure_table_exists(conn: pymysql.connections.Connection, table_name: str) -> None:
    """Create K线表（如果不存在），对齐历史表结构，去掉 zuo_shou_jia / cheng_jiao_bi_shu。"""
    ddl = f"""
    CREATE TABLE IF NOT EXISTS `{table_name}` (
      `id` bigint NOT NULL AUTO_INCREMENT COMMENT '主键',
      `peroid_type` varchar(20) DEFAULT NULL COMMENT '周期类型',
      `shi_jian` datetime NOT NULL COMMENT '时间',
      `kai_pan_jia` decimal(30,2) DEFAULT NULL COMMENT '开盘价',
      `zui_gao_jia` decimal(30,2) DEFAULT NULL COMMENT '最高价',
      `zui_di_jia` decimal(30,2) DEFAULT NULL COMMENT '最低价',
      `shou_pan_jia` decimal(30,2) DEFAULT NULL COMMENT '收盘价',
      `cheng_jiao_liang` bigint DEFAULT NULL COMMENT '成交量',
      `cheng_jiao_e` decimal(30,2) DEFAULT NULL COMMENT '成交额',
      `shi_zhi` decimal(30,2) DEFAULT NULL COMMENT '市值',
      `liu_tong_shi_zhi` decimal(30,2) DEFAULT NULL COMMENT '流通市值',
      `baidu_score` decimal(5,2) DEFAULT NULL COMMENT '百度股市通评分',
      `tonghuashun_score` decimal(5,2) DEFAULT NULL COMMENT '同花顺评分',
      `dongfang_score` decimal(5,2) DEFAULT NULL COMMENT '东方财富网评分',
      `shi_ying_lv_dong` decimal(30,2) DEFAULT NULL COMMENT '市盈率（动）',
      `shi_ying_lv_jing` decimal(30,2) DEFAULT NULL COMMENT '市盈率（静）',
      `shi_ying_lv_ttm` decimal(30,2) DEFAULT NULL COMMENT '市盈率TTM',
      `shi_jing_lv` decimal(30,2) DEFAULT NULL COMMENT '市净率',
      `mei_gu_shou_yi` decimal(30,2) DEFAULT NULL COMMENT '每股收益',
      `mei_gu_jing_zi_chan` decimal(30,2) DEFAULT NULL COMMENT '每股净资产',
      `zong_gu_ben` bigint DEFAULT NULL COMMENT '总股本',
      `liu_tong_gu_ben` bigint DEFAULT NULL COMMENT '流通股本',
      `shang_yu_bi` decimal(5,2) DEFAULT NULL COMMENT '商誉/净资产占比',
      `gu_xi` decimal(30,2) DEFAULT NULL COMMENT '股息',
      `huan_shou_lv` decimal(5,2) DEFAULT NULL COMMENT '换手率',
      `zhen_fu` decimal(5,2) DEFAULT NULL COMMENT '振幅',
      `industry_id_1` int DEFAULT NULL COMMENT '1级行业分类',
      `industry_id_2` int DEFAULT NULL COMMENT '2级行业分类',
      `industry_id_3` int DEFAULT NULL COMMENT '3级行业分类',
      `dom_festival_type` int DEFAULT NULL COMMENT '国内节日类型',
      `dom_festival_relation_type` int DEFAULT NULL COMMENT '国内节日相对类型',
      `int_festival_type` int DEFAULT NULL COMMENT '国际节日类型',
      `int_festival_relation_type` int DEFAULT NULL COMMENT '国际节日相对类型',
      `year` int DEFAULT NULL,
      `month` int DEFAULT NULL,
      `day_in_month` int DEFAULT NULL,
      `hour_in_day` int DEFAULT NULL,
      `sh_index` decimal(30,2) DEFAULT NULL COMMENT '上证指数',
      `sz_index` decimal(30,2) DEFAULT NULL COMMENT '深证指数',
      `cy_index` decimal(30,2) DEFAULT NULL COMMENT '创业板指数',
      `zx_100_index` decimal(30,2) DEFAULT NULL COMMENT '中小100',
      `hs_300_index` decimal(30,2) DEFAULT NULL COMMENT '沪深300',
      `sh_50_index` decimal(30,2) DEFAULT NULL COMMENT '上证50',
      `sh_380_index` decimal(30,2) DEFAULT NULL COMMENT '上证380',
      `hs_index` decimal(30,2) DEFAULT NULL COMMENT '恒生指数',
      `gq_index` decimal(30,2) DEFAULT NULL COMMENT '国企指数',
      `hc_index` decimal(30,2) DEFAULT NULL COMMENT '红筹指数',
      `nsdk_index` decimal(30,2) DEFAULT NULL COMMENT '纳斯达克指数',
      `dqs_index` decimal(30,2) DEFAULT NULL COMMENT '道琼斯指数',
      `bp_500_index` decimal(30,2) DEFAULT NULL COMMENT '标普500指数',
      `create_time` datetime DEFAULT NULL COMMENT '创建时间',
      `update_time` datetime DEFAULT NULL COMMENT '更新时间',
      `creator` varchar(255) DEFAULT NULL COMMENT '创建者',
      `last_operator` varchar(255) DEFAULT NULL COMMENT '更新者',
      PRIMARY KEY (`id`),
      UNIQUE KEY `shi_jian_index` (`shi_jian`,`peroid_type`) USING BTREE
    ) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4;
    """
    with conn.cursor() as cursor:
        cursor.execute(ddl)
    conn.commit()


def _ensure_columns(conn: pymysql.connections.Connection, table_name: str) -> None:
    """确保关键列存在，缺失则自动补充（当前无需新增额外列）。"""
    needed = {}
    with conn.cursor() as cursor:
        cursor.execute(f"SHOW COLUMNS FROM `{table_name}`;")
        existing: Set[str] = {row[0] for row in cursor.fetchall()}
        for col, definition in needed.items():
            if col not in existing:
                cursor.execute(
                    f"ALTER TABLE `{table_name}` ADD COLUMN {col} {definition};"
                )
                logger.info("为表 %s 补充列 %s", table_name, col)
    conn.commit()


def _save_bars(
    conn: pymysql.connections.Connection,
    table_name: str,
    period_type: str,
    bars: List[Dict],
) -> int:
    """Upsert bars into MySQL."""
    if not bars:
        return 0

    _ensure_table_exists(conn, table_name)
    _ensure_columns(conn, table_name)
    insert_sql = f"""
    INSERT INTO `{table_name}` (
        peroid_type, shi_jian, kai_pan_jia, zui_gao_jia, zui_di_jia, shou_pan_jia,
        cheng_jiao_liang, cheng_jiao_e
    ) VALUES (
        %s, %s, %s, %s, %s, %s,
        %s, %s
    ) ON DUPLICATE KEY UPDATE
        kai_pan_jia = VALUES(kai_pan_jia),
        zui_gao_jia = VALUES(zui_gao_jia),
        zui_di_jia = VALUES(zui_di_jia),
        shou_pan_jia = VALUES(shou_pan_jia),
        cheng_jiao_liang = VALUES(cheng_jiao_liang),
        cheng_jiao_e = VALUES(cheng_jiao_e);
    """

    payloads: List[tuple] = []
    for bar in bars:
        ts = bar.get("ShiJian")
        if ts is None:
            continue

        dt = datetime.fromtimestamp(int(ts))
        payloads.append(
            (
                period_type,
                dt,
                bar.get("KaiPanJia"),
                bar.get("ZuiGaoJia"),
                bar.get("ZuiDiJia"),
                bar.get("ShouPanJia"),
                int(bar.get("ChengJiaoLiang") or 0),
                bar.get("ChengJiaoE"),
            )
        )

    if not payloads:
        return 0

    with conn.cursor() as cursor:
        cursor.executemany(insert_sql, payloads)
    conn.commit()
    return len(payloads)


def fetch_and_store(
    obj: str,
    table: str,
    period: str,
    start_dt: datetime,
    end_dt: datetime,
    count: int,
) -> None:
    """Fetch K线并写入本地数据库."""
    client: DzhRestClient = build_default_client()

    logger.info(
        "开始拉取 %s %s (%s - %s)",
        obj,
        period,
        start_dt.strftime("%Y-%m-%d"),
        end_dt.strftime("%Y-%m-%d"),
    )
    bars = client.fetch_kline(
        obj=obj,
        period=period,
        begin_time=start_dt,
        end_time=end_dt,
        count=count,
        split=1,
    )
    logger.info("接口返回 %s 条记录", len(bars))

    conn = get_connection()
    try:
        try:
            saved = _save_bars(conn, table, period, bars)
            logger.info("写入表 %s 完成，记录数: %s", table, saved)
        except pymysql.err.OperationalError as exc:  # type: ignore[attr-defined]
            if exc.args and exc.args[0] == 1290:
                logger.error("数据库是只读实例，无法建表/写入，请切换到可写的本地库后再执行。", exc_info=True)
            else:
                raise
    finally:
        conn.close()


def parse_args() -> Dict[str, any]:
    defaults = _env_or_default()
    parser = argparse.ArgumentParser(description="拉取大智慧K线并写入本地DB")
    parser.add_argument("--obj", help="股票代码，如 SH601225", default=defaults["obj"])
    parser.add_argument(
        "--table",
        help="目标表名，默认 basic_data_<code小写>",
        default=None,
    )
    parser.add_argument("--period", help="周期，默认1day", default=defaults["period"])
    parser.add_argument(
        "--start", help="开始日期 yyyy-MM-dd", default=defaults["start"].strftime("%Y-%m-%d")
    )
    parser.add_argument(
        "--end", help="结束日期 yyyy-MM-dd", default=defaults["end"].strftime("%Y-%m-%d")
    )
    parser.add_argument("--count", help="拉取数量上限", type=int, default=defaults["count"])
    args = parser.parse_args()

    start_dt = _parse_date(args.start)
    end_dt = _parse_date(args.end)
    table = args.table or f"basic_data_{args.obj.lower()}"

    return {
        "obj": args.obj,
        "table": table,
        "period": args.period,
        "start": start_dt,
        "end": end_dt,
        "count": args.count,
    }


if __name__ == "__main__":
    opts = parse_args()
    fetch_and_store(
        obj=opts["obj"],
        table=opts["table"],
        period=opts["period"],
        start_dt=opts["start"],
        end_dt=opts["end"],
        count=opts["count"],
    )

