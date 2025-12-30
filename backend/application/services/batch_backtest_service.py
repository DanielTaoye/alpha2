"""批量回测服务：后端统一调度 CR分析 + 回测，并提供任务进度查询

设计目标：
- 前端只发一次“股票列表+参数”，避免前端高并发打爆后端/数据库
- 后端在后台线程执行，前端轮询任务进度
- 结果结构尽量复用现有前端展示（success/skipped/data/summary/message）
"""

from __future__ import annotations

from dataclasses import dataclass, asdict
from datetime import datetime, timedelta
from threading import Lock, Thread
from typing import Any, Dict, List, Optional
from uuid import uuid4
import time
from concurrent.futures import ThreadPoolExecutor, wait, FIRST_COMPLETED

from infrastructure.logging.logger import get_logger
from application.services.kline_service import KLineApplicationService
from application.services.cr_point_service import CRPointService
from application.services.backtest_service import BacktestService
from infrastructure.persistence.kline_repository_impl import KLineRepositoryImpl

logger = get_logger(__name__)


@dataclass
class BatchJobStatus:
    job_id: str
    created_at: str
    updated_at: str
    done: bool
    cancelled: bool
    total: int
    finished: int
    success: int
    failed: int
    skipped: int
    message: str
    results: List[Dict[str, Any]]


