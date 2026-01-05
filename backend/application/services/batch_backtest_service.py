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
from threading import local

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
    # 单股票超时（秒）：默认拉长，避免 1000 股批量时排队/慢股导致大量误判
    _per_stock_timeout_sec: int = 480
    _tls = local()  # 线程内复用对象，避免每只股票重复初始化

    @classmethod
    def _get_thread_services(cls):
        """
        为线程池里的每个 worker 线程复用 service 实例，降低 1000 股场景下的初始化/配置加载开销。

        注意：每个线程串行处理多个股票任务，所以复用是安全的；跨线程不共享。
        """
        svc = getattr(cls._tls, "svc", None)
        if svc is None:
            cls._tls.svc = {
                "kline_service": KLineApplicationService(KLineRepositoryImpl()),
                "cr_service": CRPointService(),
                "backtest_service": BacktestService(),
            }
        return cls._tls.svc

    @staticmethod
    def _fast_parse_dt(ts: str) -> datetime:
        """
        更快的时间解析：优先 fromisoformat（兼容 'YYYY-MM-DD HH:MM:SS'），失败再回退 strptime。
        """
        try:
            return datetime.fromisoformat(ts)
        except Exception:
            return datetime.strptime(ts, "%Y-%m-%d %H:%M:%S")

    @classmethod
    def start_job(
        cls,
        stocks: List[Dict[str, Any]],
        stock_nature: str,
        backtest_config: Dict[str, Any],
        period: str = "day",
        concurrency: int = 50,
        result_mode: str = "summary",
        per_stock_timeout_sec: Optional[int] = None,
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
            args=(job_id, stocks, stock_nature, backtest_config, period, concurrency, result_mode, per_stock_timeout_sec),
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
        per_stock_timeout_sec: Optional[int] = None,
    ):
        try:
            conc = max(1, min(int(concurrency or 1), 50))
            timeout_sec = cls._per_stock_timeout_sec
            try:
                if per_stock_timeout_sec is not None:
                    timeout_sec = max(30, int(per_stock_timeout_sec))
            except Exception:
                timeout_sec = cls._per_stock_timeout_sec

            logger.info(f"[batch_backtest] job={job_id} start, total={len(stocks)}, concurrency={conc}, per_stock_timeout_sec={timeout_sec}")

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

            # 关键优化：不要一次性 submit 1000 个 future。
            # 否则大量任务会在 executor 队列里排队，start_ts 从“提交时”算起会导致误判超时。
            ex = ThreadPoolExecutor(max_workers=conc)
            future_meta: Dict[Any, tuple[int, Any, float]] = {}  # fut -> (idx, stock, start_ts)
            try:
                next_i = 0
                pending: set = set()

                # 先填满 in-flight（最多 conc 个）
                while next_i < len(stocks) and len(pending) < conc:
                    s = stocks[next_i]
                    fut = ex.submit(worker, (next_i, s))
                    pending.add(fut)
                    future_meta[fut] = (next_i, s, time.monotonic())
                    next_i += 1

                # 用 wait + 超时扫描：单股票超过 timeout_sec 仍未返回，则记为超时并“自动下一个”
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

                        # 补充提交下一个任务（保持 in-flight 规模稳定）
                        if not cls._is_cancelled(job_id) and next_i < len(stocks):
                            s = stocks[next_i]
                            nfut = ex.submit(worker, (next_i, s))
                            pending.add(nfut)
                            future_meta[nfut] = (next_i, s, time.monotonic())
                            next_i += 1

                    # 扫描超时（不杀线程，只是不再等待它；并把它计入 finished，让进度能继续走）
                    for fut in list(pending):
                        idx, stock, start_ts = future_meta.get(fut, (-1, None, now))
                        if idx < 0:
                            continue
                        if results[idx] is not None:
                            pending.discard(fut)
                            continue
                        if now - start_ts >= float(timeout_sec):
                            results[idx] = {
                                "stock": stock,
                                "success": False,
                                "timeout": True,
                                "message": f"超时({timeout_sec}s)已跳过",
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
                            # 超时也继续补充下一个任务
                            if not cls._is_cancelled(job_id) and next_i < len(stocks):
                                s = stocks[next_i]
                                nfut = ex.submit(worker, (next_i, s))
                                pending.add(nfut)
                                future_meta[nfut] = (next_i, s, time.monotonic())
                                next_i += 1

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
                        # 取消后：把队列里还没提交的也直接标记跳过
                        while next_i < len(stocks):
                            stock = stocks[next_i]
                            results[next_i] = {
                                "stock": stock,
                                "success": True,
                                "skipped": True,
                                "message": "已取消(未执行)",
                            }
                            finished += 1
                            skip += 1
                            next_i += 1
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
                # 关键修复：无论是否取消，都不等待 executor 内“已超时但仍在跑”的任务，否则 job 会被拖死。
                # cancel_futures 仅能取消尚未开始执行的任务。
                ex.shutdown(wait=False, cancel_futures=cancelled)

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

        # 线程池场景：线程内复用实例，避免 1000 股下的反复初始化开销
        svc = cls._get_thread_services()
        kline_service: KLineApplicationService = svc["kline_service"]
        cr_service: CRPointService = svc["cr_service"]
        backtest_service: BacktestService = svc["backtest_service"]

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
                        time=cls._fast_parse_dt(k["time"]),
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
        # 批量回测：默认静默日志 + 跳过“1day COUNT 检查”（我们已经成功读到K线，后续会自然失败/跳过）
        bt_cfg = dict(backtest_config or {})
        bt_cfg.setdefault("quiet", True)
        bt_cfg.setdefault("skip1dayCheck", True)
        # 批量回测：若最后只有C没有R，也要把浮盈浮亏计入结果（将截止日视为“虚拟R”强制平仓）
        bt_cfg.setdefault("closeOpenPositionsAtEnd", True)

        bt = backtest_service.calculate_backtest(
            stock_code=stock_code,
            table_name=table_name,
            c_points=merged_c,
            r_points=r_points,
            backtest_config=bt_cfg,
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

    @classmethod
    def get_market_index(cls, index_name: str = '上证指数', start_date: str = '2024-01-01') -> List[Dict[str, Any]]:
        """获取大盘指数数据"""
        try:
            from infrastructure.persistence.database import DatabaseConnection
            conn = DatabaseConnection.get_connection()
            try:
                cursor = conn.cursor()
                # 简单查询：按日期升序
                sql = "SELECT trade_date, close_price FROM market_index_daily WHERE index_name = %s AND trade_date >= %s ORDER BY trade_date ASC"
                cursor.execute(sql, (index_name, start_date))
                rows = cursor.fetchall()
                # rows list of (date, decimal)
                result = []
                for r in rows:
                    if not r[0] or not r[1]: continue
                    result.append({
                        'date': str(r[0]),
                        'close': float(r[1])
                    })
                return result
            finally:
                conn.close()
        except Exception as e:
            print(f"Error getting market index: {e}")
            return []
