"""独立量化高分服务（端口 8888），复用原高分推荐的缓存逻辑。"""
import os
import sys
from flask import Flask, send_from_directory, request, jsonify
from flask_cors import CORS

# 将 backend 加入路径，复用已有的服务与配置
BASE_DIR = os.path.dirname(os.path.abspath(__file__))
BACKEND_DIR = os.path.normpath(os.path.join(BASE_DIR, "..", "backend"))
if BACKEND_DIR not in sys.path:
    sys.path.insert(0, BACKEND_DIR)

from application.services.high_score_cache_service import HighScoreCacheService
from interfaces.dto.response import ResponseBuilder
from infrastructure.logging.logger import get_logger

logger = get_logger(__name__)
high_score_service = HighScoreCacheService()

app = Flask(__name__, static_folder=BASE_DIR, static_url_path="")
CORS(app, resources={r"/api/*": {"origins": "*", "methods": ["GET", "POST", "OPTIONS"], "allow_headers": "*"}})


def _json_body() -> dict:
    """安全地获取 JSON 请求体。"""
    return request.get_json(silent=True) or {}


@app.route("/")
def index():
    """返回量化高分页面。"""
    return send_from_directory(app.static_folder, "high_score_quant.html")


@app.route("/api/streaming/high_score", methods=["POST"])
def streaming_high_score():
    """从 Redis 获取高分排行榜（不分组）。"""
    try:
        data = _json_body()
        limit = int(data.get("limit", 100))
        date_str = data.get("date") or data.get("date_str")
        result = high_score_service.get_top_from_cache(limit=limit, date_str=date_str)
        return jsonify(ResponseBuilder.success(result, "ok"))
    except Exception as exc:  # noqa: BLE001
        logger.error("获取高分排行榜失败: %s", exc, exc_info=True)
        return jsonify(ResponseBuilder.error("获取高分排行榜失败"))


@app.route("/api/streaming/high_score/grouped", methods=["POST"])
def streaming_high_score_grouped():
    """从 Redis 获取高分排行榜（按股性分组）。"""
    try:
        data = _json_body()
        limit_per_group = data.get("limit_per_group") or data.get("limitPerGroup") or data.get("limit") or 100
        scan_limit = data.get("scan_limit") or data.get("scanLimit") or 2000
        date_str = data.get("date") or data.get("date_str")
        result = high_score_service.get_top_grouped_from_cache(
            limit_per_group=int(limit_per_group),
            date_str=date_str,
            scan_limit=int(scan_limit),
        )
        return jsonify(ResponseBuilder.success(result, "ok"))
    except Exception as exc:  # noqa: BLE001
        logger.error("获取分组高分排行榜失败: %s", exc, exc_info=True)
        return jsonify(ResponseBuilder.error("获取分组高分排行榜失败"))


@app.route("/api/streaming/high_score/refresh", methods=["POST"])
def refresh_streaming_high_score():
    """手动触发刷新高分缓存。"""
    try:
        data = _json_body()
        date_str = data.get("date") or data.get("date_str")
        result = high_score_service.refresh_scores(date_str=date_str)
        if result.get("success"):
            return jsonify(ResponseBuilder.success(result, "刷新完成"))
        return jsonify(ResponseBuilder.error(result.get("message", "刷新失败")))
    except Exception as exc:  # noqa: BLE001
        logger.error("刷新高分排行榜失败: %s", exc, exc_info=True)
        return jsonify(ResponseBuilder.error("刷新失败"))


@app.route("/api/health", methods=["GET"])
def health_check():
    """健康检查。"""
    return jsonify({"status": "ok", "service": "quant_high_score"})


if __name__ == "__main__":
    logger.info("量化高分服务启动: http://localhost:8888")
    app.run(host="0.0.0.0", port=8888, debug=False, threaded=True)

