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
            result_mode = data.get("resultMode") or data.get("result_mode") or "summary"
            per_stock_timeout_sec = (
                data.get("perStockTimeoutSec")
                or data.get("per_stock_timeout_sec")
                or (backtest_config.get("perStockTimeoutSec") if isinstance(backtest_config, dict) else None)
                or (backtest_config.get("per_stock_timeout_sec") if isinstance(backtest_config, dict) else None)
            )

            if not isinstance(stocks, list) or not stocks:
                return jsonify(ResponseBuilder.error("stocks不能为空", code=400)), 400

            job_id = BatchBacktestService.start_job(
                stocks=stocks,
                stock_nature=stock_nature,
                backtest_config=backtest_config,
                period=period,
                concurrency=concurrency,
                result_mode=result_mode,
                per_stock_timeout_sec=per_stock_timeout_sec,
            )
            return jsonify(ResponseBuilder.success({"jobId": job_id}, "batch_backtest_started")), 200
        except Exception as e:
            logger.error(f"启动批量回测失败: {e}", exc_info=True)
            return jsonify(ResponseBuilder.error(f"启动批量回测失败: {e}")), 500

    def status(self, job_id: str):
        try:
            include_results = str(request.args.get("includeResults") or request.args.get("include_results") or "0").strip()
            include_results_bool = include_results in ("1", "true", "True", "yes", "Y")
            last_n = request.args.get("lastN") or request.args.get("last_n")
            st = BatchBacktestService.get_status(job_id, include_results=include_results_bool, last_n=last_n)
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

    def market_index(self):
        """获取大盘指数数据用于图表对比"""
        try:
            # 支持前端传入起始日期：用于把基准(0%)对齐到“本次回测选择的开始日期”
            start_date = (
                (request.args.get("start_date") or request.args.get("startDate") or "").strip()
                or "2024-01-01"
            )
            # 简单兜底校验，避免异常格式导致SQL报错
            if len(start_date) != 10 or start_date[4] != "-" or start_date[7] != "-":
                start_date = "2024-01-01"
            data = BatchBacktestService.get_market_index(index_name='上证指数', start_date=start_date)
            return jsonify(ResponseBuilder.success(data, "ok")), 200
        except Exception as e:
            logger.error(f"获取大盘指数失败: {e}", exc_info=True)
            return jsonify(ResponseBuilder.error(f"获取大盘指数失败: {e}")), 500
