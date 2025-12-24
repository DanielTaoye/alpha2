"""批量回测控制器：启动任务 + 查询任务状态"""

from flask import request, jsonify

from application.services.batch_backtest_service import BatchBacktestService
from interfaces.dto.response import ResponseBuilder
from infrastructure.logging.logger import get_logger

logger = get_logger(__name__)


class BatchBacktestController:
    def start(self):
        try:
            data = request.get_json(force=True) or {}
            stocks = data.get("stocks") or []
            stock_nature = data.get("stockNature") or data.get("stock_nature") or "波段"
            backtest_config = data.get("backtestConfig") or data.get("config") or {}
            period = data.get("period") or "day"
            concurrency = data.get("concurrency") or 2

            if not isinstance(stocks, list) or not stocks:
                return jsonify(ResponseBuilder.error("stocks不能为空", code=400)), 400

            job_id = BatchBacktestService.start_job(
                stocks=stocks,
                stock_nature=stock_nature,
                backtest_config=backtest_config,
                period=period,
                concurrency=concurrency,
            )
            return jsonify(ResponseBuilder.success({"jobId": job_id}, "batch_backtest_started")), 200
        except Exception as e:
            logger.error(f"启动批量回测失败: {e}", exc_info=True)
            return jsonify(ResponseBuilder.error(f"启动批量回测失败: {e}")), 500

    def status(self, job_id: str):
        try:
            st = BatchBacktestService.get_status(job_id)
            if not st:
                return jsonify(ResponseBuilder.error("job不存在", code=404)), 404
            return jsonify(ResponseBuilder.success(st, "ok")), 200
        except Exception as e:
            logger.error(f"查询批量回测状态失败: {e}", exc_info=True)
            return jsonify(ResponseBuilder.error(f"查询批量回测状态失败: {e}")), 500

    def cancel(self, job_id: str):
        try:
            ok = BatchBacktestService.cancel_job(job_id)
            if not ok:
                return jsonify(ResponseBuilder.error("job不存在", code=404)), 404
            return jsonify(ResponseBuilder.success({"jobId": job_id, "cancelled": True}, "cancelled")), 200
        except Exception as e:
            logger.error(f"取消批量回测失败: {e}", exc_info=True)
            return jsonify(ResponseBuilder.error(f"取消批量回测失败: {e}")), 500