class BatchBacktestService:
    """管理批量回测任务（内存态，重启服务后任务会丢失）"""

    _lock = Lock()
    _jobs: Dict[str, BatchJobStatus] = {}
    _cancel_flags: Dict[str, bool] = {}
    _per_stock_timeout_sec: int = 120

    @classmethod
    def start_job(
        cls,
        stocks: List[Dict[str, Any]],
        stock_nature: str,
        backtest_config: Dict[str, Any],
        period: str = "day",
        concurrency: int = 50,
        result_mode: str = "summary",
    ) -> str:
        job_id = uuid4().hex
        now = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
        status = BatchJobStatus(
            job_id=job_id,
            created_at=now,
            updated_at=now,
            done=False,
            cancelled=False,
            total=len(stocks),
            finished=0,
            success=0,
            failed=0,
            skipped=0,
            message="running",
            # 用 None 做占位：前端轮询时会过滤掉 None；避免 {} 被当成“有结果”导致渲染异常
            results=[None for _ in range(len(stocks))],
        )
        with cls._lock:
            cls._jobs[job_id] = status
            cls._cancel_flags[job_id] = False

        t = Thread(
            target=cls._run_job,
            args=(job_id, stocks, stock_nature, backtest_config, period, concurrency, result_mode),
            daemon=True,
        )
        t.start()
        return job_id

    @classmethod
    def cancel_job(cls, job_id: str) -> bool:
        with cls._lock:
            if job_id not in cls._jobs:
                return False
            cls._cancel_flags[job_id] = True
            return True

    @classmethod
    def get_status(
        cls,
        job_id: str,
        include_results: bool = False,
        last_n: Optional[int] = None,
    ) -> Optional[Dict[str, Any]]:
        with cls._lock:
            st = cls._jobs.get(job_id)
            if not st:
                return None
            payload = asdict(st)

            # 默认不返回 results：轮询时返回体会越来越大，导致浏览器/反代/后端超时
            if not include_results:
                payload["results"] = []
                return payload

            # include_results=true：只返回已完成的结果（过滤 None 占位）
            results = payload.get("results") or []
            completed = [r for r in results if r]
            if last_n is not None:
                try:
                    n = int(last_n)
                    if n > 0:
                        completed = completed[-n:]
                except Exception:
                    pass
            payload["results"] = completed
            return payload

    @classmethod
    def _set_status(cls, job_id: str, **kwargs):
        with cls._lock:
            st = cls._jobs.get(job_id)
            if not st:
                return
            for k, v in kwargs.items():
                setattr(st, k, v)
            st.updated_at = datetime.now().strftime("%Y-%m-%d %H:%M:%S")

    @classmethod
    def _is_cancelled(cls, job_id: str) -> bool:
        with cls._lock:
            return bool(cls._cancel_flags.get(job_id, False))

    @classmethod
    def _run_job(
        cls,
        job_id: str,
        stocks: List[Dict[str, Any]],
        stock_nature: str,
        backtest_config: Dict[str, Any],
        period: str,
        concurrency: int,
        result_mode: str,
    ):
        try:
            conc = max(1, min(int(concurrency or 1), 50))
            logger.info(f"[batch_backtest] job={job_id} start, total={len(stocks)}, concurrency={conc}")

            def worker(idx_stock):
                idx, stock = idx_stock
                if cls._is_cancelled(job_id):
                    return idx, {
                        "stock": stock,
                        "success": True,
                        "skipped": True,
                        "message": "已取消(未执行)",
                    }
                try:
                    return idx, cls._run_single(stock, stock_nature, backtest_config, period, result_mode=result_mode)
                except Exception as e:
                    logger.error(f"[batch_backtest] job={job_id} single crashed: {e}", exc_info=True)
                    return idx, {"stock": stock, "success": False, "message": f"异常: {e}"}

            finished = 0
            succ = 0
            fail = 0
            skip = 0
            results = [None for _ in range(len(stocks))]

            ex = ThreadPoolExecutor(max_workers=conc)
            futures = []
            future_meta: Dict[Any, tuple[int, Any, float]] = {}
            try:
                for i, s in enumerate(stocks):
                    fut = ex.submit(worker, (i, s))
                    futures.append(fut)
                    future_meta[fut] = (i, s, time.monotonic())

                pending = set(futures)
                # 用 wait + 超时扫描：单股票超过 30s 仍未返回，则记为超时并“自动下一个”
                while pending:
                    done_set, _ = wait(pending, timeout=0.4, return_when=FIRST_COMPLETED)
                    now = time.monotonic()

                    # 处理完成的
                    for fut in list(done_set):
                        pending.discard(fut)
                        try:
                            idx, res = fut.result()
                        except Exception as e:
                            idx, stock, _st = future_meta.get(fut, (-1, None, 0.0))
                            res = {"stock": stock, "success": False, "message": f"异常: {e}"}
                        if idx is None or idx < 0:
                            continue
                        # 如果该 idx 已被超时/取消提前写入，就忽略真实结果（避免反复计数）
                        if results[idx] is not None:
                            continue
                        results[idx] = res
                        finished += 1
                        if res.get("success") and res.get("skipped"):
                            skip += 1
                        elif res.get("success"):
                            succ += 1
                        else:
                            fail += 1
                        cls._set_status(
                            job_id,
                            finished=finished,
                            success=succ,
                            failed=fail,
                            skipped=skip,
                            results=results,
                            message="running",
                        )

                    # 扫描超时（不杀线程，只是不再等待它；并把它计入 finished，让进度能继续走）
                    for fut in list(pending):
                        idx, stock, start_ts = future_meta.get(fut, (-1, None, now))
                        if idx < 0:
                            continue
                        if results[idx] is not None:
                            pending.discard(fut)
                            continue
                        if now - start_ts >= float(cls._per_stock_timeout_sec):
                            results[idx] = {
                                "stock": stock,
                                "success": False,
                                "timeout": True,
                                "message": f"超时({cls._per_stock_timeout_sec}s)已跳过",
                            }
                            finished += 1
                            fail += 1
                            pending.discard(fut)
                            cls._set_status(
                                job_id,
                                finished=finished,
                                success=succ,
                                failed=fail,
                                skipped=skip,
                                results=results,
                                message="running",
                            )

                    # 打断：把仍未落盘的标记为“已取消(未执行)”并结束
                    if cls._is_cancelled(job_id):
                        for fut in list(pending):
                            idx, stock, _st = future_meta.get(fut, (-1, None, now))
                            if idx < 0:
                                continue
                            if results[idx] is not None:
                                continue
                            results[idx] = {
                                "stock": stock,
                                "success": True,
                                "skipped": True,
                                "message": "已取消(未执行)",
                            }
                            finished += 1
                            skip += 1
                        pending.clear()
                        cls._set_status(
                            job_id,
                            finished=finished,
                            success=succ,
                            failed=fail,
                            skipped=skip,
                            results=results,
                            message="running",
                        )
                        break
            finally:
                cancelled = cls._is_cancelled(job_id)
                # 取消时不等待线程池把所有计算跑完；超时的单股任务也不阻塞整个 job 结束
                ex.shutdown(wait=not cancelled, cancel_futures=cancelled)

            cancelled = cls._is_cancelled(job_id)
            cls._set_status(
                job_id,
                done=True,
                cancelled=cancelled,
                message="cancelled" if cancelled else "done",
                results=results,
            )
            logger.info(f"[batch_backtest] job={job_id} done, finished={finished}, success={succ}, failed={fail}, skipped={skip}, cancelled={cancelled}")
        except Exception as e:
            logger.error(f"[batch_backtest] job={job_id} crashed: {e}", exc_info=True)
            cls._set_status(job_id, done=True, message=f"error: {e}")

    @staticmethod
    def _parse_date_range(backtest_config: Dict[str, Any]) -> tuple[Optional[str], Optional[str]]:
        start_date = (backtest_config.get("startDate") or "").strip() or None
        end_date = (backtest_config.get("endDate") or "").strip() or None
        return start_date, end_date

    @classmethod
    def _run_single(
        cls,
        stock: Any,
        stock_nature: str,
        backtest_config: Dict[str, Any],
        period: str,
        result_mode: str = "summary",
    ) -> Dict[str, Any]:
        # 兼容多种输入：
        # - {"code": "...", "table_name": "..."}（前端完整传参）
        # - {"code": "..."}（只给code，后端推导表名）
        # - "SZ300188"（stocks 直接是字符串列表）
        stock_code = None
        stock_name = ""
        table_name = None
        if isinstance(stock, str):
            stock_code = stock.strip().upper()
        elif isinstance(stock, dict):
            stock_code = (stock.get("code") or stock.get("stockCode") or stock.get("stock_code") or "").strip().upper() or None
            stock_name = stock.get("name") or stock.get("stockName") or ""
            table_name = stock.get("table_name") or stock.get("tableName")

        if not stock_code:
            return {"stock": stock, "success": False, "message": "缺少股票代码"}

        # 未传表名时，按约定自动推导：basic_data_{code.lower()}
        if not table_name:
            table_name = f"basic_data_{stock_code.lower()}"

        # 为了线程安全：每个任务都创建独立实例（CRPointService 内部有缓存）
        kline_service = KLineApplicationService(KLineRepositoryImpl())
        cr_service = CRPointService()
        backtest_service = BacktestService()

        start_date_str, end_date_str = cls._parse_date_range(backtest_config)

        # 复用 controller 的“区间 + 缓冲”逻辑：只取区间数据，避免全量重算
        start_dt = None
        end_dt = None
        limit = 2000
        try:
            if end_date_str:
                end_dt = datetime.strptime(end_date_str, "%Y-%m-%d") + timedelta(days=1) - timedelta(seconds=1)
            if start_date_str:
                raw_start = datetime.strptime(start_date_str, "%Y-%m-%d")
                start_dt = raw_start - timedelta(days=180)
                if end_dt:
                    span_days = max(1, int((end_dt - start_dt).days) + 1)
                    limit = min(8000, max(800, span_days))
                else:
                    limit = 4000
        except Exception:
            start_dt = None
            end_dt = None
            limit = 2000

        # 1) 取K线 + 指标
        kl = kline_service.get_kline_data(
            table_name=table_name,
            period_type=period,
            exclude_today=True,
            start_date=start_dt,
            end_date=end_dt,
            limit=limit,
        )
        kline_list = kl.get("kline_data") or []
        if not kline_list:
            return {"stock": stock, "success": False, "message": "K线数据为空"}

        macd_data = kl.get("macd") or {}
        ma_data = kl.get("ma") or {}

        # 2) 转KLineData对象
        from domain.models.kline import KLineData

        kline_objects: List[KLineData] = []
        for k in kline_list:
            try:
                kline_objects.append(
                    KLineData(
                        time=datetime.strptime(k["time"], "%Y-%m-%d %H:%M:%S"),
                        open=k["open"],
                        high=k["high"],
                        low=k["low"],
                        close=k["close"],
                        volume=k["volume"],
                        liangbi=k.get("liangbi", 0),
                        weibi=k.get("weibi", 0),
                    )
                )
            except Exception:
                continue

        # 3) CR分析（返回 dict，包含 c_points/r_points/strategy2_c_points）
        cr = cr_service.analyze_cr_points(
            stock_code=stock_code,
            stock_name=stock_name,
            kline_data=kline_objects,
            ma_data=ma_data,
            macd_data=macd_data,
            volume_types=None,
            bullish_patterns=None,
            stock_nature=stock_nature,
        )

        c_points = cr.get("c_points") or []
        c_points_s2 = cr.get("strategy2_c_points") or []
        merged_c = list(c_points) + list(c_points_s2)
        r_points = cr.get("r_points") or []

        if not merged_c:
            return {"stock": stock, "success": True, "skipped": True, "message": "没有C点(已跳过)"}

        # 4) 回测
        bt = backtest_service.calculate_backtest(
            stock_code=stock_code,
            table_name=table_name,
            c_points=merged_c,
            r_points=r_points,
            backtest_config=backtest_config,
        )
        if not bt.get("success"):
            return {"stock": stock, "success": False, "message": bt.get("message") or "回测失败"}

        trades = bt.get("trades") or []
        if not trades:
            return {"stock": stock, "success": True, "skipped": True, "message": "无CR配对(已跳过)"}

        mode = (result_mode or "summary").strip().lower()
        if mode == "full":
            # 兼容旧逻辑：返回完整 trades + summary（数据量很大，建议仅用于少量股票）
            return {"stock": stock, "success": True, "skipped": False, "data": bt}

        # 默认：只返回 summary，避免 batch 结果/轮询 payload 过大导致超时
        return {
            "stock": stock,
            "success": True,
            "skipped": False,
            "data": {
                "summary": bt.get("summary") or {},
            },
        }


