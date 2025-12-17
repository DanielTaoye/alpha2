"""高分排行榜控制器（Redis缓存版）"""
from flask import request, jsonify
from interfaces.dto.response import ResponseBuilder
from application.services.high_score_cache_service import HighScoreCacheService
from infrastructure.logging.logger import get_logger

logger = get_logger(__name__)


class HighScoreController:
    def __init__(self):
        self.cache_service = HighScoreCacheService()

    def get_high_score(self):
        """从Redis读取高分排行榜"""
        try:
            data = request.get_json(silent=True) or {}
            limit = data.get("limit", 100)
            date_str = data.get("date") or data.get("date_str")
            result = self.cache_service.get_top_from_cache(limit=limit, date_str=date_str)
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

