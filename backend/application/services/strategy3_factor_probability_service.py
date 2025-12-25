"""
策略3：聚宽因子“概率”服务

做法：
- 读取 quant/strategy3_factor_weights.json（或环境变量 STRATEGY3_WEIGHTS_PATH 指定）
- 从 bendi.jq_factor_library 取指定 date 的全样本（通常是当天高分Top15已入库的那批）
- 对每个因子做横截面 z-score，然后按权重加权求和得到 raw_score
- 用 sigmoid 映射到 [0,1] 概率

注意：
- 若权重文件/因子表数据缺失，返回 None，不影响原策略1/2
"""

import json
import math
import os
from typing import Dict, Optional, Tuple

from infrastructure.logging.logger import get_logger
from infrastructure.persistence.database import DatabaseConnection

logger = get_logger(__name__)


class Strategy3FactorProbabilityService:
    def __init__(self):
        self._weights_payload = None

    @staticmethod
    def _default_weights_path() -> str:
        # 项目根/quant/strategy3_factor_weights.json
        backend_dir = os.path.dirname(os.path.abspath(__file__))  # backend/application/services
        project_root = os.path.normpath(os.path.join(backend_dir, "..", "..", ".."))
        return os.path.join(project_root, "quant", "strategy3_factor_weights.json")

    def _load_weights(self) -> Optional[Dict]:
        if self._weights_payload is not None:
            return self._weights_payload

        path = os.getenv("STRATEGY3_WEIGHTS_PATH", "").strip() or self._default_weights_path()
        if not os.path.exists(path):
            logger.info(f"策略3权重文件不存在，跳过: {path}")
            self._weights_payload = None
            return None
        try:
            with open(path, "r", encoding="utf-8") as f:
                payload = json.load(f)
            if not isinstance(payload, dict) or "weights" not in payload:
                logger.warning("策略3权重文件格式不正确，跳过")
                self._weights_payload = None
                return None
            self._weights_payload = payload
            return payload
        except Exception as e:
            logger.error(f"读取策略3权重失败: {e}", exc_info=True)
            self._weights_payload = None
            return None

    @staticmethod
    def _normalize_date(date_str: str) -> Optional[str]:
        if not date_str:
            return None
        digits = "".join(ch for ch in str(date_str) if ch.isdigit())
        if len(digits) >= 8:
            return f"{digits[0:4]}-{digits[4:6]}-{digits[6:8]}"
        return None

    @staticmethod
    def _sigmoid(x: float) -> float:
        # 防溢出保护
        if x > 20:
            return 1.0
        if x < -20:
            return 0.0
        return 1.0 / (1.0 + math.exp(-x))

    def compute_prob_for_stock(self, stock_code: str, date_str: str) -> Optional[Dict]:
        """
        返回：
        {
          "prob": 0.0~1.0,
          "raw": float,
          "date": "YYYY-MM-DD",
          "source_table": "jq_factor_library"
        }
        """
        payload = self._load_weights()
        if not payload:
            return None
        weights: Dict[str, float] = payload.get("weights") or {}
        if not weights:
            return None

        d = self._normalize_date(date_str)
        if not d:
            return None

        # 读取当日全样本（用于横截面标准化）
        # 这里默认用 bendi 库里的 jq_factor_library；如需可通过环境变量覆盖
        table = os.getenv("DB_TABLE_FACTORS", "jq_factor_library")
        try:
            with DatabaseConnection.get_connection_context() as conn:
                cur = conn.cursor()
                cur.execute(f"SELECT * FROM `{table}` WHERE `date`=%s", (d,))
                cols = [desc[0] for desc in cur.description]
                rows = cur.fetchall()
        except Exception as e:
            logger.error(f"策略3读取因子表失败: {e}", exc_info=True)
            return None

        if not rows or not cols:
            return None

        # 找到目标行
        try:
            sc_idx = cols.index("stock_code")
        except ValueError:
            return None

        target_row = None
        for r in rows:
            if str(r[sc_idx]) == str(stock_code):
                target_row = r
                break
        if target_row is None:
            return None

        # 为每个因子计算横截面均值/方差，并取目标的 z-score
        raw_score = 0.0
        used = 0
        for fac, w in weights.items():
            if fac not in cols:
                continue
            j = cols.index(fac)
            vals = []
            for r in rows:
                v = r[j]
                if v is None:
                    continue
                try:
                    vals.append(float(v))
                except Exception:
                    continue
            if len(vals) < 3:
                continue
            mu = sum(vals) / len(vals)
            var = sum((x - mu) ** 2 for x in vals) / max(len(vals) - 1, 1)
            std = math.sqrt(var) if var > 0 else 0.0
            if std <= 0:
                continue
            try:
                x0 = float(target_row[j])
            except Exception:
                continue
            z = (x0 - mu) / std
            raw_score += float(w) * z
            used += 1

        if used == 0:
            return None

        prob = self._sigmoid(raw_score)
        return {"prob": prob, "raw": raw_score, "date": d, "source_table": table, "used_factors": used}


