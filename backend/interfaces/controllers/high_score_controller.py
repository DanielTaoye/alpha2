"""高分排行榜控制器（Redis缓存版）"""
from flask import request, jsonify
from interfaces.dto.response import ResponseBuilder
from application.services.high_score_cache_service import HighScoreCacheService
from application.services.strategy3_probability_db_service import Strategy3ProbabilityDbService
from infrastructure.logging.logger import get_logger

logger = get_logger(__name__)


class HighScoreController:
    def __init__(self):
        self.cache_service = HighScoreCacheService()
        self.strategy3_db = Strategy3ProbabilityDbService()

    def get_high_score(self):
        """从Redis读取高分排行榜"""
        try:
            data = request.get_json(silent=True) or {}
            limit = data.get("limit", 100)
            date_str = data.get("date") or data.get("date_str")
            result = self.cache_service.get_top_from_cache(limit=limit, date_str=date_str)
            # 策略3：从本地DB补齐（不依赖Redis写入）
            stocks = result.get("stocks") or []
            code_list = [s.get("stock_code") for s in stocks if isinstance(s, dict)]
            s3_map = self.strategy3_db.get_probs_by_codes(date_str or "", code_list)
            for s in stocks:
                if not isinstance(s, dict):
                    continue
                extra = s3_map.get(str(s.get("stock_code")))
                if extra:
                    s.update(extra)
            return jsonify(ResponseBuilder.success(result, "ok"))
        except Exception as e:
            logger.error(f"获取高分排行榜失败: {e}", exc_info=True)
            return jsonify(ResponseBuilder.error("获取高分排行榜失败"))

    def refresh_high_score(self):
        """手动触发刷新（可用于调试或手动重算）"""
        try:
            data = request.get_json(silent=True) or {}
            date_str = data.get("date") or data.get("date_str")
            result = self.cache_service.refresh_scores(date_str=date_str)
            if result.get("success"):
                return jsonify(ResponseBuilder.success(result, "刷新完成"))
            return jsonify(ResponseBuilder.error(result.get("message", "刷新失败")))
        except Exception as e:
            logger.error(f"刷新高分排行榜失败: {e}", exc_info=True)
            return jsonify(ResponseBuilder.error("刷新失败"))

    def get_high_score_grouped(self):
        """从Redis读取高分排行榜（按股性分组分别取Top N）"""
        try:
            data = request.get_json(silent=True) or {}
            limit_per_group = data.get("limit_per_group") or data.get("limitPerGroup") or data.get("limit") or 100
            scan_limit = data.get("scan_limit") or data.get("scanLimit") or 2000
            date_str = data.get("date") or data.get("date_str")
            result = self.cache_service.get_top_grouped_from_cache(
                limit_per_group=int(limit_per_group),
                date_str=date_str,
                scan_limit=int(scan_limit),
            )
            # 策略3：从本地DB补齐
            groups = (result or {}).get("groups") or {}
            all_items = []
            for _, arr in groups.items():
                if isinstance(arr, list):
                    all_items.extend([x for x in arr if isinstance(x, dict)])
            code_list = [s.get("stock_code") for s in all_items]
            s3_map = self.strategy3_db.get_probs_by_codes(date_str or "", code_list)
            for s in all_items:
                extra = s3_map.get(str(s.get("stock_code")))
                if extra:
                    s.update(extra)
            return jsonify(ResponseBuilder.success(result, "ok"))
        except Exception as e:
            logger.error(f"获取分组高分排行榜失败: {e}", exc_info=True)
            return jsonify(ResponseBuilder.error("获取分组高分排行榜失败"))

