"""
策略3概率 - DB 读写服务（存到本地 bendi）。

表结构（默认）：
  bendi.strategy3_probabilities
    date (DATE)
    stock_code (VARCHAR)
    prob (DOUBLE)
    raw (DOUBLE)
    used_factors (INT)
    created_at/updated_at

用途：
- 先由 quant 脚本批量计算并落库
- 后端返回高分榜时按 date + stock_codes 批量补齐字段（不写 Redis）
"""

from __future__ import annotations

from typing import Dict, Iterable, Optional

from infrastructure.logging.logger import get_logger
from infrastructure.persistence.database import DatabaseConnection

logger = get_logger(__name__)


class Strategy3ProbabilityDbService:
    TABLE = "strategy3_probabilities"

    @staticmethod
    def normalize_date(date_str: str) -> Optional[str]:
        if not date_str:
            return None
        digits = "".join(ch for ch in str(date_str) if ch.isdigit())
        if len(digits) >= 8:
            return f"{digits[0:4]}-{digits[4:6]}-{digits[6:8]}"
        return None

    def get_probs_by_codes(self, date_str: str, stock_codes: Iterable[str]) -> Dict[str, Dict]:
        d = self.normalize_date(date_str)
        codes = [str(c) for c in stock_codes if c]
        if not codes:
            return {}

        placeholders = ",".join(["%s"] * len(codes))

        def _query(sql: str, params: list):
            with DatabaseConnection.get_connection_context() as conn:
                cur = conn.cursor()
                cur.execute(sql, params)
                return cur.fetchall()

        rows = []
        # 先按 date 查
        if d:
            try:
                sql = (
                    f"SELECT stock_code, prob, raw, used_factors, `date` "
                    f"FROM {self.TABLE} "
                    f"WHERE `date`=%s AND stock_code IN ({placeholders})"
                )
                rows = _query(sql, [d] + codes)
            except Exception as e:
                logger.error(f"读取策略3概率失败(date): {e}", exc_info=True)
                rows = []

        # 如果没查到，按 source_date(YYYYMMDD) 回退
        if not rows:
            digits = "".join(ch for ch in str(date_str) if ch.isdigit())[:8]
            if len(digits) == 8:
                try:
                    sql = (
                        f"SELECT stock_code, prob, raw, used_factors, `date` "
                        f"FROM {self.TABLE} "
                        f"WHERE `source_date`=%s AND stock_code IN ({placeholders})"
                    )
                    rows = _query(sql, [digits] + codes)
                except Exception as e:
                    # 可能表里还没有 source_date 列，忽略
                    logger.error(f"读取策略3概率失败(source_date): {e}", exc_info=True)
                    rows = []

        out: Dict[str, Dict] = {}
        for stock_code, prob, raw, used_factors, row_date in rows:
            d2 = None
            try:
                d2 = row_date.strftime("%Y-%m-%d") if row_date else d
            except Exception:
                d2 = d
            out[str(stock_code)] = {
                "strategy3_prob": float(prob) if prob is not None else None,
                "strategy3_raw": float(raw) if raw is not None else None,
                "strategy3_used_factors": int(used_factors) if used_factors is not None else 0,
                "strategy3_date": d2,
            }
        return out


